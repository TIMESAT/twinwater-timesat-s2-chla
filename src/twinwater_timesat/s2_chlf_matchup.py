"""Frozen Erken Phase 6C exact-date Sentinel-2 index versus CHLF analysis."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib
import numpy as np
import scipy
import yaml
from scipy.stats import pearsonr, spearmanr


matplotlib.use("Agg")

DEFAULT_CONFIG_RELATIVE_PATH = "config/erken_s2_chlf_matchup_analysis_v1.0.yaml"
EXPECTED_SCHEMA_VERSION = "erken_s2_chlf_matchup_analysis_config_v1"
EXPECTED_ANALYSIS_VERSION = "erken_s2_chlf_matchup_analysis_v1.0"
EXPECTED_METHODS = ("L1C", "L2A", "ACOLITE")
EXPECTED_METRICS = ("NDCI", "MCI")


class ChlfMatchupError(RuntimeError):
    """Raised when the frozen Phase 6C analysis cannot be reproduced."""


@dataclass(frozen=True)
class ChlfMatchupConfig:
    values: Mapping[str, Any]
    source_relative_path: str
    sha256: str

    @property
    def analysis_version(self) -> str:
        return str(self.values["analysis_version"])


@dataclass(frozen=True)
class ChlfMatchupResult:
    matchup_audit: tuple[dict[str, Any], ...]
    analysis_pairs: tuple[dict[str, Any], ...]
    association_summary: tuple[dict[str, Any], ...]
    annual_association: tuple[dict[str, Any], ...]
    loyo_predictions: tuple[dict[str, Any], ...]
    loyo_summary: tuple[dict[str, Any], ...]
    input_paths: Mapping[str, Path]
    counts: Mapping[str, Any]


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_config_path(repository_root: str | Path) -> Path:
    return Path(repository_root) / DEFAULT_CONFIG_RELATIVE_PATH


def load_chlf_matchup_config(
    path: str | Path, *, repository_root: str | Path | None = None
) -> ChlfMatchupConfig:
    source = Path(path)
    if not source.is_file():
        raise ChlfMatchupError(f"Phase 6C configuration not found: {source}")
    with source.open(encoding="utf-8") as handle:
        values = yaml.safe_load(handle)
    if not isinstance(values, Mapping):
        raise ChlfMatchupError("Phase 6C configuration must be a YAML mapping.")
    required = {
        "inputs", "matchup", "supports", "association",
        "predictive_validation", "interpretation", "outputs",
    }
    missing = sorted(required - set(values))
    if missing:
        raise ChlfMatchupError(f"Phase 6C configuration is missing: {missing}")
    if values.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise ChlfMatchupError("Unexpected Phase 6C schema version.")
    if values.get("analysis_version") != EXPECTED_ANALYSIS_VERSION:
        raise ChlfMatchupError("Unexpected Phase 6C analysis version.")
    if values.get("status") != "FROZEN_BEFORE_INDEX_CHLF_ANALYSIS":
        raise ChlfMatchupError("Phase 6C configuration must be frozen before analysis.")

    matchup = values["matchup"]
    if matchup.get("key") != "date" or matchup.get("temporal_rule") != "exact_same_calendar_date":
        raise ChlfMatchupError("Matchups must use exact calendar date.")
    if int(matchup.get("temporal_tolerance_days", -1)) != 0:
        raise ChlfMatchupError("Temporal matchup tolerance must remain zero days.")
    if matchup.get("nearest_date_matching_allowed") is not False:
        raise ChlfMatchupError("Nearest-date matching must remain forbidden.")
    if matchup.get("interpolation_allowed") is not False:
        raise ChlfMatchupError("Temporal interpolation must remain forbidden.")
    if tuple(matchup.get("methods", ())) != EXPECTED_METHODS:
        raise ChlfMatchupError(f"Methods must remain exactly {EXPECTED_METHODS}.")
    if tuple(matchup.get("metrics", {}).keys()) != EXPECTED_METRICS:
        raise ChlfMatchupError(f"Metrics must remain exactly {EXPECTED_METRICS}.")
    if values["supports"]["primary"].get("id") != "exact_three_method_metric_common_support":
        raise ChlfMatchupError("Primary support must remain exact three-method common support.")
    association = values["association"]
    if association.get("primary_metric") != "spearman_rho_raw_CHLF_vs_index":
        raise ChlfMatchupError("Primary association must remain Spearman rho.")
    if association.get("secondary_metric") != "pearson_r_log10_CHLF_vs_index":
        raise ChlfMatchupError("Secondary association must remain Pearson r on log10 CHLF.")
    bootstrap = association["year_cluster_bootstrap"]
    if int(bootstrap.get("replicates", 0)) != 10000 or int(bootstrap.get("seed", 0)) != 20260917:
        raise ChlfMatchupError("Frozen year-cluster bootstrap settings changed.")
    predictive = values["predictive_validation"]
    if predictive.get("design") != "leave_one_calendar_year_out":
        raise ChlfMatchupError("Predictive validation must remain calendar-year LOYO.")
    if predictive.get("model") != "ordinary_least_squares_intercept_plus_one_index":
        raise ChlfMatchupError("Predictive model must remain one-index OLS.")
    interpretation = values["interpretation"]
    forbidden_true = [key for key, value in interpretation.items() if value is True]
    if forbidden_true:
        raise ChlfMatchupError(f"Forbidden Phase 6C authorization(s): {forbidden_true}")

    relative = source.name
    if repository_root is not None:
        try:
            relative = source.resolve().relative_to(Path(repository_root).resolve()).as_posix()
        except ValueError:
            pass
    return ChlfMatchupConfig(values, relative, sha256_file(source))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ChlfMatchupError(f"Required input not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _bool(value: Any) -> bool | None:
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _unique(rows: Sequence[Mapping[str, Any]], keys: Sequence[str], label: str) -> None:
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = tuple(str(row.get(column, "")) for column in keys)
        if key in seen:
            raise ChlfMatchupError(f"Duplicate {label} key: {key}")
        seen.add(key)


def build_matchup_audit(
    selection_rows: Sequence[Mapping[str, str]],
    reference_rows: Sequence[Mapping[str, str]],
    config: ChlfMatchupConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exact-date join with complete audit retention and metric-specific support."""

    _unique(selection_rows, ("date", "observation_method"), "selection")
    _unique(reference_rows, ("date",), "reference")
    reference = {row["date"]: row for row in reference_rows}
    methods = tuple(config.values["matchup"]["methods"])
    metrics = config.values["matchup"]["metrics"]
    joined: list[dict[str, Any]] = []

    for source in sorted(selection_rows, key=lambda row: (row["date"], methods.index(row["observation_method"]))):
        date = source["date"]
        ref = reference.get(date)
        chlf = _float(ref.get("CHLF")) if ref else None
        open_water = _bool(ref.get("open_water")) if ref else None
        output: dict[str, Any] = dict(source)
        output["selection_chlf_used"] = _bool(output.pop("chlf_used", None))
        output.update(
            {
                "analysis_version": config.analysis_version,
                "reference_date_match": ref is not None,
                "CHLF": chlf,
                "PRESENCE_ICE": int(float(ref["PRESENCE_ICE"])) if ref and ref.get("PRESENCE_ICE", "") != "" else None,
                "open_water": open_water,
                "measurement_regime": ref.get("measurement_regime", "") if ref else "",
                "reference_analysis_eligible": bool(ref is not None and chlf is not None and open_water is True),
            }
        )
        for metric, specification in metrics.items():
            eligible = _bool(source.get(specification["eligibility_column"]))
            if ref is None:
                status = "unavailable_no_exact_date_reference"
            elif chlf is None:
                status = "unavailable_nonfinite_CHLF"
            elif open_water is not True:
                status = "ineligible_not_open_water"
            elif eligible is True:
                status = "eligible_method_specific_support"
            elif eligible is False:
                status = "ineligible_frozen_observation_rule"
            else:
                status = "unavailable_frozen_observation_selection"
            output[f"{metric.lower()}_method_specific_support"] = status == "eligible_method_specific_support"
            output[f"{metric.lower()}_matchup_status"] = status
            output[f"{metric.lower()}_primary_common_support"] = False
        joined.append(output)

    by_date: dict[str, dict[str, dict[str, Any]]] = {}
    for row in joined:
        by_date.setdefault(row["date"], {})[row["observation_method"]] = row
    for date, method_rows in by_date.items():
        if set(method_rows) != set(methods):
            raise ChlfMatchupError(f"Date {date} does not contain all frozen methods.")
        exact_alignment = all(_bool(row.get("exact_three_method_source_alignment")) is True for row in method_rows.values())
        for metric in metrics:
            key = f"{metric.lower()}_method_specific_support"
            common = exact_alignment and all(row[key] is True for row in method_rows.values())
            for row in method_rows.values():
                row[f"{metric.lower()}_primary_common_support"] = common

    pairs: list[dict[str, Any]] = []
    for row in joined:
        for metric, specification in metrics.items():
            if row[f"{metric.lower()}_method_specific_support"] is not True:
                continue
            chlf = float(row["CHLF"])
            index_value = _float(row.get(specification["value_column"]))
            if index_value is None:
                raise ChlfMatchupError(
                    f"Eligible {metric} row lacks a finite value: {row['date']} {row['observation_method']}"
                )
            pairs.append(
                {
                    "analysis_version": config.analysis_version,
                    "date": row["date"],
                    "year": int(row["year"]),
                    "measurement_regime": row["measurement_regime"],
                    "observation_method": row["observation_method"],
                    "metric": metric,
                    "index_value": index_value,
                    "CHLF": chlf,
                    "log10_CHLF": math.log10(chlf) if chlf > 0 else None,
                    "method_specific_support": True,
                    "primary_common_support": row[f"{metric.lower()}_primary_common_support"],
                    "source_product_id": row.get("source_product_id", ""),
                    "valid_pixel_count": int(float(row[specification["value_column"].replace("_median", "_valid_pixel_count")])),
                }
            )
    return joined, pairs


