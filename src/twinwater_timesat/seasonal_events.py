"""Frozen supplementary seasonal-event detection and matching protocol v1.0."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from twinwater_timesat.phase3_contract import (
    CONTRACT_VERSION,
    canonical_json_payload_sha256,
    sha256_file,
)
from twinwater_timesat.reconstruction_metrics import robust_reference_scale


PROTOCOL_VERSION = "Seasonal_Event_Detection_and_Matching_Protocol_v1.0"
ANALYSIS_CLASSIFICATION = "secondary_exploratory"
REFERENCE_DISTANCE_DAYS = 30
REFERENCE_PROMINENCE_FRACTION = 0.30
MATCH_WINDOW_DAYS = 15
PLATEAU_SIZE = (1, None)
EXPECTED_EVENT_TIMES = (
    ("ERK_2019_E01", "2019-08-26"),
    ("ERK_2019_E02", "2019-10-12"),
    ("ERK_2020_E01", "2020-04-18"),
    ("ERK_2020_E02", "2020-08-09"),
    ("ERK_2020_E03", "2020-09-09"),
    ("ERK_2021_E01", "2021-04-08"),
    ("ERK_2021_E02", "2021-08-09"),
    ("ERK_2022_E01", "2022-08-07"),
    ("ERK_2022_E02", "2022-09-26"),
    ("ERK_2023_E01", "2023-04-23"),
    ("ERK_2023_E02", "2023-07-31"),
    ("ERK_2023_E03", "2023-09-01"),
    ("ERK_2024_E01", "2024-07-19"),
    ("ERK_2024_E02", "2024-08-31"),
    ("ERK_2025_E01", "2025-03-30"),
    ("ERK_2025_E02", "2025-07-14"),
    ("ERK_2025_E03", "2025-08-28"),
    ("ERK_2025_E04", "2025-10-14"),
)
EXPECTED_YEARLY_COUNTS = {
    2019: 2,
    2020: 3,
    2021: 2,
    2022: 2,
    2023: 3,
    2024: 2,
    2025: 4,
}
EXPECTED_SCALE_DECIMALS = {
    2019: ("28.561548", 6),
    2020: ("21.051459", 6),
    2021: ("22.15631", 5),
    2022: ("16.804815", 6),
    2023: ("10.6621499", 7),
    2024: ("16.3173875", 7),
    2025: ("29.979275", 6),
}
FROZEN_SPLINE_SELECTIONS = {
    2019: 10,
    2020: 100,
    2021: 100,
    2022: 10,
    2023: 10,
    2024: 3,
    2025: 10,
}


class EventProtocolError(ValueError):
    """Raised when a frozen protocol artifact or invariant differs."""


@dataclass(frozen=True)
class CandidateDetectionResult:
    """Reconstruction candidates or an explicit unavailable state."""

    status: str
    failure_reason: str
    candidates: pd.DataFrame


REFERENCE_EVENT_COLUMNS = (
    "event_id",
    "year",
    "event_time",
    "event_date",
    "common_support_segment_id",
    "reference_magnitude",
    "plateau_start_time",
    "plateau_end_time",
    "plateau_size_days",
    "scipy_peak_index_within_segment",
    "scipy_prominence",
    "yearly_q05",
    "yearly_q95",
    "yearly_scale_q95_minus_q05",
    "prominence_threshold",
    "reference_distance_days",
    "reference_prominence_fraction",
    "find_peaks_plateau_size_min",
    "find_peaks_plateau_size_max",
    "preprocessing_applied",
)

RECONSTRUCTION_CANDIDATE_COLUMNS = (
    "candidate_id",
    "year",
    "event_time",
    "event_date",
    "common_support_segment_id",
    "reconstructed_magnitude",
    "plateau_start_time",
    "plateau_end_time",
    "plateau_size_days",
    "scipy_peak_index_within_segment",
    "detection_rule",
    "preprocessing_applied",
)


def _empty_table(columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EventProtocolError(f"Missing seasonal-event config: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EventProtocolError(
            f"Cannot read seasonal-event config {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise EventProtocolError("Seasonal-event config must contain one JSON object.")
    return value


def validate_event_protocol_config(
    config: Mapping[str, Any], *, repository_root: str | Path
) -> None:
    """Fail if a frozen event-protocol rule or parent artifact has changed."""

    root = Path(repository_root)
    expected_payload = config.get("config_payload_sha256")
    actual_payload = canonical_json_payload_sha256(
        config, excluded_keys=("config_payload_sha256",)
    )
    if expected_payload != actual_payload:
        raise EventProtocolError(
            "Seasonal-event config checksum mismatch: "
            f"expected {expected_payload}, found {actual_payload}."
        )
    exact_top = {
        "schema_version": "seasonal_event_protocol_config_v1",
        "protocol_version": PROTOCOL_VERSION,
        "analysis_classification": ANALYSIS_CLASSIFICATION,
        "frozen_before_real_event_level_performance": True,
        "global_peak_policy": (
            "existing_frozen_common_support_global_maximum_metric_unchanged"
        ),
    }
    for key, expected in exact_top.items():
        if config.get(key) != expected:
            raise EventProtocolError(
                f"Frozen event config field {key!r} must equal {expected!r}."
            )

    document = config.get("protocol_document", {})
    document_path = root / str(document.get("path", ""))
    if not document_path.is_file() or sha256_file(document_path) != document.get(
        "sha256"
    ):
        raise EventProtocolError("Frozen seasonal-event protocol document mismatch.")
    parent = config.get("parent_contract", {})
    parent_path = root / str(parent.get("path", ""))
    if (
        parent.get("version") != CONTRACT_VERSION
        or parent.get("unchanged") is not True
        or not parent_path.is_file()
        or sha256_file(parent_path) != parent.get("sha256")
    ):
        raise EventProtocolError(
            "Parent reconstruction contract changed or is missing."
        )

    reference = config.get("reference", {})
    if (
        reference.get("source")
        != "existing_published_daily_erken_chlf_exactly_as_phase3"
        or reference.get("common_support") != "frozen_phase3_common_support"
        or reference.get("scale")
        != {
            "definition": (
                "q95_minus_q05_daily_reference_over_frozen_common_support"
            ),
            "quantile_method": "linear",
        }
    ):
        raise EventProtocolError("Reference source, support, or scale changed.")
    detector = reference.get("major_event_detection", {})
    if detector != {
        "implementation": "scipy.signal.find_peaks",
        "distance_days": REFERENCE_DISTANCE_DAYS,
        "prominence_fraction_of_yearly_scale": REFERENCE_PROMINENCE_FRACTION,
        "plateau_size": [1, None],
        "height": None,
        "width": None,
        "wlen": None,
        "plateau_event_time": (
            "exact_temporal_midpoint_of_left_and_right_plateau_edges"
        ),
        "event_id_format": "ERK_<year>_E<two_digit_chronological_index>",
    }:
        raise EventProtocolError("Reference major-event detector differs from v1.0.")
    expected_events = [
        {"event_id": event_id, "event_time": event_time}
        for event_id, event_time in EXPECTED_EVENT_TIMES
    ]
    if reference.get("expected_events") != expected_events:
        raise EventProtocolError("Frozen reference event regression target changed.")
    if reference.get("expected_total_events") != 18:
        raise EventProtocolError("Frozen total reference-event count must be 18.")
    if reference.get("expected_yearly_counts") != {
        str(year): count for year, count in EXPECTED_YEARLY_COUNTS.items()
    }:
        raise EventProtocolError("Frozen yearly reference-event counts changed.")
    if reference.get("yearly_scale_regression") != {
        str(year): {
            "expected_decimal": decimal,
            "decimal_places": places,
        }
        for year, (decimal, places) in EXPECTED_SCALE_DECIMALS.items()
    }:
        raise EventProtocolError("Frozen yearly reference scales changed.")
    preprocessing = reference.get("preprocessing", {})
    if preprocessing != {
        "smoothing": False,
        "clipping": False,
        "outlier_deletion": False,
        "savitzky_golay": False,
        "loess": False,
        "spline": False,
        "rolling": False,
    }:
        raise EventProtocolError(
            "Reference preprocessing must remain entirely disabled."
        )
    if reference.get("process_disconnected_open_water_segments_separately") is not True:
        raise EventProtocolError("Reference segments must be processed separately.")

    candidates = config.get("reconstruction_candidates", {})
    if (
        candidates.get("implementation") != "scipy.signal.find_peaks"
        or candidates.get("find_peaks_kwargs") != {"plateau_size": [1, None]}
        or candidates.get("smoothing") is not False
        or candidates.get("amplitude_agnostic_detection") is not True
        or candidates.get("magnitude_used_for_identity_or_matching") is not False
        or candidates.get("prominence_role") != "diagnostic_only_if_stored"
        or candidates.get("process_disconnected_open_water_segments_separately")
        is not True
        or any(
            candidates.get(key) is not None
            for key in (
                "minimum_prominence",
                "minimum_height",
                "minimum_distance",
                "minimum_width",
                "wlen",
            )
        )
    ):
        raise EventProtocolError("Reconstruction candidate detector differs from v1.0.")
    matching = config.get("matching", {})
    if (
        matching.get("same_year_required") is not True
        or matching.get("same_common_support_segment_required") is not True
        or matching.get("maximum_absolute_timing_difference_days")
        != MATCH_WINDOW_DAYS
        or matching.get("one_to_one") is not True
        or matching.get("optimization_order")
        != [
            "maximize_number_of_matched_reference_events",
            "minimize_total_absolute_timing_error",
            (
                "lexicographically_earliest_reconstructed_peak_time_sequence_"
                "for_chronological_reference_events"
            ),
        ]
        or matching.get("magnitude_tiebreaker") is not False
        or matching.get("valid_unmatched_status")
        != "missed_no_peak_within_15d"
        or matching.get("failed_or_incomplete_reconstruction_status")
        != "unavailable"
    ):
        raise EventProtocolError("Event matching rules differ from v1.0.")
    metrics = config.get("event_metrics", {})
    if (
        metrics.get("matched")
        != [
            "signed_timing_error_days",
            "absolute_timing_error_days",
            "success_5d",
            "success_10d",
            "success_15d",
            "reference_magnitude",
            "reconstructed_magnitude",
            "signed_magnitude_error",
            "absolute_magnitude_error",
            "normalized_absolute_magnitude_error",
        ]
        or metrics.get("main_event_timing_threshold_days") != 10
        or metrics.get("sensitivity_threshold_days") != [5, 15]
        or metrics.get("magnitude_independent_of_identity_and_matching") is not True
        or metrics.get("excluded_headline_metrics")
        != [
            "extra_reconstructed_peak_count",
            "false_positive_bloom_rate",
            "reconstructed_peak_count_accuracy",
            "spring_vs_summer_dominance_classification",
        ]
    ):
        raise EventProtocolError("Event metric thresholds differ from v1.0.")
    if config.get("frozen_actual_mask_spline_selections") != {
        str(year): smoothing for year, smoothing in FROZEN_SPLINE_SELECTIONS.items()
    }:
        raise EventProtocolError("Frozen actual-mask spline selections changed.")
    if config.get("non_interference") != {
        "retune_spline": False,
        "change_timesat_defaults": False,
        "change_masks": False,
        "change_common_support": False,
        "change_primary_metrics": False,
    }:
        raise EventProtocolError("Event-analysis non-interference rules changed.")
    if config.get("task_stop_boundary") != {
        "real_reconstruction_event_performance": False,
        "controlled_gap_performance": False,
        "vombsjon": False,
        "method_ranking": False,
        "interpretive_figures": False,
    }:
        raise EventProtocolError("Event-analysis task stop boundary changed.")


def load_event_protocol_config(
    repository_root: str | Path,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Load and verify the self-checking machine-readable event protocol."""

    root = Path(repository_root)
    config_path = (
        Path(path)
        if path is not None
        else root / "config" / "seasonal_event_protocol_v1.0.json"
    )
    config = _read_json(config_path)
    validate_event_protocol_config(config, repository_root=root)
    return config


