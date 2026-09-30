"""Tests for the Vombsjon pre-performance execution-gate closure layer.

Every test runs against synthetic evidence in a temporary directory. No test
touches the real HPC archives, the real TIMESAT binary, or any Vombsjon
reconstruction or performance output: gate closure guards performance and must
never read it.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from twinwater_timesat.vombsjon_execution_gates import (
    BLOCKED,
    CANONICAL_FREEZE_PATH,
    CANONICAL_OUTPUT_ROOT,
    CANONICAL_TIMESAT_SNAPSHOT,
    EXECUTION_EVIDENCE_SCHEMA_VERSION,
    REQUIRED_EXTERNAL_ARCHIVES,
    SCENE_DECLARED_SETTINGS,
    ExecutionGateError,
    is_sha256,
    match_recorded_checksum,
    sha256_text_variants,
    repository_provenance_ready,
    validate_governing_freeze,
    EXTERNAL_EVIDENCE_SCHEMA_VERSION,
    FAIL,
    PASS,
    PROTECTED_OUTPUT_PREFIXES,
    SATELLITE_MANIFEST_NAME,
    ExecutionGateScopeError,
    GateContext,
    assert_output_path_allowed,
    build_context,
    build_manifest,
    capture_repository_state,
    evaluate_gates,
    observe_git_root,
    required_gate_ids,
    sha256_file,
    summarize,
    write_gate_outputs,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_FREEZE = REPO_ROOT / "config/erken_vomb_transfer_freeze_v1.1.json"

ACOLITE_COMMIT = "64a02ff386e2985eef68ae00198b38e04f3c4a1f"
WRAPPER_COMMIT = "6b5fe1f31a4e4d477c2ad552c97f3c2f442b8b0c"

SEVEN_GATES = (
    "verify_external_input_identity_licence_and_sha256",
    "audit_raw_sentinel2_and_acolite_product_provenance",
    "resolve_or_retain_coordinate_flags_without_silent_correction",
    "materialize_qc_and_same_day_deduplication_audit",
    "verify_acolite_versions_and_effective_settings_match_this_freeze",
    "verify_timesat_runtime_matches_snapshot",
    "materialize_the_fixed_pelagic_field_validation_polygon_and_its_provenance",
)


# ---------------------------------------------------------------------------
# Synthetic evidence
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or ["empty"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _satellite_manifest() -> dict:
    return {
        "audit_version": "vombsjon_satellite_input_audit_v1.2",
        # The audit records which governing freeze produced it. The recorded
        # value is the committed (LF) checksum, exactly as an audit run on a LF
        # checkout writes it, so the fixture also exercises cross-checkout
        # checksum matching on a CRLF working tree.
        "governing_freeze": {
            "path": "config/erken_vomb_transfer_freeze_v1.1.json",
            "sha256": sha256_text_variants(REAL_FREEZE)["as_committed_lf"],
            "freeze_version": "erken_vomb_transfer_freeze_v1.1",
        },
        "counts": {
            "l1c_products": 1509,
            "l2a_products": 1510,
            "acolite_scenes": 1505,
            "exact_unique_l1c_l2a_pairs": 1466,
            "failure_rows": 48,
            "extraction_rows": 3,
            "fixed_target_observation_rows": 3,
            "same_day_rows": 2,
            "polygon_target_grid_pixel_counts_observed": [615],
        },
        "freeze_crosscheck": [
            {"freeze_key": "observation_layer.primary_proxy", "agrees": True},
            {"freeze_key": "spatial_and_qc.minimum_valid_pixels", "agrees": True},
        ],
        "inventory_fingerprints": {
            "l1c": {"sha256": "a" * 64, "is_raster_content_checksum": False},
            "l2a": {"sha256": "b" * 64, "is_raster_content_checksum": False},
            "acolite": {"sha256": "c" * 64, "is_raster_content_checksum": False},
        },
        "extraction_and_qc_rules": {
            "spatial_support_roles": {
                "temporal_reconstruction_target": (
                    "fixed_nominal_station_3x3_20m_minimum_6_of_9"
                ),
                "primary_field_validation_support": "fixed_pelagic_convex_hull_polygon",
                "secondary_spatial_sensitivity": (
                    "actual_gps_3x3_secondary_spatial_sensitivity_only"
                ),
                "nominal_point_fallback_in_primary_field_validation": False,
            },
            "fixed_temporal_target": {
                "window_shape": "3x3",
                "window_pixel_count": 9,
                "minimum_valid_pixels": 6,
                "invalid_pixel_fill_allowed": False,
                "moves_with_field_gps": False,
            },
            "radiometry": {"clamp_negative_reflectance": False},
            "indices": {"clip_mci": False},
            "missing_required_qa_family_policy": "observation_unavailable",
            "same_day": {
                "unit": "whole_calendar_date",
                "reduction": "median_of_eligible_observation_level_medians",
                "applies_per_method": True,
                "pool_methods": False,
                "preserve_product_level_rows_first": True,
            },
            "field_matchup": {
                "unresolved_coordinate_correction_allowed": False,
                "retain_unresolved_coordinate_dates": True,
                "nominal_point_fallback_in_primary_field_validation": False,
            },
            "field_gps_sensitivity": {
                "extract_for_unresolved_coordinate_dates": False,
                "nominal_fallback_allowed": False,
            },
            "field_polygon": {
                "identical_for_every_field_date": True,
                "moves_between_dates": False,
            },
            "product_roles": {
                "primary": {
                    "method": "ACOLITE",
                    "quantity": "rhos",
                    "role": "primary_aquatic_atmospheric_correction",
                },
                "silent_processor_fallback_allowed": False,
            },
        },
        "field_sampling_area": {
            "rule_id": "vombsjon_fixed_pelagic_hull_v1.1",
            "construction": (
                "unbuffered_convex_hull_of_accepted_measured_gps_plus_nominal_anchor"
            ),
            "buffer_m": 0.0,
            "clipped_to_geometry": None,
            "vertex_count": 6,
            "area_m2": 247766.33349609375,
            "accepted_point_count": 22,
            "nominal_inside": True,
            "nominal_is_vertex": False,
            "tuned_from_satellite_or_field_performance": False,
        },
        "acolite": {
            "identity": {
                "freeze_declared_identity": {
                    "acolite_source_commit": ACOLITE_COMMIT,
                    "s2_inlandwater_ac_commit": WRAPPER_COMMIT,
                    "acolite_version_string": "Generic GitHub Clone c2026-08-19T19:07:54",
                    "ancillary_data": True,
                },
                "observed_settings": {
                    "ancillary_data": {
                        "declared_scene_count": 1505,
                        "distinct_values": ["True"],
                        "status": "verified_from_acolite_run_files",
                    },
                    "s2_target_res": {
                        "declared_scene_count": 1505,
                        "distinct_values": ["20"],
                        "status": "verified_from_acolite_run_files",
                    },
                    "l2r_export_geotiff": {
                        "declared_scene_count": 1505,
                        "distinct_values": ["True"],
                        "status": "verified_from_acolite_run_files",
                    },
                    "l2w_export_geotiff": {
                        "declared_scene_count": 1505,
                        "distinct_values": ["True"],
                        "status": "verified_from_acolite_run_files",
                    },
                    "polygon": {
                        "declared_scene_count": 1505,
                        "distinct_values": ["/srv/roi/vombsjon.geojson"],
                        "status": "verified_from_acolite_run_files",
                    },
                    "acolite_version": {
                        "declared_scene_count": 0,
                        "distinct_values": [],
                        "status": "not_verifiable_from_supplied_files",
                    },
                },
                "netcdf_fallback_allowed": False,
            }
        },
    }


def _passing_runtime() -> dict:
    return {
        "runtime_available": True,
        "import_error": None,
        "runtime_error": None,
        "registered_build_artifact": True,
        "all_runtime_checks_passed": True,
        "runtime": {
            "timesat_core_version": "4.4.1",
            "timesat_cli_version": "1.9.2",
            "timesat_core_binary_filename": "_timesat.cpython-312-darwin.so",
            "timesat_core_binary_sha256": "689d2a9b",
            "mismatches": [],
            "smoke_test": {"passed": True},
        },
        "affine_equivariance_checks": [
            {"method": "timesat_double_logistic", "passed": True},
            {"method": "timesat_smoothing_spline", "smoothing": 10, "passed": True},
        ],
    }



POLYGON_RING = [
    [13.603166666666668, 55.67378333333333],
    [13.609444444444444, 55.67444444444443],
    [13.613413, 55.67720499999999],
    [13.612141666666666, 55.67861111111111],
    [13.608819, 55.678928],
    [13.603055555555555, 55.676944444444445],
]


def _polygon_geojson(ring=None) -> dict:
    """A structurally valid closed six-vertex ring, as the audit writes it."""

    positions = [list(point) for point in (ring if ring is not None else POLYGON_RING)]
    return {
        "type": "FeatureCollection",
        "name": "vombsjon_field_sampling_area",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [positions + [positions[0]]],
                },
                "properties": {"rule_id": "vombsjon_fixed_pelagic_hull_v1.1"},
            }
        ],
    }


def _provenance_rows(accepted=22) -> list[dict[str, object]]:
    """55 offered source points of which `accepted` are accepted, plus vertices."""

    rows: list[dict[str, object]] = []
    for index in range(54):
        label = f"2020-01-{index + 1:02d}"
        rows.append(
            {
                "record_type": "source_point",
                "label": label,
                "role": "field_sampling_coordinate",
                "accepted_for_polygon": index < (accepted - 1),
                "reason": "fixture",
            }
        )
    rows.append(
        {
            "record_type": "source_point",
            "label": "paper_nominal_station",
            "role": "nominal_station_anchor",
            "accepted_for_polygon": True,
            "reason": "nominal anchor",
        }
    )
    for index in range(6):
        rows.append(
            {
                "record_type": "hull_vertex",
                "label": f"vertex_{index + 1}",
                "role": "polygon_vertex",
                "accepted_for_polygon": True,
                "reason": "convex_hull_vertex",
            }
        )
    rows.append(
        {
            "record_type": "polygon_summary",
            "label": "vombsjon_field_sampling_area",
            "role": "primary_field_validation_support",
            "accepted_for_polygon": True,
            "reason": "unbuffered_convex_hull",
        }
    )
    return rows


@pytest.fixture
def evidence(tmp_path: Path) -> dict:
    """Build a complete synthetic evidence tree that yields 7/7 PASS."""

    root = tmp_path / "repo"
    # The governing freeze lives at its canonical path inside the fixture
    # repository, so the audit's recorded anchor path can be checked honestly.
    freeze_copy = root / "config/erken_vomb_transfer_freeze_v1.1.json"
    freeze_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REAL_FREEZE, freeze_copy)
    satellite = root / "results/vombsjon/satellite_input_audit/v1.2"
    field = root / "results/vombsjon/field_input_audit/v1.0"
    satellite.mkdir(parents=True)
    field.mkdir(parents=True)

    _write_json(satellite / SATELLITE_MANIFEST_NAME, _satellite_manifest())
    for name in (
        "vombsjon_l1c_inventory.csv",
        "vombsjon_l2a_inventory.csv",
        "vombsjon_acolite_inventory.csv",
        "vombsjon_l1c_l2a_pairing_audit.csv",
        "vombsjon_extraction_failures.csv",
        "vombsjon_native_qa_inventory.csv",
    ):
        (satellite / name).write_text("placeholder\n", encoding="utf-8", newline="\n")

    for name in (
        "vombsjon_product_extraction_master.csv",
        "vombsjon_fixed_station_observation_master.csv",
    ):
        _write_csv(
            satellite / name,
            [{"method": "ACOLITE", "row": index} for index in range(3)],
        )
    _write_csv(
        satellite / "vombsjon_same_day_observation_master.csv",
        [
            {
                "method": "ACOLITE",
                "date": "2020-06-03",
                "reprocessings_counted_as_independent_observations": False,
                "methods_pooled": False,
            },
            {
                "method": "L2A",
                "date": "2020-06-03",
                "reprocessings_counted_as_independent_observations": False,
                "methods_pooled": False,
            },
        ],
    )
    _write_csv(
        satellite / "vombsjon_field_satellite_matchup_master.csv",
        [
            {
                "field_date": date,
                "method": method,
                "coordinate_status": "measured_gps_flagged_unresolved",
                "coordinate_contributed_to_polygon": False,
                "coordinate_correction_applied": False,
            }
            for date in ("2020-06-10", "2020-06-24")
            for method in ("ACOLITE", "L1C", "L2A")
        ],
    )
    _write_json(satellite / "vombsjon_field_sampling_area.geojson", _polygon_geojson())
    _write_csv(
        satellite / "vombsjon_field_sampling_area_provenance.csv", _provenance_rows()
    )
    _write_csv(
        satellite / "vombsjon_field_gps_3x3_sensitivity.csv",
        [
            {
                "field_date": date,
                "sensitivity_status": "not_extracted_unresolved_coordinate_flag",
            }
            for date in ("2020-06-10", "2020-06-24")
        ],
    )

    # One committed field source with an established licence and a real checksum.
    source_file = root / "data/sources/vombsjon/source.csv"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("date,value\n2020-06-03,1\n", encoding="utf-8", newline="\n")
    _write_csv(
        field / "vombsjon_field_source_manifest.csv",
        [
            {
                "repository_path": "data/sources/vombsjon/source.csv",
                "sha256": sha256_file(source_file),
                "licence_status": "CC BY 4.0 stated on article page 1",
            }
        ],
    )
    _write_json(field / "vombsjon_field_input_audit_manifest.json", {"audit_version": "v1.0"})

    snapshot = root / "config/timesat_double_logistic_defaults_v4.4.1.json"
    _write_json(snapshot, {"timesat_core": {"version": "4.4.1"}})

    evidence_file = root / "external_input_evidence.json"
    _write_json(
        evidence_file,
        {
            "schema_version": EXTERNAL_EVIDENCE_SCHEMA_VERSION,
            "inputs": [
                {
                    "input_id": archive,
                    "identity": f"{archive} archive on the HPC server",
                    "licence": "Copernicus Sentinel Data Terms",
                    "licence_verified": True,
                    "content_sha256": "d" * 64,
                    "content_checksum_scope": "content_manifest",
                    "verified_by": "operator",
                    "verification_date": "2026-09-30",
                }
                for archive in ("L1C", "L2A", "ACOLITE")
            ],
        },
    )

    execution_file = root / "acolite_execution_evidence.json"
    _write_json(execution_file, _execution_evidence())

    return {
        "root": root,
        "satellite": satellite,
        "field": field,
        "snapshot": snapshot,
        "freeze": freeze_copy,
        "evidence_file": evidence_file,
        "execution_file": execution_file,
    }


def _execution_evidence(**overrides) -> dict:
    """Documented, pre-specified ancillary_data False -> True correction."""

    payload = {
        "schema_version": EXECUTION_EVIDENCE_SCHEMA_VERSION,
        "base_wrapper_commit": WRAPPER_COMMIT,
        "observed_acolite_source_commit": ACOLITE_COMMIT,
        "execution_script_path": "examples/run_acolite_vombsjon.slurm",
        "execution_script_sha256": "e" * 64,
        "performance_inspected_before_override": False,
        "attested_effective_settings": {"profile": "inland"},
        "overrides": [
            {
                "setting": "ancillary_data",
                "wrapper_base_value": False,
                "executed_value": True,
                "frozen_required_value": True,
                "reason_for_override": (
                    "the wrapper example invocation predates the freeze and sets "
                    "ancillary_data=False; the freeze already required True"
                ),
                "override_pre_specified_before_performance": True,
            }
        ],
    }
    payload.update(overrides)
    return payload


def _context(evidence: dict, **overrides) -> GateContext:
    root = evidence["root"]
    context = build_context(
        repository_root=root,
        freeze_path=evidence["freeze"],
        satellite_audit_dir=evidence["satellite"],
        field_audit_dir=evidence["field"],
        timesat_snapshot_path=evidence["snapshot"],
        external_input_evidence_path=overrides.pop(
            "external_input_evidence_path", evidence["evidence_file"]
        ),
        acolite_execution_evidence_path=overrides.pop(
            "acolite_execution_evidence_path", evidence["execution_file"]
        ),
    )
    context.acolite_source_observation = overrides.pop(
        "acolite_source_observation",
        {"root_supplied": True, "root_exists": True, "head_commit": ACOLITE_COMMIT,
         "worktree_dirty": False, "porcelain_entry_count": 0, "observation_error": None},
    )
    context.wrapper_observation = overrides.pop(
        "wrapper_observation",
        {"root_supplied": True, "root_exists": True, "head_commit": WRAPPER_COMMIT,
         "worktree_dirty": False, "porcelain_entry_count": 0, "observation_error": None},
    )
    context.timesat_runtime = overrides.pop("timesat_runtime", _passing_runtime())
    assert not overrides, f"unused overrides: {sorted(overrides)}"
    return context


CLEAN_STATE = {
    "captured_before_writing_outputs": True,
    "repository_state_observable": True,
    "repository_commit_at_start": "cafebabe",
    "repository_worktree_dirty_at_start": False,
}


def _statuses(context: GateContext) -> dict[str, str]:
    return {record.gate_id: record.status for record in evaluate_gates(context)}


def _patch_manifest(evidence: dict, mutate) -> None:
    path = evidence["satellite"] / SATELLITE_MANIFEST_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    _write_json(path, payload)


# ---------------------------------------------------------------------------
# 1-2. Gate identity and order come from the freeze
# ---------------------------------------------------------------------------


def test_exactly_the_seven_freeze_gates_are_evaluated(evidence):
    records = evaluate_gates(_context(evidence))
    assert tuple(record.gate_id for record in records) == SEVEN_GATES


def test_gate_order_and_identity_are_read_from_the_freeze(evidence, tmp_path):
    freeze = json.loads(REAL_FREEZE.read_text(encoding="utf-8"))
    assert tuple(freeze["execution_gates"]["before_vomb_performance"]) == SEVEN_GATES
    assert required_gate_ids(freeze) == SEVEN_GATES

    # Reordering the freeze reorders evaluation: the list is not restated in code.
    reordered = list(reversed(SEVEN_GATES))
    freeze["execution_gates"]["before_vomb_performance"] = reordered
    alternate = tmp_path / "freeze.json"
    _write_json(alternate, freeze)
    context = build_context(
        repository_root=evidence["root"],
        freeze_path=alternate,
        satellite_audit_dir=evidence["satellite"],
        field_audit_dir=evidence["field"],
        timesat_snapshot_path=evidence["snapshot"],
    )
    context.timesat_runtime = _passing_runtime()
    assert [record.gate_id for record in evaluate_gates(context)] == reordered


# ---------------------------------------------------------------------------
# 3-6. Closure arithmetic
# ---------------------------------------------------------------------------


def test_all_seven_pass_completes_closure_and_grants_eligibility(evidence):
    records = evaluate_gates(_context(evidence))
    assert [record.status for record in records] == [PASS] * 7
    summary = summarize(records, repository_state=CLEAN_STATE)
    assert summary["gate_closure_complete"] is True
    assert summary["performance_execution_eligible"] is True
    assert summary["performance_execution_authorized"] is False


def test_any_blocked_gate_denies_eligibility(evidence):
    context = _context(evidence, acolite_source_observation=None)
    records = evaluate_gates(context)
    summary = summarize(records, repository_state=CLEAN_STATE)
    assert summary["n_blocked"] >= 1
    assert summary["gate_closure_complete"] is False
    assert summary["performance_execution_eligible"] is False


def test_any_failed_gate_denies_eligibility(evidence):
    _patch_manifest(
        evidence,
        lambda payload: payload["counts"].__setitem__("l1c_products", 1),
    )
    records = evaluate_gates(_context(evidence))
    summary = summarize(records, repository_state=CLEAN_STATE)
    assert summary["n_fail"] >= 1
    assert summary["gate_closure_complete"] is False
    assert summary["performance_execution_eligible"] is False


# ---------------------------------------------------------------------------
# 7-8. Missing evidence and the fingerprint distinction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("removed", "gate_id"),
    [
        (
            "vombsjon_l1c_inventory.csv",
            "audit_raw_sentinel2_and_acolite_product_provenance",
        ),
        (
            "vombsjon_native_qa_inventory.csv",
            "materialize_qc_and_same_day_deduplication_audit",
        ),
        (
            "vombsjon_field_sampling_area.geojson",
            "materialize_the_fixed_pelagic_field_validation_polygon_and_its_provenance",
        ),
    ],
)
def test_missing_evidence_is_blocked_never_pass(evidence, removed, gate_id):
    (evidence["satellite"] / removed).unlink()
    assert _statuses(_context(evidence))[gate_id] == BLOCKED


def test_missing_satellite_manifest_blocks_rather_than_passes(evidence):
    (evidence["satellite"] / SATELLITE_MANIFEST_NAME).unlink()
    statuses = _statuses(_context(evidence))
    for gate_id in SEVEN_GATES[1:5] + (SEVEN_GATES[6],):
        assert statuses[gate_id] == BLOCKED, gate_id


def test_path_set_fingerprint_is_not_accepted_as_content_checksum(evidence):
    """The inventory fingerprint covers ids and paths, not raster bytes."""

    records = {item.gate_id: item for item in evaluate_gates(
        _context(evidence, external_input_evidence_path=None)
    )}
    gate = records["verify_external_input_identity_licence_and_sha256"]
    assert gate.status == BLOCKED
    assert gate.details["path_set_fingerprint_accepted_as_content_checksum"] is False
    for archive in gate.details["external_satellite_archives"]:
        assert archive["content_checksum_accepted"] is False
        assert archive["declares_raster_content_checksum"] is False
    assert "content SHA256 evidence for the external" in gate.blocking_reason


def test_evidence_declaring_a_path_set_scope_is_rejected(evidence):
    """A supplied evidence file cannot launder a path fingerprint into a checksum."""

    payload = json.loads(evidence["evidence_file"].read_text(encoding="utf-8"))
    for entry in payload["inputs"]:
        entry["content_checksum_scope"] = "path_set_fingerprint"
    _write_json(evidence["evidence_file"], payload)
    statuses = _statuses(_context(evidence))
    assert statuses["verify_external_input_identity_licence_and_sha256"] == BLOCKED


def test_real_committed_evidence_blocks_gate_one(evidence):
    """The repository as committed does not establish licence or content SHA."""

    context = build_context(
        repository_root=REPO_ROOT,
        satellite_audit_dir=REPO_ROOT / "results/vombsjon/satellite_input_audit/v1.2",
        field_audit_dir=REPO_ROOT / "results/vombsjon/field_input_audit/v1.0",
    )
    records = {item.gate_id: item for item in evaluate_gates(context)}
    assert records["verify_external_input_identity_licence_and_sha256"].status == BLOCKED


# ---------------------------------------------------------------------------
# 9-10. Coordinate retention
# ---------------------------------------------------------------------------


def test_preserved_unresolved_coordinate_flags_pass_the_retention_gate(evidence):
    statuses = _statuses(_context(evidence))
    assert (
        statuses["resolve_or_retain_coordinate_flags_without_silent_correction"] == PASS
    )


def test_silent_coordinate_correction_fails(evidence):
    path = evidence["satellite"] / "vombsjon_field_satellite_matchup_master.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    for row in rows:
        if row["field_date"] == "2020-06-10":
            row["coordinate_correction_applied"] = "True"
    _write_csv(path, rows)
    records = {item.gate_id: item for item in evaluate_gates(_context(evidence))}
    gate = records["resolve_or_retain_coordinate_flags_without_silent_correction"]
    assert gate.status == FAIL
    assert "silent coordinate correction" in gate.mismatch_reason


def test_dropping_an_unresolved_date_fails(evidence):
    path = evidence["satellite"] / "vombsjon_field_satellite_matchup_master.csv"
    rows = [
        row
        for row in csv.DictReader(path.open(encoding="utf-8"))
        if row["field_date"] != "2020-06-24"
    ]
    _write_csv(path, rows)
    records = {item.gate_id: item for item in evaluate_gates(_context(evidence))}
    gate = records["resolve_or_retain_coordinate_flags_without_silent_correction"]
    assert gate.status == FAIL
    assert "retained, not dropped" in gate.mismatch_reason


def test_gps_sensitivity_extraction_of_a_flagged_date_fails(evidence):
    path = evidence["satellite"] / "vombsjon_field_gps_3x3_sensitivity.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    rows[0]["sensitivity_status"] = "extracted"
    _write_csv(path, rows)
    statuses = _statuses(_context(evidence))
    assert (
        statuses["resolve_or_retain_coordinate_flags_without_silent_correction"] == FAIL
    )


# ---------------------------------------------------------------------------
# 11. QC and same-day evidence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("fixed_temporal_target", "minimum_valid_pixels"), 3),
        (("fixed_temporal_target", "window_shape"), "5x5"),
        (("fixed_temporal_target", "invalid_pixel_fill_allowed"), True),
        (("radiometry", "clamp_negative_reflectance"), True),
        (("indices", "clip_mci"), True),
        (("same_day", "reduction"), "mean_of_everything"),
        (("same_day", "pool_methods"), True),
        (("same_day", "preserve_product_level_rows_first"), False),
    ],
)
def test_qc_rule_drift_fails_the_qc_gate(evidence, path, value):
    def mutate(payload):
        payload["extraction_and_qc_rules"][path[0]][path[1]] = value

    _patch_manifest(evidence, mutate)
    statuses = _statuses(_context(evidence))
    assert statuses["materialize_qc_and_same_day_deduplication_audit"] == FAIL


def test_reprocessings_counted_as_independent_fails(evidence):
    path = evidence["satellite"] / "vombsjon_same_day_observation_master.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    rows[0]["reprocessings_counted_as_independent_observations"] = "True"
    _write_csv(path, rows)
    statuses = _statuses(_context(evidence))
    assert statuses["materialize_qc_and_same_day_deduplication_audit"] == FAIL


def test_duplicate_same_day_method_date_key_fails(evidence):
    path = evidence["satellite"] / "vombsjon_same_day_observation_master.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    rows.append(dict(rows[0]))
    _write_csv(path, rows)
    statuses = _statuses(_context(evidence))
    assert statuses["materialize_qc_and_same_day_deduplication_audit"] == FAIL


# ---------------------------------------------------------------------------
# 12-16. ACOLITE identity
# ---------------------------------------------------------------------------


def test_ancillary_data_false_fails_the_acolite_gate(evidence):
    def mutate(payload):
        settings = payload["acolite"]["identity"]["observed_settings"]
        settings["ancillary_data"]["distinct_values"] = ["False"]

    _patch_manifest(evidence, mutate)
    records = {item.gate_id: item for item in evaluate_gates(_context(evidence))}
    gate = records["verify_acolite_versions_and_effective_settings_match_this_freeze"]
    assert gate.status == FAIL
    assert "ancillary_data" in gate.mismatch_reason


def test_ancillary_data_true_alone_does_not_establish_source_identity(evidence):
    """Effective settings are not source identity."""

    context = _context(
        evidence, acolite_source_observation=None, wrapper_observation=None
    )
    records = {item.gate_id: item for item in evaluate_gates(context)}
    gate = records["verify_acolite_versions_and_effective_settings_match_this_freeze"]
    assert gate.status == BLOCKED
    assert gate.details["effective_settings"]["ancillary_data"]["distinct_values"] == [
        "True"
    ]
    assert "stable ACOLITE source identity was not independently observed" in (
        gate.blocking_reason
    )


def test_textual_version_string_is_not_a_stable_source_identity(evidence):
    """A declared version string cannot substitute for observed Git identity."""

    def mutate(payload):
        identity = payload["acolite"]["identity"]
        identity["observed_settings"]["acolite_version"] = {
            "declared_scene_count": 1505,
            "distinct_values": ["Generic GitHub Clone c2026-08-19T19:07:54"],
            "status": "verified_from_acolite_run_files",
        }

    _patch_manifest(evidence, mutate)
    context = _context(evidence, acolite_source_observation=None)
    records = {item.gate_id: item for item in evaluate_gates(context)}
    gate = records["verify_acolite_versions_and_effective_settings_match_this_freeze"]
    assert gate.status == BLOCKED
    assert gate.details["acolite_version_string_is_stable_source_identity"] is False


def test_wrong_acolite_commit_fails(evidence):
    context = _context(
        evidence,
        acolite_source_observation={
            "head_commit": "0" * 40,
            "worktree_dirty": False,
            "observation_error": None,
        },
    )
    records = {item.gate_id: item for item in evaluate_gates(context)}
    gate = records["verify_acolite_versions_and_effective_settings_match_this_freeze"]
    assert gate.status == FAIL
    assert "differs from the frozen source commit" in gate.mismatch_reason


def test_wrong_wrapper_commit_fails(evidence):
    context = _context(
        evidence,
        wrapper_observation={
            "head_commit": "1" * 40,
            "worktree_dirty": False,
            "observation_error": None,
        },
    )
    statuses = _statuses(context)
    assert (
        statuses["verify_acolite_versions_and_effective_settings_match_this_freeze"]
        == FAIL
    )


def test_unavailable_source_commit_evidence_is_blocked(evidence):
    context = _context(
        evidence,
        acolite_source_observation={
            "head_commit": None,
            "observation_error": "git could not be executed",
        },
    )
    statuses = _statuses(context)
    assert (
        statuses["verify_acolite_versions_and_effective_settings_match_this_freeze"]
        == BLOCKED
    )


def test_dirty_source_worktree_is_recorded_and_blocks(evidence):
    """Arbitrary local modifications are never assumed harmless."""

    context = _context(
        evidence,
        acolite_source_observation={
            "head_commit": ACOLITE_COMMIT,
            "worktree_dirty": True,
            "porcelain_entry_count": 3,
            "observation_error": None,
        },
    )
    records = {item.gate_id: item for item in evaluate_gates(context)}
    gate = records["verify_acolite_versions_and_effective_settings_match_this_freeze"]
    assert gate.status == BLOCKED
    assert "dirty" in gate.blocking_reason
    assert gate.details["acolite_source_observation"]["worktree_dirty"] is True


def test_observe_git_root_reports_a_non_repository(tmp_path):
    record = observe_git_root(tmp_path / "absent")
    assert record["root_exists"] is False
    assert record["observation_error"]


# ---------------------------------------------------------------------------
# 17-19. TIMESAT runtime
# ---------------------------------------------------------------------------


def test_timesat_version_or_hash_mismatch_fails(evidence):
    runtime = _passing_runtime()
    runtime["runtime_error"] = (
        "RuntimeError: TIMESAT runtime differs from the frozen defaults snapshot: "
        "timesat_core_version, timesat_core_init_sha256"
    )
    statuses = _statuses(_context(evidence, timesat_runtime=runtime))
    assert statuses["verify_timesat_runtime_matches_snapshot"] == FAIL


def test_unregistered_timesat_binary_is_blocked_not_reported_as_registered(evidence):
    runtime = _passing_runtime()
    runtime["registered_build_artifact"] = False
    runtime["runtime"]["timesat_core_binary_filename"] = "_timesat.cpython-311-linux.so"
    records = {item.gate_id: item for item in evaluate_gates(
        _context(evidence, timesat_runtime=runtime)
    )}
    gate = records["verify_timesat_runtime_matches_snapshot"]
    assert gate.status == BLOCKED
    assert gate.details["registered_build_artifact"] is False
    assert "not registered by the frozen snapshot" in gate.blocking_reason
    assert "snapshot is not amended here" in gate.blocking_reason


def test_affine_equivariance_failure_fails_the_timesat_gate(evidence):
    runtime = _passing_runtime()
    runtime["affine_equivariance_checks"][1]["passed"] = False
    runtime["all_runtime_checks_passed"] = False
    records = {item.gate_id: item for item in evaluate_gates(
        _context(evidence, timesat_runtime=runtime)
    )}
    gate = records["verify_timesat_runtime_matches_snapshot"]
    assert gate.status == FAIL
    assert "affine equivariance failed" in gate.mismatch_reason


def test_unavailable_timesat_runtime_is_blocked(evidence):
    runtime = {
        "runtime_available": False,
        "import_error": "ModuleNotFoundError: No module named 'timesat'",
    }
    statuses = _statuses(_context(evidence, timesat_runtime=runtime))
    assert statuses["verify_timesat_runtime_matches_snapshot"] == BLOCKED


def test_missing_timesat_probe_is_blocked(evidence):
    statuses = _statuses(_context(evidence, timesat_runtime=None))
    assert statuses["verify_timesat_runtime_matches_snapshot"] == BLOCKED


# ---------------------------------------------------------------------------
# 20. Polygon provenance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("vertex_count", 5),
        ("area_m2", 300000.0),
        ("buffer_m", 25.0),
        ("clipped_to_geometry", "some_lake.shp"),
        ("accepted_point_count", 21),
        ("nominal_inside", False),
        ("nominal_is_vertex", True),
        ("tuned_from_satellite_or_field_performance", True),
    ],
)
def test_polygon_provenance_mismatch_fails(evidence, key, value):
    _patch_manifest(
        evidence, lambda payload: payload["field_sampling_area"].__setitem__(key, value)
    )
    statuses = _statuses(_context(evidence))
    assert (
        statuses[
            "materialize_the_fixed_pelagic_field_validation_polygon_and_its_provenance"
        ]
        == FAIL
    )


def test_polygon_pixel_support_drift_fails(evidence):
    _patch_manifest(
        evidence,
        lambda payload: payload["counts"].__setitem__(
            "polygon_target_grid_pixel_counts_observed", [615, 610]
        ),
    )
    statuses = _statuses(_context(evidence))
    assert (
        statuses[
            "materialize_the_fixed_pelagic_field_validation_polygon_and_its_provenance"
        ]
        == FAIL
    )


def test_polygon_area_uses_a_numeric_tolerance(evidence):
    """A tiny float difference must not fail a correct polygon."""

    _patch_manifest(
        evidence,
        lambda payload: payload["field_sampling_area"].__setitem__(
            "area_m2", 247766.3334960937
        ),
    )
    statuses = _statuses(_context(evidence))
    assert (
        statuses[
            "materialize_the_fixed_pelagic_field_validation_polygon_and_its_provenance"
        ]
        == PASS
    )


def test_gps_3x3_demoted_from_secondary_sensitivity_fails(evidence):
    _patch_manifest(
        evidence,
        lambda payload: payload["extraction_and_qc_rules"][
            "spatial_support_roles"
        ].__setitem__("secondary_spatial_sensitivity", "primary_support"),
    )
    statuses = _statuses(_context(evidence))
    assert (
        statuses[
            "materialize_the_fixed_pelagic_field_validation_polygon_and_its_provenance"
        ]
        == FAIL
    )


# ---------------------------------------------------------------------------
# 21-22. Output confinement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "refused",
    [
        "results/vombsjon/satellite_input_audit/v1.1/x.csv",
        "results/vombsjon/satellite_input_audit/v1.2/x.csv",
        "results/vombsjon/field_input_audit/v1.0/x.csv",
        "results/transfer_freeze/v1.0/erken_transfer_timesat_runtime_validation.json",
        "results/transfer_freeze/v1.0/x.json",
        "config/erken_vomb_transfer_freeze_v1.1.json",
        "results/phase6a/x.csv",
        "docs/x.md",
    ],
)
def test_output_confinement_refuses_protected_namespaces(tmp_path, refused):
    with pytest.raises(ExecutionGateScopeError):
        assert_output_path_allowed(
            tmp_path / refused,
            repository_root=tmp_path,
            output_root="results/vombsjon/execution_gate_closure/v1.0",
        )


def test_output_confinement_allows_only_the_gate_namespace(tmp_path):
    allowed = assert_output_path_allowed(
        tmp_path / "results/vombsjon/execution_gate_closure/v1.0/report.csv",
        repository_root=tmp_path,
        output_root="results/vombsjon/execution_gate_closure/v1.0",
    )
    assert allowed.name == "report.csv"


def test_transfer_freeze_namespace_is_protected_by_configuration():
    assert "results/transfer_freeze" in PROTECTED_OUTPUT_PREFIXES
    assert "results/vombsjon/satellite_input_audit" in PROTECTED_OUTPUT_PREFIXES


def test_writing_outputs_touches_only_the_gate_namespace(evidence):
    context = _context(evidence)
    records = evaluate_gates(context)
    output_root = evidence["root"] / "results/vombsjon/execution_gate_closure/v1.0"
    written = write_gate_outputs(
        records,
        context=context,
        repository_state={
            "captured_before_writing_outputs": True,
            "repository_commit_at_start": "deadbeef",
            "repository_worktree_dirty_at_start": False,
        },
        runtime_result=_passing_runtime(),
        output_root=output_root,
    )
    assert set(written) == {"gate_status", "timesat_runtime_validation", "manifest"}
    for path in written.values():
        assert path.is_absolute() and output_root in path.parents
    # Nothing was created outside the gate namespace.
    produced = {
        p.relative_to(evidence["root"]).as_posix()
        for p in evidence["root"].rglob("*")
        if p.is_file()
    }
    stray = {
        name
        for name in produced
        if name.startswith("results/")
        and not name.startswith("results/vombsjon/execution_gate_closure/")
        and not name.startswith("results/vombsjon/satellite_input_audit/")
        and not name.startswith("results/vombsjon/field_input_audit/")
    }
    assert not stray


def test_generated_files_use_lf_line_endings(evidence):
    context = _context(evidence)
    output_root = evidence["root"] / "results/vombsjon/execution_gate_closure/v1.0"
    written = write_gate_outputs(
        records=evaluate_gates(context),
        context=context,
        repository_state=CLEAN_STATE,
        runtime_result=_passing_runtime(),
        output_root=output_root,
    )
    for path in written.values():
        assert b"\r\n" not in path.read_bytes()


# ---------------------------------------------------------------------------
# 23-24. Manifest assertions and provenance capture
# ---------------------------------------------------------------------------


def test_manifest_records_performance_assertions_as_false(evidence):
    context = _context(evidence)
    manifest = build_manifest(
        evaluate_gates(context),
        context=context,
        repository_state=CLEAN_STATE,
        runtime_result=_passing_runtime(),
    )
    scope = manifest["scope_assertions"]
    for key in (
        "performance_evaluated",
        "reconstruction_run",
        "vombsjon_performance_accessed",
        "daily_reconstructed_curves_created",
        "withheld_observation_experiment_run",
        "reconstruction_metrics_computed",
        "field_correlation_or_regression_fitted",
        "processor_selected_from_vombsjon",
        "any_parameter_tuned",
        "frozen_transfer_setting_changed",
        "field_chla_used_in_gate_evaluation",
    ):
        assert scope[key] is False, key
    assert manifest["performance_execution_authorized"] is False
    assert manifest["payload_sha256"]
    assert manifest["required_gate_ids"] == list(SEVEN_GATES)


def test_manifest_never_authorizes_performance_even_at_seven_pass(evidence):
    context = _context(evidence)
    records = evaluate_gates(context)
    assert all(record.status == PASS for record in records)
    manifest = build_manifest(
        records,
        context=context,
        repository_state=CLEAN_STATE,
        runtime_result=_passing_runtime(),
    )
    assert manifest["gate_closure_complete"] is True
    assert manifest["performance_execution_eligible"] is True
    assert manifest["performance_execution_authorized"] is False


def test_repository_state_is_captured_before_outputs_exist(evidence, monkeypatch):
    """The dirty flag must describe the tree before this run writes anything."""

    state = capture_repository_state(REPO_ROOT)
    assert state["captured_before_writing_outputs"] is True
    assert set(state) >= {
        "repository_commit_at_start",
        "repository_worktree_dirty_at_start",
    }

    context = _context(evidence)
    output_root = evidence["root"] / "results/vombsjon/execution_gate_closure/v1.0"
    manifest_before = {
        "captured_before_writing_outputs": True,
        "repository_commit_at_start": "cafebabe",
        "repository_worktree_dirty_at_start": False,
    }
    written = write_gate_outputs(
        evaluate_gates(context),
        context=context,
        repository_state=manifest_before,
        runtime_result=_passing_runtime(),
        output_root=output_root,
    )
    payload = json.loads(written["manifest"].read_text(encoding="utf-8"))
    # Writing the outputs did not retroactively mark the tree dirty.
    assert payload["repository_worktree_dirty_at_start"] is False
    assert payload["repository_commit_at_start"] == "cafebabe"
    assert payload["repository_state_captured_before_writing_outputs"] is True


def test_status_csv_has_one_row_per_gate_with_reasons(evidence):
    context = _context(evidence, acolite_source_observation=None)
    records = evaluate_gates(context)
    output_root = evidence["root"] / "results/vombsjon/execution_gate_closure/v1.0"
    written = write_gate_outputs(
        records,
        context=context,
        repository_state=CLEAN_STATE,
        runtime_result=_passing_runtime(),
        output_root=output_root,
    )
    rows = list(csv.DictReader(written["gate_status"].open(encoding="utf-8")))
    assert [row["gate_id"] for row in rows] == list(SEVEN_GATES)
    blocked = [row for row in rows if row["status"] == BLOCKED]
    assert blocked and all(row["blocking_reason"] for row in blocked)


# ---------------------------------------------------------------------------
# 25. The guard never reads what it guards
# ---------------------------------------------------------------------------


def test_gate_evaluation_reads_no_performance_artifact(evidence, monkeypatch):
    """Guard against a future edit that makes gate closure read performance."""

    opened: list[str] = []
    real_open = Path.open

    def tracking_open(self, *args, **kwargs):
        opened.append(self.as_posix())
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    evaluate_gates(_context(evidence))

    forbidden = (
        "reconstruction",
        "withheld",
        "performance",
        "nrmse",
        "rmse",
        "phase3",
        "phase4",
        "phase5",
    )
    offending = [
        name
        for name in opened
        if any(marker in name.lower() for marker in forbidden)
    ]
    assert not offending, f"gate closure read performance-shaped evidence: {offending}"


def test_no_gate_evaluator_imports_timesat_at_module_scope():
    """The module must import without TIMESAT so gate 6 can report BLOCKED."""

    import twinwater_timesat.vombsjon_execution_gates as module

    assert "timesat_adapter" not in getattr(module, "__dict__", {})


# ---------------------------------------------------------------------------
# A. Governed path pinning: production cannot substitute a governed input
# ---------------------------------------------------------------------------


def test_production_cannot_substitute_another_freeze(tmp_path):
    substitute = tmp_path / "other_freeze.json"
    _write_json(substitute, json.loads(REAL_FREEZE.read_text(encoding="utf-8")))
    with pytest.raises(ExecutionGateError) as caught:
        build_context(
            repository_root=REPO_ROOT, freeze_path=substitute, enforce_canonical=True
        )
    assert CANONICAL_FREEZE_PATH in str(caught.value)
    assert "pinned to" in str(caught.value)


def test_production_cannot_substitute_another_timesat_snapshot(tmp_path):
    substitute = tmp_path / "other_snapshot.json"
    _write_json(substitute, {"timesat_core": {"version": "9.9.9"}})
    with pytest.raises(ExecutionGateError) as caught:
        build_context(
            repository_root=REPO_ROOT,
            timesat_snapshot_path=substitute,
            enforce_canonical=True,
        )
    assert CANONICAL_TIMESAT_SNAPSHOT in str(caught.value)


def test_production_cannot_substitute_another_satellite_audit(tmp_path):
    with pytest.raises(ExecutionGateError) as caught:
        build_context(
            repository_root=REPO_ROOT,
            satellite_audit_dir=tmp_path,
            enforce_canonical=True,
        )
    assert "results/vombsjon/satellite_input_audit/v1.2" in str(caught.value)


def test_tests_may_still_inject_fixture_paths_with_pinning_off(evidence):
    """Pinning is a production guarantee, not an obstacle to fixture testing."""

    context = _context(evidence)
    assert context.enforce_canonical is False
    assert context.freeze_validation is None


def test_canonical_production_context_builds_and_validates_the_freeze():
    context = build_context(repository_root=REPO_ROOT, enforce_canonical=True)
    assert context.enforce_canonical is True
    assert context.freeze_relative_path == CANONICAL_FREEZE_PATH
    assert context.freeze_validation["validated"] is True
    assert context.freeze_validation["freeze_version"] == "erken_vomb_transfer_freeze_v1.1"
    assert (
        context.freeze_validation["vombsjon_performance_execution_authorized"] is False
    )


def test_canonical_closure_cannot_be_written_to_another_namespace(tmp_path):
    with pytest.raises(ExecutionGateScopeError):
        assert_output_path_allowed(
            tmp_path / "results/vombsjon/execution_gate_closure/v2.0/manifest.json",
            repository_root=tmp_path,
            output_root=CANONICAL_OUTPUT_ROOT,
        )


@pytest.mark.parametrize(
    ("mutate", "marker"),
    [
        (lambda f: f.__setitem__("schema_version", "something_else"), "schema_version"),
        (lambda f: f.__setitem__("freeze_version", "v9"), "freeze_version"),
        (
            lambda f: f["scope"].__setitem__(
                "vombsjon_performance_execution_authorized", True
            ),
            "authorized",
        ),
        (
            lambda f: f["execution_gates"].__setitem__(
                "before_vomb_performance", list(SEVEN_GATES[:6])
            ),
            "gate identities",
        ),
    ],
)
def test_freeze_validation_rejects_a_non_canonical_freeze(mutate, marker):
    freeze = json.loads(REAL_FREEZE.read_text(encoding="utf-8"))
    mutate(freeze)
    with pytest.raises(ExecutionGateError) as caught:
        validate_governing_freeze(freeze, relative_path="config/substitute.json")
    assert marker in str(caught.value)


def test_the_real_freeze_validates_unchanged():
    freeze = json.loads(REAL_FREEZE.read_text(encoding="utf-8"))
    report = validate_governing_freeze(freeze, relative_path=CANONICAL_FREEZE_PATH)
    assert report["gate_ids"] == list(SEVEN_GATES)


# ---------------------------------------------------------------------------
# A (continued). The audit is anchored to THIS governing freeze
# ---------------------------------------------------------------------------


def _gate2(evidence, **overrides):
    records = {
        item.gate_id: item for item in evaluate_gates(_context(evidence, **overrides))
    }
    return records["audit_raw_sentinel2_and_acolite_product_provenance"]


def test_audit_is_anchored_to_the_governing_freeze(evidence):
    gate = _gate2(evidence)
    anchor = gate.details["governing_freeze_anchor"]
    assert anchor["checked"] is True
    assert anchor["path_agrees"] is True
    assert anchor["sha256_agrees"] is True
    assert gate.status == PASS


def test_audit_without_a_recorded_freeze_anchor_blocks(evidence):
    _patch_manifest(evidence, lambda payload: payload.pop("governing_freeze"))
    gate = _gate2(evidence)
    assert gate.status == BLOCKED
    assert "records no governing_freeze block" in gate.blocking_reason


def test_audit_anchored_to_a_different_freeze_path_fails(evidence):
    _patch_manifest(
        evidence,
        lambda payload: payload["governing_freeze"].__setitem__(
            "path", "config/erken_vomb_transfer_freeze_v1.0.json"
        ),
    )
    gate = _gate2(evidence)
    assert gate.status == FAIL
    assert "erken_vomb_transfer_freeze_v1.0.json" in gate.mismatch_reason


def test_audit_anchored_to_different_freeze_content_fails(evidence):
    _patch_manifest(
        evidence,
        lambda payload: payload["governing_freeze"].__setitem__("sha256", "b" * 64),
    )
    gate = _gate2(evidence)
    assert gate.status == FAIL
    assert "matches neither" in gate.mismatch_reason


def test_audit_recording_no_freeze_checksum_blocks(evidence):
    _patch_manifest(
        evidence, lambda payload: payload["governing_freeze"].__setitem__("sha256", "")
    )
    gate = _gate2(evidence)
    assert gate.status == BLOCKED
    assert "no governing freeze SHA256" in gate.blocking_reason


def test_audit_recording_an_older_freeze_version_fails(evidence):
    _patch_manifest(
        evidence,
        lambda payload: payload["governing_freeze"].__setitem__(
            "freeze_version", "erken_vomb_transfer_freeze_v1.0"
        ),
    )
    gate = _gate2(evidence)
    assert gate.status == FAIL
    assert "freeze_version" in gate.mismatch_reason


def test_checkout_line_endings_are_not_a_content_difference(tmp_path):
    """A CRLF working tree must not be reported as different committed content."""

    lf = tmp_path / "lf.json"
    lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    crlf = tmp_path / "crlf.json"
    crlf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')

    lf_checksum = sha256_text_variants(lf)["as_committed_lf"]
    assert sha256_text_variants(lf)["working_tree_uses_crlf"] is False
    assert sha256_text_variants(crlf)["working_tree_uses_crlf"] is True

    matched, detail = match_recorded_checksum(lf_checksum, crlf)
    assert matched is True
    assert detail["checksum_form_matched"] == "as_committed_lf"

    matched, detail = match_recorded_checksum(sha256_file(crlf), crlf)
    assert matched is True
    assert detail["checksum_form_matched"] == "working_tree_bytes"


def test_genuinely_different_content_is_still_a_mismatch(tmp_path):
    original = tmp_path / "a.json"
    original.write_bytes(b'{"a": 1}\n')
    altered = tmp_path / "b.json"
    altered.write_bytes(b'{"a": 2}\n')
    matched, detail = match_recorded_checksum(sha256_file(original), altered)
    assert matched is False
    assert detail["checksum_form_matched"] is None


# ---------------------------------------------------------------------------
# B. Clean-start repository provenance is a prerequisite, not an eighth gate
# ---------------------------------------------------------------------------


def test_seven_pass_plus_clean_repository_completes_closure(evidence):
    summary = summarize(evaluate_gates(_context(evidence)), repository_state=CLEAN_STATE)
    assert summary["seven_gates_passed"] is True
    assert summary["repository_provenance_ready"] is True
    assert summary["repository_provenance_blocking_reason"] is None
    assert summary["gate_closure_complete"] is True
    assert summary["performance_execution_eligible"] is True


def test_seven_pass_plus_dirty_repository_denies_closure(evidence):
    dirty = dict(CLEAN_STATE, repository_worktree_dirty_at_start=True)
    summary = summarize(evaluate_gates(_context(evidence)), repository_state=dirty)
    assert summary["seven_gates_passed"] is True
    assert summary["repository_provenance_ready"] is False
    assert summary["gate_closure_complete"] is False
    assert summary["performance_execution_eligible"] is False
    assert "dirty" in summary["repository_provenance_blocking_reason"]


def test_a_dirty_repository_never_makes_a_gate_fail(evidence):
    """A dirty tree says the artifact is not reproducible, not that a gate failed."""

    records = evaluate_gates(_context(evidence))
    assert all(record.status == PASS for record in records)
    summary = summarize(
        records,
        repository_state=dict(CLEAN_STATE, repository_worktree_dirty_at_start=True),
    )
    assert summary["n_fail"] == 0
    assert summary["n_blocked"] == 0
    assert summary["n_pass"] == 7


@pytest.mark.parametrize(
    ("state", "marker"),
    [
        (None, "not captured"),
        (
            {"repository_state_observable": False, "repository_commit_at_start": None},
            "not observable",
        ),
        (dict(CLEAN_STATE, repository_commit_at_start=None), "commit at start"),
        (dict(CLEAN_STATE, repository_worktree_dirty_at_start=None), "cleanliness"),
    ],
)
def test_unobservable_repository_state_denies_closure(evidence, state, marker):
    summary = summarize(evaluate_gates(_context(evidence)), repository_state=state)
    assert summary["seven_gates_passed"] is True
    assert summary["repository_provenance_ready"] is False
    assert summary["gate_closure_complete"] is False
    assert marker in summary["repository_provenance_blocking_reason"]


def test_repository_provenance_is_reported_as_its_own_prerequisite():
    ready, reason = repository_provenance_ready(CLEAN_STATE)
    assert ready is True and reason is None
    ready, reason = repository_provenance_ready(None)
    assert ready is False and reason


def test_a_blocked_gate_with_a_clean_tree_still_denies_closure(evidence):
    summary = summarize(
        evaluate_gates(_context(evidence, acolite_execution_evidence_path=None)),
        repository_state=CLEAN_STATE,
    )
    assert summary["repository_provenance_ready"] is True
    assert summary["seven_gates_passed"] is False
    assert summary["gate_closure_complete"] is False


# ---------------------------------------------------------------------------
# C. Gate 1 requires per-archive coverage; one archive never clears another
# ---------------------------------------------------------------------------


def _archive_entry(archive, **overrides):
    entry = {
        "input_id": archive,
        "identity": archive + " archive on the HPC server",
        "licence": "Copernicus Sentinel Data Terms",
        "licence_verified": True,
        "content_sha256": "d" * 64,
        "content_checksum_scope": "content_manifest",
    }
    entry.update(overrides)
    return entry


def _gate1(evidence, inputs):
    payload = json.loads(evidence["evidence_file"].read_text(encoding="utf-8"))
    payload["inputs"] = inputs
    _write_json(evidence["evidence_file"], payload)
    records = {item.gate_id: item for item in evaluate_gates(_context(evidence))}
    return records["verify_external_input_identity_licence_and_sha256"]


def test_only_one_archive_supplied_still_blocks(evidence):
    gate = _gate1(evidence, [_archive_entry("L1C")])
    assert gate.status == BLOCKED
    assert "L2A" in gate.blocking_reason
    assert "ACOLITE" in gate.blocking_reason
    assert gate.details["covered_external_archives"] == ["L1C"]


def test_two_of_three_archives_still_blocks(evidence):
    gate = _gate1(evidence, [_archive_entry("L1C"), _archive_entry("L2A")])
    assert gate.status == BLOCKED
    assert "ACOLITE" in gate.blocking_reason
    assert gate.details["covered_external_archives"] == ["L1C", "L2A"]


def test_an_unrelated_complete_input_clears_nothing(evidence):
    gate = _gate1(evidence, [_archive_entry("SOME_OTHER_ARCHIVE")])
    assert gate.status == BLOCKED
    for archive in REQUIRED_EXTERNAL_ARCHIVES:
        assert archive in gate.blocking_reason


@pytest.mark.parametrize("bad", ["", "abc", "z" * 64, "d" * 63, "d" * 65])
def test_malformed_content_sha256_blocks(evidence, bad):
    gate = _gate1(
        evidence,
        [
            _archive_entry(archive, content_sha256=bad)
            for archive in REQUIRED_EXTERNAL_ARCHIVES
        ],
    )
    assert gate.status == BLOCKED
    assert gate.details["covered_external_archives"] == []


def test_a_duplicate_archive_entry_is_ambiguous_coverage_and_fails(evidence):
    gate = _gate1(
        evidence,
        [_archive_entry(archive) for archive in REQUIRED_EXTERNAL_ARCHIVES]
        + [_archive_entry("L1C", content_sha256="f" * 64)],
    )
    assert gate.status == FAIL
    assert "duplicate" in gate.mismatch_reason


def test_an_unverified_licence_blocks(evidence):
    gate = _gate1(
        evidence,
        [
            _archive_entry(archive, licence_verified=False)
            for archive in REQUIRED_EXTERNAL_ARCHIVES
        ],
    )
    assert gate.status == BLOCKED
    assert "licence_verified is not true" in gate.blocking_reason


def test_all_three_archives_complete_clears_the_archive_side(evidence):
    gate = _gate1(
        evidence, [_archive_entry(archive) for archive in REQUIRED_EXTERNAL_ARCHIVES]
    )
    assert gate.status == PASS
    assert gate.details["covered_external_archives"] == ["ACOLITE", "L1C", "L2A"]
    for archive in gate.details["external_satellite_archives"]:
        assert archive["content_checksum_accepted"] is True
        assert archive["declares_raster_content_checksum"] is False


def test_is_sha256_accepts_exactly_64_hex_characters_in_either_case():
    """Hex case carries no meaning; length and alphabet are what is checked."""

    assert is_sha256("a" * 64)
    assert is_sha256("A" * 64)
    assert not is_sha256("a" * 63)
    assert not is_sha256("a" * 65)
    assert not is_sha256("g" * 64)
    assert not is_sha256(None)
    assert not is_sha256("")
    assert not is_sha256("  ")


def test_an_uppercase_recorded_checksum_still_identifies_the_content(tmp_path):
    target = tmp_path / "x.json"
    target.write_bytes(b'{"a": 1}\n')
    matched, detail = match_recorded_checksum(sha256_file(target).upper(), target)
    assert matched is True
    assert detail["checksum_form_matched"] == "working_tree_bytes"


# ---------------------------------------------------------------------------
# D/E. Gate 5 reads expectations from the freeze and requires full coverage
# ---------------------------------------------------------------------------


def _gate5(evidence, **overrides):
    records = {
        item.gate_id: item for item in evaluate_gates(_context(evidence, **overrides))
    }
    return records["verify_acolite_versions_and_effective_settings_match_this_freeze"]


def test_gate5_expectations_come_from_the_freeze_not_the_manifest(evidence):
    """Rewriting the manifest's own copy cannot move the expected commit."""

    _patch_manifest(
        evidence,
        lambda payload: payload["acolite"]["identity"][
            "freeze_declared_identity"
        ].__setitem__("acolite_source_commit", "9" * 40),
    )
    gate = _gate5(evidence)
    assert gate.details["frozen_expectations"]["acolite_source_commit"] == ACOLITE_COMMIT
    assert gate.status == FAIL
    assert "disagrees with the governing freeze" in gate.mismatch_reason


