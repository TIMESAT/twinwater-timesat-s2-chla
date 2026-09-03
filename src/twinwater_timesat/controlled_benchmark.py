"""Frozen controlled-gap reconstruction and event-performance execution."""

from __future__ import annotations

from contextlib import AbstractContextManager
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

import numpy as np
import pandas as pd

from twinwater_timesat.event_benchmark import METHODS, _require_clean_descendant
from twinwater_timesat.controlled_gaps import (
    generate_consecutive_gap_windows,
    generate_random_deletion_masks,
)
from twinwater_timesat.phase3_contract import (
    CONTRACT_VERSION,
    canonical_json_payload_sha256,
    load_contract_config,
    load_timesat_defaults_snapshot,
    sha256_file,
)
from twinwater_timesat.phase3_preflight import (
    deterministic_table_sha256,
    write_deterministic_csv,
    write_deterministic_json,
)
from twinwater_timesat.reconstruction_benchmark import (
    evaluate_method_result,
    sparse_input_checksum,
)
from twinwater_timesat.reconstruction_support import (
    build_common_support,
    read_phase3_master,
)
from twinwater_timesat.seasonal_events import (
    FROZEN_SPLINE_SELECTIONS,
    PROTOCOL_VERSION,
    detect_reconstruction_peak_candidates,
    detect_reference_major_events,
    load_event_protocol_config,
    match_detected_reconstruction_events,
    validate_parent_actual_mask_benchmark,
)
from twinwater_timesat.timesat_adapter import (
    ReconstructionResult,
    SubprocessTimesatRunner,
    linear_reconstruct,
)


FAMILIES = {
    "random_deletion": "erken_phase3_random_deletion_masks.csv",
    "consecutive_internal_gap": "erken_phase3_consecutive_gap_windows.csv",
}


