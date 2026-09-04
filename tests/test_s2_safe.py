"""Layout-tolerant SAFE discovery across processing levels and conventions."""

from __future__ import annotations

import pytest

from phase6a_fixtures import build_l1c_product, build_l2a_product, product_name
from twinwater_timesat.s2_safe import (
    SAFEDiscoveryError,
    discover_band_assets,
    discover_products,
    load_product,
    product_level,
    select_band_asset,
)


def test_processing_level_is_read_from_the_product_name():
    assert product_level(product_name("L1C")) == "L1C"
    assert product_level(product_name("L2A")) == "L2A"
    assert product_level("something_else") is None


def test_discovery_separates_l1c_and_l2a_roots(tmp_path):
    l1c_root = tmp_path / "L1C"
    l2a_root = tmp_path / "L2A"
    build_l1c_product(l1c_root)
    build_l2a_product(l2a_root)

    assert len(discover_products(l1c_root, level="L1C")) == 1
    assert discover_products(l1c_root, level="L2A") == []
    assert len(discover_products(l2a_root, level="L2A")) == 1


def test_discovery_does_not_descend_into_granules(tmp_path):
    root = tmp_path / "archive"
    build_l2a_product(root)
    products = discover_products(root)
    assert len(products) == 1
    assert products[0].name.endswith(".SAFE")


def test_discovery_handles_a_nested_year_directory_layout(tmp_path):
    root = tmp_path / "archive"
    build_l2a_product(root / "2019")
    build_l2a_product(root / "2020", platform="S2B")
    assert len(discover_products(root, level="L2A")) == 2


def test_missing_root_is_an_explicit_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        discover_products(tmp_path / "absent")


def test_l1c_layout_keeps_flat_img_data_bands(tmp_path):
    product = load_product(build_l1c_product(tmp_path))
    assert product.level == "L1C"
    bands = {asset.band for asset in product.band_assets}
    assert {"B04", "B05", "B06"} <= bands
    assert product.scl_assets == ()


def test_l2a_layout_separates_resolution_directories(tmp_path):
    product = load_product(build_l2a_product(tmp_path))
    assert product.level == "L2A"
    b4_assets = product.bands_for("B4")
    assert len(b4_assets) == 2
    assert {asset.resolution_directory for asset in b4_assets} == {"R10M", "R20M"}
    assert len(product.scl_assets) == 1


def test_r20m_b4_is_preferred_for_the_frozen_analysis_grid(tmp_path):
    product = load_product(build_l2a_product(tmp_path))
    asset = select_band_asset(product, "B4", prefer_resolution_m=20)
    assert asset.declared_resolution_m == 20
    assert "R20m" in asset.relative_path


def test_l1c_b4_has_only_its_native_10m_asset(tmp_path):
    product = load_product(build_l1c_product(tmp_path))
    asset = select_band_asset(product, "B4", prefer_resolution_m=20)
    # No 20 m B4 exists at L1C; discovery returns the native asset so the
    # pipeline can reduce it, rather than silently substituting another band.
    assert asset.declared_resolution_m is None


def test_unresolved_band_ambiguity_is_an_explicit_failure(tmp_path):
    root = build_l1c_product(tmp_path)
    image = next(root.rglob("IMG_DATA"))
    duplicate = image / "T34VCM_20190417T102031_dup_B05.tif"
    duplicate.write_bytes((image / "T34VCM_20190417T102031_B05.tif").read_bytes())
    product = load_product(root)
    with pytest.raises(SAFEDiscoveryError, match="equally"):
        select_band_asset(product, "B5", prefer_resolution_m=20)


def test_missing_band_is_an_explicit_failure(tmp_path):
    product = load_product(build_l1c_product(tmp_path))
    with pytest.raises(SAFEDiscoveryError, match="no raster for band"):
        select_band_asset(product, "B7")


def test_qi_data_is_not_mistaken_for_band_data(tmp_path):
    product = load_product(build_l2a_product(tmp_path))
    assert all(
        "QI_DATA" not in asset.relative_path for asset in product.band_assets
    )


def test_qa_assets_record_family_band_and_kind(tmp_path):
    product = load_product(build_l2a_product(tmp_path))
    qualit = product.qa_family("QUALIT")
    assert {asset.band for asset in qualit} == {"B04", "B05", "B06"}
    classi = product.qa_family("CLASSI")
    assert len(classi) == 1
    assert classi[0].band is None
    assert classi[0].is_raster


def test_a_directory_without_a_recognisable_level_is_refused(tmp_path):
    root = tmp_path / "not_a_product"
    root.mkdir()
    with pytest.raises(SAFEDiscoveryError, match="refuses to guess"):
        load_product(root)


def test_band_assets_are_empty_for_a_missing_product(tmp_path):
    assert discover_band_assets(tmp_path / "absent") == ()