def test_gate5_records_where_its_expectations_came_from(evidence):
    gate = _gate5(evidence)
    assert "governing freeze" in gate.details["expectations_source"]
    assert gate.details["frozen_expectations"]["ancillary_data"] is True
    assert gate.details["frozen_expectations"]["no_silent_product_fallback"] is True


@pytest.mark.parametrize("setting", sorted(SCENE_DECLARED_SETTINGS))
def test_a_setting_declared_by_one_scene_of_1505_does_not_pass(evidence, setting):
    _patch_manifest(
        evidence,
        lambda payload: payload["acolite"]["identity"]["observed_settings"][
            setting
        ].__setitem__("declared_scene_count", 1),
    )
    gate = _gate5(evidence)
    assert gate.status == BLOCKED
    assert "1 of 1505" in gate.blocking_reason
    assert "partial coverage" in gate.blocking_reason


def test_a_setting_declared_by_no_scene_does_not_pass(evidence):
    _patch_manifest(
        evidence,
        lambda payload: payload["acolite"]["identity"]["observed_settings"].pop(
            "ancillary_data"
        ),
    )
    gate = _gate5(evidence)
    assert gate.status == BLOCKED
    assert "no scene declares the effective ACOLITE setting ancillary_data" in (
        gate.blocking_reason
    )


