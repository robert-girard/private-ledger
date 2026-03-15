from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Import, User
from app.importing.parser import (
    ManualColumnMapping,
    ManualMappingRequirement,
    MappingValidationError,
    ParseResult,
    ProfileParseResult,
    parse_csv_text,
    parse_csv_with_mapping,
)


@dataclass(frozen=True)
class ImportPreviewResult:
    import_record: Import
    parse_result: ParseResult | MappingValidationError


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
