from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Merchant, Subscription, SubscriptionInterval, Transaction, User
from app.services.merchants import normalize_merchant_name

_FIXED_AMOUNT_TOLERANCE = Decimal("2.00")
_FIXED_AMOUNT_VARIANCE_RATIO = Decimal("0.10")
_MONTHLY_RANGE = range(25, 36)
_ANNUAL_MIN_DAYS = 330
_ANNUAL_MAX_DAYS = 390


@dataclass(frozen=True)
class RecentSubscriptionMatch:
    transaction_id: str
    posted_on: date
    description: str
    amount: Decimal
    category: str | None


@dataclass(frozen=True)
class SubscriptionWithMatches:
    subscription: Subscription
    recent_matches: list[RecentSubscriptionMatch]


@dataclass(frozen=True)
class SubscriptionInput:
    display_name: str
    category: str | None
    interval: SubscriptionInterval
    amount: Decimal
    is_active: bool
    merchant_id: str | None = None
    last_charged_on: date | None = None
    next_expected_on: date | None = None


@dataclass(frozen=True)
class DetectionCandidate:
    merchant_id: str | None
    normalized_name: str
    display_name: str
    category: str | None
    interval: SubscriptionInterval
    amount: Decimal
    last_charged_on: date
    next_expected_on: date | None
    recent_match_transaction_id: str


@dataclass(frozen=True)
class DetectSubscriptionsResult:
    subscriptions: list[Subscription]
    detected_count: int


def _intervals_in_days(dates: list[date]) -> list[int]:
    return [(current - previous).days for previous, current in zip(dates, dates[1:], strict=False)]


def _amount_is_fixed(amounts: list[Decimal]) -> bool:
    absolute_amounts = [abs(amount) for amount in amounts]
    baseline = sum(absolute_amounts, start=Decimal("0.00")) / Decimal(len(absolute_amounts))
    tolerance = max(_FIXED_AMOUNT_TOLERANCE, (baseline * _FIXED_AMOUNT_VARIANCE_RATIO).quantize(Decimal("0.01")))
    return max(absolute_amounts) - min(absolute_amounts) <= tolerance


def _average_amount(amounts: list[Decimal]) -> Decimal:
    absolute_amounts = [abs(amount) for amount in amounts]
    average = sum(absolute_amounts, start=Decimal("0.00")) / Decimal(len(absolute_amounts))
    return average.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _expected_next_charge(last_charged_on: date, interval: SubscriptionInterval) -> date | None:
    if interval in {"monthly", "variable"}:
        return last_charged_on + timedelta(days=30)
    if interval == "annual":
        return last_charged_on + timedelta(days=365)
    return None


def _classify_recurring_pattern(transactions: list[Transaction]) -> tuple[SubscriptionInterval, Decimal] | None:
    if len(transactions) < 2:
        return None

    ordered = sorted(transactions, key=lambda transaction: transaction.posted_on)
    dates = [transaction.posted_on for transaction in ordered]
    amounts = [transaction.amount for transaction in ordered]
    day_gaps = _intervals_in_days(dates)
    if not day_gaps:
        return None

    if len(ordered) >= 2 and all(_ANNUAL_MIN_DAYS <= gap <= _ANNUAL_MAX_DAYS for gap in day_gaps):
        if _amount_is_fixed(amounts):
            return "annual", _average_amount(amounts)
        return None

    monthly_like = len(ordered) >= 3 and all(gap in _MONTHLY_RANGE for gap in day_gaps)
    if not monthly_like:
        return None

    if _amount_is_fixed(amounts):
        return "monthly", _average_amount(amounts)

    return "variable", _average_amount(amounts)


def _candidate_key(transaction: Transaction) -> tuple[str | None, str]:
    return transaction.merchant_id, transaction.normalized_description


def _build_detection_candidate(transactions: list[Transaction]) -> DetectionCandidate | None:
    ordered = sorted(transactions, key=lambda transaction: transaction.posted_on)
    classification = _classify_recurring_pattern(ordered)
    if classification is None:
        return None

    interval, amount = classification
    latest = ordered[-1]
    merchant_name = latest.merchant.display_name if latest.merchant is not None else latest.description.strip()
    category = latest.category or (latest.merchant.category if latest.merchant is not None else None)

    return DetectionCandidate(
        merchant_id=latest.merchant_id,
        normalized_name=latest.normalized_description,
        display_name=merchant_name,
        category=category,
        interval=interval,
        amount=amount,
        last_charged_on=latest.posted_on,
        next_expected_on=_expected_next_charge(latest.posted_on, interval),
        recent_match_transaction_id=latest.id,
    )


