# Vombsjön pre-performance execution-gate closure protocol v1.0

**Status: implemented, not yet closed.** Gate closure has not been achieved;
see §10 for the current evaluation against committed evidence.

**Purpose and timing.** The Vombsjön raw satellite/product and matchup audit is
complete at v1.2. This protocol governs the *next* stage: evaluating and
materializing the seven gates the governing freeze requires **before** any
Vombsjön reconstruction performance is evaluated. It sits between the input
audit and the locked transfer, and it is the last checkpoint before
performance.

**Governing freeze:** [`config/erken_vomb_transfer_freeze_v1.1.json`](../config/erken_vomb_transfer_freeze_v1.1.json),
**unmodified**. It retains
`scope.vombsjon_performance_execution_authorized = false`, and this protocol
does not rewrite it.

**Implementation:** [`scripts/42_vombsjon_execution_gate_preflight.py`](../scripts/42_vombsjon_execution_gate_preflight.py)
over [`src/twinwater_timesat/vombsjon_execution_gates.py`](../src/twinwater_timesat/vombsjon_execution_gates.py).

**Output namespace:** `results/vombsjon/execution_gate_closure/v1.0/`.

**Change log.** The protocol text was hardened after first implementation to
match the code, with no change to any scientific rule, threshold or gate
identity: §1.1 (canonical path pinning and freeze validation), §3 (closure
needs a clean-start repository as well as 7/7 PASS), §4 gates 1, 2, 4, 5 and 7
(exact evidence coverage), §5.1 (checkout line endings are not a content
difference), §6.1 (the wrapper commit pins source, not the executed
invocation), §9 and §12. The evaluation against committed evidence in §10 is
unchanged at 4/7 PASS, 0 FAIL, 3 BLOCKED.

A second, smaller pass then added two evidence checks, again with no change to
any scientific rule: `licence_verified` must be the JSON boolean `true`
(§4, gate 1), and the preserved corrected execution artifact is verified by
its own bytes and parsed settings (§6.1). The committed-evidence evaluation
remains 4/7 PASS, 0 FAIL, 3 BLOCKED.

## 1. The seven gates

The gate identities and their order are read at run time from
`execution_gates.before_vomb_performance` in the freeze. They are **not**
restated in code, so a gate cannot be silently dropped, renamed or reordered.
A required gate with no evaluator is an error, never an implicit pass.

| # | Gate id |
|---|---|
| 1 | `verify_external_input_identity_licence_and_sha256` |
| 2 | `audit_raw_sentinel2_and_acolite_product_provenance` |
| 3 | `resolve_or_retain_coordinate_flags_without_silent_correction` |
| 4 | `materialize_qc_and_same_day_deduplication_audit` |
| 5 | `verify_acolite_versions_and_effective_settings_match_this_freeze` |
| 6 | `verify_timesat_runtime_matches_snapshot` |
| 7 | `materialize_the_fixed_pelagic_field_validation_polygon_and_its_provenance` |

## 1.1 The canonical closure is pinned; it cannot be pointed elsewhere

A run against a substituted freeze, audit, TIMESAT snapshot or output
namespace is **not** the canonical gate closure, so the production command
offers no way to call it one. `scripts/42_…` exposes no `--freeze`,
`--satellite-audit-dir`, `--field-audit-dir`, `--timesat-snapshot` or
`--output-root`. It always builds its context with `enforce_canonical=True`,
which pins:

| Input | Pinned path |
|---|---|
| governing freeze | `config/erken_vomb_transfer_freeze_v1.1.json` |
| satellite input audit | `results/vombsjon/satellite_input_audit/v1.2/` |
| field input audit | `results/vombsjon/field_input_audit/v1.0/` |
| TIMESAT defaults snapshot | `config/timesat_double_logistic_defaults_v4.4.1.json` |
| output namespace | `results/vombsjon/execution_gate_closure/v1.0/` |

Anything else raises rather than producing a mislabelled artifact. Tests may
still inject fixture paths through the module API with pinning off; production
may not.

