from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import StringIO
from typing import Literal

CanonicalColumn = Literal["date", "description", "amount"]

SUPPORTED_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d", "%d/%m/%Y")


@dataclass(frozen=True)
class ParsedTransactionRow:
    posted_on: str
    description: str
    amount: Decimal


@dataclass(frozen=True)
class ManualMappingRequirement:
    status: Literal["manual_mapping_required"]
    headers: list[str]
    required_columns: list[CanonicalColumn]
    unresolved_columns: list[CanonicalColumn]


@dataclass(frozen=True)
class ProfileParseResult:
    status: Literal["parsed"]
    profile_name: str
    headers: list[str]
    rows: list[ParsedTransactionRow]


@dataclass(frozen=True)
class ManualColumnMapping:
    date: str
    description: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None


@dataclass(frozen=True)
class MappingValidationError:
    status: Literal["mapping_validation_failed"]
    headers: list[str]
    errors: list[str]


ParseResult = ManualMappingRequirement | ProfileParseResult
ManualParseResult = ProfileParseResult | MappingValidationError


def _decimal(value: str) -> Decimal:
    normalized = value.strip().replace(",", "").replace("$", "")
    if normalized == "":
        return Decimal("0.00")
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = f"-{normalized[1:-1]}"
    return Decimal(normalized)


def _format_date(value: str, input_format: str) -> str:
    return datetime.strptime(value.strip(), input_format).date().isoformat()


def _auto_format_date(value: str) -> str:
    stripped = value.strip()
    for input_format in SUPPORTED_DATE_FORMATS:
        try:
            return _format_date(stripped, input_format)
        except ValueError:
            continue
    raise ValueError(stripped)


def _row_value(row: dict[str, str], field: str) -> str:
    return row.get(field, "").strip()


def _detect_td(headers: list[str]) -> bool:
    return {"Transaction Date", "Description", "Withdrawal", "Deposit"} <= set(headers)


def _parse_td(rows: list[dict[str, str]], headers: list[str]) -> ProfileParseResult:
    parsed = [
        ParsedTransactionRow(
            posted_on=_format_date(_row_value(row, "Transaction Date"), "%m/%d/%Y"),
            description=_row_value(row, "Description"),
            amount=_decimal(_row_value(row, "Deposit")) - _decimal(_row_value(row, "Withdrawal")),
        )
        for row in rows
    ]
    return ProfileParseResult(status="parsed", profile_name="td", headers=headers, rows=parsed)


def _detect_rbc(headers: list[str]) -> bool:
    return {"Transaction Date", "Description 1", "Description 2", "CAD$"} <= set(headers)


def _parse_rbc(rows: list[dict[str, str]], headers: list[str]) -> ProfileParseResult:
    parsed = []
    for row in rows:
        description = " ".join(
            part for part in [_row_value(row, "Description 1"), _row_value(row, "Description 2")] if part
        )
        parsed.append(
            ParsedTransactionRow(
                posted_on=_format_date(_row_value(row, "Transaction Date"), "%Y-%m-%d"),
                description=description,
                amount=_decimal(_row_value(row, "CAD$")),
            )
        )
    return ProfileParseResult(status="parsed", profile_name="rbc", headers=headers, rows=parsed)


def _detect_tangerine(headers: list[str]) -> bool:
    return {"Date", "Description", "Amount", "Type"} <= set(headers)


def _parse_tangerine(rows: list[dict[str, str]], headers: list[str]) -> ProfileParseResult:
    parsed = [
        ParsedTransactionRow(
            posted_on=_format_date(_row_value(row, "Date"), "%Y-%m-%d"),
            description=_row_value(row, "Description"),
            amount=_decimal(_row_value(row, "Amount")),
        )
        for row in rows
    ]
    return ProfileParseResult(status="parsed", profile_name="tangerine", headers=headers, rows=parsed)


def _detect_cibc(headers: list[str]) -> bool:
    return {"Transaction Date", "Description", "Debits", "Credits"} <= set(headers)


