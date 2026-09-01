"""Frozen Phase 3 reconstruction-contract loading and validation.

This module treats the versioned JSON configuration and its two governing
Markdown documents as immutable inputs.  It contains no reconstruction or
performance logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "Reconstruction_Analysis_Contract_v1.0.1"
MASTER_VERSION = "Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1"
PRIMARY_YEARS = (2019, 2020, 2021, 2022, 2023, 2024, 2025)
PRIMARY_METHODS = (
    "linear_interpolation",
    "timesat_double_logistic",
    "timesat_smoothing_spline",
)
SPLINE_GRID = (0, 1, 3, 10, 30, 100, 300, 1000)
RANDOM_DELETION_FRACTIONS = (0.1, 0.2, 0.3, 0.5)
RANDOM_REPLICATES = 100
MASTER_SEED = 20260901
CONSECUTIVE_GAP_DAYS = (10, 20, 30, 45)
EXPECTED_SPARSE_DATES = 288


class ContractError(ValueError):
    """Raised when a frozen contract artifact is missing or has changed."""


@dataclass(frozen=True)
class OuterFold:
    """One immutable outer year-level evaluation fold."""

    fold_id: str
    outer_test_year: int
    inner_training_years: tuple[int, ...]


def sha256_file(path: str | Path) -> str:
    """Return a streaming SHA256 checksum for *path*."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_payload_sha256(
    value: Mapping[str, Any], *, excluded_keys: Sequence[str] = ()
) -> str:
    """Checksum a mapping using deterministic compact JSON serialization."""

    payload = {key: item for key, item in value.items() if key not in excluded_keys}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError(f"Missing {label}: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{label} must contain one JSON object: {path}")
    return value


def build_outer_folds(years: Sequence[int] = PRIMARY_YEARS) -> tuple[OuterFold, ...]:
    """Build the seven deterministic LOYO folds without accessing reference data."""

    normalized = tuple(int(year) for year in years)
    if normalized != PRIMARY_YEARS:
        raise ContractError(
            f"Phase 3 outer years must be exactly {PRIMARY_YEARS}; found {normalized}."
        )
    return tuple(
        OuterFold(
            fold_id=f"outer_{test_year}",
            outer_test_year=test_year,
            inner_training_years=tuple(
                year for year in normalized if year != test_year
            ),
        )
        for test_year in normalized
    )


def validate_contract_config(
    config: Mapping[str, Any], *, repository_root: str | Path
) -> None:
    """Fail if any machine-readable frozen rule or governing file has changed."""

    root = Path(repository_root)
    checks = {
        "contract_version": CONTRACT_VERSION,
        "scientific_master_version": MASTER_VERSION,
        "years": list(PRIMARY_YEARS),
        "expected_actual_mask_sparse_dates": EXPECTED_SPARSE_DATES,
        "methods": list(PRIMARY_METHODS),
    }
    for key, expected in checks.items():
        if config.get(key) != expected:
            raise ContractError(
                f"Frozen contract field {key!r} must equal {expected!r}; "
                f"found {config.get(key)!r}."
            )

    spline = config.get("spline")
    if not isinstance(spline, Mapping) or spline.get("candidate_grid") != list(
        SPLINE_GRID
    ):
        raise ContractError(f"Spline grid must be exactly {SPLINE_GRID}.")
    controlled = config.get("controlled_gaps")
    if not isinstance(controlled, Mapping):
        raise ContractError("Missing controlled_gaps contract section.")
    expected_controlled = {
        "random_deletion_fractions": list(RANDOM_DELETION_FRACTIONS),
        "random_replicates": RANDOM_REPLICATES,
        "master_seed": MASTER_SEED,
        "consecutive_window_days": list(CONSECUTIVE_GAP_DAYS),
    }
    for key, expected in expected_controlled.items():
        if controlled.get(key) != expected:
            raise ContractError(
                f"Frozen controlled-gap field {key!r} must equal {expected!r}; "
                f"found {controlled.get(key)!r}."
            )

    documents = config.get("governing_documents")
    if not isinstance(documents, list) or len(documents) != 2:
        raise ContractError("Exactly two governing documents must be configured.")
    for document in documents:
        if not isinstance(document, Mapping):
            raise ContractError("Each governing document entry must be an object.")
        relative = document.get("path")
        expected_hash = document.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise ContractError("Governing documents require path and sha256 fields.")
        path = root / relative
        if not path.is_file():
            raise ContractError(f"Missing authoritative governing document: {relative}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise ContractError(
                f"Authoritative document checksum mismatch for {relative}: "
                f"expected {expected_hash}, found {actual_hash}."
            )

    build_outer_folds(config["years"])


def load_contract_config(
    repository_root: str | Path,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Load and strictly validate the machine-readable Phase 3 contract."""

    root = Path(repository_root)
    contract_path = (
        Path(path)
        if path is not None
        else root / "config" / "reconstruction_analysis_contract_v1.0.1.json"
    )
    config = _read_json(contract_path, label="Phase 3 contract configuration")
    validate_contract_config(config, repository_root=root)
    return config


def validate_timesat_defaults_snapshot(snapshot: Mapping[str, Any]) -> None:
    """Validate the immutable snapshot's identity and self-checksum."""

    if snapshot.get("snapshot_schema_version") != (
        "timesat_double_logistic_defaults_snapshot_v1"
    ):
        raise ContractError("Unexpected TIMESAT defaults snapshot schema version.")
    if snapshot.get("frozen_before_performance") is not True:
        raise ContractError("TIMESAT defaults snapshot is not marked pre-performance.")
    expected = snapshot.get("snapshot_payload_sha256")
    actual = canonical_json_payload_sha256(
        snapshot, excluded_keys=("snapshot_payload_sha256",)
    )
    if expected != actual:
        raise ContractError(
            "TIMESAT defaults snapshot checksum mismatch: "
            f"expected {expected}, found {actual}."
        )
    core = snapshot.get("timesat_core", {})
    cli = snapshot.get("timesat_cli", {})
    if core.get("version") != "4.4.1" or core.get("source_tag") != "v4.4.1":
        raise ContractError("Frozen TIMESAT core must be version/tag 4.4.1/v4.4.1.")
    if cli.get("version") != "1.9.2" or cli.get("source_tag") != "v1.9.2":
        raise ContractError("Frozen TIMESAT CLI must be version/tag 1.9.2/v1.9.2.")
    effective = snapshot.get("effective_runtime_parameters", {})
    if effective.get("p_fitmethod") != 1:
        raise ContractError("Frozen double-logistic p_fitmethod must equal 1.")


def load_timesat_defaults_snapshot(path: str | Path) -> dict[str, Any]:
    """Load and verify the immutable double-logistic defaults snapshot."""

    snapshot = _read_json(Path(path), label="TIMESAT defaults snapshot")
    validate_timesat_defaults_snapshot(snapshot)
    return snapshot
