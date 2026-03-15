from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Merchant, MerchantAlias, Transaction, User


@dataclass(frozen=True)
class MerchantSummary:
    merchant: Merchant
    transaction_count: int
    last_seen: date | None


def normalize_merchant_name(value: str) -> str:
    lowered = value.strip().lower()
    alphanumeric = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(alphanumeric.split())


def list_merchant_summaries(session: Session) -> list[MerchantSummary]:
    rows = session.execute(
        select(
            Merchant,
            func.count(Transaction.id).label("transaction_count"),
            func.max(Transaction.posted_on).label("last_seen"),
        )
        .outerjoin(Transaction, Transaction.merchant_id == Merchant.id)
        .group_by(Merchant.id)
        .order_by(Merchant.display_name.asc())
    ).all()

    return [
        MerchantSummary(
            merchant=merchant,
            transaction_count=int(transaction_count or 0),
            last_seen=last_seen,
        )
        for merchant, transaction_count, last_seen in rows
    ]


def create_alias_rule(session: Session, *, merchant: Merchant, alias: str) -> MerchantAlias:
    normalized_alias = normalize_merchant_name(alias)
    existing = session.scalar(select(MerchantAlias).where(MerchantAlias.normalized_alias == normalized_alias))
    if existing is not None and existing.merchant_id != merchant.id:
        raise ValueError("That alias is already assigned to another merchant.")
    if existing is not None:
        return existing

    alias_record = MerchantAlias(
        merchant_id=merchant.id,
        alias=alias.strip(),
        normalized_alias=normalized_alias,
    )
    session.add(alias_record)
    session.flush()
    return alias_record


def recategorize_transactions_for_merchant(
    session: Session,
    *,
    merchant: Merchant,
    user: User,
) -> int:
    aliases = session.scalars(select(MerchantAlias).where(MerchantAlias.merchant_id == merchant.id)).all()
    normalized_names = {normalize_merchant_name(merchant.raw_name), normalize_merchant_name(merchant.display_name)}
    normalized_names.update(alias.normalized_alias for alias in aliases)

    transactions = session.scalars(
        select(Transaction).where(
            Transaction.user_id == user.id,
            (Transaction.merchant_id == merchant.id) | (Transaction.normalized_description.in_(normalized_names)),
        )
    ).all()

    updated = 0
    for transaction in transactions:
        transaction.merchant_id = merchant.id
        transaction.category = merchant.category
        updated += 1
    session.flush()
    return updated


def merge_merchants(
    session: Session,
    *,
    source_merchant: Merchant,
    target_merchant: Merchant,
    actor: User,
) -> int:
    if source_merchant.id == target_merchant.id:
        raise ValueError("Source and target merchants must be different.")

    create_alias_rule(session, merchant=target_merchant, alias=source_merchant.raw_name)

    source_aliases = session.scalars(
        select(MerchantAlias).where(MerchantAlias.merchant_id == source_merchant.id)
    ).all()
    for alias in source_aliases:
        create_alias_rule(session, merchant=target_merchant, alias=alias.alias)
        session.delete(alias)

    transactions = session.scalars(select(Transaction).where(Transaction.merchant_id == source_merchant.id)).all()
    for transaction in transactions:
        transaction.merchant_id = target_merchant.id

    updated_count = recategorize_transactions_for_merchant(
        session,
        merchant=target_merchant,
        user=actor,
    )

    session.delete(source_merchant)
    session.flush()
    return updated_count