With pinning on, the freeze is also **validated before any gate is
evaluated**. It must declare `schema_version`
`erken_vomb_transfer_freeze_config_v2`, `freeze_version`
`erken_vomb_transfer_freeze_v1.1`, exactly the seven gate identities of §1, and
`scope.vombsjon_performance_execution_authorized = false`. A freeze that has
been edited to authorize performance is refused outright: this layer will not
run against a freeze that pre-authorizes what it exists to gate.

Pinning fixes the *path*. Gate 2 additionally requires the committed audit to
have been produced against that same freeze **by content** (§4, gate 2).

## 2. Terminal states

Exactly three, and no fourth:

- **PASS** — available evidence *affirmatively establishes* the frozen
  requirement.
- **FAIL** — available evidence *affirmatively contradicts* the frozen
  requirement.
- **BLOCKED** — the required evidence is absent, incomplete, or not
  machine-verifiable.

**Absent evidence is BLOCKED, never PASS.** Within one gate, a contradiction
outranks an absence: if any check contradicts the freeze the gate is FAIL, else
if any check lacks evidence the gate is BLOCKED, else PASS.

**A BLOCKED gate is not a failed scientific result.** It is a statement about
the evidence, not about the lake. The response is to supply evidence, never to
weaken the gate.

## 3. Closure arithmetic

Closure needs **both halves**, and they are reported separately:

```
seven_gates_passed             = all seven gates PASS
repository_provenance_ready    = the run started from an observable, clean checkout
gate_closure_complete          = seven_gates_passed AND repository_provenance_ready
performance_execution_eligible = gate_closure_complete
```

Otherwise `gate_closure_complete` and `performance_execution_eligible` are
`false`.

**The repository prerequisite is not an eighth gate.** A dirty or unobservable
working tree says the closure artifact would not be reproducible from a named
commit; it says nothing about the lake, and it never turns a gate into FAIL or
BLOCKED. Consequently, a run with 7/7 PASS on a dirty tree still prints
`n_fail = 0, n_blocked = 0` and reports the provenance prerequisite by name:

```
repository_provenance_blocking_reason = "the repository worktree was already
dirty at process start, so the closure artifact would not be reproducible
from a named commit"
```

The prerequisite is unmet when the state was not captured, `git` was not
observable, the starting commit is unknown, cleanliness is unknown, or the tree
was dirty. The remedy is to commit or stash and rerun from a clean checkout,
not to relax anything.

`performance_execution_authorized` is **always written as `false`**. The
historical freeze retains authorization `false`; this protocol establishes
*eligibility* after gate closure and does not retrospectively rewrite
governance. Eligibility and authorization are deliberately different words.

## 4. Evidence required per gate

**Gate 1 — external input identity, licence, content SHA256.** For each
committed field source: the file is present and its content SHA256 matches the
committed field source manifest, **and** the manifest establishes a licence.
For each external satellite archive (L1C, L2A, ACOLITE): identity, licence and
a *content* checksum. A licence sentence recording that none was found, or that
one was not independently verified, does not establish a licence.

Optional supplied evidence: `--external-input-evidence`, a JSON document with
`schema_version: "vombsjon_external_input_evidence_v1"` and an `inputs` list.
Each entry needs `input_id`, `identity`, `licence`, `licence_verified: true`,
`content_sha256` and a `content_checksum_scope` naming real content
(`file_content`, `archive_member_content` or `content_manifest`). Incomplete
entries block. Nothing in that file may be populated with an unsupported fact,
and no licence may be supplied from general knowledge.

**Coverage is exact and per archive.** Each of `L1C`, `L2A` and `ACOLITE` is
judged on its own evidence. An entry is *usable* only when every required
field is present and well formed; an incomplete or malformed entry contributes
nothing and can never clear a different archive's block. Concretely:

- evidence for `L1C` alone leaves `L2A` and `ACOLITE` BLOCKED;
- evidence for two archives leaves the third BLOCKED;
- a complete entry for some unrelated `input_id` clears nothing;
- a `content_sha256` that is not exactly 64 hexadecimal characters is not a
  checksum, and its entry is rejected;
