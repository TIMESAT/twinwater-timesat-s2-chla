"""NDCI and MCI formulas, guards, and index-specific validity."""

from __future__ import annotations

import numpy as np
import pytest

from twinwater_timesat.s2_indices import (
    IndexComputationError,
    band_validity,
    common_band_validity,
    compute_mci,
    compute_ndci,
    index_validity,
    mci_baseline_coefficient,
)


NOMINAL = {"B4": 665.0, "B5": 705.0, "B6": 740.0}
EPSILON = 1.0e-6


def full(value: float, shape=(3, 3)) -> np.ndarray:
    return np.full(shape, value, dtype="float64")


def test_ndci_matches_the_definition():
    result = compute_ndci(
        full(0.04),
        full(0.06),
        valid=np.ones((3, 3), dtype=bool),
        denominator_epsilon=EPSILON,
    )
    expected = (0.06 - 0.04) / (0.06 + 0.04)
    assert result.values[0, 0] == pytest.approx(expected)
    assert result.valid.all()


def test_ndci_denominator_guard_rejects_near_zero_denominators():
    b4 = np.array([[0.04, 1e-9, -0.05]])
    b5 = np.array([[0.06, 1e-9, 0.05]])
    result = compute_ndci(
        b4,
        b5,
        valid=np.ones((1, 3), dtype=bool),
        denominator_epsilon=EPSILON,
    )
    assert result.valid.tolist() == [[True, False, False]]
    assert np.isnan(result.values[0, 1])
    assert np.isnan(result.values[0, 2])
    assert result.diagnostics["denominator_below_epsilon"].tolist() == [
        [False, True, True]
    ]


def test_ndci_flags_non_finite_denominators():
    result = compute_ndci(
        np.array([[np.nan]]),
        np.array([[0.06]]),
        valid=np.ones((1, 1), dtype=bool),
        denominator_epsilon=EPSILON,
    )
    assert result.diagnostics["denominator_nonfinite"].tolist() == [[True]]
    assert np.isnan(result.values[0, 0])
    assert not result.valid[0, 0]


def test_ndci_is_never_silently_clipped_and_anomalies_are_flagged():
    # A negative B4 can push NDCI outside [-1, 1]; the value is retained.
    result = compute_ndci(
        np.array([[-0.02]]),
        np.array([[0.06]]),
        valid=np.ones((1, 1), dtype=bool),
        denominator_epsilon=EPSILON,
    )
    assert result.values[0, 0] == pytest.approx(0.08 / 0.04)
    assert result.values[0, 0] > 1.0
    assert result.diagnostics["above_theoretical_range"].tolist() == [[True]]
    assert result.valid[0, 0]


def test_ndci_never_replaces_an_invalid_pixel_with_a_substitute():
    valid = np.array([[True, False]])
    result = compute_ndci(
        np.array([[0.04, 0.04]]),
        np.array([[0.06, 0.06]]),
        valid=valid,
        denominator_epsilon=EPSILON,
    )
    assert np.isnan(result.values[0, 1])


def test_ndci_epsilon_must_be_a_positive_finite_number():
    with pytest.raises(IndexComputationError, match="pre-specified numerical guard"):
        compute_ndci(
            full(0.04),
            full(0.06),
            valid=np.ones((3, 3), dtype=bool),
            denominator_epsilon=0.0,
        )


def test_mci_baseline_coefficient_comes_from_configured_wavelengths():
    assert mci_baseline_coefficient(NOMINAL) == pytest.approx(40.0 / 75.0)


def test_mci_matches_the_definition():
    coefficient = mci_baseline_coefficient(NOMINAL)
    result = compute_mci(
        full(0.04),
        full(0.06),
        full(0.05),
        valid=np.ones((3, 3), dtype=bool),
        baseline_coefficient=coefficient,
    )
    expected = 0.06 - (0.04 + coefficient * (0.05 - 0.04))
    assert result.values[0, 0] == pytest.approx(expected)


def test_mci_is_zero_on_a_perfectly_linear_spectrum():
    coefficient = mci_baseline_coefficient(NOMINAL)
    b4, b6 = 0.04, 0.10
    b5 = b4 + coefficient * (b6 - b4)
    result = compute_mci(
        full(b4),
        full(b5),
        full(b6),
        valid=np.ones((3, 3), dtype=bool),
        baseline_coefficient=coefficient,
    )
    assert result.values[0, 0] == pytest.approx(0.0, abs=1e-12)