def test_an_unknown_scene_total_blocks_coverage(evidence):
    _patch_manifest(evidence, lambda payload: payload["counts"].pop("acolite_scenes"))
    gate = _gate5(evidence)
    assert gate.status == BLOCKED
    assert "no ACOLITE scene count" in gate.blocking_reason


def test_a_wrong_primary_product_quantity_fails(evidence):
    _patch_manifest(
        evidence,
        lambda payload: payload["extraction_and_qc_rules"]["product_roles"][
            "primary"
        ].__setitem__("quantity", "Rrs"),
    )
    gate = _gate5(evidence)
    assert gate.status == FAIL
    assert "quantity" in gate.mismatch_reason


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["acolite"]["identity"].__setitem__("netcdf_fallback_allowed", True),
        lambda p: p["extraction_and_qc_rules"]["product_roles"].__setitem__(
            "silent_processor_fallback_allowed", True
        ),
    ],
)
def test_a_permitted_product_fallback_fails(evidence, mutate):
    _patch_manifest(evidence, mutate)
    gate = _gate5(evidence)
    assert gate.status == FAIL
    assert "fallback" in gate.mismatch_reason


def test_missing_fallback_flags_block(evidence):
    _patch_manifest(
        evidence, lambda p: p["acolite"]["identity"].pop("netcdf_fallback_allowed")
    )
    gate = _gate5(evidence)
    assert gate.status == BLOCKED
    assert "fallback" in gate.blocking_reason