def detect_recurring_subscriptions(session: Session, *, user: User) -> DetectSubscriptionsResult:
    transactions = session.scalars(
        select(Transaction)
        .options(selectinload(Transaction.merchant))
        .where(Transaction.user_id == user.id, Transaction.amount < 0)
        .order_by(Transaction.posted_on.asc(), Transaction.created_at.asc())
    ).all()

    grouped: dict[tuple[str | None, str], list[Transaction]] = {}
    for transaction in transactions:
        grouped.setdefault(_candidate_key(transaction), []).append(transaction)

    existing_subscriptions = session.scalars(select(Subscription).where(Subscription.user_id == user.id)).all()
    subscriptions_by_merchant = {
        subscription.merchant_id: subscription for subscription in existing_subscriptions if subscription.merchant_id is not None
    }
    subscriptions_by_name = {
        normalize_merchant_name(subscription.display_name): subscription
        for subscription in existing_subscriptions
        if subscription.merchant_id is None
    }

    detected: list[Subscription] = []
    for transaction_group in grouped.values():
        candidate = _build_detection_candidate(transaction_group)
        if candidate is None:
            continue

        existing = None
        if candidate.merchant_id is not None:
            existing = subscriptions_by_merchant.get(candidate.merchant_id)
        if existing is None:
            existing = subscriptions_by_name.get(candidate.normalized_name)

        if existing is None:
            existing = Subscription(
                user_id=user.id,
                merchant_id=candidate.merchant_id,
                display_name=candidate.display_name,
                category=candidate.category,
                interval=candidate.interval,
                amount=candidate.amount,
                is_active=True,
                last_charged_on=candidate.last_charged_on,
                next_expected_on=candidate.next_expected_on,
                recent_match_transaction_id=candidate.recent_match_transaction_id,
            )
            session.add(existing)
            session.flush()
            if existing.merchant_id is not None:
                subscriptions_by_merchant[existing.merchant_id] = existing
            else:
                subscriptions_by_name[normalize_merchant_name(existing.display_name)] = existing
        else:
            existing.merchant_id = candidate.merchant_id
            existing.display_name = candidate.display_name
            existing.category = candidate.category
            existing.interval = candidate.interval
            existing.amount = candidate.amount
            existing.last_charged_on = candidate.last_charged_on
            existing.next_expected_on = candidate.next_expected_on
            existing.recent_match_transaction_id = candidate.recent_match_transaction_id

        detected.append(existing)

    session.commit()
    for subscription in detected:
        session.refresh(subscription)

    return DetectSubscriptionsResult(subscriptions=detected, detected_count=len(detected))


def create_subscription(session: Session, *, user: User, payload: SubscriptionInput) -> Subscription:
    merchant = session.get(Merchant, payload.merchant_id) if payload.merchant_id is not None else None
    subscription = Subscription(
        user_id=user.id,
        merchant_id=merchant.id if merchant is not None else None,
        display_name=payload.display_name.strip(),
        category=payload.category.strip() if payload.category is not None and payload.category.strip() else None,
        interval=payload.interval,
        amount=payload.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        is_active=payload.is_active,
        last_charged_on=payload.last_charged_on,
        next_expected_on=payload.next_expected_on,
    )
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return subscription


def update_subscription(subscription: Subscription, *, payload: SubscriptionInput, merchant: Merchant | None) -> Subscription:
    subscription.merchant_id = merchant.id if merchant is not None else None
    subscription.display_name = payload.display_name.strip()
    subscription.category = payload.category.strip() if payload.category is not None and payload.category.strip() else None
    subscription.interval = payload.interval
    subscription.amount = payload.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    subscription.is_active = payload.is_active
    subscription.last_charged_on = payload.last_charged_on
    subscription.next_expected_on = payload.next_expected_on
    return subscription


def get_subscription_with_matches(
    session: Session,
    *,
    subscription: Subscription,
    limit: int = 5,
) -> SubscriptionWithMatches:
    if subscription.merchant_id is not None:
        transaction_filters = [Transaction.merchant_id == subscription.merchant_id]
    else:
        normalized_name = normalize_merchant_name(subscription.display_name)
        transaction_filters = [Transaction.normalized_description == normalized_name]

    matches = session.scalars(
        select(Transaction)
        .where(Transaction.user_id == subscription.user_id, Transaction.amount < 0, *transaction_filters)
        .order_by(Transaction.posted_on.desc(), Transaction.created_at.desc())
        .limit(limit)
    ).all()

    return SubscriptionWithMatches(
        subscription=subscription,
        recent_matches=[
            RecentSubscriptionMatch(
                transaction_id=match.id,
                posted_on=match.posted_on,
                description=match.description,
                amount=match.amount,
                category=match.category,
            )
            for match in matches
        ],
    )
