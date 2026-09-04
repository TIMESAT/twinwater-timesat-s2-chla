"""Native QA canonicalization, asset discovery and missing-family handling."""

from __future__ import annotations

import numpy as np
import pytest

from phase6a_fixtures import build_l1c_product, build_l2a_product
from twinwater_timesat.s2_native_qa import (
    QA_ASSET_ABSENT,
    QA_ASSET_PRESENT,
    QA_ASSET_UNSUPPORTED_FORMAT,
    NativeQAError,
    build_native_qa,
    decode_multiband_mask,
    qa_inventory_rows,
    scl_water_mask,
    select_qa_asset,
)
from twinwater_timesat.s2_safe import load_product


# Matches the DRAFT config split: ancillary_lost is diagnostic, not hard.
HARD = ["nodata", "saturated", "defective", "msi_lost", "opaque_cloud", "cirrus"]
DIAGNOSTIC = [
    "partially_corrected",
    "msi_degraded",
    "ancillary_degraded",
    "ancillary_lost",
]
BANDS = ("B4", "B5", "B6")
QUALIT_BANDS = [
    "ancillary_lost",
    "ancillary_degraded",
    "msi_lost",
    "msi_degraded",
    "defective",
    "nodata",
    "partially_corrected",
    "saturated",
]
SHAPE = (3, 3)


def zeros() -> np.ndarray:
    return np.zeros(SHAPE, dtype=bool)


def build(**overrides):
    kwargs = {
        "band_condition_flags": {},
        "common_condition_flags": {},
        "asset_status": {"QUALIT:B04": QA_ASSET_PRESENT},
        "hard_invalid_flags": HARD,
        "diagnostic_flags": DIAGNOSTIC,
        "source_families": {},
        "source_paths": {},
        "window_shape": SHAPE,
        "bands": BANDS,
    }
    kwargs.update(overrides)
    return build_native_qa(**kwargs)


def test_hard_flags_invalidate_pixels_and_diagnostics_do_not():
    nodata = zeros()
    nodata[0, 0] = True
    degraded = zeros()
    degraded[1, 1] = True

    result = build(
        band_condition_flags={"B4": {"nodata": nodata, "msi_degraded": degraded}},
    )
    assert result.hard_invalid_for("B4")[0, 0]
    assert not result.hard_invalid_for("B4")[1, 1]
    assert result.layers["B04_nodata"].category == "hard_invalid"
    assert result.layers["B04_msi_degraded"].category == "diagnostic"


def test_ancillary_lost_is_diagnostic_pending_human_freeze():
    lost = zeros()
    lost[0, 0] = True
    result = build(band_condition_flags={"B4": {"ancillary_lost": lost}})
    assert result.layers["B04_ancillary_lost"].category == "diagnostic"
    assert not result.hard_invalid_for("B4").any()


def test_band_specific_qa_keeps_its_band_provenance():
    flags = zeros()
    flags[0, 0] = True
    result = build(band_condition_flags={"B6": {"nodata": flags}})
    assert result.layers["B06_nodata"].band == "B06"
    assert result.hard_invalid_for("B6")[0, 0]
    # A B6 defect must not leak into B4 or B5.
    assert not result.hard_invalid_for("B4").any()
    assert not result.hard_invalid_for("B5").any()


def test_common_conditions_apply_to_every_band():
    cloud = zeros()
    cloud[0, 0] = True
    result = build(common_condition_flags={"opaque_cloud": cloud})
    for band in BANDS:
        assert result.hard_invalid_for(band)[0, 0]
    assert result.layers["opaque_cloud"].band is None


def test_qa_provenance_is_not_reduced_to_one_boolean():
    result = build(
        band_condition_flags={"B4": {"nodata": zeros(), "msi_degraded": zeros()}},
        common_condition_flags={"cirrus": zeros()},
    )
    assert set(result.counts()) == {"B04_nodata", "B04_msi_degraded", "cirrus"}


def test_an_unconfigured_flag_is_never_categorised_silently():
    with pytest.raises(NativeQAError, match="not classified"):
        build(common_condition_flags={"invented_flag": zeros()})


def test_qa_for_an_unrequested_band_is_refused():
    with pytest.raises(NativeQAError, match="not one of the requested"):
        build(band_condition_flags={"B8A": {"nodata": zeros()}})