class PersistentTimesatRunner(AbstractContextManager):
    """Reuse one verified external runtime without changing TIMESAT calls."""

    def __init__(self, python: Path, script: Path, snapshot: Path):
        self.process = subprocess.Popen(
            [str(python), str(script), str(snapshot)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def reconstruct(
        self,
        *,
        method: str,
        year: int,
        sparse: pd.DataFrame,
        target_dates: pd.Series | pd.DatetimeIndex,
        smoothing: int | None = None,
    ) -> ReconstructionResult:
        request = {
            "method": method,
            "year": year,
            "dates": pd.to_datetime(sparse["date"]).dt.strftime("%Y-%m-%d").tolist(),
            "values": sparse["CHLF"].astype(float).tolist(),
            "smoothing": smoothing,
        }
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeError(f"Persistent TIMESAT runtime stopped: {stderr}")
        response = json.loads(line)
        targets = pd.DatetimeIndex(pd.to_datetime(target_dates)).normalize()
        if not response["ok"]:
            return ReconstructionResult(
                method,
                year,
                "failed",
                f"{response['error_type']}: {response['error']}",
                pd.DataFrame({"date": targets, "prediction": np.nan}),
                {"persistent_batch_transport": True},
            )
        result = response["result"]
        full = pd.DataFrame(
            {
                "date": pd.to_datetime(result["dates"]),
                "prediction": pd.to_numeric(result["prediction"]),
            }
        )
        prediction = pd.DataFrame({"date": targets}).merge(
            full, on="date", how="left", validate="one_to_one"
        )
        return ReconstructionResult(
            method,
            year,
            result["status"],
            result["failure_reason"],
            prediction,
            {**result["diagnostics"], "persistent_batch_transport": True},
        )

    def __exit__(self, exc_type, exc, traceback):
        if self.process.stdin:
            self.process.stdin.close()
        return_code = self.process.wait(timeout=30)
        if exc is None and return_code != 0:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeError(f"TIMESAT batch runtime failed: {stderr}")
        return False


def _deleted_dates(value: Any) -> pd.DatetimeIndex:
    if pd.isna(value) or not str(value):
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(pd.to_datetime(str(value).split(";"))).normalize()


def _scenario_support(support: pd.DataFrame, scenario: Any) -> pd.DataFrame:
    year_support = support.loc[support["year"].eq(int(scenario.year))].copy()
    deleted = _deleted_dates(scenario.deleted_dates)
    year_support.loc[
        year_support["date"].isin(deleted), "s2_openwater_reference_candidate"
    ] = False
    return year_support


def _methods_for_scenario(
    year_support: pd.DataFrame,
    *,
    runner: PersistentTimesatRunner,
    smoothing: int,
) -> dict[str, ReconstructionResult]:
    year = int(year_support["year"].iloc[0])
    sparse = year_support.loc[
        year_support["s2_openwater_reference_candidate"], ["date", "CHLF"]
    ].copy()
    targets = year_support.loc[year_support["common_support"], "date"]
    checksum = sparse_input_checksum(sparse)
    results = {
        "linear_interpolation": linear_reconstruct(
            year=year, sparse=sparse.copy(), target_dates=targets
        ),
        "timesat_double_logistic": runner.reconstruct(
            method="timesat_double_logistic",
            year=year,
            sparse=sparse.copy(),
            target_dates=targets,
        ),
        "timesat_smoothing_spline": runner.reconstruct(
            method="timesat_smoothing_spline",
            year=year,
            sparse=sparse.copy(),
            target_dates=targets,
            smoothing=smoothing,
        ),
    }
    return {
        method: ReconstructionResult(
            result.method,
            result.year,
            result.status,
            result.failure_reason,
            result.prediction,
            {
                **result.diagnostics,
                "sparse_input_checksum": checksum,
                "identical_sparse_input_enforced": True,
            },
        )
        for method, result in results.items()
    }


def validate_controlled_prerun(root: Path, timesat_python: Path) -> dict[str, Any]:
    commit = _require_clean_descendant(root)
    event_config = load_event_protocol_config(root)
    parent = validate_parent_actual_mask_benchmark(event_config, repository_root=root)
    contract = load_contract_config(root)
    snapshot = load_timesat_defaults_snapshot(root / contract["timesat_defaults_snapshot"])
    runner = SubprocessTimesatRunner(
        python_executable=timesat_python,
        runtime_script=root / "scripts/07_timesat_runtime.py",
        snapshot_path=root / contract["timesat_defaults_snapshot"],
    )
    runtime = runner.verify_runtime(smoke_test=True)
    preflight_path = root / "results/phase3/preflight/erken_phase3_preperformance_gate.json"
    preflight = json.loads(preflight_path.read_text())
    if not preflight.get("all_preperformance_gates_passed"):
        raise RuntimeError("Parent Phase 3 preflight is not passed.")
    for filename in FAMILIES.values():
        if sha256_file(preflight_path.parent / filename) != preflight["table_sha256"][filename]:
            raise RuntimeError(f"Controlled mask manifest changed: {filename}")
    event_preflight = json.loads(
        (root / "results/phase3/event_preflight/erken_phase3_event_preperformance_gate.json").read_text()
    )
    if not event_preflight.get("all_preperformance_gates_passed"):
        raise RuntimeError("Event reference preflight is not passed.")
    return {
        "repository_code_commit": commit,
        "repository_worktree_dirty": False,
        "parent_actual_mask_benchmark_unchanged": parent[
            "parent_actual_mask_benchmark_unchanged"
        ],
        "preperformance_manifest_payload_sha256": preflight[
            "manifest_payload_sha256"
        ],
        "event_preflight_manifest_payload_sha256": event_preflight[
            "manifest_payload_sha256"
        ],
        "timesat_core_version": runtime["timesat_core_version"],
        "timesat_cli_version": runtime["timesat_cli_version"],
        "timesat_defaults_snapshot_payload_sha256": snapshot[
            "snapshot_payload_sha256"
        ],
    }


def run_controlled_family(
    *,
    repository_root: str | Path,
    timesat_python: str | Path,
    family: str,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    root = Path(repository_root)
    if family not in FAMILIES:
        raise ValueError(f"Unknown controlled family: {family}")
    provenance = validate_controlled_prerun(root, Path(timesat_python))
    config = load_event_protocol_config(root)
    support = build_common_support(
        read_phase3_master(root / config["reference"]["temporal_master_path"])
    )
    references = detect_reference_major_events(support)
    mask_path = root / "results/phase3/preflight" / FAMILIES[family]
    scenarios = pd.read_csv(mask_path)
    metric_rows: list[dict[str, Any]] = []
    event_tables: list[pd.DataFrame] = []
    snapshot = root / "config/timesat_double_logistic_defaults_v4.4.1.json"
    with PersistentTimesatRunner(
        Path(timesat_python), root / "scripts/13_timesat_batch_runtime.py", snapshot
    ) as runner:
        for index, scenario in enumerate(scenarios.itertuples(index=False), start=1):
            year_support = _scenario_support(support, scenario)
            year = int(scenario.year)
            results = _methods_for_scenario(
                year_support,
                runner=runner,
                smoothing=FROZEN_SPLINE_SELECTIONS[year],
            )
            for method in METHODS:
                result = results[method]
                metrics, _ = evaluate_method_result(
                    year_support,
                    result,
                    provenance={
                        "contract_version": CONTRACT_VERSION,
                        "mask_id": scenario.mask_id,
                        "scenario_family": family,
                        "selected_smoothing": (
                            FROZEN_SPLINE_SELECTIONS[year]
                            if method == "timesat_smoothing_spline"
                            else np.nan
                        ),
                    },
                )
                metric_rows.append(metrics)
                detection = detect_reconstruction_peak_candidates(
                    year_support,
                    result.prediction,
                    reconstruction_status=result.status,
                    failure_reason=result.failure_reason,
                )
                event = match_detected_reconstruction_events(
                    references.loc[references["year"].eq(year)], detection
                )
                event.insert(2, "method", method)
                event.insert(3, "mask_id", scenario.mask_id)
                event.insert(4, "scenario_family", family)
                event["reconstruction_status"] = result.status
                event["reconstruction_failure_code"] = result.failure_reason
                event_tables.append(event)
            if index % 100 == 0 or index == len(scenarios):
                print(f"{family}: {index}/{len(scenarios)} scenarios", flush=True)
    metrics = pd.DataFrame(metric_rows).sort_values(
        ["year", "mask_id", "method"], kind="mergesort"
    ).reset_index(drop=True)
    events = pd.concat(event_tables, ignore_index=True).sort_values(
        ["year", "mask_id", "method", "reference_event_time"],
        kind="mergesort",
    ).reset_index(drop=True)
    prefix = "random_deletion" if family == "random_deletion" else "consecutive_gaps"
    tables = {
        f"erken_phase4_{prefix}_scenario_method_metrics.csv": metrics,
        f"erken_phase4_{prefix}_event_metrics.csv": events,
    }
    manifest: dict[str, Any] = {
        "schema_version": f"erken_phase4_{prefix}_manifest_v1",
        "contract_version": CONTRACT_VERSION,
        "event_protocol_version": PROTOCOL_VERSION,
        "analysis_classification": "controlled_gap_secondary",
        "scenario_family": family,
        "repository_code_commit": provenance["repository_code_commit"],
        "repository_worktree_dirty": False,
        "provenance": provenance,
        "mask_manifest_path": str(mask_path.relative_to(root)),
        "mask_manifest_sha256": sha256_file(mask_path),
        "n_scenarios": len(scenarios),
        "n_scenario_method_rows": len(metrics),
        "n_event_rows": len(events),
        "methods": list(METHODS),
        "frozen_spline_selections": {
            str(k): v for k, v in FROZEN_SPLINE_SELECTIONS.items()
        },
        "table_sha256": {
            name: deterministic_table_sha256(table) for name, table in tables.items()
        },
        "method_status_counts": {
            str(k): int(v)
            for k, v in metrics["reconstruction_status"].value_counts().items()
        },
        "scientific_interpretation_performed_by_pipeline": False,
        "method_ranking_generated": False,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    return tables, manifest


def write_controlled_family(
    tables: Mapping[str, pd.DataFrame],
    manifest: Mapping[str, Any],
    output: str | Path,
) -> list[Path]:
    output = Path(output)
    paths = [write_deterministic_csv(table, output / name) for name, table in tables.items()]
    name = "erken_phase4_controlled_gap_manifest.json"
    paths.append(write_deterministic_json(manifest, output / name))
    return paths


def audit_controlled_family(
    *, repository_root: str | Path, family: str
) -> dict[str, Any]:
    """Mechanically audit a completed controlled-gap family."""

    root = Path(repository_root)
    if family not in FAMILIES:
        raise ValueError(f"Unknown controlled family: {family}")
    prefix = "random_deletion" if family == "random_deletion" else "consecutive_gaps"
    output = (
        root / "results/phase4/random_deletion"
        if family == "random_deletion"
        else root / "results/phase4/consecutive_gaps"
    )
    manifest = json.loads(
        (output / "erken_phase4_controlled_gap_manifest.json").read_text()
    )
    metrics = pd.read_csv(
        output / f"erken_phase4_{prefix}_scenario_method_metrics.csv"
    )
    events = pd.read_csv(output / f"erken_phase4_{prefix}_event_metrics.csv")
    masks = pd.read_csv(root / "results/phase3/preflight" / FAMILIES[family])
    config = load_event_protocol_config(root)
    parent = validate_parent_actual_mask_benchmark(config, repository_root=root)
    support = build_common_support(
        read_phase3_master(root / config["reference"]["temporal_master_path"])
    )
    regenerated_masks = (
        generate_random_deletion_masks(support)
        if family == "random_deletion"
        else generate_consecutive_gap_windows(support)
    )
    expected_count = 2800 if family == "random_deletion" else 5746
    per_mask_methods = metrics.groupby("mask_id")["method"].agg(
        ["nunique", "count"]
    )
    spline = metrics["method"].eq("timesat_smoothing_spline")
    selected = metrics.loc[spline, ["year", "selected_smoothing"]].copy()
    selection_ok = all(
        selected.loc[selected["year"].eq(year), "selected_smoothing"].eq(value).all()
        for year, value in FROZEN_SPLINE_SELECTIONS.items()
    )
    failures = metrics["reconstruction_status"].ne("ok")
    failed_keys = set(
        map(tuple, metrics.loc[failures, ["mask_id", "method"]].to_numpy())
    )
    unavailable_keys = set(
        map(
            tuple,
            events.loc[
                events["event_status"].eq("unavailable"), ["mask_id", "method"]
            ].drop_duplicates().to_numpy(),
        )
    )
    checks = {
        "expected_scenario_count": len(masks) == expected_count,
        "deterministic_masks": deterministic_table_sha256(masks)
        == deterministic_table_sha256(regenerated_masks),
        "protected_endpoints": bool(
            masks["frozen_first_sparse_input_date"].eq(
                masks["result_first_sparse_input_date"]
            ).all()
            and masks["frozen_last_sparse_input_date"].eq(
                masks["result_last_sparse_input_date"]
            ).all()
        ),
        "same_mask_all_methods": bool(
            per_mask_methods["nunique"].eq(3).all()
            and per_mask_methods["count"].eq(3).all()
            and metrics.groupby("mask_id")["diagnostic_sparse_input_checksum"]
            .nunique()
            .eq(1)
            .all()
        ),
        "no_cross_segment_or_deduplication": bool(
            masks["mask_id"].is_unique
            and len(masks) == expected_count
            and (
                family == "random_deletion"
                or masks["common_support_segment_id"].notna().all()
            )
        ),
        "a_gap_contract_exact": bool(
            family == "random_deletion"
            and "a_gap" not in masks.columns
            or family == "consecutive_internal_gap"
            and masks["a_gap_status"].eq("ok").all()
        ),
        "no_spline_retuning": selection_ok,
        "parent_actual_mask_unchanged": parent[
            "parent_actual_mask_benchmark_unchanged"
        ],
        "event_reference_set_unchanged": bool(
            events.groupby(["mask_id", "method"])["event_id"].nunique().eq(
                events.groupby(["mask_id", "method"])["year"].first().map(
                    {2019: 2, 2020: 3, 2021: 2, 2022: 2, 2023: 3, 2024: 2, 2025: 4}
                )
            ).all()
        ),
        "failures_preserved": failed_keys == unavailable_keys,
        "output_checksums": all(
            sha256_file(output / name) == expected
            for name, expected in manifest["table_sha256"].items()
        ),
    }
    audit: dict[str, Any] = {
        "schema_version": f"erken_phase4_{prefix}_audit_v1",
        "family": family,
        "audit_status": "PASS" if all(checks.values()) else "HOLD",
        "checks": checks,
        "scenario_count": len(masks),
        "scenario_method_count": len(metrics),
        "event_row_count": len(events),
        "method_status_counts": manifest["method_status_counts"],
        "benchmark_manifest_payload_sha256": manifest[
            "manifest_payload_sha256"
        ],
    }
    audit["audit_payload_sha256"] = canonical_json_payload_sha256(audit)
    return audit
