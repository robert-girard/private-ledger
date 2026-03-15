from __future__ import annotations

import csv
import json
from io import StringIO
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Sequence, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    Budget,
    Import,
    Merchant,
    MerchantAlias,
    MerchantStatus,
    Subscription,
    SubscriptionInterval,
    Transaction,
    User,
)
from app.db.session import get_db_session
from app.dependencies.auth import get_current_user
from app.importing.parser import ManualMappingRequirement, MappingValidationError, ProfileParseResult
from app.services.imports import commit_import as create_import_commit
from app.services.imports import create_import_preview
from app.services.merchants import (
    create_alias_rule,
    list_merchant_summaries,
    merge_merchants,
    recategorize_transactions_for_merchant,
)
from app.services.subscriptions import (
    SubscriptionInput,
    create_subscription,
    detect_recurring_subscriptions,
    get_subscription_with_matches,
    update_subscription as apply_subscription_update,
)

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
    merchant_name: str | None = None
    import_source: str | None = None


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
    recent_match_transaction_id: str | None = None


class SubscriptionMatchResponse(BaseModel):
    transaction_id: str
    posted_on: date
    description: str
    amount: Decimal
    category: str | None


class SubscriptionDetailResponse(SubscriptionResponse):
    recent_matches: list[SubscriptionMatchResponse] = Field(default_factory=list)


class SubscriptionUpsertRequest(BaseModel):
    display_name: str
    category: str | None = None
    interval: Literal["monthly", "annual", "variable"]
    amount: Decimal
    is_active: bool = True
    merchant_id: str | None = None
    last_charged_on: date | None = None
    next_expected_on: date | None = None


class SubscriptionDetectResponse(BaseModel):
    detected_count: int
    subscriptions: list[SubscriptionResponse]


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
    transaction_count: int = 0
    last_seen: date | None = None


class MerchantAliasResponse(BaseModel):
    id: str
    merchant_id: str
    alias: str
    normalized_alias: str


class MerchantUpdateRequest(BaseModel):
    display_name: str | None = None
    category: str | None = None
    status: str | None = None
    is_transfer: bool | None = None
    notes: str | None = None


class MerchantAliasCreateRequest(BaseModel):
    alias: str


class MerchantMergeRequest(BaseModel):
    target_merchant_id: str


class MerchantBulkCategoryRequest(BaseModel):
    merchant_ids: list[str]
    category: str | None


class MerchantBulkCategoryResponse(BaseModel):
    updated_count: int


class MerchantRecategorizeResponse(BaseModel):
    updated_count: int


class TransactionUpdateRequest(BaseModel):
    category: str | None


class TransactionBulkCategoryRequest(BaseModel):
    transaction_ids: list[str]
    category: str | None


class TransactionBulkDeleteRequest(BaseModel):
    transaction_ids: list[str]


class TransactionBulkResult(BaseModel):
    updated_count: int = 0
    deleted_count: int = 0


def _transaction_query_for_user(user_id: str):
    return (
        select(Transaction, Merchant.display_name, Import.source_filename)
        .outerjoin(Merchant, Merchant.id == Transaction.merchant_id)
        .outerjoin(Import, Import.id == Transaction.import_id)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.posted_on.desc(), Transaction.created_at.desc())
    )