def test_unavailable_scenes_are_recorded_as_unavailable_not_as_fallback(evidence):
    gate = _gate5(evidence)
    note = gate.details["no_silent_product_fallback_evidence"]["note"]
    assert "not a fallback" in note
    assert gate.status == PASS


def test_absent_polygon_clipping_evidence_fails(evidence):
    _patch_manifest(
        evidence,
        lambda p: p["acolite"]["identity"]["observed_settings"]["polygon"].__setitem__(
            "distinct_values", []
        ),
    )
    gate = _gate5(evidence)
    assert gate.status == FAIL
    assert "polygon clipping" in gate.mismatch_reason


def test_a_polygon_that_is_not_identifiably_the_vomb_roi_blocks(evidence):
    _patch_manifest(
        evidence,
        lambda p: p["acolite"]["identity"]["observed_settings"]["polygon"].__setitem__(
            "distinct_values", ["/srv/roi/some_other_lake.geojson"]
        ),
    )
    gate = _gate5(evidence)
    assert gate.status == BLOCKED
    assert "Vombsjon ROI" in gate.blocking_reason


def test_the_frozen_profile_may_be_attested_by_checksummed_execution_evidence(evidence):
    gate = _gate5(evidence)
    profile = gate.details["profile_evidence"]
    assert profile["declared_per_scene"] is False
    assert profile["attested_in_execution_evidence"] is True
    assert profile["attested_value"] == "inland"
    assert gate.status == PASS