- a duplicate `input_id` for a required archive makes coverage ambiguous and is
  a **FAIL**, not a BLOCKED.

The gate records `covered_external_archives` so the coverage actually achieved
is auditable rather than inferred. Hexadecimal case is not significant and a
digest is compared case-insensitively; length and alphabet are what is checked.

**`licence_verified` must be the JSON boolean `true`.** It is never coerced:
`false`, `"true"`, `"false"`, `1` and `"1"` are all rejected and the entry is
BLOCKED. A truthy string or number is an assertion written in the wrong type,
not a verification, and accepting it would let a typo stand in for a checked
licence. The declared type is recorded in `licence_verified_declared_type`.

**Gate 2 — product provenance.** From the committed v1.2 audit: audit version
is v1.2; the manifest, L1C/L2A/ACOLITE inventories, pairing audit and
extraction-failure audit all exist; the manifest records 1509 L1C, 1510 L2A,
1505 ACOLITE, 1466 exact-unique pairs and 48 failure rows; every recorded
freeze cross-check agrees. The manifest's own SHA256 is recorded, so the gate
is anchored to bytes rather than to filenames.

**The audit must be anchored to *this* governing freeze.** The v1.2 manifest
records a `governing_freeze` block with the freeze path, content SHA256 and
freeze version it was produced against. The gate requires it and checks it:

- no `governing_freeze` block at all → **BLOCKED** (the audit cannot be shown
  to belong to this freeze);
- no recorded SHA256 → **BLOCKED**;
- a recorded path or freeze version naming a different freeze → **FAIL**;
- a recorded checksum matching neither form of the present freeze content
  (§5.1) → **FAIL**: the audit was produced against different freeze content.

Path pinning (§1.1) and this content anchor are complementary. Pinning stops a
run from being aimed at another freeze; the anchor stops a *correctly aimed*
run from silently accepting an audit that was produced against something else.

**Gate 3 — coordinate flags retained.** The correct behaviour is *not* to
repair 2020-06-10 and 2020-06-24. Both dates must still appear in the field
matchup table as `measured_gps_flagged_unresolved`, with
`coordinate_correction_applied = false`, contributing no coordinate to polygon
construction, and with a GPS 3×3 sensitivity status that is not `extracted`.
The declared rules must forbid coordinate correction, retain the unresolved
dates in the primary polygon comparison, and forbid a nominal-point fallback.
Dropping an unresolved date is a FAIL, as is any silent correction.

**Gate 4 — QC and same-day deduplication.** The product extraction master,
native QA inventory, fixed-station observation master and same-day observation
master all exist. The declared rules keep the fixed 3×3 target, 6-of-9 minimum
valid pixels, no invalid-pixel filling, no negative-reflectance clamping, no
MCI clipping, `observation_unavailable` for missing required QA, the whole
calendar date as the unit, per-method median of eligible observation-level
medians, product rows preserved first, and methods never pooled. The same-day
table must not mark reprocessings as independent observations, must not pool
methods, and must have no duplicate `(method, date)` key.

**Existence is not content.** Each materialized table's data-row count is
cross-checked against the count the manifest itself records —
`extraction_rows`, `fixed_target_observation_rows` and `same_day_rows` — so a
truncated or emptied CSV cannot pass merely by being present. A disagreement
is a **FAIL**; a manifest that records no count for a present table is
**BLOCKED**, because the table then cannot be cross-checked at all. The
expected values are read from the manifest, never hard-coded in the gate.

**Gate 5 — ACOLITE identity and settings.** Four things are kept apart:

- **A. stable source-code identity** — the Git commit. Verified only from
  *observed* evidence: `--acolite-source-root` and `--wrapper-root` are
  inspected read-only for `git rev-parse HEAD` and `git status --porcelain`.
  **A commit declared by the freeze is not observed evidence**; without an
  observation the gate is BLOCKED. A dirty worktree is recorded explicitly and
  blocks: arbitrary local modifications are not assumed harmless.
