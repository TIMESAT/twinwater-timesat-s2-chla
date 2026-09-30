"""Evidence-driven closure of the frozen Vombsjon pre-performance execution gates.

The governing freeze lists seven gates that must be closed *before* any Vombsjon
reconstruction performance is evaluated. This module evaluates those gates from
committed evidence and from optional observed source evidence, and materializes
a gate report, a Vombsjon-specific TIMESAT runtime record and a manifest.

Three terminal states, and only three:

``PASS``
    Available evidence affirmatively establishes the frozen requirement.
``FAIL``
    Available evidence affirmatively contradicts the frozen requirement.
``BLOCKED``
    The required evidence is absent, incomplete, or not machine-verifiable.

**Absent evidence is BLOCKED, never PASS.** A BLOCKED gate is not a failed
scientific result; it says the evidence does not reach the bar.

Closure succeeds only when all seven gates PASS. Closure then sets
``performance_execution_eligible``. It never sets
``performance_execution_authorized``: the historical freeze retains
``vombsjon_performance_execution_authorized = false`` and this module does not
rewrite governance retrospectively.

This module evaluates the guard; it never inspects the thing the guard
protects. It reads no reconstruction output, computes no reconstruction or
matchup metric, fits no regression or correlation, ranks no processor, and
tunes nothing. The gate list itself is read from the freeze rather than
restated here, so a gate cannot be silently dropped or renamed.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform as platform_module
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


GATE_CLOSURE_VERSION = "vombsjon_execution_gate_closure_v1.0"
MANIFEST_SCHEMA_VERSION = "vombsjon_execution_gate_closure_manifest_v1"
STATUS_SCHEMA_VERSION = "vombsjon_execution_gate_status_v1"
RUNTIME_SCHEMA_VERSION = "vombsjon_gate_timesat_runtime_validation_v1"
EXTERNAL_EVIDENCE_SCHEMA_VERSION = "vombsjon_external_input_evidence_v1"

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
TERMINAL_STATES: tuple[str, ...] = (PASS, FAIL, BLOCKED)

DEFAULT_FREEZE_PATH = "config/erken_vomb_transfer_freeze_v1.1.json"
DEFAULT_SATELLITE_AUDIT_DIR = "results/vombsjon/satellite_input_audit/v1.2"
DEFAULT_FIELD_AUDIT_DIR = "results/vombsjon/field_input_audit/v1.0"
DEFAULT_TIMESAT_SNAPSHOT = "config/timesat_double_logistic_defaults_v4.4.1.json"
DEFAULT_OUTPUT_ROOT = "results/vombsjon/execution_gate_closure/v1.0"

SATELLITE_MANIFEST_NAME = "vombsjon_satellite_input_audit_manifest.json"
FIELD_MANIFEST_NAME = "vombsjon_field_input_audit_manifest.json"
FIELD_SOURCE_MANIFEST_NAME = "vombsjon_field_source_manifest.csv"

# Namespaces this module must never write into. The transfer-freeze namespace
# and both satellite-audit namespaces are committed, immutable evidence that
# gate closure reads.
PROTECTED_OUTPUT_PREFIXES: tuple[str, ...] = (
    "results/transfer_freeze",
    "results/vombsjon/satellite_input_audit",
    "results/vombsjon/field_input_audit",
    "results/phase3",
    "results/phase4",
    "results/phase5",
    "results/phase6a",
    "results/phase6b",
    "results/phase6c",
    "results/phase6d",
    "results/reliability_synthesis",
    "results/tables",
    "results/figures",
    "config",
    "data",
    "docs",
    "manuscript",
    "references",
    "src",
    "scripts",
    "tests",
)

STATUS_FIELDNAMES: tuple[str, ...] = (
    "gate_index",
    "gate_id",
    "status",
    "evidence_summary",
    "evidence_paths",
    "blocking_reason",
    "mismatch_reason",
)


class ExecutionGateError(RuntimeError):
    """Raised when gate closure cannot proceed without an assumption."""


class ExecutionGateScopeError(RuntimeError):
    """Raised when an action would leave the governed output namespace."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def sha256_file(path: str | Path) -> str:
    """Return the streaming SHA256 of one file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_payload_sha256(
    value: Mapping[str, Any], *, excluded_keys: Sequence[str] = ()
) -> str:
    """Checksum a mapping with deterministic compact JSON, as elsewhere in the repo."""

    payload = {key: item for key, item in value.items() if key not in excluded_keys}
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _dotted(values: Mapping[str, Any], key: str, default: Any = None) -> Any:
    current: Any = values
    for part in key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return default
        current = current[part]
    return current


def _close(observed: Any, expected: float, *, tolerance: float) -> bool:
    try:
        value = float(observed)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value) and abs(value - float(expected)) <= tolerance


def capture_repository_state(repository_root: str | Path) -> dict[str, Any]:
    """Record commit and worktree cleanliness **before** any output is written.

    The earlier satellite audit queried ``git status`` after writing its own
    outputs, so the new untracked files made the worktree look dirty in its own
    manifest. Gate closure captures the state first and says so explicitly.
    """

    root = Path(repository_root)

    def _git(*arguments: str) -> str | None:
        try:
            completed = subprocess.run(
                ["git", *arguments],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout

    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    return {
        "captured_before_writing_outputs": True,
        "repository_commit_at_start": commit.strip() if commit else None,
        "repository_worktree_dirty_at_start": (
            bool(status.strip()) if status is not None else None
        ),
        "repository_state_observable": commit is not None and status is not None,
    }


def observe_git_root(root: str | Path) -> dict[str, Any]:
    """Observe an external Git checkout read-only. Never modifies it."""

    path = Path(root)
    record: dict[str, Any] = {
        "root_supplied": True,
        "root_exists": path.is_dir(),
        "head_commit": None,
        "worktree_dirty": None,
        "porcelain_entry_count": None,
        "observation_error": None,
    }
    if not path.is_dir():
        record["observation_error"] = "supplied root is not a directory"
        return record
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        record["observation_error"] = f"git could not be executed: {error}"
        return record
    if head.returncode != 0 or status.returncode != 0:
        record["observation_error"] = "git rev-parse/status failed in the supplied root"
        return record
    entries = [line for line in status.stdout.splitlines() if line.strip()]
    record["head_commit"] = head.stdout.strip() or None
    record["worktree_dirty"] = bool(entries)
    record["porcelain_entry_count"] = len(entries)
    return record


# ---------------------------------------------------------------------------
# Gate records and context
# ---------------------------------------------------------------------------


@dataclass
class GateRecord:
    """One evaluated gate. ``status`` is always one of the three terminal states."""

    gate_id: str
    status: str
    evidence_summary: str = ""
    evidence_paths: tuple[str, ...] = ()
    blocking_reason: str | None = None
    mismatch_reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in TERMINAL_STATES:
            raise ExecutionGateError(
                f"Gate {self.gate_id!r} produced non-terminal status "
                f"{self.status!r}; expected one of {list(TERMINAL_STATES)}."
            )
        if self.status == BLOCKED and not self.blocking_reason:
            raise ExecutionGateError(
                f"Gate {self.gate_id!r} is BLOCKED without a blocking_reason."
            )
        if self.status == FAIL and not self.mismatch_reason:
            raise ExecutionGateError(
                f"Gate {self.gate_id!r} is FAIL without a mismatch_reason."
            )

    def as_row(self, index: int) -> dict[str, Any]:
        return {
            "gate_index": index,
            "gate_id": self.gate_id,
            "status": self.status,
            "evidence_summary": self.evidence_summary,
            "evidence_paths": ";".join(self.evidence_paths) or None,
            "blocking_reason": self.blocking_reason,
            "mismatch_reason": self.mismatch_reason,
        }

    def as_record(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "status": self.status,
            "evidence_summary": self.evidence_summary,
            "evidence_paths": list(self.evidence_paths),
            "blocking_reason": self.blocking_reason,
            "mismatch_reason": self.mismatch_reason,
            "details": self.details,
        }


@dataclass
class GateContext:
    """Everything the gate evaluators may read. Nothing here is mutated."""

    repository_root: Path
    freeze: Mapping[str, Any]
    freeze_relative_path: str
    freeze_sha256: str
    satellite_audit_dir: Path
    satellite_manifest: Mapping[str, Any] | None
    field_audit_dir: Path
    field_manifest: Mapping[str, Any] | None
    timesat_snapshot_path: Path
    external_input_evidence: Mapping[str, Any] | None = None
    external_input_evidence_path: str | None = None
    acolite_source_observation: Mapping[str, Any] | None = None
    wrapper_observation: Mapping[str, Any] | None = None
    timesat_runtime: Mapping[str, Any] | None = None

    def relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.repository_root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    def satellite_file(self, name: str) -> Path:
        return self.satellite_audit_dir / name


def required_gate_ids(freeze: Mapping[str, Any]) -> tuple[str, ...]:
    """Read the required gate identities and order from the freeze itself."""

    gates = _dotted(freeze, "execution_gates.before_vomb_performance")
    if not isinstance(gates, Sequence) or isinstance(gates, (str, bytes)) or not gates:
        raise ExecutionGateError(
            "The governing freeze declares no "
            "execution_gates.before_vomb_performance list."
        )
    identities = tuple(str(item) for item in gates)
    if len(set(identities)) != len(identities):
        raise ExecutionGateError(
            f"The freeze declares duplicate gate identities: {identities}."
        )
    return identities


# ---------------------------------------------------------------------------
# Gate 1 - external input identity, licence and content checksum
# ---------------------------------------------------------------------------


def _gate_external_input_identity(context: GateContext) -> GateRecord:
    gate_id = "verify_external_input_identity_licence_and_sha256"
    paths: list[str] = []
    blocking: list[str] = []
    mismatches: list[str] = []
    details: dict[str, Any] = {
        "path_set_fingerprint_accepted_as_content_checksum": False,
        "path_set_fingerprint_note": (
            "The satellite audit's inventory fingerprints are SHA256 over sorted "
            "'<id>\\t<root-relative path>' lines and are explicitly flagged "
            "is_raster_content_checksum=false. They identify which products were "
            "found, not their bytes, and are never accepted here as a content "
            "checksum."
        ),
    }

    # --- committed field-source evidence -------------------------------------
    source_manifest = context.field_audit_dir / FIELD_SOURCE_MANIFEST_NAME
    if not source_manifest.is_file():
        blocking.append(
            f"committed field source manifest not found: "
            f"{context.relative(source_manifest)}"
        )
        details["field_sources"] = None
    else:
        paths.append(context.relative(source_manifest))
        rows = _read_csv(source_manifest)
        field_records: list[dict[str, Any]] = []
        for row in rows:
            repo_path = str(row.get("repository_path", "")).strip()
            declared = str(row.get("sha256", "")).strip()
            licence = str(row.get("licence_status", "")).strip()
            target = context.repository_root / repo_path
            observed = sha256_file(target) if target.is_file() else None
            checksum_ok = bool(declared) and observed == declared
            # A licence is only established when the manifest states one; the
            # existing wording records, for three of four sources, that no
            # licence was found or that it was not independently verified.
            licence_established = _licence_is_established(licence)
            field_records.append(
                {
                    "repository_path": repo_path,
                    "present": target.is_file(),
                    "declared_sha256": declared or None,
                    "observed_sha256": observed,
                    "content_checksum_verified": checksum_ok,
                    "licence_status_text": licence or None,
                    "licence_established": licence_established,
                }
            )
            if not target.is_file():
                mismatches.append(f"declared field source missing: {repo_path}")
            elif not checksum_ok:
                mismatches.append(
                    f"field source content SHA256 mismatch: {repo_path}"
                )
            if not licence_established:
                blocking.append(
                    f"licence not established for {repo_path}: "
                    f"{licence or 'no licence_status recorded'}"
                )
        details["field_sources"] = field_records

    # --- external satellite archives -----------------------------------------
    satellite = context.satellite_manifest
    fingerprints = _dotted(satellite or {}, "inventory_fingerprints", {}) or {}
    archive_records: list[dict[str, Any]] = []
    for archive in ("l1c", "l2a", "acolite"):
        entry = fingerprints.get(archive) if isinstance(fingerprints, Mapping) else None
        is_content = bool(
            isinstance(entry, Mapping) and entry.get("is_raster_content_checksum")
        )
        archive_records.append(
            {
                "archive": archive,
                "path_set_fingerprint_present": isinstance(entry, Mapping),
                "path_set_fingerprint_sha256": (
                    entry.get("sha256") if isinstance(entry, Mapping) else None
                ),
                "declares_raster_content_checksum": is_content,
                "content_checksum_accepted": False,
            }
        )
        blocking.append(
            f"no raster/content SHA256 evidence for the external {archive.upper()} "
            "archive; the committed inventory fingerprint covers identifiers and "
            "paths only"
        )
    details["external_satellite_archives"] = archive_records

    # --- optional supplied external-input evidence ---------------------------
    supplied = context.external_input_evidence
    if supplied is not None:
        if context.external_input_evidence_path:
            paths.append(context.external_input_evidence_path)
        accepted, supplied_block, supplied_mismatch, supplied_detail = (
            _evaluate_external_input_evidence(supplied)
        )
        details["supplied_external_input_evidence"] = supplied_detail
        mismatches.extend(supplied_mismatch)
        if accepted:
            # Only a complete, self-declared-verified evidence file can clear the
            # archive-side blocks; it never clears a contradicted checksum.
            blocking = [
                item
                for item in blocking
                if not item.startswith("no raster/content SHA256 evidence")
            ]
            covered = {str(item) for item in supplied_detail.get("covered_inputs", [])}
            blocking = [
                item
                for item in blocking
                if not any(
                    item.startswith(f"licence not established for {name}")
                    for name in covered
                )
            ]
        blocking.extend(supplied_block)
    else:
        details["supplied_external_input_evidence"] = None
        blocking.append(
            "no external-input evidence file was supplied "
            "(--external-input-evidence)"
        )

    summary = (
        f"{len(details.get('field_sources') or [])} committed field source(s) "
        f"checksum-verified against the repository; external archive content "
        f"checksums and full licence identity not established from committed "
        f"evidence."
    )
    if mismatches:
        return GateRecord(
            gate_id=gate_id,
            status=FAIL,
            evidence_summary=summary,
            evidence_paths=tuple(paths),
            mismatch_reason="; ".join(sorted(set(mismatches))),
            details=details,
        )
    if blocking:
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary=summary,
            evidence_paths=tuple(paths),
            blocking_reason="; ".join(sorted(set(blocking))),
            details=details,
        )
    return GateRecord(
        gate_id=gate_id,
        status=PASS,
        evidence_summary=(
            "Identity, licence and content checksum are established for every "
            "declared external input."
        ),
        evidence_paths=tuple(paths),
        details=details,
    )


def _licence_is_established(text: str) -> bool:
    """Say whether a licence_status string actually establishes a licence.

    Deliberately conservative: a sentence recording that no licence was found,
    or that a licence was not independently verified, does not establish one.
    """

    lowered = text.strip().lower()
    if not lowered:
        return False
    negative_markers = (
        "not stated",
        "no licence",
        "not independently verified",
        "does not state",
        "unknown",
        "unverified",
    )
    if any(marker in lowered for marker in negative_markers):
        return False
    positive_markers = ("cc by", "cc0", "public domain", "licence:", "license:")
    return any(marker in lowered for marker in positive_markers)


def _evaluate_external_input_evidence(
    evidence: Mapping[str, Any],
) -> tuple[bool, list[str], list[str], dict[str, Any]]:
    """Validate an optional supplied external-input evidence document.

    The interface is deliberately minimal and refuses to be satisfied by a
    path-set fingerprint: ``content_checksum_scope`` must name real content.
    """

    blocking: list[str] = []
    mismatches: list[str] = []
    detail: dict[str, Any] = {
        "schema_version": evidence.get("schema_version"),
        "inputs": [],
        "covered_inputs": [],
    }
    if str(evidence.get("schema_version")) != EXTERNAL_EVIDENCE_SCHEMA_VERSION:
        blocking.append(
            f"external-input evidence schema_version must be "
            f"{EXTERNAL_EVIDENCE_SCHEMA_VERSION!r}"
        )
        return False, blocking, mismatches, detail

    inputs = evidence.get("inputs")
    if not isinstance(inputs, Sequence) or not inputs:
        blocking.append("external-input evidence declares no inputs")
        return False, blocking, mismatches, detail

    accepted_scopes = {"file_content", "archive_member_content", "content_manifest"}
    complete = True
    for entry in inputs:
        if not isinstance(entry, Mapping):
            mismatches.append("external-input evidence contains a non-object input")
            complete = False
            continue
        input_id = str(entry.get("input_id", "")).strip()
        scope = str(entry.get("content_checksum_scope", "")).strip()
        record = {
            "input_id": input_id or None,
            "identity": entry.get("identity"),
            "licence": entry.get("licence"),
            "licence_verified": bool(entry.get("licence_verified")),
            "content_sha256": entry.get("content_sha256"),
            "content_checksum_scope": scope or None,
            "verified_by": entry.get("verified_by"),
            "verification_date": entry.get("verification_date"),
        }
        detail["inputs"].append(record)
        problems: list[str] = []
        if not input_id:
            problems.append("missing input_id")
        if not str(entry.get("identity", "")).strip():
            problems.append("missing identity")
        if not str(entry.get("licence", "")).strip() or not record["licence_verified"]:
            problems.append("licence not present and verified")
        if not str(entry.get("content_sha256", "")).strip():
            problems.append("missing content_sha256")
        if scope not in accepted_scopes:
            problems.append(
                "content_checksum_scope must name real content "
                f"({sorted(accepted_scopes)}); a path-set fingerprint is not a "
                "content checksum"
            )
        if problems:
            complete = False
            blocking.append(
                f"external-input evidence incomplete for "
                f"{input_id or '<unnamed>'}: {', '.join(problems)}"
            )
        else:
            detail["covered_inputs"].append(input_id)
    detail["complete"] = complete
    return complete, blocking, mismatches, detail


# ---------------------------------------------------------------------------
# Gate 2 - raw Sentinel-2 and ACOLITE product provenance
# ---------------------------------------------------------------------------

EXPECTED_AUDIT_VERSION = "vombsjon_satellite_input_audit_v1.2"
EXPECTED_AUDIT_COUNTS: dict[str, int] = {
    "l1c_products": 1509,
    "l2a_products": 1510,
    "acolite_scenes": 1505,
    "exact_unique_l1c_l2a_pairs": 1466,
    "failure_rows": 48,
}
REQUIRED_AUDIT_FILES: tuple[str, ...] = (
    SATELLITE_MANIFEST_NAME,
    "vombsjon_l1c_inventory.csv",
    "vombsjon_l2a_inventory.csv",
    "vombsjon_acolite_inventory.csv",
    "vombsjon_l1c_l2a_pairing_audit.csv",
    "vombsjon_extraction_failures.csv",
)


def _gate_product_provenance(context: GateContext) -> GateRecord:
    gate_id = "audit_raw_sentinel2_and_acolite_product_provenance"
    blocking: list[str] = []
    mismatches: list[str] = []
    paths: list[str] = []
    details: dict[str, Any] = {}

    manifest = context.satellite_manifest
    if manifest is None:
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary="No canonical satellite input audit manifest was found.",
            evidence_paths=(context.relative(context.satellite_audit_dir),),
            blocking_reason=(
                "canonical v1.2 satellite audit manifest missing at "
                f"{context.relative(context.satellite_file(SATELLITE_MANIFEST_NAME))}"
            ),
            details={"manifest_present": False},
        )

    for name in REQUIRED_AUDIT_FILES:
        target = context.satellite_file(name)
        if target.is_file():
            paths.append(context.relative(target))
        else:
            blocking.append(f"required audit product missing: {name}")

    version = str(manifest.get("audit_version", ""))
    details["audit_version"] = version
    if version != EXPECTED_AUDIT_VERSION:
        mismatches.append(
            f"audit_version is {version!r}; the gate requires "
            f"{EXPECTED_AUDIT_VERSION!r}"
        )

    counts = manifest.get("counts") or {}
    observed_counts: dict[str, Any] = {}
    for key, expected in EXPECTED_AUDIT_COUNTS.items():
        observed = counts.get(key) if isinstance(counts, Mapping) else None
        observed_counts[key] = observed
        if observed is None:
            blocking.append(f"manifest records no count for {key}")
        elif int(observed) != expected:
            mismatches.append(f"{key} is {observed}; expected {expected}")
    details["counts"] = observed_counts

    crosscheck = manifest.get("freeze_crosscheck")
    if not isinstance(crosscheck, Sequence) or not crosscheck:
        blocking.append("manifest records no freeze cross-check")
        details["freeze_crosscheck"] = None
    else:
        disagreeing = [
            str(row.get("freeze_key"))
            for row in crosscheck
            if isinstance(row, Mapping) and not row.get("agrees")
        ]
        details["freeze_crosscheck"] = {
            "row_count": len(crosscheck),
            "disagreeing_keys": disagreeing,
        }
        if disagreeing:
            mismatches.append(
                f"{len(disagreeing)} freeze cross-check(s) disagree: {disagreeing}"
            )

    # Content identity of the manifest itself, so the gate is anchored to bytes
    # rather than to a filename.
    manifest_path = context.satellite_file(SATELLITE_MANIFEST_NAME)
    if manifest_path.is_file():
        details["manifest_sha256"] = sha256_file(manifest_path)

    summary = (
        f"v1.2 audit manifest with {observed_counts.get('l1c_products')} L1C, "
        f"{observed_counts.get('l2a_products')} L2A and "
        f"{observed_counts.get('acolite_scenes')} ACOLITE products, "
        f"{observed_counts.get('exact_unique_l1c_l2a_pairs')} exact-unique pairs, "
        f"{observed_counts.get('failure_rows')} recorded failures."
    )
    return _terminal(gate_id, summary, paths, blocking, mismatches, details)


# ---------------------------------------------------------------------------
# Gate 3 - coordinate flags retained without silent correction
# ---------------------------------------------------------------------------

UNRESOLVED_COORDINATE_DATES: tuple[str, ...] = ("2020-06-10", "2020-06-24")


def _gate_coordinate_flags(context: GateContext) -> GateRecord:
    gate_id = "resolve_or_retain_coordinate_flags_without_silent_correction"
    blocking: list[str] = []
    mismatches: list[str] = []
    paths: list[str] = []
    details: dict[str, Any] = {"unresolved_dates": list(UNRESOLVED_COORDINATE_DATES)}

    manifest = context.satellite_manifest
    if manifest is None:
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary="No satellite audit manifest to read coordinate policy from.",
            evidence_paths=(),
            blocking_reason="canonical v1.2 satellite audit manifest missing",
            details=details,
        )

    matchup_path = context.satellite_file("vombsjon_field_satellite_matchup_master.csv")
    sensitivity_path = context.satellite_file("vombsjon_field_gps_3x3_sensitivity.csv")
    for target in (matchup_path, sensitivity_path):
        if target.is_file():
            paths.append(context.relative(target))
        else:
            blocking.append(f"required evidence missing: {target.name}")

    rules = _dotted(manifest, "extraction_and_qc_rules.field_matchup", {}) or {}
    sensitivity_rules = (
        _dotted(manifest, "extraction_and_qc_rules.field_gps_sensitivity", {}) or {}
    )
    details["declared_rules"] = {
        "unresolved_coordinate_correction_allowed": rules.get(
            "unresolved_coordinate_correction_allowed"
        ),
        "retain_unresolved_coordinate_dates": rules.get(
            "retain_unresolved_coordinate_dates"
        ),
        "nominal_point_fallback_in_primary_field_validation": rules.get(
            "nominal_point_fallback_in_primary_field_validation"
        ),
        "extract_for_unresolved_coordinate_dates": sensitivity_rules.get(
            "extract_for_unresolved_coordinate_dates"
        ),
        "nominal_fallback_allowed": sensitivity_rules.get("nominal_fallback_allowed"),
    }
    if rules.get("unresolved_coordinate_correction_allowed") is not False:
        mismatches.append(
            "the audit does not declare unresolved_coordinate_correction_allowed=false"
        )
    if rules.get("retain_unresolved_coordinate_dates") is not True:
        mismatches.append(
            "the audit does not retain unresolved coordinate dates in the "
            "primary polygon comparison"
        )
    if rules.get("nominal_point_fallback_in_primary_field_validation") is not False:
        mismatches.append(
            "a nominal-point fallback is declared for primary field validation"
        )
    if sensitivity_rules.get("extract_for_unresolved_coordinate_dates") is not False:
        mismatches.append(
            "the GPS 3x3 sensitivity is declared to extract unresolved coordinates"
        )
    if sensitivity_rules.get("nominal_fallback_allowed") is not False:
        mismatches.append("the GPS 3x3 sensitivity allows a nominal fallback")

    per_date: dict[str, Any] = {}
    if matchup_path.is_file() and sensitivity_path.is_file():
        matchup = _read_csv(matchup_path)
        sensitivity = _read_csv(sensitivity_path)
        for date in UNRESOLVED_COORDINATE_DATES:
            rows = [row for row in matchup if row.get("field_date") == date]
            gps_rows = [row for row in sensitivity if row.get("field_date") == date]
            statuses = {row.get("coordinate_status") for row in rows}
            contributed = {row.get("coordinate_contributed_to_polygon") for row in rows}
            corrected = {row.get("coordinate_correction_applied") for row in rows}
            gps_statuses = {row.get("sensitivity_status") for row in gps_rows}
            per_date[date] = {
                "matchup_row_count": len(rows),
                "coordinate_status": sorted(x for x in statuses if x is not None),
                "contributed_to_polygon": sorted(
                    x for x in contributed if x is not None
                ),
                "coordinate_correction_applied": sorted(
                    x for x in corrected if x is not None
                ),
                "gps_sensitivity_status": sorted(
                    x for x in gps_statuses if x is not None
                ),
            }
            if not rows:
                mismatches.append(
                    f"{date} is absent from the field matchup table; an "
                    "unresolved date must be retained, not dropped"
                )
                continue
            if not all(
                str(row.get("coordinate_status")) == "measured_gps_flagged_unresolved"
                for row in rows
            ):
                mismatches.append(
                    f"{date} is no longer recorded as an unresolved coordinate flag"
                )
            if any(
                str(row.get("coordinate_correction_applied")).strip().lower() == "true"
                for row in rows
            ):
                mismatches.append(f"{date} records a silent coordinate correction")
            if any(
                str(row.get("coordinate_contributed_to_polygon")).strip().lower()
                == "true"
                for row in rows
            ):
                mismatches.append(
                    f"{date} contributed a coordinate to polygon construction"
                )
            if any(
                str(row.get("sensitivity_status")) == "extracted" for row in gps_rows
            ):
                mismatches.append(
                    f"{date} received an actual-GPS 3x3 sensitivity extraction"
                )
    details["per_date"] = per_date

    summary = (
        f"{len(UNRESOLVED_COORDINATE_DATES)} flagged date(s) retained as "
        "unresolved, contributing no polygon coordinate and receiving no "
        "actual-GPS 3x3 extraction, with no coordinate correction applied."
    )
    return _terminal(gate_id, summary, paths, blocking, mismatches, details)


# ---------------------------------------------------------------------------
# Gate 4 - QC and same-day deduplication audit
# ---------------------------------------------------------------------------

QC_REQUIRED_FILES: tuple[str, ...] = (
    "vombsjon_product_extraction_master.csv",
    "vombsjon_native_qa_inventory.csv",
    "vombsjon_fixed_station_observation_master.csv",
    "vombsjon_same_day_observation_master.csv",
)


def _gate_qc_same_day(context: GateContext) -> GateRecord:
    gate_id = "materialize_qc_and_same_day_deduplication_audit"
    blocking: list[str] = []
    mismatches: list[str] = []
    paths: list[str] = []
    details: dict[str, Any] = {}

    manifest = context.satellite_manifest
    if manifest is None:
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary="No satellite audit manifest to read QC rules from.",
            evidence_paths=(),
            blocking_reason="canonical v1.2 satellite audit manifest missing",
            details=details,
        )

    for name in QC_REQUIRED_FILES:
        target = context.satellite_file(name)
        if target.is_file():
            paths.append(context.relative(target))
        else:
            blocking.append(f"required QC evidence missing: {name}")

    fixed = _dotted(manifest, "extraction_and_qc_rules.fixed_temporal_target", {}) or {}
    same_day = _dotted(manifest, "extraction_and_qc_rules.same_day", {}) or {}
    radiometry = _dotted(manifest, "extraction_and_qc_rules.radiometry", {}) or {}
    indices = _dotted(manifest, "extraction_and_qc_rules.indices", {}) or {}
    qa_policy = _dotted(
        manifest, "extraction_and_qc_rules.missing_required_qa_family_policy"
    )
    details["rules"] = {
        "window_shape": fixed.get("window_shape"),
        "window_pixel_count": fixed.get("window_pixel_count"),
        "minimum_valid_pixels": fixed.get("minimum_valid_pixels"),
        "invalid_pixel_fill_allowed": fixed.get("invalid_pixel_fill_allowed"),
        "moves_with_field_gps": fixed.get("moves_with_field_gps"),
        "same_day_unit": same_day.get("unit"),
        "same_day_reduction": same_day.get("reduction"),
        "same_day_applies_per_method": same_day.get("applies_per_method"),
        "same_day_pool_methods": same_day.get("pool_methods"),
        "same_day_preserve_product_level_rows_first": same_day.get(
            "preserve_product_level_rows_first"
        ),
        "clamp_negative_reflectance": radiometry.get("clamp_negative_reflectance"),
        "clip_mci": indices.get("clip_mci"),
        "missing_required_qa_family_policy": qa_policy,
    }

    if str(fixed.get("window_shape")) != "3x3":
        mismatches.append(f"fixed temporal target window_shape is {fixed.get('window_shape')!r}")
    if fixed.get("window_pixel_count") != 9:
        mismatches.append(
            f"fixed temporal target window_pixel_count is {fixed.get('window_pixel_count')!r}"
        )
    if fixed.get("minimum_valid_pixels") != 6:
        mismatches.append(
            f"minimum_valid_pixels is {fixed.get('minimum_valid_pixels')!r}; the frozen rule is 6 of 9"
        )
    if fixed.get("invalid_pixel_fill_allowed") is not False:
        mismatches.append("invalid pixel filling is not forbidden")
    if fixed.get("moves_with_field_gps") is not False:
        mismatches.append("the fixed temporal target is declared to move with field GPS")
    if radiometry.get("clamp_negative_reflectance") is not False:
        mismatches.append("negative reflectance clamping is not forbidden")
    if indices.get("clip_mci") is not False:
        mismatches.append("MCI clipping is not forbidden")
    if str(same_day.get("unit")) != "whole_calendar_date":
        mismatches.append(f"same-day unit is {same_day.get('unit')!r}")
    if str(same_day.get("reduction")) != "median_of_eligible_observation_level_medians":
        mismatches.append(f"same-day reduction is {same_day.get('reduction')!r}")
    if same_day.get("applies_per_method") is not True:
        mismatches.append("same-day reduction is not declared per method")
    if same_day.get("pool_methods") is not False:
        mismatches.append("methods are declared as pooled")
    if same_day.get("preserve_product_level_rows_first") is not True:
        mismatches.append("product-level rows are not preserved before reduction")
    if str(qa_policy) != "observation_unavailable":
        mismatches.append(
            f"missing required QA policy is {qa_policy!r}; the frozen rule makes "
            "the observation unavailable"
        )

    same_day_path = context.satellite_file("vombsjon_same_day_observation_master.csv")
    if same_day_path.is_file():
        rows = _read_csv(same_day_path)
        flagged = [
            row
            for row in rows
            if str(row.get("reprocessings_counted_as_independent_observations", ""))
            .strip()
            .lower()
            == "true"
        ]
        pooled = [
            row
            for row in rows
            if str(row.get("methods_pooled", "")).strip().lower() == "true"
        ]
        duplicates = _duplicate_keys(rows, ("method", "date"))
        details["same_day_rows"] = len(rows)
        details["reprocessings_counted_as_independent"] = len(flagged)
        details["methods_pooled_rows"] = len(pooled)
        details["duplicate_method_date_keys"] = duplicates[:10]
        if flagged:
            mismatches.append(
                f"{len(flagged)} same-day row(s) count reprocessings as independent"
            )
        if pooled:
            mismatches.append(f"{len(pooled)} same-day row(s) pool methods")
        if duplicates:
            mismatches.append(
                f"{len(duplicates)} duplicate (method, date) same-day key(s); "
                "the calendar date is the observation unit"
            )

    summary = (
        "Fixed 3x3 target with minimum 6 of 9 valid pixels, no invalid-pixel "
        "filling, no reflectance or MCI clipping, per-method same-day median of "
        "eligible observation-level medians with product rows preserved and "
        "methods never pooled."
    )
    return _terminal(gate_id, summary, paths, blocking, mismatches, details)


def _duplicate_keys(
    rows: Sequence[Mapping[str, Any]], columns: Sequence[str]
) -> list[tuple[str, ...]]:
    seen: set[tuple[str, ...]] = set()
    duplicates: list[tuple[str, ...]] = []
    for row in rows:
        key = tuple(str(row.get(column, "")) for column in columns)
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    return duplicates


# ---------------------------------------------------------------------------
# Gate 5 - ACOLITE source identity and effective settings
# ---------------------------------------------------------------------------

ACOLITE_EXPECTED_SETTINGS: dict[str, str] = {
    "ancillary_data": "True",
    "s2_target_res": "20",
    "l2r_export_geotiff": "True",
    "l2w_export_geotiff": "True",
}


def _gate_acolite_identity(context: GateContext) -> GateRecord:
    gate_id = "verify_acolite_versions_and_effective_settings_match_this_freeze"
    blocking: list[str] = []
    mismatches: list[str] = []
    paths: list[str] = []
    details: dict[str, Any] = {
        "acolite_version_string_is_stable_source_identity": False,
        "acolite_version_string_note": (
            "ACOLITE's 'Generic GitHub Clone c<timestamp>' string is derived from "
            "the local .git/HEAD filesystem mtime of a GitHub clone. It differs "
            "between checkouts of the same commit, so it is environment metadata "
            "and is never treated here as a stable source-code identifier. The "
            "frozen string is not rewritten."
        ),
    }

    manifest = context.satellite_manifest
    if manifest is None:
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary="No satellite audit manifest to read ACOLITE identity from.",
            evidence_paths=(),
            blocking_reason="canonical v1.2 satellite audit manifest missing",
            details=details,
        )
    manifest_path = context.satellite_file(SATELLITE_MANIFEST_NAME)
    if manifest_path.is_file():
        paths.append(context.relative(manifest_path))

    # --- B. effective run settings, observed per scene ------------------------
    identity = _dotted(manifest, "acolite.identity", {}) or {}
    observed_settings = identity.get("observed_settings") or {}
    frozen_declared = identity.get("freeze_declared_identity") or {}
    settings_detail: dict[str, Any] = {}
    for key, expected in ACOLITE_EXPECTED_SETTINGS.items():
        entry = (
            observed_settings.get(key)
            if isinstance(observed_settings, Mapping)
            else None
        )
        values = list(entry.get("distinct_values") or []) if isinstance(entry, Mapping) else []
        scenes = entry.get("declared_scene_count") if isinstance(entry, Mapping) else None
        settings_detail[key] = {
            "declared_scene_count": scenes,
            "distinct_values": values,
            "expected": expected,
        }
        if not isinstance(entry, Mapping) or not scenes:
            blocking.append(f"no scene declares the effective ACOLITE setting {key}")
        elif values != [expected]:
            mismatches.append(
                f"effective ACOLITE {key} is {values}; the freeze requires {expected!r}"
            )
    details["effective_settings"] = settings_detail

    # The frozen requirement that ancillary data is enabled lives in the freeze;
    # read it rather than restating it.
    frozen_ancillary = _dotted(
        context.freeze, "observation_layer.primary_processing_product.ancillary_data"
    )
    details["freeze_requires_ancillary_data"] = frozen_ancillary
    if frozen_ancillary is not True:
        mismatches.append(
            "the governing freeze no longer requires ancillary_data=true"
        )

    # --- C. textual version string: recorded, never used as identity ----------
    version_entry = (
        observed_settings.get("acolite_version")
        if isinstance(observed_settings, Mapping)
        else None
    )
    details["acolite_version_string_status"] = (
        version_entry.get("status") if isinstance(version_entry, Mapping) else None
    )
    details["frozen_acolite_version_string"] = frozen_declared.get(
        "acolite_version_string"
    )

    # --- A. stable source identity, from observed evidence only ---------------
    expected_source = str(frozen_declared.get("acolite_source_commit") or "")
    expected_wrapper = str(frozen_declared.get("s2_inlandwater_ac_commit") or "")
    details["frozen_acolite_source_commit"] = expected_source or None
    details["frozen_wrapper_commit"] = expected_wrapper or None

    source_observation = context.acolite_source_observation
    details["acolite_source_observation"] = source_observation
    if source_observation is None:
        blocking.append(
            "stable ACOLITE source identity was not independently observed; "
            "supply --acolite-source-root. A commit declared by the freeze is "
            "not observed evidence"
        )
    elif source_observation.get("observation_error"):
        blocking.append(
            "ACOLITE source root could not be observed: "
            f"{source_observation['observation_error']}"
        )
    else:
        head = str(source_observation.get("head_commit") or "")
        if not head:
            blocking.append("ACOLITE source root reported no HEAD commit")
        elif expected_source and head != expected_source:
            mismatches.append(
                f"observed ACOLITE source HEAD {head} differs from the frozen "
                f"source commit {expected_source}"
            )
        if source_observation.get("worktree_dirty"):
            blocking.append(
                "the observed ACOLITE source worktree is dirty "
                f"({source_observation.get('porcelain_entry_count')} entries); "
                "local modifications are not assumed harmless"
            )

    wrapper_observation = context.wrapper_observation
    details["wrapper_observation"] = wrapper_observation
    if wrapper_observation is None:
        blocking.append(
            "wrapper source identity was not independently observed; supply "
            "--wrapper-root"
        )
    elif wrapper_observation.get("observation_error"):
        blocking.append(
            "wrapper root could not be observed: "
            f"{wrapper_observation['observation_error']}"
        )
    else:
        head = str(wrapper_observation.get("head_commit") or "")
        if not head:
            blocking.append("wrapper root reported no HEAD commit")
        elif expected_wrapper and head != expected_wrapper:
            mismatches.append(
                f"observed wrapper HEAD {head} differs from the frozen wrapper "
                f"commit {expected_wrapper}"
            )
        if wrapper_observation.get("worktree_dirty"):
            blocking.append(
                "the observed wrapper worktree is dirty "
                f"({wrapper_observation.get('porcelain_entry_count')} entries); "
                "local modifications are not assumed harmless"
            )

    summary = (
        "Effective ACOLITE run settings verified per scene; stable source "
        "identity requires independently observed Git evidence and is never "
        "inferred from the textual version string."
    )
    return _terminal(gate_id, summary, paths, blocking, mismatches, details)


# ---------------------------------------------------------------------------
# Gate 6 - TIMESAT runtime
# ---------------------------------------------------------------------------


def default_timesat_runtime_probe(
    snapshot_path: str | Path, *, transfer_config: Mapping[str, Any]
) -> dict[str, Any]:
    """Probe the active TIMESAT runtime and the frozen affine equivariance.

    Imports are deferred so this module stays importable without TIMESAT. The
    result is a structured record; it never raises for a runtime mismatch,
    because the gate must classify that as FAIL rather than crash.
    """

    result: dict[str, Any] = {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "runtime_available": False,
        "import_error": None,
        "runtime_error": None,
        "runtime": None,
        "registered_build_artifact": None,
        "affine_equivariance_checks": [],
        "all_runtime_checks_passed": False,
        "scientific_performance_evaluated": False,
        "vombsjon_data_or_performance_accessed": False,
    }
    try:
        import numpy as np
        import pandas as pd

        from .timesat_adapter import _run_timesat_core, probe_runtime
        from .phase3_contract import load_timesat_defaults_snapshot
        from .transfer_freeze import fit_training_affine_scale
    except Exception as error:  # noqa: BLE001 - recorded, never absorbed
        result["import_error"] = f"{type(error).__name__}: {error}"
        return result

    result["runtime_available"] = True
    try:
        snapshot = load_timesat_defaults_snapshot(snapshot_path)
        runtime = probe_runtime(snapshot_path, smoke_test=True)
    except Exception as error:  # noqa: BLE001 - recorded, never absorbed
        result["runtime_error"] = f"{type(error).__name__}: {error}"
        return result

    result["runtime"] = runtime
    result["registered_build_artifact"] = bool(runtime.get("registered_build_artifact"))

    # Synthetic series only. No Vombsjon observation is read for this check.
    doys = np.arange(1, 366, 15, dtype=int)
    native = (
        -0.018
        + 0.018 * np.exp(-(((doys - 105) / 42) ** 2))
        + 0.041 * np.exp(-(((doys - 235) / 52) ** 2))
    )
    dates = [
        pd.Timestamp("2019-01-01") + pd.Timedelta(days=int(day - 1)) for day in doys
    ]
    scale_handling = transfer_config.get("scale_handling") or {}
    frozen_minimum = float(scale_handling.get("scaled_training_minimum", 1000.0))
    frozen_maximum = float(scale_handling.get("scaled_training_maximum", 9000.0))
    low_scale = fit_training_affine_scale(
        native, scaled_minimum=100.0, scaled_maximum=900.0
    )
    frozen_scale = fit_training_affine_scale(
        native, scaled_minimum=frozen_minimum, scaled_maximum=frozen_maximum
    )

    tolerance = 1e-8
    checks: list[dict[str, Any]] = []
    for method, smoothing in (
        ("timesat_double_logistic", None),
        ("timesat_smoothing_spline", 10),
    ):
        try:
            low = _run_timesat_core(
                year=2019,
                dates=dates,
                values=low_scale.transform(native).tolist(),
                method=method,
                smoothing=smoothing,
                parameters=snapshot["effective_runtime_parameters"],
            )
            frozen = _run_timesat_core(
                year=2019,
                dates=dates,
                values=frozen_scale.transform(native).tolist(),
                method=method,
                smoothing=smoothing,
                parameters=snapshot["effective_runtime_parameters"],
            )
        except Exception as error:  # noqa: BLE001 - recorded, never absorbed
            checks.append(
                {
                    "method": method,
                    "smoothing": smoothing,
                    "error": f"{type(error).__name__}: {error}",
                    "passed": False,
                }
            )
            continue
        low_native = low_scale.inverse(np.asarray(low["prediction"], dtype=float))
        frozen_native = frozen_scale.inverse(
            np.asarray(frozen["prediction"], dtype=float)
        )
        difference = np.abs(low_native - frozen_native)
        maximum = float(np.nanmax(difference))
        checks.append(
            {
                "method": method,
                "smoothing": smoothing,
                "lower_scale_status": low["status"],
                "frozen_scale_status": frozen["status"],
                "maximum_native_unit_absolute_difference": maximum,
                "absolute_tolerance": tolerance,
                "passed": bool(
                    low["status"] == "ok"
                    and frozen["status"] == "ok"
                    and bool(np.isfinite(difference).all())
                    and maximum <= tolerance
                ),
            }
        )
    result["affine_equivariance_checks"] = checks
    smoke = runtime.get("smoke_test") or {}
    result["all_runtime_checks_passed"] = bool(
        runtime.get("runtime_defaults_match_snapshot")
        and smoke.get("passed")
        and checks
        and all(item.get("passed") for item in checks)
    )
    result["scaled_training_minimum"] = frozen_minimum
    result["scaled_training_maximum"] = frozen_maximum
    return result


def _gate_timesat_runtime(context: GateContext) -> GateRecord:
    gate_id = "verify_timesat_runtime_matches_snapshot"
    paths: list[str] = []
    details: dict[str, Any] = {}

    snapshot_path = context.timesat_snapshot_path
    if snapshot_path.is_file():
        paths.append(context.relative(snapshot_path))
        details["timesat_snapshot_sha256"] = sha256_file(snapshot_path)
    else:
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary="No frozen TIMESAT defaults snapshot was found.",
            evidence_paths=(),
            blocking_reason=(
                f"TIMESAT defaults snapshot missing at {context.relative(snapshot_path)}"
            ),
            details=details,
        )

    runtime = context.timesat_runtime
    if runtime is None:
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary="The TIMESAT runtime was not probed.",
            evidence_paths=tuple(paths),
            blocking_reason="no TIMESAT runtime probe result was supplied",
            details=details,
        )

    details["runtime_available"] = runtime.get("runtime_available")
    details["import_error"] = runtime.get("import_error")
    details["runtime_error"] = runtime.get("runtime_error")
    details["registered_build_artifact"] = runtime.get("registered_build_artifact")
    details["affine_equivariance_checks"] = runtime.get("affine_equivariance_checks")
    probe = runtime.get("runtime") or {}
    details["observed"] = {
        "timesat_core_version": probe.get("timesat_core_version"),
        "timesat_cli_version": probe.get("timesat_cli_version"),
        "timesat_core_binary_filename": probe.get("timesat_core_binary_filename"),
        "timesat_core_binary_sha256": probe.get("timesat_core_binary_sha256"),
        "mismatches": probe.get("mismatches"),
    }
    details["registered_build_artifact_note"] = (
        "The frozen snapshot registers a macOS CPython 3.12 build artifact. A "
        "runtime whose binary is not registered by the snapshot is reported as "
        "BLOCKED, never silently described as the registered frozen binary. The "
        "snapshot is not amended here."
    )

    if not runtime.get("runtime_available"):
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary="TIMESAT is not importable in this interpreter.",
            evidence_paths=tuple(paths),
            blocking_reason=(
                "TIMESAT runtime unavailable: "
                f"{runtime.get('import_error') or 'import failed'}"
            ),
            details=details,
        )

    runtime_error = runtime.get("runtime_error")
    if runtime_error:
        # probe_runtime raises on an explicit mismatch with the frozen snapshot.
        if "differs from the frozen defaults snapshot" in str(runtime_error):
            return GateRecord(
                gate_id=gate_id,
                status=FAIL,
                evidence_summary="The active TIMESAT runtime differs from the frozen snapshot.",
                evidence_paths=tuple(paths),
                mismatch_reason=str(runtime_error),
                details=details,
            )
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary="The TIMESAT runtime could not be probed.",
            evidence_paths=tuple(paths),
            blocking_reason=f"TIMESAT runtime probe failed: {runtime_error}",
            details=details,
        )

    failed_checks = [
        item
        for item in runtime.get("affine_equivariance_checks") or []
        if not item.get("passed")
    ]
    if failed_checks:
        return GateRecord(
            gate_id=gate_id,
            status=FAIL,
            evidence_summary="Affine-equivariance validation failed.",
            evidence_paths=tuple(paths),
            mismatch_reason=(
                "affine equivariance failed for "
                + ", ".join(str(item.get("method")) for item in failed_checks)
            ),
            details=details,
        )

    if not runtime.get("all_runtime_checks_passed"):
        return GateRecord(
            gate_id=gate_id,
            status=FAIL,
            evidence_summary="One or more TIMESAT runtime checks did not pass.",
            evidence_paths=tuple(paths),
            mismatch_reason=(
                "TIMESAT runtime checks did not all pass: "
                f"mismatches={probe.get('mismatches')}, "
                f"smoke_test={probe.get('smoke_test')}"
            ),
            details=details,
        )

    if not runtime.get("registered_build_artifact"):
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary=(
                "Runtime checks pass, but the active build artifact is not one "
                "the frozen snapshot registers."
            ),
            evidence_paths=tuple(paths),
            blocking_reason=(
                "the active TIMESAT build artifact "
                f"{probe.get('timesat_core_binary_filename')!r} is not registered "
                "by the frozen snapshot; run this gate in the registered macOS "
                "CPython 3.12 TIMESAT environment. The snapshot is not amended here"
            ),
            details=details,
        )

    return GateRecord(
        gate_id=gate_id,
        status=PASS,
        evidence_summary=(
            "TIMESAT core/CLI versions, module hashes, source defaults, effective "
            "parameters, synthetic smoke test and affine equivariance all match "
            "the frozen snapshot, on a registered build artifact."
        ),
        evidence_paths=tuple(paths),
        details=details,
    )


# ---------------------------------------------------------------------------
# Gate 7 - fixed pelagic polygon and its provenance
# ---------------------------------------------------------------------------

POLYGON_EXPECTED_AREA_M2 = 247766.333
POLYGON_AREA_TOLERANCE_M2 = 0.5
POLYGON_EXPECTED_VERTICES = 6
POLYGON_EXPECTED_PIXELS = 615
POLYGON_EXPECTED_ACCEPTED_POINTS = 22


def _gate_polygon(context: GateContext) -> GateRecord:
    gate_id = "materialize_the_fixed_pelagic_field_validation_polygon_and_its_provenance"
    blocking: list[str] = []
    mismatches: list[str] = []
    paths: list[str] = []
    details: dict[str, Any] = {}

    manifest = context.satellite_manifest
    if manifest is None:
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary="No satellite audit manifest to read polygon provenance from.",
            evidence_paths=(),
            blocking_reason="canonical v1.2 satellite audit manifest missing",
            details=details,
        )

    geojson_path = context.satellite_file("vombsjon_field_sampling_area.geojson")
    provenance_path = context.satellite_file(
        "vombsjon_field_sampling_area_provenance.csv"
    )
    for target in (geojson_path, provenance_path):
        if target.is_file():
            paths.append(context.relative(target))
        else:
            blocking.append(f"required polygon evidence missing: {target.name}")

    area = manifest.get("field_sampling_area") or {}
    details["field_sampling_area"] = {
        "rule_id": area.get("rule_id"),
        "construction": area.get("construction"),
        "buffer_m": area.get("buffer_m"),
        "clipped_to_geometry": area.get("clipped_to_geometry"),
        "vertex_count": area.get("vertex_count"),
        "area_m2": area.get("area_m2"),
        "accepted_point_count": area.get("accepted_point_count"),
        "nominal_inside": area.get("nominal_inside"),
        "nominal_is_vertex": area.get("nominal_is_vertex"),
        "tuned_from_satellite_or_field_performance": area.get(
            "tuned_from_satellite_or_field_performance"
        ),
    }
    if not area:
        blocking.append("the manifest records no field_sampling_area summary")
    else:
        if area.get("vertex_count") != POLYGON_EXPECTED_VERTICES:
            mismatches.append(
                f"polygon vertex_count is {area.get('vertex_count')!r}; expected "
                f"{POLYGON_EXPECTED_VERTICES}"
            )
        if not _close(
            area.get("area_m2"),
            POLYGON_EXPECTED_AREA_M2,
            tolerance=POLYGON_AREA_TOLERANCE_M2,
        ):
            mismatches.append(
                f"polygon area {area.get('area_m2')!r} m2 is outside "
                f"{POLYGON_EXPECTED_AREA_M2} +/- {POLYGON_AREA_TOLERANCE_M2} m2"
            )
        if not _close(area.get("buffer_m"), 0.0, tolerance=0.0):
            mismatches.append(f"polygon buffer_m is {area.get('buffer_m')!r}; expected 0")
        if area.get("clipped_to_geometry") not in (None, ""):
            mismatches.append(
                f"polygon was clipped to {area.get('clipped_to_geometry')!r}; no "
                "authoritative open-water geometry may be invented"
            )
        if "unbuffered_convex_hull" not in str(area.get("construction")):
            mismatches.append(
                f"polygon construction is {area.get('construction')!r}; expected an "
                "unbuffered convex hull"
            )
        if area.get("accepted_point_count") != POLYGON_EXPECTED_ACCEPTED_POINTS:
            mismatches.append(
                f"polygon accepted_point_count is {area.get('accepted_point_count')!r}; "
                f"expected {POLYGON_EXPECTED_ACCEPTED_POINTS} including the nominal anchor"
            )
        if area.get("nominal_inside") is not True:
            mismatches.append("the nominal station is not inside the hull")
        if area.get("nominal_is_vertex") is not False:
            mismatches.append("the nominal station is a hull vertex")
        if area.get("tuned_from_satellite_or_field_performance") is not False:
            mismatches.append("the polygon is recorded as tuned from performance")

    counts = manifest.get("counts") or {}
    pixel_counts = counts.get("polygon_target_grid_pixel_counts_observed")
    details["polygon_target_grid_pixel_counts_observed"] = pixel_counts
    if not pixel_counts:
        blocking.append("the manifest records no observed polygon pixel count")
    elif list(pixel_counts) != [POLYGON_EXPECTED_PIXELS]:
        mismatches.append(
            f"observed polygon pixel counts {list(pixel_counts)}; expected a "
            f"constant [{POLYGON_EXPECTED_PIXELS}] across every product"
        )

    rules = _dotted(manifest, "extraction_and_qc_rules.spatial_support_roles", {}) or {}
    details["spatial_support_roles"] = dict(rules) if rules else None
    if str(rules.get("primary_field_validation_support")) != (
        "fixed_pelagic_convex_hull_polygon"
    ):
        mismatches.append(
            "the primary field-validation support is not the fixed pelagic polygon"
        )
    secondary = str(rules.get("secondary_spatial_sensitivity") or "")
    if "actual_gps_3x3" not in secondary or "secondary" not in secondary:
        mismatches.append(
            f"actual-GPS 3x3 is not recorded as a secondary sensitivity: {secondary!r}"
        )

    polygon_rules = _dotted(manifest, "extraction_and_qc_rules.field_polygon", {}) or {}
    details["identical_for_every_field_date"] = polygon_rules.get(
        "identical_for_every_field_date"
    )
    details["moves_between_dates"] = polygon_rules.get("moves_between_dates")
    if polygon_rules.get("identical_for_every_field_date") is not True:
        mismatches.append("the polygon is not declared identical for every field date")
    if polygon_rules.get("moves_between_dates") is not False:
        mismatches.append("the polygon is declared to move between dates")

    summary = (
        f"Fixed pelagic hull with {area.get('vertex_count')} vertices, "
        f"{area.get('area_m2')} m2, {POLYGON_EXPECTED_PIXELS} centre-in-polygon "
        "20 m pixels, unbuffered and unclipped, identical on every field date."
    )
    return _terminal(gate_id, summary, paths, blocking, mismatches, details)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _terminal(
    gate_id: str,
    summary: str,
    paths: Sequence[str],
    blocking: Sequence[str],
    mismatches: Sequence[str],
    details: Mapping[str, Any],
) -> GateRecord:
    """Resolve a gate: contradiction outranks absence, absence outranks PASS."""

    if mismatches:
        return GateRecord(
            gate_id=gate_id,
            status=FAIL,
            evidence_summary=summary,
            evidence_paths=tuple(paths),
            mismatch_reason="; ".join(dict.fromkeys(mismatches)),
            details=dict(details),
        )
    if blocking:
        return GateRecord(
            gate_id=gate_id,
            status=BLOCKED,
            evidence_summary=summary,
            evidence_paths=tuple(paths),
            blocking_reason="; ".join(dict.fromkeys(blocking)),
            details=dict(details),
        )
    return GateRecord(
        gate_id=gate_id,
        status=PASS,
        evidence_summary=summary,
        evidence_paths=tuple(paths),
        details=dict(details),
    )


GATE_EVALUATORS: dict[str, Callable[[GateContext], GateRecord]] = {
    "verify_external_input_identity_licence_and_sha256": _gate_external_input_identity,
    "audit_raw_sentinel2_and_acolite_product_provenance": _gate_product_provenance,
    "resolve_or_retain_coordinate_flags_without_silent_correction": (
        _gate_coordinate_flags
    ),
    "materialize_qc_and_same_day_deduplication_audit": _gate_qc_same_day,
    "verify_acolite_versions_and_effective_settings_match_this_freeze": (
        _gate_acolite_identity
    ),
    "verify_timesat_runtime_matches_snapshot": _gate_timesat_runtime,
    "materialize_the_fixed_pelagic_field_validation_polygon_and_its_provenance": (
        _gate_polygon
    ),
}


def evaluate_gates(context: GateContext) -> list[GateRecord]:
    """Evaluate every gate the freeze requires, in the freeze's own order."""

    gate_ids = required_gate_ids(context.freeze)
    unknown = [gate_id for gate_id in gate_ids if gate_id not in GATE_EVALUATORS]
    if unknown:
        raise ExecutionGateError(
            "The governing freeze requires gate(s) this module cannot evaluate: "
            f"{unknown}. A required gate is never skipped or assumed to pass."
        )
    return [GATE_EVALUATORS[gate_id](context) for gate_id in gate_ids]


