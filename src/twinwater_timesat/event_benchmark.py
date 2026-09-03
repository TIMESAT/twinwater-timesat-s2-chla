"""Guarded actual-mask seasonal-event benchmark and mechanical audit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

import numpy as np
import pandas as pd
import scipy

from twinwater_timesat.event_preflight import deterministic_table_sha256
from twinwater_timesat.phase3_contract import (
    CONTRACT_VERSION,
    canonical_json_payload_sha256,
    sha256_file,
)
from twinwater_timesat.phase3_preflight import (
    write_deterministic_csv,
    write_deterministic_json,
)
from twinwater_timesat.reconstruction_support import (
    build_common_support,
    read_phase3_master,
)
from twinwater_timesat.seasonal_events import (
    EXPECTED_EVENT_TIMES,
    FROZEN_SPLINE_SELECTIONS,
    PROTOCOL_VERSION,
    detect_reconstruction_peak_candidates,
    detect_reference_major_events,
    load_event_protocol_config,
    match_detected_reconstruction_events,
    validate_parent_actual_mask_benchmark,
)


STARTING_COMMIT = "9345c7af644c1e6ab0924834235167b688a1ed61"
METHODS = (
    "linear_interpolation",
    "timesat_double_logistic",
    "timesat_smoothing_spline",
)
IMPLEMENTATION_PATHS = (
    "src/twinwater_timesat/seasonal_events.py",
    "src/twinwater_timesat/event_benchmark.py",
    "scripts/11_erken_phase3_event_actual_mask.py",
    "scripts/12_erken_phase3_event_audit.py",
    "tests/test_event_benchmark.py",
)


class EventBenchmarkGuardError(RuntimeError):
    """Raised before any event-performance output when a hard gate fails."""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _require_clean_descendant(root: Path) -> str:
    dirty = _git(root, "status", "--porcelain")
    if dirty:
        raise EventBenchmarkGuardError(
            "Refusing seasonal-event performance: repository worktree is dirty."
        )
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", STARTING_COMMIT, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise EventBenchmarkGuardError(
            f"Current HEAD does not descend from required commit {STARTING_COMMIT}."
        )
    return _git(root, "rev-parse", "HEAD")


def _bundle_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for relative in IMPLEMENTATION_PATHS:
        path = root / relative
        if not path.is_file():
            raise EventBenchmarkGuardError(f"Missing implementation file: {relative}")
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(sha256_file(path).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def validate_actual_event_prerun(root: str | Path) -> dict[str, Any]:
    """Run every Phase A hard gate before reading reconstruction values."""

    root = Path(root)
    commit = _require_clean_descendant(root)
    config = load_event_protocol_config(root)
    parent = validate_parent_actual_mask_benchmark(config, repository_root=root)
    event_manifest_path = (
        root
        / "results/phase3/event_preflight/erken_phase3_event_preperformance_gate.json"
    )
    event_manifest = json.loads(event_manifest_path.read_text(encoding="utf-8"))
    if event_manifest.get("manifest_payload_sha256") != canonical_json_payload_sha256(
        event_manifest, excluded_keys=("manifest_payload_sha256",)
    ):
        raise EventBenchmarkGuardError("Event preflight manifest checksum failed.")
    required = {
        "all_preperformance_gates_passed": True,
        "event_level_performance_generated": False,
        "event_level_performance_inspected": False,
        "reference_event_count": 18,
    }
    for key, expected in required.items():
        if event_manifest.get(key) != expected:
            raise EventBenchmarkGuardError(
                f"Event preflight gate {key} must equal {expected!r}."
            )
    master_path = root / config["reference"]["temporal_master_path"]
    support = build_common_support(read_phase3_master(master_path))
    references = detect_reference_major_events(support)
    actual_events = list(
        zip(references["event_id"], references["event_date"], strict=True)
    )
    if actual_events != list(EXPECTED_EVENT_TIMES):
        raise EventBenchmarkGuardError("The frozen 18 reference events changed.")
    selection = pd.read_csv(
        root / "results/phase3/actual_mask/erken_phase3_spline_selection.csv"
    )
    actual_selection = dict(
        zip(
            selection["outer_test_year"].astype(int),
            selection["selected_smoothing"].astype(int),
            strict=True,
        )
    )
    if actual_selection != FROZEN_SPLINE_SELECTIONS:
        raise EventBenchmarkGuardError("Frozen spline selections changed.")
    return {
        "repository_code_commit": commit,
        "repository_worktree_dirty": False,
        "implementation_bundle_sha256": _bundle_sha256(root),
        "event_preflight_manifest_payload_sha256": event_manifest[
            "manifest_payload_sha256"
        ],
        **parent,
    }


def _year_method_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (year, method), group in events.groupby(["year", "method"], sort=True):
        available = group["event_status"].ne("unavailable")
        matched = group["event_status"].eq("matched")
        method_failed = group["reconstruction_status"].ne("ok")
        row: dict[str, Any] = {
            "year": int(year),
            "method": method,
            "n_reference_events": int(len(group)),
            "n_available_reference_events": int(available.sum()),
            "n_matched_events": int(matched.sum()),
            "n_missed_events": int(
                group["event_status"].eq("missed_no_peak_within_15d").sum()
            ),
            "n_unavailable_events": int(group["event_status"].eq("unavailable").sum()),
            "n_method_failures": int(method_failed.any()),
        }
        denominator = int(available.sum())
        for days in (5, 10, 15):
            row[f"recovery_fraction_{days}d"] = (
                float(group.loc[available, f"success_{days}d"].astype(bool).mean())
                if denominator
                else np.nan
            )
        row["mean_absolute_timing_error_matched_days"] = float(
            group.loc[matched, "absolute_timing_error_days"].mean()
        )
        row["median_absolute_timing_error_matched_days"] = float(
            group.loc[matched, "absolute_timing_error_days"].median()
        )
        for metric in (
            "absolute_magnitude_error",
            "normalized_absolute_magnitude_error",
        ):
            row[f"mean_{metric}_matched"] = float(group.loc[matched, metric].mean())
            row[f"median_{metric}_matched"] = float(
                group.loc[matched, metric].median()
            )
        rows.append(row)
    return pd.DataFrame(rows)


def build_actual_mask_event_products(
    *, repository_root: str | Path
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Compute frozen Phase A event outputs from immutable parent trajectories."""

    root = Path(repository_root)
    provenance = validate_actual_event_prerun(root)
    config = load_event_protocol_config(root)
    support = build_common_support(
        read_phase3_master(root / config["reference"]["temporal_master_path"])
    )
    references = detect_reference_major_events(support)
    daily_path = (
        root
        / "results/phase3/actual_mask/erken_phase3_actual_mask_daily_reconstructions.csv"
    )
    daily = pd.read_csv(daily_path, parse_dates=["date"])
    rows: list[pd.DataFrame] = []
    for year in sorted(references["year"].unique()):
        year_support = support.loc[support["year"].eq(year)].copy()
        year_references = references.loc[references["year"].eq(year)].copy()
        for method in METHODS:
            curve = daily.loc[
                daily["outer_test_year"].eq(year) & daily["method"].eq(method)
            ].copy()
            statuses = curve["reconstruction_status"].drop_duplicates().tolist()
            status = statuses[0] if len(statuses) == 1 else "unavailable"
            reasons = curve["reconstruction_failure_reason"].dropna().astype(str)
            reason = ";".join(sorted(set(reasons)))
            detection = detect_reconstruction_peak_candidates(
                year_support,
                curve[["date", "prediction"]],
                reconstruction_status="ok" if status == "ok" else "unavailable",
                failure_reason=reason,
            )
            matched = match_detected_reconstruction_events(year_references, detection)
            matched.insert(2, "method", method)
            matched["reconstruction_status"] = status
            matched["reconstruction_failure_code"] = (
                reason if reason else detection.failure_reason
            )
            matched["reconstructed_prominence_diagnostic"] = np.nan
            rows.append(matched)
    events = pd.concat(rows, ignore_index=True).sort_values(
        ["year", "method", "reference_event_time"], kind="mergesort"
    ).reset_index(drop=True)
    summary = _year_method_summary(events)
    audit_summary = pd.DataFrame(
        [
            {
                "n_event_rows": len(events),
                "n_reference_events": references["event_id"].nunique(),
                "n_methods": events["method"].nunique(),
                "n_matched": int(events["event_status"].eq("matched").sum()),
                "n_missed": int(
                    events["event_status"].eq("missed_no_peak_within_15d").sum()
                ),
                "n_unavailable": int(events["event_status"].eq("unavailable").sum()),
                "event_protocol_version": PROTOCOL_VERSION,
            }
        ]
    )
    tables = {
        "erken_phase3_actual_mask_event_metrics.csv": events,
        "erken_phase3_actual_mask_event_year_method_summary.csv": summary,
        "erken_phase3_actual_mask_event_audit_summary.csv": audit_summary,
    }
    table_hashes = {
        name: deterministic_table_sha256(table) for name, table in tables.items()
    }
    manifest: dict[str, Any] = {
        "schema_version": "erken_phase3_actual_mask_event_benchmark_manifest_v1",
        "contract_version": CONTRACT_VERSION,
        "event_protocol_version": PROTOCOL_VERSION,
        "analysis_classification": "secondary_exploratory",
        "repository_code_commit": provenance["repository_code_commit"],
        "repository_worktree_dirty": False,
        "provenance": provenance,
        "scipy_version": scipy.__version__,
        "methods": list(METHODS),
        "n_reference_events": 18,
        "n_event_method_rows": len(events),
        "frozen_spline_selections": {
            str(k): v for k, v in FROZEN_SPLINE_SELECTIONS.items()
        },
        "parent_daily_reconstruction_sha256": sha256_file(daily_path),
        "table_sha256": table_hashes,
        "event_level_performance_generated": True,
        "scientific_interpretation_performed_by_pipeline": False,
        "method_ranking_generated": False,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    return tables, manifest


def write_actual_mask_event_products(
    tables: Mapping[str, pd.DataFrame],
    manifest: Mapping[str, Any],
    output_directory: str | Path,
) -> list[Path]:
    output = Path(output_directory)
    paths = [
        write_deterministic_csv(table, output / name) for name, table in tables.items()
    ]
    paths.append(
        write_deterministic_json(
            manifest,
            output / "erken_phase3_actual_mask_event_benchmark_manifest.json",
        )
    )
    return paths


def audit_actual_mask_event_products(
    *, repository_root: str | Path, output_directory: str | Path
) -> dict[str, Any]:
    """Independently regenerate and verify every frozen Phase B invariant."""

    root = Path(repository_root)
    output = Path(output_directory)
    stored_manifest = json.loads(
        (output / "erken_phase3_actual_mask_event_benchmark_manifest.json").read_text()
    )
    stored = pd.read_csv(
        output / "erken_phase3_actual_mask_event_metrics.csv",
        parse_dates=["reference_event_time", "reconstructed_event_time"],
    )
    config = load_event_protocol_config(root)
    parent = validate_parent_actual_mask_benchmark(config, repository_root=root)
    regenerated_tables, _ = build_actual_mask_event_products(repository_root=root)
    flags_ok = True
    for days in (5, 10, 15):
        matched = stored["event_status"].eq("matched")
        flags_ok &= bool(
            stored.loc[matched, f"success_{days}d"].astype(bool).eq(
                stored.loc[matched, "absolute_timing_error_days"].le(days)
            ).all()
        )
    matched = stored.loc[stored["event_status"].eq("matched")]
    checks = {
        "18_events_for_each_method": bool(
            stored.groupby("method")["event_id"].nunique().eq(18).all()
            and set(stored["method"]) == set(METHODS)
        ),
        "one_to_one_matching": bool(
            not matched.duplicated(["year", "method", "matched_candidate_id"]).any()
        ),
        "no_match_beyond_15_days": bool(
            matched["absolute_timing_error_days"].le(15).all()
        ),
        "timing_threshold_flags_exact": flags_ok,
        "valid_unmatched_status_exact": bool(
            stored.loc[
                stored["reconstruction_status"].eq("ok")
                & stored["matched_candidate_id"].isna(),
                "event_status",
            ].eq("missed_no_peak_within_15d").all()
        ),
        "failures_are_unavailable": bool(
            stored.loc[
                stored["reconstruction_status"].ne("ok"), "event_status"
            ].eq("unavailable").all()
        ),
        "magnitude_not_used_for_matching": bool(
            stored["magnitude_used_for_matching"].eq(False).all()  # noqa: E712
        ),
        "frozen_spline_selections": stored_manifest.get(
            "frozen_spline_selections"
        )
        == {str(k): v for k, v in FROZEN_SPLINE_SELECTIONS.items()},
        "actual_mask_parent_unchanged": parent[
            "parent_actual_mask_benchmark_unchanged"
        ],
    }
    table_hashes_ok = all(
        sha256_file(output / name) == expected
        for name, expected in stored_manifest["table_sha256"].items()
    )
    checks["stored_table_checksums"] = table_hashes_ok
    checks["deterministic_byte_for_byte_regeneration"] = all(
        deterministic_table_sha256(table) == stored_manifest["table_sha256"][name]
        for name, table in regenerated_tables.items()
    )
    audit: dict[str, Any] = {
        "schema_version": "erken_phase3_actual_mask_event_audit_v1",
        "audit_status": "PASS" if all(checks.values()) else "HOLD",
        "checks": checks,
        "benchmark_manifest_payload_sha256": stored_manifest[
            "manifest_payload_sha256"
        ],
        "parent_actual_mask_benchmark_unchanged": parent[
            "parent_actual_mask_benchmark_unchanged"
        ],
    }
    audit["audit_payload_sha256"] = canonical_json_payload_sha256(audit)
    return audit