- **B. effective run settings** — verified per scene from the committed audit:
  `ancillary_data=True`, `s2_target_res=20`, `polygon` (a single Vombsjön ROI),
  `l2r_export_geotiff=True`, `l2w_export_geotiff=True`, plus `profile=inland`
  (see below).
- **C. textual version metadata** — recorded, never used as identity (§6).
- **D. the invocation actually executed** — reconciled separately (§6.1),
  because a commit pins source, not execution.

**The freeze is the only source of expected values.** Every expectation is read
at run time from `observation_layer.primary_processing_product` in the
governing freeze: method, quantity, `acolite_source_commit`,
`s2_inlandwater_ac_commit`, `profile`, `resolution_m`, `polygon_clip`,
`ancillary_data`, `output_quantity` and `no_silent_product_fallback`. The gate
records `expectations_source` alongside them.

The v1.2 manifest carries its own copy of the frozen identity in
`acolite.identity.freeze_declared_identity`. That copy is **checked against the
freeze, never used to define it**: if it disagrees with the freeze the gate is
**FAIL**. Editing the manifest's copy therefore cannot move the target.

**Coverage must be complete.** A scene-declared setting establishes a frozen
requirement only when `declared_scene_count` equals the discovered ACOLITE
scene count the manifest records — 1505. A setting declared by 1 scene, or by
1504, is **BLOCKED** as partial coverage, not accepted as evidence; the
blocking reason names the shortfall (`declared by 1 of 1505 discovered
scenes`). If the manifest records no scene count at all, coverage cannot be
established and the gate is BLOCKED.

**`profile = inland`** is frozen but is not a per-scene setting in the v1.2
audit. It may instead be attested by the checksum-identified execution
evidence of §6.1, whose `attested_effective_settings.profile` must equal the
frozen value. With neither source it is **BLOCKED** — never assumed. An
attested value contradicting the freeze is a **FAIL**.

**Polygon clipping** is evidenced by a single non-empty polygon passed to every
scene. The absolute path is machine-specific and is not asserted; an empty or
multi-valued setting is a FAIL, and a polygon that does not identifiably
correspond to the Vombsjön ROI is BLOCKED rather than assumed to be it.

**No silent product fallback** needs both recorded flags —
`acolite.identity.netcdf_fallback_allowed` and
`extraction_and_qc_rules.product_roles.silent_processor_fallback_allowed`. A
missing flag is BLOCKED; a permitted fallback is FAIL. The four ACOLITE scenes
with no usable rhos GeoTIFF are recorded as *unavailable*; an unavailable
observation is not a fallback, and the gate records that distinction.

If effective settings verify but stable source identity cannot be observed, or
the executed invocation is not established, the gate remains **BLOCKED**.

**Gate 6 — TIMESAT runtime.** See §7.

**Gate 7 — fixed pelagic polygon.** The GeoJSON and provenance table exist; the
polygon has 6 vertices, area 247766.333 m² within ±0.5 m², zero buffer, no
clipping geometry, unbuffered convex-hull construction, 22 accepted
construction points including the nominal anchor, the nominal station inside
the hull but not a vertex, `tuned_from_..._performance = false`, a constant 615
centre-in-polygon 20 m pixels across every product, the polygon identical on
every field date and not moving between dates, and actual-GPS 3×3 still
recorded as a secondary sensitivity. Area uses a numeric tolerance, not a float
string comparison.

**The committed files are parsed, not just listed.** Without this, an emptied
or replaced GeoJSON would still pass because the manifest continues to state
the old summary. The gate therefore reads the two files themselves and
checksums both:

- the GeoJSON must hold exactly one feature, of geometry type `Polygon`, with
  one closed 2-D coordinate ring. A GeoJSON ring repeats its first position to
  close, so the **vertex count is the ring length minus that repetition**: a
  valid six-vertex hull has seven ring positions. An unclosed ring, a wrong
  vertex count, a wrong geometry type or an unparseable file is a **FAIL**;