def test_missing_qa_family_is_flagged_never_assumed_clean():
    result = build(
        asset_status={
            "QUALIT:B04": QA_ASSET_PRESENT,
            "CLASSI:product": QA_ASSET_ABSENT,
        }
    )
    assert result.native_qa_incomplete
    assert result.incomplete_families == ("CLASSI:product",)
    # Absence does not fabricate validity: no pixel is marked invalid by it.
    assert not result.common_hard_invalid.any()


def test_complete_qa_is_not_flagged_incomplete():
    assert not build().native_qa_incomplete


def test_scl_water_context_invalidates_non_water_pixels():
    scl = np.array([[6, 6, 6], [6, 9, 6], [6, 6, 4]])
    water = scl_water_mask(scl, water_class=6)
    result = build(water_mask=water)
    assert result.common_hard_invalid.sum() == 2
    assert result.layers["scl_not_water"].category == "hard_invalid"


@pytest.mark.parametrize("code", [0, 1, 3, 4, 8, 9, 10, 11])
def test_only_scl_class_six_counts_as_water(code):
    assert not scl_water_mask(np.array([[code]]), water_class=6)[0, 0]


def test_multiband_mask_decoding_maps_configured_conditions():
    values = np.zeros((8, 3, 3), dtype="uint8")
    values[5, 0, 0] = 1
    decoded = decode_multiband_mask(values, QUALIT_BANDS, family="QUALIT")
    assert decoded["nodata"][0, 0]
    assert not decoded["saturated"].any()


def test_band_count_mismatch_refuses_to_guess_the_ordering():
    values = np.zeros((3, 3, 3), dtype="uint8")
    with pytest.raises(NativeQAError, match="refuses to guess"):
        decode_multiband_mask(values, QUALIT_BANDS, family="QUALIT")


def test_condition_shape_must_match_the_frozen_window():
    with pytest.raises(NativeQAError, match="expected"):
        build(common_condition_flags={"nodata": np.zeros((5, 5), dtype=bool)})


def test_qa_asset_selection_prefers_band_specific_rasters(tmp_path):
    product = load_product(build_l2a_product(tmp_path))
    asset, status = select_qa_asset(product, "QUALIT", band="B05")
    assert status == QA_ASSET_PRESENT
    assert asset is not None and asset.band == "B05"


@pytest.mark.parametrize(
    ("requested", "expected"), [("B4", "B04"), ("B5", "B05"), ("B6", "B06")]
)
def test_unpadded_band_request_selects_the_matching_qualit_mask(
    tmp_path, requested, expected
):
    # Config names bands B4/B5/B6 while discovered assets are B04/B05/B06;
    # the request must be canonicalized, not string-compared.
    product = load_product(build_l2a_product(tmp_path))
    asset, status = select_qa_asset(product, "QUALIT", band=requested)
    assert status == QA_ASSET_PRESENT
    assert asset is not None
    assert asset.band == expected
    assert f"MSK_QUALIT_{expected}" in asset.relative_path


def test_a_missing_per_band_mask_never_falls_back_to_another_band(tmp_path):
    root = build_l2a_product(tmp_path)
    for path in root.rglob("MSK_QUALIT_B06.tif"):
        path.unlink()
    product = load_product(root)
    asset, status = select_qa_asset(product, "QUALIT", band="B6")
    assert status == QA_ASSET_ABSENT
    assert asset is None


def test_absent_qa_family_reports_absent(tmp_path):
    product = load_product(build_l1c_product(tmp_path))
    asset, status = select_qa_asset(product, "SATURA")
    assert asset is None
    assert status == QA_ASSET_ABSENT


def test_vector_only_qa_family_is_reported_as_unsupported(tmp_path):
    root = build_l1c_product(tmp_path)
    quality = next(root.rglob("QI_DATA"))
    (quality / "MSK_TECQUA_B04.gml").write_text("<gml/>", encoding="utf-8")
    product = load_product(root)
    asset, status = select_qa_asset(product, "TECQUA", band="B04")
    assert status == QA_ASSET_UNSUPPORTED_FORMAT
    assert asset is not None and asset.is_vector


def test_inventory_reports_present_and_absent_families(tmp_path):
    product = load_product(build_l2a_product(tmp_path))
    rows = qa_inventory_rows(
        product, families=("QUALIT", "CLASSI", "SATURA"), bands=("B4", "B5", "B6")
    )
    families = {row["qa_family"] for row in rows}
    assert {"QUALIT", "CLASSI", "SATURA", "SCL"} <= families
    absent = [row for row in rows if row["qa_family"] == "SATURA"]
    assert absent and absent[0]["asset_status"] == QA_ASSET_ABSENT