def _transaction_response_rows(
    rows: Sequence[tuple[Transaction, str | None, str | None]],
) -> list[TransactionResponse]:
    return [
        TransactionResponse(
            id=transaction.id,
            user_id=transaction.user_id,
            import_id=transaction.import_id,
            merchant_id=transaction.merchant_id,
            posted_on=transaction.posted_on,
            description=transaction.description,
            normalized_description=transaction.normalized_description,
            amount=transaction.amount,
            currency=transaction.currency,
            category=transaction.category,
            notes=transaction.notes,
            dedupe_hash=transaction.dedupe_hash,
            merchant_name=merchant_name,
            import_source=import_source,
        )
        for transaction, merchant_name, import_source in rows
    ]


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
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    merchant_id: str | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    import_id: str | None = None,
    import_source: str | None = None,
    categorized: bool | None = None,
    uncategorized_only: bool = False,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[TransactionResponse]:
    query = _transaction_query_for_user(user.id)

    if start_date is not None:
        query = query.where(Transaction.posted_on >= start_date)
    if end_date is not None:
        query = query.where(Transaction.posted_on <= end_date)
    if category is not None:
        query = query.where(Transaction.category == category)
    if merchant_id is not None:
        query = query.where(Transaction.merchant_id == merchant_id)
    if amount_min is not None:
        query = query.where(Transaction.amount >= amount_min)
    if amount_max is not None:
        query = query.where(Transaction.amount <= amount_max)
    if import_id is not None:
        query = query.where(Transaction.import_id == import_id)
    if import_source is not None:
        query = query.where(Import.source_filename == import_source)
    if uncategorized_only:
        query = query.where(Transaction.category.is_(None))
    elif categorized is True:
        query = query.where(Transaction.category.is_not(None))
    elif categorized is False:
        query = query.where(Transaction.category.is_(None))

    raw_rows = session.execute(query).all()
    rows = [(row[0], row[1], row[2]) for row in raw_rows]
    return _transaction_response_rows(rows)


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: str,
    payload: TransactionUpdateRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> TransactionResponse:
    transaction = cast(Transaction, _user_scoped_resource(session, Transaction, transaction_id, user.id))
    transaction.category = payload.category.strip() if payload.category is not None and payload.category.strip() else None
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return get_transaction(transaction_id, user, session)


