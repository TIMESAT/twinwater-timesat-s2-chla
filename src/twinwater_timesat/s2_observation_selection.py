"""Frozen post-pilot Erken Sentinel-2 observation selection.

This module consumes only committed Phase 6A/6B QA and index tables.  It must
never read CHLF or an ice-status field: the purpose is to freeze observation
availability before any field-matchup or scientific processor comparison.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .s2_pilot_summary import write_rows


DEFAULT_CONFIG_RELATIVE_PATH = "config/erken_s2_observation_selection_v1.0.yaml"
EXPECTED_SCHEMA_VERSION = "erken_s2_observation_selection_config_v1"
EXPECTED_SELECTION_VERSION = "erken_s2_observation_selection_v1.0"
EXPECTED_RULE_ID = "erken_s2_primary3x3_min6_v1"
EXPECTED_METHODS = ("L1C", "L2A", "ACOLITE")
PROHIBITED_INPUT_COLUMNS = {"CHLF", "PRESENCE_ICE"}
METRIC_COLUMNS = {
    "ndci": ("NDCI_valid_pixel_count", "NDCI_median"),
    "mci": ("MCI_valid_pixel_count", "MCI_median"),
    "common_b456": ("common_B456_valid_count", None),
}


class ObservationSelectionError(RuntimeError):
    """Raised when the frozen selection contract cannot be satisfied."""


@dataclass(frozen=True)
class ObservationSelectionConfig:
    """Validated frozen selection configuration and its provenance identity."""

    values: Mapping[str, Any]
    source_relative_path: str
    sha256: str

    @property
    def minimum_valid_pixels(self) -> int:
        return int(self.values["selection"]["minimum_valid_pixels"])

    @property
    def selection_version(self) -> str:
        return str(self.values["selection_version"])

    @property
    def rule_id(self) -> str:
        return str(self.values["selection"]["rule_id"])


@dataclass(frozen=True)
class ObservationSelectionResult:
    """Deterministic unified rows and the metadata used to write them."""

    rows: tuple[dict[str, Any], ...]
    input_paths: Mapping[str, Path]
    counts: Mapping[str, Any]


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_config_path(repository_root: str | Path) -> Path:
    return Path(repository_root) / DEFAULT_CONFIG_RELATIVE_PATH


def load_selection_config(
    path: str | Path, *, repository_root: str | Path | None = None
) -> ObservationSelectionConfig:
    """Load and strictly validate the frozen post-pilot selection config."""

    source = Path(path)
    if not source.is_file():
        raise ObservationSelectionError(f"Selection config not found: {source}")
    with source.open(encoding="utf-8") as handle:
        values = yaml.safe_load(handle)
    if not isinstance(values, Mapping):
        raise ObservationSelectionError("Selection config must be a YAML mapping.")

    required = {"scope", "inputs", "selection", "qa_freeze", "indices", "outputs"}
    missing = sorted(required - set(values))
    if missing:
        raise ObservationSelectionError(
            f"Selection config is missing required section(s): {missing}."
        )
    if values.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise ObservationSelectionError("Unexpected observation-selection schema.")
    if values.get("selection_version") != EXPECTED_SELECTION_VERSION:
        raise ObservationSelectionError("Unexpected observation-selection version.")
    if values.get("status") != "FROZEN_PRE_FIELD_MATCHUP":
        raise ObservationSelectionError("Selection status must remain frozen.")

    scope = values["scope"]
    selection = values["selection"]
    qa = values["qa_freeze"]
    indices = values["indices"]
    if tuple(scope.get("methods", ())) != EXPECTED_METHODS:
        raise ObservationSelectionError(
            f"Methods must remain exactly {list(EXPECTED_METHODS)}."
        )
    if int(scope.get("primary_window_size", 0)) != 3:
        raise ObservationSelectionError("Primary window must remain 3x3.")
    if int(scope.get("grid_resolution_m", 0)) != 20:
        raise ObservationSelectionError("Primary grid must remain 20 m.")
    if selection.get("rule_id") != EXPECTED_RULE_ID:
        raise ObservationSelectionError("Unexpected frozen selection rule ID.")
    if int(selection.get("window_pixel_count", 0)) != 9:
        raise ObservationSelectionError("Frozen window must contain nine pixels.")
    if int(selection.get("minimum_valid_pixels", 0)) != 6:
        raise ObservationSelectionError("Frozen threshold must remain at least 6/9.")
    if selection.get("apply_same_threshold_to_all_methods") is not True:
        raise ObservationSelectionError("The same 6/9 threshold must apply to all methods.")
    if selection.get("metric_specific_count_columns") != {
        "NDCI": "NDCI_valid_pixel_count",
        "MCI": "MCI_valid_pixel_count",
        "common_B456": "common_B456_valid_count",
    }:
        raise ObservationSelectionError("Metric-specific count columns changed.")
    if qa.get("required_validity_contributing_families_missing_or_unreadable") != "unavailable":
        raise ObservationSelectionError("Missing required QA must remain unavailable.")
    if qa.get("existing_diagnostic_flags") != "diagnostic_only_not_hard_reject":
        raise ObservationSelectionError("Diagnostic flags must remain non-exclusionary.")
    if indices.get("mci_wavelength_source") != "nominal_fixed" or indices.get(
        "nominal_central_wavelength_nm"
    ) != {"B4": 665.0, "B5": 705.0, "B6": 740.0}:
        raise ObservationSelectionError("MCI wavelengths must remain nominal 665/705/740 nm.")

    relative = source.name
    if repository_root is not None:
        try:
            relative = source.resolve().relative_to(Path(repository_root).resolve()).as_posix()
        except ValueError:
            pass
    return ObservationSelectionConfig(values, relative, sha256_file(source))


def _read_governed_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ObservationSelectionError(f"Required governed input not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = set(reader.fieldnames or ())
        prohibited = sorted(header & PROHIBITED_INPUT_COLUMNS)
        if prohibited:
            raise ObservationSelectionError(
                f"Governed input {path} contains prohibited field(s): {prohibited}."
            )
        return list(reader)


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _finite_int(value: Any) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def classify_metric(
    *, count: Any, source_available: bool, required_qa_complete: bool,
    unavailable_reason: str, minimum_valid_pixels: int = 6,
) -> tuple[bool | None, str]:
    """Classify one metric without conflating missing support and low support."""

    if not source_available:
        return None, f"unavailable_{unavailable_reason or 'source_not_available'}"
    if not required_qa_complete:
        return None, f"unavailable_{unavailable_reason or 'required_qa_incomplete'}"
    valid_count = _finite_int(count)
    if valid_count is None:
        return None, f"unavailable_{unavailable_reason or 'valid_pixel_count_missing'}"
    if valid_count >= minimum_valid_pixels:
        return True, "eligible_at_least_6_of_9_valid_pixels"
    return False, "ineligible_below_6_valid_pixels"


def _validate_unique(rows: Sequence[Mapping[str, Any]], keys: Sequence[str], label: str) -> None:
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = tuple(str(row.get(column, "")) for column in keys)
        if key in seen:
            raise ObservationSelectionError(f"Duplicate {label} key: {key}")
        seen.add(key)


def _source_state(
    method: str,
    pairing: Mapping[str, str],
    phase6a: Mapping[tuple[str, str], Mapping[str, str]],
    acolite: Mapping[str, Mapping[str, str]],
    alignment: Mapping[str, Mapping[str, str]],
) -> tuple[Mapping[str, str] | None, str, str, str, bool, bool, str]:
    """Return source row, id, reflectance, alignment, availability, QA, reason."""

    date = pairing["date"]
    if method in {"L1C", "L2A"}:
        source = phase6a.get((date, method))
        product_id = pairing.get(f"{method.lower()}_product_id", "")
        alignment_status = pairing.get(
            "l1c_pairing_status" if method == "L1C" else "l2a_representative_status", ""
        )
        if source is None:
            reason = alignment_status or "source_not_available"
            return None, product_id, "TOA" if method == "L1C" else "BOA", alignment_status, False, False, reason
        available = bool(source.get("product_id"))
        qa_complete = available and not _bool(source.get("native_qa_incomplete"))
        reason = source.get("failure_reason", "")
        return source, product_id, "TOA" if method == "L1C" else "BOA", alignment_status, available, qa_complete, reason

    alignment_row = alignment.get(date, {})
    product_id = pairing.get("l1c_product_id", "")
    alignment_status = alignment_row.get("acolite_phase6a_alignment_status", "")
    source = acolite.get(product_id) if product_id else None
    if source is None:
        reason = alignment_status or pairing.get("l1c_pairing_status", "") or "source_not_available"
        return None, product_id, "rhos", alignment_status, False, False, reason
    required_fields_present = all(
        source.get(column, "")
        for column in (
            "acolite_run_json_relative_path",
            "acolite_settings_relative_paths",
            "acolite_l2_flags_relative_path",
        )
    )
    qa_complete = (
        required_fields_present
        and source.get("acolite_flag_exponent_validation_status")
        == "all_declared_values_match"
    )
    return (
        source,
        product_id,
        source.get("reflectance_quantity", "rhos"),
        alignment_status,
        True,
        qa_complete,
        source.get("failure_reason", ""),
    )


def build_selection_rows(
    *,
    pairing_rows: Sequence[Mapping[str, str]],
    phase6a_rows: Sequence[Mapping[str, str]],
    acolite_rows: Sequence[Mapping[str, str]],
    alignment_rows: Sequence[Mapping[str, str]],
    config: ObservationSelectionConfig,
) -> list[dict[str, Any]]:
    """Build the complete 926-date x 3-method frozen audit table."""

    _validate_unique(pairing_rows, ("date",), "pairing date")
    _validate_unique(phase6a_rows, ("date", "product_level"), "Phase 6A observation")
    _validate_unique(acolite_rows, ("source_l1c_product_id",), "ACOLITE product")
    _validate_unique(alignment_rows, ("date",), "ACOLITE alignment date")
    phase6a = {(row["date"], row["product_level"]): row for row in phase6a_rows}
    acolite = {row["source_l1c_product_id"]: row for row in acolite_rows}
    alignment = {row["date"]: row for row in alignment_rows}
    minimum = config.minimum_valid_pixels

    output: list[dict[str, Any]] = []
    for pairing in sorted(pairing_rows, key=lambda row: row["date"]):
        exact_alignment = (
            pairing.get("l2a_representative_status") == "frozen_representative"
            and pairing.get("l1c_pairing_status") == "exact_unique"
            and alignment.get(pairing["date"], {}).get("acolite_phase6a_alignment_status")
            == "eligible_exact_l1c_product_found"
        )
        for method in EXPECTED_METHODS:
            source, product_id, reflectance, alignment_status, available, qa_complete, reason = _source_state(
                method, pairing, phase6a, acolite, alignment
            )
            source = source or {}
            entry: dict[str, Any] = {
                "selection_version": config.selection_version,
                "selection_rule_id": config.rule_id,
                "date": pairing["date"],
                "year": int(pairing["year"]),
                "observation_method": method,
                "product_level": method if method != "ACOLITE" else "L2R",
                "reflectance_quantity": reflectance,
                "source_product_id": product_id,
                "paired_l2a_product_id": pairing.get("l2a_product_id", ""),
                "source_alignment_status": alignment_status,
                "frozen_scl_gate_pass": _bool(pairing.get("scl_gate_pass")),
                "l2a_representative_status": pairing.get("l2a_representative_status", ""),
                "l1c_pairing_status": pairing.get("l1c_pairing_status", ""),
                "exact_three_method_source_alignment": exact_alignment,
                "method_product_available": available,
                "required_qa_complete": qa_complete,
                "source_failure_reason": reason,
                "minimum_valid_pixels": minimum,
                "window_pixel_count": 9,
                "diagnostic_flags_exclusionary": False,
                "mci_wavelength_source": "nominal_fixed_665_705_740_nm",
                "chlf_used": False,
            }
            for metric, (count_column, value_column) in METRIC_COLUMNS.items():
                count = _finite_int(source.get(count_column))
                value = _finite_float(source.get(value_column)) if value_column else None
                eligible, status = classify_metric(
                    count=count,
                    source_available=available,
                    required_qa_complete=qa_complete,
                    unavailable_reason=reason,
                    minimum_valid_pixels=minimum,
                )
                entry[count_column] = count
                if value_column:
                    entry[value_column] = value
                entry[f"{metric}_observation_eligible"] = eligible
                entry[f"{metric}_selection_status"] = status
            output.append(entry)

    expected = len(pairing_rows) * len(EXPECTED_METHODS)
    if len(output) != expected:
        raise ObservationSelectionError(
            f"Expected {expected} unified rows but built {len(output)}."
        )
    return output


def run_observation_selection(
    *, config: ObservationSelectionConfig, repository_root: str | Path
) -> ObservationSelectionResult:
    root = Path(repository_root)
    input_paths = {
        name: root / str(relative)
        for name, relative in config.values["inputs"].items()
    }
    tables = {name: _read_governed_csv(path) for name, path in input_paths.items()}
    rows = build_selection_rows(
        pairing_rows=tables["phase6a_pairing_audit"],
        phase6a_rows=tables["phase6a_date_observation_master"],
        acolite_rows=tables["acolite_extraction_master"],
        alignment_rows=tables["acolite_alignment_audit"],
        config=config,
    )
    methods: dict[str, Any] = {}
    for method in EXPECTED_METHODS:
        subset = [row for row in rows if row["observation_method"] == method]
        methods[method] = {
            "rows": len(subset),
            "product_available": sum(row["method_product_available"] is True for row in subset),
            "required_qa_complete": sum(row["required_qa_complete"] is True for row in subset),
            "ndci_eligible": sum(row["ndci_observation_eligible"] is True for row in subset),
            "mci_eligible": sum(row["mci_observation_eligible"] is True for row in subset),
            "common_b456_eligible": sum(row["common_b456_observation_eligible"] is True for row in subset),
        }
    counts = {
        "candidate_dates": len(tables["phase6a_pairing_audit"]),
        "methods": len(EXPECTED_METHODS),
        "rows": len(rows),
        "exact_three_method_source_alignment_dates": len(
            {row["date"] for row in rows if row["exact_three_method_source_alignment"]}
        ),
        "by_method": methods,
    }
    return ObservationSelectionResult(tuple(rows), input_paths, counts)


def _git_state(repository_root: Path) -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repository_root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"], cwd=repository_root, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
        )
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def write_selection_outputs(
    result: ObservationSelectionResult,
    *, config: ObservationSelectionConfig,
    repository_root: str | Path,
) -> dict[str, Path]:
    """Write the unified table and deterministic provenance manifest."""

    root = Path(repository_root)
    table_path = root / str(config.values["outputs"]["selection_table"])
    manifest_path = root / str(config.values["outputs"]["manifest"])
    output_root = (root / str(config.values["outputs"]["root"])).resolve()
    for destination in (table_path, manifest_path):
        try:
            destination.resolve().relative_to(output_root)
        except ValueError as error:
            raise ObservationSelectionError(
                f"Output escapes frozen namespace: {destination}"
            ) from error

    commit, dirty = _git_state(root)
    write_rows(result.rows, table_path)
    manifest = {
        "schema_version": "erken_s2_observation_selection_manifest_v1",
        "selection_version": config.selection_version,
        "selection_rule_id": config.rule_id,
        "decision_id": config.values["decision_id"],
        "status": "FROZEN_PRE_FIELD_MATCHUP",
        "configuration": {
            "relative_path": config.source_relative_path,
            "sha256": config.sha256,
        },
        "repository": {
            "commit_at_generation_start": commit,
            "worktree_dirty_at_generation_start": dirty,
        },
        "inputs": {
            name: {
                "relative_path": path.resolve().relative_to(root.resolve()).as_posix(),
                "sha256": sha256_file(path),
            }
            for name, path in sorted(result.input_paths.items())
        },
        "output": {
            "selection_table": table_path.resolve().relative_to(root.resolve()).as_posix(),
            "selection_table_sha256": sha256_file(table_path),
        },
        "counts": result.counts,
        "scientific_guards": {
            "chlf_read": False,
            "presence_ice_read": False,
            "field_matchup_generated": False,
            "processor_ranking_generated": False,
            "timesat_run": False,
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"selection_table": table_path, "manifest": manifest_path}
