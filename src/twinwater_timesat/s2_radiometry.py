"""Sentinel-2 radiometric metadata harmonization and physical reflectance.

Phase 6A converts digital numbers to physical reflectance using values read
from each product's own metadata:

    reflectance = (DN + add_offset) / quantification_value

``DN / 10000`` is never applied as a universal rule. When a required
quantification value is absent, non-finite or inconsistent, the observation is
retained and an explicit failure is recorded; no constant is invented.

Offset handling is **baseline-aware**. A zero additive offset is only accepted
for products whose processing baseline predates the offset convention. For a
baseline at or after the convention, a missing offset list is an explicit
failure rather than a silent zero, so a malformed product or a parser failure
can never be mistaken for a pre-offset product.

Band identity is resolved from the product's own ``Spectral_Information_List``
where present, with the canonical MSI mapping as a documented fallback. The
source actually used is always reported so the choice stays auditable.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree

import numpy as np


class RadiometryError(ValueError):
    """Raised when product radiometric metadata cannot be used without guessing."""


L1C_METADATA_NAMES: tuple[str, ...] = ("MTD_MSIL1C.xml",)
L2A_METADATA_NAMES: tuple[str, ...] = ("MTD_MSIL2A.xml",)

# Offset conventions differ by level; both resolve to the same conversion rule.
LEVEL_METADATA_TAGS: dict[str, dict[str, str]] = {
    "L1C": {
        "quantification": "QUANTIFICATION_VALUE",
        "offset_list": "Radiometric_Offset_List",
        "offset": "RADIO_ADD_OFFSET",
    },
    "L2A": {
        "quantification": "BOA_QUANTIFICATION_VALUE",
        "offset_list": "BOA_ADD_OFFSET_VALUES_LIST",
        "offset": "BOA_ADD_OFFSET",
    },
}


# Processing baseline at which the radiometric offset convention was
# introduced. Products at or after this baseline are expected to declare
# RADIO_ADD_OFFSET (L1C) or BOA_ADD_OFFSET (L2A).
DEFAULT_OFFSET_CONVENTION_MINIMUM_BASELINE = "N0400"


def normalise_baseline(value: str | None) -> str | None:
    """Return a ``Nxxxx`` processing baseline, or ``None`` if unparseable."""

    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if re.fullmatch(r"N\d{4}", text):
        return text
    decimal = re.fullmatch(r"(\d{2})\.(\d{2})", text)
    if decimal:
        return f"N{decimal.group(1)}{decimal.group(2)}"
    embedded = re.search(r"N\d{4}", text)
    return embedded.group(0) if embedded else None


def baseline_expects_offset(
    baseline: str | None,
    *,
    minimum_baseline: str = DEFAULT_OFFSET_CONVENTION_MINIMUM_BASELINE,
) -> bool | None:
    """Say whether a baseline is expected to declare an additive offset.

    Returns ``True``/``False`` for a parseable baseline and ``None`` when the
    baseline could not be determined at all - in which case the caller must fail
    explicitly rather than guess a convention.
    """

    normalised = normalise_baseline(baseline)
    minimum = normalise_baseline(minimum_baseline)
    if normalised is None or minimum is None:
        return None
    return int(normalised[1:]) >= int(minimum[1:])


def baseline_from_product_name(name: str) -> str | None:
    """Extract a processing baseline from a compact SAFE product name."""

    match = re.search(r"_(N\d{4})_", str(name).upper())
    return match.group(1) if match else None


@dataclass(frozen=True)
class BandRadiometry:
    """Metadata-derived conversion terms for one band of one product."""

    band: str
    band_id: int
    band_id_source: str
    quantification_value: float
    quantification_source: str
    add_offset: float
    offset_source: str
    central_wavelength_nm: float | None

    def conversion_rule(self) -> str:
        """Return the human-readable rule actually applied for this band."""

        return (
            f"(DN + {self.add_offset:g}) / {self.quantification_value:g}"
        )


@dataclass(frozen=True)
class ProductRadiometry:
    """Product-level radiometric metadata plus per-band conversion terms."""

    product_id: str
    level: str
    metadata_relative_path: str | None
    quantification_value: float
    bands: Mapping[str, BandRadiometry]
    processing_baseline: str | None = None
    processing_baseline_source: str | None = None
    offset_expected: bool | None = None


def find_product_metadata(product_path: str | Path, level: str) -> Path | None:
    """Locate the product-level metadata XML for an L1C or L2A product."""

    product = Path(product_path)
    names = L1C_METADATA_NAMES if level.upper() == "L1C" else L2A_METADATA_NAMES
    for name in names:
        direct = product / name
        if direct.is_file():
            return direct
    stem = names[0].rsplit(".", 1)[0]
    matches = sorted(
        path
        for path in product.glob(f"{stem}.*")
        if path.is_file() and path.suffix.lower() == ".xml"
    )
    return matches[0] if matches else None


def _local_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _parse_float(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _canonical_band(band: str) -> str:
    text = str(band).strip().upper()
    if text.endswith("A"):
        stem, suffix = text[:-1], "A"
    else:
        stem, suffix = text, ""
    digits = stem[1:] if stem.startswith("B") else stem
    if not digits.isdigit():
        raise RadiometryError(f"Unrecognised Sentinel-2 band name: {band!r}")
    return f"B{int(digits):02d}{suffix}"


def _band_key(band: str) -> str:
    """Normalise a band name for config lookup (``B04`` and ``B4`` agree)."""

    canonical = _canonical_band(band)
    if canonical.endswith("A"):
        return f"B{int(canonical[1:-1])}A"
    return f"B{int(canonical[1:])}"


def parse_spectral_information(root: ElementTree.Element) -> dict[str, dict[str, Any]]:
    """Read the product's own physical band to band-id and wavelength mapping."""

    information: dict[str, dict[str, Any]] = {}
    for element in root.iter():
        if _local_name(element) != "Spectral_Information":
            continue
        physical = element.attrib.get("physicalBand")
        band_id = element.attrib.get("bandId")
        if not physical or band_id is None:
            continue
        try:
            numeric_id = int(band_id)
        except (TypeError, ValueError):
            continue
        wavelength: float | None = None
        for child in element.iter():
            if _local_name(child) == "CENTRAL":
                wavelength = _parse_float(child.text)
                break
        try:
            key = _band_key(physical)
        except RadiometryError:
            continue
        information[key] = {
            "band_id": numeric_id,
            "central_wavelength_nm": wavelength,
        }
    return information


