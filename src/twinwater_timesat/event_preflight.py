"""Reference-only gates for the frozen seasonal-event protocol v1.0."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from typing import Any, Mapping

import numpy as np
import pandas as pd
import scipy

from twinwater_timesat.phase3_contract import (
    CONTRACT_VERSION,
    canonical_json_payload_sha256,
    sha256_file,
)
from twinwater_timesat.phase3_preflight import (
    deterministic_table_sha256,
    write_deterministic_csv,
    write_deterministic_json,
)
from twinwater_timesat.reconstruction_support import (
    build_common_support,
    read_phase3_master,
)
from twinwater_timesat.seasonal_events import (
    ANALYSIS_CLASSIFICATION,
    EXPECTED_EVENT_TIMES,
    EXPECTED_SCALE_DECIMALS,
    EXPECTED_YEARLY_COUNTS,
    PROTOCOL_VERSION,
    RECONSTRUCTION_CANDIDATE_COLUMNS,
    EventProtocolError,
    detect_reconstruction_peak_candidates,
    detect_reference_major_events,
    load_event_protocol_config,
    match_reference_events,
    validate_parent_actual_mask_benchmark,
)


EVENT_IMPLEMENTATION_PATHS = (
    "pyproject.toml",
    "config/seasonal_event_protocol_v1.0.json",
    "docs/Seasonal_Event_Detection_and_Matching_Protocol_v1.0.md",
    "docs/CODEX_Implement_Seasonal_Event_Protocol_v1.0.md",
    "docs/Reconstruction_Analysis_Contract_v1.0.1.md",
    "scripts/10_erken_phase3_event_preflight.py",
    "src/twinwater_timesat/event_preflight.py",
    "src/twinwater_timesat/seasonal_events.py",
    "src/twinwater_timesat/reconstruction_metrics.py",
    "src/twinwater_timesat/reconstruction_support.py",
)


def _implementation_provenance(root: Path) -> dict[str, Any]:
    paths = [root / relative for relative in EVENT_IMPLEMENTATION_PATHS]
    missing = [
        relative
        for relative, path in zip(EVENT_IMPLEMENTATION_PATHS, paths, strict=True)
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Seasonal-event implementation bundle is incomplete: "
            + ", ".join(missing)
        )
    digest = hashlib.sha256()
    for relative, path in zip(EVENT_IMPLEMENTATION_PATHS, paths, strict=True):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *EVENT_IMPLEMENTATION_PATHS,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "repository_commit": commit,
        "implementation_bundle_sha256": digest.hexdigest(),
        "implementation_files_dirty": bool(dirty),
        "implementation_paths": list(EVENT_IMPLEMENTATION_PATHS),
    }


def _support(
    values: list[float],
    *,
    start: str = "2020-01-01",
    segments: list[str] | None = None,
) -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(values), freq="D")
    segment_ids = segments or ["2020_segment_1"] * len(values)
    return pd.DataFrame(
        {
            "date": dates,
            "year": dates.year,
            "CHLF": values,
            "common_support": True,
            "reference_value_available": True,
            "common_support_segment_id": segment_ids,
        }
    )


def _reference_rows(
    times_and_segments: list[tuple[str, str]],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": f"ERK_2020_E{index:02d}",
                "year": 2020,
                "event_time": pd.Timestamp(event_time),
                "common_support_segment_id": segment,
                "reference_magnitude": float(10 + index),
                "yearly_scale_q95_minus_q05": 10.0,
            }
            for index, (event_time, segment) in enumerate(
                times_and_segments, start=1
            )
        ]
    )


def _candidate_rows(
    times_segments_magnitudes: list[tuple[str, str, float]],
) -> pd.DataFrame:
    if not times_segments_magnitudes:
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
            for index, (event_time, segment, magnitude) in enumerate(
                times_segments_magnitudes, start=1
            )
        ]
    )


def synthetic_event_gate_results() -> dict[str, bool]:
    """Exercise candidate detection/matching without real reconstructions."""

    plateau_support = _support([0, 0, 10, 10, 0, 0])
    plateau_reference = detect_reference_major_events(plateau_support)
    plateau_ok = bool(
        len(plateau_reference) == 1
        and plateau_reference.iloc[0]["event_time"]
        == pd.Timestamp("2020-01-03 12:00:00")
        and plateau_reference.iloc[0]["plateau_size_days"] == 2
    )

    candidate_support = _support([0, 0, 0, 0, 0, 0, 0])
    low = detect_reconstruction_peak_candidates(
        candidate_support,
        pd.Series(
            [0, 0.001, 0, 0.002, 0, 0.0001, 0],
            index=candidate_support["date"],
        ),
    )
    high = detect_reconstruction_peak_candidates(
        candidate_support,
        pd.Series(
            [0, 1000, 0, 1, 0, 50000, 0],
            index=candidate_support["date"],
        ),
    )
    amplitude_candidate_ok = bool(
        low.status == high.status == "ok"
        and low.candidates["event_time"].tolist()
        == high.candidates["event_time"].tolist()
        and len(low.candidates) == 3
    )

    amplitude_reference = _reference_rows(
        [("2020-01-10", "s1"), ("2020-01-20", "s1")]
    )
    early_large = _candidate_rows(
        [("2020-01-09", "s1", 1e12), ("2020-01-21", "s1", 1e-12)]
    )
    early_small = early_large.copy()
    early_small["reconstructed_magnitude"] = [1e-12, 1e12]
    matched_large = match_reference_events(amplitude_reference, early_large)
    matched_small = match_reference_events(amplitude_reference, early_small)
    amplitude_matching_ok = bool(
        matched_large["matched_candidate_id"].tolist()
        == matched_small["matched_candidate_id"].tolist()
        and matched_large["reconstructed_event_time"].tolist()
        == matched_small["reconstructed_event_time"].tolist()
    )

    one_candidate = _candidate_rows([("2020-01-12", "s1", 99.0)])
    one_to_one = match_reference_events(amplitude_reference, one_candidate)
    cardinality_first = match_reference_events(
        amplitude_reference,
        _candidate_rows(
            [("2020-01-01", "s1", 1e12), ("2020-01-11", "s1", 1e-12)]
        ),
    )
    one_to_one_ok = bool(
        one_to_one["event_status"].eq("matched").sum() == 1
        and one_to_one.iloc[0]["event_status"] == "matched"
        and one_to_one.iloc[1]["event_status"]
        == "missed_no_peak_within_15d"
        and cardinality_first["event_status"].eq("matched").all()
        and cardinality_first["reconstructed_event_time"].tolist()
        == [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-11")]
    )

    tie_reference = _reference_rows([("2020-01-10", "s1")])
    tie_candidates = _candidate_rows(
        [("2020-01-09", "s1", -1e9), ("2020-01-11", "s1", 1e9)]
    )
    tie_first = match_reference_events(tie_reference, tie_candidates)
    tie_second = match_reference_events(tie_reference, tie_candidates)
    deterministic_matching_ok = bool(
        tie_first.iloc[0]["reconstructed_event_time"]
        == pd.Timestamp("2020-01-09")
        and deterministic_table_sha256(tie_first)
        == deterministic_table_sha256(tie_second)
    )

    segment_support = _support(
        [0, 2, 0, 0, 3, 0],
        segments=["s1", "s1", "s1", "s2", "s2", "s2"],
    )
    segment_candidates = detect_reconstruction_peak_candidates(
        segment_support,
        pd.Series([0, 2, 0, 0, 3, 0], index=segment_support["date"]),
    )
    wrong_segment = match_reference_events(
        _reference_rows([("2020-01-05", "s1")]),
        _candidate_rows([("2020-01-05", "s2", 3.0)]),
    )
    segment_boundary_ok = bool(
        segment_candidates.status == "ok"
        and len(segment_candidates.candidates) == 2
        and wrong_segment.iloc[0]["event_status"]
        == "missed_no_peak_within_15d"
    )

    missed_reference = _reference_rows([("2020-02-01", "s1")])
    missed = match_reference_events(
        missed_reference,
        _candidate_rows([]),
    ).iloc[0]
    unavailable = match_reference_events(
        missed_reference,
        _candidate_rows([]),
        reconstruction_status="unavailable",
        failure_reason="synthetic_reconstruction_failed",
    ).iloc[0]
    missed_ok = bool(
        missed["event_status"] == "missed_no_peak_within_15d"
        and not bool(missed["success_5d"])
        and not bool(missed["success_10d"])
        and not bool(missed["success_15d"])
        and unavailable["event_status"] == "unavailable"
        and pd.isna(unavailable["success_5d"])
        and pd.isna(unavailable["success_10d"])
        and pd.isna(unavailable["success_15d"])
    )

    threshold_reference = _reference_rows(
        [
            ("2020-03-01", "s1"),
            ("2020-04-01", "s2"),
            ("2020-05-01", "s3"),
        ]
    )
    threshold_candidates = _candidate_rows(
        [
            ("2020-03-06", "s1", 1.0),
            ("2020-04-11", "s2", 1.0),
            ("2020-05-16", "s3", 1.0),
        ]
    )
    thresholds = match_reference_events(
        threshold_reference, threshold_candidates
    ).reset_index(drop=True)
    threshold_ok = bool(
        thresholds["absolute_timing_error_days"].tolist() == [5.0, 10.0, 15.0]
        and thresholds["success_5d"].tolist() == [True, False, False]
        and thresholds["success_10d"].tolist() == [True, True, False]
        and thresholds["success_15d"].tolist() == [True, True, True]
    )
    return {
        "deterministic_matching_tests": deterministic_matching_ok,
        "amplitude_independence_test": (
            amplitude_candidate_ok and amplitude_matching_ok
        ),
        "plateau_test": plateau_ok,
        "one_to_one_matching_test": one_to_one_ok,
        "segment_boundary_test": segment_boundary_ok,
        "missed_event_test": missed_ok,
        "threshold_5_10_15_tests": threshold_ok,
    }


def _validate_reference_regression(events: pd.DataFrame) -> dict[str, bool]:
    actual_events = list(zip(events["event_id"], events["event_date"], strict=True))
    actual_counts = events.groupby("year", sort=True).size().to_dict()
    scale_ok = True
    for year, (expected_decimal, places) in EXPECTED_SCALE_DECIMALS.items():
        values = events.loc[
            events["year"].eq(year), "yearly_scale_q95_minus_q05"
        ].unique()
        if (
            len(values) != 1
            or format(float(values[0]), f".{places}f") != expected_decimal
        ):
            scale_ok = False
    return {
        "exact_18_reference_events": len(events) == 18,
        "exact_reference_dates_and_ids": actual_events == list(EXPECTED_EVENT_TIMES),
        "exact_yearly_event_counts": actual_counts == EXPECTED_YEARLY_COUNTS,
        "exact_yearly_q95_minus_q05_scales": scale_ok,
        "reference_distance_30_days": bool(
            events["reference_distance_days"].eq(30).all()
        ),
        "reference_prominence_0_30_scale": bool(
            np.allclose(
                events["prominence_threshold"],
                0.30 * events["yearly_scale_q95_minus_q05"],
                rtol=0,
                atol=0,
            )
        ),
        "reference_preprocessing_none": bool(
            events["preprocessing_applied"].eq("none").all()
        ),
    }


def build_event_preflight_products(
    *, repository_root: str | Path, temporal_master_path: str | Path
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Build only reference events and synthetic pre-performance gates."""

    root = Path(repository_root)
    config_path = root / "config" / "seasonal_event_protocol_v1.0.json"
    config = load_event_protocol_config(root, config_path)
    parent = validate_parent_actual_mask_benchmark(config, repository_root=root)
    expected_master_hash = config["reference"]["temporal_master_sha256"]
    if sha256_file(temporal_master_path) != expected_master_hash:
        raise EventProtocolError("Frozen Phase 3 temporal master changed.")
    support = build_common_support(read_phase3_master(temporal_master_path))
    events = detect_reference_major_events(support)
    reference_gates = _validate_reference_regression(events)
    synthetic_gates = synthetic_event_gate_results()
    all_gates = {**reference_gates, **synthetic_gates}
    if not all(reference_gates.values()):
        failures = [name for name, passed in reference_gates.items() if not passed]
        raise EventProtocolError(
            "Frozen reference-only event regression mismatch: " + ", ".join(failures)
        )

    table_name = "erken_phase3_reference_events.csv"
    table_hash = deterministic_table_sha256(events)
    event_result = [
        {"event_id": str(row.event_id), "event_time": str(row.event_date)}
        for row in events.itertuples(index=False)
    ]
    yearly_counts = {
        str(year): int(count)
        for year, count in events.groupby("year", sort=True).size().items()
    }
    yearly_scales = {
        str(year): format(
            float(
                events.loc[
                    events["year"].eq(year), "yearly_scale_q95_minus_q05"
                ].iloc[0]
            ),
            f".{EXPECTED_SCALE_DECIMALS[year][1]}f",
        )
        for year in EXPECTED_YEARLY_COUNTS
    }
    implementation = _implementation_provenance(root)
    gates = [
        {"gate": name, "passed": bool(passed)}
        for name, passed in all_gates.items()
    ]
    gates.append(
        {
            "gate": "parent_actual_mask_benchmark_unchanged",
            "passed": parent["parent_actual_mask_benchmark_unchanged"],
        }
    )
    manifest: dict[str, Any] = {
        "schema_version": "erken_phase3_event_preperformance_gate_v1",
        "protocol_version": PROTOCOL_VERSION,
        "analysis_classification": ANALYSIS_CLASSIFICATION,
        "parent_contract_version": CONTRACT_VERSION,
        "protocol_sha256": sha256_file(
            root / config["protocol_document"]["path"]
        ),
        "config_sha256": sha256_file(config_path),
        "config_payload_sha256": config["config_payload_sha256"],
        "repository_commit": implementation["repository_commit"],
        "scipy_version": scipy.__version__,
        "reference_event_count": len(events),
        "reference_events": event_result,
        "reference_event_counts_by_year": yearly_counts,
        "reference_yearly_scale_q95_minus_q05": yearly_scales,
        "reference_event_table": table_name,
        "reference_event_table_sha256": table_hash,
        "synthetic_preperformance_tests": synthetic_gates,
        "parent_actual_mask_benchmark": parent,
        "implementation_provenance": implementation,
        "gates": gates,
        "all_preperformance_gates_passed": all(
            bool(gate["passed"]) for gate in gates
        ),
        "event_level_performance_generated": False,
        "event_level_performance_inspected": False,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    return {table_name: events}, manifest


def write_event_preflight_products(
    tables: Mapping[str, pd.DataFrame],
    manifest: Mapping[str, Any],
    output_directory: str | Path,
) -> list[Path]:
    output = Path(output_directory)
    paths = [
        write_deterministic_csv(table, output / name)
        for name, table in tables.items()
    ]
    paths.append(
        write_deterministic_json(
            manifest,
            output / "erken_phase3_event_preperformance_gate.json",
        )
    )
    return paths
