"""Deterministic L1C/L2A pairing, and explicit failure on ambiguity."""

from __future__ import annotations

import pytest

from twinwater_timesat.s2_pairing import (
    PAIRING_AMBIGUOUS,
    PAIRING_EXACT_UNIQUE,
    PAIRING_METADATA_INCOMPLETE,
    PAIRING_ROOT_NOT_PROVIDED,
    PAIRING_UNMATCHED,
    AcquisitionIdentity,
    build_identity,
    identity_from_product_name,
    normalise_datetime,
    pair_l1c_to_l2a,
    pairing_audit_row,
)


L2A_NAME = "S2A_MSIL2A_20190417T102031_N0500_R065_T34VCM_20221023T092125"
L1C_NAME = "S2A_MSIL1C_20190417T102031_N0500_R065_T34VCM_20221023T092125"


def l2a() -> AcquisitionIdentity:
    identity = identity_from_product_name(L2A_NAME)
    assert identity is not None
    return identity


def l1c(name: str = L1C_NAME) -> AcquisitionIdentity:
    identity = identity_from_product_name(name)
    assert identity is not None
    return identity


def test_identity_is_parsed_from_the_compact_product_name():
    identity = l2a()
    assert identity.level == "L2A"
    assert identity.platform == "S2A"
    assert identity.sensing_datetime_utc == "2019-04-17T10:20:31Z"
    assert identity.tile_id == "T34VCM"
    assert identity.relative_orbit == 65
    assert identity.processing_baseline == "N0500"


def test_metadata_takes_precedence_over_the_product_name():
    identity = build_identity(
        product_id=L2A_NAME,
        level="L2A",
        metadata={
            "spacecraft_name": "Sentinel-2A",
            "sensing_datetime_raw": "2019-04-17T10:20:31.024Z",
            "tile_id": "S2A_OPER_MSI_L2A_TL_T34VCM_N05.00",
            "relative_orbit": 65,
            "processing_baseline": "05.00",
        },
    )
    assert identity.tile_id == "T34VCM"
    assert identity.processing_baseline == "N0500"
    assert identity.sensing_datetime_utc == "2019-04-17T10:20:31Z"


def test_exact_unique_pairing_is_deterministic():
    result = pair_l1c_to_l2a(l2a(), [l1c()])
    assert result.status == PAIRING_EXACT_UNIQUE
    assert result.l1c is not None
    assert result.l1c.product_id == L1C_NAME


def test_pairing_is_not_a_filename_substring_match():
    # Same calendar date and tile, different acquisition time: not a pair.
    other = l1c("S2A_MSIL1C_20190417T104531_N0500_R065_T34VCM_20221023T092125")
    result = pair_l1c_to_l2a(l2a(), [other])
    assert result.status == PAIRING_UNMATCHED
    assert result.l1c is None


def test_different_tile_does_not_pair():
    other = l1c("S2A_MSIL1C_20190417T102031_N0500_R065_T33VWF_20221023T092125")
    assert pair_l1c_to_l2a(l2a(), [other]).status == PAIRING_UNMATCHED


def test_different_platform_does_not_pair():
    other = l1c("S2B_MSIL1C_20190417T102031_N0500_R065_T34VCM_20221023T092125")
    assert pair_l1c_to_l2a(l2a(), [other]).status == PAIRING_UNMATCHED


def test_declared_orbit_mismatch_does_not_pair():
    other = l1c("S2A_MSIL1C_20190417T102031_N0500_R022_T34VCM_20221023T092125")
    assert pair_l1c_to_l2a(l2a(), [other]).status == PAIRING_UNMATCHED


def test_duplicate_candidates_are_an_explicit_ambiguity_failure():
    duplicate = l1c(
        "S2A_MSIL1C_20190417T102031_N0500_R065_T34VCM_20230101T000000"
    )
    result = pair_l1c_to_l2a(l2a(), [l1c(), duplicate])
    assert result.status == PAIRING_AMBIGUOUS
    assert result.l1c is None
    assert len(result.candidate_product_ids) == 2
    assert "does not" in (result.detail or "")


def test_incomplete_l2a_metadata_is_reported_not_guessed():
    incomplete = AcquisitionIdentity(
        product_id="unknown",
        level="L2A",
        platform=None,
        sensing_datetime_utc=None,
        tile_id=None,
        relative_orbit=None,
        processing_baseline=None,
        generation_time_utc=None,
    )
    result = pair_l1c_to_l2a(incomplete, [l1c()])
    assert result.status == PAIRING_METADATA_INCOMPLETE
    assert result.l1c is None


def test_missing_l1c_root_is_its_own_status():
    result = pair_l1c_to_l2a(l2a(), [], l1c_root_provided=False)
    assert result.status == PAIRING_ROOT_NOT_PROVIDED


def test_failed_pairing_still_preserves_the_date_and_l2a_provenance():
    result = pair_l1c_to_l2a(l2a(), [])
    row = pairing_audit_row(
        date="2019-04-17",
        year=2019,
        l2a_representative_status="frozen_representative",
        scl_gate_pass=True,
        l2a=l2a(),
        result=result,
    )
    assert row["date"] == "2019-04-17"
    assert row["l2a_product_id"] == L2A_NAME
    assert row["l1c_pairing_status"] == PAIRING_UNMATCHED
    assert row["l1c_product_id"] is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("20190417T102031", "2019-04-17T10:20:31Z"),
        ("2019-04-17T10:20:31.024Z", "2019-04-17T10:20:31Z"),
        ("not a datetime", None),
        (None, None),
    ],
)
def test_datetime_normalisation(value, expected):
    assert normalise_datetime(value) == expected
