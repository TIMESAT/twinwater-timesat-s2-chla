"""Tests for the Vombsjon pre-performance execution-gate closure layer.

Every test runs against synthetic evidence in a temporary directory. No test
touches the real HPC archives, the real TIMESAT binary, or any Vombsjon
reconstruction or performance output: gate closure guards performance and must
never read it.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from twinwater_timesat.vombsjon_execution_gates import (
    BLOCKED,
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
        "counts": {
            "l1c_products": 1509,
            "l2a_products": 1510,
            "acolite_scenes": 1505,
            "exact_unique_l1c_l2a_pairs": 1466,
            "failure_rows": 48,
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
                    "acolite_version": {
                        "declared_scene_count": 0,
                        "distinct_values": [],
                        "status": "not_verifiable_from_supplied_files",
                    },
                },
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


@pytest.fixture
def evidence(tmp_path: Path) -> dict:
    """Build a complete synthetic evidence tree that yields 7/7 PASS."""

    root = tmp_path / "repo"
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
        "vombsjon_product_extraction_master.csv",
        "vombsjon_native_qa_inventory.csv",
        "vombsjon_fixed_station_observation_master.csv",
        "vombsjon_field_sampling_area.geojson",
        "vombsjon_field_sampling_area_provenance.csv",
    ):
        (satellite / name).write_text("placeholder\n", encoding="utf-8", newline="\n")

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

    return {
        "root": root,
        "satellite": satellite,
        "field": field,
        "snapshot": snapshot,
        "evidence_file": evidence_file,
    }


def _context(evidence: dict, **overrides) -> GateContext:
    root = evidence["root"]
    context = build_context(
        repository_root=root,
        freeze_path=REAL_FREEZE,
        satellite_audit_dir=evidence["satellite"],
        field_audit_dir=evidence["field"],
        timesat_snapshot_path=evidence["snapshot"],
        external_input_evidence_path=overrides.pop(
            "external_input_evidence_path", evidence["evidence_file"]
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
    summary = summarize(records)
    assert summary["gate_closure_complete"] is True
    assert summary["performance_execution_eligible"] is True
    assert summary["performance_execution_authorized"] is False


def test_any_blocked_gate_denies_eligibility(evidence):
    context = _context(evidence, acolite_source_observation=None)
    records = evaluate_gates(context)
    summary = summarize(records)
    assert summary["n_blocked"] >= 1
    assert summary["gate_closure_complete"] is False
    assert summary["performance_execution_eligible"] is False


def test_any_failed_gate_denies_eligibility(evidence):
    _patch_manifest(
        evidence,
        lambda payload: payload["counts"].__setitem__("l1c_products", 1),
    )
    records = evaluate_gates(_context(evidence))
    summary = summarize(records)
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
    assert "no raster/content SHA256 evidence" in gate.blocking_reason


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
        repository_state={"captured_before_writing_outputs": True},
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
        repository_state={"captured_before_writing_outputs": True},
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
        repository_state={"captured_before_writing_outputs": True},
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
        repository_state={"captured_before_writing_outputs": True},
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
