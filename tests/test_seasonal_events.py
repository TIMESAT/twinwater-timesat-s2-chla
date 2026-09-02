from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

from twinwater_timesat.event_preflight import (
    build_event_preflight_products,
    synthetic_event_gate_results,
)
from twinwater_timesat.reconstruction_support import (
    build_common_support,
    read_phase3_master,
)
from twinwater_timesat.seasonal_events import (
    EXPECTED_EVENT_TIMES,
    EXPECTED_SCALE_DECIMALS,
    EXPECTED_YEARLY_COUNTS,
    RECONSTRUCTION_CANDIDATE_COLUMNS,
    detect_reconstruction_peak_candidates,
    detect_reference_major_events,
    load_event_protocol_config,
    match_detected_reconstruction_events,
    match_reference_events,
    validate_parent_actual_mask_benchmark,
)


ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "processed" / "erken_temporal_sampling_master.csv"


def _support(
    values: list[float],
    *,
    start: str = "2020-01-01",
    segments: list[str] | None = None,
) -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "year": dates.year,
            "CHLF": values,
            "common_support": True,
            "reference_value_available": True,
            "common_support_segment_id": (
                segments or ["2020_segment_1"] * len(values)
            ),
        }
    )


def _references(times_and_segments: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": f"ERK_2020_E{index:02d}",
                "year": 2020,
                "event_time": pd.Timestamp(event_time),
                "common_support_segment_id": segment,
                "reference_magnitude": float(index * 10),
                "yearly_scale_q95_minus_q05": 10.0,
            }
            for index, (event_time, segment) in enumerate(
                times_and_segments, start=1
            )
        ]
    )


def _candidates(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(RECONSTRUCTION_CANDIDATE_COLUMNS))
    return pd.DataFrame(
        [
            {
                "candidate_id": f"REC_2020_P{index:03d}",
                "year": 2020,
                "event_time": pd.Timestamp(event_time),
                "common_support_segment_id": segment,
                "reconstructed_magnitude": magnitude,
            }
            for index, (event_time, segment, magnitude) in enumerate(rows, start=1)
        ]
    )


def test_protocol_config_and_parent_phase3_artifacts_are_frozen() -> None:
    config = load_event_protocol_config(ROOT)
    parent = validate_parent_actual_mask_benchmark(config, repository_root=ROOT)
    assert config["parent_contract"]["unchanged"] is True
    assert parent["parent_actual_mask_benchmark_unchanged"] is True
    assert parent["parent_manifest_payload_sha256"] == (
        "ade16b1bc6f622a863ed64740bf59a67309487e93933b7521d9b7a2b9712d31d"
    )


def test_exact_18_erken_reference_events_dates_ids_counts_and_scales() -> None:
    support = build_common_support(read_phase3_master(MASTER))
    events = detect_reference_major_events(support)
    assert list(zip(events["event_id"], events["event_date"], strict=True)) == list(
        EXPECTED_EVENT_TIMES
    )
    assert len(events) == 18
    assert events.groupby("year").size().to_dict() == EXPECTED_YEARLY_COUNTS
    for year, (expected_decimal, places) in EXPECTED_SCALE_DECIMALS.items():
        actual = events.loc[
            events["year"].eq(year), "yearly_scale_q95_minus_q05"
        ].unique()
        assert len(actual) == 1
        assert format(float(actual[0]), f".{places}f") == expected_decimal


