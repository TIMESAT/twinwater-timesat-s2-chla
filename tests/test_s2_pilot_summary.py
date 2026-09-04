"""Frozen 3x3 statistics, QA-only attrition and failure retention."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from twinwater_timesat.s2_pilot_summary import (
    attrition_table,
    collapse_to_date_observations,
    failure_rows,
    qa_failure_counts,
    render_native_qa_audit,
    render_qa_findings,
    summarize_index_window,
    write_markdown,
    write_rows,
)


def test_median_is_the_primary_statistic_over_valid_pixels_only():
    values = np.array([[0.1, 0.2, 0.3], [0.4, 99.0, 0.5], [0.6, 0.7, 0.8]])
    valid = np.ones((3, 3), dtype=bool)
    valid[1, 1] = False

    summary = summarize_index_window(
        values, valid, prefix="NDCI", window_pixel_count=9
    )
    assert summary["NDCI_valid_pixel_count"] == 8
    assert summary["NDCI_valid_pixel_fraction"] == pytest.approx(8 / 9)
    assert summary["NDCI_median"] == pytest.approx(0.45)
    assert summary["NDCI_min"] == pytest.approx(0.1)
    assert summary["NDCI_max"] == pytest.approx(0.8)
    assert summary["NDCI_IQR"] == pytest.approx(0.35)


def test_no_valid_pixel_yields_missing_statistics_not_substitutes():
    summary = summarize_index_window(
        np.full((3, 3), np.nan),
        np.zeros((3, 3), dtype=bool),
        prefix="MCI",
        window_pixel_count=9,
    )
    assert summary["MCI_valid_pixel_count"] == 0
    assert summary["MCI_median"] is None
    assert summary["MCI_mean"] is None


def test_single_valid_pixel_reports_no_standard_deviation():
    valid = np.zeros((3, 3), dtype=bool)
    valid[0, 0] = True
    summary = summarize_index_window(
        np.full((3, 3), 0.2), valid, prefix="NDCI", window_pixel_count=9
    )
    assert summary["NDCI_valid_pixel_count"] == 1
    assert summary["NDCI_SD"] is None
    assert summary["NDCI_IQR"] == pytest.approx(0.0)


def test_non_finite_values_never_enter_the_statistics():
    values = np.array([[0.1, np.nan, 0.3]])
    summary = summarize_index_window(
        values, np.ones((1, 3), dtype=bool), prefix="NDCI", window_pixel_count=9
    )
    assert summary["NDCI_valid_pixel_count"] == 2


class Layer:
    def __init__(self, flags, *, name=None, band=None):
        self.flags = flags
        self.name = name
        self.band = band


def test_qa_failure_counts_and_fractions_are_retained_per_reason():
    flags = np.zeros((3, 3), dtype=bool)
    flags[0, :] = True
    counts = qa_failure_counts(
        {"opaque_cloud": Layer(flags, name="opaque_cloud")}, window_pixel_count=9
    )
    assert counts["qa_opaque_cloud"] == 3
    assert counts["qa_opaque_cloud_fraction"] == pytest.approx(3 / 9)


def test_qa_counts_keep_band_provenance_and_add_an_aggregate():
    b4 = np.zeros((3, 3), dtype=bool)
    b4[0, 0] = True
    b6 = np.zeros((3, 3), dtype=bool)
    b6[1, 1] = True
    counts = qa_failure_counts(
        {
            "B04_nodata": Layer(b4, name="nodata", band="B04"),
            "B06_nodata": Layer(b6, name="nodata", band="B06"),
        },
        window_pixel_count=9,
    )
    assert counts["qa_B04_nodata"] == 1
    assert counts["qa_B04_nodata_band"] == "B04"
    assert counts["qa_B06_nodata"] == 1
    # The aggregate is the union across bands, not a sum of overlapping pixels.
    assert counts["qa_nodata"] == 2
    assert counts["qa_nodata_fraction"] == pytest.approx(2 / 9)


def test_aggregate_qa_count_does_not_double_count_a_shared_pixel():
    shared = np.zeros((3, 3), dtype=bool)
    shared[0, 0] = True
    counts = qa_failure_counts(
        {
            "B04_nodata": Layer(shared.copy(), name="nodata", band="B04"),
            "B05_nodata": Layer(shared.copy(), name="nodata", band="B05"),
        },
        window_pixel_count=9,
    )
    assert counts["qa_nodata"] == 1


def test_attrition_covers_the_pre_specified_pilot_thresholds():
    rows = [
        {"product_level": "L2A", "ndci_valid_pixel_count": 9},
        {"product_level": "L2A", "ndci_valid_pixel_count": 8},
        {"product_level": "L2A", "ndci_valid_pixel_count": 6},
        {"product_level": "L2A", "ndci_valid_pixel_count": 5},
        {"product_level": "L2A", "ndci_valid_pixel_count": 0},
    ]
    table = attrition_table(
        rows,
        thresholds=[9, 8, 6, 5],
        count_columns={"NDCI": "ndci_valid_pixel_count"},
        group_columns=("product_level",),
    )
    passing = {entry["minimum_valid_pixels"]: entry["n_passing"] for entry in table}
    assert passing == {9: 1, 8: 2, 6: 3, 5: 4}
    assert {entry["threshold_status"] for entry in table} == {"PILOT_NOT_SELECTED"}


def test_attrition_reports_unavailable_counts_rather_than_treating_them_as_zero():
    rows = [
        {"product_level": "L1C", "ndci_valid_pixel_count": 9},
        {"product_level": "L1C", "ndci_valid_pixel_count": None},
    ]
    table = attrition_table(
        rows,
        thresholds=[9],
        count_columns={"NDCI": "ndci_valid_pixel_count"},
        group_columns=("product_level",),
    )
    entry = table[0]
    assert entry["n_records"] == 2
    assert entry["n_records_with_valid_pixel_count"] == 1
    assert entry["n_records_unavailable"] == 1
    assert entry["pass_fraction_of_available"] == pytest.approx(1.0)
    assert entry["pass_fraction_of_all_records"] == pytest.approx(0.5)


def test_annual_attrition_groups_by_year():
    rows = [
        {"product_level": "L2A", "year": 2019, "ndci_valid_pixel_count": 9},
        {"product_level": "L2A", "year": 2020, "ndci_valid_pixel_count": 4},
    ]
    table = attrition_table(
        rows,
        thresholds=[5],
        count_columns={"NDCI": "ndci_valid_pixel_count"},
        group_columns=("product_level", "year"),
    )
    by_year = {entry["year"]: entry["n_passing"] for entry in table}
    assert by_year == {2019: 1, 2020: 0}


def test_failed_observations_are_retained_with_explicit_reasons():
    rows = [
        {"date": "2019-04-17", "failure_reason": None},
        {"date": "2019-04-19", "failure_reason": "no_frozen_representative"},
    ]
    failures = failure_rows(rows)
    assert len(failures) == 1
    assert failures[0]["date"] == "2019-04-19"


def test_date_collapse_keeps_the_calendar_date_observation_unit():
    rows = [
        {
            "date": "2019-04-17",
            "year": 2019,
            "product_id": "A",
            "NDCI_median": 0.1,
            "failure_reason": None,
        },
        {
            "date": "2019-04-19",
            "year": 2019,
            "product_id": None,
            "NDCI_median": None,
            "failure_reason": "no_frozen_representative",
        },
    ]
    collapsed = collapse_to_date_observations(rows, level="L2A")
    assert [entry["date"] for entry in collapsed] == ["2019-04-17", "2019-04-19"]
    assert collapsed[1]["failure_reason"] == "no_frozen_representative"


def test_write_rows_uses_a_stable_union_header(tmp_path):
    path = write_rows(
        [{"a": 1}, {"a": 2, "b": 3}], tmp_path / "out" / "table.csv"
    )
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == ["a", "b"]
    assert rows[0]["b"] == ""


# --- concise Markdown audits -------------------------------------------------


QA_ROWS = [
    {
        "product_id": "P1",
        "product_level": "L1C",
        "qa_family": "QUALIT",
        "band": "B04",
        "declared_resolution_m": None,
        "asset_kind": "raster",
        "asset_status": "present",
        "band_specific": True,
    },
    {
        "product_id": "P1",
        "product_level": "L1C",
        "qa_family": "SATURA",
        "band": None,
        "declared_resolution_m": None,
        "asset_kind": None,
        "asset_status": "absent",
        "band_specific": None,
    },
]
EXTRACTION_ROWS = [
    {
        "product_level": "L2A",
        "year": 2019,
        "platform": "S2A",
        "processing_baseline": "N0500",
        "ndci_valid_pixel_count": 9,
        "mci_valid_pixel_count": 8,
        "common_B456_valid_count": 8,
        "B4_grid_alignment": "native_target_grid",
        "failure_reason": None,
    },
    {
        "product_level": "L1C",
        "year": 2019,
        "platform": "S2A",
        "processing_baseline": "N0500",
        "ndci_valid_pixel_count": None,
        "mci_valid_pixel_count": None,
        "common_B456_valid_count": None,
        "B4_grid_alignment": "block_mean_reduce_x2",
        "failure_reason": "l1c_not_extracted: unmatched_no_candidate",
    },
]
PAIRING_ROWS = [
    {"l1c_pairing_status": "exact_unique"},
    {"l1c_pairing_status": "unmatched_no_candidate"},
]


def test_native_qa_audit_describes_families_and_gaps():
    text = render_native_qa_audit(QA_ROWS, EXTRACTION_ROWS)
    assert "native QA inventory audit" in text
    assert "QUALIT" in text and "SATURA" in text
    assert "absent" in text
    assert "never treated as clean" in text
    assert "block_mean_reduce_x2" in text


def test_qa_findings_reports_availability_without_performance_claims():
    attrition = attrition_table(
        EXTRACTION_ROWS,
        thresholds=[9, 8, 6, 5],
        count_columns={"NDCI": "ndci_valid_pixel_count"},
        group_columns=("product_level",),
    )
    text = render_qa_findings(
        EXTRACTION_ROWS, PAIRING_ROWS, attrition, {"candidate_dates": 2}
    )
    assert "QA and data-availability findings" in text
    assert "No CHLF was inspected" in text
    assert "exact_unique" in text
    assert "not selected here" in text
    # The audit states the governance limits explicitly...
    assert "No threshold is declared scientifically superior" in text
    # ...and no affirmative performance vocabulary leaks into it.
    for forbidden in ("correlation", "rmse", "outperform", "better than"):
        assert forbidden not in text.lower()


def test_qa_findings_retains_failure_reasons():
    text = render_qa_findings(EXTRACTION_ROWS, PAIRING_ROWS, [], {})
    assert "l1c_not_extracted" in text


def test_write_markdown_creates_parent_directories(tmp_path):
    path = write_markdown("# title\n", tmp_path / "qa" / "doc.md")
    assert path.read_text(encoding="utf-8").startswith("# title")