def test_the_frozen_profile_without_any_evidence_blocks(evidence):
    payload = _execution_evidence()
    payload.pop("attested_effective_settings")
    _write_json(evidence["execution_file"], payload)
    gate = _gate5(evidence)
    assert gate.status == BLOCKED
    assert "profile" in gate.blocking_reason
    assert gate.details["profile_evidence"]["attested_in_execution_evidence"] is False


def test_an_attested_profile_contradicting_the_freeze_fails(evidence):
    _write_json(
        evidence["execution_file"],
        _execution_evidence(attested_effective_settings={"profile": "coastal"}),
    )
    gate = _gate5(evidence)
    assert gate.status == FAIL
    assert "profile" in gate.mismatch_reason


# ---------------------------------------------------------------------------
# F. The wrapper commit pins source, not the executed invocation
# ---------------------------------------------------------------------------


def test_a_clean_wrapper_alone_does_not_establish_the_executed_invocation(evidence):
    gate = _gate5(evidence, acolite_execution_evidence_path=None)
    assert gate.status == BLOCKED
    assert "executed ACOLITE invocation is not established" in gate.blocking_reason
    detail = gate.details["execution_provenance"]
    assert detail["evidence_supplied"] is False
    assert detail["wrapper_commit_alone_establishes_execution"] is False