- the provenance table must record 22 accepted `source_point` rows including
  exactly one `nominal_station_anchor`, and 6 `hull_vertex` rows. Any drift in
  that accepted set is a **FAIL**, as is the acceptance of an unresolved
  coordinate date (2020-06-10, 2020-06-24) as a construction point — which
  would silently contradict gate 3.

## 5. A path-set fingerprint is not a content checksum

The v1.2 audit records `inventory_fingerprints`: SHA256 over sorted
`<id>\t<root-relative path>` lines, explicitly flagged
`is_raster_content_checksum: false`. Those fingerprints identify **which
products were discovered and where**, not what their bytes are. Two entirely
different rasters at the same path produce the same fingerprint.

Gate 1 therefore **never** accepts a path-set fingerprint as a raster or
content SHA256, records `path_set_fingerprint_accepted_as_content_checksum:
false`, and rejects a supplied evidence entry whose
`content_checksum_scope` names a path set.

## 5.1 Checkout line endings are not a content difference

A checkout made with `core.autocrlf=true` stores CRLF in the working tree while
the committed bytes use LF, so the working-tree checksum of a tracked text file
differs from the checksum an audit computed on a LF checkout. The v1.2
satellite audit was produced on a LF host and records the freeze's LF
checksum; on a CRLF workstation a naive byte comparison reports a mismatch that
is a checkout artifact, not different content.

Every recorded-checksum comparison in this layer therefore computes **both**
comparable forms of the file and accepts either, recording which one matched:

```
observed_sha256                  working-tree bytes
observed_sha256_as_committed_lf  the same content with committed LF endings
working_tree_uses_crlf           whether this checkout normalized line endings
checksum_form_matched            which form the recorded value identified
```

This is not a relaxation. The LF form *is* the committed content, so accepting
it identifies exactly the bytes under version control; a genuinely different
file matches neither form and is still reported as a mismatch. Rejecting the
LF form would produce a false FAIL on a Windows checkout, which is the opposite
of an honest gate.

## 6. ACOLITE stable Git identity versus the checkout timestamp string

ACOLITE reports a version string such as
`Generic GitHub Clone c2026-08-19T22:04:44`. For a GitHub clone that timestamp
is derived from the **local `.git/HEAD` filesystem mtime**, so two checkouts of
the *same* commit print different strings. It is environment and checkout
metadata, not a source-code identifier.

Consequences, all enforced in code:

- the frozen `acolite_version_string` is **not** rewritten to match a new
  checkout;
- literal version-string equality is never claimed, and the audit's
  `not_verifiable_from_supplied_files` status is not converted into one;
- a declared version string never establishes source identity, even when a
  scene file does declare one;
- the **Git commit** `64a02ff386e2985eef68ae00198b38e04f3c4a1f` (ACOLITE) and
  `6b5fe1f31a4e4d477c2ad552c97f3c2f442b8b0c` (wrapper) are the stable
  identities the gate checks, against observed evidence.

## 6.1 The wrapper commit pins source, not the executed invocation

The corrected v1.2 archive was produced with `ancillary_data=True`. The frozen
wrapper commit `6b5fe1f3…`, however, carries an example invocation that sets
`ancillary_data=False`. **The frozen wrapper script itself did not contain
`ancillary_data=True`, and this protocol does not pretend otherwise.** A clean
wrapper checkout at the frozen commit is therefore evidence of *which source*
was used, and is not by itself evidence of *what was run*. The gate records
`wrapper_commit_alone_establishes_execution: false`.

Nor may a permanently dirty wrapper worktree stand in for that record: an
uncommitted local edit is not an auditable statement of the executed
configuration, so a dirty wrapper is BLOCKED (§4, gate 5 A).

The only accepted reconciliation is an explicit execution record supplied with
`--acolite-execution-evidence`: a JSON document with `schema_version`
`vombsjon_acolite_execution_evidence_v1`, the `base_wrapper_commit`, the
`execution_script_path` and its `execution_script_sha256` (verified against
the artifact itself, below), the `observed_acolite_source_commit`,
`performance_inspected_before_override`, any
`attested_effective_settings`, and an `overrides` list. Without it, gate 5 is
**BLOCKED** — never PASS by assumption.

