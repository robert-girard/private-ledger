from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Sequence, cast

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Budget, Transaction, User


@dataclass(frozen=True)
class MoneyFlowRow:
    direction: str
    category: str
    amount: Decimal


@dataclass(frozen=True)
class CategoryBreakdownRow:
    category: str
    amount: Decimal
    transaction_count: int
    share: Decimal


@dataclass(frozen=True)
class MonthlyTrendRow:
    month_start: date
    income_total: Decimal
    expense_total: Decimal
    net_total: Decimal


@dataclass(frozen=True)
class BudgetVsActualRow:
    month_start: date
    category: str
    planned_amount: Decimal
    actual_amount: Decimal
    variance_amount: Decimal


@dataclass(frozen=True)
class TopMerchantRow:
    merchant_id: str | None
    merchant_name: str
    category: str | None
    amount: Decimal
    transaction_count: int


@dataclass(frozen=True)
class IncomeExpenseSummary:
    start_date: date | None
    end_date: date | None
    income_total: Decimal
    expense_total: Decimal
    net_total: Decimal


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _month_end(value: date) -> date:
    return date(value.year + (1 if value.month == 12 else 0), 1 if value.month == 12 else value.month + 1, 1)


def _filtered_transactions(
    session: Session,
    *,
    user: User,
    start_date: date | None,
    end_date: date | None,
) -> list[Transaction]:
    query = (
        select(Transaction)
        .options(selectinload(Transaction.merchant))
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.posted_on.asc(), Transaction.created_at.asc())
    )
    if start_date is not None:
        query = query.where(Transaction.posted_on >= start_date)
    if end_date is not None:
        query = query.where(Transaction.posted_on <= end_date)
    return list(session.scalars(query).all())


def _reporting_transactions(
    session: Session,
    *,
    user: User,
    start_date: date | None,
    end_date: date | None,
) -> list[Transaction]:
    return list(
        [
        transaction
        for transaction in _filtered_transactions(session, user=user, start_date=start_date, end_date=end_date)
        if transaction.merchant is None or transaction.merchant.is_transfer is False
        ]
    )