def test_reference_detector_uses_exact_distance_prominence_and_plateau_kwargs(
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    def recording_find_peaks(values, **kwargs):
        calls.append(kwargs)
        return np.array([], dtype=int), {
            "left_edges": np.array([], dtype=int),
            "right_edges": np.array([], dtype=int),
            "plateau_sizes": np.array([], dtype=int),
            "prominences": np.array([], dtype=float),
        }

    monkeypatch.setattr(
        "twinwater_timesat.seasonal_events.find_peaks", recording_find_peaks
    )
    support = _support([0, 1, 4, 1, 0])
    scale = support["CHLF"].quantile(0.95) - support["CHLF"].quantile(0.05)
    detect_reference_major_events(support)
    assert calls == [
        {
            "distance": 30,
            "prominence": 0.30 * scale,
            "plateau_size": (1, None),
        }
    ]


def test_reference_plateau_uses_exact_temporal_midpoint() -> None:
    events = detect_reference_major_events(_support([0, 0, 10, 10, 0, 0]))
    assert len(events) == 1
    assert events.iloc[0]["event_time"] == pd.Timestamp("2020-01-03 12:00:00")
    assert events.iloc[0]["plateau_start_time"] == pd.Timestamp("2020-01-03")
    assert events.iloc[0]["plateau_end_time"] == pd.Timestamp("2020-01-04")


def test_reference_and_candidate_detection_do_not_cross_segments() -> None:
    segments = ["s1", "s1", "s1", "s2", "s2", "s2"]
    support = _support([0, 10, 0, 0, 9, 0], segments=segments)
    reference = detect_reference_major_events(support)
    candidates = detect_reconstruction_peak_candidates(
        support,
        pd.Series([0, 2, 0, 0, 3, 0], index=support["date"]),
    )
    assert reference["common_support_segment_id"].tolist() == ["s1", "s2"]
    assert candidates.status == "ok"
    assert candidates.candidates["common_support_segment_id"].tolist() == [
        "s1",
        "s2",
    ]
    wrong_segment = match_reference_events(
        _references([("2020-01-05", "s1")]),
        _candidates([("2020-01-05", "s2", 3.0)]),
    )
    assert wrong_segment.iloc[0]["event_status"] == "missed_no_peak_within_15d"


def test_reconstruction_candidate_detection_is_amplitude_agnostic() -> None:
    support = _support([0] * 7)
    low = detect_reconstruction_peak_candidates(
        support,
        pd.Series(
            [0, 1e-12, 0, 2e-12, 0, 3e-12, 0], index=support["date"]
        ),
    )
    high = detect_reconstruction_peak_candidates(
        support,
        pd.Series([0, 10, 0, 1e12, 0, 1, 0], index=support["date"]),
    )
    assert low.status == high.status == "ok"
    assert low.candidates["event_time"].tolist() == [
        pd.Timestamp("2020-01-02"),
        pd.Timestamp("2020-01-04"),
        pd.Timestamp("2020-01-06"),
    ]
    assert high.candidates["event_time"].tolist() == [
        pd.Timestamp("2020-01-02"),
        pd.Timestamp("2020-01-04"),
        pd.Timestamp("2020-01-06"),
    ]


def test_matching_is_amplitude_independent_one_to_one_and_deterministic() -> None:
    references = _references(
        [("2020-01-10", "s1"), ("2020-01-20", "s1")]
    )
    first = _candidates(
        [("2020-01-09", "s1", 1e12), ("2020-01-21", "s1", 1e-12)]
    )
    second = first.copy()
    second["reconstructed_magnitude"] = [1e-12, 1e12]
    matched_first = match_reference_events(references, first)
    matched_second = match_reference_events(references, second)
    assert matched_first["matched_candidate_id"].tolist() == (
        matched_second["matched_candidate_id"].tolist()
    )
    assert matched_first["reconstructed_event_time"].tolist() == (
        matched_second["reconstructed_event_time"].tolist()
    )

    only_one = match_reference_events(
        references, _candidates([("2020-01-12", "s1", 5.0)])
    )
    assert only_one["event_status"].eq("matched").sum() == 1
    assert only_one.iloc[0]["event_status"] == "matched"

    cardinality_first = match_reference_events(
        references,
        _candidates(
            [("2020-01-01", "s1", 1e12), ("2020-01-11", "s1", 1e-12)]
        ),
    )
    assert cardinality_first["event_status"].eq("matched").all()
    assert cardinality_first["reconstructed_event_time"].tolist() == [
        pd.Timestamp("2020-01-01"),
        pd.Timestamp("2020-01-11"),
    ]

    exact_tie = match_reference_events(
        _references([("2020-02-10", "s1")]),
        _candidates(
            [("2020-02-09", "s1", -1e12), ("2020-02-11", "s1", 1e12)]
        ),
    )
    assert exact_tie.iloc[0]["reconstructed_event_time"] == pd.Timestamp(
        "2020-02-09"
    )


def test_event_metric_thresholds_and_magnitude_errors() -> None:
    references = _references(
        [
            ("2020-03-01", "s1"),
            ("2020-04-01", "s2"),
            ("2020-05-01", "s3"),
        ]
    )
    matched = match_reference_events(
        references,
        _candidates(
            [
                ("2020-03-06", "s1", 15.0),
                ("2020-04-11", "s2", 10.0),
                ("2020-05-16", "s3", 45.0),
            ]
        ),
    )
    assert matched["signed_timing_error_days"].tolist() == [5.0, 10.0, 15.0]
    assert matched["success_5d"].tolist() == [True, False, False]
    assert matched["success_10d"].tolist() == [True, True, False]
    assert matched["success_15d"].tolist() == [True, True, True]
    assert matched["signed_magnitude_error"].tolist() == [5.0, -10.0, 15.0]
    assert matched["normalized_absolute_magnitude_error"].tolist() == [0.5, 1.0, 1.5]


def test_valid_miss_differs_from_failed_or_incomplete_reconstruction() -> None:
    references = _references([("2020-02-01", "s1")])
    valid_miss = match_reference_events(references, _candidates([])).iloc[0]
    assert valid_miss["event_status"] == "missed_no_peak_within_15d"
    assert not bool(valid_miss["success_5d"])
    assert not bool(valid_miss["success_10d"])
    assert not bool(valid_miss["success_15d"])
    assert pd.isna(valid_miss["signed_timing_error_days"])

    failed = match_reference_events(
        references,
        _candidates([]),
        reconstruction_status="unavailable",
        failure_reason="synthetic_failure",
    ).iloc[0]
    assert failed["event_status"] == "unavailable"
    assert failed["event_unavailable_reason"] == "synthetic_failure"
    assert pd.isna(failed["success_5d"])
    assert pd.isna(failed["success_10d"])
    assert pd.isna(failed["success_15d"])

    support = _support([0, 0, 0])
    incomplete = detect_reconstruction_peak_candidates(
        support,
        pd.Series([0.0, 1.0], index=support["date"].iloc[:2]),
    )
    assert incomplete.status == "unavailable"
    assert incomplete.failure_reason == "required_common_support_prediction_incomplete"
    incomplete_metrics = match_detected_reconstruction_events(
        references, incomplete
    ).iloc[0]
    assert incomplete_metrics["event_status"] == "unavailable"
    assert incomplete_metrics["event_unavailable_reason"] == (
        "required_common_support_prediction_incomplete"
    )


def test_all_synthetic_event_preperformance_gates_pass() -> None:
    assert all(synthetic_event_gate_results().values())


def test_reference_only_preflight_has_no_real_event_performance() -> None:
    tables, manifest = build_event_preflight_products(
        repository_root=ROOT, temporal_master_path=MASTER
    )
    assert set(tables) == {"erken_phase3_reference_events.csv"}
    assert manifest["reference_event_count"] == 18
    assert manifest["all_preperformance_gates_passed"] is True
    assert manifest["event_level_performance_generated"] is False
    assert manifest["event_level_performance_inspected"] is False


def test_event_preflight_cli_is_explicitly_reference_only() -> None:
    help_result = subprocess.run(
        [sys.executable, "scripts/10_erken_phase3_event_preflight.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "No real reconstruction event-level performance" in help_result.stdout
    run_result = subprocess.run(
        [
            sys.executable,
            "scripts/10_erken_phase3_event_preflight.py",
            "--no-write",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "reference events: 18" in run_result.stdout
    assert "Event-level performance generated: False; inspected: False" in (
        run_result.stdout
    )
