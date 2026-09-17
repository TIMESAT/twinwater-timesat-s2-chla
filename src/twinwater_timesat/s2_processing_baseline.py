"""Sentinel-2 processing-baseline provenance and harmonization gate."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import re
import statistics
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml


DEFAULT_CONFIG_RELATIVE_PATH = (
    "config/erken_s2_processing_baseline_control_v1.0.yaml"
)
EXPECTED_SCHEMA_VERSION = "erken_s2_processing_baseline_control_config_v1"
EXPECTED_CONTROL_VERSION = "erken_s2_processing_baseline_control_v1.0"
EXPECTED_METHODS = ("L1C", "L2A", "ACOLITE")
EXPECTED_BANDS = ("B4", "B5", "B6")
PRODUCT_ID_PATTERN = re.compile(
    r"^(?P<platform>S2[A-Z])_MSI(?P<level>L1C|L2A)_"
    r"(?P<sensing>\d{8}T\d{6})_(?P<baseline>N\d{4})_"
    r"(?P<orbit>R\d{3})_(?P<tile>T[A-Z0-9]{5})_"
    r"(?P<generation>\d{8}T\d{6})$"
)


class ProcessingBaselineError(RuntimeError):
    """Raised when the processing-baseline audit cannot be reproduced."""


@dataclass(frozen=True)
class ProcessingBaselineConfig:
    values: Mapping[str, Any]
    source_relative_path: str
    sha256: str

    @property
    def control_version(self) -> str:
        return str(self.values["control_version"])


@dataclass(frozen=True)
class ProductIdentity:
    product_id: str
    platform: str
    level: str
    sensing_datetime: str
    processing_baseline: str
    relative_orbit: str
    tile: str
    generation_time: str

    @property
    def acquisition_identity(self) -> str:
        return "|".join(
            (
                self.platform,
                self.sensing_datetime,
                self.relative_orbit,
                self.tile,
            )
        )


@dataclass(frozen=True)
class ProcessingBaselineResult:
    observation_audit: tuple[dict[str, Any], ...]
    acquisition_inventory: tuple[dict[str, Any], ...]
    reflectance_summary: tuple[dict[str, Any], ...]
    input_paths: Mapping[str, Path]
    counts: Mapping[str, Any]
    phase6c_hash_check: Mapping[str, Any]
    gate_status: str


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_config_path(repository_root: str | Path) -> Path:
    return Path(repository_root) / DEFAULT_CONFIG_RELATIVE_PATH


def load_processing_baseline_config(
    path: str | Path, *, repository_root: str | Path | None = None
) -> ProcessingBaselineConfig:
    source = Path(path)
    if not source.is_file():
        raise ProcessingBaselineError(
            f"Processing-baseline configuration not found: {source}"
        )
    with source.open(encoding="utf-8") as handle:
        values = yaml.safe_load(handle)
    if not isinstance(values, Mapping):
        raise ProcessingBaselineError(
            "Processing-baseline configuration must be a YAML mapping."
        )
    required = {
        "inputs",
        "scope",
        "processing_baseline",
        "radiometry",
        "harmonization_gate",
        "scientific_guards",
        "outputs",
    }
    missing = sorted(required - set(values))
    if missing:
        raise ProcessingBaselineError(f"Configuration is missing: {missing}")
    if values.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise ProcessingBaselineError("Unexpected configuration schema version.")
    if values.get("control_version") != EXPECTED_CONTROL_VERSION:
        raise ProcessingBaselineError("Unexpected processing-baseline version.")
    if values.get("status") != "FROZEN_BEFORE_BASELINE_AUDIT":
        raise ProcessingBaselineError("Configuration must be frozen before audit.")
    scope = values["scope"]
    if tuple(scope.get("methods", ())) != EXPECTED_METHODS:
        raise ProcessingBaselineError(
            f"Methods must remain exactly {EXPECTED_METHODS}."
        )
    if tuple(scope.get("bands", ())) != EXPECTED_BANDS:
        raise ProcessingBaselineError(f"Bands must remain exactly {EXPECTED_BANDS}.")
    if int(scope.get("primary_window_size", -1)) != 3:
        raise ProcessingBaselineError("Primary support must remain the 3x3 window.")
    if int(scope.get("grid_resolution_m", -1)) != 20:
        raise ProcessingBaselineError("Analysis grid must remain 20 m.")
    if scope.get("mix_reflectance_quantities_for_harmonization") is not False:
        raise ProcessingBaselineError(
            "TOA, BOA and ACOLITE rhos must not be mixed for harmonization."
        )
    baseline = values["processing_baseline"]
    if baseline.get("required_for_available_product") is not True:
        raise ProcessingBaselineError("Available products must retain a baseline.")
    if baseline.get("exact_l1c_l2a_pair_must_share_baseline") is not True:
        raise ProcessingBaselineError("Exact L1C/L2A pairs must share a baseline.")
    gate = values["harmonization_gate"]
    if gate.get("empirical_correction_allowed") is not False:
        raise ProcessingBaselineError(
            "Empirical correction must remain forbidden in this audit."
        )
    if gate.get("same_acquisition_cross_baseline_pairs_required") is not True:
        raise ProcessingBaselineError(
            "Same-acquisition cross-baseline pairs must remain required."
        )
    if gate.get("response_or_chlf_may_define_correction") is not False:
        raise ProcessingBaselineError("CHLF must not define baseline correction.")
    guards = values["scientific_guards"]
    if guards.get("chlf_read") is not False:
        raise ProcessingBaselineError("The baseline audit must not read CHLF.")
    forbidden = [
        key
        for key in (
            "processor_ranking_authorized",
            "reconstruction_authorized",
            "timesat_authorized",
            "vombsjon_access_authorized",
        )
        if guards.get(key) is not False
    ]
    if forbidden:
        raise ProcessingBaselineError(f"Forbidden authorization(s): {forbidden}")

    relative = source.name
    if repository_root is not None:
        try:
            relative = source.resolve().relative_to(
                Path(repository_root).resolve()
            ).as_posix()
        except ValueError:
            pass
    return ProcessingBaselineConfig(values, relative, sha256_file(source))


def parse_product_identity(product_id: str) -> ProductIdentity:
    match = PRODUCT_ID_PATTERN.fullmatch(str(product_id).strip().upper())
    if match is None:
        raise ProcessingBaselineError(
            f"Cannot parse Sentinel-2 compact product identifier: {product_id!r}"
        )
    values = match.groupdict()
    return ProductIdentity(
        product_id=str(product_id).strip(),
        platform=values["platform"],
        level=values["level"],
        sensing_datetime=_compact_datetime(values["sensing"]),
        processing_baseline=values["baseline"],
        relative_orbit=values["orbit"],
        tile=values["tile"],
        generation_time=_compact_datetime(values["generation"]),
    )


def _compact_datetime(value: str) -> str:
    parsed = datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")


def _datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _bool(value: Any) -> bool | None:
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ProcessingBaselineError(f"Required input not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def generation_lag_days(
    sensing_datetime: Any, generation_time: Any
) -> float | None:
    sensing = _datetime(sensing_datetime)
    generated = _datetime(generation_time)
    if sensing is None or generated is None:
        return None
    return (generated - sensing).total_seconds() / 86400.0


def generation_context(
    lag_days: float | None, config: ProcessingBaselineConfig
) -> str:
    settings = config.values["processing_baseline"]["generation_context"]
    labels = settings["labels"]
    if lag_days is None:
        return str(labels["unavailable"])
    if lag_days <= float(settings["near_sensing_max_days"]):
        return str(labels["near_sensing"])
    return str(labels["delayed"])


def official_product_context(
    *,
    processing_baseline: str,
    sensing_datetime: str,
    generation_context_label: str,
    config: ProcessingBaselineConfig,
) -> str:
    acquired = _datetime(sensing_datetime)
    if acquired is None:
        return "official_product_context_unavailable"
    acquired_date = acquired.date()
    baseline_settings = config.values["processing_baseline"]
    deployment = baseline_settings["operational_deployment_dates"].get(
        processing_baseline
    )
    if (
        deployment
        and acquired_date >= date.fromisoformat(str(deployment))
        and generation_context_label == "near_sensing_generation"
    ):
        return "nominal_operational"
    window = baseline_settings["official_collection1_windows"].get(
        processing_baseline
    )
    if window:
        first = date.fromisoformat(str(window["first_acquisition_date"]))
        last = date.fromisoformat(str(window["last_acquisition_date"]))
        if first <= acquired_date <= last:
            return "collection1_historical_reprocessed"
    if generation_context_label == "near_sensing_generation":
        return "other_nominal_operational"
    if generation_context_label == "delayed_generation":
        return "other_delayed_generation"
    return "official_product_context_unavailable"


def _window_index(
    rows: Sequence[Mapping[str, str]],
    *,
    key_column: str,
    primary_window_size: int,
    label: str,
) -> dict[str, Mapping[str, str]]:
    result: dict[str, Mapping[str, str]] = {}
    for row in rows:
        if int(float(row.get("window_size") or -1)) != primary_window_size:
            continue
        key = str(row.get(key_column, "")).strip()
        if not key:
            continue
        if key in result:
            raise ProcessingBaselineError(f"Duplicate {label} 3x3 product: {key}")
        result[key] = row
    return result


def build_acquisition_inventory(
    rows: Sequence[Mapping[str, str]], config: ProcessingBaselineConfig
) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for source in sorted(rows, key=lambda row: str(row.get("source_l1c_product_id"))):
        product_id = str(source.get("source_l1c_product_id", "")).strip()
        identity = parse_product_identity(product_id)
        lag = generation_lag_days(
            identity.sensing_datetime, identity.generation_time
        )
        generation = generation_context(lag, config)
        inventory.append(
            {
                "control_version": config.control_version,
                "source_l1c_product_id": product_id,
                "platform": identity.platform,
                "sensing_datetime": identity.sensing_datetime,
                "relative_orbit": identity.relative_orbit,
                "tile": identity.tile,
                "acquisition_identity": identity.acquisition_identity,
                "processing_baseline": identity.processing_baseline,
                "generation_time": identity.generation_time,
                "generation_lag_days": lag,
                "generation_context": generation,
                "official_product_context": official_product_context(
                    processing_baseline=identity.processing_baseline,
                    sensing_datetime=identity.sensing_datetime,
                    generation_context_label=generation,
                    config=config,
                ),
                "phase6a_exact_pair_eligible": _bool(
                    source.get("phase6a_exact_pair_eligible")
                ),
                "rhos_geotiff_count": int(
                    float(source.get("rhos_geotiff_count") or 0)
                ),
            }
        )
    by_acquisition: dict[str, list[dict[str, Any]]] = {}
    for row in inventory:
        by_acquisition.setdefault(row["acquisition_identity"], []).append(row)
    for members in by_acquisition.values():
        baselines = sorted({str(row["processing_baseline"]) for row in members})
        if len(baselines) > 1:
            duplicate_status = "cross_baseline_duplicate"
        elif len(members) > 1:
            duplicate_status = "same_baseline_duplicate"
        else:
            duplicate_status = "unique_acquisition"
        products = ";".join(sorted(str(row["source_l1c_product_id"]) for row in members))
        for row in members:
            row["acquisition_product_count"] = len(members)
            row["acquisition_distinct_baseline_count"] = len(baselines)
            row["acquisition_baselines"] = ";".join(baselines)
            row["acquisition_product_ids"] = products
            row["acquisition_duplicate_status"] = duplicate_status
    return inventory


def _metadata_radiometry_status(
    method: str, source: Mapping[str, str]
) -> str:
    if method == "ACOLITE":
        scales = [_float(source.get(f"{band}_geotiff_scale")) for band in EXPECTED_BANDS]
        offsets = [_float(source.get(f"{band}_geotiff_offset")) for band in EXPECTED_BANDS]
        if all(value is not None for value in scales + offsets):
            return "acolite_geotiff_scale_offset_applied_source_l1c_baseline_recorded"
        return "acolite_geotiff_scale_offset_unavailable"
    baseline = str(source.get("processing_baseline", "")).strip()
    radiometry_baseline = str(
        source.get("radiometry_processing_baseline", "")
    ).strip()
    if baseline != radiometry_baseline:
        return "failed_radiometry_baseline_mismatch"
    if _bool(source.get("radiometry_offset_expected_for_baseline")) is not True:
        return "failed_offset_not_expected_for_n0400_or_later"
    for band in EXPECTED_BANDS:
        if str(source.get(f"{band}_offset_source", "")) != "product_offset_list":
            return f"failed_{band.lower()}_product_offset_not_used"
        if _float(source.get(f"{band}_add_offset")) is None:
            return f"failed_{band.lower()}_offset_unavailable"
        rule = str(source.get(f"{band}_conversion_rule", ""))
        if not rule.startswith("(DN + ") or "/" not in rule:
            return f"failed_{band.lower()}_conversion_rule_unavailable"
    return "metadata_derived_offset_and_quantification_applied"


def build_observation_audit(
    selection_rows: Sequence[Mapping[str, str]],
    phase6a_window_rows: Sequence[Mapping[str, str]],
    acolite_window_rows: Sequence[Mapping[str, str]],
    config: ProcessingBaselineConfig,
) -> list[dict[str, Any]]:
    primary_window_size = int(config.values["scope"]["primary_window_size"])
    phase6a = _window_index(
        phase6a_window_rows,
        key_column="product_id",
        primary_window_size=primary_window_size,
        label="Phase 6A",
    )
    acolite = _window_index(
        acolite_window_rows,
        key_column="source_l1c_product_id",
        primary_window_size=primary_window_size,
        label="ACOLITE",
    )
    by_date: dict[str, dict[str, Mapping[str, str]]] = {}
    for row in selection_rows:
        method = str(row.get("observation_method", ""))
        if method not in EXPECTED_METHODS:
            raise ProcessingBaselineError(f"Unexpected observation method: {method}")
        date_key = str(row.get("date", ""))
        if method in by_date.setdefault(date_key, {}):
            raise ProcessingBaselineError(
                f"Duplicate selection key: {(date_key, method)}"
            )
        by_date[date_key][method] = row

    pair_status: dict[str, str] = {}
    for date_key, methods in by_date.items():
        if set(methods) != set(EXPECTED_METHODS):
            raise ProcessingBaselineError(
                f"Date {date_key} does not contain all governed methods."
            )
        exact = all(
            _bool(row.get("exact_three_method_source_alignment")) is True
            for row in methods.values()
        )
        if not exact:
            pair_status[date_key] = "not_applicable_not_exact_three_method_alignment"
            continue
        identities = {
            method: parse_product_identity(str(row.get("source_product_id", "")))
            for method, row in methods.items()
        }
        l1c = identities["L1C"]
        l2a = identities["L2A"]
        acolite_identity = identities["ACOLITE"]
        if l1c.acquisition_identity != l2a.acquisition_identity:
            raise ProcessingBaselineError(
                f"Exact pair acquisition identity mismatch on {date_key}."
            )
        if l1c.processing_baseline != l2a.processing_baseline:
            raise ProcessingBaselineError(
                "Exact L1C/L2A processing-baseline mismatch on "
                f"{date_key}: {l1c.processing_baseline} vs "
                f"{l2a.processing_baseline}."
            )
        if acolite_identity.product_id != l1c.product_id:
            raise ProcessingBaselineError(
                f"ACOLITE does not inherit the exact source L1C on {date_key}."
            )
        pair_status[date_key] = "exact_pair_same_processing_baseline"

    audit: list[dict[str, Any]] = []
    reflectance_quantities = config.values["scope"]["reflectance_quantities"]
    for selection in sorted(
        selection_rows,
        key=lambda row: (
            str(row["date"]),
            EXPECTED_METHODS.index(str(row["observation_method"])),
        ),
    ):
        method = str(selection["observation_method"])
        product_available = _bool(selection.get("method_product_available")) is True
        product_id = str(selection.get("source_product_id", "")).strip()
        identity = parse_product_identity(product_id) if product_available else None
        if product_available:
            source = (acolite if method == "ACOLITE" else phase6a).get(product_id)
            if source is None:
                raise ProcessingBaselineError(
                    f"Available {method} product lacks a 3x3 reflectance row: {product_id}"
                )
            source_baseline = str(source.get("processing_baseline", "")).strip()
            if source_baseline != identity.processing_baseline:
                raise ProcessingBaselineError(
                    f"{method} baseline disagrees with product ID for {product_id}: "
                    f"{source_baseline!r} vs {identity.processing_baseline!r}."
                )
            sensing = str(source.get("sensing_datetime") or identity.sensing_datetime)
            generated = str(source.get("generation_time") or identity.generation_time)
            lag = generation_lag_days(sensing, generated)
            generation = generation_context(lag, config)
            official_context = official_product_context(
                processing_baseline=identity.processing_baseline,
                sensing_datetime=sensing,
                generation_context_label=generation,
                config=config,
            )
            radiometry_status = _metadata_radiometry_status(method, source)
        else:
            source = {}
            sensing = generated = ""
            lag = None
            generation = "generation_context_unavailable"
            official_context = "official_product_context_unavailable"
            radiometry_status = "unavailable_no_method_product"

        output: dict[str, Any] = {
            "control_version": config.control_version,
            "date": selection["date"],
            "year": int(selection["year"]),
            "observation_method": method,
            "product_level": selection.get("product_level"),
            "reflectance_quantity": reflectance_quantities[method],
            "source_product_id": product_id or None,
            "method_product_available": product_available,
            "exact_three_method_source_alignment": _bool(
                selection.get("exact_three_method_source_alignment")
            ),
            "processing_baseline": (
                identity.processing_baseline if identity is not None else None
            ),
            "sensing_datetime": sensing or None,
            "generation_time": generated or None,
            "generation_lag_days": lag,
            "generation_context": generation,
            "official_product_context": official_context,
            "l1c_l2a_baseline_pair_status": pair_status[str(selection["date"])],
            "radiometric_conversion_status": radiometry_status,
            "empirical_cross_baseline_correction_applied": False,
            "source_failure_reason": selection.get("source_failure_reason") or None,
            "ndci_observation_eligible": _bool(
                selection.get("ndci_observation_eligible")
            ),
            "mci_observation_eligible": _bool(
                selection.get("mci_observation_eligible")
            ),
            "common_b456_observation_eligible": _bool(
                selection.get("common_b456_observation_eligible")
            ),
        }
        complete = True
        for band in EXPECTED_BANDS:
            for suffix in (
                "valid_pixel_count",
                "valid_pixel_fraction",
                "median",
                "mean",
                "SD",
                "IQR",
                "min",
                "max",
            ):
                key = f"{band}_reflectance_{suffix}"
                output[key] = _float(source.get(key))
            if output[f"{band}_reflectance_median"] is None:
                complete = False
        output["b4_b5_b6_reflectance_summary_complete"] = complete
        audit.append(output)
    return audit


def build_reflectance_summary(
    audit_rows: Sequence[Mapping[str, Any]], config: ProcessingBaselineConfig
) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    groups: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for row in audit_rows:
        if row.get("method_product_available") is not True:
            continue
        for band in EXPECTED_BANDS:
            groups.setdefault(
                (
                    str(row["observation_method"]),
                    str(row["processing_baseline"]),
                    str(row["official_product_context"]),
                    band,
                ),
                [],
            ).append(row)
    for key in sorted(groups):
        method, baseline, product_context, band = key
        members = groups[key]
        medians = [
            float(row[f"{band}_reflectance_median"])
            for row in members
            if _float(row.get(f"{band}_reflectance_median")) is not None
        ]
        valid_counts = [
            float(row[f"{band}_reflectance_valid_pixel_count"])
            for row in members
            if _float(row.get(f"{band}_reflectance_valid_pixel_count")) is not None
        ]
        lags = [
            float(row["generation_lag_days"])
            for row in members
            if _float(row.get("generation_lag_days")) is not None
        ]
        summary.append(
            {
                "control_version": config.control_version,
                "observation_method": method,
                "reflectance_quantity": config.values["scope"][
                    "reflectance_quantities"
                ][method],
                "processing_baseline": baseline,
                "official_product_context": product_context,
                "band": band,
                "n_available_products": len(members),
                "n_products_with_finite_reflectance_median": len(medians),
                "first_date": min(str(row["date"]) for row in members),
                "last_date": max(str(row["date"]) for row in members),
                "median_generation_lag_days": (
                    statistics.median(lags) if lags else None
                ),
                "median_valid_pixel_count": (
                    statistics.median(valid_counts) if valid_counts else None
                ),
                "median_of_product_reflectance_medians": (
                    statistics.median(medians) if medians else None
                ),
                "q05_of_product_reflectance_medians": (
                    float(np.quantile(medians, 0.05, method="linear"))
                    if medians
                    else None
                ),
                "q95_of_product_reflectance_medians": (
                    float(np.quantile(medians, 0.95, method="linear"))
                    if medians
                    else None
                ),
                "cross_baseline_values_directly_comparable": False,
                "descriptive_not_a_harmonization_coefficient": True,
            }
        )
    return summary


def verify_phase6c_outputs(
    manifest_path: Path, repository_root: Path
) -> Mapping[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProcessingBaselineError(
            f"Cannot read frozen Phase 6C manifest: {manifest_path}"
        ) from error
    checked: dict[str, Any] = {}
    for name, specification in sorted(manifest.get("outputs", {}).items()):
        relative = str(specification.get("relative_path", ""))
        expected = str(specification.get("sha256", ""))
        path = repository_root / relative
        actual = sha256_file(path)
        if not expected or actual != expected:
            raise ProcessingBaselineError(
                f"Frozen Phase 6C output changed ({name}): expected "
                f"{expected or '<missing>'}, got {actual}."
            )
        checked[name] = {
            "relative_path": relative,
            "expected_sha256": expected,
            "actual_sha256": actual,
            "unchanged": True,
        }
    if not checked:
        raise ProcessingBaselineError("Phase 6C manifest contains no output hashes.")
    return {
        "manifest_relative_path": manifest_path.relative_to(repository_root).as_posix(),
        "manifest_sha256": sha256_file(manifest_path),
        "outputs": checked,
        "all_outputs_unchanged": True,
    }


def run_processing_baseline_audit(
    *, config: ProcessingBaselineConfig, repository_root: str | Path
) -> ProcessingBaselineResult:
    root = Path(repository_root).resolve()
    input_paths = {
        name: root / str(relative)
        for name, relative in config.values["inputs"].items()
    }
    selection = _read_csv(input_paths["observation_selection"])
    if len(selection) != 2778 or len({row["date"] for row in selection}) != 926:
        raise ProcessingBaselineError(
            "Observation-selection input must remain 926 dates x 3 methods."
        )
    selection_manifest = json.loads(
        input_paths["observation_selection_manifest"].read_text(encoding="utf-8")
    )
    expected_selection_hash = str(
        selection_manifest.get("output", {}).get("selection_table_sha256", "")
    )
    if sha256_file(input_paths["observation_selection"]) != expected_selection_hash:
        raise ProcessingBaselineError(
            "Observation-selection bytes do not match the frozen manifest."
        )
    phase6a_window = _read_csv(input_paths["phase6a_window_reflectance"])
    acolite_window = _read_csv(input_paths["acolite_window_reflectance"])
    inventory_source = _read_csv(input_paths["acolite_product_inventory"])
    phase6c_check = verify_phase6c_outputs(input_paths["phase6c_manifest"], root)

    inventory = build_acquisition_inventory(inventory_source, config)
    audit = build_observation_audit(
        selection, phase6a_window, acolite_window, config
    )
    summary = build_reflectance_summary(audit, config)
    cross_baseline_identities = {
        row["acquisition_identity"]
        for row in inventory
        if int(row["acquisition_distinct_baseline_count"]) >= 2
    }
    same_baseline_duplicate_identities = {
        row["acquisition_identity"]
        for row in inventory
        if row["acquisition_duplicate_status"] == "same_baseline_duplicate"
    }
    exact_dates = {
        str(row["date"])
        for row in audit
        if row["exact_three_method_source_alignment"] is True
    }
    available = [row for row in audit if row["method_product_available"] is True]
    unknown_baseline = [row for row in available if not row["processing_baseline"]]
    failed_radiometry = [
        row
        for row in available
        if row["observation_method"] in {"L1C", "L2A"}
        and row["radiometric_conversion_status"]
        != "metadata_derived_offset_and_quantification_applied"
    ]
    if unknown_baseline:
        raise ProcessingBaselineError(
            f"{len(unknown_baseline)} available products lack processing baseline."
        )
    if failed_radiometry:
        first = failed_radiometry[0]
        raise ProcessingBaselineError(
            "Known metadata radiometry audit failed for "
            f"{first['source_product_id']}: "
            f"{first['radiometric_conversion_status']}."
        )
    gate_settings = config.values["harmonization_gate"]
    if cross_baseline_identities:
        gate_status = str(gate_settings["correction_with_pairs_status"])
    else:
        gate_status = str(gate_settings["correction_without_identifiability_status"])
    baseline_counts: dict[str, dict[str, int]] = {}
    for method in EXPECTED_METHODS:
        baseline_counts[method] = {}
        for row in available:
            if row["observation_method"] != method:
                continue
            baseline = str(row["processing_baseline"])
            baseline_counts[method][baseline] = (
                baseline_counts[method].get(baseline, 0) + 1
            )
    counts = {
        "candidate_dates": 926,
        "observation_rows": len(audit),
        "exact_three_method_alignment_dates": len(exact_dates),
        "available_products_by_method": {
            method: sum(
                row["method_product_available"] is True
                and row["observation_method"] == method
                for row in audit
            )
            for method in EXPECTED_METHODS
        },
        "processing_baselines_by_method": baseline_counts,
        "l1c_l2a_metadata_radiometry_verified_products": sum(
            row["radiometric_conversion_status"]
            == "metadata_derived_offset_and_quantification_applied"
            for row in audit
        ),
        "inventory_products": len(inventory),
        "inventory_acquisition_identities": len(
            {row["acquisition_identity"] for row in inventory}
        ),
        "same_baseline_duplicate_acquisition_identities": len(
            same_baseline_duplicate_identities
        ),
        "cross_baseline_duplicate_acquisition_identities": len(
            cross_baseline_identities
        ),
        "reflectance_summary_rows": len(summary),
    }
    return ProcessingBaselineResult(
        tuple(audit),
        tuple(inventory),
        tuple(summary),
        input_paths,
        counts,
        phase6c_check,
        gate_status,
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
        writer = csv.DictWriter(
            handle, fieldnames=fields or ["empty"], lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})
    return destination


def _git_state(root: Path) -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def write_processing_baseline_outputs(
    result: ProcessingBaselineResult,
    *,
    config: ProcessingBaselineConfig,
    repository_root: str | Path,
) -> dict[str, Path]:
    root = Path(repository_root).resolve()
    output_root = (root / str(config.values["outputs"]["root"])).resolve()
    paths = {
        name: (root / str(relative)).resolve()
        for name, relative in config.values["outputs"].items()
        if name != "root"
    }
    for path in paths.values():
        try:
            path.relative_to(output_root)
        except ValueError as error:
            raise ProcessingBaselineError(
                f"Output escapes Phase 6D namespace: {path}"
            ) from error
        path.parent.mkdir(parents=True, exist_ok=True)

    write_csv(result.observation_audit, paths["observation_audit"])
    write_csv(result.acquisition_inventory, paths["acquisition_inventory"])
    write_csv(result.reflectance_summary, paths["reflectance_summary"])
    output_hashes = {
        name: {
            "relative_path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
        }
        for name, path in sorted(paths.items())
        if name != "gate_manifest"
    }
    commit, dirty = _git_state(root)
    manifest = {
        "schema_version": "erken_s2_processing_baseline_gate_manifest_v1",
        "control_version": config.control_version,
        "status": result.gate_status,
        "decision_id": config.values.get("decision_id"),
        "configuration": {
            "relative_path": config.source_relative_path,
            "sha256": config.sha256,
        },
        "inputs": {
            name: {
                "relative_path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
            }
            for name, path in sorted(result.input_paths.items())
        },
        "counts": result.counts,
        "harmonization_gate": {
            "known_l1c_l2a_metadata_offset_correction_verified": True,
            "same_acquisition_cross_baseline_pairs_available": (
                result.counts[
                    "cross_baseline_duplicate_acquisition_identities"
                ]
                > 0
            ),
            "empirical_cross_baseline_correction_identifiable": (
                result.counts[
                    "cross_baseline_duplicate_acquisition_identities"
                ]
                > 0
            ),
            "empirical_cross_baseline_correction_applied": False,
            "chlf_or_year_used_to_define_correction": False,
            "reflectance_quantities_pooled_for_harmonization": False,
        },
        "phase6c_protection": result.phase6c_hash_check,
        "outputs": output_hashes,
        "repository": {
            "commit_at_generation_start": commit,
            "worktree_dirty_at_generation_start": dirty,
        },
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
        },
        "scientific_guards": {
            "chlf_read": False,
            "phase6c_results_recomputed": False,
            "processor_ranking_generated": False,
            "reconstruction_run": False,
            "timesat_run": False,
            "vombsjon_accessed": False,
        },
    }
    paths["gate_manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return paths
