"""Governance tests for the Vombsjon satellite input audit version succession.

v1.2 is an external ACOLITE execution correction, not a scientific amendment.
These tests hold that line: they prove the scientific sections of the v1.2
configuration are identical to v1.1, that v1.1 remains preserved and loadable
as historical provenance, that each version writes only into its own output
namespace, and that the freeze cross-check still passes for both.

Nothing here touches the real Sentinel-2 or ACOLITE archives; every check runs
against committed repository files only.
"""

from pathlib import Path

import pytest
import yaml

from twinwater_timesat.vombsjon_satellite_audit import (
    AUDIT_VERSION_CONFIGS,
    AUDIT_VERSION_OUTPUT_ROOTS,
    CURRENT_AUDIT_VERSION,
    DEFAULT_CONFIG_RELATIVE_PATH,
    RECOGNIZED_AUDIT_VERSIONS,
    RETIRED_AUDIT_CONFIGS,
    VombsjonAuditConfigError,
    VombsjonScopeError,
    assert_output_path_allowed,
    crosscheck_freeze,
    default_config_path,
    load_audit_config,
    load_transfer_freeze,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

V11 = "vombsjon_satellite_input_audit_v1.1"
V12 = "vombsjon_satellite_input_audit_v1.2"

# Sections that carry scientific rules. v1.2 must not differ from v1.1 in any
# of them; that is the whole claim the version bump makes.
SCIENTIFIC_SECTIONS: tuple[str, ...] = (
    "scope",
    "field_source",
    "fixed_target",
    "field_polygon",
    "field_gps_sensitivity",
    "products",
    "grid",
    "radiometry",
    "native_qa",
    "pairing",
    "acolite",
    "indices",
    "observation",
    "same_day",
    "field_matchup",
)

# The only top-level keys v1.2 is allowed to differ in.
ALLOWED_TOP_LEVEL_DIFFERENCES: frozenset[str] = frozenset(
    {
        "audit_version",
        "status",
        "amendment",
        "execution_correction",
        "freeze",
        "outputs",
    }
)


def _config_path(version: str) -> Path:
    return REPO_ROOT / AUDIT_VERSION_CONFIGS[version]


def _raw(version: str) -> dict:
    with _config_path(version).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


# ---------------------------------------------------------------------------
# Version registry
# ---------------------------------------------------------------------------


def test_v12_is_the_current_default_version():
    assert CURRENT_AUDIT_VERSION == V12
    assert DEFAULT_CONFIG_RELATIVE_PATH == AUDIT_VERSION_CONFIGS[V12]
    assert default_config_path(REPO_ROOT) == _config_path(V12)


def test_both_versions_are_recognized_and_v11_is_preserved():
    assert set(RECOGNIZED_AUDIT_VERSIONS) == {V11, V12}
    # v1.1 must stay on disk and stay loadable: its committed outputs have to
    # remain reproducible from the repository.
    assert _config_path(V11).is_file()
    assert load_audit_config(
        _config_path(V11), repository_root=REPO_ROOT
    ).audit_version == V11


def test_v10_is_retired_and_not_executable():
    retired = REPO_ROOT / RETIRED_AUDIT_CONFIGS[0]
    assert retired.is_file(), "v1.0 is preserved for provenance"
    with pytest.raises(VombsjonAuditConfigError):
        load_audit_config(retired, repository_root=REPO_ROOT)


# ---------------------------------------------------------------------------
# v1.2 loads and is confined to its own namespace
# ---------------------------------------------------------------------------


def test_v12_config_loads():
    config = load_audit_config(_config_path(V12), repository_root=REPO_ROOT)
    assert config.audit_version == V12
    assert config.sha256
    assert config.source_relative_path == AUDIT_VERSION_CONFIGS[V12]


@pytest.mark.parametrize("version", [V11, V12])
def test_each_version_declares_its_own_output_root(version):
    config = load_audit_config(_config_path(version), repository_root=REPO_ROOT)
    assert (
        str(config.section("outputs")["root"]).strip("/")
        == AUDIT_VERSION_OUTPUT_ROOTS[version]
    )


def test_v12_output_is_confined_to_its_namespace():
    config = load_audit_config(_config_path(V12), repository_root=REPO_ROOT)
    allowed = REPO_ROOT / AUDIT_VERSION_OUTPUT_ROOTS[V12] / "x.csv"
    assert assert_output_path_allowed(
        allowed, config, repository_root=REPO_ROOT
    ).is_relative_to(REPO_ROOT / AUDIT_VERSION_OUTPUT_ROOTS[V12])


@pytest.mark.parametrize(
    "refused",
    [
        "results/vombsjon/satellite_input_audit/v1.1/x.csv",
        "results/vombsjon/satellite_input_audit/v1.0/x.csv",
        "results/vombsjon/field_input_audit/v1.0/x.csv",
        "results/phase6a/x.csv",
        "config/x.yaml",
    ],
)
def test_v12_cannot_write_outside_its_namespace(refused):
    """A v1.2 run must never touch v1.1's immutable committed outputs."""

    config = load_audit_config(_config_path(V12), repository_root=REPO_ROOT)
    with pytest.raises(VombsjonScopeError):
        assert_output_path_allowed(
            REPO_ROOT / refused, config, repository_root=REPO_ROOT
        )


def test_v12_protects_the_v11_namespace_explicitly():
    config = load_audit_config(_config_path(V12), repository_root=REPO_ROOT)
    protected = {
        str(prefix).strip("/")
        for prefix in config.section("outputs")["protected_prefixes"]
    }
    assert AUDIT_VERSION_OUTPUT_ROOTS[V11] in protected


def test_v11_committed_outputs_are_still_present():
    committed = REPO_ROOT / AUDIT_VERSION_OUTPUT_ROOTS[V11]
    assert committed.is_dir()
    assert (committed / "vombsjon_satellite_input_audit_manifest.json").is_file()


# ---------------------------------------------------------------------------
# v1.2 changed no scientific rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("section", SCIENTIFIC_SECTIONS)
def test_scientific_sections_are_identical_between_v11_and_v12(section):
    assert _raw(V11)[section] == _raw(V12)[section]


def test_only_governance_and_output_keys_differ():
    v11, v12 = _raw(V11), _raw(V12)
    assert set(v12) - set(v11) == {"execution_correction"}
    differing = {
        key
        for key in set(v11) | set(v12)
        if v11.get(key) != v12.get(key)
    }
    assert differing <= ALLOWED_TOP_LEVEL_DIFFERENCES, (
        f"v1.2 differs from v1.1 outside the allowed governance keys: "
        f"{sorted(differing - ALLOWED_TOP_LEVEL_DIFFERENCES)}"
    )


def test_freeze_section_differs_only_in_protocol_pointers():
    v11_freeze = dict(_raw(V11)["freeze"])
    v12_freeze = dict(_raw(V12)["freeze"])
    for pointer in ("protocol", "inherited_protocol"):
        v11_freeze.pop(pointer, None)
        v12_freeze.pop(pointer, None)
    # The governing freeze file, its expected version, the authorized stage and
    # the full cross-check list must be identical.
    assert v11_freeze == v12_freeze


def test_outputs_differ_only_in_root_and_the_added_protection():
    v11_outputs = dict(_raw(V11)["outputs"])
    v12_outputs = dict(_raw(V12)["outputs"])
    assert v11_outputs["files"] == v12_outputs["files"]
    assert v11_outputs["root"] == AUDIT_VERSION_OUTPUT_ROOTS[V11]
    assert v12_outputs["root"] == AUDIT_VERSION_OUTPUT_ROOTS[V12]
    added = set(v12_outputs["protected_prefixes"]) - set(
        v11_outputs["protected_prefixes"]
    )
    assert added == {AUDIT_VERSION_OUTPUT_ROOTS[V11]}


def test_v12_declares_itself_a_non_scientific_correction():
    v12 = _raw(V12)
    amendment = v12["amendment"]
    assert amendment["supersedes"] == V11
    assert amendment["supersedes_file"] == AUDIT_VERSION_CONFIGS[V11]
    assert amendment["predecessor_preserved"] is True
    assert amendment["scientific_amendment"] is False
    assert amendment["scientific_rules_changed"] is False

    correction = v12["execution_correction"]
    assert correction["scientific_rule_changed"] is False
    assert correction["scientific_parameter_selected_or_changed"] is False
    assert correction["vombsjon_performance_inspected_before_correction"] is False
    assert correction["vombsjon_field_correlation_or_regression_inspected"] is False
    assert correction["corrected_setting"] == "ancillary_data"
    assert correction["previous_external_value"] is False
    assert correction["corrected_external_value"] is True


# ---------------------------------------------------------------------------
# Freeze conformance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("version", [V11, V12])
def test_freeze_crosscheck_passes(version):
    config = load_audit_config(_config_path(version), repository_root=REPO_ROOT)
    freeze = load_transfer_freeze(config, repository_root=REPO_ROOT)
    rows = crosscheck_freeze(config, freeze)
    assert rows
    assert all(row["agrees"] for row in rows)


@pytest.mark.parametrize("version", [V11, V12])
def test_ancillary_data_is_true_in_the_freeze_declared_identity(version):
    """The freeze always required ancillary_data=True; v1.2 only makes the
    external execution conform to it."""

    config = load_audit_config(_config_path(version), repository_root=REPO_ROOT)
    declared = config.section("acolite")["freeze_declared_identity"]
    assert declared["ancillary_data"] is True

    freeze = load_transfer_freeze(config, repository_root=REPO_ROOT)
    frozen_product = freeze.values["observation_layer"]["primary_processing_product"]
    assert frozen_product["ancillary_data"] is True


def test_frozen_acolite_source_commit_is_unchanged():
    """The Git commit is the stable ACOLITE source identity and must not move."""

    commit = "64a02ff386e2985eef68ae00198b38e04f3c4a1f"
    for version in (V11, V12):
        config = load_audit_config(_config_path(version), repository_root=REPO_ROOT)
        assert (
            config.section("acolite")["freeze_declared_identity"][
                "acolite_source_commit"
            ]
            == commit
        )
    v12 = _raw(V12)["execution_correction"]
    assert v12["acolite_stable_source_commit"] == commit
    assert v12["unchanged_external_settings"]["acolite_source_commit"] == commit
    # The cYYYY-... version string is checkout metadata, not a source id, so the
    # freeze must not have been rewritten to chase it.
    assert v12["acolite_version_string_is_stable_source_identity"] is False
    assert v12["frozen_acolite_version_string_rewritten"] is False


def test_both_versions_govern_the_same_unchanged_freeze_file():
    v11 = load_audit_config(_config_path(V11), repository_root=REPO_ROOT)
    v12 = load_audit_config(_config_path(V12), repository_root=REPO_ROOT)
    assert (
        v11.section("freeze")["config_path"] == v12.section("freeze")["config_path"]
    )
    assert load_transfer_freeze(v11, repository_root=REPO_ROOT).sha256 == (
        load_transfer_freeze(v12, repository_root=REPO_ROOT).sha256
    )
