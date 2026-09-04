"""End-to-end Phase 6A extraction on minimal controlled SAFE fixtures."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from phase6a_fixtures import (
    B04_SINGLE_FINE_CELL,
    OPAQUE_COARSE_CELL,
    OPAQUE_COARSE_CELL_SINGLE,
    OPAQUE_WINDOW_PIXELS,
    OPAQUE_WINDOW_PIXELS_SINGLE,
    TARGET_SIZE,
    build_l1c_product,
    build_l2a_product,
    product_name,
    write_frozen_mask_csv,
)
from twinwater_timesat.s2_pilot import (
    PilotExecutionError,
    extract_product,
    read_frozen_observation_mask,
    run_pilot,
    write_outputs,
)
from twinwater_timesat.s2_pilot_config import (
    PilotScopeError,
    default_pilot_config_path,
    load_pilot_config,
)
from twinwater_timesat.s2_safe import load_product


ROOT = Path(__file__).resolve().parents[1]
L2A_ID = product_name("L2A")
L1C_ID = product_name("L1C")


@pytest.fixture(scope="module")
def config():
    return load_pilot_config(default_pilot_config_path(ROOT), repository_root=ROOT)


@pytest.fixture
def repository(tmp_path, config):
    """A minimal repository stand-in carrying a frozen-mask table."""

    write_frozen_mask_csv(
        tmp_path / "data" / "processed" / "erken_s2_observation_mask.csv",
        [
            {
                "date": "2019-04-17",
                "year": 2019,
                "s2_date_usable": "True",
                "selected_product_id": L2A_ID,
            },
            {
                "date": "2019-04-19",
                "year": 2019,
                "s2_date_usable": "False",
                "selected_product_id": "",
            },
        ],
    )
    return tmp_path


def base_row() -> dict:
    return {"date": "2019-04-17", "year": 2019, "failure_reason": None}


# --- single-product extraction -------------------------------------------------


def test_l2a_extraction_produces_indices_on_the_frozen_window(tmp_path, config):
    product = load_product(build_l2a_product(tmp_path))
    outcome = extract_product(
        product, config=config, scl_product=product, base_row=base_row()
    )
    row = outcome.row
    assert outcome.failure_reason is None
    assert row["NDCI_valid_pixel_count"] == 9
    assert row["MCI_valid_pixel_count"] == 9
    assert row["common_B456_valid_count"] == 9
    # (1500-1000)/10000 = 0.05 and (1200-1000)/10000 = 0.02.
    assert row["NDCI_median"] == pytest.approx((0.05 - 0.02) / (0.05 + 0.02))


def test_l1c_extraction_reduces_10m_b4_onto_the_20m_grid(tmp_path, config):
    l2a = load_product(build_l2a_product(tmp_path / "L2A"))
    l1c = load_product(build_l1c_product(tmp_path / "L1C"))
    outcome = extract_product(
        l1c, config=config, scl_product=l2a, base_row=base_row()
    )
    row = outcome.row
    assert outcome.failure_reason is None
    assert row["B4_grid_alignment"] == "block_mean_reduce_x2"
    assert row["B5_grid_alignment"] == "native_target_grid"
    assert row["NDCI_valid_pixel_count"] == 9
    # L1C fixture DNs: B4 1400 -> 0.04, B5 1600 -> 0.06.
    assert row["NDCI_median"] == pytest.approx((0.06 - 0.04) / (0.06 + 0.04))


def test_qa_is_applied_before_the_index_and_reduces_valid_pixels(tmp_path, config):
    # A product-level opaque-cloud cell invalidates every band.
    product = load_product(
        build_l2a_product(
            tmp_path, classi_flags=[("opaque_cloud", OPAQUE_COARSE_CELL)]
        )
    )
    outcome = extract_product(
        product, config=config, scl_product=product, base_row=base_row()
    )
    row = outcome.row
    assert row["qa_opaque_cloud"] == OPAQUE_WINDOW_PIXELS
    assert row["NDCI_valid_pixel_count"] == 9 - OPAQUE_WINDOW_PIXELS
    assert row["MCI_valid_pixel_count"] == 9 - OPAQUE_WINDOW_PIXELS


# --- Issue 2: a QA mask finer than the 20 m target grid ----------------------


def test_one_invalid_10m_b4_qualit_subpixel_invalidates_its_20m_pixel(
    tmp_path, config
):
    # L1C MSK_QUALIT_B04 is 10 m while the frozen support is 20 m. Exactly one
    # 10 m subpixel is flagged; conservative any-invalid reduction must make the
    # containing 20 m pixel invalid.
    l2a = load_product(build_l2a_product(tmp_path / "L2A"))
    l1c = load_product(
        build_l1c_product(
            tmp_path / "L1C",
            qualit_flags={"B04": [("nodata", B04_SINGLE_FINE_CELL)]},
        )
    )
    outcome = extract_product(
        l1c, config=config, scl_product=l2a, base_row=base_row()
    )
    row = outcome.row
    assert row["qa_qualit_b04_grid_alignment"] == "any_invalid_reduce_x2"
    assert row["qa_B04_nodata"] == 1
    assert row["B4_valid_count"] == 8
    assert row["NDCI_valid_pixel_count"] == 8
    assert row["MCI_valid_pixel_count"] == 8


def test_target_resolution_qa_mask_is_read_directly(tmp_path, config):
    l2a = load_product(build_l2a_product(tmp_path / "L2A"))
    l1c = load_product(
        build_l1c_product(
            tmp_path / "L1C", qualit_flags={"B05": [("nodata", (4, 4))]}
        )
    )
    row = extract_product(
        l1c, config=config, scl_product=l2a, base_row=base_row()
    ).row
    assert row["qa_qualit_b05_grid_alignment"] == "native_target_grid"
    assert row["qa_B05_nodata"] == 1


def test_coarse_qa_mask_is_expanded_by_exact_footprint(tmp_path, config):
    product = load_product(
        build_l2a_product(
            tmp_path, classi_flags=[("cirrus", OPAQUE_COARSE_CELL_SINGLE)]
        )
    )
    row = extract_product(
        product, config=config, scl_product=product, base_row=base_row()
    ).row
    assert row["qa_classi_product_grid_alignment"] == "exact_footprint_expand_x3"
    assert row["qa_cirrus"] == OPAQUE_WINDOW_PIXELS_SINGLE


# --- Issue 3: band-specific QA must not collapse across bands ----------------


def test_b6_only_qa_defect_does_not_reduce_ndci(tmp_path, config):
    product = load_product(
        build_l2a_product(tmp_path, qualit_flags={"B06": [("nodata", (4, 4))]})
    )
    row = extract_product(
        product, config=config, scl_product=product, base_row=base_row()
    ).row
    assert row["qa_B06_nodata"] == 1
    assert row["B6_valid_count"] == 8
    assert row["B4_valid_count"] == 9
    assert row["B5_valid_count"] == 9
    # NDCI requires B4 and B5 only.
    assert row["NDCI_valid_pixel_count"] == 9
    # MCI and common_B456 do require B6.
    assert row["MCI_valid_pixel_count"] == 8
    assert row["common_B456_valid_count"] == 8


@pytest.mark.parametrize(
    ("mask_band", "reflectance_band"), [("B04", "B4"), ("B05", "B5")]
)
def test_b4_or_b5_qa_defect_reduces_both_indices(
    tmp_path, config, mask_band, reflectance_band
):
    cell = B04_SINGLE_FINE_CELL if mask_band == "B04" else (4, 4)
    product = load_product(
        build_l2a_product(tmp_path, qualit_flags={mask_band: [("nodata", cell)]})
    )
    row = extract_product(
        product, config=config, scl_product=product, base_row=base_row()
    ).row
    assert row[f"{reflectance_band}_valid_count"] == 8
    assert row["NDCI_valid_pixel_count"] == 8
    assert row["MCI_valid_pixel_count"] == 8


def test_band_provenance_is_retained_in_the_output_row(tmp_path, config):
    product = load_product(
        build_l2a_product(tmp_path, qualit_flags={"B06": [("nodata", (4, 4))]})
    )
    row = extract_product(
        product, config=config, scl_product=product, base_row=base_row()
    ).row
    # Per-band column keeps provenance; the aggregate column supplies the
    # canonical schema field.
    assert row["qa_B06_nodata"] == 1
    assert row["qa_B06_nodata_band"] == "B06"
    assert row["qa_nodata"] == 1


def test_ancillary_lost_is_diagnostic_and_does_not_invalidate(tmp_path, config):
    product = load_product(
        build_l2a_product(
            tmp_path, qualit_flags={"B05": [("ancillary_lost", (4, 4))]}
        )
    )
    row = extract_product(
        product, config=config, scl_product=product, base_row=base_row()
    ).row
    assert row["qa_B05_ancillary_lost"] == 1
    assert row["B5_valid_count"] == 9
    assert row["NDCI_valid_pixel_count"] == 9


def test_scl_water_context_excludes_non_water_pixels(tmp_path, config):
    scl = np.full((TARGET_SIZE, TARGET_SIZE), 6, dtype="uint8")
    scl[4, 4] = 9  # cloud high probability inside the frozen window
    scl[5, 5] = 4  # vegetation
    product = load_product(build_l2a_product(tmp_path, scl_values=scl))
    outcome = extract_product(
        product, config=config, scl_product=product, base_row=base_row()
    )
    assert outcome.row["qa_scl_not_water"] == 2
    assert outcome.row["NDCI_valid_pixel_count"] == 7


def test_l1c_without_a_paired_l2a_scl_is_an_explicit_failure(tmp_path, config):
    l1c = load_product(build_l1c_product(tmp_path))
    outcome = extract_product(
        l1c, config=config, scl_product=None, base_row=base_row()
    )
    assert outcome.failure_reason == "no_paired_l2a_scl_for_common_water_context"
    # No index is produced on a different spatial support; the row survives.
    assert "NDCI_valid_pixel_count" not in outcome.row
    assert outcome.row["date"] == "2019-04-17"


def test_unusable_radiometric_metadata_keeps_the_row(tmp_path, config):
    root = build_l2a_product(tmp_path)
    (root / "MTD_MSIL2A.xml").unlink()
    product = load_product(root)
    outcome = extract_product(
        product, config=config, scl_product=product, base_row=base_row()
    )
    assert outcome.failure_reason is not None
    assert outcome.failure_reason.startswith("radiometric_metadata_unusable")
    assert outcome.row["date"] == "2019-04-17"


def test_missing_qa_family_flags_the_row_without_assuming_clean(tmp_path, config):
    root = build_l2a_product(tmp_path)
    for path in root.rglob("MSK_CLASSI_B00.tif"):
        path.unlink()
    product = load_product(root)
    outcome = extract_product(
        product, config=config, scl_product=product, base_row=base_row()
    )
    assert outcome.row["native_qa_incomplete"] is True
    assert "CLASSI" in outcome.row["native_qa_incomplete_families"]
    assert outcome.row["NDCI_valid_pixel_count"] == 9


def test_extraction_records_the_conversion_rule_actually_used(tmp_path, config):
    product = load_product(build_l2a_product(tmp_path))
    row = extract_product(
        product, config=config, scl_product=product, base_row=base_row()
    ).row
    assert row["B4_conversion_rule"] == "(DN + -1000) / 10000"
    assert row["ndci_has_any_valid_pixel"] is True
    assert "ndci_qc_pass" not in row
    assert row["final_valid_pixel_threshold_status"] == (
        "NOT_SELECTED_REQUIRES_HUMAN_FREEZE"
    )
    assert row["radiometry_processing_baseline"] == "N0500"
    assert row["B4_offset_source"] == "product_offset_list"
    assert row["quantification_value"] == 10000.0
    assert row["target_grid_pixel_size_x"] == 20.0


# --- full run ------------------------------------------------------------------


def run(repository, config, *, l1c_root, l2a_root):
    return run_pilot(
        config=config,
        repository_root=repository,
        l2a_root=l2a_root,
        l1c_root=l1c_root,
    )


def test_run_pairs_products_and_retains_every_frozen_date(tmp_path, repository, config):
    l2a_root = tmp_path / "archive" / "L2A"
    l1c_root = tmp_path / "archive" / "L1C"
    build_l2a_product(l2a_root)
    build_l1c_product(l1c_root)

    result = run(repository, config, l1c_root=l1c_root, l2a_root=l2a_root)

    assert result.counts["candidate_dates"] == 2
    assert result.counts["frozen_representative_l2a_dates"] == 1
    assert result.counts["exact_l1c_l2a_pairs"] == 1
    assert result.counts["dates_without_l2a_representative"] == 1
    # A date the frozen SCL gate rejected is not an L1C pairing failure.
    assert result.counts["unmatched_or_ambiguous_dates"] == 0
    assert {row["date"] for row in result.pairing_rows} == {
        "2019-04-17",
        "2019-04-19",
    }

    levels = {
        (row["date"], row.get("product_level")) for row in result.extraction_rows
    }
    assert ("2019-04-17", "L2A") in levels
    assert ("2019-04-17", "L1C") in levels
    # The SCL-gate-failed date is preserved with an explicit reason.
    failed = [row for row in result.extraction_rows if row["date"] == "2019-04-19"]
    assert len(failed) == 1
    assert failed[0]["failure_reason"] == (
        "no_frozen_representative_l2a_product_for_date"
    )


def test_run_without_an_l1c_root_records_the_status_and_keeps_l2a(
    tmp_path, repository, config
):
    l2a_root = tmp_path / "archive" / "L2A"
    build_l2a_product(l2a_root)

    result = run(repository, config, l1c_root=None, l2a_root=l2a_root)

    statuses = {row["l1c_pairing_status"] for row in result.pairing_rows}
    assert statuses == {"l1c_root_not_provided", "no_l2a_representative_for_date"}
    l2a_rows = [
        row for row in result.extraction_rows if row.get("product_level") == "L2A"
    ]
    assert l2a_rows and l2a_rows[0]["NDCI_valid_pixel_count"] == 9


def test_ambiguous_l1c_pairing_prevents_l1c_extraction(tmp_path, repository, config):
    l2a_root = tmp_path / "archive" / "L2A"
    l1c_root = tmp_path / "archive" / "L1C"
    build_l2a_product(l2a_root)
    original = build_l1c_product(l1c_root)
    duplicate = l1c_root / f"{L1C_ID.replace('20221023', '20230101')}.SAFE"
    subprocess.run(["cp", "-R", str(original), str(duplicate)], check=True)

    result = run(repository, config, l1c_root=l1c_root, l2a_root=l2a_root)

    pairing = [row for row in result.pairing_rows if row["l2a_product_id"]][0]
    assert pairing["l1c_pairing_status"] == "ambiguous_multiple_candidates"
    assert pairing["l1c_candidate_count"] == 2
    l1c_rows = [
        row for row in result.extraction_rows if row.get("product_level") == "L1C"
    ]
    assert l1c_rows[0]["failure_reason"].startswith("l1c_not_extracted")


def test_missing_frozen_mask_is_an_explicit_error(tmp_path, config):
    with pytest.raises(PilotExecutionError, match="Frozen observation mask"):
        read_frozen_observation_mask(tmp_path / "absent.csv")


# --- outputs -------------------------------------------------------------------


def test_outputs_are_confined_to_the_phase6a_namespace(tmp_path, repository, config):
    l2a_root = tmp_path / "archive" / "L2A"
    build_l2a_product(l2a_root)
    result = run(repository, config, l1c_root=None, l2a_root=l2a_root)

    output_root = repository / "results" / "phase6a"
    written = write_outputs(
        result,
        config=config,
        repository_root=repository,
        output_root=output_root,
        l1c_root_provided=False,
        l2a_root_provided=True,
    )

    for path in written.values():
        assert path.is_relative_to(output_root)
    assert not (repository / "results" / "phase5").exists()
    assert set(written) >= {
        "pairing_audit",
        "native_qa_inventory",
        "extraction_master",
        "date_observation_master",
        "attrition_table",
        "annual_attrition_table",
        "baseline_platform_audit",
        "provenance_manifest",
        "failure_audit",
        "qa_findings_document",
        "native_qa_audit_document",
    }


def test_writing_outside_phase6a_is_refused(tmp_path, repository, config):
    l2a_root = tmp_path / "archive" / "L2A"
    build_l2a_product(l2a_root)
    result = run(repository, config, l1c_root=None, l2a_root=l2a_root)
    with pytest.raises(PilotScopeError):
        write_outputs(
            result,
            config=config,
            repository_root=repository,
            output_root=repository / "results" / "phase5",
            l1c_root_provided=False,
            l2a_root_provided=True,
        )


def test_provenance_manifest_is_portable_and_states_the_stopping_rule(
    tmp_path, repository, config
):
    l2a_root = tmp_path / "archive" / "L2A"
    build_l2a_product(l2a_root)
    result = run(repository, config, l1c_root=None, l2a_root=l2a_root)
    written = write_outputs(
        result,
        config=config,
        repository_root=repository,
        output_root=repository / "results" / "phase6a",
        l1c_root_provided=False,
        l2a_root_provided=True,
    )
    manifest = json.loads(written["provenance_manifest"].read_text(encoding="utf-8"))
    assert manifest["pilot_status"] == "DRAFT_PENDING_HUMAN_FREEZE"
    assert (
        manifest["final_minimum_valid_pixel_threshold"]
        == "NOT_SELECTED_REQUIRES_HUMAN_FREEZE"
    )
    assert "TIMESAT" in manifest["stopping_rule"]
    serialized = json.dumps(manifest)
    assert str(l2a_root) not in serialized
    assert "/Users/" not in serialized


def test_extraction_master_never_embeds_the_runtime_archive_root(
    tmp_path, repository, config
):
    l2a_root = tmp_path / "archive" / "L2A"
    build_l2a_product(l2a_root)
    result = run(repository, config, l1c_root=None, l2a_root=l2a_root)
    written = write_outputs(
        result,
        config=config,
        repository_root=repository,
        output_root=repository / "results" / "phase6a",
        l1c_root_provided=False,
        l2a_root_provided=True,
    )
    text = written["extraction_master"].read_text(encoding="utf-8")
    assert str(l2a_root) not in text
    assert "GRANULE/" in text


def test_attrition_output_covers_the_pilot_thresholds(tmp_path, repository, config):
    l2a_root = tmp_path / "archive" / "L2A"
    build_l2a_product(l2a_root)
    result = run(repository, config, l1c_root=None, l2a_root=l2a_root)
    written = write_outputs(
        result,
        config=config,
        repository_root=repository,
        output_root=repository / "results" / "phase6a",
        l1c_root_provided=False,
        l2a_root_provided=True,
    )
    with written["attrition_table"].open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    thresholds = {int(row["minimum_valid_pixels"]) for row in rows}
    assert thresholds == {9, 8, 6, 5}
    assert {row["threshold_status"] for row in rows} == {"PILOT_NOT_SELECTED"}


# --- script interface ----------------------------------------------------------


def test_script_stops_cleanly_without_a_real_archive():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "26_erken_phase6a_real_s2_pilot.py")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert completed.returncode == 0
    assert "STOP:" in completed.stdout
    assert "does not guess archive paths" in completed.stdout


def test_script_fails_when_a_real_archive_is_required():
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "26_erken_phase6a_real_s2_pilot.py"),
            "--require-real-archive",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert completed.returncode == 2


def test_script_refuses_a_prohibited_site_root(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "26_erken_phase6a_real_s2_pilot.py"),
            "--l2a-root",
            str(tmp_path / "Vombsjon" / "L2A"),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert completed.returncode != 0
    assert "Lake Erken" in (completed.stderr + completed.stdout)


# --- protocol / config / implementation consistency ---------------------------


def test_qa_flag_categories_are_disjoint_and_complete(config):
    qa = config.section("native_qa")
    hard = set(qa["hard_invalid_flags"])
    diagnostic = set(qa["diagnostic_flags"])
    assert not hard & diagnostic
    declared = set(qa["msk_qualit_bands"]) | set(qa["msk_classi_bands"])
    # Every condition a native mask can report must be classified, and no
    # classified flag may lack a real mask source.
    assert declared <= hard | diagnostic
    assert (hard | diagnostic) - declared == set()


def test_ancillary_lost_is_diagnostic_in_the_config(config):
    qa = config.section("native_qa")
    assert "ancillary_lost" in qa["diagnostic_flags"]
    assert "ancillary_lost" not in qa["hard_invalid_flags"]
    assert qa["qa_split_status"] == "DRAFT_REQUIRES_HUMAN_FREEZE"


def test_qa60_is_never_a_validity_contributing_family(config):
    qa = config.section("native_qa")
    validity_families = set(qa["band_specific_qa_families"]) | set(
        qa["common_qa_families"]
    )
    assert "CLOUDS" not in validity_families
    assert qa["qa60_alone_is_sufficient"] is False
    assert qa["qa60_role"] == "inventory_provenance_only"


def test_every_declared_output_is_actually_written(tmp_path, repository, config):
    l2a_root = tmp_path / "archive" / "L2A"
    build_l2a_product(l2a_root)
    result = run(repository, config, l1c_root=None, l2a_root=l2a_root)
    written = write_outputs(
        result,
        config=config,
        repository_root=repository,
        output_root=repository / "results" / "phase6a",
        l1c_root_provided=False,
        l2a_root_provided=True,
    )
    declared = set(config.section("outputs")["files"])
    assert declared <= set(written)
    for path in written.values():
        assert path.is_file()


def test_generated_markdown_audits_carry_the_governance_disclaimers(
    tmp_path, repository, config
):
    l2a_root = tmp_path / "archive" / "L2A"
    build_l2a_product(l2a_root)
    result = run(repository, config, l1c_root=None, l2a_root=l2a_root)
    written = write_outputs(
        result,
        config=config,
        repository_root=repository,
        output_root=repository / "results" / "phase6a",
        l1c_root_provided=False,
        l2a_root_provided=True,
    )
    findings = written["qa_findings_document"].read_text(encoding="utf-8")
    assert "No CHLF was inspected" in findings
    assert "not selected here" in findings
    audit = written["native_qa_audit_document"].read_text(encoding="utf-8")
    assert "never treated as clean" in audit
