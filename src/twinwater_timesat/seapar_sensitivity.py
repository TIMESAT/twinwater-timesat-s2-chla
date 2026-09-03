"""Governed double-logistic p_seapar sensitivity workflow utilities."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

import pandas as pd

from twinwater_timesat.phase3_contract import (
    PRIMARY_YEARS,
    canonical_json_payload_sha256,
    sha256_file,
)
from twinwater_timesat.phase3_preflight import (
    deterministic_table_sha256,
    write_deterministic_csv,
    write_deterministic_json,
)
from twinwater_timesat.timesat_adapter import SubprocessTimesatRunner


STARTING_COMMIT = "ce2fd7d5fa039584ccb1f6f0751dc46acedd0be1"
CLASSIFICATION = "secondary_sensitivity_double_logistic_seasonal_parameter"
PROTOCOL_VERSION = "Double_Logistic_Seasonal_Parameter_Sensitivity_Protocol_v1.0"
SEAPAR_GRID = tuple(round(index / 10, 1) for index in range(11))
CONFIG_PATH = "config/double_logistic_seapar_sensitivity_v1.0.json"
PARENT_OUTPUT_DIRECTORIES = (
    "results/phase3/preflight",
    "results/phase3/actual_mask",
    "results/phase3/event_preflight",
    "results/phase3/event_actual_mask",
    "results/phase4/random_deletion",
    "results/phase4/consecutive_gaps",
    "results/phase4/synthesis",
    "results/phase4/review/trajectories",
)


class SeaparSensitivityGuardError(RuntimeError):
    """Raised at a hard workflow boundary before unauthorized computation."""


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def require_clean_descendant(root: str | Path) -> str:
    """Require a clean commit descending from the workflow's frozen start."""

    root = Path(root)
    if _git(root, "status", "--porcelain"):
        raise SeaparSensitivityGuardError(
            "Refusing p_seapar sensitivity execution because the Git worktree is dirty."
        )
    lineage = subprocess.run(
        ["git", "merge-base", "--is-ancestor", STARTING_COMMIT, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if lineage.returncode != 0:
        raise SeaparSensitivityGuardError(
            f"HEAD is not a descendant of required starting commit {STARTING_COMMIT}."
        )
    return _git(root, "rev-parse", "HEAD")


def load_seapar_sensitivity_config(root: str | Path) -> dict[str, Any]:
    """Load the frozen config and validate its self and parent hashes."""

    root = Path(root)
    path = root / CONFIG_PATH
    config = json.loads(path.read_text(encoding="utf-8"))
    expected_payload = config.get("config_payload_sha256")
    actual_payload = canonical_json_payload_sha256(
        config, excluded_keys=("config_payload_sha256",)
    )
    if expected_payload != actual_payload:
        raise SeaparSensitivityGuardError("Sensitivity config payload checksum mismatch.")
    if config.get("protocol_version") != PROTOCOL_VERSION:
        raise SeaparSensitivityGuardError("Unexpected sensitivity protocol version.")
    if config.get("analysis_classification") != CLASSIFICATION:
        raise SeaparSensitivityGuardError("Unexpected sensitivity classification.")
    if config.get("starting_commit") != STARTING_COMMIT:
        raise SeaparSensitivityGuardError("Sensitivity starting commit changed.")
    if tuple(config["timesat"]["candidate_grid"]) != SEAPAR_GRID:
        raise SeaparSensitivityGuardError("Frozen p_seapar candidate grid changed.")
    if tuple(config["selection"]["outer_fold_years"]) != PRIMARY_YEARS:
        raise SeaparSensitivityGuardError("Frozen outer-fold years changed.")
    for section in ("protocol_document", "parent_contract", "parent_event_protocol"):
        item = config[section]
        if sha256_file(root / item["path"]) != item["sha256"]:
            raise SeaparSensitivityGuardError(f"{section} document checksum mismatch.")
    for section in ("parent_contract", "parent_event_protocol"):
        item = config[section]
        if sha256_file(root / item["config_path"]) != item["config_file_sha256"]:
            raise SeaparSensitivityGuardError(f"{section} config checksum mismatch.")
    if not config.get("original_outputs_remain_untouched"):
        raise SeaparSensitivityGuardError("Original-output immutability is not frozen.")
    if not config.get("event_metrics_never_used_for_tuning"):
        raise SeaparSensitivityGuardError("Event exclusion from tuning is not frozen.")
    if not config.get("vombsjon_forbidden"):
        raise SeaparSensitivityGuardError("The Vombsjön prohibition is not frozen.")
    return config


def parent_output_inventory(root: str | Path) -> dict[str, str]:
    """Hash only the explicitly allowed original Erken output directories."""

    root = Path(root)
    inventory: dict[str, str] = {}
    for relative_directory in PARENT_OUTPUT_DIRECTORIES:
        directory = root / relative_directory
        if not directory.is_dir():
            raise SeaparSensitivityGuardError(
                f"Required frozen output directory is missing: {relative_directory}"
            )
        for path in sorted(item for item in directory.iterdir() if item.is_file()):
            relative = str(path.relative_to(root))
            inventory[relative] = sha256_file(path)
    if not inventory:
        raise SeaparSensitivityGuardError("Frozen parent-output inventory is empty.")
    return inventory


def validate_parent_output_inventory(
    root: str | Path, expected: Mapping[str, str]
) -> None:
    """Fail if any allowlisted original output was added, removed, or changed."""

    observed = parent_output_inventory(root)
    if dict(expected) != observed:
        missing = sorted(set(expected) - set(observed))
        added = sorted(set(observed) - set(expected))
        changed = sorted(
            path
            for path in set(expected) & set(observed)
            if expected[path] != observed[path]
        )
        raise SeaparSensitivityGuardError(
            "Frozen parent outputs changed; "
            f"missing={missing}, added={added}, changed={changed}."
        )


def build_seapar_preperformance_products(
    *,
    repository_root: str | Path,
    timesat_python: str | Path,
    runtime_script: str | Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Run S0 gates without evaluating any real Erken reconstruction."""

    root = Path(repository_root)
    commit = require_clean_descendant(root)
    config = load_seapar_sensitivity_config(root)
    snapshot_path = root / config["timesat"]["defaults_snapshot_path"]
    runner = SubprocessTimesatRunner(
        python_executable=timesat_python,
        runtime_script=runtime_script,
        snapshot_path=snapshot_path,
    )
    result = runner.verify_seapar_grid(SEAPAR_GRID)
    rows = []
    for check in result["candidate_checks"]:
        row = dict(check)
        row["runtime_nseason"] = ";".join(map(str, row["runtime_nseason"]))
        rows.append(row)
    candidates = pd.DataFrame(rows)
    exact_grid = tuple(candidates["requested_p_seapar"].tolist()) == SEAPAR_GRID
    exact_effective = bool(candidates["effective_equals_requested"].all())
    all_smoke = bool(
        candidates["reconstruction_status"].eq("ok").all()
        and candidates["n_output_dates"].eq(365).all()
        and candidates["n_finite_output_dates"].eq(365).all()
    )
    gates = {
        "config_and_governing_hashes_valid": True,
        "repository_clean_descendant": True,
        "candidate_grid_exact": exact_grid,
        "all_candidates_exactly_materialized_without_coercion": exact_effective,
        "all_candidates_pass_synthetic_smoke_test": all_smoke,
        "runtime_defaults_match_frozen_snapshot": bool(
            result["runtime"]["runtime_defaults_match_snapshot"]
        ),
        "original_outputs_inventoried_before_performance": True,
        "no_real_sensitivity_performance_generated": True,
        "vombsjon_not_accessed": True,
    }
    if not all(gates.values()):
        failed = [name for name, passed in gates.items() if not passed]
        raise SeaparSensitivityGuardError(
            "S0 pre-performance gate failed: " + ", ".join(failed)
        )
    tables = {
        "erken_phase5_seapar_runtime_candidate_preflight.csv": candidates,
    }
    manifest: dict[str, Any] = {
        "schema_version": "erken_phase5_seapar_preperformance_manifest_v1",
        "protocol_version": PROTOCOL_VERSION,
        "analysis_classification": CLASSIFICATION,
        "repository_commit": commit,
        "repository_worktree_dirty": False,
        "starting_commit": STARTING_COMMIT,
        "protocol_path": config["protocol_document"]["path"],
        "protocol_sha256": config["protocol_document"]["sha256"],
        "config_path": CONFIG_PATH,
        "config_file_sha256": sha256_file(root / CONFIG_PATH),
        "config_payload_sha256": config["config_payload_sha256"],
        "parent_contract_version": config["parent_contract"]["version"],
        "parent_contract_sha256": config["parent_contract"]["sha256"],
        "parent_event_protocol_version": config["parent_event_protocol"]["version"],
        "parent_event_protocol_sha256": config["parent_event_protocol"]["sha256"],
        "candidate_grid": list(SEAPAR_GRID),
        "original_default_p_seapar": config["timesat"][
            "original_default_p_seapar"
        ],
        "runtime": result["runtime"],
        "runtime_candidate_table_sha256": deterministic_table_sha256(candidates),
        "parent_output_sha256": parent_output_inventory(root),
        "gates": gates,
        "all_preperformance_gates_passed": True,
        "real_sensitivity_performance_generated": False,
        "real_sensitivity_performance_inspected": False,
        "event_metrics_used_for_tuning": False,
        "vombsjon_accessed": False,
    }
    manifest["manifest_payload_sha256"] = canonical_json_payload_sha256(manifest)
    return tables, manifest


def write_seapar_preperformance_products(
    tables: Mapping[str, pd.DataFrame],
    manifest: Mapping[str, Any],
    output_directory: str | Path,
) -> list[Path]:
    output = Path(output_directory)
    paths = [
        write_deterministic_csv(table, output / name)
        for name, table in tables.items()
    ]
    paths.append(
        write_deterministic_json(
            manifest, output / "erken_phase5_seapar_preperformance_manifest.json"
        )
    )
    return paths


def load_passed_seapar_preflight(root: str | Path) -> dict[str, Any]:
    """Load S0 evidence and revalidate its payload and immutable parents."""

    root = Path(root)
    path = (
        root
        / "results/phase5/double_logistic_seapar_preflight/"
        "erken_phase5_seapar_preperformance_manifest.json"
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("manifest_payload_sha256") != canonical_json_payload_sha256(
        manifest, excluded_keys=("manifest_payload_sha256",)
    ):
        raise SeaparSensitivityGuardError("S0 manifest payload checksum mismatch.")
    if manifest.get("all_preperformance_gates_passed") is not True:
        raise SeaparSensitivityGuardError("S0 pre-performance gates are not passed.")
    if manifest.get("real_sensitivity_performance_generated") is not False:
        raise SeaparSensitivityGuardError("S0 manifest has an invalid performance state.")
    validate_parent_output_inventory(root, manifest["parent_output_sha256"])
    load_seapar_sensitivity_config(root)
    return manifest