An override is accepted only when **all** of these hold:

| Requirement | Otherwise |
|---|---|
| the setting is one the governing freeze declares | BLOCKED — an arbitrary local change is not a documented correction |
| the executed value equals the frozen required value | FAIL |
| the record states the frozen required value correctly | FAIL |
| `override_pre_specified_before_performance: true` | FAIL |
| `performance_inspected_before_override: false` | FAIL |
| a `reason_for_override` is recorded | BLOCKED |
| `base_wrapper_commit` is the frozen wrapper commit | FAIL |
| `execution_script_sha256` is a valid 64-character digest | BLOCKED |

### The preserved artifact's own bytes

A declared `execution_script_sha256` is an assertion about a file. The
artifact itself is supplied with `--acolite-execution-artifact`, which is
**evidence, not a governed repository input**, so it may live outside the
repository: the supplied path is retained verbatim, its SHA256 is computed
from the file's real bytes at context construction, and neither is ever
reconstructed from `repository_root` plus a basename.

| Situation | Outcome |
|---|---|
| declared `execution_script_sha256` malformed | BLOCKED |
| evidence JSON supplied, artifact absent | BLOCKED |
| artifact's real SHA256 ≠ declared value | **FAIL** |
| exact match | artifact checksum identity established |

Gate 5 records `declared_execution_script_sha256`,
`observed_execution_artifact_sha256`, `execution_artifact_checksum_matches`
and `execution_artifact_path`, and the manifest records the same under
`evidence.acolite_execution_artifact` with an `outside_repository` flag.

The artifact's own declared settings are then read by **deterministic text
matching** — `--profile <value>`, `--resolution <value>`,
`--set polygon_clip=<value>`, `--set ancillary_data=<value>` — and compared
with the freeze. This is not a shell interpreter: a setting written in an
unrecognized form is reported as *not observed* rather than guessed at, and is
BLOCKED; a setting declared twice with conflicting values is ambiguous and is
BLOCKED; a parsed value that **contradicts** the freeze is a **FAIL**.

**What this does and does not establish.** It establishes that a preserved
corrected execution artifact exists, that its bytes are the ones the evidence
names, and that the settings it declares are independently consistent with the
`ancillary_data=True` effective configuration the v1.2 audit observed on all
1505 discovered ACOLITE scenes. **It is not job-log verification.** No
surviving job log links that exact file path to the invocation, the gate
records `execution_artifact_job_log_verified: false`, and no such claim may be
made anywhere in this project.

**Classification.** Running with `ancillary_data=True` implements a value the
freeze *already required* before any Vombsjön performance existed. That is an
execution and provenance correction, not scientific retuning, and the gate
says so in `execution_provenance.note`. The distinction is enforced, not
merely asserted: an override chosen after inspecting performance is retuning by
definition and is a **FAIL**, and so is an override to any value the freeze
does not require. No statement here claims that `ancillary_data=True` is
scientifically superior; it is simply what the freeze required.

## 7. The TIMESAT registered-build issue

Gate 6 runs a Vombsjön-specific runtime validation and writes it to
`results/vombsjon/execution_gate_closure/v1.0/vombsjon_timesat_runtime_validation.json`.
It **does not** call script 37 and **does not** overwrite
`results/transfer_freeze/v1.0/erken_transfer_timesat_runtime_validation.json`,
which belongs to the historical Erken freeze namespace.

It checks: TIMESAT core and CLI versions, module SHA256s, source defaults,
effective runtime parameters, the synthetic smoke test, and affine
equivariance for `timesat_double_logistic` and `timesat_smoothing_spline` at
`p_smooth=10`, using the frozen training affine scale from the governing
configuration. The series is synthetic; **no Vombsjön observation is read.**

