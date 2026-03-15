from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Import, Merchant, Transaction, User
from app.importing.parser import (
    ManualColumnMapping,
    ManualMappingRequirement,
    MappingValidationError,
    ParseResult,
    ProfileParseResult,
    parse_csv_text,
    parse_csv_with_mapping,
)
from app.services.merchants import normalize_merchant_name


@dataclass(frozen=True)
class ImportPreviewResult:
    import_record: Import
    parse_result: ParseResult | MappingValidationError


@dataclass(frozen=True)
class ImportCommitResult:
    import_record: Import
    inserted_count: int
    skipped_count: int
    failed_count: int


def _safe_filename(filename: str) -> str:
    candidate = Path(filename).name.strip()
    return candidate or "upload.csv"


def _store_upload(
    *,
    settings: Settings,
    user: User,
    filename: str,
    csv_text: str,
) -> Path:
    user_dir = settings.import_storage_dir / user.id
    user_dir.mkdir(parents=True, exist_ok=True)

    stored_path = user_dir / f"{uuid4()}-{_safe_filename(filename)}"
    stored_path.write_text(csv_text, encoding="utf-8")
    return stored_path


def _parse_mapping_json(column_mapping: str | None) -> ManualColumnMapping | None:
    if column_mapping is None:
        return None

    payload = json.loads(column_mapping)
    return ManualColumnMapping(
        date=str(payload["date"]),
        description=str(payload["description"]),
        amount=str(payload["amount"]) if payload.get("amount") is not None else None,
        debit=str(payload["debit"]) if payload.get("debit") is not None else None,
        credit=str(payload["credit"]) if payload.get("credit") is not None else None,
    )


def _load_staged_csv(import_record: Import, settings: Settings) -> str:
    if import_record.stored_path is None:
        raise ValueError("This import does not have a staged CSV path.")

    base_dir = settings.import_storage_dir.resolve()
    stored_path = Path(import_record.stored_path).resolve()
    if not stored_path.is_relative_to(base_dir):
        raise ValueError("The staged import file is outside the configured import storage directory.")

    return stored_path.read_text(encoding="utf-8")


def _dedupe_hash(*, user_id: str, posted_on: str, amount: str, normalized_merchant: str) -> str:
    digest = hashlib.sha256()
    digest.update(f"{user_id}|{posted_on}|{amount}|{normalized_merchant}".encode("utf-8"))
    return digest.hexdigest()


def _resolve_parse_result(
    *,
    csv_text: str,
    import_record: Import,
    column_mapping: str | None,
) -> ParseResult | MappingValidationError:
    mapping = _parse_mapping_json(column_mapping)
    detected_result = parse_csv_text(csv_text)

    if isinstance(detected_result, ProfileParseResult):
        return detected_result

    if import_record.source_bank == "manual" or mapping is not None:
        if mapping is None:
            return MappingValidationError(
                status="mapping_validation_failed",
                headers=detected_result.headers,
                errors=[
                    "This staged import requires a manual column mapping before it can be committed.",
                ],
            )
        return parse_csv_with_mapping(csv_text, mapping)

    return detected_result


def create_import_preview(
    *,
    session: Session,
    settings: Settings,
    user: User,
    filename: str,
    csv_text: str,
    column_mapping: str | None = None,
) -> ImportPreviewResult:
    mapping = _parse_mapping_json(column_mapping)
    detected_result = parse_csv_text(csv_text)
    parse_result: ParseResult | MappingValidationError

    if isinstance(detected_result, ProfileParseResult):
        parse_result = detected_result
    elif mapping is not None:
        parse_result = parse_csv_with_mapping(csv_text, mapping)
    else:
        parse_result = detected_result

    stored_path = _store_upload(
        settings=settings,
        user=user,
        filename=filename,
        csv_text=csv_text,
    )

    source_bank = parse_result.profile_name if isinstance(parse_result, ProfileParseResult) else None
    row_count = len(parse_result.rows) if isinstance(parse_result, ProfileParseResult) else 0
    import_status = "preview_ready" if isinstance(parse_result, ProfileParseResult) else "mapping_required"

    import_record = Import(
        user_id=user.id,
        source_filename=_safe_filename(filename),
        source_bank=source_bank,
        import_status=import_status,
        row_count=row_count,
        stored_path=str(stored_path),
    )
    session.add(import_record)
    session.commit()
    session.refresh(import_record)

    return ImportPreviewResult(import_record=import_record, parse_result=parse_result)


def commit_import(
    *,
    session: Session,
    settings: Settings,
    user: User,
    import_record: Import,
    column_mapping: str | None = None,
) -> ImportCommitResult:
    csv_text = _load_staged_csv(import_record, settings)
    parse_result = _resolve_parse_result(
        csv_text=csv_text,
        import_record=import_record,
        column_mapping=column_mapping,
    )

    if isinstance(parse_result, ManualMappingRequirement):
        raise ValueError("This staged import requires manual column mapping before it can be committed.")

    if isinstance(parse_result, MappingValidationError):
        raise ValueError(" | ".join(parse_result.errors))

    existing_merchants = session.scalars(select(Merchant)).all()
    merchant_by_normalized_name = {
        normalize_merchant_name(merchant.raw_name): merchant for merchant in existing_merchants
    }

    dedupe_hashes = [
        _dedupe_hash(
            user_id=user.id,
            posted_on=row.posted_on,
            amount=f"{row.amount:.2f}",
            normalized_merchant=normalize_merchant_name(row.description),
        )
        for row in parse_result.rows
    ]
    existing_hashes = set(
        session.scalars(select(Transaction.dedupe_hash).where(Transaction.dedupe_hash.in_(dedupe_hashes))).all()
    )

    inserted_count = 0
    skipped_count = 0
    seen_hashes = set(existing_hashes)

    for row in parse_result.rows:
        normalized_merchant = normalize_merchant_name(row.description)
        dedupe_hash = _dedupe_hash(
            user_id=user.id,
            posted_on=row.posted_on,
            amount=f"{row.amount:.2f}",
            normalized_merchant=normalized_merchant,
        )
        if dedupe_hash in seen_hashes:
            skipped_count += 1
            continue

        merchant = merchant_by_normalized_name.get(normalized_merchant)
        if merchant is None:
            merchant = Merchant(
                raw_name=row.description.strip(),
                display_name=row.description.strip(),
            )
            session.add(merchant)
            session.flush()
            merchant_by_normalized_name[normalized_merchant] = merchant

        session.add(
            Transaction(
                user_id=user.id,
                import_id=import_record.id,
                merchant_id=merchant.id,
                posted_on=datetime.fromisoformat(row.posted_on).date(),
                description=row.description.strip(),
                normalized_description=normalized_merchant,
                amount=row.amount,
                currency="CAD",
                dedupe_hash=dedupe_hash,
            )
        )
        seen_hashes.add(dedupe_hash)
        inserted_count += 1

    import_record.source_bank = parse_result.profile_name
    import_record.import_status = "complete"
    import_record.imported_at = datetime.now(UTC)
    import_record.row_count = len(parse_result.rows)

    session.add(import_record)
    session.commit()
    session.refresh(import_record)

    return ImportCommitResult(
        import_record=import_record,
        inserted_count=inserted_count,
        skipped_count=skipped_count,
        failed_count=0,
    )