@router.post("/transactions/bulk-category", response_model=TransactionBulkResult)
def bulk_update_transactions(
    payload: TransactionBulkCategoryRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> TransactionBulkResult:
    transactions = session.scalars(
        select(Transaction).where(Transaction.user_id == user.id, Transaction.id.in_(payload.transaction_ids))
    ).all()
    for transaction in transactions:
        transaction.category = payload.category.strip() if payload.category is not None and payload.category.strip() else None
    session.commit()
    return TransactionBulkResult(updated_count=len(transactions))


@router.post("/transactions/bulk-delete", response_model=TransactionBulkResult)
def bulk_delete_transactions(
    payload: TransactionBulkDeleteRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> TransactionBulkResult:
    transactions = session.scalars(
        select(Transaction).where(Transaction.user_id == user.id, Transaction.id.in_(payload.transaction_ids))
    ).all()
    deleted_count = len(transactions)
    for transaction in transactions:
        session.delete(transaction)
    session.commit()
    return TransactionBulkResult(deleted_count=deleted_count)


@router.get("/transactions/export", response_class=PlainTextResponse)
def export_transactions(
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    merchant_id: str | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    import_id: str | None = None,
    import_source: str | None = None,
    categorized: bool | None = None,
    uncategorized_only: bool = False,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> PlainTextResponse:
    rows = list_transactions(
        start_date=start_date,
        end_date=end_date,
        category=category,
        merchant_id=merchant_id,
        amount_min=amount_min,
        amount_max=amount_max,
        import_id=import_id,
        import_source=import_source,
        categorized=categorized,
        uncategorized_only=uncategorized_only,
        user=user,
        session=session,
    )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["posted_on", "description", "merchant_name", "amount", "category", "import_source"])
    for row in rows:
        writer.writerow([row.posted_on.isoformat(), row.description, row.merchant_name, row.amount, row.category, row.import_source])

    return PlainTextResponse(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> TransactionResponse:
    item = session.scalar(select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user.id))
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")

    merchant_name = None
    import_source = None
    if item.merchant_id is not None:
        merchant_name = session.scalar(select(Merchant.display_name).where(Merchant.id == item.merchant_id))
    if item.import_id is not None:
        import_source = session.scalar(select(Import.source_filename).where(Import.id == item.import_id))
    return TransactionResponse(
        id=item.id,
        user_id=item.user_id,
        import_id=item.import_id,
        merchant_id=item.merchant_id,
        posted_on=item.posted_on,
        description=item.description,
        normalized_description=item.normalized_description,
        amount=item.amount,
        currency=item.currency,
        category=item.category,
        notes=item.notes,
        dedupe_hash=item.dedupe_hash,
        merchant_name=merchant_name,
        import_source=import_source,
    )


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


@router.post("/subscriptions/detect", response_model=SubscriptionDetectResponse)
def detect_subscriptions(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> SubscriptionDetectResponse:
    result = detect_recurring_subscriptions(session, user=user)
    return SubscriptionDetectResponse(
        detected_count=result.detected_count,
        subscriptions=[SubscriptionResponse.model_validate(item, from_attributes=True) for item in result.subscriptions],
    )


@router.post("/subscriptions", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription_entry(
    payload: SubscriptionUpsertRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> SubscriptionResponse:
    if payload.merchant_id is not None and session.get(Merchant, payload.merchant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")

    subscription = create_subscription(
        session,
        user=user,
        payload=SubscriptionInput(
            display_name=payload.display_name,
            category=payload.category,
            interval=cast(SubscriptionInterval, payload.interval),
            amount=payload.amount,
            is_active=payload.is_active,
            merchant_id=payload.merchant_id,
            last_charged_on=payload.last_charged_on,
            next_expected_on=payload.next_expected_on,
        ),
    )
    return SubscriptionResponse.model_validate(subscription, from_attributes=True)


@router.get("/subscriptions", response_model=list[SubscriptionResponse])
def list_subscriptions(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[SubscriptionResponse]:
    items = session.scalars(select(Subscription).where(Subscription.user_id == user.id)).all()
    return [SubscriptionResponse.model_validate(item, from_attributes=True) for item in items]


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
def update_subscription(
    subscription_id: str,
    payload: SubscriptionUpsertRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> SubscriptionResponse:
    subscription = cast(Subscription, _user_scoped_resource(session, Subscription, subscription_id, user.id))
    merchant = None
    if payload.merchant_id is not None:
        merchant = session.get(Merchant, payload.merchant_id)
        if merchant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")

    apply_subscription_update(
        subscription,
        payload=SubscriptionInput(
            display_name=payload.display_name,
            category=payload.category,
            interval=cast(SubscriptionInterval, payload.interval),
            amount=payload.amount,
            is_active=payload.is_active,
            merchant_id=payload.merchant_id,
            last_charged_on=payload.last_charged_on,
            next_expected_on=payload.next_expected_on,
        ),
        merchant=merchant,
    )
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return SubscriptionResponse.model_validate(subscription, from_attributes=True)


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionDetailResponse)
def get_subscription(
    subscription_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> SubscriptionDetailResponse:
    item = cast(Subscription, _user_scoped_resource(session, Subscription, subscription_id, user.id))
    detail = get_subscription_with_matches(session, subscription=item)
    return SubscriptionDetailResponse(
        id=detail.subscription.id,
        user_id=detail.subscription.user_id,
        merchant_id=detail.subscription.merchant_id,
        display_name=detail.subscription.display_name,
        category=detail.subscription.category,
        interval=detail.subscription.interval,
        amount=detail.subscription.amount,
        is_active=detail.subscription.is_active,
        last_charged_on=detail.subscription.last_charged_on,
        next_expected_on=detail.subscription.next_expected_on,
        recent_match_transaction_id=detail.subscription.recent_match_transaction_id,
        recent_matches=[
            SubscriptionMatchResponse(
                transaction_id=match.transaction_id,
                posted_on=match.posted_on,
                description=match.description,
                amount=match.amount,
                category=match.category,
            )
            for match in detail.recent_matches
        ],
    )


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
    summaries = list_merchant_summaries(session)
    return [
        MerchantResponse(
            id=summary.merchant.id,
            raw_name=summary.merchant.raw_name,
            display_name=summary.merchant.display_name,
            category=summary.merchant.category,
            status=summary.merchant.status,
            is_transfer=summary.merchant.is_transfer,
            notes=summary.merchant.notes,
            transaction_count=summary.transaction_count,
            last_seen=summary.last_seen,
        )
        for summary in summaries
    ]


@router.patch("/merchants/{merchant_id}", response_model=MerchantResponse)
def update_merchant(
    merchant_id: str,
    payload: MerchantUpdateRequest,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> MerchantResponse:
    merchant = session.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")

    if payload.display_name is not None:
        merchant.display_name = payload.display_name.strip()
    if payload.category is not None:
        merchant.category = payload.category.strip() or None
    if payload.status is not None:
        if payload.status not in {"reviewed", "unreviewed"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid merchant status.")
        merchant_status = cast(MerchantStatus, payload.status)
        merchant.status = merchant_status
    if payload.is_transfer is not None:
        merchant.is_transfer = payload.is_transfer
    if payload.notes is not None:
        merchant.notes = payload.notes.strip() or None

    session.add(merchant)
    session.commit()
    session.refresh(merchant)

    transaction_count = session.scalar(
        select(func.count(Transaction.id)).where(Transaction.merchant_id == merchant.id)
    )
    last_seen = session.scalar(select(func.max(Transaction.posted_on)).where(Transaction.merchant_id == merchant.id))
    return MerchantResponse(
        id=merchant.id,
        raw_name=merchant.raw_name,
        display_name=merchant.display_name,
        category=merchant.category,
        status=merchant.status,
        is_transfer=merchant.is_transfer,
        notes=merchant.notes,
        transaction_count=int(transaction_count or 0),
        last_seen=last_seen,
    )


@router.post("/merchants/bulk-category", response_model=MerchantBulkCategoryResponse)
def bulk_assign_merchant_category(
    payload: MerchantBulkCategoryRequest,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> MerchantBulkCategoryResponse:
    merchants = session.scalars(select(Merchant).where(Merchant.id.in_(payload.merchant_ids))).all()
    for merchant in merchants:
        merchant.category = payload.category.strip() if payload.category is not None and payload.category.strip() else None
    session.commit()
    return MerchantBulkCategoryResponse(updated_count=len(merchants))


@router.post("/merchants/{merchant_id}/aliases", response_model=MerchantAliasResponse, status_code=status.HTTP_201_CREATED)
def create_merchant_alias(
    merchant_id: str,
    payload: MerchantAliasCreateRequest,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> MerchantAliasResponse:
    merchant = session.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    try:
        alias = create_alias_rule(session, merchant=merchant, alias=payload.alias)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    session.commit()
    session.refresh(alias)
    return MerchantAliasResponse.model_validate(alias, from_attributes=True)


@router.delete("/merchant-aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_merchant_alias(
    alias_id: str,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> Response:
    alias = session.get(MerchantAlias, alias_id)
    if alias is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    session.delete(alias)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/merchants/{merchant_id}/merge", response_model=MerchantRecategorizeResponse)
def merge_merchant_records(
    merchant_id: str,
    payload: MerchantMergeRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> MerchantRecategorizeResponse:
    source_merchant = session.get(Merchant, merchant_id)
    target_merchant = session.get(Merchant, payload.target_merchant_id)
    if source_merchant is None or target_merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    try:
        updated_count = merge_merchants(
            session,
            source_merchant=source_merchant,
            target_merchant=target_merchant,
            actor=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    session.commit()
    return MerchantRecategorizeResponse(updated_count=updated_count)


@router.post("/merchants/{merchant_id}/recategorize", response_model=MerchantRecategorizeResponse)
def recategorize_merchant_history(
    merchant_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> MerchantRecategorizeResponse:
    merchant = session.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    updated_count = recategorize_transactions_for_merchant(session, merchant=merchant, user=user)
    session.commit()
    return MerchantRecategorizeResponse(updated_count=updated_count)


@router.get("/merchant-aliases", response_model=list[MerchantAliasResponse])
def list_merchant_aliases(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> list[MerchantAliasResponse]:
    items = session.scalars(select(MerchantAlias)).all()
    return [MerchantAliasResponse.model_validate(item, from_attributes=True) for item in items]