def parse_offsets(root: ElementTree.Element, level: str) -> dict[int, float] | None:
    """Read per-band additive offsets, or ``None`` when no list is declared.

    ``None`` means the product declares no radiometric offset list at all, which
    is the pre-N0400 convention and implies a zero offset by product definition.
    An empty dictionary means a list exists but declared no usable entry, which
    is an inconsistency the caller must surface rather than absorb.
    """

    tags = LEVEL_METADATA_TAGS[level.upper()]
    list_tag = tags["offset_list"].upper()
    offset_tag = tags["offset"].upper()

    offsets: dict[int, float] | None = None
    for element in root.iter():
        if _local_name(element).upper() != list_tag:
            continue
        offsets = {}
        for child in element.iter():
            if _local_name(child).upper() != offset_tag:
                continue
            band_id = child.attrib.get("band_id", child.attrib.get("bandId"))
            value = _parse_float(child.text)
            if band_id is None or value is None:
                continue
            try:
                offsets[int(band_id)] = value
            except (TypeError, ValueError):
                continue
        break
    return offsets


def parse_quantification(root: ElementTree.Element, level: str) -> float | None:
    """Read the level-appropriate quantification value from product metadata."""

    wanted = LEVEL_METADATA_TAGS[level.upper()]["quantification"].upper()
    for element in root.iter():
        if _local_name(element).upper() == wanted:
            value = _parse_float(element.text)
            if value is not None:
                return value
    return None