def _correlation(x: np.ndarray, y: np.ndarray, kind: str, minimum_n: int) -> tuple[float | None, str, str]:
    finite = np.isfinite(x) & np.isfinite(y)
    x = x[finite]
    y = y[finite]
    if len(x) < minimum_n:
        return None, "unavailable", "insufficient_pairs"
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return None, "unavailable", "constant_variable"
    value = spearmanr(x, y).statistic if kind == "spearman" else pearsonr(x, y).statistic
    return float(value), "ok", ""


def _derived_seed(master_seed: int, key: str) -> int:
    token = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16)
    return (master_seed + token) % (2**63 - 1)


def _cluster_bootstrap_ci(
    rows: Sequence[Mapping[str, Any]], *, x_column: str, y_column: str,
    kind: str, replicates: int, master_seed: int, key: str,
    confidence_level: float, minimum_n: int,
) -> tuple[float | None, float | None, int]:
    by_year: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        if _float(row.get(x_column)) is not None and _float(row.get(y_column)) is not None:
            by_year.setdefault(int(row["year"]), []).append(row)
    years = sorted(by_year)
    if len(years) < 2:
        return None, None, 0
    rng = np.random.default_rng(_derived_seed(master_seed, key))
    values: list[float] = []
    for _ in range(replicates):
        sampled = rng.choice(years, size=len(years), replace=True)
        members = [row for year in sampled for row in by_year[int(year)]]
        x = np.asarray([float(row[x_column]) for row in members], dtype="float64")
        y = np.asarray([float(row[y_column]) for row in members], dtype="float64")
        value, status, _ = _correlation(x, y, kind, minimum_n)
        if status == "ok" and value is not None:
            values.append(value)
    if not values:
        return None, None, 0
    alpha = (1.0 - confidence_level) / 2.0
    lower, upper = np.quantile(values, [alpha, 1.0 - alpha], method="linear")
    return float(lower), float(upper), len(values)


