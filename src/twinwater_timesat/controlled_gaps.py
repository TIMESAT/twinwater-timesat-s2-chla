"""Frozen deterministic Phase 3 controlled-missingness generators."""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pandas as pd

from twinwater_timesat.phase3_contract import (
    CONSECUTIVE_GAP_DAYS,
    MASTER_SEED,
    PRIMARY_YEARS,
    RANDOM_DELETION_FRACTIONS,
    RANDOM_REPLICATES,
)
from twinwater_timesat.reconstruction_metrics import robust_reference_scale


RNG_SPECIFICATION = "numpy.random.Generator(numpy.random.PCG64(seed))"


def frozen_deletion_count(n_interior: int, fraction: float) -> int:
    """Apply the frozen half-up deletion-count rule and bounds."""

    if n_interior < 0:
        raise ValueError("n_interior must be non-negative.")
    if not 0 <= fraction <= 1:
        raise ValueError("deletion fraction must lie in [0, 1].")
    value = math.floor(fraction * n_interior + 0.5)
    return min(max(value, 0), n_interior)


def frozen_random_seed(year: int, level_index: int, replicate: int) -> int:
    """Return the contract v1.0.1 seed for one random mask."""

    if year not in PRIMARY_YEARS:
        raise ValueError(f"year must be in {PRIMARY_YEARS}.")
    if level_index not in (1, 2, 3, 4):
        raise ValueError("level_index must be 1, 2, 3, or 4.")
    if not 1 <= replicate <= RANDOM_REPLICATES:
        raise ValueError(f"replicate must be in [1, {RANDOM_REPLICATES}].")
    return (
        MASTER_SEED
        + 100000 * (year - 2019)
        + 1000 * level_index
        + replicate
    )


def _iso_dates(dates: Sequence[pd.Timestamp] | pd.DatetimeIndex) -> str:
    return ";".join(pd.Timestamp(date).strftime("%Y-%m-%d") for date in dates)


def _maximum_internal_gap(dates: pd.DatetimeIndex) -> int:
    ordered = dates.sort_values()
    if len(ordered) < 2:
        return 0
    return int(np.max(np.diff(ordered.to_numpy()).astype("timedelta64[D]").astype(int)))


def generate_random_deletion_masks(
    common_support: pd.DataFrame,
    *,
    fractions: Sequence[float] = RANDOM_DELETION_FRACTIONS,
    replicates: int = RANDOM_REPLICATES,
) -> pd.DataFrame:
    """Generate all 2,800 frozen actual-mask random-deletion manifests."""

    if tuple(float(value) for value in fractions) != RANDOM_DELETION_FRACTIONS:
        raise ValueError(
            f"Random deletion fractions must be exactly {RANDOM_DELETION_FRACTIONS}."
        )
    if replicates != RANDOM_REPLICATES:
        raise ValueError(f"Random replicate count must be {RANDOM_REPLICATES}.")
    rows: list[dict[str, Any]] = []
    for year in PRIMARY_YEARS:
        group = common_support.loc[common_support["year"].eq(year)].sort_values("date")
        sparse = pd.DatetimeIndex(
            group.loc[group["s2_openwater_reference_candidate"], "date"]
        ).sort_values()
        if len(sparse) < 2:
            raise ValueError(f"Year {year} needs at least two protected sparse inputs.")
        first_sparse, last_sparse = sparse[0], sparse[-1]
        interior = sparse[1:-1]
        n_support = int(group["common_support"].sum())
        if n_support <= 0:
            raise ValueError(f"Year {year} has no common-support days.")
        for level_index, fraction in enumerate(fractions, start=1):
            n_delete = frozen_deletion_count(len(interior), float(fraction))
            for replicate in range(1, replicates + 1):
                seed = frozen_random_seed(year, level_index, replicate)
                generator = np.random.Generator(np.random.PCG64(seed))
                if n_delete:
                    deleted_raw = generator.choice(
                        interior.to_numpy(), size=n_delete, replace=False
                    )
                    deleted = pd.DatetimeIndex(deleted_raw).sort_values()
                else:
                    deleted = pd.DatetimeIndex([])
                remaining = sparse.difference(deleted).sort_values()
                if remaining[0] != first_sparse or remaining[-1] != last_sparse:
                    raise AssertionError("Random deletion moved frozen support boundaries.")
                rows.append(
                    {
                        "mask_id": (
                            f"random_{year}_k{level_index}_r{replicate:03d}"
                        ),
                        "scenario_family": "random_deletion",
                        "year": year,
                        "deletion_fraction": float(fraction),
                        "deletion_level_index": level_index,
                        "replicate": replicate,
                        "seed": seed,
                        "rng_specification": RNG_SPECIFICATION,
                        "n_interior": int(len(interior)),
                        "n_delete": n_delete,
                        "deleted_dates": _iso_dates(deleted),
                        "observations_remaining": int(len(remaining)),
                        "common_support_open_water_days": n_support,
                        "resulting_observation_density": float(
                            len(remaining) / n_support
                        ),
                        "resulting_maximum_internal_gap_days": (
                            _maximum_internal_gap(remaining)
                        ),
                        "frozen_first_sparse_input_date": first_sparse,
                        "frozen_last_sparse_input_date": last_sparse,
                        "result_first_sparse_input_date": remaining[0],
                        "result_last_sparse_input_date": remaining[-1],
                    }
                )
    output = pd.DataFrame(rows)
    expected_rows = len(PRIMARY_YEARS) * 4 * RANDOM_REPLICATES
    if len(output) != expected_rows:
        raise AssertionError(
            f"Expected {expected_rows} random masks, generated {len(output)}."
        )
    return output


