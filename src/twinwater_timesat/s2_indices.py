"""Pixel-level NDCI and MCI with explicit, pre-specified numerical guards.

Indices are computed only after physical reflectance, then QA, then valid-pixel
determination. The primary index is never computed from already spatially
averaged reflectance.

Nothing here is chosen from CHLF, index-versus-field performance, reconstruction
performance or visual preference. The NDCI denominator guard is a numerical
epsilon supplied by the configuration, and the MCI wavelengths are configuration
constants rather than values hidden inside a function.

Invalid values are never silently replaced, and NDCI is never silently clipped
to [-1, 1]; theoretical-range anomalies are recorded as diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


class IndexComputationError(ValueError):
    """Raised when index constants or inputs are unusable."""


@dataclass(frozen=True)
class IndexResult:
    """Pixel-level index values plus the diagnostics needed to audit them."""

    values: np.ndarray
    valid: np.ndarray
    diagnostics: Mapping[str, np.ndarray]

    def diagnostic_counts(self) -> dict[str, int]:
        """Return per-diagnostic pixel counts within the window."""

        return {
            name: int(np.count_nonzero(flags))
            for name, flags in sorted(self.diagnostics.items())
        }


def band_validity(
    reflectance: Mapping[str, np.ndarray],
    hard_invalid: np.ndarray | Mapping[str, np.ndarray],
    *,
    common_hard_invalid: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Determine per-band pixel validity from finite reflectance and hard QA.

    ``hard_invalid`` may be a single mask applied to every band, or a mapping of
    band to that band's own hard-invalid mask. The band-specific form is what
    the pipeline uses, because ``MSK_QUALIT`` is distributed per spectral band:
    a B6 defect must not invalidate B4 or B5, and therefore must not invalidate
    NDCI. ``common_hard_invalid`` carries the product-level conditions
    (``MSK_CLASSI`` cloud/cirrus/snow and the SCL water context) that do apply
    to every band.
    """

    validity: dict[str, np.ndarray] = {}
    per_band = isinstance(hard_invalid, Mapping)

    reference_shape: tuple[int, ...] | None = None
    if common_hard_invalid is not None:
        common = np.asarray(common_hard_invalid).astype(bool)
        reference_shape = common.shape
    else:
        common = None

    for band, values in reflectance.items():
        array = np.asarray(values, dtype="float64")
        if per_band:
            band_mask = hard_invalid.get(band)
            if band_mask is None:
                raise IndexComputationError(
                    f"No hard-invalid QA mask was supplied for band {band!r}; "
                    "Phase 6A does not assume a band is QA-clean."
                )
            invalid = np.asarray(band_mask).astype(bool)
        else:
            invalid = np.asarray(hard_invalid).astype(bool)

        if common is not None:
            if common.shape != invalid.shape:
                raise IndexComputationError(
                    f"Common QA mask shape {common.shape} does not match the "
                    f"band {band!r} QA mask shape {invalid.shape}."
                )
            invalid = invalid | common
        if reference_shape is None:
            reference_shape = invalid.shape

        if array.shape != invalid.shape:
            raise IndexComputationError(
                f"Band {band!r} reflectance shape {array.shape} does not match "
                f"the QA window shape {invalid.shape}."
            )
        validity[band] = np.isfinite(array) & ~invalid
    return validity


def index_validity(
    validity: Mapping[str, np.ndarray], required_bands: tuple[str, ...]
) -> np.ndarray:
    """Combine per-band validity into index-specific validity."""

    missing = [band for band in required_bands if band not in validity]
    if missing:
        raise IndexComputationError(
            f"Index validity requires band(s) {missing}, which were not extracted."
        )
    result = np.ones_like(validity[required_bands[0]], dtype=bool)
    for band in required_bands:
        result &= np.asarray(validity[band]).astype(bool)
    return result


def common_band_validity(
    validity: Mapping[str, np.ndarray], bands: tuple[str, ...] = ("B4", "B5", "B6")
) -> np.ndarray:
    """Return ``common_B456_valid`` for later same-support sensitivity analysis."""

    return index_validity(validity, bands)


