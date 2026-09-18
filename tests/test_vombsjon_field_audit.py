from pathlib import Path

import pytest

from twinwater_timesat.vombsjon_field_audit import (
    audit_field_inputs,
    parse_gps_coordinate,
    read_metadata_records,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("raw", "expected", "format_name"),
    [
        ("55 40.505", 55 + 40.505 / 60, "degrees_decimal_minutes"),
        ("13 36 34", 13 + 36 / 60 + 34 / 3600, "degrees_minutes_seconds"),
        (55.678341, 55.678341, "decimal_degrees"),
    ],
)
def test_parse_gps_coordinate_formats(raw, expected, format_name):
    value, parsed_format = parse_gps_coordinate(raw)
    assert value == pytest.approx(expected)
    assert parsed_format == format_name


def test_metadata_workbook_dates_and_extra_field_occasion():
    records = read_metadata_records(REPO_ROOT / "data/sources/vombsjon/Metadata_Vombsjon_SR.xlsx")
    assert len(records) == 49
    assert sum(record["year"] == 2019 for record in records) == 23
    assert sum(record["year"] == 2020 for record in records) == 26
    assert any(record["date"] == "2019-05-02" for record in records)


def test_field_audit_core_and_unresolved_coordinates():
    audit = audit_field_inputs(REPO_ROOT)
    core = audit["core"]
    assert core["row_count"] == 54
    assert core["year_counts"] == {2018: 6, 2019: 22, 2020: 26}
    assert core["duplicate_dates"] == []
    assert core["missing_counts"]["chla_fluorometry_ug_L"] == 0
    assert core["metadata_discrepancy_count"] == 0
    assert core["coordinate_mismatch_count"] == 0
    assert core["distance_mismatch_count"] == 0
    assert core["flagged_dates"] == ["2020-06-10", "2020-06-24"]
    flagged = [row for row in audit["coordinate_rows"] if row["audit_status"].startswith("flagged")]
    assert len(flagged) == 2
    assert all(not row["matchup_lat"] and not row["matchup_lon"] for row in flagged)