def _segment_reference_diagnostics(window: pd.DataFrame) -> dict[str, Any]:
    values = window["CHLF"].to_numpy(dtype=float)
    differences = np.diff(values)
    return {
        "reference_range_inside_window": float(np.max(values) - np.min(values)),
        "maximum_absolute_daily_change_inside_window": (
            float(np.max(np.abs(differences))) if len(differences) else 0.0
        ),
        "net_start_to_end_reference_change": (
            float(values[-1] - values[0]) if len(values) else np.nan
        ),
        "within_window_total_variation": (
            float(np.sum(np.abs(differences))) if len(differences) else 0.0
        ),
    }


def generate_consecutive_gap_windows(
    common_support: pd.DataFrame,
    *,
    durations: Sequence[int] = CONSECUTIVE_GAP_DAYS,
) -> pd.DataFrame:
    """Generate exhaustive eligible daily sliding windows and frozen annotations."""

    if tuple(int(value) for value in durations) != CONSECUTIVE_GAP_DAYS:
        raise ValueError(
            f"Consecutive durations must be exactly {CONSECUTIVE_GAP_DAYS}."
        )
    rows: list[dict[str, Any]] = []
    gap_id = 0
    for year in PRIMARY_YEARS:
        year_data = common_support.loc[common_support["year"].eq(year)].sort_values(
            "date"
        )
        support = year_data.loc[year_data["common_support"]].copy()
        sparse = pd.DatetimeIndex(
            year_data.loc[
                year_data["s2_openwater_reference_candidate"], "date"
            ]
        ).sort_values()
        first_sparse, last_sparse = sparse[0], sparse[-1]
        reference_scale = robust_reference_scale(support["CHLF"])
        global_maximum = float(support["CHLF"].max())
        global_maximum_dates = pd.DatetimeIndex(
            support.loc[support["CHLF"].eq(global_maximum), "date"]
        )
        for segment_id, segment in support.groupby(
            "common_support_segment_id", sort=True
        ):
            segment = segment.sort_values("date")
            segment_start = segment["date"].iloc[0]
            segment_end = segment["date"].iloc[-1]
            segment_elapsed = int((segment_end - segment_start).days)
            for duration in durations:
                last_start = segment_end - pd.Timedelta(days=int(duration) - 1)
                if last_start < segment_start:
                    continue
                for window_start in pd.date_range(
                    segment_start, last_start, freq="D"
                ):
                    window_end = window_start + pd.Timedelta(days=int(duration) - 1)
                    window = segment.loc[
                        segment["date"].between(window_start, window_end)
                    ]
                    if len(window) != duration:
                        raise AssertionError(
                            "A consecutive window crossed a support discontinuity."
                        )
                    deleted = sparse[
                        (sparse >= window_start) & (sparse <= window_end)
                    ]
                    if len(deleted) == 0:
                        continue
                    if first_sparse in deleted or last_sparse in deleted:
                        continue
                    remaining = sparse.difference(deleted).sort_values()
                    if remaining[0] != first_sparse or remaining[-1] != last_sparse:
                        raise AssertionError(
                            "Consecutive deletion moved frozen support boundaries."
                        )
                    gap_id += 1
                    midpoint = window_start + pd.Timedelta(
                        days=(int(duration) - 1) / 2
                    )
                    diagnostics = _segment_reference_diagnostics(window)
                    if reference_scale["scale_available"]:
                        a_gap = (
                            diagnostics["within_window_total_variation"]
                            / reference_scale["scale"]
                        )
                        a_gap_status = "ok"
                        a_gap_reason = ""
                    else:
                        a_gap = np.nan
                        a_gap_status = "unavailable"
                        a_gap_reason = reference_scale["scale_unavailable_reason"]
                    rows.append(
                        {
                            "gap_id": gap_id,
                            "mask_id": (
                                f"consecutive_{year}_{duration}d_"
                                f"{window_start.strftime('%Y%m%d')}"
                            ),
                            "scenario_family": "consecutive_internal_gap",
                            "year": year,
                            "common_support_segment_id": str(segment_id),
                            "duration_days": int(duration),
                            "window_start_date": window_start,
                            "window_end_date": window_end,
                            "window_midpoint_date": midpoint,
                            "window_midpoint_relative_position": (
                                float((midpoint - segment_start).total_seconds() / 86400)
                                / segment_elapsed
                                if segment_elapsed > 0
                                else np.nan
                            ),
                            "midpoint_position_status": (
                                "ok" if segment_elapsed > 0 else "unavailable"
                            ),
                            "midpoint_position_reason": (
                                "" if segment_elapsed > 0 else "zero_duration_segment"
                            ),
                            "observations_removed": int(len(deleted)),
                            "deleted_dates": _iso_dates(deleted),
                            "observations_remaining": int(len(remaining)),
                            "resulting_observation_density": float(
                                len(remaining) / len(support)
                            ),
                            "resulting_maximum_internal_gap_days": (
                                _maximum_internal_gap(remaining)
                            ),
                            "contains_reference_global_peak": bool(
                                global_maximum_dates.isin(
                                    pd.date_range(window_start, window_end, freq="D")
                                ).any()
                            ),
                            "reference_global_maximum": global_maximum,
                            "q05_reference": reference_scale["q05"],
                            "q95_reference": reference_scale["q95"],
                            "q95_minus_q05": reference_scale["scale"],
                            "a_gap": float(a_gap) if np.isfinite(a_gap) else np.nan,
                            "a_gap_status": a_gap_status,
                            "a_gap_reason": a_gap_reason,
                            **diagnostics,
                            "frozen_first_sparse_input_date": first_sparse,
                            "frozen_last_sparse_input_date": last_sparse,
                            "result_first_sparse_input_date": remaining[0],
                            "result_last_sparse_input_date": remaining[-1],
                        }
                    )
    return pd.DataFrame(rows)