def _association_record(
    rows: Sequence[Mapping[str, Any]], *, support: str, method: str,
    metric: str, stratum_type: str, stratum_value: str,
    config: ChlfMatchupConfig, bootstrap: bool,
) -> dict[str, Any]:
    minimum_n = int(config.values["association"]["minimum_n"])
    x_raw = np.asarray([float(row["index_value"]) for row in rows], dtype="float64")
    y_raw = np.asarray([float(row["CHLF"]) for row in rows], dtype="float64")
    positive = np.asarray([row["log10_CHLF"] is not None for row in rows], dtype=bool)
    x_log = x_raw[positive]
    y_log = np.asarray([float(row["log10_CHLF"]) for row in rows if row["log10_CHLF"] is not None], dtype="float64")
    rho, rho_status, rho_reason = _correlation(x_raw, y_raw, "spearman", minimum_n)
    pearson, pearson_status, pearson_reason = _correlation(x_log, y_log, "pearson", minimum_n)
    rho_low = rho_high = pearson_low = pearson_high = None
    rho_valid = pearson_valid = 0
    if bootstrap:
        settings = config.values["association"]["year_cluster_bootstrap"]
        base_key = f"{support}|{method}|{metric}|{stratum_type}|{stratum_value}"
        rho_low, rho_high, rho_valid = _cluster_bootstrap_ci(
            rows, x_column="index_value", y_column="CHLF", kind="spearman",
            replicates=int(settings["replicates"]), master_seed=int(settings["seed"]),
            key=base_key + "|spearman", confidence_level=float(settings["confidence_level"]),
            minimum_n=minimum_n,
        )
        log_rows = [row for row in rows if row["log10_CHLF"] is not None]
        pearson_low, pearson_high, pearson_valid = _cluster_bootstrap_ci(
            log_rows, x_column="index_value", y_column="log10_CHLF", kind="pearson",
            replicates=int(settings["replicates"]), master_seed=int(settings["seed"]),
            key=base_key + "|pearson", confidence_level=float(settings["confidence_level"]),
            minimum_n=minimum_n,
        )
    years = sorted({int(row["year"]) for row in rows})
    dates = sorted(str(row["date"]) for row in rows)
    return {
        "analysis_version": config.analysis_version,
        "support": support,
        "observation_method": method,
        "metric": metric,
        "stratum_type": stratum_type,
        "stratum_value": stratum_value,
        "n_pairs_raw_CHLF": len(rows),
        "n_pairs_positive_CHLF": int(positive.sum()),
        "n_years": len(years),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "spearman_rho": rho,
        "spearman_status": rho_status,
        "spearman_reason": rho_reason,
        "spearman_cluster_bootstrap_CI_low": rho_low,
        "spearman_cluster_bootstrap_CI_high": rho_high,
        "spearman_bootstrap_valid_replicates": rho_valid,
        "pearson_r_log10_CHLF": pearson,
        "pearson_status": pearson_status,
        "pearson_reason": pearson_reason,
        "pearson_cluster_bootstrap_CI_low": pearson_low,
        "pearson_cluster_bootstrap_CI_high": pearson_high,
        "pearson_bootstrap_valid_replicates": pearson_valid,
        "p_values_reported": False,
    }


