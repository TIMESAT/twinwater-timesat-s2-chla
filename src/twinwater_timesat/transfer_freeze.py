"""Erken-only second-freeze derivation and leakage-safe holdout utilities.

This module consumes committed Erken evidence and synthetic inputs only.  It
does not discover, read, or evaluate Vombsjön data.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from twinwater_timesat.phase3_contract import (
    PRIMARY_YEARS,
    SPLINE_GRID,
    canonical_json_payload_sha256,
    load_timesat_defaults_snapshot,
    sha256_file,
)


FREEZE_VERSION = "erken_vomb_transfer_freeze_v1.0"
CONFIG_PATH = Path("config/erken_vomb_transfer_freeze_v1.0.json")
PROTOCOL_PATH = Path("docs/Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md")
OUTPUT_DIRECTORY = Path("results/transfer_freeze/v1.0")
CORRECTION_DIRECTORY = Path("results/reliability_synthesis/v1.0.1")
SOURCE_REPORT = Path(
    "results/reliability_synthesis/v1.0/erken_reliability_report_v1.0.md"
)
SOURCE_RELIABILITY_MANIFEST = Path(
    "results/reliability_synthesis/v1.0/erken_reliability_synthesis_manifest_v1.0.json"
)
CORRECTED_REPORT_NAME = "erken_reliability_report_v1.0.1.md"
CORRIGENDUM_MANIFEST_NAME = "erken_reliability_corrigendum_manifest_v1.0.1.json"
FREEZE_MANIFEST_NAME = "erken_vomb_transfer_freeze_manifest_v1.0.json"


class TransferFreezeError(ValueError):
    """Raised when a frozen rule or saved Erken input is inconsistent."""


@dataclass(frozen=True)
class AffineScale:
    """Positive affine training-only transformation used before TIMESAT."""

    native_minimum: float
    native_maximum: float
    scaled_minimum: float
    scaled_maximum: float

    @property
    def multiplier(self) -> float:
        return (self.scaled_maximum - self.scaled_minimum) / (
            self.native_maximum - self.native_minimum
        )

    @property
    def offset(self) -> float:
        return self.scaled_minimum - self.multiplier * self.native_minimum

    def transform(self, values: Sequence[float] | np.ndarray) -> np.ndarray:
        array = np.asarray(values, dtype=np.float64)
        return self.multiplier * array + self.offset

    def inverse(self, values: Sequence[float] | np.ndarray) -> np.ndarray:
        array = np.asarray(values, dtype=np.float64)
        return (array - self.offset) / self.multiplier


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransferFreezeError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TransferFreezeError(f"Expected one JSON object in {path}.")
    return value


def load_transfer_config(repository_root: str | Path) -> dict[str, Any]:
    """Load and strictly validate the machine-readable transfer freeze."""

    root = Path(repository_root)
    config = _read_json(root / CONFIG_PATH)
    if config.get("schema_version") != "erken_vomb_transfer_freeze_config_v1":
        raise TransferFreezeError("Unexpected transfer-freeze schema version.")
    if config.get("freeze_version") != FREEZE_VERSION:
        raise TransferFreezeError("Unexpected transfer-freeze version.")
    if config.get("status") != "FROZEN_ERKEN_ONLY_BEFORE_VOMB_INPUT_AUDIT":
        raise TransferFreezeError("Transfer configuration is not frozen.")
    scope = config.get("scope", {})
    if scope.get("vombsjon_data_or_performance_used") is not False:
        raise TransferFreezeError("The freeze must not use Vombsjön data or performance.")
    if scope.get("vombsjon_performance_execution_authorized") is not False:
        raise TransferFreezeError("The freeze must not authorize Vomb performance execution.")
    if scope.get("second_freeze_complete") is not True:
        raise TransferFreezeError("The configuration does not mark the second freeze complete.")

    methods = config.get("reconstruction_methods", {})
    expected_methods = [
        "linear_interpolation",
        "timesat_double_logistic",
        "timesat_smoothing_spline",
    ]
    if methods.get("primary_order") != expected_methods:
        raise TransferFreezeError("Primary transfer methods changed from the contract.")
    spline = methods.get("timesat_smoothing_spline", {})
    if spline.get("candidate_grid") != list(SPLINE_GRID):
        raise TransferFreezeError("Spline candidate grid changed from the contract.")
    if spline.get("p_fitmethod") != 2 or spline.get("p_smooth") != 10:
        raise TransferFreezeError("Final spline must be p_fitmethod=2, p_smooth=10.")
    double_logistic = methods.get("timesat_double_logistic", {})
    if double_logistic.get("p_fitmethod") != 1 or double_logistic.get("p_seapar") != 1.0:
        raise TransferFreezeError("Primary double logistic is not the frozen default.")
    sensitivity = methods.get("timesat_double_logistic_cv_sensitivity", {})
    if sensitivity.get("analysis_role") != "secondary_sensitivity_not_primary_replacement":
        raise TransferFreezeError("CV double logistic is not labelled as a sensitivity.")
    if sensitivity.get("p_seapar") != 0.0:
        raise TransferFreezeError("Frozen CV double-logistic sensitivity must use p_seapar=0.")

    observation = config.get("observation_layer", {})
    if observation.get("primary_proxy") != "MCI":
        raise TransferFreezeError("The frozen primary proxy must be MCI.")
    primary_product = observation.get("primary_processing_product", {})
    if primary_product.get("method") != "ACOLITE" or primary_product.get("quantity") != "rhos":
        raise TransferFreezeError("The primary product must be ACOLITE rhos.")
    if primary_product.get("no_silent_product_fallback") is not True:
        raise TransferFreezeError("Silent processing-product fallback is forbidden.")

    qc = config.get("spatial_and_qc", {})
    if qc.get("window_pixel_count") != 9 or qc.get("minimum_valid_pixels") != 6:
        raise TransferFreezeError("The frozen 3x3 minimum-6 QC rule changed.")
    holdout = config.get("holdout_design", {})
    if holdout.get("consecutive", {}).get("block_sizes_observed_dates") != [2, 3, 4]:
        raise TransferFreezeError("Consecutive holdout block sizes must be [2, 3, 4].")
    if holdout.get("random_subsampling") is not False:
        raise TransferFreezeError("Holdout scenarios must be exhaustively enumerated.")
    if holdout.get("random_seed_for_year_cluster_bootstrap") != 20260918:
        raise TransferFreezeError("Unexpected year-cluster bootstrap seed.")

    scale = config.get("scale_handling", {})
    if scale.get("fit_data") != (
        "retained_training_observations_within_year_and_holdout_scenario_only"
    ):
        raise TransferFreezeError("Scale fitting is not training-only.")
    if scale.get("timesat_p_ylu") != [0.0, 10000.0]:
        raise TransferFreezeError("TIMESAT p_ylu changed from the frozen snapshot.")
    snapshot = load_timesat_defaults_snapshot(root / "config/timesat_double_logistic_defaults_v4.4.1.json")
    if snapshot["effective_runtime_parameters"]["p_ylu"] != scale["timesat_p_ylu"]:
        raise TransferFreezeError("Transfer p_ylu differs from the frozen TIMESAT snapshot.")
    return config


def derive_final_spline_scores(
    candidate_year_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    """Reduce saved outer-fold repetitions to one score per candidate-year."""

    required = {
        "outer_test_year",
        "smoothing",
        "inner_training_year",
        "nrmse",
        "candidate_year_status",
        "outer_test_reference_used",
        "tuning_metric",
        "seasonal_metric_used_for_tuning",
    }
    missing = required - set(candidate_year_rows.columns)
    if missing:
        raise TransferFreezeError(f"Spline score table is missing columns: {sorted(missing)}")
    rows = candidate_year_rows.copy()
    if set(rows["smoothing"].astype(int).unique()) != set(SPLINE_GRID):
        raise TransferFreezeError("Saved spline candidates do not match the frozen grid.")
    if set(rows["inner_training_year"].astype(int).unique()) != set(PRIMARY_YEARS):
        raise TransferFreezeError("Saved spline scores do not cover all seven Erken years.")
    if not rows["candidate_year_status"].eq("ok").all():
        raise TransferFreezeError("An all-Erken spline candidate-year is ineligible.")
    if rows["outer_test_reference_used"].astype(bool).any():
        raise TransferFreezeError("Outer-test reference leakage is recorded in spline scores.")
    if not rows["tuning_metric"].eq("withheld_day_nrmse").all():
        raise TransferFreezeError("Spline tuning metric changed from withheld-day nRMSE.")
    if rows["seasonal_metric_used_for_tuning"].astype(bool).any():
        raise TransferFreezeError("A seasonal metric entered spline tuning.")
    if (rows["outer_test_year"].astype(int) == rows["inner_training_year"].astype(int)).any():
        raise TransferFreezeError("An outer test year appears in its own training scores.")

    reduced_rows: list[dict[str, Any]] = []
    for (smoothing, year), group in rows.groupby(
        ["smoothing", "inner_training_year"], sort=True
    ):
        if len(group) != len(PRIMARY_YEARS) - 1:
            raise TransferFreezeError(
                f"Expected six saved repetitions for spline {smoothing}, year {year}."
            )
        values = group["nrmse"].to_numpy(dtype=np.float64)
        if not np.isfinite(values).all() or not np.all(values == values[0]):
            raise TransferFreezeError(
                f"Saved repetitions disagree for spline {smoothing}, year {year}."
            )
        reduced_rows.append(
            {
                "smoothing": int(smoothing),
                "year": int(year),
                "nrmse": float(values[0]),
                "saved_outer_fold_repetitions": int(len(group)),
                "repetitions_identical": True,
            }
        )
    reduced = pd.DataFrame(reduced_rows)
    summary = (
        reduced.groupby("smoothing", sort=True)
        .agg(
            n_years=("year", "nunique"),
            mean_equal_year_nrmse=("nrmse", "mean"),
            minimum_year_nrmse=("nrmse", "min"),
            maximum_year_nrmse=("nrmse", "max"),
            repetitions_per_candidate_year=("saved_outer_fold_repetitions", "first"),
        )
        .reset_index()
    )
    if not summary["n_years"].eq(len(PRIMARY_YEARS)).all():
        raise TransferFreezeError("A spline candidate does not contain seven year scores.")
    summary = summary.sort_values("smoothing", kind="mergesort").reset_index(drop=True)
    best_score = float(summary["mean_equal_year_nrmse"].min())
    eligible_best = summary.loc[summary["mean_equal_year_nrmse"].eq(best_score)]
    selected = int(eligible_best["smoothing"].min())
    summary["delta_from_best"] = summary["mean_equal_year_nrmse"] - best_score
    summary["rank"] = summary["mean_equal_year_nrmse"].rank(
        method="min", ascending=True
    ).astype(int)
    summary["selected_for_transfer"] = summary["smoothing"].eq(selected)
    summary["selection_rule"] = (
        "minimum_seven_year_equal_weight_mean_nrmse_then_smaller_exact_tie"
    )
    return summary, selected


def fit_training_affine_scale(
    training_values: Sequence[float] | np.ndarray,
    *,
    scaled_minimum: float = 1000.0,
    scaled_maximum: float = 9000.0,
) -> AffineScale:
    """Fit the frozen positive affine scale from training observations only."""

    values = np.asarray(training_values, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
        raise TransferFreezeError("Training scale requires a finite one-dimensional vector.")
    native_minimum = float(values.min())
    native_maximum = float(values.max())
    if not native_maximum > native_minimum:
        raise TransferFreezeError("Training scale range must be positive.")
    if not (0.0 < scaled_minimum < scaled_maximum < 10000.0):
        raise TransferFreezeError("Scaled training bounds must lie inside (0, 10000).")
    return AffineScale(
        native_minimum=native_minimum,
        native_maximum=native_maximum,
        scaled_minimum=float(scaled_minimum),
        scaled_maximum=float(scaled_maximum),
    )


def collapse_same_day_observations(observations: pd.DataFrame) -> pd.DataFrame:
    """Apply the frozen calendar-date median and retain provenance counts."""

    required = {"date", "value", "eligible"}
    missing = required - set(observations.columns)
    if missing:
        raise TransferFreezeError(f"Observation table is missing columns: {sorted(missing)}")
    table = observations.loc[observations["eligible"].astype(bool), ["date", "value"]].copy()
    table["date"] = pd.to_datetime(table["date"], errors="coerce").dt.normalize()
    table["value"] = pd.to_numeric(table["value"], errors="coerce")
    table = table.loc[table["date"].notna() & np.isfinite(table["value"])].copy()
    table["year"] = table["date"].dt.year.astype(int)
    table["day_of_year"] = table["date"].dt.dayofyear.astype(int)
    table = table.loc[table["day_of_year"].ne(366)].copy()
    if table.empty:
        return pd.DataFrame(
            columns=["date", "year", "day_of_year", "value", "n_source_observations"]
        )
    collapsed = (
        table.groupby("date", sort=True)
        .agg(
            year=("year", "first"),
            day_of_year=("day_of_year", "first"),
            value=("value", "median"),
            n_source_observations=("value", "size"),
        )
        .reset_index()
    )
    return collapsed


def _date_list_json(values: Iterable[pd.Timestamp]) -> str:
    return json.dumps(
        [pd.Timestamp(value).strftime("%Y-%m-%d") for value in values],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def enumerate_holdout_scenarios(
    observations: pd.DataFrame,
    *,
    minimum_full_year_dates: int = 8,
    minimum_training_dates: int = 6,
    block_sizes: Sequence[int] = (2, 3, 4),
) -> pd.DataFrame:
    """Exhaustively enumerate frozen isolated and internal block holdouts."""

    collapsed = collapse_same_day_observations(observations)
    rows: list[dict[str, Any]] = []
    for year, year_table in collapsed.groupby("year", sort=True):
        year_table = year_table.sort_values("date", kind="mergesort").reset_index(drop=True)
        dates = pd.DatetimeIndex(year_table["date"])
        n_dates = len(dates)
        if n_dates < minimum_full_year_dates:
            continue
        designs = [("isolated", 1), *[("consecutive", int(size)) for size in block_sizes]]
        for kind, size in designs:
            if size < 1:
                raise TransferFreezeError("Holdout block sizes must be positive.")
            ordinal = 0
            for start in range(1, n_dates - size):
                stop = start + size
                heldout = dates[start:stop]
                if len(heldout) != size or n_dates - size < minimum_training_dates:
                    continue
                ordinal += 1
                training = dates.delete(np.arange(start, stop))
                scenario_id = (
                    f"{int(year)}_{kind}_{size:02d}_{ordinal:03d}_"
                    f"{heldout[0].strftime('%Y%m%d')}_{heldout[-1].strftime('%Y%m%d')}"
                )
                rows.append(
                    {
                        "scenario_id": scenario_id,
                        "year": int(year),
                        "scenario_kind": kind,
                        "block_size_observed_dates": int(size),
                        "heldout_start": heldout[0].strftime("%Y-%m-%d"),
                        "heldout_end": heldout[-1].strftime("%Y-%m-%d"),
                        "heldout_dates_json": _date_list_json(heldout),
                        "training_dates_json": _date_list_json(training),
                        "n_full_year_dates": int(n_dates),
                        "n_training_dates": int(len(training)),
                        "n_heldout_dates": int(len(heldout)),
                        "support_start": training[0].strftime("%Y-%m-%d"),
                        "support_end": training[-1].strftime("%Y-%m-%d"),
                        "first_date_protected": bool(dates[0] in training),
                        "last_date_protected": bool(dates[-1] in training),
                        "randomly_subsampled": False,
                    }
                )
    return pd.DataFrame(rows)


def common_evaluation_dates(
    heldout_dates: Sequence[pd.Timestamp | str],
    predictions: Mapping[str, pd.DataFrame],
    *,
    methods: Sequence[str] = (
        "linear_interpolation",
        "timesat_double_logistic",
        "timesat_smoothing_spline",
    ),
) -> pd.DatetimeIndex:
    """Return held-out dates with finite predictions from every primary method."""

    common = set(pd.DatetimeIndex(pd.to_datetime(heldout_dates)).normalize())
    for method in methods:
        if method not in predictions:
            raise TransferFreezeError(f"Missing primary prediction table: {method}")
        table = predictions[method].copy()
        if not {"date", "prediction"}.issubset(table.columns):
            raise TransferFreezeError(f"Prediction table {method} lacks date/prediction.")
        table["date"] = pd.to_datetime(table["date"], errors="coerce").dt.normalize()
        table["prediction"] = pd.to_numeric(table["prediction"], errors="coerce")
        valid = set(table.loc[table["date"].notna() & np.isfinite(table["prediction"]), "date"])
        common &= valid
    return pd.DatetimeIndex(sorted(common))


def synthetic_holdout_audit() -> pd.DataFrame:
    """Exercise holdout, common-date, scale, and no-leakage behavior."""

    dates = pd.date_range("2020-03-01", periods=10, freq="12D")
    values = np.array([-0.018, -0.013, -0.005, 0.006, 0.019, 0.012, 0.004, 0.011, 0.002, -0.004])
    observations = pd.DataFrame({"date": dates, "value": values, "eligible": True})
    duplicate = pd.DataFrame(
        {"date": [dates[4]], "value": [0.021], "eligible": [True]}
    )
    observations = pd.concat([observations, duplicate], ignore_index=True)
    scenarios = enumerate_holdout_scenarios(observations)
    isolated = scenarios.loc[scenarios["scenario_kind"].eq("isolated")]
    blocks = scenarios.loc[scenarios["scenario_kind"].eq("consecutive")]
    expected_counts = {2: 7, 3: 6, 4: 5}

    one = isolated.iloc[3]
    heldout = set(json.loads(one["heldout_dates_json"]))
    training_dates = set(json.loads(one["training_dates_json"]))
    collapsed = collapse_same_day_observations(observations)
    training_values = collapsed.loc[
        collapsed["date"].dt.strftime("%Y-%m-%d").isin(training_dates), "value"
    ].to_numpy(dtype=np.float64)
    scale_before = fit_training_affine_scale(training_values)
    mutated = observations.copy()
    heldout_mask = mutated["date"].dt.strftime("%Y-%m-%d").isin(heldout)
    mutated.loc[heldout_mask, "value"] = mutated.loc[heldout_mask, "value"] + 1000.0
    mutated_collapsed = collapse_same_day_observations(mutated)
    mutated_training = mutated_collapsed.loc[
        mutated_collapsed["date"].dt.strftime("%Y-%m-%d").isin(training_dates), "value"
    ].to_numpy(dtype=np.float64)
    scale_after = fit_training_affine_scale(mutated_training)
    scaled_training = scale_before.transform(training_values)

    fake_predictions: dict[str, pd.DataFrame] = {}
    heldout_dates = pd.DatetimeIndex(pd.to_datetime(json.loads(blocks.iloc[0]["heldout_dates_json"])))
    for method in (
        "linear_interpolation",
        "timesat_double_logistic",
        "timesat_smoothing_spline",
    ):
        prediction = np.arange(len(heldout_dates), dtype=float)
        if method == "timesat_double_logistic":
            prediction[-1] = np.nan
        fake_predictions[method] = pd.DataFrame(
            {"date": heldout_dates, "prediction": prediction}
        )
    common = common_evaluation_dates(heldout_dates, fake_predictions)

    checks = [
        (
            "same_day_median",
            np.isclose(
                collapsed.loc[collapsed["date"].eq(dates[4]), "value"].iloc[0],
                np.median([values[4], 0.021]),
            ),
            "duplicate eligible observations collapse to the calendar-date median",
        ),
        (
            "isolated_exhaustive_internal_count",
            len(isolated) == 8,
            f"observed={len(isolated)} expected=8",
        ),
        (
            "consecutive_exhaustive_internal_counts",
            blocks.groupby("block_size_observed_dates").size().to_dict() == expected_counts,
            f"observed={blocks.groupby('block_size_observed_dates').size().to_dict()} expected={expected_counts}",
        ),
        (
            "endpoints_protected",
            bool(
                scenarios["first_date_protected"].all()
                and scenarios["last_date_protected"].all()
            ),
            "first and last dates remain in every training set",
        ),
        (
            "training_holdout_disjoint",
            heldout.isdisjoint(training_dates),
            "selected scenario training and held-out date sets are disjoint",
        ),
        (
            "heldout_value_mutation_no_scale_leakage",
            scale_before == scale_after,
            "mutating held-out values does not change the fitted affine scale",
        ),
        (
            "scaled_training_inside_timesat_range",
            bool(
                np.isclose(scaled_training.min(), 1000.0)
                and np.isclose(scaled_training.max(), 9000.0)
                and (scaled_training > 0.0).all()
                and (scaled_training < 10000.0).all()
            ),
            f"scaled_min={scaled_training.min():.6f} scaled_max={scaled_training.max():.6f}",
        ),
        (
            "affine_roundtrip",
            bool(np.allclose(scale_before.inverse(scaled_training), training_values, rtol=0, atol=1e-12)),
            "inverse transform restores native training values",
        ),
        (
            "common_evaluation_date_intersection",
            len(common) == len(heldout_dates) - 1 and heldout_dates[-1] not in common,
            f"common={len(common)} heldout={len(heldout_dates)}",
        ),
        (
            "no_random_scenario_subsampling",
            not scenarios["randomly_subsampled"].any(),
            "all eligible internal scenarios are retained",
        ),
    ]
    return pd.DataFrame(
        [
            {
                "check_id": check_id,
                "status": "pass" if bool(passed) else "fail",
                "passed": bool(passed),
                "detail": detail,
            }
            for check_id, passed, detail in checks
        ]
    )


def method_parameter_basis_table(config: Mapping[str, Any]) -> pd.DataFrame:
    """Create the requested method-parameter-basis-role table."""

    methods = config["reconstruction_methods"]
    rows = [
        {
            "method": "linear_interpolation",
            "primary_or_sensitivity": "primary",
            "parameter_and_effective_configuration": "piecewise linear; no extrapolation; scenario-specific common support; training-only affine scale then inverse transform",
            "erken_basis": "untuned benchmark; lowest equal-year mean point error but not uniformly best by year or scientific metric",
            "analysis_role": methods["linear_interpolation"]["analysis_role"],
            "software_identity": "twinwater_timesat implementation in frozen manifest",
        },
        {
            "method": "timesat_double_logistic",
            "primary_or_sensitivity": "primary",
            "parameter_and_effective_configuration": "p_fitmethod=1; p_seapar=1; all remaining parameters from timesat_double_logistic_defaults_v4.4.1.json",
            "erken_basis": "pre-performance default retained by contract; metric-specific integral advantage did not justify replacing other primary methods",
            "analysis_role": methods["timesat_double_logistic"]["analysis_role"],
            "software_identity": "TIMESAT 4.4.1 b208441; TIMESAT CLI 1.9.2 258b505",
        },
        {
            "method": "timesat_smoothing_spline",
            "primary_or_sensitivity": "primary",
            "parameter_and_effective_configuration": "p_fitmethod=2; p_smooth=10; remaining effective settings from the frozen TIMESAT snapshot",
            "erken_basis": "minimum seven-year equal-weight withheld-day nRMSE (0.212145438); original grid/failure/tie rules; not the outer-fold mode",
            "analysis_role": methods["timesat_smoothing_spline"]["analysis_role"],
            "software_identity": "TIMESAT 4.4.1 b208441; TIMESAT CLI 1.9.2 258b505",
        },
        {
            "method": "timesat_double_logistic_cv_sensitivity",
            "primary_or_sensitivity": "secondary_sensitivity",
            "parameter_and_effective_configuration": "p_fitmethod=1; p_seapar=0; remaining effective settings from the frozen default snapshot",
            "erken_basis": "all seven pre-frozen Erken outer-fold selections chose p_seapar=0",
            "analysis_role": methods["timesat_double_logistic_cv_sensitivity"]["analysis_role"],
            "software_identity": "TIMESAT 4.4.1 b208441; TIMESAT CLI 1.9.2 258b505",
        },
    ]
    return pd.DataFrame(rows)


def corrected_reliability_report(source: str) -> tuple[str, list[dict[str, str]]]:
    """Apply only the accepted interpretive corrections to frozen v1.0 text."""

    replacements = [
        (
            "# Erken reliability synthesis v1.0\n",
            "# Erken reliability synthesis v1.0.1 — interpretive correction\n\n"
            "**Correction status:** v1.0 numerical tables, figures, manifest and all frozen analysis outputs are unchanged. This version corrects interpretation only: leave-one-year-out ties are separated from reversals, the spline is described as producing a smoother curve rather than independently verified denoising, and `A_gap` is identified as an Erken-only retrospective explanatory variable. Statements that the synthesis itself did not execute the second freeze are retained as the scope of that saved-result analysis; the completed freeze is governed separately by `docs/Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md`.\n",
        ),
        (
            "5. 随机删除与连续缺口都没有产生重建失败，但可靠性随缺测增强而总体下降，并受年份、方法、A_gap、峰值是否落在缺口内和实际移除观测数共同影响；不存在由这 7 个年份支持的通用缺口阈值。",
            "5. 随机删除与连续缺口都没有产生重建失败，但可靠性随缺测增强而总体下降，并受年份、方法、A_gap、峰值是否落在缺口内和实际移除观测数共同影响；不存在由这 7 个年份支持的通用缺口阈值。A_gap 由 Erken 完整参考序列事后计算，只是解释与分层变量，不能作为 Vomb 隐藏缺口内已知的运行输入。",
        ),
        (
            "6. 逐次剔除一年表明，一些平均优势方向稳定，另一些会随被剔除年份改变；因此报告同时给出平均优势、逐年胜负与 leave-one-year-out 范围，不能把平均较低误差写成每年均优。",
            "6. 逐次剔除一年后，线性插值相对默认双逻辑或平滑样条的峰值日期优势在部分情况下变为持平，但没有反转；平滑样条与默认双逻辑之间则同时出现正负差异，说明两者的峰值日期优势会随被剔除年份改变。报告因此同时给出平均优势、逐年胜负与 leave-one-year-out 范围，不能把平均较低误差写成每年均优。",
        ),
        (
            "It reduced noise with more flexibility than the default double logistic, but still attenuated or reordered peaks",
            "It produced smoother reconstructed curves with more flexibility than the default double logistic, but still attenuated or reordered peaks",
        ),
        (
            "- Linear interpolation vs TIMESAT double logistic (default), `peak_timing_success_10d`: full advantage for method A 0.143; leave-one-year-out range 0.000 to 0.167; direction changed.",
            "- Linear interpolation vs TIMESAT double logistic (default), `peak_timing_success_10d`: full advantage for method A 0.143; leave-one-year-out range 0.000 to 0.167; some leave-one-year-out summaries tied, and none reversed the linear-interpolation advantage.",
        ),
        (
            "- Linear interpolation vs TIMESAT smoothing spline, `peak_timing_success_10d`: full advantage for method A 0.143; leave-one-year-out range 0.000 to 0.167; direction changed.",
            "- Linear interpolation vs TIMESAT smoothing spline, `peak_timing_success_10d`: full advantage for method A 0.143; leave-one-year-out range 0.000 to 0.167; some leave-one-year-out summaries tied, and none reversed the linear-interpolation advantage.",
        ),
        (
            "- TIMESAT smoothing spline vs TIMESAT double logistic (default), `peak_timing_success_10d`: full advantage for method A 0.000; leave-one-year-out range -0.167 to 0.167; direction changed.",
            "- TIMESAT smoothing spline vs TIMESAT double logistic (default), `peak_timing_success_10d`: full advantage for method A 0.000; leave-one-year-out range -0.167 to 0.167; the contrast took both signs, so the two methods alternated in advantage across leave-one-year-out summaries.",
        ),
        (
            "A_gap remains continuous in the primary association table. Low/medium/high labels are used only for visualization",
            "A_gap remains continuous in the primary association table. It is calculated retrospectively from the complete Erken reference trajectory and is not a known operational input inside a hidden Vomb gap. Low/medium/high labels are used only for visualization",
        ),
        (
            "and on duration, relative position, global-peak containment, removed-observation count, and hidden reference activity for consecutive gaps.",
            "and on duration, relative position, global-peak containment, removed-observation count, and hidden reference activity for consecutive gaps. The last quantity is available retrospectively in Erken and cannot be assumed known inside an operational Vomb gap.",
        ),
        (
            "The synthesis script reads only the eight allowlisted saved Erken result files recorded in `config/erken_reliability_synthesis_v1.0.json`.",
            "The v1.0 synthesis script reads only the eight allowlisted saved Erken result files recorded in `config/erken_reliability_synthesis_v1.0.json`. Reproduce the v1.0.1 interpretive correction and its checksum manifest with `python scripts/35_prepare_erken_transfer_freeze.py` after the synthetic TIMESAT runtime validation has been materialized.",
        ),
    ]
    corrected = source
    applied: list[dict[str, str]] = []
    for old, new in replacements:
        count = corrected.count(old)
        if count != 1:
            raise TransferFreezeError(
                f"Expected exactly one report correction target, found {count}: {old[:80]!r}"
            )
        corrected = corrected.replace(old, new, 1)
        applied.append({"old": old, "new": new})
    return corrected, applied


def _write_csv(table: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False, lineterminator="\n", float_format="%.15g")


def _git_identity(root: Path) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {"commit_at_materialization_start": commit, "worktree_dirty_at_materialization_start": bool(status.strip())}


def _hash_paths(root: Path, paths: Iterable[Path]) -> dict[str, str]:
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def write_transfer_freeze_products(repository_root: str | Path) -> list[Path]:
    """Write the correction, freeze tables, synthetic audit, and manifests."""

    root = Path(repository_root)
    config = load_transfer_config(root)
    repository = _git_identity(root)
    input_path = root / config["erken_selection_inputs"]["spline_candidate_year_scores"]
    candidate_rows = pd.read_csv(input_path)
    spline_summary, selected = derive_final_spline_scores(candidate_rows)
    if selected != config["reconstruction_methods"]["timesat_smoothing_spline"]["p_smooth"]:
        raise TransferFreezeError(
            f"Derived final spline {selected} differs from frozen configuration."
        )
    methods = method_parameter_basis_table(config)
    synthetic = synthetic_holdout_audit()
    if not synthetic["passed"].all():
        failed = synthetic.loc[~synthetic["passed"], "check_id"].tolist()
        raise TransferFreezeError(f"Synthetic holdout validation failed: {failed}")

    output = root / OUTPUT_DIRECTORY
    output.mkdir(parents=True, exist_ok=True)
    candidate_output = output / config["outputs"]["spline_candidate_summary"]
    method_output = output / config["outputs"]["method_parameter_basis"]
    synthetic_output = output / config["outputs"]["synthetic_holdout_validation"]
    _write_csv(spline_summary, candidate_output)
    _write_csv(methods, method_output)
    _write_csv(synthetic, synthetic_output)

    correction = root / CORRECTION_DIRECTORY
    correction.mkdir(parents=True, exist_ok=True)
    source_text = (root / SOURCE_REPORT).read_text(encoding="utf-8")
    corrected, replacements = corrected_reliability_report(source_text)
    corrected_path = correction / CORRECTED_REPORT_NAME
    corrected_path.write_text(corrected, encoding="utf-8", newline="\n")
    corrigendum = {
        "schema_version": "erken_reliability_corrigendum_manifest_v1",
        "correction_version": "Erken_Reliability_Synthesis_v1.0.1",
        "correction_date": config["freeze_date"],
        "classification": "necessary_interpretive_correction_no_numeric_change",
        "source_report": {
            "relative_path": SOURCE_REPORT.as_posix(),
            "sha256": sha256_file(root / SOURCE_REPORT),
        },
        "source_reliability_manifest": {
            "relative_path": SOURCE_RELIABILITY_MANIFEST.as_posix(),
            "sha256": sha256_file(root / SOURCE_RELIABILITY_MANIFEST),
        },
        "corrected_report": {
            "relative_path": corrected_path.relative_to(root).as_posix(),
            "sha256": sha256_file(corrected_path),
        },
        "replacements": replacements,
        "numeric_tables_recomputed": False,
        "reconstruction_rerun": False,
        "satellite_extraction_rerun": False,
        "vombsjon_data_or_performance_inspected": False,
    }
    corrigendum["manifest_payload_sha256"] = canonical_json_payload_sha256(
        corrigendum, excluded_keys=("manifest_payload_sha256",)
    )
    corrigendum_path = correction / CORRIGENDUM_MANIFEST_NAME
    corrigendum_path.write_text(
        json.dumps(corrigendum, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    governed_inputs = [
        CONFIG_PATH,
        PROTOCOL_PATH,
        Path("docs/Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md"),
        Path("docs/Reconstruction_Analysis_Contract_v1.0.1.md"),
        Path("config/timesat_double_logistic_defaults_v4.4.1.json"),
        Path(config["erken_selection_inputs"]["spline_candidate_year_scores"]),
        Path(config["erken_selection_inputs"]["spline_outer_fold_summary"]),
        Path(config["erken_selection_inputs"]["actual_mask_metrics"]),
        Path(config["erken_selection_inputs"]["reliability_manifest"]),
        Path(config["erken_selection_inputs"]["phase6c_manifest"]),
        Path(config["erken_selection_inputs"]["processing_baseline_gate"]),
        SOURCE_REPORT,
    ]
    implementation_paths = [
        Path("src/twinwater_timesat/transfer_freeze.py"),
        Path("scripts/35_prepare_erken_transfer_freeze.py"),
        Path("scripts/36_validate_erken_transfer_freeze.py"),
        Path("scripts/37_validate_transfer_timesat_runtime.py"),
        Path("scripts/38_prepare_locked_transfer_scenarios.py"),
        Path("tests/test_transfer_freeze.py"),
    ]
    runtime_validation_path = output / config["outputs"]["timesat_runtime_validation"]
    if not runtime_validation_path.is_file():
        raise TransferFreezeError(
            "TIMESAT runtime validation is missing; run "
            "scripts/37_validate_transfer_timesat_runtime.py in the frozen runtime first."
        )
    runtime_validation = _read_json(runtime_validation_path)
    if runtime_validation.get("all_passed") is not True:
        raise TransferFreezeError("TIMESAT runtime affine-equivariance validation did not pass.")
    if runtime_validation.get("vombsjon_data_or_performance_accessed") is not False:
        raise TransferFreezeError("Runtime validation records forbidden Vomb access.")
    output_paths = [
        candidate_output,
        method_output,
        synthetic_output,
        runtime_validation_path,
        corrected_path,
        corrigendum_path,
    ]
    manifest = {
        "schema_version": "erken_vomb_transfer_freeze_manifest_v1",
        "freeze_version": FREEZE_VERSION,
        "freeze_date": config["freeze_date"],
        "status": "FROZEN_COMPLETE_ERKEN_ONLY_VOMB_PERFORMANCE_NOT_RUN",
        "starting_commit": config["starting_commit"],
        "repository": repository,
        "input_sha256": _hash_paths(root, governed_inputs),
        "implementation_sha256": _hash_paths(root, implementation_paths),
        "output_sha256": {
            path.relative_to(root).as_posix(): sha256_file(path) for path in output_paths
        },
        "final_spline": {
            "p_smooth": int(selected),
            "selection_metric": "seven_year_equal_weight_mean_withheld_day_nrmse",
            "selected_score": float(
                spline_summary.loc[
                    spline_summary["selected_for_transfer"], "mean_equal_year_nrmse"
                ].iloc[0]
            ),
            "outer_fold_mode_used": False,
            "vombsjon_performance_used": False,
        },
        "primary_methods": config["reconstruction_methods"]["primary_order"],
        "primary_proxy": "ACOLITE_rhos_MCI",
        "cv_double_logistic_role": "secondary_sensitivity_not_primary_replacement",
        "synthetic_validation": {
            "n_checks": int(len(synthetic)),
            "n_passed": int(synthetic["passed"].sum()),
            "all_passed": bool(synthetic["passed"].all()),
            "timesat_runtime_affine_equivariance": "pass",
        },
        "scientific_guards": {
            "erken_only_selection": True,
            "original_reconstruction_rerun": False,
            "original_reliability_numeric_results_changed": False,
            "vombsjon_input_read": False,
            "vombsjon_performance_run": False,
            "second_freeze_complete": True,
            "next_stage_limited_to_vombsjon_input_and_raw_matchup_audit": True,
        },
        "external_execution_gates": config["execution_gates"],
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(
        manifest, excluded_keys=("manifest_payload_sha256",)
    )
    manifest_path = output / FREEZE_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return [*output_paths, manifest_path]
