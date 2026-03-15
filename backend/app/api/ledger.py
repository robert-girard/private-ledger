from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Budget, Import, Merchant, MerchantAlias, Subscription, Transaction, User
from app.db.session import get_db_session
from app.dependencies.auth import get_current_user
from app.importing.parser import ManualMappingRequirement, MappingValidationError, ProfileParseResult
from app.services.imports import commit_import as create_import_commit
from app.services.imports import create_import_preview

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


class ParsedPreviewRowResponse(BaseModel):
    posted_on: str
    description: str
    amount: Decimal


class ImportPreviewResponse(BaseModel):
    import_id: str
    source_filename: str
    stored_path: str
    status: str
    profile_name: str | None
    headers: list[str]
    row_count: int
    unresolved_columns: list[str]
    preview_rows: list[ParsedPreviewRowResponse]


class ManualColumnMappingRequest(BaseModel):
    date: str
    description: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None


class ImportCommitRequest(BaseModel):
    column_mapping: ManualColumnMappingRequest | None = None


class ImportCommitResponse(BaseModel):
    import_id: str
    status: str
    inserted_count: int
    skipped_count: int
    failed_count: int
    row_count: int


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
    item = session.scalar(select(Import).where(Import.id == import_id, Import.user_id == user.id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    return ImportResponse.model_validate(item, from_attributes=True)


@router.post("/imports/preview", response_model=ImportPreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    column_mapping: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ImportPreviewResponse:
    try:
        csv_text = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file must be UTF-8 encoded: {exc.reason}.",
        ) from exc

    try:
        preview = create_import_preview(
            session=session,
            settings=get_settings(),
            user=user,
            filename=file.filename or "upload.csv",
            csv_text=csv_text,
            column_mapping=column_mapping,
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Invalid column mapping.", "errors": [str(exc)]},
        ) from exc

    parse_result = preview.parse_result
    if isinstance(parse_result, MappingValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Invalid column mapping.", "errors": parse_result.errors},
        )

    if isinstance(parse_result, ManualMappingRequirement):
        return ImportPreviewResponse(
            import_id=preview.import_record.id,
            source_filename=preview.import_record.source_filename,
            stored_path=preview.import_record.stored_path or "",
            status=parse_result.status,
            profile_name=None,
            headers=parse_result.headers,
            row_count=0,
            unresolved_columns=list(parse_result.unresolved_columns),
            preview_rows=[],
        )

    if isinstance(parse_result, ProfileParseResult):
        return ImportPreviewResponse(
            import_id=preview.import_record.id,
            source_filename=preview.import_record.source_filename,
            stored_path=preview.import_record.stored_path or "",
            status=parse_result.status,
            profile_name=parse_result.profile_name,
            headers=parse_result.headers,
            row_count=len(parse_result.rows),
            unresolved_columns=[],
            preview_rows=[
                ParsedPreviewRowResponse(
                    posted_on=row.posted_on,
                    description=row.description,
                    amount=row.amount,
                )
                for row in parse_result.rows
            ],
        )

    raise AssertionError("Unhandled import preview result.")


@router.post("/imports/{import_id}/commit", response_model=ImportCommitResponse)
def commit_import_rows(
    import_id: str,
    payload: ImportCommitRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ImportCommitResponse:
    import_record = session.scalar(select(Import).where(Import.id == import_id, Import.user_id == user.id))
    if import_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    column_mapping = payload.column_mapping.model_dump_json() if payload.column_mapping is not None else None

    try:
        result = create_import_commit(
            session=session,
            settings=get_settings(),
            user=user,
            import_record=import_record,
            column_mapping=column_mapping,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Import commit failed.", "errors": [str(exc)]},
        ) from exc

    return ImportCommitResponse(
        import_id=result.import_record.id,
        status=result.import_record.import_status,
        inserted_count=result.inserted_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
        row_count=result.import_record.row_count,
    )


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