def compute_ndci(
    b4: np.ndarray,
    b5: np.ndarray,
    *,
    valid: np.ndarray,
    denominator_epsilon: float,
    require_positive_denominator: bool = True,
    theoretical_min: float = -1.0,
    theoretical_max: float = 1.0,
) -> IndexResult:
    """Compute ``NDCI = (B5 - B4) / (B5 + B4)`` under an explicit guard.

    The denominator must be finite and, when configured, strictly greater than
    ``denominator_epsilon``. Guarded pixels yield ``NaN`` and are flagged; they
    are never replaced by a substitute value.
    """

    if not np.isfinite(denominator_epsilon) or denominator_epsilon <= 0:
        raise IndexComputationError(
            "The NDCI denominator epsilon must be a positive finite number; it "
            "is a pre-specified numerical guard, not a tunable parameter."
        )

    red = np.asarray(b4, dtype="float64")
    rededge = np.asarray(b5, dtype="float64")
    band_valid = np.asarray(valid).astype(bool)
    if red.shape != rededge.shape or red.shape != band_valid.shape:
        raise IndexComputationError(
            "NDCI inputs must share one shape; got "
            f"B4={red.shape}, B5={rededge.shape}, valid={band_valid.shape}."
        )

    denominator = rededge + red
    denominator_finite = np.isfinite(denominator)
    if require_positive_denominator:
        denominator_ok = denominator_finite & (denominator > float(denominator_epsilon))
    else:
        denominator_ok = denominator_finite & (
            np.abs(denominator) > float(denominator_epsilon)
        )

    values = np.full(red.shape, np.nan, dtype="float64")
    computable = band_valid & denominator_ok
    np.divide(
        rededge - red,
        denominator,
        out=values,
        where=computable,
    )
    values = np.where(computable, values, np.nan)

    finite_values = np.isfinite(values)
    result_valid = computable & finite_values

    diagnostics = {
        "denominator_nonfinite": band_valid & ~denominator_finite,
        "denominator_below_epsilon": band_valid
        & denominator_finite
        & ~denominator_ok,
        "nonfinite_result": computable & ~finite_values,
        "below_theoretical_range": finite_values & (values < float(theoretical_min)),
        "above_theoretical_range": finite_values & (values > float(theoretical_max)),
    }
    return IndexResult(values=values, valid=result_valid, diagnostics=diagnostics)


def mci_baseline_coefficient(
    wavelengths: Mapping[str, Any],
    *,
    red: str = "B4",
    rededge: str = "B5",
    outer: str = "B6",
) -> float:
    """Return ``(lambda_B5 - lambda_B4) / (lambda_B6 - lambda_B4)`` from config."""

    try:
        lambda_red = float(wavelengths[red])
        lambda_rededge = float(wavelengths[rededge])
        lambda_outer = float(wavelengths[outer])
    except (KeyError, TypeError, ValueError) as error:
        raise IndexComputationError(
            "MCI requires finite nominal centre wavelengths for "
            f"{red}, {rededge} and {outer} in the pilot configuration."
        ) from error
    span = lambda_outer - lambda_red
    if not np.isfinite(span) or span == 0:
        raise IndexComputationError(
            "MCI baseline span (lambda_B6 - lambda_B4) must be finite and "
            "non-zero."
        )
    return float((lambda_rededge - lambda_red) / span)


def compute_mci(
    b4: np.ndarray,
    b5: np.ndarray,
    b6: np.ndarray,
    *,
    valid: np.ndarray,
    baseline_coefficient: float,
) -> IndexResult:
    """Compute the maximum chlorophyll index against the B4-B6 baseline."""

    if not np.isfinite(baseline_coefficient):
        raise IndexComputationError("MCI baseline coefficient must be finite.")

    red = np.asarray(b4, dtype="float64")
    rededge = np.asarray(b5, dtype="float64")
    outer = np.asarray(b6, dtype="float64")
    band_valid = np.asarray(valid).astype(bool)
    if not (red.shape == rededge.shape == outer.shape == band_valid.shape):
        raise IndexComputationError(
            "MCI inputs must share one shape; got "
            f"B4={red.shape}, B5={rededge.shape}, B6={outer.shape}, "
            f"valid={band_valid.shape}."
        )

    baseline = red + float(baseline_coefficient) * (outer - red)
    values = np.where(band_valid, rededge - baseline, np.nan)

    finite_values = np.isfinite(values)
    result_valid = band_valid & finite_values
    diagnostics = {
        "nonfinite_result": band_valid & ~finite_values,
    }
    return IndexResult(values=values, valid=result_valid, diagnostics=diagnostics)