def read_product_radiometry(
    product_path: str | Path,
    *,
    product_id: str,
    level: str,
    bands: tuple[str, ...],
    canonical_band_ids: Mapping[str, Any],
    missing_offset_list_is_zero_offset: bool = True,
    offset_convention_minimum_baseline: str = (
        DEFAULT_OFFSET_CONVENTION_MINIMUM_BASELINE
    ),
) -> ProductRadiometry:
    """Build metadata-derived conversion terms for the requested pilot bands.

    ``missing_offset_list_is_zero_offset`` only permits a zero offset for a
    product whose processing baseline predates the offset convention. It never
    permits a zero offset for a baseline that is expected to declare one, and
    never for a product whose baseline could not be determined.
    """

    level_upper = level.upper()
    if level_upper not in LEVEL_METADATA_TAGS:
        raise RadiometryError(
            f"Phase 6A supports only L1C and L2A radiometry; got {level!r}."
        )

    product = Path(product_path)
    metadata_path = find_product_metadata(product, level_upper)
    if metadata_path is None:
        raise RadiometryError(
            f"Product {product_id!r} has no {level_upper} product metadata XML; "
            "reflectance conversion terms cannot be read and must not be assumed."
        )

    try:
        root = ElementTree.parse(metadata_path).getroot()
    except (ElementTree.ParseError, OSError) as error:
        raise RadiometryError(
            f"Product {product_id!r} metadata {metadata_path.name} could not be "
            f"parsed: {error}"
        ) from error

    quantification = parse_quantification(root, level_upper)
    if quantification is None:
        raise RadiometryError(
            f"Product {product_id!r} declares no usable "
            f"{LEVEL_METADATA_TAGS[level_upper]['quantification']}; Phase 6A "
            "does not substitute a default quantification value."
        )
    if quantification == 0:
        raise RadiometryError(
            f"Product {product_id!r} declares a zero quantification value, "
            "which cannot define a reflectance conversion."
        )

    spectral = parse_spectral_information(root)
    offsets = parse_offsets(root, level_upper)

    # Baseline provenance: product metadata first, compact product name second.
    baseline_source = "product_metadata_PROCESSING_BASELINE"
    baseline = None
    for element in root.iter():
        if _local_name(element).upper() == "PROCESSING_BASELINE":
            baseline = normalise_baseline(element.text)
            if baseline:
                break
    if baseline is None:
        baseline = normalise_baseline(baseline_from_product_name(product_id))
        baseline_source = (
            "product_name_fallback" if baseline else "undetermined"
        )
    offset_expected = baseline_expects_offset(
        baseline, minimum_baseline=offset_convention_minimum_baseline
    )

    if offsets is None:
        if offset_expected is None:
            raise RadiometryError(
                f"Product {product_id!r} declares no "
                f"{LEVEL_METADATA_TAGS[level_upper]['offset_list']} and its "
                "processing baseline could not be determined; Phase 6A will not "
                "assume a pre-offset product."
            )
        if offset_expected:
            raise RadiometryError(
                f"Product {product_id!r} has processing baseline {baseline}, at "
                f"or after {offset_convention_minimum_baseline}, so a "
                f"{LEVEL_METADATA_TAGS[level_upper]['offset_list']} is expected but absent. "
                "Phase 6A records this as unusable radiometric "
                "metadata rather than substituting a zero offset."
            )
        if not missing_offset_list_is_zero_offset:
            raise RadiometryError(
                f"Product {product_id!r} declares no "
                f"{LEVEL_METADATA_TAGS[level_upper]['offset_list']} and the "
                "configuration forbids assuming a zero offset."
            )
    elif not offsets:
        raise RadiometryError(
            f"Product {product_id!r} declares a "
            f"{LEVEL_METADATA_TAGS[level_upper]['offset_list']} containing no "
            "usable per-band entry; Phase 6A does not treat a malformed offset "
            "structure as a zero offset."
        )

    resolved: dict[str, BandRadiometry] = {}
    for band in bands:
        key = _band_key(band)
        if key in spectral:
            band_id = int(spectral[key]["band_id"])
            band_id_source = "product_spectral_information_list"
            wavelength = spectral[key]["central_wavelength_nm"]
        elif key in canonical_band_ids:
            band_id = int(canonical_band_ids[key])
            band_id_source = "canonical_msi_fallback"
            wavelength = None
        else:
            raise RadiometryError(
                f"Product {product_id!r} does not declare band {band!r} and no "
                "canonical band-id mapping is configured for it."
            )

        if offsets is None:
            # Reached only for a baseline that predates the offset convention;
            # the zero is a product-definition fact, recorded as such.
            add_offset = 0.0
            offset_source = f"absent_no_offset_list_pre_{offset_convention_minimum_baseline}"
        elif band_id in offsets:
            add_offset = float(offsets[band_id])
            offset_source = "product_offset_list"
        else:
            raise RadiometryError(
                f"Product {product_id!r} declares a "
                f"{LEVEL_METADATA_TAGS[level_upper]['offset_list']} but omits "
                f"band {band!r} (band_id {band_id}); Phase 6A does not infer a "
                "missing per-band offset."
            )

        resolved[key] = BandRadiometry(
            band=key,
            band_id=band_id,
            band_id_source=band_id_source,
            quantification_value=float(quantification),
            quantification_source=(
                f"product_{LEVEL_METADATA_TAGS[level_upper]['quantification']}"
            ),
            add_offset=add_offset,
            offset_source=offset_source,
            central_wavelength_nm=wavelength,
        )

    try:
        metadata_relative = metadata_path.relative_to(product).as_posix()
    except ValueError:  # pragma: no cover - metadata always lives in the product
        metadata_relative = metadata_path.name

    return ProductRadiometry(
        product_id=product_id,
        level=level_upper,
        metadata_relative_path=metadata_relative,
        quantification_value=float(quantification),
        bands=resolved,
        processing_baseline=baseline,
        processing_baseline_source=baseline_source,
        offset_expected=offset_expected,
    )