def test_a_documented_pre_specified_false_to_true_correction_is_accepted(evidence):
    gate = _gate5(evidence)
    assert gate.status == PASS
    detail = gate.details["execution_provenance"]
    assert detail["base_wrapper_commit"] == WRAPPER_COMMIT
    assert is_sha256(detail["evidence_sha256"])
    override = detail["overrides"][0]
    assert override["setting"] == "ancillary_data"
    assert override["wrapper_base_value"] is False
    assert override["executed_value"] is True
    assert override["frozen_required_value"] is True
    assert override["override_pre_specified_before_performance"] is True
    assert "not scientific retuning" in detail["note"]


def test_an_arbitrarily_dirty_wrapper_worktree_blocks(evidence):
    gate = _gate5(
        evidence,
        wrapper_observation={
            "head_commit": WRAPPER_COMMIT,
            "worktree_dirty": True,
            "porcelain_entry_count": 4,
            "observation_error": None,
        },
    )
    assert gate.status == BLOCKED
    assert "not assumed harmless" in gate.blocking_reason


def test_an_override_to_a_value_the_freeze_does_not_require_fails(evidence):
    _write_json(
        evidence["execution_file"],
        _execution_evidence(
            overrides=[
                {
                    "setting": "ancillary_data",
                    "wrapper_base_value": False,
                    "executed_value": False,
                    "frozen_required_value": True,
                    "reason_for_override": "kept the wrapper default",
                    "override_pre_specified_before_performance": True,
                }
            ]
        ),
    )
    gate = _gate5(evidence)
    assert gate.status == FAIL
    assert "not the frozen required value" in gate.mismatch_reason


