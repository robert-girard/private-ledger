from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Budget, Merchant, Subscription, Transaction, User
from app.services.merchants import normalize_merchant_name

_AVERAGE_MONTH_WINDOW = 3


@dataclass(frozen=True)
class BudgetRecommendation:
    budget: Budget
    source_type: str
    subscription_names: list[str]
    months_used: int


@dataclass(frozen=True)
class BudgetGenerationResult:
    month_start: date
    recommendations: list[BudgetRecommendation]


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _active_subscription_keys(subscriptions: Sequence[Subscription]) -> tuple[set[str], set[str]]:
    merchant_ids = {subscription.merchant_id for subscription in subscriptions if subscription.merchant_id is not None}
    normalized_names = {
        normalize_merchant_name(subscription.display_name)
        for subscription in subscriptions
        if subscription.merchant_id is None
    }
    return merchant_ids, normalized_names


def _replace_month_budgets(session: Session, *, user_id: str, month_start: date) -> None:
    existing = session.scalars(select(Budget).where(Budget.user_id == user_id, Budget.month_start == month_start)).all()
    for budget in existing:
        session.delete(budget)
    session.flush()


def generate_budget_plan(session: Session, *, user: User, month_start: date) -> BudgetGenerationResult:
    target_month = _month_start(month_start)
    active_subscriptions = session.scalars(
        select(Subscription).where(Subscription.user_id == user.id, Subscription.is_active.is_(True))
    ).all()
    merchant_ids, normalized_names = _active_subscription_keys(active_subscriptions)

    _replace_month_budgets(session, user_id=user.id, month_start=target_month)

    recommendations: list[BudgetRecommendation] = []

    fixed_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    fixed_names: dict[str, list[str]] = defaultdict(list)
    for subscription in active_subscriptions:
        category = (subscription.category or "Subscriptions").strip() or "Subscriptions"
        fixed_totals[category] += subscription.amount
        fixed_names[category].append(subscription.display_name)

    for category, total in fixed_totals.items():
        budget = Budget(
            user_id=user.id,
            month_start=target_month,
            category=category,
            planned_amount=_quantize(total),
            spent_amount=Decimal("0.00"),
            is_active=False,
        )
        session.add(budget)
        session.flush()
        recommendations.append(
            BudgetRecommendation(
                budget=budget,
                source_type="subscription",
                subscription_names=sorted(fixed_names[category]),
                months_used=len(fixed_names[category]),
            )
        )

    transactions = session.scalars(
        select(Transaction)
        .options(selectinload(Transaction.merchant))
        .where(Transaction.user_id == user.id, Transaction.posted_on < target_month, Transaction.amount < 0)
        .order_by(Transaction.posted_on.desc(), Transaction.created_at.desc())
    ).all()

    month_totals_by_category: dict[str, dict[date, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0.00")))
    for transaction in transactions:
        if transaction.category is None:
            continue
        merchant = transaction.merchant
        if merchant is not None and merchant.is_transfer:
            continue
        if transaction.merchant_id in merchant_ids:
            continue
        if transaction.merchant_id is None and transaction.normalized_description in normalized_names:
            continue

        tx_month = _month_start(transaction.posted_on)
        category = transaction.category.strip()
        month_totals_by_category[category][tx_month] += abs(transaction.amount)

    for category, monthly_totals in month_totals_by_category.items():
        recent_months = sorted(monthly_totals.keys(), reverse=True)[:_AVERAGE_MONTH_WINDOW]
        if not recent_months:
            continue

        totals = [monthly_totals[month] for month in recent_months]
        average = _quantize(sum(totals, start=Decimal("0.00")) / Decimal(len(totals)))
        if average <= Decimal("0.00"):
            continue

        budget = Budget(
            user_id=user.id,
            month_start=target_month,
            category=category,
            planned_amount=average,
            spent_amount=Decimal("0.00"),
            is_active=False,
        )
        session.add(budget)
        session.flush()
        recommendations.append(
            BudgetRecommendation(
                budget=budget,
                source_type="variable",
                subscription_names=[],
                months_used=len(recent_months),
            )
        )

    session.commit()
    for recommendation in recommendations:
        session.refresh(recommendation.budget)

    return BudgetGenerationResult(
        month_start=target_month,
        recommendations=sorted(recommendations, key=lambda item: (item.source_type, item.budget.category)),
    )


def activate_budget_month(session: Session, *, user: User, month_start: date) -> list[Budget]:
    target_month = _month_start(month_start)
    month_budgets = session.scalars(
        select(Budget).where(Budget.user_id == user.id, Budget.month_start == target_month)
    ).all()
    if not month_budgets:
        raise ValueError("Generate or create budget rows for that month before activation.")

    all_budgets = session.scalars(select(Budget).where(Budget.user_id == user.id)).all()
    for budget in all_budgets:
        budget.is_active = budget.month_start == target_month
    session.commit()
    for budget in month_budgets:
        session.refresh(budget)
    return list(month_budgets)


def refresh_budget_spent_amounts(session: Session, *, user: User, month_start: date) -> list[Budget]:
    target_month = _month_start(month_start)
    month_budgets = session.scalars(
        select(Budget).where(Budget.user_id == user.id, Budget.month_start == target_month)
    ).all()
    if not month_budgets:
        return []

    month_end = date(target_month.year + (1 if target_month.month == 12 else 0), 1 if target_month.month == 12 else target_month.month + 1, 1)
    transactions = session.scalars(
        select(Transaction)
        .options(selectinload(Transaction.merchant))
        .where(
            Transaction.user_id == user.id,
            Transaction.posted_on >= target_month,
            Transaction.posted_on < month_end,
            Transaction.amount < 0,
        )
    ).all()

    spend_by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for transaction in transactions:
        if transaction.category is None:
            continue
        merchant = transaction.merchant
        if merchant is not None and merchant.is_transfer:
            continue
        spend_by_category[transaction.category] += abs(transaction.amount)

    for budget in month_budgets:
        budget.spent_amount = _quantize(spend_by_category.get(budget.category, Decimal("0.00")))

    session.commit()
    for budget in month_budgets:
        session.refresh(budget)
    return list(month_budgets)