def get_money_flow(
    session: Session,
    *,
    user: User,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[MoneyFlowRow]:
    totals: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0.00"))
    for transaction in _reporting_transactions(session, user=user, start_date=start_date, end_date=end_date):
        direction = "income" if transaction.amount > 0 else "expense"
        category = transaction.category or ("Income" if direction == "income" else "Uncategorized")
        totals[(direction, category)] += abs(transaction.amount)

    return [
        MoneyFlowRow(direction=direction, category=category, amount=_quantize(amount))
        for (direction, category), amount in sorted(totals.items(), key=lambda item: (item[0][0], -item[1], item[0][1]))
    ]


def get_category_breakdown(
    session: Session,
    *,
    user: User,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[CategoryBreakdownRow]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    counts: dict[str, int] = defaultdict(int)
    for transaction in _reporting_transactions(session, user=user, start_date=start_date, end_date=end_date):
        if transaction.amount >= 0:
            continue
        category = transaction.category or "Uncategorized"
        totals[category] += abs(transaction.amount)
        counts[category] += 1

    total_spend = sum(totals.values(), start=Decimal("0.00"))
    rows = [
        CategoryBreakdownRow(
            category=category,
            amount=_quantize(amount),
            transaction_count=counts[category],
            share=_quantize((amount / total_spend) if total_spend > 0 else Decimal("0.00")),
        )
        for category, amount in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]
    return rows


def get_monthly_trend(
    session: Session,
    *,
    user: User,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[MonthlyTrendRow]:
    grouped: dict[date, dict[str, Decimal]] = defaultdict(lambda: {"income": Decimal("0.00"), "expense": Decimal("0.00")})
    for transaction in _reporting_transactions(session, user=user, start_date=start_date, end_date=end_date):
        month_start = _month_start(transaction.posted_on)
        if transaction.amount > 0:
            grouped[month_start]["income"] += transaction.amount
        else:
            grouped[month_start]["expense"] += abs(transaction.amount)

    return [
        MonthlyTrendRow(
            month_start=month_start,
            income_total=_quantize(values["income"]),
            expense_total=_quantize(values["expense"]),
            net_total=_quantize(values["income"] - values["expense"]),
        )
        for month_start, values in sorted(grouped.items())
    ]


def get_budget_vs_actual(
    session: Session,
    *,
    user: User,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[BudgetVsActualRow]:
    budget_query = select(Budget).where(Budget.user_id == user.id).order_by(Budget.month_start.asc(), Budget.category.asc())
    if start_date is not None:
        budget_query = budget_query.where(Budget.month_start >= _month_start(start_date))
    if end_date is not None:
        budget_query = budget_query.where(Budget.month_start <= _month_start(end_date))

    budgets = session.scalars(budget_query).all()
    if not budgets:
        return []

    month_actuals: dict[tuple[date, str], Decimal] = defaultdict(lambda: Decimal("0.00"))
    actual_start = budgets[0].month_start
    actual_end = _month_end(budgets[-1].month_start)
    for transaction in _reporting_transactions(session, user=user, start_date=actual_start, end_date=actual_end):
        if transaction.amount >= 0 or transaction.category is None:
            continue
        transaction_month = _month_start(transaction.posted_on)
        month_actuals[(transaction_month, transaction.category)] += abs(transaction.amount)

    return [
        BudgetVsActualRow(
            month_start=budget.month_start,
            category=budget.category,
            planned_amount=_quantize(budget.planned_amount),
            actual_amount=_quantize(month_actuals.get((budget.month_start, budget.category), Decimal("0.00"))),
            variance_amount=_quantize(budget.planned_amount - month_actuals.get((budget.month_start, budget.category), Decimal("0.00"))),
        )
        for budget in budgets
    ]


def get_top_merchants(
    session: Session,
    *,
    user: User,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 10,
) -> list[TopMerchantRow]:
    totals: dict[tuple[str | None, str], Decimal] = defaultdict(lambda: Decimal("0.00"))
    counts: dict[tuple[str | None, str], int] = defaultdict(int)
    categories: dict[tuple[str | None, str], str | None] = {}
    for transaction in _reporting_transactions(session, user=user, start_date=start_date, end_date=end_date):
        if transaction.amount >= 0:
            continue
        merchant_name = transaction.merchant.display_name if transaction.merchant is not None else transaction.description
        key = (transaction.merchant_id, merchant_name)
        totals[key] += abs(transaction.amount)
        counts[key] += 1
        categories[key] = transaction.merchant.category if transaction.merchant is not None else categories.get(key) or transaction.category

    rows = [
        TopMerchantRow(
            merchant_id=merchant_id,
            merchant_name=merchant_name,
            category=categories[(merchant_id, merchant_name)],
            amount=_quantize(amount),
            transaction_count=counts[(merchant_id, merchant_name)],
        )
        for (merchant_id, merchant_name), amount in sorted(
            totals.items(),
            key=lambda item: (-item[1], item[0][1].lower()),
        )[:limit]
    ]
    return rows


def get_income_expense_summary(
    session: Session,
    *,
    user: User,
    start_date: date | None = None,
    end_date: date | None = None,
) -> IncomeExpenseSummary:
    income_total = Decimal("0.00")
    expense_total = Decimal("0.00")
    for transaction in _reporting_transactions(session, user=user, start_date=start_date, end_date=end_date):
        if transaction.amount > 0:
            income_total += transaction.amount
        else:
            expense_total += abs(transaction.amount)

    return IncomeExpenseSummary(
        start_date=start_date,
        end_date=end_date,
        income_total=_quantize(income_total),
        expense_total=_quantize(expense_total),
        net_total=_quantize(income_total - expense_total),
    )


def report_rows_as_dicts(rows: Sequence[object]) -> list[dict[str, object]]:
    return [cast(dict[str, object], asdict(cast(Any, row))) for row in rows]
