"""Gated TIMESAT 4.4.1 adapters for one-dimensional Phase 3 curves.

The public runner uses a separate Python interpreter so the compiled
TIMESAT core remains an explicit runtime dependency rather than a project
installation side effect.  Importing this module never imports TIMESAT.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping

import numpy as np
import pandas as pd

from twinwater_timesat.phase3_contract import (
    SPLINE_GRID,
    load_timesat_defaults_snapshot,
    sha256_file,
)


@dataclass(frozen=True)
class ReconstructionResult:
    """One method's explicit reconstruction or failure outcome."""

    method: str
    year: int
    status: str
    failure_reason: str
    prediction: pd.DataFrame
    diagnostics: Mapping[str, Any]


def _runtime_source_defaults() -> dict[str, Any]:
    from timesat_cli.config import DEFAULT_CLASS, DEFAULT_GENERAL, DEFAULT_OUTPUT

    return {
        "output": {
            key: DEFAULT_OUTPUT[key]
            for key in (
                "drop_first_year",
                "drop_last_year",
                "outputvariables",
                "p_hrvppformat",
                "p_nodata",
                "p_st_timestep",
                "time_sampling",
                "time_step_days",
            )
        },
        "general": {
            key: DEFAULT_GENERAL[key]
            for key in (
                "p_davailwin",
                "p_ignoreday",
                "p_outlier",
                "p_printflag",
                "p_ylu",
            )
        },
        "class": {
            key: DEFAULT_CLASS[key]
            for key in (
                "highrangemode",
                "landuse",
                "lowrangemode",
                "p_fillbase",
                "p_fitmethod",
                "p_low_percentile",
                "p_nenvi",
                "p_seapar",
                "p_seasonmethod",
                "p_smooth",
                "p_startcutoff",
                "p_startmethod",
                "p_wfactnum",
                "rangedownweight",
            )
        },
    }


def _effective_parameters(source: Mapping[str, Any]) -> dict[str, Any]:
    output = source["output"]
    general = source["general"]
    class_defaults = source["class"]
    return {
        "outputvariables": output["outputvariables"],
        "p_ignoreday": general["p_ignoreday"],
        "p_ylu": general["p_ylu"],
        "p_printflag": general["p_printflag"],
        "landuse": class_defaults["landuse"],
        "p_fitmethod": 1,
        "p_smooth": class_defaults["p_smooth"],
        "p_nodata": output["p_nodata"],
        "p_davailwin": general["p_davailwin"],
        "p_outlier": general["p_outlier"],
        "p_nenvi": class_defaults["p_nenvi"],
        "p_wfactnum": class_defaults["p_wfactnum"],
        "p_startmethod": class_defaults["p_startmethod"],
        "p_startcutoff": class_defaults["p_startcutoff"],
        "p_low_percentile": class_defaults["p_low_percentile"],
        "p_fillbase": class_defaults["p_fillbase"],
        "p_hrvppformat": output["p_hrvppformat"],
        "p_seasonmethod": class_defaults["p_seasonmethod"],
        "p_seapar": class_defaults["p_seapar"],
        "p_lowrangemode": class_defaults["lowrangemode"],
        "p_highrangemode": class_defaults["highrangemode"],
        "p_rangedownweight": class_defaults["rangedownweight"],
        "time_sampling": output["time_sampling"],
        "time_step_days": output["time_step_days"],
        "p_st_timestep": output["p_st_timestep"],
        "drop_first_year": output["drop_first_year"],
        "drop_last_year": output["drop_last_year"],
        "sparse_input_weight": 1.0,
    }