def validate_parent_actual_mask_benchmark(
    config: Mapping[str, Any], *, repository_root: str | Path
) -> dict[str, Any]:
    """Verify parent benchmark bytes without reading its performance values."""

    root = Path(repository_root)
    parent = config["parent_actual_mask_benchmark"]
    manifest_path = root / parent["manifest_path"]
    if sha256_file(manifest_path) != parent["manifest_file_sha256"]:
        raise EventProtocolError("Parent actual-mask benchmark manifest changed.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_payload_sha256") != parent["manifest_payload_sha256"]:
        raise EventProtocolError("Parent benchmark payload identity changed.")
    if manifest.get("table_sha256") != parent["table_sha256"]:
        raise EventProtocolError("Parent benchmark table manifest changed.")
    for filename, expected_hash in parent["table_sha256"].items():
        if sha256_file(manifest_path.parent / filename) != expected_hash:
            raise EventProtocolError(f"Parent benchmark table changed: {filename}")
    return {
        "parent_actual_mask_benchmark_unchanged": True,
        "parent_manifest_payload_sha256": parent["manifest_payload_sha256"],
    }


def _eligible_support(data: pd.DataFrame) -> pd.DataFrame:
    required = {
        "date",
        "year",
        "CHLF",
        "common_support",
        "reference_value_available",
        "common_support_segment_id",
    }
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"Event support table lacks columns: {missing}")
    support = data.loc[data["common_support"]].copy()
    support["date"] = pd.to_datetime(support["date"], errors="raise").dt.normalize()
    support["year"] = pd.to_numeric(support["year"], errors="raise").astype(int)
    support["CHLF"] = pd.to_numeric(support["CHLF"], errors="coerce")
    if support["date"].duplicated().any():
        raise ValueError("Event support dates must be unique.")
    if not support["reference_value_available"].all() or not np.isfinite(
        support["CHLF"].to_numpy(dtype=float)
    ).all():
        raise ValueError("Reference event support must contain finite CHLF values.")
    if support["common_support_segment_id"].isna().any():
        raise ValueError("Every event support date needs a physical segment ID.")
    return support.sort_values(["year", "date"], kind="mergesort").reset_index(
        drop=True
    )