def test_an_override_chosen_after_inspecting_performance_fails(evidence):
    _write_json(
        evidence["execution_file"],
        _execution_evidence(performance_inspected_before_override=True),
    )
    gate = _gate5(evidence)
    assert gate.status == FAIL
    assert "retuning" in gate.mismatch_reason


def test_an_override_not_recorded_as_pre_specified_fails(evidence):
    payload = _execution_evidence()
    payload["overrides"][0]["override_pre_specified_before_performance"] = False
    _write_json(evidence["execution_file"], payload)
    gate = _gate5(evidence)
    assert gate.status == FAIL
    assert "pre-specified" in gate.mismatch_reason


def test_an_override_of_a_setting_the_freeze_does_not_govern_blocks(evidence):
    payload = _execution_evidence()
    payload["overrides"].append(
        {
            "setting": "some_local_tweak",
            "wrapper_base_value": 1,
            "executed_value": 2,
            "frozen_required_value": 2,
            "reason_for_override": "local convenience",
            "override_pre_specified_before_performance": True,
        }
    )
    _write_json(evidence["execution_file"], payload)
    gate = _gate5(evidence)
    assert gate.status == BLOCKED
    assert "not a property the governing freeze declares" in gate.blocking_reason


def test_an_override_misstating_the_frozen_required_value_fails(evidence):
    payload = _execution_evidence()
    payload["overrides"][0]["frozen_required_value"] = False
    _write_json(evidence["execution_file"], payload)
    gate = _gate5(evidence)
    assert gate.status == FAIL
    assert "misstates the frozen required value" in gate.mismatch_reason