def probe_runtime(snapshot_path: str | Path, *, smoke_test: bool = False) -> dict[str, Any]:
    """Inspect and gate the active TIMESAT runtime; called in its own interpreter."""

    import timesat
    import timesat_cli
    import timesat_cli.config
    import timesat_cli.single_pixel

    snapshot = load_timesat_defaults_snapshot(snapshot_path)
    source_defaults = _runtime_source_defaults()
    effective = _effective_parameters(source_defaults)
    core_version = metadata.version("timesat")
    cli_version = metadata.version("timesat-cli")
    core_init = Path(timesat.__file__)
    cli_config = Path(timesat_cli.config.__file__)
    cli_single_pixel = Path(timesat_cli.single_pixel.__file__)
    binary_candidates = sorted(core_init.parent.glob("_timesat*"))
    binary = binary_candidates[0] if binary_candidates else None
    observed = {
        "timesat_core_version": core_version,
        "timesat_cli_version": cli_version,
        "timesat_core_init_sha256": sha256_file(core_init),
        "timesat_cli_config_sha256": sha256_file(cli_config),
        "timesat_cli_single_pixel_sha256": sha256_file(cli_single_pixel),
        "timesat_core_binary_filename": binary.name if binary else None,
        "timesat_core_binary_sha256": sha256_file(binary) if binary else None,
        "source_defaults": source_defaults,
        "effective_runtime_parameters": effective,
    }
    mismatches: list[str] = []
    if core_version != snapshot["timesat_core"]["version"]:
        mismatches.append("timesat_core_version")
    if cli_version != snapshot["timesat_cli"]["version"]:
        mismatches.append("timesat_cli_version")
    expected_hashes = {
        "timesat_core_init_sha256": snapshot["timesat_core"]["source_init_sha256"],
        "timesat_cli_config_sha256": snapshot["timesat_cli"]["config_module_sha256"],
        "timesat_cli_single_pixel_sha256": snapshot["timesat_cli"][
            "single_pixel_module_sha256"
        ],
    }
    for key, expected in expected_hashes.items():
        if observed[key] != expected:
            mismatches.append(key)
    if source_defaults != snapshot["source_defaults"]:
        mismatches.append("source_defaults")
    if effective != snapshot["effective_runtime_parameters"]:
        mismatches.append("effective_runtime_parameters")

    matching_build = None
    if binary is not None:
        matching_build = next(
            (
                item
                for item in snapshot["timesat_core"]["observed_build_artifacts"]
                if item["filename"] == binary.name
            ),
            None,
        )
        if matching_build and matching_build["sha256"] != observed[
            "timesat_core_binary_sha256"
        ]:
            mismatches.append("timesat_core_binary_sha256")
    observed["registered_build_artifact"] = bool(matching_build)
    observed["runtime_defaults_match_snapshot"] = not mismatches
    observed["mismatches"] = mismatches
    observed["smoke_test"] = None
    if smoke_test and not mismatches:
        observed["smoke_test"] = synthetic_timesat_smoke_test(snapshot_path)
        if not observed["smoke_test"]["passed"]:
            mismatches.append("synthetic_timesat_smoke_test")
            observed["runtime_defaults_match_snapshot"] = False
    if mismatches:
        raise RuntimeError(
            "TIMESAT runtime differs from the frozen defaults snapshot: "
            + ", ".join(mismatches)
        )
    return observed


def _parameter_array(value: Any, dtype: Any) -> np.ndarray:
    return np.full(255, value, dtype=dtype)