The frozen snapshot registers a macOS CPython 3.12 build artifact
(`_timesat.cpython-312-darwin.so`) by SHA256. `probe_runtime` records
`registered_build_artifact` but does not itself fail when it is false. This
protocol makes that explicit and conservative:

| Condition | State |
|---|---|
| registered artifact **and** all runtime checks pass | PASS |
| explicit runtime mismatch with the snapshot | FAIL |
| affine equivariance fails | FAIL |
| otherwise-correct runtime, artifact **not** registered by the snapshot | BLOCKED |
| TIMESAT not importable, or probe failed for another reason | BLOCKED |

An unregistered Linux binary is never silently reported as the registered
frozen binary. **The snapshot is not amended to accommodate a runtime.** This
means the final gate run may need to happen in the registered macOS CPython
3.12 TIMESAT environment; that is the expected cost of the guarantee.

## 8. Outputs and stop behaviour

Written only under `results/vombsjon/execution_gate_closure/v1.0/`:

| File | Content |
|---|---|
| `vombsjon_execution_gate_status.csv` | one row per required gate: `gate_index`, `gate_id`, `status`, `evidence_summary`, `evidence_paths`, `blocking_reason`, `mismatch_reason` |
| `vombsjon_timesat_runtime_validation.json` | the Vombsjön gate-specific TIMESAT runtime record |
| `vombsjon_execution_gate_manifest.json` | full manifest (§9) |

Writes into `results/transfer_freeze/`, either satellite-audit namespace, the
field-audit namespace, any Erken phase namespace, `config/`, `data/`, `docs/`
or the source tree are refused in code.

The report and manifest are materialized **whether or not** closure succeeds,
so a blocked run leaves an auditable record. On 7/7 PASS the command prints
that closure is complete and performance is eligible but was not run. Otherwise
it prints a STOP message naming what is blocked or contradicted.

## 9. Manifest contents

`schema_version`, `gate_closure_version`, `processing_timestamp_utc`,
`repository_commit_at_start`, `repository_worktree_dirty_at_start`, Python and
platform, the governing freeze path and SHA256 with its retained
`vombsjon_performance_execution_authorized`, the satellite audit, field audit,
field source manifest, TIMESAT snapshot, polygon GeoJSON, polygon provenance,
external-input evidence and ACOLITE execution evidence paths with SHA256s,
the satellite audit's freeze anchor (§4, gate 2), `required_gate_ids` read from
the freeze, all seven gate records with their details, the observed ACOLITE and
wrapper Git records, the TIMESAT runtime validation,
`n_pass`/`n_fail`/`n_blocked`, `seven_gates_passed`,
`repository_provenance_ready` with its blocking reason,
`gate_closure_complete`, `performance_execution_eligible`,
`performance_execution_authorized = false`, the unresolved/blocking evidence
list, scope assertions, and `payload_sha256` over the canonical payload.

Every evidence file the gates read is anchored by content SHA256, so the
manifest identifies the bytes it was computed from rather than a set of
filenames.

**Repository state is captured before any output file is created.** The earlier
satellite audit queried `git status` *after* writing its outputs, so its own new
files made the worktree look dirty in its own manifest. This protocol captures
commit and cleanliness first and records
`repository_state_captured_before_writing_outputs: true`. A final closure
artifact **must** be produced from a clean starting repository: a dirty or
unobservable tree denies `gate_closure_complete` even at 7/7 PASS (§3), and is
recorded plainly rather than hidden.

## 10. Current evaluation against committed evidence

Run on the committed repository with no supplied source roots and no TIMESAT
probe, the outcome is **4/7 PASS, 0 FAIL, 3 BLOCKED**:

- gates 2, 3, 4 and 7 **PASS** from the committed v1.2 audit alone;
- gate 1 is **BLOCKED**: three of four committed field sources record no
  established licence, and no content SHA256 exists for any external satellite
  archive;
- gate 5 is **BLOCKED** for four separate reasons: the frozen `profile=inland`
  is neither scene-declared nor attested; stable ACOLITE source identity has
  not been independently observed; wrapper source identity has not been
  independently observed; and the executed ACOLITE invocation is not
  established, because the frozen wrapper commit alone does not record it
  (§6.1);