def _validate_daily_segment(segment: pd.DataFrame) -> None:
    ordered = segment.sort_values("date")
    if len(ordered) > 1 and not ordered["date"].diff().dropna().dt.days.eq(1).all():
        raise ValueError("Event detection segment is not daily and contiguous.")


def detect_reference_major_events(common_support: pd.DataFrame) -> pd.DataFrame:
    """Detect raw-reference major events under the exact frozen SciPy call."""

    support = _eligible_support(common_support)
    rows: list[dict[str, Any]] = []
    for year, year_data in support.groupby("year", sort=True):
        scale = robust_reference_scale(year_data["CHLF"])
        if not scale["scale_available"]:
            raise EventProtocolError(
                f"Reference event scale is unavailable for {year}: "
                f"{scale['scale_unavailable_reason']}"
            )
        threshold = REFERENCE_PROMINENCE_FRACTION * float(scale["scale"])
        for segment_id, segment in year_data.groupby(
            "common_support_segment_id", sort=True
        ):
            segment = segment.sort_values("date").reset_index(drop=True)
            _validate_daily_segment(segment)
            values = segment["CHLF"].to_numpy(dtype=float)
            peaks, properties = find_peaks(
                values,
                distance=REFERENCE_DISTANCE_DAYS,
                prominence=threshold,
                plateau_size=PLATEAU_SIZE,
            )
            for position, peak_index in enumerate(peaks):
                left_index = int(properties["left_edges"][position])
                right_index = int(properties["right_edges"][position])
                plateau_start = segment.loc[left_index, "date"]
                plateau_end = segment.loc[right_index, "date"]
                event_time = plateau_start + (plateau_end - plateau_start) / 2
                rows.append(
                    {
                        "year": int(year),
                        "event_time": event_time,
                        "event_date": event_time.strftime("%Y-%m-%d"),
                        "common_support_segment_id": str(segment_id),
                        "reference_magnitude": float(values[int(peak_index)]),
                        "plateau_start_time": plateau_start,
                        "plateau_end_time": plateau_end,
                        "plateau_size_days": int(
                            properties["plateau_sizes"][position]
                        ),
                        "scipy_peak_index_within_segment": int(peak_index),
                        "scipy_prominence": float(properties["prominences"][position]),
                        "yearly_q05": float(scale["q05"]),
                        "yearly_q95": float(scale["q95"]),
                        "yearly_scale_q95_minus_q05": float(scale["scale"]),
                        "prominence_threshold": threshold,
                        "reference_distance_days": REFERENCE_DISTANCE_DAYS,
                        "reference_prominence_fraction": (
                            REFERENCE_PROMINENCE_FRACTION
                        ),
                        "find_peaks_plateau_size_min": 1,
                        "find_peaks_plateau_size_max": pd.NA,
                        "preprocessing_applied": "none",
                    }
                )
    if not rows:
        return _empty_table(REFERENCE_EVENT_COLUMNS)
    events = pd.DataFrame(rows).sort_values(
        ["year", "event_time"], kind="mergesort"
    )
    events.insert(
        0,
        "event_id",
        [
            f"ERK_{int(year)}_E{int(index):02d}"
            for year, index in zip(
                events["year"],
                events.groupby("year", sort=False).cumcount() + 1,
                strict=True,
            )
        ],
    )
    return events.loc[:, REFERENCE_EVENT_COLUMNS].reset_index(drop=True)