def build_association_tables(
    pairs: Sequence[Mapping[str, Any]], config: ChlfMatchupConfig
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary: list[dict[str, Any]] = []
    annual: list[dict[str, Any]] = []
    for support, support_field in (
        ("primary_common", "primary_common_support"),
        ("secondary_method_specific", "method_specific_support"),
    ):
        for method in EXPECTED_METHODS:
            for metric in EXPECTED_METRICS:
                subset = [
                    row for row in pairs
                    if row["observation_method"] == method
                    and row["metric"] == metric and row[support_field] is True
                ]
                summary.append(
                    _association_record(
                        subset, support=support, method=method, metric=metric,
                        stratum_type="overall", stratum_value="all",
                        config=config, bootstrap=True,
                    )
                )
                for regime in sorted({str(row["measurement_regime"]) for row in subset}):
                    members = [row for row in subset if row["measurement_regime"] == regime]
                    summary.append(
                        _association_record(
                            members, support=support, method=method, metric=metric,
                            stratum_type="measurement_regime", stratum_value=regime,
                            config=config, bootstrap=False,
                        )
                    )
                for year in sorted({int(row["year"]) for row in subset}):
                    members = [row for row in subset if int(row["year"]) == year]
                    annual.append(
                        _association_record(
                            members, support=support, method=method, metric=metric,
                            stratum_type="calendar_year", stratum_value=str(year),
                            config=config, bootstrap=False,
                        )
                    )
    return summary, annual


def build_loyo_tables(
    pairs: Sequence[Mapping[str, Any]], config: ChlfMatchupConfig
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    predictions: list[dict[str, Any]] = []
    minimum_train = int(config.values["predictive_validation"]["minimum_training_n"])
    minimum_test = int(config.values["predictive_validation"]["minimum_test_n"])
    for method in EXPECTED_METHODS:
        for metric in EXPECTED_METRICS:
            subset = [
                row for row in pairs
                if row["observation_method"] == method
                and row["metric"] == metric
                and row["primary_common_support"] is True
                and row["log10_CHLF"] is not None
            ]
            years = sorted({int(row["year"]) for row in subset})
            for test_year in years:
                train = [row for row in subset if int(row["year"]) != test_year]
                test = [row for row in subset if int(row["year"]) == test_year]
                status = "ok"
                reason = ""
                if len(train) < minimum_train or len(test) < minimum_test:
                    status = "unavailable"
                    reason = "insufficient_training_or_test_pairs"
                x_train = np.asarray([float(row["index_value"]) for row in train], dtype="float64")
                mean = float(np.mean(x_train)) if len(x_train) else None
                sd = float(np.std(x_train, ddof=1)) if len(x_train) > 1 else None
                if status == "ok" and (sd is None or not math.isfinite(sd) or sd == 0):
                    status = "unavailable"
                    reason = "constant_or_invalid_training_predictor"
                intercept = slope = None
                predicted: np.ndarray | None = None
                if status == "ok":
                    z_train = (x_train - float(mean)) / float(sd)
                    y_train = np.asarray([float(row["log10_CHLF"]) for row in train], dtype="float64")
                    design = np.column_stack((np.ones(len(train)), z_train))
                    coefficients = np.linalg.lstsq(design, y_train, rcond=None)[0]
                    intercept, slope = map(float, coefficients)
                    x_test = np.asarray([float(row["index_value"]) for row in test], dtype="float64")
                    predicted = intercept + slope * ((x_test - float(mean)) / float(sd))
                for index, row in enumerate(test):
                    observed = float(row["log10_CHLF"])
                    prediction = float(predicted[index]) if predicted is not None else None
                    predictions.append(
                        {
                            "analysis_version": config.analysis_version,
                            "observation_method": method,
                            "metric": metric,
                            "test_year": test_year,
                            "date": row["date"],
                            "index_value": row["index_value"],
                            "observed_CHLF": row["CHLF"],
                            "observed_log10_CHLF": observed,
                            "predicted_log10_CHLF": prediction,
                            "residual_log10_CHLF": observed - prediction if prediction is not None else None,
                            "training_n": len(train),
                            "test_n": len(test),
                            "training_predictor_mean": mean,
                            "training_predictor_sample_sd": sd,
                            "standardized_intercept": intercept,
                            "standardized_slope": slope,
                            "fold_status": status,
                            "fold_reason": reason,
                        }
                    )

    summary: list[dict[str, Any]] = []
    for method in EXPECTED_METHODS:
        for metric in EXPECTED_METRICS:
            subset = [row for row in predictions if row["observation_method"] == method and row["metric"] == metric]
            for scope, value, members in [
                ("pooled_all_heldout", "all", subset),
                *[("test_year", str(year), [row for row in subset if int(row["test_year"]) == year]) for year in sorted({int(row["test_year"]) for row in subset})],
            ]:
                valid = [row for row in members if row["fold_status"] == "ok" and row["predicted_log10_CHLF"] is not None]
                if not valid:
                    rmse = mae = r2 = None
                    status, reason = "unavailable", "no_valid_heldout_predictions"
                else:
                    observed = np.asarray([float(row["observed_log10_CHLF"]) for row in valid])
                    predicted = np.asarray([float(row["predicted_log10_CHLF"]) for row in valid])
                    residual = observed - predicted
                    rmse = float(np.sqrt(np.mean(residual**2)))
                    mae = float(np.mean(np.abs(residual)))
                    sst = float(np.sum((observed - np.mean(observed)) ** 2))
                    r2 = float(1.0 - np.sum(residual**2) / sst) if sst > 0 else None
                    status = "ok" if r2 is not None else "partial"
                    reason = "" if r2 is not None else "constant_observed_test_response"
                summary.append(
                    {
                        "analysis_version": config.analysis_version,
                        "observation_method": method,
                        "metric": metric,
                        "evaluation_scope": scope,
                        "scope_value": value,
                        "n_predictions": len(valid),
                        "RMSE_log10_CHLF": rmse,
                        "MAE_log10_CHLF": mae,
                        "R2_log10_CHLF": r2,
                        "status": status,
                        "reason": reason,
                    }
                )
    return predictions, summary


def run_chlf_matchup_analysis(
    *, config: ChlfMatchupConfig, repository_root: str | Path
) -> ChlfMatchupResult:
    root = Path(repository_root)
    input_paths = {name: root / str(path) for name, path in config.values["inputs"].items()}
    selection = _read_csv(input_paths["observation_selection"])
    reference = _read_csv(input_paths["daily_reference"])
    audit, pairs = build_matchup_audit(selection, reference, config)
    association, annual = build_association_tables(pairs, config)
    predictions, loyo = build_loyo_tables(pairs, config)
    common_counts = {
        metric: len({row["date"] for row in pairs if row["metric"] == metric and row["primary_common_support"] is True})
        for metric in EXPECTED_METRICS
    }
    method_counts = {
        method: {
            metric: sum(
                row["observation_method"] == method and row["metric"] == metric
                for row in pairs
            )
            for metric in EXPECTED_METRICS
        }
        for method in EXPECTED_METHODS
    }
    counts = {
        "matchup_audit_rows": len(audit),
        "analysis_pair_rows": len(pairs),
        "candidate_dates": len({row["date"] for row in audit}),
        "primary_common_support_dates_by_metric": common_counts,
        "method_specific_pairs": method_counts,
        "association_summary_rows": len(association),
        "annual_association_rows": len(annual),
        "loyo_prediction_rows": len(predictions),
        "loyo_summary_rows": len(loyo),
    }
    return ChlfMatchupResult(
        tuple(audit), tuple(pairs), tuple(association), tuple(annual),
        tuple(predictions), tuple(loyo), input_paths, counts,
    )


def write_csv(rows: Sequence[Mapping[str, Any]], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["empty"], lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})
    return destination


def _git_state(root: Path) -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True).stdout.strip())
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def _write_figures(result: ChlfMatchupResult, paths: Mapping[str, Path]) -> None:
    import matplotlib.pyplot as plt

    colors = {"L1C": "#4C78A8", "L2A": "#F58518", "ACOLITE": "#54A24B"}
    fig, axes = plt.subplots(2, 3, figsize=(12, 7.2), constrained_layout=True)
    for row_index, metric in enumerate(EXPECTED_METRICS):
        for column_index, method in enumerate(EXPECTED_METHODS):
            ax = axes[row_index, column_index]
            rows = [row for row in result.analysis_pairs if row["metric"] == metric and row["observation_method"] == method and row["primary_common_support"] is True]
            x = [row["index_value"] for row in rows]
            y = [row["CHLF"] for row in rows]
            ax.scatter(x, y, s=18, alpha=0.65, color=colors[method], edgecolors="none")
            ax.set_yscale("log")
            ax.set_title(f"{method} {metric} (n={len(rows)})")
            ax.set_xlabel(metric)
            ax.set_ylabel("CHLF (log scale)")
            ax.grid(alpha=0.2)
    fig.suptitle("Erken same-day common-support index–CHLF matchups")
    metadata = {"Creator": "twinwater-timesat-s2-chla", "CreationDate": None, "ModDate": None}
    fig.savefig(paths["scatter_figure_png"], dpi=200, metadata={"Software": "twinwater-timesat-s2-chla"})
    fig.savefig(paths["scatter_figure_pdf"], metadata=metadata)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(12, 7.2), constrained_layout=True)
    for row_index, metric in enumerate(EXPECTED_METRICS):
        for column_index, method in enumerate(EXPECTED_METHODS):
            ax = axes[row_index, column_index]
            rows = [row for row in result.loyo_predictions if row["metric"] == metric and row["observation_method"] == method and row["fold_status"] == "ok"]
            x = np.asarray([row["observed_log10_CHLF"] for row in rows], dtype=float)
            y = np.asarray([row["predicted_log10_CHLF"] for row in rows], dtype=float)
            ax.scatter(x, y, s=18, alpha=0.65, color=colors[method], edgecolors="none")
            if len(x):
                low = float(min(np.min(x), np.min(y)))
                high = float(max(np.max(x), np.max(y)))
                ax.plot([low, high], [low, high], color="#555555", linewidth=1, linestyle="--")
            ax.set_title(f"{method} {metric} (n={len(rows)})")
            ax.set_xlabel("Observed log10(CHLF)")
            ax.set_ylabel("LOYO predicted log10(CHLF)")
            ax.grid(alpha=0.2)
    fig.suptitle("Erken leave-one-year-out proxy predictions")
    fig.savefig(paths["loyo_figure_png"], dpi=200, metadata={"Software": "twinwater-timesat-s2-chla"})
    fig.savefig(paths["loyo_figure_pdf"], metadata=metadata)
    plt.close(fig)


