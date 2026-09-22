"""Vombsjon raw Sentinel-2 / ACOLITE product audit and matchup materialization.

This module inventories the Vombsjon satellite archives, pairs L1C with the
official ESA L2A, discovers the actual ACOLITE output layout, extracts the
frozen fixed-station target and the field-location target, applies the frozen
QC, deduplicates same-day observations per method, and materializes a derived
field-satellite matchup table.

It is an input audit. It never runs TIMESAT, never builds a daily reconstructed
curve, never withholds an observation, never computes a reconstruction metric,
never tunes a rule from Vombsjon, and never chooses a processor from Vombsjon
performance. Every scientific rule it applies is read from the already-frozen
``config/erken_vomb_transfer_freeze_v1.0.json`` and cross-checked against it
before any product is opened.

Three product roles are kept strictly separate and are never pooled and never
substituted for one another:

* ACOLITE ``rhos`` MCI - the primary observation product;
* official L2A BOA MCI - a separate processing sensitivity; and
* L1C TOA MCI - a separate transparent diagnostic baseline.

The Erken Phase 6A/6B scope guards are untouched. This module does not import
the Erken pilot or ACOLITE orchestrators; it reuses only the site-independent
low-level Sentinel-2 and ACOLITE utilities they now share.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform as platform_module
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import rasterio
import yaml

from .provenance import PROHIBITED_PATH_MARKERS
from .s2_acolite_io import (
    AcoliteReadError,
    AcoliteWindowCoverageError,
    decode_flag_bits,
    derive_target_grid,
    parse_flag_exponent_settings,
    read_reflectance_window,
    reduce_flag_window,
    read_native_window,
    scene_basename,
    select_nearest_rhos_assets,
)
from .s2_grid import (
    GridAlignmentError,
    assert_same_grid,
    grid_spec_from_dataset,
)
from .s2_indices import (
    IndexComputationError,
    band_validity,
    common_band_validity,
    compute_mci,
    compute_ndci,
    index_validity,
    mci_baseline_coefficient,
)
from .s2_native_qa import (
    QA_ASSET_ABSENT,
    QA_ASSET_PRESENT,
    QA_ASSET_UNREADABLE,
    NativeQAError,
    build_native_qa,
    decode_multiband_mask,
    qa_inventory_rows,
    scl_water_mask,
    select_qa_asset,
)
from .s2_observation_selection import classify_metric
from .s2_pairing import (
    PAIRING_EXACT_UNIQUE,
    AcquisitionIdentity,
    build_identity,
    identity_from_product_name,
    normalise_datetime,
    pair_l1c_to_l2a,
)
from .s2_pilot_summary import summarize_index_window, write_rows
from .s2_radiometry import (
    RadiometryError,
    read_product_radiometry,
    sensing_metadata,
    to_physical_reflectance,
)
from .s2_safe import (
    SAFEDiscoveryError,
    SAFEProduct,
    canonical_band_name,
    discover_products,
    load_product,
    select_band_asset,
)
from .s2_scl import station_to_pixel, transform_station_coordinate
from .s2_window_io import read_categorical_window, read_target_band


DEFAULT_CONFIG_RELATIVE_PATH = "config/vombsjon_satellite_input_audit_v1.0.yaml"
EXPECTED_SCHEMA_VERSION = "vombsjon_satellite_input_audit_config_v1"
EXPECTED_AUDIT_VERSION = "vombsjon_satellite_input_audit_v1.0"

METHOD_ACOLITE = "ACOLITE"
METHOD_L2A = "L2A"
METHOD_L1C = "L1C"

FIXED_TARGET_ROLE = "fixed_temporal_target"
FIELD_TARGET_ROLE = "field_location"

COORDINATE_MEASURED_GPS = "measured_field_gps"
COORDINATE_NOMINAL_FALLBACK = "nominal_station_fallback"
COORDINATE_UNRESOLVED = "unresolved_flag_retained_extraction_withheld"

# The exact frozen strings this audit implements. They are asserted against
# config/erken_vomb_transfer_freeze_v1.0.json so the executed rule and the
# frozen rule cannot drift apart silently.
FROZEN_PRIMARY_PROXY = "MCI"
FROZEN_MCI_FORMULA = "B5 - (B4 + ((705 - 665) / (740 - 665)) * (B6 - B4))"
FROZEN_SAME_DAY_RULE = (
    "median_of_all_eligible_primary_product_observation_medians_on_calendar_date"
)
FROZEN_WINDOW_SHAPE = "3x3"

REQUIRED_CONFIG_SECTIONS: tuple[str, ...] = (
    "freeze",
    "scope",
    "field_source",
    "fixed_target",
    "products",
    "grid",
    "radiometry",
    "native_qa",
    "pairing",
    "acolite",
    "indices",
    "observation",
    "same_day",
    "field_matchup",
    "outputs",
)

# ACOLITE output basenames such as S2A_MSI_2020_06_10_10_20_31_T33UVB.
ACOLITE_BASENAME_RE = re.compile(
    r"(?P<platform>S2[A-Z0-9])_(?:MSI|MSI_L1C|L1C)?_?"
    r"(?P<year>\d{4})[_-](?P<month>\d{2})[_-](?P<day>\d{2})"
    r"[_T](?P<hour>\d{2})[_:]?(?P<minute>\d{2})[_:]?(?P<second>\d{2})"
    r"(?:_(?P<tile>T\d{2}[A-Z]{3}))?",
    re.IGNORECASE,
)
SAFE_COMPACT_DATETIME_RE = re.compile(r"(?P<acquisition>\d{8}T\d{6})")
TILE_RE = re.compile(r"T\d{2}[A-Z]{3}", re.IGNORECASE)


class VombsjonAuditConfigError(ValueError):
    """Raised when the Vombsjon audit configuration is missing or invalid."""


class VombsjonAuditError(RuntimeError):
    """Raised when the audit would require an unrecorded assumption."""


class VombsjonScopeError(RuntimeError):
    """Raised when an action would leave the governed Vombsjon audit boundary."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VombsjonAuditConfig:
    """A validated audit configuration plus its own identity for provenance."""

    values: Mapping[str, Any]
    source_relative_path: str
    sha256: str

    def section(self, name: str) -> Mapping[str, Any]:
        value = self.values.get(name)
        if not isinstance(value, Mapping):
            raise VombsjonAuditConfigError(
                f"Vombsjon audit configuration section {name!r} must be a mapping."
            )
        return value

    @property
    def audit_version(self) -> str:
        return str(self.values["audit_version"])

    @property
    def status(self) -> str:
        return str(self.values["status"])


@dataclass(frozen=True)
class FrozenTransferFreeze:
    """The frozen transfer configuration this audit executes under."""

    values: Mapping[str, Any]
    relative_path: str
    sha256: str


def sha256_file(path: str | Path) -> str:
    """Return the byte-level SHA256 of one file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    """Return the SHA256 of a UTF-8 string, used for runtime-root identity."""

    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def default_config_path(repository_root: str | Path) -> Path:
    """Return the repository-relative default configuration location."""

    return Path(repository_root) / DEFAULT_CONFIG_RELATIVE_PATH


def load_audit_config(
    path: str | Path, *, repository_root: str | Path | None = None
) -> VombsjonAuditConfig:
    """Load, validate and fingerprint the Vombsjon audit configuration."""

    config_path = Path(path)
    if not config_path.is_file():
        raise VombsjonAuditConfigError(
            f"Vombsjon audit configuration not found: {config_path}"
        )
    with config_path.open(encoding="utf-8") as handle:
        values = yaml.safe_load(handle)
    if not isinstance(values, Mapping):
        raise VombsjonAuditConfigError(
            "Vombsjon audit configuration must be a YAML mapping."
        )

    schema_version = str(values.get("schema_version", ""))
    if schema_version != EXPECTED_SCHEMA_VERSION:
        raise VombsjonAuditConfigError(
            f"Unexpected schema_version {schema_version!r}; expected "
            f"{EXPECTED_SCHEMA_VERSION!r}."
        )
    if str(values.get("audit_version", "")) != EXPECTED_AUDIT_VERSION:
        raise VombsjonAuditConfigError(
            f"Unexpected audit_version {values.get('audit_version')!r}; expected "
            f"{EXPECTED_AUDIT_VERSION!r}."
        )

    missing = [name for name in REQUIRED_CONFIG_SECTIONS if name not in values]
    if missing:
        raise VombsjonAuditConfigError(
            f"Vombsjon audit configuration is missing section(s): {missing}."
        )

    fixed = values["fixed_target"]
    if int(fixed.get("window_size", 0)) != 3:
        raise VombsjonAuditConfigError(
            "The frozen Vombsjon temporal target must remain a 3x3 window."
        )
    if bool(fixed.get("moves_with_field_gps", True)):
        raise VombsjonAuditConfigError(
            "The fixed temporal target must not move with field GPS."
        )
    if int(fixed.get("minimum_valid_pixels", 0)) != 6:
        raise VombsjonAuditConfigError(
            "The frozen minimum is 6 of 9 valid pixels."
        )

    if repository_root is not None:
        try:
            relative_path = (
                config_path.resolve()
                .relative_to(Path(repository_root).resolve())
                .as_posix()
            )
        except ValueError:
            relative_path = config_path.name
    else:
        relative_path = config_path.name

    return VombsjonAuditConfig(
        values=values,
        source_relative_path=relative_path,
        sha256=sha256_file(config_path),
    )


def load_transfer_freeze(
    config: VombsjonAuditConfig, *, repository_root: str | Path
) -> FrozenTransferFreeze:
    """Load the frozen transfer configuration that governs this audit."""

    relative = str(config.section("freeze")["config_path"])
    path = Path(repository_root) / relative
    if not path.is_file():
        raise VombsjonAuditError(f"Frozen transfer configuration not found: {relative}")
    with path.open(encoding="utf-8") as handle:
        values = json.load(handle)
    if not isinstance(values, Mapping):
        raise VombsjonAuditError("Frozen transfer configuration must be a JSON object.")

    expected_version = str(config.section("freeze")["expected_freeze_version"])
    if str(values.get("freeze_version")) != expected_version:
        raise VombsjonAuditError(
            f"Frozen transfer configuration declares freeze_version "
            f"{values.get('freeze_version')!r}; this audit requires "
            f"{expected_version!r}."
        )
    expected_stage = str(config.section("freeze")["expected_next_authorized_stage"])
    actual_stage = str(values.get("scope", {}).get("next_authorized_stage"))
    if actual_stage != expected_stage:
        raise VombsjonAuditError(
            f"The freeze authorizes next stage {actual_stage!r}; this audit is "
            f"only authorized as {expected_stage!r}."
        )
    return FrozenTransferFreeze(
        values=values, relative_path=relative, sha256=sha256_file(path)
    )


def _dotted(values: Mapping[str, Any], key: str) -> Any:
    current: Any = values
    for part in str(key).split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise VombsjonAuditError(
                f"Frozen transfer configuration has no key {key!r}."
            )
        current = current[part]
    return current


def _comparable(value: Any) -> Any:
    """Normalise a value so a YAML mirror and a JSON freeze compare cleanly."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _comparable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_comparable(item) for item in value]
    return str(value)


def freeze_expectations(config: VombsjonAuditConfig) -> dict[str, Any]:
    """Return the value this audit implements for every cross-checked rule."""

    fixed = config.section("fixed_target")
    grid = config.section("grid")
    indices = config.section("indices")
    products = config.section("products")
    native = config.section("native_qa")
    radiometry = config.section("radiometry")
    matchup = config.section("field_matchup")
    primary = products["primary"]
    station = fixed["station"]

    return {
        "observation_layer.primary_proxy": FROZEN_PRIMARY_PROXY,
        "observation_layer.mci_formula": FROZEN_MCI_FORMULA,
        "observation_layer.nominal_wavelengths_nm": indices[
            "nominal_central_wavelength_nm"
        ],
        "observation_layer.primary_processing_product.method": primary["method"],
        "observation_layer.primary_processing_product.quantity": primary["quantity"],
        "observation_layer.primary_processing_product.output_quantity": (
            config.section("acolite")["freeze_declared_identity"]["output_quantity"]
        ),
        "observation_layer.primary_processing_product.resolution_m": grid[
            "target_resolution_m"
        ],
        "observation_layer.primary_processing_product.no_silent_product_fallback": (
            not bool(products["silent_processor_fallback_allowed"])
        ),
        "observation_layer.processing_baseline_policy": {
            "read_exact_baseline_from_product_metadata": True,
            "apply_metadata_additive_offset_and_quantification": (
                not bool(radiometry["universal_dn_divided_by_10000"])
            ),
            "empirical_cross_baseline_correction": False,
            "pool_reflectance_quantities": bool(
                products["pool_reflectance_quantities"]
            ),
            "negative_reflectance_or_mci_clipping": bool(
                radiometry["clamp_negative_reflectance"]
            )
            or bool(indices["clip_mci"]),
        },
        "spatial_and_qc.nominal_station_wgs84": {
            "latitude": station["latitude"],
            "longitude": station["longitude"],
        },
        "spatial_and_qc.grid_resolution_m": grid["target_resolution_m"],
        "spatial_and_qc.window_shape": FROZEN_WINDOW_SHAPE,
        "spatial_and_qc.window_pixel_count": fixed["window_pixel_count"],
        "spatial_and_qc.minimum_valid_pixels": fixed["minimum_valid_pixels"],
        "spatial_and_qc.index_value_statistic": fixed["index_value_statistic"],
        "spatial_and_qc.required_bands": indices["mci"]["required_bands"],
        "spatial_and_qc.missing_required_qa_family_policy": native[
            "missing_required_qa_family_policy"
        ],
        "spatial_and_qc.invalid_pixel_fill_allowed": bool(
            fixed["invalid_pixel_fill_allowed"]
        ),
        "spatial_and_qc.same_day_deduplication": FROZEN_SAME_DAY_RULE,
        "spatial_and_qc.field_matchup_support": {
            "actual_gps_when_available": True,
            "nominal_station_fallback_with_provenance": bool(
                matchup["nominal_fallback_requires_explicit_provenance"]
            ),
            "unresolved_coordinate_correction_allowed": bool(
                matchup["unresolved_coordinate_correction_allowed"]
            ),
            "primary_temporal_target_changes_with_field_gps": bool(
                fixed["moves_with_field_gps"]
            ),
        },
    }