def _prediction_series(prediction: pd.DataFrame | pd.Series) -> pd.Series:
    if isinstance(prediction, pd.Series):
        result = prediction.copy()
        if not isinstance(result.index, pd.DatetimeIndex):
            raise ValueError("Prediction Series must have a DatetimeIndex.")
        result.index = result.index.normalize()
    else:
        missing = sorted({"date", "prediction"} - set(prediction.columns))
        if missing:
            raise ValueError(f"Prediction table lacks columns: {missing}")
        dates = pd.to_datetime(prediction["date"], errors="raise").dt.normalize()
        result = pd.Series(
            pd.to_numeric(prediction["prediction"], errors="coerce").to_numpy(),
            index=dates,
            name="prediction",
        )
    if result.index.duplicated().any():
        raise ValueError("Prediction dates must be unique.")
    return result.sort_index()


def detect_reconstruction_peak_candidates(
    year_support: pd.DataFrame,
    prediction: pd.DataFrame | pd.Series,
    *,
    reconstruction_status: str = "ok",
    failure_reason: str = "",
) -> CandidateDetectionResult:
    """Detect amplitude-agnostic candidates; intended for synthetic tests here."""

    if reconstruction_status != "ok":
        return CandidateDetectionResult(
            "unavailable",
            failure_reason or "reconstruction_failed",
            _empty_table(RECONSTRUCTION_CANDIDATE_COLUMNS),
        )
    support = _eligible_support(year_support)
    years = support["year"].unique()
    if len(years) != 1:
        raise ValueError("Reconstruction candidate detection requires one year.")
    pred = _prediction_series(prediction)
    support["prediction"] = support["date"].map(pred)
    finite = support["prediction"].notna() & np.isfinite(
        support["prediction"].to_numpy(dtype=float)
    )
    if not finite.all():
        return CandidateDetectionResult(
            "unavailable",
            "required_common_support_prediction_incomplete",
            _empty_table(RECONSTRUCTION_CANDIDATE_COLUMNS),
        )
    rows: list[dict[str, Any]] = []
    year = int(years[0])
    for segment_id, segment in support.groupby(
        "common_support_segment_id", sort=True
    ):
        segment = segment.sort_values("date").reset_index(drop=True)
        _validate_daily_segment(segment)
        values = segment["prediction"].to_numpy(dtype=float)
        peaks, properties = find_peaks(values, plateau_size=PLATEAU_SIZE)
        for position, peak_index in enumerate(peaks):
            left_index = int(properties["left_edges"][position])
            right_index = int(properties["right_edges"][position])
            plateau_start = segment.loc[left_index, "date"]
            plateau_end = segment.loc[right_index, "date"]
            event_time = plateau_start + (plateau_end - plateau_start) / 2
            rows.append(
                {
                    "year": year,
                    "event_time": event_time,
                    "event_date": event_time.strftime("%Y-%m-%d"),
                    "common_support_segment_id": str(segment_id),
                    "reconstructed_magnitude": float(values[int(peak_index)]),
                    "plateau_start_time": plateau_start,
                    "plateau_end_time": plateau_end,
                    "plateau_size_days": int(properties["plateau_sizes"][position]),
                    "scipy_peak_index_within_segment": int(peak_index),
                    "detection_rule": "find_peaks_plateau_size_only",
                    "preprocessing_applied": "none",
                }
            )
    if not rows:
        candidates = _empty_table(RECONSTRUCTION_CANDIDATE_COLUMNS)
    else:
        candidates = pd.DataFrame(rows).sort_values(
            ["year", "event_time"], kind="mergesort"
        )
        candidates.insert(
            0,
            "candidate_id",
            [f"REC_{year}_P{index:03d}" for index in range(1, len(candidates) + 1)],
        )
        candidates = candidates.loc[:, RECONSTRUCTION_CANDIDATE_COLUMNS].reset_index(
            drop=True
        )
    return CandidateDetectionResult("ok", "", candidates)