- gate 6 is **BLOCKED**: the registered TIMESAT runtime is not available here.

The hardening of §1.1, §3, §4, §5.1 and §6.1 did not change this outcome. The
stricter checks it added — the freeze content anchor, the 1505-scene coverage
requirement, the materialized row-count cross-checks and the parsed polygon
files — are all satisfied by the committed v1.2 evidence, which is why gates
2, 4 and 7 still PASS. Gate 5 gained one further blocking reason (the executed
invocation), which was previously not required at all.

Because gate 5 has not passed, **do not yet write that the corrected ACOLITE
archive "fully conforms to the freeze."** Effective settings conform; source
identity is not yet established.

## 11. Rules that cannot be relaxed

- **No performance.** This stage runs no reconstruction, creates no daily
  curve, withholds no observation, computes no reconstruction or matchup
  metric, fits no regression or correlation, and ranks no processor.
- **The guard never inspects what it guards.** Gate evaluation must never read
  the reconstruction performance it exists to protect. A regression test
  asserts that no performance-shaped artifact is opened during evaluation.
- **No retuning.** No parameter, threshold, polygon, QC rule or processor role
  may be adjusted to make a gate pass. A FAIL means stop and resolve, not
  retune or fall back to another product.
- **No gate may be waived because a Vombsjön result looks good.** Gate outcomes
  are independent of any Vombsjön value, and no Vombsjön value may be consulted
  when deciding one.
- **Field Chl-a is not used here.** It plays no part in gate evaluation. In the
  later transfer it remains complementary ecological and proxy validation,
  never daily truth.
- **7/7 PASS is required** before locked-transfer performance. Four of seven is
  not a partial authorization.
- **Eligibility, not retrospective rewriting.** Closure establishes eligibility
  going forward; the historical freeze keeps its own recorded state.
- **The canonical closure cannot be aimed elsewhere.** No substituted freeze,
  audit, TIMESAT snapshot or output namespace may be called the canonical gate
  closure (§1.1), and no audit produced against different freeze content may
  be accepted as evidence for this one (§4, gate 2).
- **A clean starting repository is required for the final artifact** (§3). It
  is a reproducibility prerequisite, never a scientific verdict, and a dirty
  tree must not be reported as a gate failure.
- **No gate may be weakened to make it pass.** Where this protocol accepts a
  second checksum form (§5.1) or an attested setting (§4, gate 5), it accepts
  strictly equivalent or independently checksummed evidence, never an
  assumption. Every other absence stays BLOCKED.

## 12. Running it

The governed inputs and the output namespace are pinned (§1.1), so there are no
flags for them. The only options supply *evidence* the repository does not
already contain, or reduce what is attempted.

Evidence-only evaluation, no TIMESAT, nothing written:

```
python scripts/42_vombsjon_execution_gate_preflight.py --dry-run --skip-timesat-probe
```

With observed source provenance:

```
python scripts/42_vombsjon_execution_gate_preflight.py \
  --acolite-source-root /path/to/s2-inlandwater-ac/.external/acolite \
  --wrapper-root /path/to/s2-inlandwater-ac
```

Final closure, in the registered macOS CPython 3.12 TIMESAT environment, from a
**clean** repository:

```
python scripts/42_vombsjon_execution_gate_preflight.py \
  --acolite-source-root /path/to/s2-inlandwater-ac/.external/acolite \
  --wrapper-root /path/to/s2-inlandwater-ac \
  --external-input-evidence path/to/vombsjon_external_input_evidence.json \
  --acolite-execution-evidence path/to/vombsjon_acolite_execution_evidence.json \
  --acolite-execution-artifact /path/to/provenance/run_acolite_vombsjon_executed_ancillary_true.slurm \
  --require-closure
```

Both evidence documents must be prepared from facts that were actually
observed. Neither may be populated from general knowledge, from this protocol,
or from what would make a gate pass.