def crosscheck_freeze(
    config: VombsjonAuditConfig, freeze: FrozenTransferFreeze
) -> list[dict[str, Any]]:
    """Verify every declared rule against the frozen transfer configuration.

    A mismatch stops the audit. This is the mechanism that prevents a Vombsjon
    run from quietly executing a rule the second freeze did not authorize.
    """

    requested = [str(key) for key in config.section("freeze")["crosscheck"]]
    expectations = freeze_expectations(config)
    unbound = sorted(set(requested) - set(expectations))
    if unbound:
        raise VombsjonAuditConfigError(
            "The configuration requests a freeze cross-check with no "
            f"implementation binding: {unbound}."
        )

    rows: list[dict[str, Any]] = []
    mismatched: list[str] = []
    for key in requested:
        frozen_value = _comparable(_dotted(freeze.values, key))
        audit_value = _comparable(expectations[key])
        agrees = frozen_value == audit_value
        if not agrees:
            mismatched.append(key)
        rows.append(
            {
                "freeze_key": key,
                "frozen_value": json.dumps(frozen_value, sort_keys=True),
                "audit_value": json.dumps(audit_value, sort_keys=True),
                "agrees": agrees,
            }
        )
    if mismatched:
        detail = "; ".join(
            f"{row['freeze_key']}: frozen={row['frozen_value']} "
            f"audit={row['audit_value']}"
            for row in rows
            if not row["agrees"]
        )
        raise VombsjonAuditError(
            "The Vombsjon audit configuration does not match the frozen "
            f"transfer configuration for {mismatched}. {detail}"
        )
    return rows


# ---------------------------------------------------------------------------
# Output-path and portability guards
# ---------------------------------------------------------------------------


def assert_output_path_allowed(
    path: str | Path, config: VombsjonAuditConfig, *, repository_root: str | Path
) -> Path:
    """Confine every write to the versioned Vombsjon audit namespace."""

    outputs = config.section("outputs")
    root = Path(repository_root).resolve()
    target = Path(path)
    resolved = (root / target if not target.is_absolute() else target).resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as error:
        raise VombsjonScopeError(
            f"Vombsjon audit output path escapes the repository root: {resolved}."
        ) from error

    allowed_root = str(outputs["root"]).strip("/")
    if not (relative == allowed_root or relative.startswith(f"{allowed_root}/")):
        raise VombsjonScopeError(
            f"The Vombsjon audit may only write under '{allowed_root}/'; "
            f"refused: '{relative}'."
        )
    for prefix in outputs.get("protected_prefixes", []):
        protected = str(prefix).strip("/")
        if relative == protected or relative.startswith(f"{protected}/"):
            raise VombsjonScopeError(
                f"Refusing to write into frozen/protected namespace "
                f"'{protected}': '{relative}'."
            )
    lowered = relative.lower()
    for token in config.section("scope").get("prohibited_output_tokens", []):
        text = str(token).strip().lower()
        if text and text in lowered:
            raise VombsjonScopeError(
                f"Vombsjon audit output path '{relative}' refers to a "
                f"prohibited namespace token {text!r}."
            )
    return resolved


def assert_portable_rows(
    rows: Iterable[Mapping[str, Any]], *, context: str = "output rows"
) -> None:
    """Fail if a committed table would embed a machine-specific home path."""

    for index, row in enumerate(rows):
        for column, value in row.items():
            if value is None:
                continue
            text = str(value)
            detected = [
                marker for marker in PROHIBITED_PATH_MARKERS if marker in text
            ]
            if detected:
                raise VombsjonScopeError(
                    f"{context} row {index} column {column!r} contains "
                    f"machine-specific absolute path marker(s) {detected}."
                )


# ---------------------------------------------------------------------------
# Extraction targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractionTarget:
    """One geographic target to extract a station-centred window around."""

    target_id: str
    role: str
    latitude: float
    longitude: float
    crs: str
    coordinate_provenance: str
    field_date: str | None = None


@dataclass(frozen=True)
class FieldRecord:
    """One preserved field row plus the target derived from it."""

    field_date: str
    year: int | None
    source_row: Mapping[str, str]
    coordinate_provenance: str
    latitude: float | None
    longitude: float | None
    withheld_reason: str | None


def _float_or_none(value: Any) -> float | None:
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _int_or_none(value: Any) -> int | None:
    number = _float_or_none(value)
    return int(number) if number is not None else None


def fixed_target(config: VombsjonAuditConfig) -> ExtractionTarget:
    """Return the frozen station-centred target that never moves between dates."""

    station = config.section("fixed_target")["station"]
    return ExtractionTarget(
        target_id=str(config.section("fixed_target")["id"]),
        role=FIXED_TARGET_ROLE,
        latitude=float(station["latitude"]),
        longitude=float(station["longitude"]),
        crs=str(station["crs"]),
        coordinate_provenance="frozen_nominal_station_fixed_for_all_dates",
    )


def read_field_source(
    config: VombsjonAuditConfig, *, repository_root: str | Path
) -> tuple[list[FieldRecord], str, str]:
    """Read the committed field table read-only and derive its matchup targets.

    The committed CSV is never written to. The two known unresolved 2020
    longitude flags are preserved with their QC text, and their field-location
    extraction is withheld rather than resolved to either candidate minute.
    """

    source = config.section("field_source")
    relative = str(source["path"])
    path = Path(repository_root) / relative
    if not path.is_file():
        raise VombsjonAuditError(f"Committed Vombsjon field source not found: {relative}")

    digest = sha256_file(path)
    expected = str(source["sha256"])
    if digest != expected:
        raise VombsjonAuditError(
            f"Committed field source {relative} has SHA256 {digest}, but the "
            f"audit configuration pins {expected}. The frozen input changed; "
            "this audit stops rather than recording a mismatched identity."
        )

    columns = source["columns"]
    with path.open(encoding=str(source.get("encoding", "utf-8-sig")), newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]

    expected_rows = int(source["expected_row_count"])
    if len(rows) != expected_rows:
        raise VombsjonAuditError(
            f"Committed field source {relative} holds {len(rows)} rows; the "
            f"prior field-input audit verified {expected_rows}."
        )

    unresolved_value = str(source["unresolved_coordinate_source_value"])
    nominal_station = config.section("fixed_target")["station"]

    records: list[FieldRecord] = []
    for row in rows:
        field_date = str(row.get(columns["date"], "")).strip()
        coordinate_source = str(row.get(columns["coordinate_source"], "")).strip()
        gps_latitude = _float_or_none(row.get(columns["gps_latitude"]))
        gps_longitude = _float_or_none(row.get(columns["gps_longitude"]))
        nominal_latitude = _float_or_none(row.get(columns["nominal_latitude"]))
        nominal_longitude = _float_or_none(row.get(columns["nominal_longitude"]))

        if coordinate_source == unresolved_value:
            provenance = COORDINATE_UNRESOLVED
            latitude = None
            longitude = None
            withheld = (
                "field_coordinate_flag_unresolved_extraction_withheld: the "
                "source longitude minute is disputed and must not be silently "
                "corrected"
            )
        elif gps_latitude is not None and gps_longitude is not None:
            provenance = COORDINATE_MEASURED_GPS
            latitude = gps_latitude
            longitude = gps_longitude
            withheld = None
        else:
            provenance = COORDINATE_NOMINAL_FALLBACK
            latitude = (
                nominal_latitude
                if nominal_latitude is not None
                else float(nominal_station["latitude"])
            )
            longitude = (
                nominal_longitude
                if nominal_longitude is not None
                else float(nominal_station["longitude"])
            )
            withheld = None

        records.append(
            FieldRecord(
                field_date=field_date,
                year=_int_or_none(row.get(columns["year"])),
                source_row=row,
                coordinate_provenance=provenance,
                latitude=latitude,
                longitude=longitude,
                withheld_reason=withheld,
            )
        )
    return records, relative, digest


def field_targets_by_date(
    records: Sequence[FieldRecord], *, crs: str
) -> dict[str, list[ExtractionTarget]]:
    """Group the extractable field targets by their calendar date."""

    grouped: dict[str, list[ExtractionTarget]] = {}
    for record in records:
        if record.latitude is None or record.longitude is None:
            continue
        grouped.setdefault(record.field_date, []).append(
            ExtractionTarget(
                target_id=f"field_{record.field_date}",
                role=FIELD_TARGET_ROLE,
                latitude=float(record.latitude),
                longitude=float(record.longitude),
                crs=crs,
                coordinate_provenance=record.coordinate_provenance,
                field_date=record.field_date,
            )
        )
    return grouped


# ---------------------------------------------------------------------------
# SAFE inventory and pairing
# ---------------------------------------------------------------------------


def _acquisition_date(identity: AcquisitionIdentity | None) -> str | None:
    if identity is None or not identity.sensing_datetime_utc:
        return None
    return identity.sensing_datetime_utc[:10]