def _optimal_ordered_matches(
    reference_times: tuple[pd.Timestamp, ...],
    candidate_times: tuple[pd.Timestamp, ...],
) -> tuple[tuple[int, int], ...]:
    """Solve the frozen lexicographic one-to-one timing objective."""

    max_delta_ns = int(pd.Timedelta(days=MATCH_WINDOW_DAYS).value)

    def key(pairs: tuple[tuple[int, int], ...]) -> tuple[Any, ...]:
        total_error = sum(
            abs(reference_times[i].value - candidate_times[j].value)
            for i, j in pairs
        )
        reconstructed_sequence = tuple(candidate_times[j].value for _, j in pairs)
        reference_sequence = tuple(reference_times[i].value for i, _ in pairs)
        return (-len(pairs), total_error, reconstructed_sequence, reference_sequence)

    @lru_cache(maxsize=None)
    def solve(i: int, j: int) -> tuple[tuple[int, int], ...]:
        if i >= len(reference_times) or j >= len(candidate_times):
            return ()
        options = [solve(i + 1, j), solve(i, j + 1)]
        if abs(reference_times[i].value - candidate_times[j].value) <= max_delta_ns:
            options.append(((i, j),) + solve(i + 1, j + 1))
        return min(options, key=key)

    return solve(0, 0)


