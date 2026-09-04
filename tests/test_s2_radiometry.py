"""Metadata-driven reflectance conversion, offsets, baselines and failures."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from phase6a_fixtures import (
    CANONICAL_BAND_IDS,
    build_l1c_product,
    build_l2a_product,
    l1c_metadata_xml,
    l2a_metadata_xml,
    product_name,
)
from twinwater_timesat.s2_radiometry import (
    RadiometryError,
    baseline_expects_offset,
    normalise_baseline,
    read_product_radiometry,
    reflectance_range_flags,
    sensing_metadata,
    to_physical_reflectance,
)


BANDS = ("B4", "B5", "B6")


def read(product: Path, level: str, **kwargs):
    return read_product_radiometry(
        product,
        product_id=product.name,
        level=level,
        bands=BANDS,
        canonical_band_ids=CANONICAL_BAND_IDS,
        **kwargs,
    )


def test_l1c_conversion_uses_product_quantification_and_offset(tmp_path):
    product = build_l1c_product(tmp_path)
    radiometry = read(product, "L1C")
    terms = radiometry.bands["B4"]
    assert terms.quantification_value == 10000.0
    assert terms.add_offset == -1000.0
    assert terms.offset_source == "product_offset_list"
    assert terms.band_id_source == "product_spectral_information_list"
    assert terms.conversion_rule() == "(DN + -1000) / 10000"

    values = to_physical_reflectance(np.array([[1400.0]]), terms)
    # (1400 - 1000) / 10000 = 0.04, not the naive 1400/10000 = 0.14.
    assert values[0, 0] == pytest.approx(0.04)


def test_l2a_conversion_uses_boa_quantification_and_boa_offset(tmp_path):
    product = build_l2a_product(tmp_path)
    radiometry = read(product, "L2A")
    terms = radiometry.bands["B5"]
    assert terms.quantification_source == "product_BOA_QUANTIFICATION_VALUE"
    assert terms.add_offset == -1000.0
    assert to_physical_reflectance(np.array([[1500.0]]), terms)[0, 0] == pytest.approx(
        0.05
    )


# --- baseline-aware offset handling ------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("N0500", "N0500"), ("05.00", "N0500"), ("02.09", "N0209"), ("", None)],
)
def test_baseline_normalisation(value, expected):
    assert normalise_baseline(value) == expected


@pytest.mark.parametrize(
    ("baseline", "expected"),
    [("N0400", True), ("N0500", True), ("N0399", False), ("N0209", False)],
)
def test_baseline_offset_expectation(baseline, expected):
    assert baseline_expects_offset(baseline) is expected


def test_undetermined_baseline_has_no_offset_expectation():
    assert baseline_expects_offset(None) is None


def test_pre_offset_baseline_without_an_offset_list_records_zero_offset(tmp_path):
    name = product_name("L1C")
    product = build_l1c_product(
        tmp_path,
        metadata_xml=l1c_metadata_xml(
            product_uri=f"{name}.SAFE", offset=None, baseline="02.09"
        ),
    )
    radiometry = read(product, "L1C")
    terms = radiometry.bands["B4"]
    assert radiometry.processing_baseline == "N0209"
    assert radiometry.offset_expected is False
    assert terms.add_offset == 0.0
    assert terms.offset_source == "absent_no_offset_list_pre_N0400"
    assert to_physical_reflectance(np.array([[1400.0]]), terms)[0, 0] == pytest.approx(
        0.14
    )


@pytest.mark.parametrize("baseline", ["04.00", "05.00", "05.11"])
def test_offset_era_baseline_without_an_offset_list_is_a_failure(tmp_path, baseline):
    name = product_name("L1C")
    product = build_l1c_product(
        tmp_path,
        metadata_xml=l1c_metadata_xml(
            product_uri=f"{name}.SAFE", offset=None, baseline=baseline
        ),
    )
    with pytest.raises(RadiometryError, match="expected\n?.*but absent|is expected"):
        read(product, "L1C")


def test_n0500_product_with_a_valid_offset_list_converts_correctly(tmp_path):
    product = build_l2a_product(tmp_path)
    radiometry = read(product, "L2A")
    assert radiometry.processing_baseline == "N0500"
    assert radiometry.offset_expected is True
    terms = radiometry.bands["B4"]
    assert terms.offset_source == "product_offset_list"
    assert to_physical_reflectance(np.array([[1200.0]]), terms)[0, 0] == pytest.approx(
        0.02
    )


def test_misnamed_offset_structure_in_an_n05xx_product_fails(tmp_path):
    # The offset list tag is present but misspelled, so the parser sees no list.
    # A parser failure must not be interpreted as a pre-offset product.
    name = product_name("L2A")
    xml = l2a_metadata_xml(product_uri=f"{name}.SAFE").replace(
        "BOA_ADD_OFFSET_VALUES_LIST", "BOA_ADD_OFFSET_VALUE_LIST"
    )
    product = build_l2a_product(tmp_path, metadata_xml=xml)
    with pytest.raises(RadiometryError, match="is expected"):
        read(product, "L2A")


def test_empty_offset_list_is_a_failure_not_a_zero_offset(tmp_path):
    name = product_name("L2A")
    xml = l2a_metadata_xml(product_uri=f"{name}.SAFE").replace(
        '<BOA_ADD_OFFSET band_id="3">-1000</BOA_ADD_OFFSET>'
        '<BOA_ADD_OFFSET band_id="4">-1000</BOA_ADD_OFFSET>'
        '<BOA_ADD_OFFSET band_id="5">-1000</BOA_ADD_OFFSET>',
        "",
    )
    product = build_l2a_product(tmp_path, metadata_xml=xml)
    with pytest.raises(RadiometryError, match="no usable per-band entry"):
        read(product, "L2A")


def test_undetermined_baseline_without_an_offset_list_is_a_failure(tmp_path):
    name = product_name("L1C")
    xml = l1c_metadata_xml(
        product_uri="unparseable_product_uri", offset=None, baseline=None
    )
    product = build_l1c_product(tmp_path, metadata_xml=xml)
    with pytest.raises(RadiometryError, match="could not be determined"):
        read_product_radiometry(
            product,
            product_id="unparseable_product_uri",
            level="L1C",
            bands=BANDS,
            canonical_band_ids=CANONICAL_BAND_IDS,
        )


def test_pre_offset_zero_offset_can_still_be_forbidden_by_configuration(tmp_path):
    name = product_name("L1C")
    product = build_l1c_product(
        tmp_path,
        metadata_xml=l1c_metadata_xml(
            product_uri=f"{name}.SAFE", offset=None, baseline="02.09"
        ),
    )
    with pytest.raises(RadiometryError, match="forbids assuming a zero offset"):
        read(product, "L1C", missing_offset_list_is_zero_offset=False)


def test_offset_list_missing_a_required_band_is_an_explicit_failure(tmp_path):
    name = product_name("L2A")
    product = build_l2a_product(
        tmp_path,
        metadata_xml=l2a_metadata_xml(
            product_uri=f"{name}.SAFE", include_bands={"B4": 3}
        ),
    )
    with pytest.raises(RadiometryError, match="omits band"):
        read(product, "L2A")


def test_missing_quantification_value_never_falls_back_to_10000(tmp_path):
    name = product_name("L2A")
    product = build_l2a_product(
        tmp_path,
        metadata_xml=l2a_metadata_xml(
            product_uri=f"{name}.SAFE", quantification=None
        ),
    )
    with pytest.raises(RadiometryError, match="does not substitute a default"):
        read(product, "L2A")


def test_missing_product_metadata_is_an_explicit_failure(tmp_path):
    product = build_l1c_product(tmp_path)
    (product / "MTD_MSIL1C.xml").unlink()
    with pytest.raises(RadiometryError, match="no L1C product metadata"):
        read(product, "L1C")


def test_band_id_falls_back_to_the_canonical_map_and_says_so(tmp_path):
    name = product_name("L1C")
    product = build_l1c_product(
        tmp_path,
        metadata_xml=l1c_metadata_xml(
            product_uri=f"{name}.SAFE", spectral_information=False
        ),
    )
    terms = read(product, "L1C").bands["B6"]
    assert terms.band_id == 5
    assert terms.band_id_source == "canonical_msi_fallback"
    assert terms.central_wavelength_nm is None


def test_processing_baseline_metadata_is_normalised(tmp_path):
    product = build_l2a_product(tmp_path)
    metadata = sensing_metadata(product, "L2A")
    assert metadata["processing_baseline"] == "05.00"
    assert read(product, "L2A").processing_baseline_source == (
        "product_metadata_PROCESSING_BASELINE"
    )
    assert metadata["relative_orbit"] == 65
    assert metadata["spacecraft_name"] == "Sentinel-2A"


def test_negative_reflectance_is_preserved_not_clamped(tmp_path):
    product = build_l1c_product(tmp_path)
    terms = read(product, "L1C").bands["B4"]
    values = to_physical_reflectance(np.array([[500.0]]), terms)
    assert values[0, 0] == pytest.approx(-0.05)


def test_zero_digital_number_is_treated_as_absent_radiometry(tmp_path):
    product = build_l1c_product(tmp_path)
    terms = read(product, "L1C").bands["B4"]
    values = to_physical_reflectance(np.array([[0.0]]), terms)
    assert np.isnan(values[0, 0])


def test_range_flags_report_anomalies_without_altering_values():
    values = np.array([[-0.05, 0.4, 1.4, np.nan]])
    flags = reflectance_range_flags(values, minimum=0.0, maximum=1.0)
    assert flags["below_range"].tolist() == [[True, False, False, False]]
    assert flags["above_range"].tolist() == [[False, False, True, False]]
    assert flags["nonfinite"].tolist() == [[False, False, False, True]]