def _relative_to(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


@dataclass
class SafeArchive:
    """One indexed SAFE archive level with its inventory and failures."""

    level: str
    root: Path | None
    products: dict[str, SAFEProduct] = field(default_factory=dict)
    identities: dict[str, AcquisitionIdentity] = field(default_factory=dict)
    inventory_rows: list[dict[str, Any]] = field(default_factory=list)
    qa_inventory_rows: list[dict[str, Any]] = field(default_factory=list)
    failure_rows: list[dict[str, Any]] = field(default_factory=list)


def inventory_safe_archive(
    root: str | Path | None, *, level: str, config: VombsjonAuditConfig
) -> SafeArchive:
    """Inventory every discovered SAFE product before any scientific filtering.

    Products that cannot be interpreted are retained as explicit discovery
    failures rather than dropped, so the inventory describes the archive as it
    actually is.
    """

    archive = SafeArchive(level=level.upper(), root=None if root is None else Path(root))
    if archive.root is None:
        return archive
    if not archive.root.is_dir():
        raise VombsjonAuditError(
            f"{level.upper()} archive root is not a directory: {archive.root}"
        )

    families = [
        str(name) for name in config.section("native_qa")["inventoried_qa_families"]
    ]
    bands = [str(name) for name in config.section("radiometry")["bands"]]

    for product_path in discover_products(archive.root, level=level):
        relative = _relative_to(product_path, archive.root)
        try:
            product = load_product(product_path)
        except SAFEDiscoveryError as error:
            archive.failure_rows.append(
                {
                    "stage": "safe_discovery",
                    "method": level.upper(),
                    "product_id": product_path.name,
                    "source_relative_path": relative,
                    "failure_reason": f"safe_discovery_failed: {error}",
                }
            )
            continue
        if product.level != level.upper():
            archive.failure_rows.append(
                {
                    "stage": "safe_discovery",
                    "method": level.upper(),
                    "product_id": product.product_id,
                    "source_relative_path": relative,
                    "failure_reason": (
                        f"product_level_mismatch: declared {product.level}, "
                        f"expected {level.upper()}"
                    ),
                }
            )
            continue

        metadata = sensing_metadata(product.root, level)
        identity = build_identity(
            product_id=product.product_id,
            level=level,
            name_fallback=product.root.name,
            metadata=metadata,
        )
        archive.products[product.product_id] = product
        archive.identities[product.product_id] = identity

        discovered_bands = {
            band: len(product.bands_for(band)) for band in bands
        }
        archive.inventory_rows.append(
            {
                "product_id": product.product_id,
                "product_level": product.level,
                "source_relative_path": relative,
                "platform": identity.platform,
                "sensing_datetime_utc": identity.sensing_datetime_utc,
                "acquisition_date": _acquisition_date(identity),
                "year": (
                    int(_acquisition_date(identity)[:4])
                    if _acquisition_date(identity)
                    else None
                ),
                "tile_id": identity.tile_id,
                "relative_orbit": identity.relative_orbit,
                "processing_baseline": identity.processing_baseline,
                "generation_time_utc": identity.generation_time_utc,
                "product_uri": metadata.get("product_uri"),
                "metadata_tile_id": metadata.get("tile_id"),
                "acquisition_metadata_complete": identity.complete,
                "band_asset_count": len(product.band_assets),
                "qa_asset_count": len(product.qa_assets),
                "scl_asset_count": len(product.scl_assets),
                **{
                    f"{band}_raster_count": count
                    for band, count in sorted(discovered_bands.items())
                },
                "discovery_status": "inventoried",
            }
        )
        archive.qa_inventory_rows.extend(
            qa_inventory_rows(product, families=families, bands=bands)
        )

    archive.inventory_rows.sort(
        key=lambda row: (str(row.get("sensing_datetime_utc") or ""), str(row["product_id"]))
    )
    return archive


def pairing_audit(
    *,
    l2a: SafeArchive,
    l1c: SafeArchive,
    config: VombsjonAuditConfig,
) -> list[dict[str, Any]]:
    """Pair every official L2A product with exactly one L1C acquisition.

    Both directions are reported: an L2A product with no unique L1C partner and
    an L1C product no L2A product claims are each an explicit audit row.
    """

    pairing_config = config.section("pairing")
    tolerance = float(pairing_config["sensing_datetime_tolerance_seconds"])
    compare_orbit = bool(pairing_config["compare_relative_orbit"])
    l1c_candidates = [l1c.identities[key] for key in sorted(l1c.identities)]
    l1c_root_provided = l1c.root is not None

    rows: list[dict[str, Any]] = []
    matched_l1c: set[str] = set()
    for product_id in sorted(l2a.identities):
        identity = l2a.identities[product_id]
        result = pair_l1c_to_l2a(
            identity,
            l1c_candidates,
            tolerance_seconds=tolerance,
            compare_orbit=compare_orbit,
            l1c_root_provided=l1c_root_provided,
        )
        if result.status == PAIRING_EXACT_UNIQUE and result.l1c is not None:
            matched_l1c.add(result.l1c.product_id)
        rows.append(
            {
                "pairing_direction": "l2a_to_l1c",
                "acquisition_date": _acquisition_date(identity),
                "l2a_product_id": identity.product_id,
                "l2a_platform": identity.platform,
                "l2a_sensing_datetime_utc": identity.sensing_datetime_utc,
                "l2a_tile_id": identity.tile_id,
                "l2a_relative_orbit": identity.relative_orbit,
                "l2a_processing_baseline": identity.processing_baseline,
                "l2a_generation_time_utc": identity.generation_time_utc,
                "l2a_metadata_complete": identity.complete,
                "l1c_pairing_status": result.status,
                "l1c_product_id": result.l1c.product_id if result.l1c else None,
                "l1c_platform": result.l1c.platform if result.l1c else None,
                "l1c_sensing_datetime_utc": (
                    result.l1c.sensing_datetime_utc if result.l1c else None
                ),
                "l1c_tile_id": result.l1c.tile_id if result.l1c else None,
                "l1c_relative_orbit": (
                    result.l1c.relative_orbit if result.l1c else None
                ),
                "l1c_processing_baseline": (
                    result.l1c.processing_baseline if result.l1c else None
                ),
                "l1c_generation_time_utc": (
                    result.l1c.generation_time_utc if result.l1c else None
                ),
                "l1c_candidate_count": len(result.candidate_product_ids),
                "l1c_candidate_product_ids": (
                    ";".join(result.candidate_product_ids) or None
                ),
                "pairing_detail": result.detail,
            }
        )

    for product_id in sorted(l1c.identities):
        if product_id in matched_l1c:
            continue
        identity = l1c.identities[product_id]
        rows.append(
            {
                "pairing_direction": "l1c_without_l2a",
                "acquisition_date": _acquisition_date(identity),
                "l1c_product_id": identity.product_id,
                "l1c_platform": identity.platform,
                "l1c_sensing_datetime_utc": identity.sensing_datetime_utc,
                "l1c_tile_id": identity.tile_id,
                "l1c_relative_orbit": identity.relative_orbit,
                "l1c_processing_baseline": identity.processing_baseline,
                "l1c_generation_time_utc": identity.generation_time_utc,
                "l1c_metadata_complete": identity.complete,
                "l1c_pairing_status": "no_official_l2a_product_for_acquisition",
                "pairing_detail": (
                    "No official L2A product shares this acquisition identity. "
                    "The L1C diagnostic baseline therefore has no paired SCL "
                    "water context and its observation is unavailable."
                ),
            }
        )
    return rows


def paired_l2a_for_l1c(
    pairing_rows: Sequence[Mapping[str, Any]]
) -> dict[str, str]:
    """Map each uniquely paired L1C product to its official L2A partner."""

    mapping: dict[str, str] = {}
    for row in pairing_rows:
        if row.get("pairing_direction") != "l2a_to_l1c":
            continue
        if row.get("l1c_pairing_status") != PAIRING_EXACT_UNIQUE:
            continue
        l1c_id = row.get("l1c_product_id")
        l2a_id = row.get("l2a_product_id")
        if l1c_id and l2a_id:
            mapping[str(l1c_id)] = str(l2a_id)
    return mapping


# ---------------------------------------------------------------------------
# ACOLITE discovery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AcoliteScene:
    """One discovered ACOLITE output scene, described by what is on disk."""

    scene_id: str
    output_dir: Path
    relative_dir: str
    layout_depth: int
    rhos_assets: tuple[tuple[float, Path], ...]
    flags_paths: tuple[Path, ...]
    netcdf_paths: tuple[Path, ...]
    settings_paths: tuple[Path, ...]
    run_json_paths: tuple[Path, ...]
    ancestor_directory_names: tuple[str, ...]


def _rhos_pattern(marker: str) -> re.Pattern[str]:
    return re.compile(
        rf"{re.escape(str(marker))}(?P<wavelength>\d+(?:\.\d+)?)\.tiff?$",
        re.IGNORECASE,
    )


def discover_acolite_scenes(
    root: str | Path, *, config: VombsjonAuditConfig
) -> tuple[list[AcoliteScene], list[dict[str, Any]]]:
    """Discover the ACOLITE layout that actually exists under the supplied root.

    No directory convention is assumed. Every directory that directly contains
    at least one ``L2R rhos`` GeoTIFF is treated as an ACOLITE output
    directory, scenes are grouped by the ACOLITE output basename, and the
    observed relative layout is recorded as provenance. Raw files are only
    read; nothing is moved, renamed or modified.
    """

    archive = Path(root)
    if not archive.is_dir():
        raise VombsjonAuditError(f"ACOLITE root is not a directory: {archive}")

    acolite = config.section("acolite")
    marker = str(acolite["reflectance_filename_marker"])
    reflectance_infix = str(acolite["reflectance_infix"])
    flags_infix = str(acolite["flags_infix"])
    flags_marker = str(acolite["flags_filename_marker"]).lower()
    # The configured marker ends in .tif; GDAL writers also emit .tiff, so both
    # spellings are accepted. Nothing else about the name is assumed.
    flags_markers = (flags_marker, f"{flags_marker}f")
    settings_globs = [str(item) for item in acolite["settings_filename_globs"]]
    run_json_name = str(acolite["run_json_filename"])
    maximum_depth = int(acolite["maximum_walk_depth"])
    pattern = _rhos_pattern(marker)

    scenes: list[AcoliteScene] = []
    failures: list[dict[str, Any]] = []

    for current, directory_names, filenames in os.walk(archive, followlinks=False):
        current_path = Path(current)
        relative_dir = _relative_to(current_path, archive)
        depth = 0 if relative_dir in (".", "") else len(Path(relative_dir).parts)
        if depth >= maximum_depth:
            directory_names[:] = []
        directory_names.sort()

        rhos_by_scene: dict[str, list[tuple[float, Path]]] = {}
        flags_by_scene: dict[str, list[Path]] = {}
        netcdf_by_scene: dict[str, list[Path]] = {}
        for name in sorted(filenames):
            lower = name.lower()
            path = current_path / name
            match = pattern.search(name)
            if match:
                key = scene_basename(name, infix=reflectance_infix)
                rhos_by_scene.setdefault(key, []).append(
                    (float(match.group("wavelength")), path)
                )
                continue
            if lower.endswith(flags_markers):
                key = scene_basename(name, infix=flags_infix)
                flags_by_scene.setdefault(key, []).append(path)
                continue
            if lower.endswith(".nc"):
                key = name
                for infix in (reflectance_infix, flags_infix, "_L2R.", "_L2W."):
                    if infix in name:
                        key = scene_basename(name, infix=infix)
                        break
                netcdf_by_scene.setdefault(key, []).append(path)

        if not rhos_by_scene:
            # A directory that holds only NetCDF ACOLITE output carries no
            # readable GeoTIFF pair. It is recorded, never silently skipped
            # and never read as a substitute for the required GeoTIFFs.
            for key, paths in sorted(netcdf_by_scene.items()):
                failures.append(
                    {
                        "stage": "acolite_discovery",
                        "method": METHOD_ACOLITE,
                        "product_id": key,
                        "source_relative_path": relative_dir,
                        "failure_reason": (
                            "acolite_geotiff_rhos_absent_netcdf_only: "
                            + ";".join(path.name for path in paths)
                        ),
                    }
                )
            continue

        # ACOLITE writes its settings beside the products, but some layouts keep
        # one settings file one level up. The parent is searched only when it is
        # still inside the supplied archive root, so discovery never reads
        # outside the directory the operator named.
        search_directories = [current_path]
        if depth >= 1:
            search_directories.append(current_path.parent)
        settings_paths: list[Path] = []
        run_json_candidates: list[Path] = []
        for directory in search_directories:
            for glob_pattern in settings_globs:
                settings_paths.extend(directory.glob(glob_pattern))
            run_json_candidates.extend(directory.glob(run_json_name))
        unique_settings = sorted(
            {path for path in settings_paths if path.is_file()},
            key=lambda item: item.as_posix(),
        )
        run_json_paths = sorted(
            {path for path in run_json_candidates if path.is_file()},
            key=lambda item: item.as_posix(),
        )
        ancestors = tuple(
            part for part in Path(relative_dir).parts if part not in (".",)
        )

        for key in sorted(rhos_by_scene):
            scenes.append(
                AcoliteScene(
                    scene_id=key,
                    output_dir=current_path,
                    relative_dir=relative_dir,
                    layout_depth=depth,
                    rhos_assets=tuple(sorted(rhos_by_scene[key])),
                    flags_paths=tuple(sorted(flags_by_scene.get(key, []))),
                    netcdf_paths=tuple(sorted(netcdf_by_scene.get(key, []))),
                    settings_paths=tuple(unique_settings),
                    run_json_paths=tuple(run_json_paths),
                    ancestor_directory_names=ancestors,
                )
            )

    scenes.sort(key=lambda item: (item.relative_dir, item.scene_id))
    return scenes, failures


def parse_acolite_scene_identity(scene_id: str) -> tuple[AcquisitionIdentity | None, str]:
    """Parse an acquisition identity from an ACOLITE output basename.

    Returns the identity and the parser actually used, so the inventory records
    how the acquisition was recovered instead of implying one convention.
    """

    safe_identity = identity_from_product_name(scene_id)
    if safe_identity is not None:
        return safe_identity, "safe_compact_product_name"

    match = ACOLITE_BASENAME_RE.search(scene_id)
    if match:
        sensing = normalise_datetime(
            "{year}{month}{day}T{hour}{minute}{second}".format(
                year=match.group("year"),
                month=match.group("month"),
                day=match.group("day"),
                hour=match.group("hour"),
                minute=match.group("minute"),
                second=match.group("second"),
            )
        )
        tile = match.group("tile")
        return (
            AcquisitionIdentity(
                product_id=scene_id,
                level="ACOLITE",
                platform=match.group("platform").upper(),
                sensing_datetime_utc=sensing,
                tile_id=tile.upper() if tile else None,
                relative_orbit=None,
                processing_baseline=None,
                generation_time_utc=None,
            ),
            "acolite_output_basename",
        )

    compact = SAFE_COMPACT_DATETIME_RE.search(scene_id)
    tile_match = TILE_RE.search(scene_id)
    platform_match = re.search(r"S2[A-Z0-9]", scene_id.upper())
    if compact and platform_match:
        return (
            AcquisitionIdentity(
                product_id=scene_id,
                level="ACOLITE",
                platform=platform_match.group(0),
                sensing_datetime_utc=normalise_datetime(compact.group("acquisition")),
                tile_id=tile_match.group(0).upper() if tile_match else None,
                relative_orbit=None,
                processing_baseline=None,
                generation_time_utc=None,
            ),
            "embedded_compact_datetime",
        )
    return None, "unparsed"


def _settings_values(paths: Sequence[Path], keys: Sequence[str]) -> dict[str, list[str]]:
    """Read declared ACOLITE settings values for the requested keys."""

    wanted = {str(key) for key in keys}
    observed: dict[str, list[str]] = {}
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw = (part.strip() for part in stripped.split("=", 1))
            if key not in wanted:
                continue
            value = raw.split("#", 1)[0].strip()
            values = observed.setdefault(key, [])
            if value not in values:
                values.append(value)
    return observed


def link_acolite_scene(
    scene: AcoliteScene,
    *,
    identity: AcquisitionIdentity | None,
    l1c: SafeArchive,
    settings: Mapping[str, list[str]],
    tolerance_seconds: float,
    linkage_order: Sequence[str],
) -> tuple[str | None, str, str]:
    """Link one ACOLITE scene to a source L1C product without guessing.

    Returns the linked L1C product id, the linkage method, and an explicit
    status. An ambiguous or absent link is reported as such.
    """

    for method in linkage_order:
        name = str(method)
        if name == "ancestor_directory_l1c_product_name":
            for part in reversed(scene.ancestor_directory_names):
                candidate = part[:-5] if part.upper().endswith(".SAFE") else part
                if candidate in l1c.products:
                    return candidate, name, "exact_unique"
        elif name == "acolite_output_basename_acquisition_identity":
            if identity is None or not identity.sensing_datetime_utc:
                continue
            matches = [
                product_id
                for product_id, candidate in sorted(l1c.identities.items())
                if _identity_matches(
                    identity, candidate, tolerance_seconds=tolerance_seconds
                )
            ]
            if len(matches) == 1:
                return matches[0], name, "exact_unique"
            if len(matches) > 1:
                return None, name, f"ambiguous_{len(matches)}_l1c_candidates"
        elif name == "acolite_settings_inputfile":
            declared = settings.get("inputfile", [])
            candidates: list[str] = []
            for value in declared:
                stem = Path(value.replace("\\", "/")).name
                stem = stem[:-5] if stem.upper().endswith(".SAFE") else stem
                if stem in l1c.products and stem not in candidates:
                    candidates.append(stem)
            if len(candidates) == 1:
                return candidates[0], name, "exact_unique"
            if len(candidates) > 1:
                return None, name, f"ambiguous_{len(candidates)}_declared_inputfiles"
    if not l1c.products:
        return None, "none", "l1c_archive_not_indexed"
    return None, "none", "unlinked_no_candidate"


def _identity_matches(
    left: AcquisitionIdentity,
    right: AcquisitionIdentity,
    *,
    tolerance_seconds: float,
) -> bool:
    if not (left.sensing_datetime_utc and right.sensing_datetime_utc):
        return False
    if left.platform and right.platform and left.platform != right.platform:
        return False
    if left.tile_id and right.tile_id and left.tile_id != right.tile_id:
        return False
    first = datetime.strptime(left.sensing_datetime_utc, "%Y-%m-%dT%H:%M:%SZ")
    second = datetime.strptime(right.sensing_datetime_utc, "%Y-%m-%dT%H:%M:%SZ")
    return abs((first - second).total_seconds()) <= float(tolerance_seconds)


def acolite_inventory_rows(
    scenes: Sequence[AcoliteScene],
    *,
    archive_root: Path,
    l1c: SafeArchive,
    config: VombsjonAuditConfig,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Inventory every discovered ACOLITE scene before scientific filtering."""

    acolite = config.section("acolite")
    identity_keys = [
        str(key) for key in acolite["verifiable_identity_setting_keys"]
    ]
    linkage_order = [str(item) for item in acolite["linkage_order"]]
    tolerance = float(acolite["linkage_datetime_tolerance_seconds"])

    rows: list[dict[str, Any]] = []
    linkage: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        identity, parser = parse_acolite_scene_identity(scene.scene_id)
        settings = _settings_values(scene.settings_paths, identity_keys)
        linked_id, linkage_method, linkage_status = link_acolite_scene(
            scene,
            identity=identity,
            l1c=l1c,
            settings=settings,
            tolerance_seconds=tolerance,
            linkage_order=linkage_order,
        )
        linked_identity = l1c.identities.get(linked_id) if linked_id else None
        sensing = (
            linked_identity.sensing_datetime_utc
            if linked_identity is not None
            else (identity.sensing_datetime_utc if identity else None)
        )
        row: dict[str, Any] = {
            "acolite_scene_id": scene.scene_id,
            "acolite_output_relative_dir": scene.relative_dir,
            "acolite_layout_depth": scene.layout_depth,
            "acolite_layout_pattern": _layout_pattern(scene),
            "acolite_basename_parser": parser,
            "platform": identity.platform if identity else None,
            "tile_id": identity.tile_id if identity else None,
            "sensing_datetime_utc": sensing,
            "acquisition_date": sensing[:10] if sensing else None,
            "year": int(sensing[:4]) if sensing else None,
            "rhos_geotiff_count": len(scene.rhos_assets),
            "rhos_wavelengths_nm": ";".join(
                f"{wavelength:g}" for wavelength, _ in scene.rhos_assets
            )
            or None,
            "l2_flags_geotiff_count": len(scene.flags_paths),
            "l2_flags_relative_path": (
                _relative_to(scene.flags_paths[0], archive_root)
                if len(scene.flags_paths) == 1
                else None
            ),
            "netcdf_output_count": len(scene.netcdf_paths),
            "netcdf_output_names": ";".join(
                path.name for path in scene.netcdf_paths
            )
            or None,
            "settings_file_count": len(scene.settings_paths),
            "settings_relative_paths": ";".join(
                _relative_to(path, archive_root) for path in scene.settings_paths
            )
            or None,
            "settings_sha256": ";".join(
                sha256_file(path) for path in scene.settings_paths
            )
            or None,
            "run_json_count": len(scene.run_json_paths),
            "run_json_relative_paths": ";".join(
                _relative_to(path, archive_root) for path in scene.run_json_paths
            )
            or None,
            "run_json_sha256": ";".join(
                sha256_file(path) for path in scene.run_json_paths
            )
            or None,
            "linked_l1c_product_id": linked_id,
            "l1c_linkage_method": linkage_method,
            "l1c_linkage_status": linkage_status,
            "l1c_processing_baseline": (
                linked_identity.processing_baseline if linked_identity else None
            ),
            "l1c_relative_orbit": (
                linked_identity.relative_orbit if linked_identity else None
            ),
        }
        for key in identity_keys:
            declared = settings.get(key, [])
            row[f"acolite_setting_{key}"] = ";".join(declared) or None
            row[f"acolite_setting_{key}_status"] = (
                "declared_in_settings_file" if declared else "not_declared_unverified"
            )
        rows.append(row)
        linkage[scene.scene_id] = {
            "linked_l1c_product_id": linked_id,
            "l1c_linkage_method": linkage_method,
            "l1c_linkage_status": linkage_status,
            "sensing_datetime_utc": sensing,
            "platform": row["platform"],
            "tile_id": row["tile_id"],
            "settings": settings,
        }
    return rows, linkage


def _layout_pattern(scene: AcoliteScene) -> str:
    """Describe the observed directory layout of one ACOLITE scene."""

    parts = list(scene.ancestor_directory_names)
    if not parts:
        return "<acolite_root>/<files>"
    tokens: list[str] = []
    for part in parts:
        upper = part.upper()
        if "_MSIL1C_" in upper:
            tokens.append("<l1c_product>")
        elif "_MSIL2A_" in upper:
            tokens.append("<l2a_product>")
        elif re.fullmatch(r"\d{4}", part):
            tokens.append("<year>")
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", part):
            tokens.append("<date>")
        elif part.lower() == "acolite":
            tokens.append("acolite")
        elif ACOLITE_BASENAME_RE.search(part):
            tokens.append("<acolite_scene>")
        else:
            tokens.append("<dir>")
    return "<acolite_root>/" + "/".join(tokens) + "/<files>"


# ---------------------------------------------------------------------------
# Extraction - official SAFE products
# ---------------------------------------------------------------------------


def _base_row(
    *,
    method: str,
    product_id: str,
    identity: AcquisitionIdentity | None,
    source_relative_path: str,
    target: ExtractionTarget,
) -> dict[str, Any]:
    sensing = identity.sensing_datetime_utc if identity else None
    return {
        "method": method,
        "product_id": product_id,
        "source_relative_path": source_relative_path,
        "target_id": target.target_id,
        "target_role": target.role,
        "target_latitude": target.latitude,
        "target_longitude": target.longitude,
        "target_crs": target.crs,
        "coordinate_provenance": target.coordinate_provenance,
        "field_date": target.field_date,
        "platform": identity.platform if identity else None,
        "sensing_datetime_utc": sensing,
        "acquisition_date": sensing[:10] if sensing else None,
        "year": int(sensing[:4]) if sensing else None,
        "tile_id": identity.tile_id if identity else None,
        "relative_orbit": identity.relative_orbit if identity else None,
        "processing_baseline": identity.processing_baseline if identity else None,
        "generation_time_utc": identity.generation_time_utc if identity else None,
        "failure_reason": None,
    }


def _summarize_target(
    row: dict[str, Any],
    *,
    bands: Sequence[str],
    reflectance: Mapping[str, np.ndarray],
    validity: Mapping[str, np.ndarray],
    common_valid: np.ndarray,
    ndci: Any,
    mci: Any,
    window_pixels: int,
    diagnostic_minimum: float,
    diagnostic_maximum: float,
) -> dict[str, Any]:
    for band in bands:
        values = np.asarray(reflectance[band], dtype="float64")
        valid = np.asarray(validity[band]).astype(bool)
        row.update(
            summarize_index_window(
                values,
                valid,
                prefix=f"{band}_reflectance",
                window_pixel_count=window_pixels,
            )
        )
        finite = np.isfinite(values)
        row[f"{band}_reflectance_nonfinite_count"] = int(np.count_nonzero(~finite))
        row[f"{band}_reflectance_below_range_count"] = int(
            np.count_nonzero(finite & (values < diagnostic_minimum))
        )
        row[f"{band}_reflectance_above_range_count"] = int(
            np.count_nonzero(finite & (values > diagnostic_maximum))
        )

    row["common_B456_valid_count"] = int(np.count_nonzero(common_valid))
    row.update(
        summarize_index_window(
            ndci.values, ndci.valid, prefix="NDCI", window_pixel_count=window_pixels
        )
    )
    row.update(
        summarize_index_window(
            mci.values, mci.valid, prefix="MCI", window_pixel_count=window_pixels
        )
    )
    for name, flags in sorted(ndci.diagnostics.items()):
        row[f"NDCI_diag_{name}"] = int(np.count_nonzero(flags))
    for name, flags in sorted(mci.diagnostics.items()):
        row[f"MCI_diag_{name}"] = int(np.count_nonzero(flags))
    return row


def extract_safe_product(
    product: SAFEProduct,
    *,
    config: VombsjonAuditConfig,
    identity: AcquisitionIdentity | None,
    scl_product: SAFEProduct | None,
    targets: Sequence[ExtractionTarget],
    source_relative_path: str,
) -> list[dict[str, Any]]:
    """Extract reflectance, native QA and indices for one SAFE product.

    One row is produced for every requested target. Every failure mode keeps
    its row and states an explicit reason, so no product or date is dropped for
    being inconvenient.
    """

    grid_config = config.section("grid")
    radiometry_config = config.section("radiometry")
    qa_config = config.section("native_qa")
    index_config = config.section("indices")
    fixed = config.section("fixed_target")

    bands = tuple(str(band) for band in radiometry_config["bands"])
    window_size = int(fixed["window_size"])
    window_pixels = window_size * window_size
    target_resolution = int(grid_config["target_resolution_m"])
    method = product.level.upper()

    rows = [
        _base_row(
            method=method,
            product_id=product.product_id,
            identity=identity,
            source_relative_path=source_relative_path,
            target=target,
        )
        for target in targets
    ]
    for row in rows:
        row["window_size"] = window_size
        row["window_pixel_count"] = window_pixels
        row["grid_resolution_m"] = target_resolution
        row["required_qa_complete"] = None

    def fail_all(reason: str) -> list[dict[str, Any]]:
        for row in rows:
            row["failure_reason"] = reason
            row["observation_available"] = False
        return rows

    # --- product-level radiometry --------------------------------------------
    try:
        product_radiometry = read_product_radiometry(
            product.root,
            product_id=product.product_id,
            level=product.level,
            bands=bands,
            canonical_band_ids=radiometry_config["canonical_band_ids"],
            missing_offset_list_is_zero_offset=bool(
                radiometry_config["missing_offset_list_is_zero_offset"]
            ),
            offset_convention_minimum_baseline=str(
                radiometry_config["offset_convention_minimum_baseline"]
            ),
        )
    except RadiometryError as error:
        return fail_all(f"radiometric_metadata_unusable: {error}")

    radiometry_columns: dict[str, Any] = {
        "quantification_value": product_radiometry.quantification_value,
        "product_metadata_relative_path": product_radiometry.metadata_relative_path,
        "radiometry_processing_baseline": product_radiometry.processing_baseline,
        "radiometry_processing_baseline_source": (
            product_radiometry.processing_baseline_source
        ),
        "radiometry_offset_expected_for_baseline": product_radiometry.offset_expected,
    }
    for band, terms in product_radiometry.bands.items():
        radiometry_columns[f"{band}_band_id"] = terms.band_id
        radiometry_columns[f"{band}_band_id_source"] = terms.band_id_source
        radiometry_columns[f"{band}_add_offset"] = terms.add_offset
        radiometry_columns[f"{band}_offset_source"] = terms.offset_source
        radiometry_columns[f"{band}_conversion_rule"] = terms.conversion_rule()
    for row in rows:
        row.update(radiometry_columns)

    # --- product-level target grid -------------------------------------------
    try:
        target_asset = select_band_asset(
            product, "B5", prefer_resolution_m=target_resolution
        )
        with rasterio.open(target_asset.path) as dataset:
            grid = grid_spec_from_dataset(dataset)
        if abs(grid.pixel_size_x - target_resolution) > float(
            grid_config["pixel_size_tolerance_m"]
        ):
            raise GridAlignmentError(
                f"B5 raster pixel size {grid.pixel_size_x} m does not define "
                f"the frozen {target_resolution} m analysis grid."
            )
    except (SAFEDiscoveryError, GridAlignmentError, rasterio.RasterioIOError) as error:
        return fail_all(f"target_grid_unresolved: {error}")

    grid_columns = {f"target_grid_{key}": value for key, value in grid.audit().items()}
    for row in rows:
        row.update(grid_columns)

    # --- product-level QA asset selection ------------------------------------
    qualit_names = [str(name) for name in qa_config["msk_qualit_bands"]]
    classi_names = [str(name) for name in qa_config["msk_classi_bands"]]
    hard_flags = [str(name) for name in qa_config["hard_invalid_flags"]]
    diagnostic_flags = [str(name) for name in qa_config["diagnostic_flags"]]
    configured = set(hard_flags) | set(diagnostic_flags)
    family_band_names = {"QUALIT": qualit_names, "CLASSI": classi_names}
    required_families = {str(name) for name in qa_config["required_qa_families"]}

    qa_plan: list[tuple[str, str | None, Any, list[str]]] = []
    asset_status: dict[str, str] = {}
    for family in (str(name) for name in qa_config["band_specific_qa_families"]):
        for band in bands:
            slot = canonical_band_name(band)
            asset, status = select_qa_asset(product, family, band=band)
            asset_status[f"{family}:{slot}"] = status
            if asset is not None and status == QA_ASSET_PRESENT:
                qa_plan.append((family, band, asset, family_band_names[family]))
    for family in (str(name) for name in qa_config["common_qa_families"]):
        asset, status = select_qa_asset(product, family)
        asset_status[f"{family}:product"] = status
        if asset is not None and status == QA_ASSET_PRESENT:
            qa_plan.append((family, None, asset, family_band_names[family]))

    # --- paired L2A SCL water context ----------------------------------------
    water_config = qa_config["pixel_water_context"]
    water_applies = method in {
        str(level).upper() for level in water_config["applies_to"]
    }
    scl_asset = None
    if water_applies:
        if scl_product is None:
            asset_status["SCL_WATER_CONTEXT:product"] = QA_ASSET_ABSENT
        elif not scl_product.scl_assets:
            asset_status["SCL_WATER_CONTEXT:product"] = QA_ASSET_ABSENT
        else:
            scl_asset = min(
                scl_product.scl_assets,
                key=lambda asset: (
                    0 if asset.declared_resolution_m == target_resolution else 1,
                    asset.relative_path,
                ),
            )
            asset_status["SCL_WATER_CONTEXT:product"] = QA_ASSET_PRESENT

    for row in rows:
        row["scl_source_product_id"] = (
            scl_product.product_id if scl_product is not None else None
        )
        row["scl_asset_relative_path"] = (
            scl_asset.relative_path if scl_asset is not None else None
        )

    # --- per-target extraction -----------------------------------------------
    diagnostic_minimum = float(radiometry_config["diagnostic_reflectance_min"])
    diagnostic_maximum = float(radiometry_config["diagnostic_reflectance_max"])
    window_shape = (window_size, window_size)

    for row, target in zip(rows, targets):
        try:
            station_x, station_y = transform_station_coordinate(
                station_lon=float(target.longitude),
                station_lat=float(target.latitude),
                station_crs=str(target.crs),
                raster_crs=grid.crs,
            )
        except Exception as error:  # noqa: BLE001 - reported, never absorbed
            row["failure_reason"] = f"target_projection_failed: {error}"
            row["observation_available"] = False
            continue

        location = station_to_pixel(
            grid.transform,
            raster_width=grid.width,
            raster_height=grid.height,
            station_x=station_x,
            station_y=station_y,
        )
        row["target_row"] = location.row
        row["target_col"] = location.col
        row["target_inside_raster"] = location.inside
        if not location.inside:
            row["failure_reason"] = "target_outside_raster"
            row["observation_available"] = False
            continue

        reflectance: dict[str, np.ndarray] = {}
        try:
            for band in bands:
                digital_numbers, provenance = read_target_band(
                    product,
                    band,
                    target=grid,
                    target_row=location.row,
                    target_col=location.col,
                    window_size=window_size,
                    prefer_resolution_m=target_resolution,
                    grid_config=grid_config,
                )
                row.update(provenance)
                # read_product_radiometry keys its terms by the configured band
                # name (B4, not B04), exactly as the Phase 6A pilot does.
                reflectance[band] = to_physical_reflectance(
                    digital_numbers, product_radiometry.bands[band]
                )
        except (
            SAFEDiscoveryError,
            GridAlignmentError,
            rasterio.RasterioIOError,
        ) as error:
            row["failure_reason"] = f"reflectance_extraction_failed: {error}"
            row["observation_available"] = False
            continue

        band_condition_flags: dict[str, dict[str, np.ndarray]] = {}
        common_condition_flags: dict[str, np.ndarray] = {}
        source_families: dict[str, str] = {}
        source_paths: dict[str, str | None] = {}
        target_status = dict(asset_status)

        for family, band, asset, band_names in qa_plan:
            slot = canonical_band_name(band) if band is not None else "product"
            try:
                values, geometry = read_categorical_window(
                    asset.path,
                    target=grid,
                    target_row=location.row,
                    target_col=location.col,
                    window_size=window_size,
                    grid_config=grid_config,
                    boolean_conditions=True,
                )
                decoded = decode_multiband_mask(values, band_names, family=family)
            except (
                GridAlignmentError,
                NativeQAError,
                rasterio.RasterioIOError,
            ) as error:
                target_status[f"{family}:{slot}"] = QA_ASSET_UNREADABLE
                row[f"qa_{family.lower()}_{slot.lower()}_error"] = str(error)
                continue

            row[f"qa_{family.lower()}_{slot.lower()}_asset_relative_path"] = (
                asset.relative_path
            )
            row[f"qa_{family.lower()}_{slot.lower()}_grid_alignment"] = geometry[
                "alignment"
            ]
            row[f"qa_{family.lower()}_{slot.lower()}_native_pixel_size_m"] = geometry[
                "native_pixel_size_m"
            ]
            for name, flags in decoded.items():
                if name not in configured:
                    continue
                if band is not None:
                    key = canonical_band_name(band)
                    slot_flags = band_condition_flags.setdefault(key, {})
                    existing = slot_flags.get(name)
                    slot_flags[name] = flags if existing is None else (existing | flags)
                    source_families[f"{key}:{name}"] = family
                    source_paths[f"{key}:{name}"] = asset.relative_path
                else:
                    existing = common_condition_flags.get(name)
                    common_condition_flags[name] = (
                        flags if existing is None else (existing | flags)
                    )
                    source_families[name] = family
                    source_paths[name] = asset.relative_path

        water_mask: np.ndarray | None = None
        if water_applies and scl_asset is not None:
            try:
                scl_window, scl_geometry = read_categorical_window(
                    scl_asset.path,
                    target=grid,
                    target_row=location.row,
                    target_col=location.col,
                    window_size=window_size,
                    grid_config=grid_config,
                    boolean_conditions=False,
                )
                water_mask = scl_water_mask(
                    scl_window[0], water_class=int(water_config["require_scl_class"])
                )
                source_paths["scl_not_water"] = scl_asset.relative_path
                row["scl_grid_alignment"] = scl_geometry["alignment"]
                row["scl_native_pixel_size_m"] = scl_geometry["native_pixel_size_m"]
            except (GridAlignmentError, rasterio.RasterioIOError) as error:
                target_status["SCL_WATER_CONTEXT:product"] = QA_ASSET_UNREADABLE
                row["scl_water_context_error"] = str(error)

        try:
            qa_result = build_native_qa(
                band_condition_flags=band_condition_flags,
                common_condition_flags=common_condition_flags,
                asset_status=target_status,
                hard_invalid_flags=hard_flags,
                diagnostic_flags=diagnostic_flags,
                source_families=source_families,
                source_paths=source_paths,
                window_shape=window_shape,
                bands=bands,
                water_mask=water_mask,
            )
        except NativeQAError as error:
            row["failure_reason"] = f"native_qa_canonicalization_failed: {error}"
            row["observation_available"] = False
            continue

        incomplete_required = sorted(
            {
                key.split(":", 1)[0]
                for key, status in target_status.items()
                if status != QA_ASSET_PRESENT
                and key.split(":", 1)[0] in required_families
            }
        )
        row["native_qa_incomplete"] = qa_result.native_qa_incomplete
        row["native_qa_incomplete_families"] = (
            ";".join(qa_result.incomplete_families) or None
        )
        row["required_qa_incomplete_families"] = (
            ";".join(incomplete_required) or None
        )
        row["required_qa_complete"] = not incomplete_required
        for key, count in qa_result.counts().items():
            row[f"qa_{key}_count"] = count

        try:
            validity = band_validity(
                reflectance,
                {
                    band: qa_result.hard_invalid_by_band.get(
                        canonical_band_name(band), np.zeros(window_shape, dtype=bool)
                    )
                    for band in reflectance
                },
                common_hard_invalid=qa_result.common_hard_invalid,
            )
            ndci_valid = index_validity(
                validity,
                tuple(str(band) for band in index_config["ndci"]["required_bands"]),
            )
            mci_valid = index_validity(
                validity,
                tuple(str(band) for band in index_config["mci"]["required_bands"]),
            )
            common_valid = common_band_validity(validity)
            ndci = compute_ndci(
                reflectance["B4"],
                reflectance["B5"],
                valid=ndci_valid,
                denominator_epsilon=float(
                    index_config["ndci"]["denominator_epsilon"]
                ),
                require_positive_denominator=bool(
                    index_config["ndci"]["require_positive_denominator"]
                ),
                theoretical_min=float(index_config["ndci"]["theoretical_min"]),
                theoretical_max=float(index_config["ndci"]["theoretical_max"]),
            )
            coefficient = mci_baseline_coefficient(
                index_config["nominal_central_wavelength_nm"]
            )
            mci = compute_mci(
                reflectance["B4"],
                reflectance["B5"],
                reflectance["B6"],
                valid=mci_valid,
                baseline_coefficient=coefficient,
            )
        except IndexComputationError as error:
            row["failure_reason"] = f"index_computation_failed: {error}"
            row["observation_available"] = False
            continue

        row["mci_baseline_coefficient"] = coefficient
        row["observation_available"] = True
        _summarize_target(
            row,
            bands=bands,
            reflectance=reflectance,
            validity=validity,
            common_valid=common_valid,
            ndci=ndci,
            mci=mci,
            window_pixels=window_pixels,
            diagnostic_minimum=diagnostic_minimum,
            diagnostic_maximum=diagnostic_maximum,
        )
    return rows


# ---------------------------------------------------------------------------
# Extraction - ACOLITE
# ---------------------------------------------------------------------------


def extract_acolite_scene(
    scene: AcoliteScene,
    *,
    config: VombsjonAuditConfig,
    archive_root: Path,
    identity: AcquisitionIdentity | None,
    linkage: Mapping[str, Any],
    targets: Sequence[ExtractionTarget],
) -> list[dict[str, Any]]:
    """Extract ACOLITE rhos, l2_flags QA and indices for one scene.

    The primary observation product must come from its own ``L2R rhos`` rasters
    and the matching ``L2W l2_flags`` raster. A missing or ambiguous flags
    raster makes the observation unavailable; no other processor and no NetCDF
    output is substituted.
    """

    acolite = config.section("acolite")
    grid_config = config.section("grid")
    index_config = config.section("indices")
    fixed = config.section("fixed_target")

    window_size = int(fixed["window_size"])
    window_pixels = window_size * window_size
    target_resolution = int(grid_config["target_resolution_m"])
    bands = ("B4", "B5", "B6")

    rows = [
        _base_row(
            method=METHOD_ACOLITE,
            product_id=scene.scene_id,
            identity=identity,
            source_relative_path=scene.relative_dir,
            target=target,
        )
        for target in targets
    ]
    for row in rows:
        row["acolite_scene_id"] = scene.scene_id
        row["acolite_output_relative_dir"] = scene.relative_dir
        row["acolite_layout_pattern"] = _layout_pattern(scene)
        row["reflectance_quantity"] = str(acolite["quantity"])
        row["atmospheric_correction_method"] = METHOD_ACOLITE
        row["linked_l1c_product_id"] = linkage.get("linked_l1c_product_id")
        row["l1c_linkage_method"] = linkage.get("l1c_linkage_method")
        row["l1c_linkage_status"] = linkage.get("l1c_linkage_status")
        row["window_size"] = window_size
        row["window_pixel_count"] = window_pixels
        row["grid_resolution_m"] = target_resolution
        row["required_qa_complete"] = None

    def fail_all(reason: str) -> list[dict[str, Any]]:
        for row in rows:
            row["failure_reason"] = reason
            row["observation_available"] = False
            row["required_qa_complete"] = False
        return rows

    if len(scene.flags_paths) != 1:
        return fail_all(
            "required_acolite_l2w_l2_flags_unavailable: "
            f"{len(scene.flags_paths)} matching l2_flags rasters"
        )

    try:
        selected = select_nearest_rhos_assets(
            list(scene.rhos_assets),
            target_wavelengths_nm={
                str(band): float(details["target_wavelength_nm"])
                for band, details in acolite["logical_bands"].items()
            },
            maximum_difference_nm=float(acolite["maximum_wavelength_difference_nm"]),
        )
    except AcoliteReadError as error:
        return fail_all(f"acolite_rhos_selection_failed: {error}")

    try:
        declared = parse_flag_exponent_settings(
            scene.settings_paths,
            setting_keys=[
                str(value) for value in acolite["flag_exponent_setting_keys"].values()
            ],
        )
    except (AcoliteReadError, OSError) as error:
        return fail_all(f"acolite_settings_unreadable: {error}")

    expected_exponents = {
        str(name): int(value) for name, value in acolite["flag_exponents"].items()
    }
    setting_keys = {
        str(name): str(value)
        for name, value in acolite["flag_exponent_setting_keys"].items()
    }
    declared_count = 0
    for name, expected_value in expected_exponents.items():
        observed = declared.get(setting_keys[name], set())
        if len(observed) > 1:
            return fail_all(
                f"conflicting_{setting_keys[name]}_values_in_acolite_settings: "
                f"{sorted(observed)}"
            )
        if observed:
            declared_count += 1
            actual = next(iter(observed))
            if actual != expected_value:
                return fail_all(
                    f"acolite_{setting_keys[name]}={actual}_differs_from_configured_"
                    f"exponent_{expected_value}"
                )
    flag_validation_status = (
        "all_declared_values_match"
        if declared_count == len(expected_exponents)
        else "declared_values_match_remaining_use_official_defaults"
        if declared_count
        else "not_declared_use_official_defaults"
    )
    for row in rows:
        row["acolite_flag_exponent_validation_status"] = flag_validation_status
        row["acolite_flag_exponents_declared_count"] = declared_count
        row["acolite_l2_flags_relative_path"] = _relative_to(
            scene.flags_paths[0], archive_root
        )
        for band, (wavelength, path) in selected.items():
            row[f"{band}_selected_wavelength_nm"] = wavelength
            row[f"{band}_rhos_relative_path"] = _relative_to(path, archive_root)

    datasets: dict[str, Any] = {}
    flags_dataset: Any | None = None
    try:
        for band, (_, path) in selected.items():
            datasets[band] = rasterio.open(path)
        flags_dataset = rasterio.open(scene.flags_paths[0])

        source = grid_spec_from_dataset(datasets["B4"])
        for band in ("B5", "B6"):
            assert_same_grid(
                source,
                grid_spec_from_dataset(datasets[band]),
                origin_tolerance_m=float(grid_config["origin_tolerance_m"]),
                pixel_size_tolerance_m=float(grid_config["pixel_size_tolerance_m"]),
                left_label="ACOLITE B4 rhos",
                right_label=f"ACOLITE {band} rhos",
            )
        assert_same_grid(
            source,
            grid_spec_from_dataset(flags_dataset),
            origin_tolerance_m=float(grid_config["origin_tolerance_m"]),
            pixel_size_tolerance_m=float(grid_config["pixel_size_tolerance_m"]),
            left_label="ACOLITE rhos",
            right_label="ACOLITE l2_flags",
        )
        grid, factor = derive_target_grid(
            source,
            target_resolution_m=target_resolution,
            accepted_native_resolutions_m=acolite["accepted_native_resolutions_m"],
            origin_tolerance_m=float(grid_config["origin_tolerance_m"]),
            pixel_size_tolerance_m=float(grid_config["pixel_size_tolerance_m"]),
        )
    except (AcoliteReadError, GridAlignmentError, rasterio.RasterioError, OSError) as error:
        for dataset in datasets.values():
            dataset.close()
        if flags_dataset is not None:
            flags_dataset.close()
        return fail_all(f"acolite_grid_unresolved: {error}")

    grid_columns = {f"target_grid_{key}": value for key, value in grid.audit().items()}
    for row in rows:
        row.update(grid_columns)
        row["acolite_native_resolution_m"] = source.pixel_size_x
        row["native_to_target_reduction_factor"] = factor

    try:
        for row, target in zip(rows, targets):
            try:
                station_x, station_y = transform_station_coordinate(
                    station_lon=float(target.longitude),
                    station_lat=float(target.latitude),
                    station_crs=str(target.crs),
                    raster_crs=grid.crs,
                )
            except Exception as error:  # noqa: BLE001 - reported, never absorbed
                row["failure_reason"] = f"target_projection_failed: {error}"
                row["observation_available"] = False
                continue

            location = station_to_pixel(
                grid.transform,
                raster_width=grid.width,
                raster_height=grid.height,
                station_x=station_x,
                station_y=station_y,
            )
            row["target_row"] = location.row
            row["target_col"] = location.col
            row["target_inside_raster"] = location.inside
            if not location.inside:
                row["failure_reason"] = "target_outside_acolite_raster"
                row["observation_available"] = False
                continue

            try:
                reflectance: dict[str, np.ndarray] = {}
                band_nodata: dict[str, np.ndarray] = {}
                for band in bands:
                    values, nodata, scale, offset = read_reflectance_window(
                        datasets[band],
                        target_row=location.row,
                        target_col=location.col,
                        target_size=window_size,
                        factor=factor,
                    )
                    reflectance[band] = values
                    band_nodata[band] = nodata
                    row[f"{band}_geotiff_scale"] = scale
                    row[f"{band}_geotiff_offset"] = offset
                    row[f"{band}_geotiff_nodata"] = datasets[band].nodata

                masked = read_native_window(
                    flags_dataset,
                    target_row=location.row,
                    target_col=location.col,
                    target_size=window_size,
                    factor=factor,
                )
                flags_nodata = np.ma.getmaskarray(masked)
                flag_layers, hard_invalid, flag_values = reduce_flag_window(
                    *decode_flag_bits(
                        np.asarray(masked.filled(0)),
                        flag_exponents=acolite["flag_exponents"],
                        hard_invalid_flags=[
                            str(name) for name in acolite["hard_invalid_flags"]
                        ],
                        nodata_mask=flags_nodata,
                        unknown_bits_hard=(
                            str(acolite["unknown_bits_policy"]) == "hard_invalid"
                        ),
                    ),
                    factor=factor,
                )
            except AcoliteWindowCoverageError as error:
                row["failure_reason"] = f"acolite_window_not_covered: {error}"
                row["observation_available"] = False
                continue
            except (AcoliteReadError, GridAlignmentError, rasterio.RasterioError) as error:
                row["failure_reason"] = f"acolite_window_read_failed: {error}"
                row["observation_available"] = False
                continue

            try:
                validity = band_validity(
                    reflectance, band_nodata, common_hard_invalid=hard_invalid
                )
                ndci_valid = index_validity(
                    validity,
                    tuple(str(band) for band in index_config["ndci"]["required_bands"]),
                )
                mci_valid = index_validity(
                    validity,
                    tuple(str(band) for band in index_config["mci"]["required_bands"]),
                )
                common_valid = common_band_validity(validity)
                ndci = compute_ndci(
                    reflectance["B4"],
                    reflectance["B5"],
                    valid=ndci_valid,
                    denominator_epsilon=float(
                        index_config["ndci"]["denominator_epsilon"]
                    ),
                    require_positive_denominator=bool(
                        index_config["ndci"]["require_positive_denominator"]
                    ),
                    theoretical_min=float(index_config["ndci"]["theoretical_min"]),
                    theoretical_max=float(index_config["ndci"]["theoretical_max"]),
                )
                coefficient = mci_baseline_coefficient(
                    index_config["nominal_central_wavelength_nm"]
                )
                mci = compute_mci(
                    reflectance["B4"],
                    reflectance["B5"],
                    reflectance["B6"],
                    valid=mci_valid,
                    baseline_coefficient=coefficient,
                )
            except IndexComputationError as error:
                row["failure_reason"] = f"index_computation_failed: {error}"
                row["observation_available"] = False
                continue

            row["mci_baseline_coefficient"] = coefficient
            row["required_qa_complete"] = True
            row["observation_available"] = True
            for name, flags in sorted(flag_layers.items()):
                count = int(np.count_nonzero(flags))
                row[f"qa_acolite_{name}_count"] = count
                row[f"qa_acolite_{name}_fraction"] = count / window_pixels
            hard_count = int(np.count_nonzero(hard_invalid))
            row["qa_acolite_hard_invalid_count"] = hard_count
            row["qa_acolite_hard_invalid_fraction"] = hard_count / window_pixels
            row["qa_acolite_any_flag_count"] = int(np.count_nonzero(flag_values != 0))
            row["qa_acolite_flag_value_max"] = int(np.max(flag_values))
            _summarize_target(
                row,
                bands=bands,
                reflectance=reflectance,
                validity=validity,
                common_valid=common_valid,
                ndci=ndci,
                mci=mci,
                window_pixels=window_pixels,
                diagnostic_minimum=0.0,
                diagnostic_maximum=1.0,
            )
    finally:
        for dataset in datasets.values():
            dataset.close()
        if flags_dataset is not None:
            flags_dataset.close()
    return rows


# ---------------------------------------------------------------------------
# Observation-level QC, same-day reduction and field matchup
# ---------------------------------------------------------------------------


OBSERVATION_COLUMNS: tuple[str, ...] = (
    "method",
    "product_id",
    "acolite_scene_id",
    "linked_l1c_product_id",
    "source_relative_path",
    "target_id",
    "target_role",
    "target_latitude",
    "target_longitude",
    "coordinate_provenance",
    "field_date",
    "acquisition_date",
    "year",
    "sensing_datetime_utc",
    "platform",
    "tile_id",
    "relative_orbit",
    "processing_baseline",
    "radiometry_processing_baseline",
    "radiometry_processing_baseline_source",
    "generation_time_utc",
    "grid_resolution_m",
    "window_size",
    "window_pixel_count",
    "target_row",
    "target_col",
    "target_inside_raster",
    "required_qa_complete",
    "required_qa_incomplete_families",
    "native_qa_incomplete",
    "native_qa_incomplete_families",
    "observation_available",
    "failure_reason",
    "MCI_valid_pixel_count",
    "MCI_valid_pixel_fraction",
    "MCI_median",
    "MCI_mean",
    "MCI_SD",
    "MCI_IQR",
    "MCI_min",
    "MCI_max",
    "NDCI_valid_pixel_count",
    "NDCI_valid_pixel_fraction",
    "NDCI_median",
    "NDCI_mean",
    "NDCI_SD",
    "NDCI_IQR",
    "NDCI_min",
    "NDCI_max",
    "common_B456_valid_count",
    "B4_reflectance_median",
    "B5_reflectance_median",
    "B6_reflectance_median",
)


def build_observation_rows(
    extraction_rows: Sequence[Mapping[str, Any]],
    *,
    config: VombsjonAuditConfig,
    target_role: str,
) -> list[dict[str, Any]]:
    """Apply the frozen 6-of-9 rule to one target role, keeping every row."""

    minimum = int(config.section("observation")["minimum_valid_pixels"])
    rows: list[dict[str, Any]] = []
    for source in extraction_rows:
        if str(source.get("target_role")) != target_role:
            continue
        row = {column: source.get(column) for column in OBSERVATION_COLUMNS}
        available = bool(source.get("observation_available"))
        required_complete = source.get("required_qa_complete")
        reason = str(source.get("failure_reason") or "")
        unavailable_reason = (
            reason.split(":", 1)[0]
            if reason
            else "required_qa_incomplete"
            if required_complete is False
            else "source_not_available"
        )
        for metric in ("MCI", "NDCI"):
            eligible, detail = classify_metric(
                count=source.get(f"{metric}_valid_pixel_count"),
                source_available=available,
                required_qa_complete=bool(required_complete),
                unavailable_reason=unavailable_reason,
                minimum_valid_pixels=minimum,
            )
            row[f"{metric.lower()}_observation_eligible"] = eligible
            row[f"{metric.lower()}_observation_status"] = detail
        row["eligibility_rule_id"] = str(
            config.section("observation")["eligibility_rule_id"]
        )
        row["minimum_valid_pixels"] = minimum
        rows.append(row)
    rows.sort(
        key=lambda item: (
            str(item.get("method") or ""),
            str(item.get("acquisition_date") or ""),
            str(item.get("product_id") or ""),
        )
    )
    return rows


def same_day_observation_rows(
    observation_rows: Sequence[Mapping[str, Any]], *, config: VombsjonAuditConfig
) -> list[dict[str, Any]]:
    """Reduce eligible same-date observations per method to one median value.

    The unit is the whole calendar date. Product-level rows are preserved
    upstream; this table records the reduced value together with the exact
    products that contributed and those that were present but not eligible.
    """

    same_day = config.section("same_day")
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in observation_rows:
        method = str(row.get("method") or "")
        date = str(row.get("acquisition_date") or "")
        if not method or not date:
            continue
        grouped.setdefault((method, date), []).append(row)

    reduced: list[dict[str, Any]] = []
    for (method, date), members in sorted(grouped.items()):
        eligible = [
            member
            for member in members
            if member.get("mci_observation_eligible") is True
            and _float_or_none(member.get("MCI_median")) is not None
        ]
        # Membership is tracked by object identity: two distinct product rows
        # with numerically equal content must not collapse into one another.
        eligible_ids = {id(member) for member in eligible}
        excluded = [member for member in members if id(member) not in eligible_ids]
        medians = [float(member["MCI_median"]) for member in eligible]
        ndci_eligible = [
            member
            for member in members
            if member.get("ndci_observation_eligible") is True
            and _float_or_none(member.get("NDCI_median")) is not None
        ]
        ndci_medians = [float(member["NDCI_median"]) for member in ndci_eligible]
        reduced.append(
            {
                "method": method,
                "date": date,
                "year": int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None,
                "observation_unit": str(same_day["unit"]),
                "same_day_reduction": str(same_day["reduction"]),
                "n_products_considered": len(members),
                "n_products_mci_eligible": len(eligible),
                "n_products_ndci_eligible": len(ndci_eligible),
                "mci_observation_available": bool(medians),
                "MCI_date_median": float(np.median(medians)) if medians else None,
                "MCI_observation_median_min": min(medians) if medians else None,
                "MCI_observation_median_max": max(medians) if medians else None,
                "MCI_observation_median_spread": (
                    max(medians) - min(medians) if len(medians) > 1 else 0.0
                )
                if medians
                else None,
                "ndci_observation_available": bool(ndci_medians),
                "NDCI_date_median": (
                    float(np.median(ndci_medians)) if ndci_medians else None
                ),
                "contributing_product_ids": ";".join(
                    str(member.get("product_id")) for member in eligible
                )
                or None,
                "contributing_sensing_datetimes_utc": ";".join(
                    str(member.get("sensing_datetime_utc")) for member in eligible
                )
                or None,
                "contributing_mci_valid_pixel_counts": ";".join(
                    str(member.get("MCI_valid_pixel_count")) for member in eligible
                )
                or None,
                "excluded_product_ids": ";".join(
                    str(member.get("product_id")) for member in excluded
                )
                or None,
                "excluded_product_statuses": ";".join(
                    str(member.get("mci_observation_status")) for member in excluded
                )
                or None,
                "methods_pooled": False,
            }
        )
    return reduced


# Fixed-target columns carried onto every matchup row, so the field-location
# result and the frozen temporal-target result for the same product can be read
# side by side without joining another table.
_FIXED_TARGET_MATCHUP_COLUMNS: tuple[str, ...] = (
    "target_row",
    "target_col",
    "observation_available",
    "failure_reason",
    "MCI_valid_pixel_count",
    "MCI_valid_pixel_fraction",
    "MCI_median",
    "NDCI_valid_pixel_count",
    "NDCI_median",
    "mci_observation_eligible",
    "mci_observation_status",
)


def field_matchup_rows(
    records: Sequence[FieldRecord],
    *,
    config: VombsjonAuditConfig,
    field_observation_rows: Sequence[Mapping[str, Any]],
    fixed_observation_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Materialize the derived field-satellite matchup table.

    The committed source CSV is never modified. Each field row is preserved,
    including the two unresolved coordinate flags, whose field-location
    extraction is explicitly withheld. No regression, correlation, ranking or
    performance model is computed here.
    """

    matchup = config.section("field_matchup")
    columns = config.section("field_source")["columns"]
    methods = (METHOD_ACOLITE, METHOD_L2A, METHOD_L1C)
    tolerance_days = int(matchup["temporal_tolerance_days"])

    by_field_date: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in field_observation_rows:
        key = (str(row.get("field_date") or ""), str(row.get("method") or ""))
        by_field_date.setdefault(key, []).append(row)

    fixed_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    fixed_by_date: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in fixed_observation_rows:
        method_key = str(row.get("method") or "")
        fixed_by_key[(str(row.get("product_id") or ""), method_key)] = row
        fixed_by_date.setdefault(
            (str(row.get("acquisition_date") or ""), method_key), []
        ).append(row)

    rows: list[dict[str, Any]] = []
    for record in records:
        source_row = record.source_row
        base: dict[str, Any] = {
            "field_date": record.field_date,
            "field_year": record.year,
            "field_chla_fluorometry_ug_L": _float_or_none(
                source_row.get(columns["chla"])
            ),
            "field_integrated_sample_depth_m": source_row.get(
                columns["integrated_sample_depth"]
            ),
            "field_gps_lat_measured": _float_or_none(
                source_row.get(columns["gps_latitude"])
            ),
            "field_gps_lon_measured": _float_or_none(
                source_row.get(columns["gps_longitude"])
            ),
            "field_gps_raw_N": source_row.get(columns["gps_raw_north"]),
            "field_gps_raw_E": source_row.get(columns["gps_raw_east"]),
            "source_matchup_lat": _float_or_none(
                source_row.get(columns["matchup_latitude"])
            ),
            "source_matchup_lon": _float_or_none(
                source_row.get(columns["matchup_longitude"])
            ),
            "source_coordinate_source_for_matchup": source_row.get(
                columns["coordinate_source"]
            ),
            "source_coordinate_qc": source_row.get(columns["coordinate_qc"]),
            "nominal_station_lat": _float_or_none(
                source_row.get(columns["nominal_latitude"])
            ),
            "nominal_station_lon": _float_or_none(
                source_row.get(columns["nominal_longitude"])
            ),
            "coordinate_provenance": record.coordinate_provenance,
            "coordinates_used_lat": record.latitude,
            "coordinates_used_lon": record.longitude,
            "coordinate_correction_applied": False,
            "field_extraction_withheld_reason": record.withheld_reason,
            "temporal_rule": str(matchup["temporal_rule"]),
            "temporal_tolerance_days": tolerance_days,
            "field_sampling_time_available": bool(
                matchup["field_sampling_time_available"]
            ),
            "acquisition_time_difference_reference": str(
                matchup["acquisition_time_difference_reference"]
            ),
        }

        for method in methods:
            members = by_field_date.get((record.field_date, method), [])
            if not members:
                # No field-location extraction exists for this date and method,
                # either because no product was acquired or because the field
                # coordinate is an unresolved flag. The row is still emitted,
                # and any fixed-target observation on the same date is attached
                # so the reader can see that satellite data exists even where
                # the field location could not be used.
                same_date = fixed_by_date.get((record.field_date, method), [])
                status = (
                    "field_coordinate_unresolved_extraction_withheld"
                    if record.withheld_reason
                    else "no_satellite_product_on_field_date"
                )
                if not same_date:
                    row = dict(base)
                    row["method"] = method
                    row["matchup_status"] = status
                    rows.append(row)
                    continue
                for fixed_only in same_date:
                    row = dict(base)
                    row["method"] = method
                    row["matchup_status"] = status
                    row["product_id"] = fixed_only.get("product_id")
                    row["acolite_scene_id"] = fixed_only.get("acolite_scene_id")
                    row["sensing_datetime_utc"] = fixed_only.get(
                        "sensing_datetime_utc"
                    )
                    row["acquisition_date"] = fixed_only.get("acquisition_date")
                    row["acquisition_minus_field_date_days"] = (
                        _date_difference_days(
                            fixed_only.get("acquisition_date"), record.field_date
                        )
                    )
                    row["acquisition_time_difference_hours"] = _hours_from_midnight(
                        fixed_only.get("sensing_datetime_utc"), record.field_date
                    )
                    for column in _FIXED_TARGET_MATCHUP_COLUMNS:
                        row[f"fixed_target_{column}"] = fixed_only.get(column)
                    rows.append(row)
                continue
            for member in members:
                row = dict(base)
                row["method"] = method
                row["matchup_status"] = "extracted"
                row["product_id"] = member.get("product_id")
                row["acolite_scene_id"] = member.get("acolite_scene_id")
                row["linked_l1c_product_id"] = member.get("linked_l1c_product_id")
                row["source_relative_path"] = member.get("source_relative_path")
                row["sensing_datetime_utc"] = member.get("sensing_datetime_utc")
                row["acquisition_date"] = member.get("acquisition_date")
                row["platform"] = member.get("platform")
                row["tile_id"] = member.get("tile_id")
                row["relative_orbit"] = member.get("relative_orbit")
                row["processing_baseline"] = member.get("processing_baseline")
                row["radiometry_processing_baseline"] = member.get(
                    "radiometry_processing_baseline"
                )
                row["generation_time_utc"] = member.get("generation_time_utc")
                row["acquisition_minus_field_date_days"] = _date_difference_days(
                    member.get("acquisition_date"), record.field_date
                )
                row["acquisition_time_difference_hours"] = _hours_from_midnight(
                    member.get("sensing_datetime_utc"), record.field_date
                )
                for column in (
                    "grid_resolution_m",
                    "window_size",
                    "window_pixel_count",
                    "target_row",
                    "target_col",
                    "target_inside_raster",
                    "required_qa_complete",
                    "required_qa_incomplete_families",
                    "native_qa_incomplete",
                    "native_qa_incomplete_families",
                    "observation_available",
                    "failure_reason",
                    "MCI_valid_pixel_count",
                    "MCI_valid_pixel_fraction",
                    "MCI_median",
                    "MCI_mean",
                    "MCI_SD",
                    "MCI_IQR",
                    "MCI_min",
                    "MCI_max",
                    "NDCI_valid_pixel_count",
                    "NDCI_valid_pixel_fraction",
                    "NDCI_median",
                    "NDCI_mean",
                    "NDCI_SD",
                    "NDCI_IQR",
                    "NDCI_min",
                    "NDCI_max",
                    "common_B456_valid_count",
                    "B4_reflectance_median",
                    "B5_reflectance_median",
                    "B6_reflectance_median",
                    "mci_observation_eligible",
                    "mci_observation_status",
                    "ndci_observation_eligible",
                    "ndci_observation_status",
                ):
                    row[f"field_location_{column}"] = member.get(column)

                fixed_row = fixed_by_key.get(
                    (str(member.get("product_id") or ""), method)
                )
                for column in _FIXED_TARGET_MATCHUP_COLUMNS:
                    row[f"fixed_target_{column}"] = (
                        fixed_row.get(column) if fixed_row else None
                    )
                rows.append(row)

    rows.sort(
        key=lambda item: (
            str(item.get("field_date") or ""),
            str(item.get("method") or ""),
            str(item.get("product_id") or ""),
        )
    )
    return rows


def _date_difference_days(acquisition_date: Any, field_date: str) -> int | None:
    if not acquisition_date or not field_date:
        return None
    try:
        first = datetime.strptime(str(acquisition_date), "%Y-%m-%d")
        second = datetime.strptime(str(field_date), "%Y-%m-%d")
    except ValueError:
        return None
    return int((first - second).days)


def _hours_from_midnight(sensing_datetime: Any, field_date: str) -> float | None:
    if not sensing_datetime or not field_date:
        return None
    try:
        sensing = datetime.strptime(str(sensing_datetime), "%Y-%m-%dT%H:%M:%SZ")
        reference = datetime.strptime(str(field_date), "%Y-%m-%d")
    except ValueError:
        return None
    return (sensing - reference).total_seconds() / 3600.0


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


@dataclass
class VombsjonAuditResult:
    """In-memory products of one Vombsjon satellite input audit run."""

    l1c_inventory_rows: list[dict[str, Any]] = field(default_factory=list)
    l2a_inventory_rows: list[dict[str, Any]] = field(default_factory=list)
    pairing_rows: list[dict[str, Any]] = field(default_factory=list)
    acolite_inventory_rows: list[dict[str, Any]] = field(default_factory=list)
    native_qa_inventory_rows: list[dict[str, Any]] = field(default_factory=list)
    extraction_rows: list[dict[str, Any]] = field(default_factory=list)
    fixed_observation_rows: list[dict[str, Any]] = field(default_factory=list)
    field_observation_rows: list[dict[str, Any]] = field(default_factory=list)
    same_day_rows: list[dict[str, Any]] = field(default_factory=list)
    matchup_rows: list[dict[str, Any]] = field(default_factory=list)
    failure_rows: list[dict[str, Any]] = field(default_factory=list)
    freeze_crosscheck_rows: list[dict[str, Any]] = field(default_factory=list)
    unresolved_items: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)
    field_source: dict[str, Any] = field(default_factory=dict)
    freeze: dict[str, Any] = field(default_factory=dict)
    acolite_identity: dict[str, Any] = field(default_factory=dict)
    runtime_roots: dict[str, Any] = field(default_factory=dict)


def run_audit(
    *,
    config: VombsjonAuditConfig,
    repository_root: str | Path,
    l1c_root: str | Path | None,
    l2a_root: str | Path | None,
    acolite_root: str | Path | None,
) -> VombsjonAuditResult:
    """Run the Vombsjon raw satellite/product and matchup audit."""

    repository = Path(repository_root)
    freeze = load_transfer_freeze(config, repository_root=repository)
    result = VombsjonAuditResult()
    result.freeze_crosscheck_rows = crosscheck_freeze(config, freeze)
    result.freeze = {
        "path": freeze.relative_path,
        "sha256": freeze.sha256,
        "freeze_version": str(freeze.values.get("freeze_version")),
        "status": str(freeze.values.get("status")),
        "same_day_deduplication_rule": FROZEN_SAME_DAY_RULE,
        "mci_formula": FROZEN_MCI_FORMULA,
    }

    records, field_relative, field_digest = read_field_source(
        config, repository_root=repository
    )
    result.field_source = {
        "path": field_relative,
        "sha256": field_digest,
        "row_count": len(records),
        "source_edited": False,
    }

    station_crs = str(config.section("fixed_target")["station"]["crs"])
    target_fixed = fixed_target(config)
    field_targets = field_targets_by_date(records, crs=station_crs)

    # --- inventories ---------------------------------------------------------
    l1c = inventory_safe_archive(l1c_root, level=METHOD_L1C, config=config)
    l2a = inventory_safe_archive(l2a_root, level=METHOD_L2A, config=config)
    result.l1c_inventory_rows = l1c.inventory_rows
    result.l2a_inventory_rows = l2a.inventory_rows
    result.native_qa_inventory_rows = l1c.qa_inventory_rows + l2a.qa_inventory_rows
    result.failure_rows.extend(l1c.failure_rows)
    result.failure_rows.extend(l2a.failure_rows)

    result.pairing_rows = pairing_audit(l2a=l2a, l1c=l1c, config=config)
    l1c_to_l2a = paired_l2a_for_l1c(result.pairing_rows)

    # --- ACOLITE discovery ---------------------------------------------------
    scenes: list[AcoliteScene] = []
    acolite_linkage: dict[str, dict[str, Any]] = {}
    acolite_root_path: Path | None = None
    if acolite_root is not None:
        acolite_root_path = Path(acolite_root)
        scenes, acolite_failures = discover_acolite_scenes(
            acolite_root_path, config=config
        )
        result.failure_rows.extend(acolite_failures)
        result.acolite_inventory_rows, acolite_linkage = acolite_inventory_rows(
            scenes, archive_root=acolite_root_path, l1c=l1c, config=config
        )

    # --- extraction ----------------------------------------------------------
    for archive in (l2a, l1c):
        for product_id in sorted(archive.products):
            product = archive.products[product_id]
            identity = archive.identities[product_id]
            acquisition_date = _acquisition_date(identity)
            targets = [target_fixed]
            if acquisition_date:
                targets.extend(field_targets.get(acquisition_date, []))
            if archive.level == METHOD_L2A:
                scl_product: SAFEProduct | None = product
            else:
                partner = l1c_to_l2a.get(product_id)
                scl_product = l2a.products.get(partner) if partner else None
            rows = extract_safe_product(
                product,
                config=config,
                identity=identity,
                scl_product=scl_product,
                targets=targets,
                source_relative_path=_relative_to(
                    product.root, archive.root or product.root
                ),
            )
            result.extraction_rows.extend(rows)

    if acolite_root_path is not None:
        for scene in scenes:
            identity, _parser = parse_acolite_scene_identity(scene.scene_id)
            linkage = acolite_linkage.get(scene.scene_id, {})
            linked_id = linkage.get("linked_l1c_product_id")
            linked_identity = l1c.identities.get(linked_id) if linked_id else None
            # The linked L1C acquisition identity is preferred because it is
            # read from product metadata; the ACOLITE basename is the fallback.
            effective_identity = linked_identity or identity
            acquisition_date = _acquisition_date(effective_identity)
            targets = [target_fixed]
            if acquisition_date:
                targets.extend(field_targets.get(acquisition_date, []))
            result.extraction_rows.extend(
                extract_acolite_scene(
                    scene,
                    config=config,
                    archive_root=acolite_root_path,
                    identity=effective_identity,
                    linkage=linkage,
                    targets=targets,
                )
            )

    result.extraction_rows.sort(
        key=lambda row: (
            str(row.get("method") or ""),
            str(row.get("acquisition_date") or ""),
            str(row.get("product_id") or ""),
            str(row.get("target_role") or ""),
            str(row.get("target_id") or ""),
        )
    )
    result.failure_rows.extend(
        {
            "stage": "extraction",
            "method": row.get("method"),
            "product_id": row.get("product_id"),
            "source_relative_path": row.get("source_relative_path"),
            "target_id": row.get("target_id"),
            "target_role": row.get("target_role"),
            "acquisition_date": row.get("acquisition_date"),
            "failure_reason": row.get("failure_reason"),
        }
        for row in result.extraction_rows
        if row.get("failure_reason")
    )

    # --- observation layers --------------------------------------------------
    result.fixed_observation_rows = build_observation_rows(
        result.extraction_rows, config=config, target_role=FIXED_TARGET_ROLE
    )
    result.field_observation_rows = build_observation_rows(
        result.extraction_rows, config=config, target_role=FIELD_TARGET_ROLE
    )
    result.same_day_rows = same_day_observation_rows(
        result.fixed_observation_rows, config=config
    )
    result.matchup_rows = field_matchup_rows(
        records,
        config=config,
        field_observation_rows=result.field_observation_rows,
        fixed_observation_rows=result.fixed_observation_rows,
    )

    result.acolite_identity = summarize_acolite_identity(
        result.acolite_inventory_rows, config=config
    )
    result.unresolved_items = collect_unresolved_items(
        result, config=config, records=records, l1c=l1c, l2a=l2a
    )
    result.runtime_roots = {
        "l1c_root_supplied": l1c_root is not None,
        "l2a_root_supplied": l2a_root is not None,
        "acolite_root_supplied": acolite_root is not None,
        "l1c_root": str(l1c_root) if l1c_root is not None else None,
        "l2a_root": str(l2a_root) if l2a_root is not None else None,
        "acolite_root": str(acolite_root) if acolite_root is not None else None,
        "l1c_root_sha256": sha256_text(str(l1c_root)) if l1c_root else None,
        "l2a_root_sha256": sha256_text(str(l2a_root)) if l2a_root else None,
        "acolite_root_sha256": sha256_text(str(acolite_root)) if acolite_root else None,
    }
    result.counts = _counts(result, records=records)
    return result


def summarize_acolite_identity(
    inventory_rows: Sequence[Mapping[str, Any]], *, config: VombsjonAuditConfig
) -> dict[str, Any]:
    """Report the ACOLITE identity that the run files actually establish."""

    acolite = config.section("acolite")
    keys = [str(key) for key in acolite["verifiable_identity_setting_keys"]]
    observed: dict[str, dict[str, Any]] = {}
    for key in keys:
        values: list[str] = []
        declared_scenes = 0
        for row in inventory_rows:
            value = row.get(f"acolite_setting_{key}")
            if not value:
                continue
            declared_scenes += 1
            for item in str(value).split(";"):
                if item and item not in values:
                    values.append(item)
        observed[key] = {
            "declared_scene_count": declared_scenes,
            "distinct_values": values,
            "status": (
                "verified_from_settings_files"
                if declared_scenes
                else "not_verifiable_from_supplied_files"
            ),
        }
    layouts: dict[str, int] = {}
    for row in inventory_rows:
        pattern = str(row.get("acolite_layout_pattern") or "unknown")
        layouts[pattern] = layouts.get(pattern, 0) + 1
    return {
        "freeze_declared_identity": dict(acolite["freeze_declared_identity"]),
        "observed_settings": observed,
        "observed_layout_patterns": layouts,
        "netcdf_fallback_allowed": bool(acolite["netcdf_fallback_allowed"]),
        "assume_erken_layout": bool(acolite["assume_erken_layout"]),
    }


def collect_unresolved_items(
    result: VombsjonAuditResult,
    *,
    config: VombsjonAuditConfig,
    records: Sequence[FieldRecord],
    l1c: SafeArchive,
    l2a: SafeArchive,
) -> list[dict[str, Any]]:
    """List every item this audit could not resolve, instead of guessing one."""

    items: list[dict[str, Any]] = []
    unresolved_dates = sorted(
        record.field_date for record in records if record.withheld_reason
    )
    if unresolved_dates:
        items.append(
            {
                "item": "field_coordinate_longitude_minute_flags",
                "detail": (
                    "Field rows are preserved with their QC text and the "
                    "field-location extraction is withheld; the disputed "
                    "longitude minute is not resolved to either candidate."
                ),
                "affected": unresolved_dates,
                "status": "unresolved_retained",
            }
        )
    items.append(
        {
            "item": "field_gps_crs_declaration",
            "detail": (
                "The supplied field GPS records carry no machine-readable CRS "
                "declaration; WGS84 is applied as the configured station CRS "
                "and this remains an unverified source property."
            ),
            "affected": [str(config.section("fixed_target")["station"]["crs"])],
            "status": "unverified_source_property",
        }
    )
    items.append(
        {
            "item": "field_sampling_clock_time",
            "detail": (
                "The committed field table records no sampling time, so the "
                "acquisition-minus-sampling interval cannot be computed. The "
                "recorded difference is measured from the field calendar date "
                "at 00:00 UTC."
            ),
            "affected": [],
            "status": "not_available_in_source",
        }
    )

    unverified = sorted(
        key
        for key, value in result.acolite_identity.get("observed_settings", {}).items()
        if value.get("status") != "verified_from_settings_files"
    )
    if unverified:
        items.append(
            {
                "item": "acolite_settings_not_declared_in_supplied_files",
                "detail": (
                    "These ACOLITE settings were not declared by any discovered "
                    "settings or run file, so the frozen declared identity could "
                    "not be verified from the products themselves."
                ),
                "affected": unverified,
                "status": "not_verifiable_from_supplied_files",
            }
        )

    unlinked = sorted(
        str(row.get("acolite_scene_id"))
        for row in result.acolite_inventory_rows
        if str(row.get("l1c_linkage_status")) != "exact_unique"
    )
    if unlinked:
        items.append(
            {
                "item": "acolite_scenes_without_unique_l1c_linkage",
                "detail": (
                    "These ACOLITE scenes could not be linked to exactly one "
                    "L1C product by directory name, output basename or declared "
                    "input file."
                ),
                "affected": unlinked,
                "status": "unresolved_retained",
            }
        )

    ambiguous = sorted(
        str(row.get("l2a_product_id"))
        for row in result.pairing_rows
        if row.get("pairing_direction") == "l2a_to_l1c"
        and str(row.get("l1c_pairing_status")) != PAIRING_EXACT_UNIQUE
    )
    if ambiguous:
        items.append(
            {
                "item": "l2a_products_without_unique_l1c_pair",
                "detail": (
                    "These official L2A products have no exact unique L1C "
                    "partner; the pairing is recorded, never substituted."
                ),
                "affected": ambiguous,
                "status": "unresolved_retained",
            }
        )

    netcdf_only = sorted(
        str(row.get("product_id"))
        for row in result.failure_rows
        if str(row.get("failure_reason") or "").startswith(
            "acolite_geotiff_rhos_absent_netcdf_only"
        )
    )
    if netcdf_only:
        items.append(
            {
                "item": "acolite_scenes_with_netcdf_output_only",
                "detail": (
                    "These ACOLITE outputs carry no L2R rhos GeoTIFF. NetCDF is "
                    "inventoried but never read as a substitute."
                ),
                "affected": netcdf_only,
                "status": "unavailable_recorded",
            }
        )

    if l1c.root is None:
        items.append(
            {
                "item": "l1c_archive_root_not_supplied",
                "detail": "No L1C root was supplied; the diagnostic baseline is absent.",
                "affected": [],
                "status": "input_not_supplied",
            }
        )
    if l2a.root is None:
        items.append(
            {
                "item": "l2a_archive_root_not_supplied",
                "detail": (
                    "No official L2A root was supplied, so the SCL water context "
                    "required by both SAFE levels is unavailable."
                ),
                "affected": [],
                "status": "input_not_supplied",
            }
        )
    return items


def _date_range(rows: Sequence[Mapping[str, Any]], column: str) -> dict[str, Any]:
    dates = sorted(
        {str(row.get(column)) for row in rows if row.get(column)}
    )
    return {
        "count": len(dates),
        "first": dates[0] if dates else None,
        "last": dates[-1] if dates else None,
    }


def _counts(
    result: VombsjonAuditResult, *, records: Sequence[FieldRecord]
) -> dict[str, Any]:
    eligible_by_method: dict[str, int] = {}
    products_by_method: dict[str, int] = {}
    for row in result.fixed_observation_rows:
        method = str(row.get("method") or "")
        products_by_method[method] = products_by_method.get(method, 0) + 1
        if row.get("mci_observation_eligible") is True:
            eligible_by_method[method] = eligible_by_method.get(method, 0) + 1
    same_day_by_method: dict[str, int] = {}
    for row in result.same_day_rows:
        if row.get("mci_observation_available"):
            method = str(row.get("method") or "")
            same_day_by_method[method] = same_day_by_method.get(method, 0) + 1
    return {
        "l1c_products": len(result.l1c_inventory_rows),
        "l2a_products": len(result.l2a_inventory_rows),
        "acolite_scenes": len(result.acolite_inventory_rows),
        "pairing_rows": len(result.pairing_rows),
        "exact_unique_l1c_l2a_pairs": sum(
            1
            for row in result.pairing_rows
            if row.get("pairing_direction") == "l2a_to_l1c"
            and str(row.get("l1c_pairing_status")) == PAIRING_EXACT_UNIQUE
        ),
        "extraction_rows": len(result.extraction_rows),
        "fixed_target_observation_rows": len(result.fixed_observation_rows),
        "field_location_observation_rows": len(result.field_observation_rows),
        "same_day_rows": len(result.same_day_rows),
        "field_matchup_rows": len(result.matchup_rows),
        "failure_rows": len(result.failure_rows),
        "field_source_rows": len(records),
        "field_rows_with_measured_gps": sum(
            1
            for record in records
            if record.coordinate_provenance == COORDINATE_MEASURED_GPS
        ),
        "field_rows_using_nominal_fallback": sum(
            1
            for record in records
            if record.coordinate_provenance == COORDINATE_NOMINAL_FALLBACK
        ),
        "field_rows_coordinate_unresolved": sum(
            1 for record in records if record.withheld_reason
        ),
        "fixed_target_products_by_method": products_by_method,
        "fixed_target_mci_eligible_by_method": eligible_by_method,
        "same_day_mci_available_dates_by_method": same_day_by_method,
        "l1c_acquisition_dates": _date_range(
            result.l1c_inventory_rows, "acquisition_date"
        ),
        "l2a_acquisition_dates": _date_range(
            result.l2a_inventory_rows, "acquisition_date"
        ),
        "acolite_acquisition_dates": _date_range(
            result.acolite_inventory_rows, "acquisition_date"
        ),
        "field_dates": _date_range(
            [{"date": record.field_date} for record in records], "date"
        ),
    }


# ---------------------------------------------------------------------------
# Manifest and writers
# ---------------------------------------------------------------------------


def _git_value(repository_root: Path, arguments: Sequence[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    value = completed.stdout.strip()
    return value or None


def build_manifest(
    result: VombsjonAuditResult,
    *,
    config: VombsjonAuditConfig,
    repository_root: Path,
    record_absolute_roots: bool,
) -> dict[str, Any]:
    """Build the audit manifest, stating unresolved items rather than guesses."""

    status = _git_value(repository_root, ("status", "--porcelain"))
    roots = dict(result.runtime_roots)
    if not record_absolute_roots:
        for key in ("l1c_root", "l2a_root", "acolite_root"):
            roots[key] = None
        roots["absolute_paths_recorded"] = False
    else:
        roots["absolute_paths_recorded"] = True

    acolite = config.section("acolite")
    fixed = config.section("fixed_target")
    return {
        "audit_version": config.audit_version,
        "status": config.status,
        "lake": str(config.values.get("lake")),
        "processing_timestamp_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "repository_commit": _git_value(repository_root, ("rev-parse", "HEAD")),
        "repository_worktree_dirty": bool(status),
        "python_version": sys.version.split()[0],
        "platform": platform_module.platform(terse=True),
        "package_versions": {
            "numpy": np.__version__,
            "rasterio": rasterio.__version__,
        },
        "config": {
            "path": config.source_relative_path,
            "sha256": config.sha256,
        },
        "governing_freeze": result.freeze,
        "freeze_crosscheck": result.freeze_crosscheck_rows,
        "field_source": result.field_source,
        "runtime_input_roots": roots,
        "counts": result.counts,
        "extraction_and_qc_rules": {
            "fixed_temporal_target": {
                "station_wgs84": dict(fixed["station"]),
                "moves_with_field_gps": bool(fixed["moves_with_field_gps"]),
                "window_shape": FROZEN_WINDOW_SHAPE,
                "window_pixel_count": int(fixed["window_pixel_count"]),
                "grid_resolution_m": int(
                    config.section("grid")["target_resolution_m"]
                ),
                "minimum_valid_pixels": int(fixed["minimum_valid_pixels"]),
                "index_value_statistic": str(fixed["index_value_statistic"]),
                "invalid_pixel_fill_allowed": bool(
                    fixed["invalid_pixel_fill_allowed"]
                ),
            },
            "product_roles": dict(config.section("products")),
            "radiometry": {
                "conversion_formula": str(
                    config.section("radiometry")["conversion_formula"]
                ),
                "universal_dn_divided_by_10000": bool(
                    config.section("radiometry")["universal_dn_divided_by_10000"]
                ),
                "offset_convention_minimum_baseline": str(
                    config.section("radiometry")[
                        "offset_convention_minimum_baseline"
                    ]
                ),
                "clamp_negative_reflectance": bool(
                    config.section("radiometry")["clamp_negative_reflectance"]
                ),
            },
            "required_qa_families": [
                str(name)
                for name in config.section("native_qa")["required_qa_families"]
            ],
            "missing_required_qa_family_policy": str(
                config.section("native_qa")["missing_required_qa_family_policy"]
            ),
            "same_day": dict(config.section("same_day")),
            "field_matchup": dict(config.section("field_matchup")),
            "indices": {
                "mci_formula": FROZEN_MCI_FORMULA,
                "nominal_central_wavelength_nm": dict(
                    config.section("indices")["nominal_central_wavelength_nm"]
                ),
                "clip_mci": bool(config.section("indices")["clip_mci"]),
            },
        },
        "acolite": {
            "layout_discovery": str(acolite["layout_discovery"]),
            "assume_erken_layout": bool(acolite["assume_erken_layout"]),
            "identity": result.acolite_identity,
        },
        "unresolved_items": result.unresolved_items,
        "scope_assertions": {
            "timesat_run": False,
            "daily_reconstruction_generated": False,
            "withheld_observation_experiment_run": False,
            "reconstruction_metrics_computed": False,
            "vombsjon_performance_inspected": False,
            "processor_selected_from_vombsjon": False,
            "frozen_transfer_setting_changed": False,
            "committed_field_source_modified": False,
            "erken_outputs_modified": False,
        },
    }


def write_audit_outputs(
    result: VombsjonAuditResult,
    *,
    config: VombsjonAuditConfig,
    repository_root: str | Path,
    output_root: str | Path,
    record_absolute_roots: bool = False,
) -> dict[str, Path]:
    """Write the versioned Vombsjon satellite input audit tables and manifest."""

    repository = Path(repository_root)
    requested = Path(output_root)
    if not requested.is_absolute():
        requested = repository / requested
    root = assert_output_path_allowed(
        requested, config, repository_root=repository
    )
    files = config.section("outputs")["files"]

    def target(key: str) -> Path:
        return assert_output_path_allowed(
            root / str(files[key]), config, repository_root=repository
        )

    tables: list[tuple[str, list[dict[str, Any]]]] = [
        ("l1c_inventory", result.l1c_inventory_rows),
        ("l2a_inventory", result.l2a_inventory_rows),
        ("pairing_audit", result.pairing_rows),
        ("acolite_inventory", result.acolite_inventory_rows),
        ("native_qa_inventory", result.native_qa_inventory_rows),
        ("product_extraction_master", result.extraction_rows),
        ("fixed_station_observation_master", result.fixed_observation_rows),
        ("same_day_observation_master", result.same_day_rows),
        ("field_satellite_matchup_master", result.matchup_rows),
        ("extraction_failures", result.failure_rows),
    ]

    written: dict[str, Path] = {}
    for key, rows in tables:
        assert_portable_rows(rows, context=key)
        written[key] = write_rows(rows, target(key))

    manifest = build_manifest(
        result,
        config=config,
        repository_root=repository,
        record_absolute_roots=record_absolute_roots,
    )
    manifest_path = target("manifest")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    written["manifest"] = manifest_path
    return written