def match_reference_events(
    reference_events: pd.DataFrame,
    reconstruction_candidates: pd.DataFrame,
    *,
    reconstruction_status: str = "ok",
    failure_reason: str = "",
) -> pd.DataFrame:
    """Match candidates to references without using magnitude or prominence."""

    required_reference = {
        "event_id",
        "year",
        "event_time",
        "common_support_segment_id",
        "reference_magnitude",
        "yearly_scale_q95_minus_q05",
    }
    missing = sorted(required_reference - set(reference_events.columns))
    if missing:
        raise ValueError(f"Reference event table lacks columns: {missing}")
    references = reference_events.copy()
    references["event_time"] = pd.to_datetime(references["event_time"], errors="raise")
    references = references.sort_values(["year", "event_time"], kind="mergesort")
    candidate_required = {
        "candidate_id",
        "year",
        "event_time",
        "common_support_segment_id",
        "reconstructed_magnitude",
    }
    if reconstruction_status == "ok":
        candidate_missing = sorted(
            candidate_required - set(reconstruction_candidates.columns)
        )
        if candidate_missing:
            raise ValueError(
                f"Reconstruction candidate table lacks columns: {candidate_missing}"
            )
    candidates = reconstruction_candidates.copy()
    if "event_time" in candidates:
        candidates["event_time"] = pd.to_datetime(
            candidates["event_time"], errors="raise"
        )
    rows: list[dict[str, Any]] = []

    if reconstruction_status != "ok":
        reason = failure_reason or "reconstruction_failed_or_support_incomplete"
        for reference in references.itertuples(index=False):
            rows.append(_event_metric_row(reference, None, "unavailable", reason))
        return pd.DataFrame(rows)

    matched_candidate_by_event: dict[str, pd.Series] = {}
    for (year, segment_id), group in references.groupby(
        ["year", "common_support_segment_id"], sort=True
    ):
        reference_group = group.sort_values("event_time").reset_index(drop=True)
        candidate_group = candidates.loc[
            candidates["year"].eq(year)
            & candidates["common_support_segment_id"].astype(str).eq(str(segment_id))
        ].sort_values("event_time").reset_index(drop=True)
        pairs = _optimal_ordered_matches(
            tuple(reference_group["event_time"]),
            tuple(candidate_group["event_time"]),
        )
        for reference_index, candidate_index in pairs:
            event_id = str(reference_group.loc[reference_index, "event_id"])
            matched_candidate_by_event[event_id] = candidate_group.loc[candidate_index]

    for reference in references.itertuples(index=False):
        candidate = matched_candidate_by_event.get(str(reference.event_id))
        if candidate is None:
            rows.append(
                _event_metric_row(
                    reference,
                    None,
                    "missed_no_peak_within_15d",
                    "",
                )
            )
        else:
            rows.append(_event_metric_row(reference, candidate, "matched", ""))
    return pd.DataFrame(rows)