def summarize(records: Sequence[GateRecord]) -> dict[str, Any]:
    """Summarize gate outcomes. Closure requires every gate to PASS."""

    counts = {state: sum(1 for item in records if item.status == state) for state in TERMINAL_STATES}
    complete = bool(records) and counts[PASS] == len(records)
    return {
        "gate_count": len(records),
        "n_pass": counts[PASS],
        "n_fail": counts[FAIL],
        "n_blocked": counts[BLOCKED],
        "gate_closure_complete": complete,
        "performance_execution_eligible": complete,
        # Never set true here. The historical freeze retains authorization=false
        # and this module does not rewrite governance retrospectively.
        "performance_execution_authorized": False,
    }


# ---------------------------------------------------------------------------
# Context construction
# ---------------------------------------------------------------------------


def build_context(
    *,
    repository_root: str | Path,
    freeze_path: str | Path | None = None,
    satellite_audit_dir: str | Path | None = None,
    field_audit_dir: str | Path | None = None,
    timesat_snapshot_path: str | Path | None = None,
    external_input_evidence_path: str | Path | None = None,
    acolite_source_root: str | Path | None = None,
    wrapper_root: str | Path | None = None,
    timesat_runtime: Mapping[str, Any] | None = None,
) -> GateContext:
    """Load every piece of evidence the gates may read."""

    root = Path(repository_root)
    freeze_file = Path(freeze_path) if freeze_path else root / DEFAULT_FREEZE_PATH
    if not freeze_file.is_file():
        raise ExecutionGateError(f"Governing freeze not found: {freeze_file}")
    freeze = _read_json(freeze_file)
    if not isinstance(freeze, Mapping):
        raise ExecutionGateError("The governing freeze must be a JSON object.")

    satellite_dir = (
        Path(satellite_audit_dir)
        if satellite_audit_dir
        else root / DEFAULT_SATELLITE_AUDIT_DIR
    )
    field_dir = (
        Path(field_audit_dir) if field_audit_dir else root / DEFAULT_FIELD_AUDIT_DIR
    )
    snapshot = (
        Path(timesat_snapshot_path)
        if timesat_snapshot_path
        else root / DEFAULT_TIMESAT_SNAPSHOT
    )

    satellite_manifest_path = satellite_dir / SATELLITE_MANIFEST_NAME
    satellite_manifest = (
        _read_json(satellite_manifest_path)
        if satellite_manifest_path.is_file()
        else None
    )
    field_manifest_path = field_dir / FIELD_MANIFEST_NAME
    field_manifest = (
        _read_json(field_manifest_path) if field_manifest_path.is_file() else None
    )

    evidence: Mapping[str, Any] | None = None
    evidence_relative: str | None = None
    if external_input_evidence_path:
        evidence_file = Path(external_input_evidence_path)
        if not evidence_file.is_file():
            raise ExecutionGateError(
                f"External-input evidence file not found: {evidence_file}"
            )
        loaded = _read_json(evidence_file)
        if not isinstance(loaded, Mapping):
            raise ExecutionGateError(
                "External-input evidence must be a JSON object."
            )
        evidence = loaded
        try:
            evidence_relative = evidence_file.resolve().relative_to(
                root.resolve()
            ).as_posix()
        except ValueError:
            evidence_relative = evidence_file.name

    return GateContext(
        repository_root=root,
        freeze=freeze,
        freeze_relative_path=(
            freeze_file.resolve().relative_to(root.resolve()).as_posix()
            if _within(freeze_file, root)
            else freeze_file.as_posix()
        ),
        freeze_sha256=sha256_file(freeze_file),
        satellite_audit_dir=satellite_dir,
        satellite_manifest=satellite_manifest,
        field_audit_dir=field_dir,
        field_manifest=field_manifest,
        timesat_snapshot_path=snapshot,
        external_input_evidence=evidence,
        external_input_evidence_path=evidence_relative,
        acolite_source_observation=(
            observe_git_root(acolite_source_root) if acolite_source_root else None
        ),
        wrapper_observation=(
            observe_git_root(wrapper_root) if wrapper_root else None
        ),
        timesat_runtime=timesat_runtime,
    )


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Manifest and writers
# ---------------------------------------------------------------------------


