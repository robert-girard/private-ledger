from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import StringIO
from typing import Literal

CanonicalColumn = Literal["date", "description", "amount"]


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


ParseResult = ManualMappingRequirement | ProfileParseResult


def _decimal(value: str) -> Decimal:
    normalized = value.strip().replace(",", "").replace("$", "")
    if normalized == "":
        return Decimal("0.00")
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = f"-{normalized[1:-1]}"
    return Decimal(normalized)


def _format_date(value: str, input_format: str) -> str:
    return datetime.strptime(value.strip(), input_format).date().isoformat()


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