def match_detected_reconstruction_events(
    reference_events: pd.DataFrame,
    detection: CandidateDetectionResult,
) -> pd.DataFrame:
    """Match while preserving a failed/incomplete candidate-detection state."""

    return match_reference_events(
        reference_events,
        detection.candidates,
        reconstruction_status=detection.status,
        failure_reason=detection.failure_reason,
    )


def _event_metric_row(
    reference: Any,
    candidate: pd.Series | None,
    event_status: str,
    unavailable_reason: str,
) -> dict[str, Any]:
    reference_time = pd.Timestamp(reference.event_time)
    reference_magnitude = float(reference.reference_magnitude)
    scale = float(reference.yearly_scale_q95_minus_q05)
    base: dict[str, Any] = {
        "event_id": str(reference.event_id),
        "year": int(reference.year),
        "common_support_segment_id": str(reference.common_support_segment_id),
        "reference_event_time": reference_time,
        "reference_magnitude": reference_magnitude,
        "yearly_scale_q95_minus_q05": scale,
        "event_status": event_status,
        "event_unavailable_reason": unavailable_reason,
        "matching_window_days": MATCH_WINDOW_DAYS,
        "magnitude_used_for_matching": False,
    }
    if event_status == "unavailable":
        return {
            **base,
            "matched_candidate_id": pd.NA,
            "reconstructed_event_time": pd.NaT,
            "signed_timing_error_days": np.nan,
            "absolute_timing_error_days": np.nan,
            "success_5d": pd.NA,
            "success_10d": pd.NA,
            "success_15d": pd.NA,
            "reconstructed_magnitude": np.nan,
            "signed_magnitude_error": np.nan,
            "absolute_magnitude_error": np.nan,
            "normalized_absolute_magnitude_error": np.nan,
            "magnitude_metric_status": "unavailable",
            "magnitude_metric_reason": unavailable_reason,
        }
    if candidate is None:
        return {
            **base,
            "matched_candidate_id": pd.NA,
            "reconstructed_event_time": pd.NaT,
            "signed_timing_error_days": np.nan,
            "absolute_timing_error_days": np.nan,
            "success_5d": False,
            "success_10d": False,
            "success_15d": False,
            "reconstructed_magnitude": np.nan,
            "signed_magnitude_error": np.nan,
            "absolute_magnitude_error": np.nan,
            "normalized_absolute_magnitude_error": np.nan,
            "magnitude_metric_status": "unavailable",
            "magnitude_metric_reason": "no_matched_reconstruction_event",
        }
    candidate_time = pd.Timestamp(candidate["event_time"])
    signed_days = (candidate_time - reference_time).total_seconds() / 86400
    absolute_days = abs(signed_days)
    reconstructed_magnitude = float(candidate["reconstructed_magnitude"])
    signed_magnitude = reconstructed_magnitude - reference_magnitude
    scale_valid = bool(np.isfinite(scale) and scale > 0)
    return {
        **base,
        "matched_candidate_id": str(candidate["candidate_id"]),
        "reconstructed_event_time": candidate_time,
        "signed_timing_error_days": float(signed_days),
        "absolute_timing_error_days": float(absolute_days),
        "success_5d": bool(absolute_days <= 5),
        "success_10d": bool(absolute_days <= 10),
        "success_15d": bool(absolute_days <= 15),
        "reconstructed_magnitude": reconstructed_magnitude,
        "signed_magnitude_error": float(signed_magnitude),
        "absolute_magnitude_error": float(abs(signed_magnitude)),
        "normalized_absolute_magnitude_error": (
            float(abs(signed_magnitude) / scale) if scale_valid else np.nan
        ),
        "magnitude_metric_status": "ok" if scale_valid else "unavailable",
        "magnitude_metric_reason": "" if scale_valid else "yearly_scale_invalid",
    }