def test_an_override_without_a_recorded_reason_blocks(evidence):
    payload = _execution_evidence()
    payload["overrides"][0]["reason_for_override"] = "  "
    _write_json(evidence["execution_file"], payload)
    gate = _gate5(evidence)
    assert gate.status == BLOCKED
    assert "records no reason_for_override" in gate.blocking_reason


def test_execution_evidence_declaring_the_wrong_base_wrapper_commit_fails(evidence):
    _write_json(
        evidence["execution_file"], _execution_evidence(base_wrapper_commit="7" * 40)
    )
    gate = _gate5(evidence)
    assert gate.status == FAIL
    assert "not the frozen wrapper commit" in gate.mismatch_reason


def test_execution_evidence_without_a_script_checksum_blocks(evidence):
    _write_json(
        evidence["execution_file"], _execution_evidence(execution_script_sha256="nope")
    )
    gate = _gate5(evidence)
    assert gate.status == BLOCKED
    assert "execution_script_sha256" in gate.blocking_reason


def test_execution_evidence_with_the_wrong_schema_version_blocks(evidence):
    _write_json(
        evidence["execution_file"], _execution_evidence(schema_version="something_else")
    )
    gate = _gate5(evidence)
    assert gate.status == BLOCKED
    assert "schema_version" in gate.blocking_reason


# ---------------------------------------------------------------------------
# G. Gate 4 cross-checks materialized table content, not just existence
# ---------------------------------------------------------------------------


def _gate4(evidence):
    records = {item.gate_id: item for item in evaluate_gates(_context(evidence))}
    return records["materialize_qc_and_same_day_deduplication_audit"]


def test_a_truncated_extraction_table_fails(evidence):
    _write_csv(
        evidence["satellite"] / "vombsjon_product_extraction_master.csv",
        [{"method": "ACOLITE", "row": 0}],
    )
    gate = _gate4(evidence)
    assert gate.status == FAIL
    assert "1 data row" in gate.mismatch_reason


def test_an_emptied_table_fails(evidence):
    (evidence["satellite"] / "vombsjon_fixed_station_observation_master.csv").write_text(
        "method,row\n", encoding="utf-8", newline=""
    )
    gate = _gate4(evidence)
    assert gate.status == FAIL
    assert "0 data row" in gate.mismatch_reason


def test_row_counts_are_cross_checked_against_the_manifest(evidence):
    _patch_manifest(
        evidence, lambda payload: payload["counts"].__setitem__("same_day_rows", 99)
    )
    gate = _gate4(evidence)
    assert gate.status == FAIL
    assert "same_day_rows=99" in gate.mismatch_reason


def test_a_manifest_without_a_row_count_blocks_the_cross_check(evidence):
    _patch_manifest(evidence, lambda payload: payload["counts"].pop("extraction_rows"))
    gate = _gate4(evidence)
    assert gate.status == BLOCKED
    assert "cannot be cross-checked" in gate.blocking_reason


def test_row_checks_are_recorded_for_every_materialized_table(evidence):
    gate = _gate4(evidence)
    checks = gate.details["materialized_row_checks"]
    assert set(checks) == {
        "vombsjon_product_extraction_master.csv",
        "vombsjon_fixed_station_observation_master.csv",
        "vombsjon_same_day_observation_master.csv",
    }
    for check in checks.values():
        assert check["observed_rows"] == check["expected_rows"]


# ---------------------------------------------------------------------------
# H. Gate 7 parses the committed polygon files, not only the manifest summary
# ---------------------------------------------------------------------------


def _gate7(evidence):
    records = {item.gate_id: item for item in evaluate_gates(_context(evidence))}
    return records[
        "materialize_the_fixed_pelagic_field_validation_polygon_and_its_provenance"
    ]


def test_an_emptied_geojson_fails_although_the_manifest_is_unchanged(evidence):
    _write_json(evidence["satellite"] / "vombsjon_field_sampling_area.geojson", {})
    gate = _gate7(evidence)
    assert gate.status == FAIL
    assert "exactly one" in gate.mismatch_reason


def test_a_geojson_with_the_wrong_vertex_count_fails(evidence):
    _write_json(
        evidence["satellite"] / "vombsjon_field_sampling_area.geojson",
        _polygon_geojson(POLYGON_RING[:4]),
    )
    gate = _gate7(evidence)
    assert gate.status == FAIL
    assert "4 vertices" in gate.mismatch_reason


def test_an_unclosed_geojson_ring_fails(evidence):
    payload = _polygon_geojson()
    payload["features"][0]["geometry"]["coordinates"][0].pop()
    _write_json(evidence["satellite"] / "vombsjon_field_sampling_area.geojson", payload)
    gate = _gate7(evidence)
    assert gate.status == FAIL
    assert "not closed" in gate.mismatch_reason


def test_a_replaced_geometry_type_fails(evidence):
    payload = _polygon_geojson()
    payload["features"][0]["geometry"]["type"] = "MultiPolygon"
    _write_json(evidence["satellite"] / "vombsjon_field_sampling_area.geojson", payload)
    gate = _gate7(evidence)
    assert gate.status == FAIL
    assert "geometry type" in gate.mismatch_reason


def test_the_ring_closing_position_is_not_counted_as_a_vertex(evidence):
    gate = _gate7(evidence)
    geometry = gate.details["committed_geometry"]
    assert geometry["parsed"] is True
    assert geometry["ring_position_count"] == 7
    assert geometry["ring_is_closed"] is True
    assert geometry["vertex_count"] == 6
    assert gate.status == PASS


def test_an_altered_accepted_construction_point_set_fails(evidence):
    _write_csv(
        evidence["satellite"] / "vombsjon_field_sampling_area_provenance.csv",
        _provenance_rows(accepted=19),
    )
    gate = _gate7(evidence)
    assert gate.status == FAIL
    assert "accepted construction point" in gate.mismatch_reason


def test_an_unresolved_date_accepted_as_a_construction_point_fails(evidence):
    rows = _provenance_rows()
    rows[0]["label"] = "2020-06-10"
    rows[0]["accepted_for_polygon"] = True
    _write_csv(
        evidence["satellite"] / "vombsjon_field_sampling_area_provenance.csv", rows
    )
    gate = _gate7(evidence)
    assert gate.status == FAIL
    assert "2020-06-10" in gate.mismatch_reason


def test_a_removed_hull_vertex_row_fails(evidence):
    rows = [
        row
        for row in _provenance_rows()
        if not (row["record_type"] == "hull_vertex" and row["label"] == "vertex_6")
    ]
    _write_csv(
        evidence["satellite"] / "vombsjon_field_sampling_area_provenance.csv", rows
    )
    gate = _gate7(evidence)
    assert gate.status == FAIL
    assert "hull vertex" in gate.mismatch_reason


def test_polygon_evidence_files_are_anchored_by_content_checksum(evidence):
    gate = _gate7(evidence)
    assert is_sha256(gate.details["committed_geometry"]["sha256"])
    assert is_sha256(gate.details["committed_provenance"]["sha256"])
    assert gate.details["committed_provenance"]["accepted_source_point_count"] == 22
    assert gate.details["committed_provenance"]["nominal_anchor_accepted"] == 1


# ---------------------------------------------------------------------------
# I. No performance leakage anywhere in the hardened layer
# ---------------------------------------------------------------------------


def test_the_hardened_manifest_anchors_every_evidence_file_by_checksum(evidence):
    context = _context(evidence)
    manifest = build_manifest(
        evaluate_gates(context),
        context=context,
        repository_state=CLEAN_STATE,
        runtime_result=_passing_runtime(),
    )
    anchored = manifest["evidence"]
    for key in (
        "satellite_input_audit",
        "field_input_audit",
        "field_source_manifest",
        "timesat_defaults_snapshot",
        "polygon_geojson",
        "polygon_provenance",
    ):
        assert anchored[key]["present"] is True, key
        assert is_sha256(anchored[key]["sha256"]), key
    for key in (
        "governing_freeze",
        "external_input_evidence",
        "acolite_execution_evidence",
    ):
        assert is_sha256(anchored[key]["sha256"]), key
    assert anchored["governing_freeze"][
        "vombsjon_performance_execution_authorized"
    ] is False


def test_the_hardened_manifest_reports_both_closure_halves(evidence):
    context = _context(evidence)
    manifest = build_manifest(
        evaluate_gates(context),
        context=context,
        repository_state=dict(CLEAN_STATE, repository_worktree_dirty_at_start=True),
        runtime_result=_passing_runtime(),
    )
    assert manifest["seven_gates_passed"] is True
    assert manifest["repository_provenance_ready"] is False
    assert manifest["gate_closure_complete"] is False
    assert manifest["performance_execution_eligible"] is False
    assert manifest["performance_execution_authorized"] is False


def test_the_hardened_layer_still_names_no_performance_quantity():
    """Nothing added by hardening may compute or read a performance metric."""

    import twinwater_timesat.vombsjon_execution_gates as gates

    source = Path(gates.__file__).read_text(encoding="utf-8").lower()
    for forbidden in (
        "nrmse",
        "rmse",
        "r_squared",
        "pearson",
        "linregress",
        "reconstructed_daily",
        "curve_fit",
        "polyfit",
    ):
        assert forbidden not in source, forbidden