def write_chlf_matchup_outputs(
    result: ChlfMatchupResult, *, config: ChlfMatchupConfig,
    repository_root: str | Path,
) -> dict[str, Path]:
    root = Path(repository_root).resolve()
    output_root = (root / str(config.values["outputs"]["root"])).resolve()
    paths = {name: (root / str(relative)).resolve() for name, relative in config.values["outputs"].items() if name != "root"}
    for path in paths.values():
        try:
            path.relative_to(output_root)
        except ValueError as error:
            raise ChlfMatchupError(f"Output escapes Phase 6C namespace: {path}") from error
        path.parent.mkdir(parents=True, exist_ok=True)
    commit, dirty = _git_state(root)
    table_rows = {
        "matchup_audit": result.matchup_audit,
        "analysis_pairs": result.analysis_pairs,
        "association_summary": result.association_summary,
        "annual_association": result.annual_association,
        "loyo_predictions": result.loyo_predictions,
        "loyo_summary": result.loyo_summary,
    }
    for name, rows in table_rows.items():
        write_csv(rows, paths[name])
    _write_figures(result, paths)
    output_hashes = {
        name: {
            "relative_path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
        }
        for name, path in sorted(paths.items()) if name != "manifest"
    }
    manifest = {
        "schema_version": "erken_s2_chlf_matchup_analysis_manifest_v1",
        "analysis_version": config.analysis_version,
        "status": "COMPLETE_EXPLORATORY_OBSERVATION_LAYER_ANALYSIS",
        "decision_id": config.values["decision_id"],
        "configuration": {"relative_path": config.source_relative_path, "sha256": config.sha256},
        "repository": {"commit_at_generation_start": commit, "worktree_dirty_at_generation_start": dirty},
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "inputs": {
            name: {"relative_path": path.resolve().relative_to(root).as_posix(), "sha256": sha256_file(path)}
            for name, path in sorted(result.input_paths.items())
        },
        "outputs": output_hashes,
        "counts": result.counts,
        "frozen_analysis": {
            "exact_date_tolerance_days": 0,
            "primary_support": "exact_three_method_metric_common_support",
            "primary_association": "spearman_rho_raw_CHLF_vs_index",
            "secondary_association": "pearson_r_log10_CHLF_vs_index",
            "bootstrap_replicates": 10000,
            "bootstrap_seed": 20260917,
            "predictive_validation": "leave_one_calendar_year_out",
        },
        "scientific_guards": {
            "observation_threshold_retuned": False,
            "processor_winner_selected": False,
            "reconstruction_run": False,
            "timesat_run": False,
            "vombsjon_accessed": False,
        },
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return paths
