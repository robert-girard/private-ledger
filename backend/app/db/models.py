from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MerchantStatus = Literal["unreviewed", "reviewed"]
SubscriptionInterval = Literal["monthly", "annual", "variable"]


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    password_salt: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean(), default=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)

    imports: Mapped[list[Import]] = relationship(back_populates="user")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="user")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user")
    budgets: Mapped[list[Budget]] = relationship(back_populates="user")


class RefreshTokenBlocklist(Base):
    __tablename__ = "refresh_token_blocklist"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    token_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(), default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(DateTime())


class Merchant(TimestampMixin, Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    raw_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[MerchantStatus] = mapped_column(String(32), default="unreviewed")
    is_transfer: Mapped[bool] = mapped_column(Boolean(), default=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    aliases: Mapped[list[MerchantAlias]] = relationship(back_populates="merchant")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="merchant")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="merchant")


class MerchantAlias(TimestampMixin, Base):
    __tablename__ = "merchant_aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    normalized_alias: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    merchant: Mapped[Merchant] = relationship(back_populates="aliases")


class Import(TimestampMixin, Base):
    __tablename__ = "imports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_filename: Mapped[str] = mapped_column(String(255))
    source_bank: Mapped[str | None] = mapped_column(String(120), nullable=True)
    import_status: Mapped[str] = mapped_column(String(32), default="pending")
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer(), default=0)
    stored_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="imports")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="source_import")


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    import_id: Mapped[str | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"), nullable=True)
    merchant_id: Mapped[str | None] = mapped_column(
        ForeignKey("merchants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    posted_on: Mapped[date] = mapped_column(Date(), index=True)
    description: Mapped[str] = mapped_column(String(255))
    normalized_description: Mapped[str] = mapped_column(String(255), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    dedupe_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    user: Mapped[User] = relationship(back_populates="transactions")
    source_import: Mapped[Import | None] = relationship(back_populates="transactions")
    merchant: Mapped[Merchant | None] = relationship(back_populates="transactions")


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    merchant_id: Mapped[str | None] = mapped_column(
        ForeignKey("merchants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    interval: Mapped[SubscriptionInterval] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)
    last_charged_on: Mapped[date | None] = mapped_column(Date(), nullable=True)
    next_expected_on: Mapped[date | None] = mapped_column(Date(), nullable=True)
    recent_match_transaction_id: Mapped[str | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )

    user: Mapped[User] = relationship(back_populates="subscriptions")
    merchant: Mapped[Merchant | None] = relationship(back_populates="subscriptions")


class Budget(TimestampMixin, Base):
    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    month_start: Mapped[date] = mapped_column(Date(), index=True)
    category: Mapped[str] = mapped_column(String(120))
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    spent_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    is_active: Mapped[bool] = mapped_column(Boolean(), default=False)

    user: Mapped[User] = relationship(back_populates="budgets")
