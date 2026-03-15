from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Budget, Import, Merchant, MerchantAlias, Subscription, Transaction, User
from app.db.session import get_db_session
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/api", tags=["ledger"])


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    is_admin: bool


class TransactionResponse(BaseModel):
    id: str
    user_id: str
    import_id: str | None
    merchant_id: str | None
    posted_on: date
    description: str
    normalized_description: str
    amount: Decimal
    currency: str
    category: str | None
    notes: str | None
    dedupe_hash: str


class ImportResponse(BaseModel):
    id: str
    user_id: str
    source_filename: str
    source_bank: str | None
    import_status: str
    imported_at: datetime | None
    row_count: int
    stored_path: str | None


class SubscriptionResponse(BaseModel):
    id: str
    user_id: str
    merchant_id: str | None
    display_name: str
    category: str | None
    interval: str
    amount: Decimal
    is_active: bool
    last_charged_on: date | None
    next_expected_on: date | None


class BudgetResponse(BaseModel):
    id: str
    user_id: str
    month_start: date
    category: str
    planned_amount: Decimal
    spent_amount: Decimal
    is_active: bool


class MerchantResponse(BaseModel):
    id: str
    raw_name: str
    display_name: str
    category: str | None
    status: str
    is_transfer: bool
    notes: str | None


class MerchantAliasResponse(BaseModel):
    id: str
    merchant_id: str
    alias: str
    normalized_alias: str


def _user_scoped_resource(
    session: Session,
    model: type[Transaction] | type[Import] | type[Subscription] | type[Budget],
    resource_id: str,
    user_id: str,
) -> Transaction | Import | Subscription | Budget:
    resource = session.scalar(
        select(model).where(model.id == resource_id, model.user_id == user_id)
    )
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    return resource


@router.get("/me", response_model=CurrentUserResponse)
def current_user(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(user)


@router.get("/transactions", response_model=list[TransactionResponse])
def list_transactions(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[TransactionResponse]:
    items = session.scalars(select(Transaction).where(Transaction.user_id == user.id)).all()
    return [TransactionResponse.model_validate(item, from_attributes=True) for item in items]


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> TransactionResponse:
    item = _user_scoped_resource(session, Transaction, transaction_id, user.id)
    return TransactionResponse.model_validate(item, from_attributes=True)


@router.get("/imports", response_model=list[ImportResponse])
def list_imports(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[ImportResponse]:
    items = session.scalars(select(Import).where(Import.user_id == user.id)).all()
    return [ImportResponse.model_validate(item, from_attributes=True) for item in items]


@router.get("/imports/{import_id}", response_model=ImportResponse)
def get_import(
    import_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ImportResponse:
    item = _user_scoped_resource(session, Import, import_id, user.id)
    return ImportResponse.model_validate(item, from_attributes=True)


@router.get("/subscriptions", response_model=list[SubscriptionResponse])
def list_subscriptions(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[SubscriptionResponse]:
    items = session.scalars(select(Subscription).where(Subscription.user_id == user.id)).all()
    return [SubscriptionResponse.model_validate(item, from_attributes=True) for item in items]


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
def get_subscription(
    subscription_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> SubscriptionResponse:
    item = _user_scoped_resource(session, Subscription, subscription_id, user.id)
    return SubscriptionResponse.model_validate(item, from_attributes=True)


@router.get("/budgets", response_model=list[BudgetResponse])
def list_budgets(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[BudgetResponse]:
    items = session.scalars(select(Budget).where(Budget.user_id == user.id)).all()
    return [BudgetResponse.model_validate(item, from_attributes=True) for item in items]


@router.get("/budgets/{budget_id}", response_model=BudgetResponse)
def get_budget(
    budget_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> BudgetResponse:
    item = _user_scoped_resource(session, Budget, budget_id, user.id)
    return BudgetResponse.model_validate(item, from_attributes=True)


@router.get("/merchants", response_model=list[MerchantResponse])
def list_merchants(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[MerchantResponse]:
    items = session.scalars(select(Merchant)).all()
    return [MerchantResponse.model_validate(item, from_attributes=True) for item in items]


@router.get("/merchant-aliases", response_model=list[MerchantAliasResponse])
def list_merchant_aliases(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[MerchantAliasResponse]:
    items = session.scalars(select(MerchantAlias)).all()
    return [MerchantAliasResponse.model_validate(item, from_attributes=True) for item in items]