def _run_timesat_core(
    *,
    year: int,
    dates: list[pd.Timestamp],
    values: list[float],
    method: str,
    smoothing: int | None,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    import timesat
    from timesat_cli.dateutils import date_with_ignored_day

    if method not in {"timesat_double_logistic", "timesat_smoothing_spline"}:
        raise ValueError(f"Unsupported TIMESAT method: {method}")
    if method == "timesat_smoothing_spline":
        if smoothing not in SPLINE_GRID:
            raise ValueError(f"Spline smoothing must be in {SPLINE_GRID}; found {smoothing}.")
        fit_method = 2
        smooth = int(smoothing)
    else:
        if smoothing is not None:
            raise ValueError("Double logistic does not accept a tuned smoothing value.")
        fit_method = int(parameters["p_fitmethod"])
        smooth = int(parameters["p_smooth"])

    normalized_dates = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    if normalized_dates.duplicated().any():
        raise ValueError("TIMESAT sparse input dates must be unique.")
    if any(date.year != year for date in normalized_dates):
        raise ValueError("Every TIMESAT sparse input date must belong to its year.")
    array_values = np.asarray(values, dtype=np.float64)
    if len(array_values) != len(normalized_dates) or not np.isfinite(array_values).all():
        raise ValueError("TIMESAT sparse values must be finite and align with dates.")
    order = np.argsort(normalized_dates.to_numpy())
    normalized_dates = normalized_dates[order]
    array_values = array_values[order]
    tv = np.asarray(
        [date.year * 1000 + date.dayofyear for date in normalized_dates],
        dtype=np.int32,
    )
    raw_y = np.asfortranarray(array_values.reshape(1, 1, -1), dtype=np.float64)
    raw_w = np.asfortranarray(
        np.full_like(raw_y, parameters["sparse_input_weight"]), dtype=np.float64
    )
    output_index = np.arange(
        1, 366, int(parameters["p_st_timestep"]), dtype=np.int32
    )
    p_startcutoff = np.asfortranarray(
        np.tile(parameters["p_startcutoff"], (255, 1)), dtype=np.float64
    )
    result = timesat.tsfprocess(
        1,
        raw_y,
        raw_w,
        tv,
        np.ones((1, 1), dtype=np.uint8),
        1,
        _parameter_array(parameters["landuse"], np.uint8),
        output_index,
        parameters["p_ignoreday"],
        np.asarray(parameters["p_ylu"], dtype=np.float64),
        parameters["p_printflag"],
        _parameter_array(fit_method, np.uint8),
        _parameter_array(smooth, np.float64),
        parameters["p_nodata"],
        parameters["p_davailwin"],
        parameters["p_outlier"],
        _parameter_array(parameters["p_nenvi"], np.uint8),
        _parameter_array(parameters["p_wfactnum"], np.float64),
        _parameter_array(parameters["p_startmethod"], np.uint8),
        p_startcutoff,
        _parameter_array(parameters["p_low_percentile"], np.float64),
        _parameter_array(parameters["p_fillbase"], np.uint8),
        parameters["p_hrvppformat"],
        _parameter_array(parameters["p_seasonmethod"], np.uint8),
        _parameter_array(parameters["p_seapar"], np.float64),
        _parameter_array(parameters["p_lowrangemode"], np.int32),
        _parameter_array(parameters["p_highrangemode"], np.int32),
        _parameter_array(parameters["p_rangedownweight"], np.float64),
        1,
        1,
        1,
        len(normalized_dates),
        len(output_index),
    )
    nseason = np.asarray(result[2])
    yfit = np.asarray(result[3], dtype=float)[0, 0, :]
    yfitqa = np.asarray(result[4])[0, 0, :]
    output_dates = [
        pd.Timestamp(date_with_ignored_day(year, int(index), parameters["p_ignoreday"]))
        for index in output_index
    ]
    finite = np.isfinite(yfit)
    status = "ok"
    failure_reason = ""
    if len(yfit) != len(output_dates):
        status = "failed"
        failure_reason = "unexpected_output_length"
    elif not finite.all():
        status = "failed"
        failure_reason = "missing_or_nonfinite_reconstruction"
    elif np.all(yfit == 0) and np.any(array_values != 0):
        status = "failed"
        failure_reason = "timesat_returned_zero_initialized_curve"
    prediction = [float(value) if np.isfinite(value) else None for value in yfit]
    return {
        "method": method,
        "year": year,
        "smoothing": smoothing,
        "status": status,
        "failure_reason": failure_reason,
        "dates": [date.strftime("%Y-%m-%d") for date in output_dates],
        "prediction": prediction,
        "diagnostics": {
            "n_sparse_inputs": len(normalized_dates),
            "nseason": nseason.astype(int).ravel().tolist(),
            "n_output_dates": len(output_dates),
            "n_finite_output_dates": int(finite.sum()),
            "minimum_reconstructed_value": float(np.min(yfit[finite])) if finite.any() else None,
            "n_negative_reconstructed_days": int((yfit[finite] < 0).sum()),
            "fraction_negative_reconstructed_days": (
                float((yfit[finite] < 0).mean()) if finite.any() else None
            ),
            "negative_values_clipped": False,
            "timesat_yfitqa_values": sorted(np.unique(yfitqa).astype(int).tolist()),
        },
    }


def execute_runtime_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one external-runtime request for the small adapter CLI."""

    operation = request.get("operation")
    snapshot_path = request.get("snapshot_path")
    if not isinstance(snapshot_path, str):
        raise ValueError("Runtime request requires snapshot_path.")
    if operation == "probe":
        return probe_runtime(snapshot_path, smoke_test=bool(request.get("smoke_test")))
    if operation == "probe_seapar_grid":
        runtime = probe_runtime(snapshot_path, smoke_test=False)
        sensitivity = synthetic_seapar_grid_smoke_test(
            snapshot_path, request.get("candidate_grid")
        )
        return {"runtime": runtime, **sensitivity}
    if operation not in {"reconstruct", "reconstruct_seapar_sensitivity"}:
        raise ValueError(f"Unknown runtime operation: {operation!r}")
    snapshot = load_timesat_defaults_snapshot(snapshot_path)
    probe_runtime(snapshot_path, smoke_test=False)
    parameters = snapshot["effective_runtime_parameters"]
    sensitivity_parameter: float | None = None
    if operation == "reconstruct_seapar_sensitivity":
        if request.get("method") != "timesat_double_logistic":
            raise ValueError("p_seapar sensitivity is double-logistic only.")
        sensitivity_parameter = _validated_p_seapar(request.get("p_seapar"))
        parameters = {**parameters, "p_seapar": sensitivity_parameter}
    output = _run_timesat_core(
        year=int(request["year"]),
        dates=[pd.Timestamp(value) for value in request["dates"]],
        values=[float(value) for value in request["values"]],
        method=str(request["method"]),
        smoothing=(
            None if request.get("smoothing") is None else int(request["smoothing"])
        ),
        parameters=parameters,
    )
    if sensitivity_parameter is not None:
        materialized = _parameter_array(sensitivity_parameter, np.float64)
        output["diagnostics"].update(
            {
                "requested_p_seapar": sensitivity_parameter,
                "requested_p_seapar_float64_hex": sensitivity_parameter.hex(),
                "effective_p_seapar": float(materialized[0]),
                "effective_p_seapar_float64_hex": float(materialized[0]).hex(),
                "p_seapar_array_dtype": str(materialized.dtype),
                "p_seapar_array_unique_count": int(np.unique(materialized).size),
                "p_seapar_exactly_materialized": bool(
                    np.all(materialized == sensitivity_parameter)
                ),
            }
        )
    return output


def _validated_p_seapar(value: Any) -> float:
    """Validate a sensitivity value without rounding, clipping, or coercion."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("p_seapar must be a real JSON number.")
    candidate = float(value)
    if not np.isfinite(candidate) or not 0.0 <= candidate <= 1.0:
        raise ValueError("p_seapar must be finite and in the closed interval [0, 1].")
    return candidate


def synthetic_seapar_grid_smoke_test(
    snapshot_path: str | Path, candidate_grid: Any
) -> dict[str, Any]:
    """Materialize and exercise every requested sensitivity candidate."""

    if not isinstance(candidate_grid, list) or not candidate_grid:
        raise ValueError("A non-empty p_seapar candidate_grid list is required.")
    candidates = [_validated_p_seapar(value) for value in candidate_grid]
    snapshot = load_timesat_defaults_snapshot(snapshot_path)
    base_parameters = snapshot["effective_runtime_parameters"]
    doys = np.arange(1, 366, 15, dtype=int)
    values = 2 + 5 * np.exp(-((doys - 100) / 35) ** 2) + 8 * np.exp(
        -((doys - 235) / 45) ** 2
    )
    dates = [
        pd.Timestamp("2019-01-01") + pd.Timedelta(days=int(day - 1))
        for day in doys
    ]
    checks: list[dict[str, Any]] = []
    for candidate in candidates:
        materialized = _parameter_array(candidate, np.float64)
        parameters = {**base_parameters, "p_seapar": candidate}
        output = _run_timesat_core(
            year=2019,
            dates=dates,
            values=values.tolist(),
            method="timesat_double_logistic",
            smoothing=None,
            parameters=parameters,
        )
        exact = bool(
            np.all(materialized == candidate)
            and float(materialized[0]).hex() == candidate.hex()
        )
        checks.append(
            {
                "requested_p_seapar": candidate,
                "requested_float64_hex": candidate.hex(),
                "effective_p_seapar": float(materialized[0]),
                "effective_float64_hex": float(materialized[0]).hex(),
                "materialized_dtype": str(materialized.dtype),
                "materialized_unique_count": int(np.unique(materialized).size),
                "effective_equals_requested": exact,
                "reconstruction_status": output["status"],
                "reconstruction_failure_reason": output["failure_reason"],
                "n_output_dates": output["diagnostics"]["n_output_dates"],
                "n_finite_output_dates": output["diagnostics"][
                    "n_finite_output_dates"
                ],
                "runtime_nseason": output["diagnostics"]["nseason"],
            }
        )
    passed = all(
        check["effective_equals_requested"]
        and check["reconstruction_status"] == "ok"
        and check["n_output_dates"] == 365
        and check["n_finite_output_dates"] == 365
        for check in checks
    )
    return {
        "candidate_grid_accepted": passed,
        "candidate_checks": checks,
        "scientific_performance_evaluated": False,
    }


def synthetic_timesat_smoke_test(snapshot_path: str | Path) -> dict[str, Any]:
    """Exercise both TIMESAT algorithms on synthetic data without Erken results."""

    snapshot = load_timesat_defaults_snapshot(snapshot_path)
    doys = np.arange(1, 366, 15, dtype=int)
    values = 2 + 8 * np.exp(-((doys - 210) / 60) ** 2)
    dates = [pd.Timestamp("2019-01-01") + pd.Timedelta(days=int(day - 1)) for day in doys]
    checks = []
    for method, smoothing in (
        ("timesat_double_logistic", None),
        ("timesat_smoothing_spline", 10),
    ):
        output = _run_timesat_core(
            year=2019,
            dates=dates,
            values=values.tolist(),
            method=method,
            smoothing=smoothing,
            parameters=snapshot["effective_runtime_parameters"],
        )
        checks.append(
            {
                "method": method,
                "status": output["status"],
                "failure_reason": output["failure_reason"],
                "n_output_dates": output["diagnostics"]["n_output_dates"],
                "n_finite_output_dates": output["diagnostics"][
                    "n_finite_output_dates"
                ],
            }
        )
    return {
        "passed": all(
            item["status"] == "ok"
            and item["n_output_dates"] == 365
            and item["n_finite_output_dates"] == 365
            for item in checks
        ),
        "checks": checks,
        "scientific_performance_evaluated": False,
    }


class SubprocessTimesatRunner:
    """Run the frozen TIMESAT environment through a checked helper process."""

    def __init__(
        self,
        *,
        python_executable: str | Path,
        runtime_script: str | Path,
        snapshot_path: str | Path,
    ) -> None:
        self.python_executable = Path(python_executable)
        self.runtime_script = Path(runtime_script)
        self.snapshot_path = Path(snapshot_path)

    def _request(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not self.python_executable.is_file():
            raise FileNotFoundError(
                f"Configured TIMESAT Python executable not found: {self.python_executable}"
            )
        if not self.runtime_script.is_file():
            raise FileNotFoundError(f"TIMESAT runtime script not found: {self.runtime_script}")
        load_timesat_defaults_snapshot(self.snapshot_path)
        request = dict(payload)
        request["snapshot_path"] = str(self.snapshot_path.resolve())
        with tempfile.TemporaryDirectory(prefix="twinwater_timesat_") as directory:
            request_path = Path(directory) / "request.json"
            output_path = Path(directory) / "output.json"
            request_path.write_text(
                json.dumps(request, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    str(self.python_executable),
                    str(self.runtime_script),
                    "--request",
                    str(request_path),
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                message = completed.stderr.strip() or completed.stdout.strip()
                raise RuntimeError(
                    f"TIMESAT runtime request failed ({completed.returncode}): {message}"
                )
            if not output_path.is_file():
                raise RuntimeError("TIMESAT runtime did not write its JSON response.")
            return json.loads(output_path.read_text(encoding="utf-8"))

    def verify_runtime(self, *, smoke_test: bool = True) -> dict[str, Any]:
        """Fail loudly unless versions, defaults, hashes, and smoke test match."""

        return self._request({"operation": "probe", "smoke_test": smoke_test})

    def verify_seapar_grid(self, candidate_grid: tuple[float, ...]) -> dict[str, Any]:
        """Verify exact materialization and synthetic execution of a frozen grid."""

        return self._request(
            {"operation": "probe_seapar_grid", "candidate_grid": list(candidate_grid)}
        )

    def reconstruct_with_seapar(
        self,
        *,
        year: int,
        sparse: pd.DataFrame,
        target_dates: pd.Series | pd.DatetimeIndex,
        p_seapar: float,
    ) -> ReconstructionResult:
        """Run double logistic with an explicit, recorded sensitivity parameter."""

        required = {"date", "CHLF"}
        missing = sorted(required - set(sparse.columns))
        if missing:
            raise ValueError(f"Sparse input table lacks columns: {missing}")
        response = self._request(
            {
                "operation": "reconstruct_seapar_sensitivity",
                "method": "timesat_double_logistic",
                "year": int(year),
                "dates": pd.to_datetime(sparse["date"])
                .dt.strftime("%Y-%m-%d")
                .tolist(),
                "values": pd.to_numeric(sparse["CHLF"], errors="raise").tolist(),
                "smoothing": None,
                "p_seapar": _validated_p_seapar(p_seapar),
            }
        )
        prediction = pd.DataFrame(
            {
                "date": pd.to_datetime(response["dates"]),
                "prediction": response["prediction"],
            }
        )
        targets = pd.DatetimeIndex(pd.to_datetime(target_dates)).normalize()
        prediction = prediction.loc[prediction["date"].isin(targets)].copy()
        missing_targets = targets.difference(pd.DatetimeIndex(prediction["date"]))
        status = response["status"]
        failure_reason = response["failure_reason"]
        if len(missing_targets):
            status = "failed"
            failure_reason = "timesat_calendar_missing_required_support_dates"
        return ReconstructionResult(
            method="timesat_double_logistic_cv_seapar",
            year=int(year),
            status=status,
            failure_reason=failure_reason,
            prediction=prediction.sort_values("date").reset_index(drop=True),
            diagnostics={
                **response["diagnostics"],
                "n_missing_required_support_dates": int(len(missing_targets)),
            },
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
        """Reconstruct from only the supplied sparse dates and values."""

        required = {"date", "CHLF"}
        missing = sorted(required - set(sparse.columns))
        if missing:
            raise ValueError(f"Sparse input table lacks columns: {missing}")
        response = self._request(
            {
                "operation": "reconstruct",
                "method": method,
                "year": int(year),
                "dates": pd.to_datetime(sparse["date"]).dt.strftime("%Y-%m-%d").tolist(),
                "values": pd.to_numeric(sparse["CHLF"], errors="raise").tolist(),
                "smoothing": smoothing,
            }
        )
        prediction = pd.DataFrame(
            {"date": pd.to_datetime(response["dates"]), "prediction": response["prediction"]}
        )
        targets = pd.DatetimeIndex(pd.to_datetime(target_dates)).normalize()
        prediction = prediction.loc[prediction["date"].isin(targets)].copy()
        missing_targets = targets.difference(pd.DatetimeIndex(prediction["date"]))
        status = response["status"]
        failure_reason = response["failure_reason"]
        if len(missing_targets):
            status = "failed"
            failure_reason = "timesat_calendar_missing_required_support_dates"
        return ReconstructionResult(
            method=method,
            year=int(year),
            status=status,
            failure_reason=failure_reason,
            prediction=prediction.sort_values("date").reset_index(drop=True),
            diagnostics={
                **response["diagnostics"],
                "n_missing_required_support_dates": int(len(missing_targets)),
            },
        )


def linear_reconstruct(
    *, year: int, sparse: pd.DataFrame, target_dates: pd.Series | pd.DatetimeIndex
) -> ReconstructionResult:
    """Fixed interpolation baseline with no boundary extrapolation."""

    required = {"date", "CHLF"}
    missing = sorted(required - set(sparse.columns))
    if missing:
        raise ValueError(f"Sparse input table lacks columns: {missing}")
    observed = sparse[["date", "CHLF"]].copy()
    observed["date"] = pd.to_datetime(observed["date"]).dt.normalize()
    observed["CHLF"] = pd.to_numeric(observed["CHLF"], errors="coerce")
    observed = observed.sort_values("date")
    targets = pd.DatetimeIndex(pd.to_datetime(target_dates)).normalize().sort_values()
    if observed["date"].duplicated().any():
        raise ValueError("Linear sparse input dates must be unique.")
    if len(observed) < 2 or not np.isfinite(observed["CHLF"]).all():
        return ReconstructionResult(
            "linear_interpolation",
            int(year),
            "failed",
            "insufficient_or_nonfinite_sparse_inputs",
            pd.DataFrame({"date": targets, "prediction": np.nan}),
            {"n_sparse_inputs": int(len(observed)), "negative_values_clipped": False},
        )
    first = observed["date"].iloc[0]
    last = observed["date"].iloc[-1]
    if (targets < first).any() or (targets > last).any():
        return ReconstructionResult(
            "linear_interpolation",
            int(year),
            "failed",
            "target_dates_outside_sparse_boundaries",
            pd.DataFrame({"date": targets, "prediction": np.nan}),
            {"n_sparse_inputs": int(len(observed)), "negative_values_clipped": False},
        )
    origin = first
    x = (observed["date"] - origin).dt.total_seconds().to_numpy() / 86400
    x_target = (targets - origin).total_seconds().to_numpy() / 86400
    values = np.interp(x_target, x, observed["CHLF"].to_numpy(dtype=float))
    return ReconstructionResult(
        "linear_interpolation",
        int(year),
        "ok",
        "",
        pd.DataFrame({"date": targets, "prediction": values}),
        {
            "n_sparse_inputs": int(len(observed)),
            "minimum_reconstructed_value": float(np.min(values)),
            "n_negative_reconstructed_days": int((values < 0).sum()),
            "fraction_negative_reconstructed_days": float((values < 0).mean()),
            "negative_values_clipped": False,
            "boundary_extrapolation": False,
        },
    )