def test_mci_requires_finite_wavelength_span():
    with pytest.raises(IndexComputationError, match="non-zero"):
        mci_baseline_coefficient({"B4": 665.0, "B5": 705.0, "B6": 665.0})


# --- band-specific QA must not leak across bands -----------------------------


def reflectance_set():
    return {"B4": full(0.04), "B5": full(0.06), "B6": full(0.05)}


def clean_masks():
    return {band: np.zeros((3, 3), dtype=bool) for band in ("B4", "B5", "B6")}


def test_b6_only_hard_invalid_does_not_reduce_ndci():
    masks = clean_masks()
    masks["B6"][0, 0] = True
    validity = band_validity(
        reflectance_set(),
        masks,
        common_hard_invalid=np.zeros((3, 3), dtype=bool),
    )
    # NDCI primary validity is B4 AND B5 only.
    assert index_validity(validity, ("B4", "B5")).sum() == 9


def test_b6_only_hard_invalid_does_reduce_mci_and_common_b456():
    masks = clean_masks()
    masks["B6"][0, 0] = True
    validity = band_validity(
        reflectance_set(),
        masks,
        common_hard_invalid=np.zeros((3, 3), dtype=bool),
    )
    assert index_validity(validity, ("B4", "B5", "B6")).sum() == 8
    assert common_band_validity(validity).sum() == 8


@pytest.mark.parametrize("band", ["B4", "B5"])
def test_b4_or_b5_hard_invalid_reduces_both_indices(band):
    masks = clean_masks()
    masks[band][0, 0] = True
    validity = band_validity(
        reflectance_set(),
        masks,
        common_hard_invalid=np.zeros((3, 3), dtype=bool),
    )
    assert index_validity(validity, ("B4", "B5")).sum() == 8
    assert index_validity(validity, ("B4", "B5", "B6")).sum() == 8


def test_product_level_hard_invalid_reduces_every_index():
    common = np.zeros((3, 3), dtype=bool)
    common[0, 0] = True
    validity = band_validity(reflectance_set(), clean_masks(), common_hard_invalid=common)
    assert index_validity(validity, ("B4", "B5")).sum() == 8
    assert index_validity(validity, ("B4", "B5", "B6")).sum() == 8
    assert common_band_validity(validity).sum() == 8


def test_a_band_without_a_supplied_qa_mask_is_never_assumed_clean():
    with pytest.raises(IndexComputationError, match="does not assume"):
        band_validity(reflectance_set(), {"B4": np.zeros((3, 3), dtype=bool)})


def test_index_specific_validity_differs_between_ndci_and_mci():
    reflectance = {
        "B4": full(0.04),
        "B5": full(0.06),
        "B6": np.array([[np.nan, 0.05, 0.05]] * 3),
    }
    hard_invalid = np.zeros((3, 3), dtype=bool)
    validity = band_validity(reflectance, hard_invalid)

    ndci_valid = index_validity(validity, ("B4", "B5"))
    mci_valid = index_validity(validity, ("B4", "B5", "B6"))
    assert ndci_valid.sum() == 9
    assert mci_valid.sum() == 6


def test_common_b456_valid_is_recorded_separately():
    reflectance = {
        "B4": full(0.04),
        "B5": full(0.06),
        "B6": np.array([[np.nan, 0.05, 0.05]] * 3),
    }
    validity = band_validity(reflectance, np.zeros((3, 3), dtype=bool))
    assert common_band_validity(validity).sum() == 6


def test_hard_qa_invalidity_removes_pixels_before_the_index():
    reflectance = {"B4": full(0.04), "B5": full(0.06)}
    hard_invalid = np.zeros((3, 3), dtype=bool)
    hard_invalid[0, :] = True
    validity = band_validity(reflectance, hard_invalid)
    ndci_valid = index_validity(validity, ("B4", "B5"))
    result = compute_ndci(
        reflectance["B4"],
        reflectance["B5"],
        valid=ndci_valid,
        denominator_epsilon=EPSILON,
    )
    assert result.valid.sum() == 6
    assert np.isnan(result.values[0, 0])


def test_validity_requires_matching_shapes():
    with pytest.raises(IndexComputationError, match="does not match"):
        band_validity({"B4": full(0.04, (2, 2))}, np.zeros((3, 3), dtype=bool))


def test_index_validity_reports_a_missing_band():
    validity = band_validity({"B4": full(0.04)}, np.zeros((3, 3), dtype=bool))
    with pytest.raises(IndexComputationError, match="requires band"):
        index_validity(validity, ("B4", "B5"))
