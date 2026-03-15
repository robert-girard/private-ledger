from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.importing.parser import ManualMappingRequirement, ProfileParseResult, parse_csv_text


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "csv"


@pytest.mark.parametrize(
    ("fixture_name", "profile_name", "expected_first_date", "expected_first_amount"),
    [
        ("td.csv", "td", "2026-03-01", Decimal("-5.45")),
        ("rbc.csv", "rbc", "2026-03-01", Decimal("-5.45")),
        ("tangerine.csv", "tangerine", "2026-03-01", Decimal("-5.45")),
        ("cibc.csv", "cibc", "2026-03-01", Decimal("-5.45")),
        ("scotiabank.csv", "scotiabank", "2026-03-01", Decimal("-5.45")),
    ],
)
def test_supported_bank_profiles_parse_with_normalized_dates_and_amounts(
    fixture_name: str,
    profile_name: str,
    expected_first_date: str,
    expected_first_amount: Decimal,
) -> None:
    result = parse_csv_text((FIXTURE_DIR / fixture_name).read_text())

    assert isinstance(result, ProfileParseResult)
    assert result.profile_name == profile_name
    assert result.rows[0].posted_on == expected_first_date
    assert result.rows[0].amount == expected_first_amount
    assert result.rows[1].amount == Decimal("1500.00")


def test_unknown_headers_require_manual_mapping() -> None:
    result = parse_csv_text((FIXTURE_DIR / "unknown.csv").read_text())

    assert isinstance(result, ManualMappingRequirement)
    assert result.status == "manual_mapping_required"
    assert result.headers == ["Booked On", "Vendor", "Outflow", "Inflow"]
    assert result.required_columns == ["date", "description", "amount"]
    assert result.unresolved_columns == ["date", "description", "amount"]