def to_physical_reflectance(
    digital_numbers: np.ndarray,
    radiometry: BandRadiometry,
    *,
    nodata_value: float | int | None = 0,
) -> np.ndarray:
    """Convert digital numbers to physical reflectance without clamping.

    Negative physical reflectance is preserved. ``nodata_value`` marks DNs that
    carry no radiometry at all (the SAFE zero fill) as ``NaN`` so they cannot be
    mistaken for a measured value; pass ``None`` to disable that mapping.
    """

    values = np.asarray(digital_numbers, dtype="float64")
    reflectance = (values + float(radiometry.add_offset)) / float(
        radiometry.quantification_value
    )
    if nodata_value is not None:
        reflectance = np.where(values == float(nodata_value), np.nan, reflectance)
    return reflectance


def reflectance_range_flags(
    reflectance: np.ndarray, *, minimum: float, maximum: float
) -> dict[str, np.ndarray]:
    """Flag out-of-range and non-finite reflectance without altering values."""

    values = np.asarray(reflectance, dtype="float64")
    finite = np.isfinite(values)
    return {
        "nonfinite": ~finite,
        "below_range": finite & (values < float(minimum)),
        "above_range": finite & (values > float(maximum)),
    }


def sensing_metadata(product_path: str | Path, level: str) -> dict[str, Any]:
    """Read acquisition identity fields used for deterministic product pairing."""

    product = Path(product_path)
    metadata_path = find_product_metadata(product, level)
    values: dict[str, Any] = {
        "product_uri": None,
        "sensing_datetime_raw": None,
        "spacecraft_name": None,
        "processing_baseline": None,
        "relative_orbit": None,
        "generation_time": None,
        "tile_id": None,
    }
    if metadata_path is None:
        return values
    try:
        root = ElementTree.parse(metadata_path).getroot()
    except (ElementTree.ParseError, OSError):
        return values

    wanted = {
        "PRODUCT_URI": "product_uri",
        "DATATAKE_SENSING_START": "sensing_datetime_raw",
        "PRODUCT_START_TIME": "product_start_time",
        "SENSING_TIME": "sensing_time",
        "SPACECRAFT_NAME": "spacecraft_name",
        "PROCESSING_BASELINE": "processing_baseline",
        "SENSING_ORBIT_NUMBER": "relative_orbit",
        "GENERATION_TIME": "generation_time",
        "TILE_ID": "tile_id",
    }
    seen: dict[str, str] = {}
    for element in root.iter():
        name = _local_name(element).upper()
        text = (element.text or "").strip()
        if name in wanted and text and name not in seen:
            seen[name] = text

    for tag, key in wanted.items():
        if tag in seen:
            values[key] = seen[tag]
    if not values.get("sensing_datetime_raw"):
        values["sensing_datetime_raw"] = seen.get("PRODUCT_START_TIME") or seen.get(
            "SENSING_TIME"
        )
    orbit = values.get("relative_orbit")
    if orbit is not None:
        match = re.search(r"\d+", str(orbit))
        values["relative_orbit"] = int(match.group(0)) if match else None
    return values