def _parse_cibc(rows: list[dict[str, str]], headers: list[str]) -> ProfileParseResult:
    parsed = [
        ParsedTransactionRow(
            posted_on=_format_date(_row_value(row, "Transaction Date"), "%m/%d/%Y"),
            description=_row_value(row, "Description"),
            amount=_decimal(_row_value(row, "Credits")) - _decimal(_row_value(row, "Debits")),
        )
        for row in rows
    ]
    return ProfileParseResult(status="parsed", profile_name="cibc", headers=headers, rows=parsed)


def _detect_scotiabank(headers: list[str]) -> bool:
    return {"Date", "Description", "Money In", "Money Out"} <= set(headers)


def _parse_scotiabank(rows: list[dict[str, str]], headers: list[str]) -> ProfileParseResult:
    parsed = [
        ParsedTransactionRow(
            posted_on=_format_date(_row_value(row, "Date"), "%d-%b-%Y"),
            description=_row_value(row, "Description"),
            amount=_decimal(_row_value(row, "Money In")) - _decimal(_row_value(row, "Money Out")),
        )
        for row in rows
    ]
    return ProfileParseResult(status="parsed", profile_name="scotiabank", headers=headers, rows=parsed)


PROFILE_HANDLERS = (
    (_detect_td, _parse_td),
    (_detect_rbc, _parse_rbc),
    (_detect_tangerine, _parse_tangerine),
    (_detect_cibc, _parse_cibc),
    (_detect_scotiabank, _parse_scotiabank),
)


def parse_csv_text(csv_text: str) -> ParseResult:
    reader = csv.DictReader(StringIO(csv_text))
    headers = list(reader.fieldnames or [])
    rows = list(reader)

    for detect, parse in PROFILE_HANDLERS:
        if detect(headers):
            return parse(rows, headers)

    return ManualMappingRequirement(
        status="manual_mapping_required",
        headers=headers,
        required_columns=["date", "description", "amount"],
        unresolved_columns=["date", "description", "amount"],
    )


def parse_csv_with_mapping(
    csv_text: str,
    mapping: ManualColumnMapping,
) -> ManualParseResult:
    reader = csv.DictReader(StringIO(csv_text))
    headers = list(reader.fieldnames or [])
    rows = list(reader)

    errors: list[str] = []

    mapped_headers = {
        "date": mapping.date,
        "description": mapping.description,
        "amount": mapping.amount,
        "debit": mapping.debit,
        "credit": mapping.credit,
    }

    for field_name, header in mapped_headers.items():
        if header is not None and header not in headers:
            errors.append(f"Mapped header '{header}' for '{field_name}' was not found in the uploaded CSV.")

    if mapping.amount is None and mapping.debit is None and mapping.credit is None:
        errors.append("Provide either 'amount' or at least one of 'debit'/'credit' in the column mapping.")

    used_headers = [header for header in mapped_headers.values() if header is not None]
    if len(used_headers) != len(set(used_headers)):
        errors.append("Each mapped CSV header must be used for only one semantic field.")

    if errors:
        return MappingValidationError(
            status="mapping_validation_failed",
            headers=headers,
            errors=errors,
        )

    parsed_rows: list[ParsedTransactionRow] = []
    for index, row in enumerate(rows, start=2):
        try:
            posted_on = _auto_format_date(_row_value(row, mapping.date))
        except ValueError as exc:
            errors.append(
                f"Row {index} has an unsupported date value '{exc.args[0]}' in column '{mapping.date}'."
            )
            continue

        try:
            if mapping.amount is not None:
                amount = _decimal(_row_value(row, mapping.amount))
            else:
                credit_amount = _decimal(_row_value(row, mapping.credit or ""))
                debit_amount = _decimal(_row_value(row, mapping.debit or ""))
                amount = credit_amount - debit_amount
        except ArithmeticError:
            amount_columns = [header for header in [mapping.amount, mapping.debit, mapping.credit] if header]
            errors.append(
                f"Row {index} contains an invalid amount value in column(s): {', '.join(amount_columns)}."
            )
            continue

        parsed_rows.append(
            ParsedTransactionRow(
                posted_on=posted_on,
                description=_row_value(row, mapping.description),
                amount=amount,
            )
        )

    if errors:
        return MappingValidationError(
            status="mapping_validation_failed",
            headers=headers,
            errors=errors,
        )

    return ProfileParseResult(
        status="parsed",
        profile_name="manual",
        headers=headers,
        rows=parsed_rows,
    )
