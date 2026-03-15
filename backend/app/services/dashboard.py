from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Budget, Merchant, Subscription, Transaction, User
from app.services.budgets import refresh_budget_spent_amounts


@dataclass(frozen=True)
class DashboardSummary:
    month_start: date | None
    total_budgeted: Decimal
    spent_to_date: Decimal
    projected_month_end: Decimal


@dataclass(frozen=True)
class BurnDownItem:
    category: str
    planned_amount: Decimal
    spent_amount: Decimal
    remaining_amount: Decimal
    status: str


@dataclass(frozen=True)
class UpcomingSubscription:
    id: str
    display_name: str
    category: str | None
    amount: Decimal
    interval: str
    next_expected_on: date | None


@dataclass(frozen=True)
class RecentDashboardTransaction:
    id: str
    posted_on: date
    description: str
    amount: Decimal
    category: str | None
    merchant_name: str | None


@dataclass(frozen=True)
class DashboardAttention:
    upcoming_subscriptions: list[UpcomingSubscription]
    recent_transactions: list[RecentDashboardTransaction]
    unreviewed_merchant_count: int


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _month_end(month_start: date) -> date:
    return date(month_start.year + (1 if month_start.month == 12 else 0), 1 if month_start.month == 12 else month_start.month + 1, 1)


def _active_month_budgets(session: Session, *, user: User) -> list[Budget]:
    active_budgets = session.scalars(
        select(Budget).where(Budget.user_id == user.id, Budget.is_active.is_(True)).order_by(Budget.category.asc())
    ).all()
    if not active_budgets:
        return []
    return refresh_budget_spent_amounts(session, user=user, month_start=active_budgets[0].month_start)


def get_dashboard_summary(session: Session, *, user: User) -> DashboardSummary:
    active_budgets = _active_month_budgets(session, user=user)
    if not active_budgets:
        zero = Decimal("0.00")
        return DashboardSummary(month_start=None, total_budgeted=zero, spent_to_date=zero, projected_month_end=zero)

    month_start = active_budgets[0].month_start
    total_budgeted = _quantize(sum((budget.planned_amount for budget in active_budgets), start=Decimal("0.00")))
    spent_to_date = _quantize(sum((budget.spent_amount for budget in active_budgets), start=Decimal("0.00")))

    month_end = _month_end(month_start)
    latest_tx_date = session.scalar(
        select(func.max(Transaction.posted_on))
        .join(Merchant, Merchant.id == Transaction.merchant_id, isouter=True)
        .where(
            Transaction.user_id == user.id,
            Transaction.posted_on >= month_start,
            Transaction.posted_on < month_end,
            Transaction.amount < 0,
            (Merchant.is_transfer.is_(False)) | (Merchant.id.is_(None)),
        )
    )
    if latest_tx_date is None:
        projected = spent_to_date
    else:
        elapsed_days = max(1, (latest_tx_date - month_start).days + 1)
        total_days = (month_end - month_start).days
        projected = _quantize((spent_to_date / Decimal(elapsed_days)) * Decimal(total_days))

    return DashboardSummary(
        month_start=month_start,
        total_budgeted=total_budgeted,
        spent_to_date=spent_to_date,
        projected_month_end=projected,
    )


def get_budget_burn_down(session: Session, *, user: User) -> list[BurnDownItem]:
    active_budgets = _active_month_budgets(session, user=user)
    items: list[BurnDownItem] = []
    for budget in active_budgets:
        ratio = (budget.spent_amount / budget.planned_amount) if budget.planned_amount > 0 else Decimal("0.00")
        if ratio >= Decimal("1.00"):
            status = "over"
        elif ratio >= Decimal("0.80"):
            status = "warning"
        else:
            status = "safe"
        items.append(
            BurnDownItem(
                category=budget.category,
                planned_amount=budget.planned_amount,
                spent_amount=budget.spent_amount,
                remaining_amount=_quantize(budget.planned_amount - budget.spent_amount),
                status=status,
            )
        )
    return items


def get_dashboard_attention(session: Session, *, user: User) -> DashboardAttention:
    upcoming_rows = session.scalars(
        select(Subscription)
        .where(Subscription.user_id == user.id, Subscription.is_active.is_(True))
        .order_by(Subscription.next_expected_on.asc(), Subscription.display_name.asc())
        .limit(5)
    ).all()

    recent_rows = session.scalars(
        select(Transaction)
        .options(selectinload(Transaction.merchant))
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.posted_on.desc(), Transaction.created_at.desc())
        .limit(5)
    ).all()
    filtered_recent = [
        row
        for row in recent_rows
        if row.merchant is None or row.merchant.is_transfer is False
    ]

    unreviewed_merchant_count = int(
        session.scalar(select(func.count(Merchant.id)).where(Merchant.status == "unreviewed")) or 0
    )

    return DashboardAttention(
        upcoming_subscriptions=[
            UpcomingSubscription(
                id=item.id,
                display_name=item.display_name,
                category=item.category,
                amount=item.amount,
                interval=item.interval,
                next_expected_on=item.next_expected_on,
            )
            for item in upcoming_rows
        ],
        recent_transactions=[
            RecentDashboardTransaction(
                id=item.id,
                posted_on=item.posted_on,
                description=item.description,
                amount=item.amount,
                category=item.category,
                merchant_name=item.merchant.display_name if item.merchant is not None else None,
            )
            for item in filtered_recent
        ],
        unreviewed_merchant_count=unreviewed_merchant_count,
    )
