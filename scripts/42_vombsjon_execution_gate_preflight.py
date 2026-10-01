#!/usr/bin/env python3
"""Vombsjon pre-performance execution-gate closure preflight.

Evaluates the seven gates that ``config/erken_vomb_transfer_freeze_v1.1.json``
requires before any Vombsjon reconstruction performance, and materializes the
gate report, a Vombsjon-specific TIMESAT runtime record and a manifest under
``results/vombsjon/execution_gate_closure/v1.0/``.

Governed by ``docs/Vombsjon_Execution_Gate_Closure_Protocol_v1.0.md``.

Three terminal states only: PASS, FAIL, BLOCKED. Absent evidence is BLOCKED,
never PASS. Closure requires 7/7 PASS and then sets
``performance_execution_eligible``; it never sets
``performance_execution_authorized``, which the historical freeze retains as
false.

This command runs no reconstruction, creates no daily curve, withholds no
observation, computes no reconstruction or matchup metric, fits no regression
or correlation, ranks no processor and tunes nothing. It never reads the
performance it exists to guard.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twinwater_timesat.vombsjon_execution_gates import (  # noqa: E402
    BLOCKED,
    DEFAULT_FIELD_AUDIT_DIR,
    DEFAULT_FREEZE_PATH,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SATELLITE_AUDIT_DIR,
    DEFAULT_TIMESAT_SNAPSHOT,
    FAIL,
    PASS,
    ExecutionGateError,
    ExecutionGateScopeError,
    build_context,
    capture_repository_state,
    default_timesat_runtime_probe,
    evaluate_gates,
    summarize,
    write_gate_outputs,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate and materialize the frozen Vombsjon pre-performance "
            "execution gates from committed and supplied evidence. Runs no "
            "reconstruction and reads no Vombsjon performance."
        )
    )
    # The governed inputs are pinned, not configurable. A run against another
    # freeze, audit or TIMESAT snapshot is not the canonical gate closure, so
    # the production CLI offers no way to substitute one. Tests inject fixture
    # paths through the module API instead.
    parser.add_argument(
        "--external-input-evidence",
        type=Path,
        default=None,
        help=(
            "Optional JSON document supplying observed identity, licence and "
            "content SHA256 for external inputs. Without it, gate 1 is BLOCKED "
            "rather than assumed. A path-set fingerprint is never accepted as a "
            "content checksum."
        ),
    )
    parser.add_argument(
        "--acolite-source-root",
        type=Path,
        default=None,
        help=(
            "Read-only path to the ACOLITE source checkout, so its stable Git "
            "identity can be observed rather than assumed from the freeze."
        ),
    )
    parser.add_argument(
        "--wrapper-root",
        type=Path,
        default=None,
        help=(
            "Read-only path to the s2-inlandwater-ac wrapper checkout, observed "
            "the same way."
        ),
    )
    parser.add_argument(
        "--acolite-execution-evidence",
        type=Path,
        default=None,
        help=(
            "Optional JSON document recording the ACOLITE invocation actually "
            "used, including any documented pre-specified execution override. "
            "The frozen wrapper commit alone does not record the executed "
            "configuration, so without this gate 5 remains BLOCKED."
        ),
    )
    parser.add_argument(
        "--acolite-execution-artifact",
        type=Path,
        default=None,
        help=(
            "Read-only path to the preserved corrected ACOLITE execution "
            "artifact itself. Its SHA256 is computed from the file's actual "
            "bytes and checked against the execution evidence's declared "
            "execution_script_sha256, and its declared --profile, --resolution, "
            "polygon_clip and ancillary_data settings are compared with the "
            "freeze. This is evidence, not a governed repository input, so it "
            "may live outside the repository."
        ),
    )
    parser.add_argument(
        "--skip-timesat-probe",
        action="store_true",
        help=(
            "Do not probe the TIMESAT runtime. Gate 6 is then BLOCKED, which is "
            "the honest outcome when the registered runtime is unavailable."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate and report, but write no output files.",
    )
    parser.add_argument(
        "--require-closure",
        action="store_true",
        help="Exit non-zero unless all required gates PASS.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Capture the repository state BEFORE any output file is created, so newly
    # written outputs cannot make this run report its own worktree as dirty.
    repository_state = capture_repository_state(ROOT)

    try:
        context = build_context(
            repository_root=ROOT,
            freeze_path=ROOT / DEFAULT_FREEZE_PATH,
            satellite_audit_dir=ROOT / DEFAULT_SATELLITE_AUDIT_DIR,
            field_audit_dir=ROOT / DEFAULT_FIELD_AUDIT_DIR,
            timesat_snapshot_path=ROOT / DEFAULT_TIMESAT_SNAPSHOT,
            external_input_evidence_path=args.external_input_evidence,
            acolite_execution_evidence_path=args.acolite_execution_evidence,
            acolite_execution_artifact_path=args.acolite_execution_artifact,
            acolite_source_root=args.acolite_source_root,
            wrapper_root=args.wrapper_root,
            enforce_canonical=True,
        )
    except ExecutionGateError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    runtime_result = None
    if not args.skip_timesat_probe:
        runtime_result = default_timesat_runtime_probe(
            context.timesat_snapshot_path, transfer_config=context.freeze
        )
    context.timesat_runtime = runtime_result

    try:
        records = evaluate_gates(context)
    except ExecutionGateError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    summary = summarize(records, repository_state=repository_state)

    written: dict[str, Path] = {}
    if not args.dry_run:
        try:
            written = write_gate_outputs(
                records,
                context=context,
                repository_state=repository_state,
                runtime_result=runtime_result,
                output_root=ROOT / DEFAULT_OUTPUT_ROOT,
            )
        except (ExecutionGateError, ExecutionGateScopeError) as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2

    print("Vombsjon pre-performance execution-gate preflight")
    print(f"  governing freeze : {context.freeze_relative_path}")
    print(
        "  repository at start: "
        f"{repository_state.get('repository_commit_at_start')} "
        f"(dirty={repository_state.get('repository_worktree_dirty_at_start')})"
    )
    print()
    for index, record in enumerate(records, start=1):
        print(f"  [{index}/{len(records)}] {record.status:<7} {record.gate_id}")
        if record.blocking_reason:
            print(f"          blocked: {record.blocking_reason}")
        if record.mismatch_reason:
            print(f"          mismatch: {record.mismatch_reason}")
    print()
    for name, path in sorted(written.items()):
        print(f"Wrote {path.relative_to(ROOT)} ({name})")
    if args.dry_run:
        print("Dry run: no output file was written.")
    print()

    total = summary["gate_count"]
    if summary["gate_closure_complete"]:
        print(f"Vombsjön pre-performance execution gates: {total}/{total} PASS")
        print("Gate closure complete.")
        print(
            "Performance execution eligible, but no performance was run by this "
            "command."
        )
        return 0

    print(
        f"STOP: Vombsjön pre-performance execution gates: {summary['n_pass']}/{total} "
        f"PASS, {summary['n_fail']} FAIL, {summary['n_blocked']} BLOCKED."
    )
    if summary["seven_gates_passed"] and not summary["repository_provenance_ready"]:
        print(
            "All seven evidence gates PASS, but the repository provenance "
            "prerequisite is not met: "
            f"{summary['repository_provenance_blocking_reason']}."
        )
        print(
            "This is a provenance prerequisite, not a scientific failure and not "
            "an eighth gate. Commit or stash the working tree and rerun from a "
            "clean checkout to produce a canonical closure artifact."
        )
    print("Gate closure is NOT complete and performance execution is NOT eligible.")
    if summary["n_blocked"]:
        print(
            "A BLOCKED gate is not a failed scientific result: it means the "
            "required evidence is absent, incomplete or not machine-verifiable. "
            "Supply the evidence; do not weaken the gate."
        )
    if summary["n_fail"]:
        print(
            "A FAIL gate means committed evidence contradicts the freeze. Stop "
            "and resolve it; do not retune a setting or fall back to another "
            "product."
        )
    return 1 if args.require_closure else 0


if __name__ == "__main__":
    raise SystemExit(main())
