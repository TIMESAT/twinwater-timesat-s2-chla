"""Executable actual-mask Phase 3 benchmark without scientific interpretation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from twinwater_timesat.phase3_contract import (
    CONTRACT_VERSION,
    PRIMARY_METHODS,
    PRIMARY_YEARS,
    SPLINE_GRID,
    build_outer_folds,
    canonical_json_payload_sha256,
)
from twinwater_timesat.phase3_preflight import (
    deterministic_table_sha256,
    write_deterministic_csv,
    write_deterministic_json,
)
from twinwater_timesat.reconstruction_benchmark import (
    evaluate_method_result,
    reconstruct_all_methods_for_year,
)
from twinwater_timesat.spline_selection import select_spline_for_all_outer_folds
from twinwater_timesat.timesat_adapter import SubprocessTimesatRunner


def _selection_provenance(
    table: pd.DataFrame, provenance: Mapping[str, Any]
) -> pd.DataFrame:
    output = table.copy()
    output.insert(0, "contract_version", CONTRACT_VERSION)
    for key, value in reversed(list(provenance.items())):
        output.insert(1, key, value)
    output["spline_candidate_grid"] = ";".join(map(str, SPLINE_GRID))
    return output


def run_actual_mask_benchmark(
    common_support: pd.DataFrame,
    *,
    runner: SubprocessTimesatRunner,
    provenance: Mapping[str, Any],
) -> dict[str, pd.DataFrame]:
    """Run frozen spline selection and the three outer-year reconstructions.

    This function computes and records contract-defined outputs but does not
    rank methods, summarize a winner, make figures, or interpret performance.
    Callers must complete the pre-performance gate before invoking it.
    """

    selection, candidates, candidate_years = select_spline_for_all_outer_folds(
        common_support, runner=runner
    )
    selection_by_year = selection.set_index("outer_test_year")
    folds = {fold.outer_test_year: fold for fold in build_outer_folds()}
    metric_rows: list[dict[str, Any]] = []
    residual_tables: list[pd.DataFrame] = []
    curve_tables: list[pd.DataFrame] = []

    for year in PRIMARY_YEARS:
        year_support = common_support.loc[common_support["year"].eq(year)].copy()
        selected_raw = selection_by_year.loc[year, "selected_smoothing"]
        selected = None if pd.isna(selected_raw) else int(selected_raw)
        method_results = reconstruct_all_methods_for_year(
            year_support,
            selected_smoothing=selected,
            timesat_runner=runner,
        )
        if tuple(method_results) != PRIMARY_METHODS:
            raise AssertionError("Phase 3 method set/order differs from the contract.")
        fold_provenance = {
            **dict(provenance),
            "contract_version": CONTRACT_VERSION,
            "outer_test_year": year,
            "inner_selection_years": ";".join(
                str(value) for value in folds[year].inner_training_years
            ),
            "spline_candidate_grid": ";".join(map(str, SPLINE_GRID)),
            "selected_smoothing": selected,
            "first_sparse_input_date": year_support.loc[
                year_support["s2_openwater_reference_candidate"], "date"
            ].min(),
            "last_sparse_input_date": year_support.loc[
                year_support["s2_openwater_reference_candidate"], "date"
            ].max(),
            "mask_scenario_id": "actual_sentinel2_primary_sparse_input",
        }
        support_dates = year_support.loc[
            year_support["common_support"],
            [
                "date",
                "year",
                "CHLF",
                "s2_openwater_reference_candidate",
                "common_support_segment_id",
            ],
        ].copy()
        for method in PRIMARY_METHODS:
            reconstruction = method_results[method]
            metrics, residuals = evaluate_method_result(
                year_support,
                reconstruction,
                provenance=fold_provenance,
            )
            metric_rows.append(metrics)
            residuals.insert(0, "contract_version", CONTRACT_VERSION)
            residuals.insert(1, "outer_test_year", year)
            residual_tables.append(residuals)

            curve = support_dates.merge(
                reconstruction.prediction[["date", "prediction"]],
                on="date",
                how="left",
                validate="one_to_one",
            )
            curve.insert(0, "contract_version", CONTRACT_VERSION)
            curve.insert(1, "outer_test_year", year)
            curve.insert(2, "method", method)
            curve["selected_smoothing"] = (
                selected if method == "timesat_smoothing_spline" else np.nan
            )
            curve["reconstruction_status"] = reconstruction.status
            curve["reconstruction_failure_reason"] = reconstruction.failure_reason
            curve_tables.append(curve)

    return {
        "erken_phase3_spline_selection.csv": _selection_provenance(
            selection, provenance
        ),
        "erken_phase3_spline_candidate_summary.csv": _selection_provenance(
            candidates, provenance
        ),
        "erken_phase3_spline_candidate_year_nrmse.csv": _selection_provenance(
            candidate_years, provenance
        ),
        "erken_phase3_actual_mask_daily_reconstructions.csv": pd.concat(
            curve_tables, ignore_index=True
        ),
        "erken_phase3_actual_mask_withheld_residuals.csv": pd.concat(
            residual_tables, ignore_index=True
        ),
        "erken_phase3_actual_mask_year_method_metrics.csv": pd.DataFrame(metric_rows),
    }


def write_actual_mask_benchmark(
    tables: Mapping[str, pd.DataFrame],
    *,
    output_directory: str | Path,
    provenance: Mapping[str, Any],
) -> tuple[list[Path], dict[str, Any]]:
    """Write transparent deterministic tables and a non-interpretive manifest."""

    output = Path(output_directory)
    paths = [
        write_deterministic_csv(table, output / filename)
        for filename, table in tables.items()
    ]
    metrics = tables["erken_phase3_actual_mask_year_method_metrics.csv"]
    manifest: dict[str, Any] = {
        "schema_version": "phase3_actual_mask_benchmark_manifest_v1",
        "contract_version": CONTRACT_VERSION,
        "provenance": dict(provenance),
        "methods": list(PRIMARY_METHODS),
        "outer_years": list(PRIMARY_YEARS),
        "spline_candidate_grid": list(SPLINE_GRID),
        "scientific_interpretation_performed_by_pipeline": False,
        "method_ranking_generated": False,
        "n_year_method_rows": int(len(metrics)),
        "reconstruction_status_counts": {
            str(key): int(value)
            for key, value in metrics["reconstruction_status"]
            .value_counts(dropna=False)
            .sort_index()
            .items()
        },
        "table_sha256": {
            filename: deterministic_table_sha256(table)
            for filename, table in tables.items()
        },
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    manifest_path = output / "erken_phase3_actual_mask_benchmark_manifest.json"
    write_deterministic_json(manifest, manifest_path)
    paths.append(manifest_path)
    return paths, manifest


def load_passed_preperformance_manifest(path: str | Path) -> dict[str, Any]:
    """Load an on-disk gate manifest and reject any non-passed state."""

    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise RuntimeError(
            "Phase 3 pre-performance manifest is missing; run script 08 first."
        )
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_hash = value.get("manifest_payload_sha256")
    actual_hash = canonical_json_payload_sha256(
        value, excluded_keys=("manifest_payload_sha256",)
    )
    if expected_hash != actual_hash:
        raise RuntimeError("Phase 3 pre-performance manifest checksum mismatch.")
    if value.get("schema_version") != "phase3_preperformance_gate_manifest_v1":
        raise RuntimeError("Unexpected Phase 3 pre-performance manifest schema.")
    if value.get("contract_version") != CONTRACT_VERSION:
        raise RuntimeError("Pre-performance manifest contract version mismatch.")
    if value.get("all_preperformance_gates_passed") is not True:
        raise RuntimeError("Phase 3 pre-performance gates have not all passed.")
    if value.get("scientific_reconstruction_performance_generated") is not False:
        raise RuntimeError("Pre-performance manifest has an invalid performance state.")
    if value.get("scientific_reconstruction_performance_inspected") is not False:
        raise RuntimeError("Pre-performance manifest has an invalid inspection state.")
    return value