def build_manifest(
    records: Sequence[GateRecord],
    *,
    context: GateContext,
    repository_state: Mapping[str, Any],
    runtime_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build the gate-closure manifest."""

    summary = summarize(records)
    evidence: dict[str, Any] = {
        "governing_freeze": {
            "path": context.freeze_relative_path,
            "sha256": context.freeze_sha256,
            "freeze_version": context.freeze.get("freeze_version"),
            "vombsjon_performance_execution_authorized": _dotted(
                context.freeze, "scope.vombsjon_performance_execution_authorized"
            ),
        },
        "satellite_input_audit": _evidence_entry(
            context, context.satellite_audit_dir / SATELLITE_MANIFEST_NAME
        ),
        "field_input_audit": _evidence_entry(
            context, context.field_audit_dir / FIELD_MANIFEST_NAME
        ),
        "field_source_manifest": _evidence_entry(
            context, context.field_audit_dir / FIELD_SOURCE_MANIFEST_NAME
        ),
        "timesat_defaults_snapshot": _evidence_entry(
            context, context.timesat_snapshot_path
        ),
        "external_input_evidence": (
            {"path": context.external_input_evidence_path, "supplied": True}
            if context.external_input_evidence is not None
            else {"path": None, "supplied": False}
        ),
    }

    unresolved = [
        {
            "gate_id": item.gate_id,
            "status": item.status,
            "blocking_reason": item.blocking_reason,
            "mismatch_reason": item.mismatch_reason,
        }
        for item in records
        if item.status != PASS
    ]

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "gate_closure_version": GATE_CLOSURE_VERSION,
        "processing_timestamp_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "repository_commit_at_start": repository_state.get("repository_commit_at_start"),
        "repository_worktree_dirty_at_start": repository_state.get(
            "repository_worktree_dirty_at_start"
        ),
        "repository_state_captured_before_writing_outputs": repository_state.get(
            "captured_before_writing_outputs"
        ),
        "python_version": sys.version.split()[0],
        "platform": platform_module.platform(terse=True),
        "evidence": evidence,
        "required_gate_ids": list(required_gate_ids(context.freeze)),
        "gate_records": [item.as_record() for item in records],
        "acolite_source_observation": context.acolite_source_observation,
        "wrapper_observation": context.wrapper_observation,
        "timesat_runtime_validation": runtime_result,
        "unresolved_or_blocking_evidence": unresolved,
        "interpretation": {
            "PASS": "evidence affirmatively establishes the frozen requirement",
            "FAIL": "evidence affirmatively contradicts the frozen requirement",
            "BLOCKED": (
                "required evidence is absent, incomplete or not machine-verifiable; "
                "this is not a failed scientific result"
            ),
            "missing_evidence_is_blocked_never_pass": True,
            "path_set_fingerprint_is_not_a_content_checksum": True,
            "acolite_version_string_is_not_a_stable_source_identity": True,
        },
        "scope_assertions": {
            "performance_evaluated": False,
            "reconstruction_run": False,
            "vombsjon_performance_accessed": False,
            "daily_reconstructed_curves_created": False,
            "withheld_observation_experiment_run": False,
            "reconstruction_metrics_computed": False,
            "field_correlation_or_regression_fitted": False,
            "processor_selected_from_vombsjon": False,
            "any_parameter_tuned": False,
            "frozen_transfer_setting_changed": False,
            "satellite_audit_outputs_modified": False,
            "transfer_freeze_outputs_modified": False,
            "field_chla_used_in_gate_evaluation": False,
        },
    }
    manifest.update(summary)
    manifest["payload_sha256"] = canonical_payload_sha256(
        manifest, excluded_keys=("payload_sha256",)
    )
    return manifest


def _evidence_entry(context: GateContext, path: Path) -> dict[str, Any]:
    present = path.is_file()
    return {
        "path": context.relative(path),
        "present": present,
        "sha256": sha256_file(path) if present else None,
    }


def assert_output_path_allowed(
    path: str | Path, *, repository_root: str | Path, output_root: str | Path
) -> Path:
    """Confine every write to the gate-closure namespace.

    The transfer-freeze namespace and both satellite-audit namespaces are
    committed evidence this module reads; writing into them is refused.
    """

    root = Path(repository_root).resolve()
    allowed = Path(output_root)
    if not allowed.is_absolute():
        allowed = root / allowed
    allowed = allowed.resolve()
    target = Path(path)
    resolved = (root / target if not target.is_absolute() else target).resolve()

    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as error:
        raise ExecutionGateScopeError(
            f"Gate-closure output escapes the repository root: {resolved}"
        ) from error
    try:
        allowed_relative = allowed.relative_to(root).as_posix()
    except ValueError as error:
        raise ExecutionGateScopeError(
            f"Gate-closure output root escapes the repository root: {allowed}"
        ) from error

    if not (relative == allowed_relative or relative.startswith(f"{allowed_relative}/")):
        raise ExecutionGateScopeError(
            f"Gate closure may only write under {allowed_relative!r}; refused "
            f"{relative!r}."
        )
    for prefix in PROTECTED_OUTPUT_PREFIXES:
        if relative == prefix or relative.startswith(f"{prefix}/"):
            raise ExecutionGateScopeError(
                f"Refusing to write into the protected namespace {prefix!r}: "
                f"{relative!r}."
            )
    return resolved


def write_gate_outputs(
    records: Sequence[GateRecord],
    *,
    context: GateContext,
    repository_state: Mapping[str, Any],
    runtime_result: Mapping[str, Any] | None,
    output_root: str | Path,
) -> dict[str, Path]:
    """Write the status CSV, the runtime record and the manifest, with LF endings."""

    repository_root = context.repository_root
    status_path = assert_output_path_allowed(
        Path(output_root) / "vombsjon_execution_gate_status.csv",
        repository_root=repository_root,
        output_root=output_root,
    )
    runtime_path = assert_output_path_allowed(
        Path(output_root) / "vombsjon_timesat_runtime_validation.json",
        repository_root=repository_root,
        output_root=output_root,
    )
    manifest_path = assert_output_path_allowed(
        Path(output_root) / "vombsjon_execution_gate_manifest.json",
        repository_root=repository_root,
        output_root=output_root,
    )

    status_path.parent.mkdir(parents=True, exist_ok=True)
    with status_path.open("w", encoding="utf-8", newline="") as handle:
        # csv defaults to \r\n regardless of the stream newline, so the
        # terminator is set explicitly to keep generated CSV LF-only.
        writer = csv.DictWriter(
            handle, fieldnames=list(STATUS_FIELDNAMES), lineterminator="\n"
        )
        writer.writeheader()
        for index, record in enumerate(records, start=1):
            writer.writerow(record.as_row(index))

    payload = runtime_result if runtime_result is not None else {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "runtime_available": False,
        "note": "The TIMESAT runtime was not probed in this invocation.",
    }
    runtime_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    manifest = build_manifest(
        records,
        context=context,
        repository_state=repository_state,
        runtime_result=runtime_result,
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "gate_status": status_path,
        "timesat_runtime_validation": runtime_path,
        "manifest": manifest_path,
    }
