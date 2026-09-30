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

Closure succeeds only when **all seven gates PASS**. Then:

```
gate_closure_complete        = true
performance_execution_eligible = true
```

Otherwise both are `false`.

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

**Gate 2 — product provenance.** From the committed v1.2 audit: audit version
is v1.2; the manifest, L1C/L2A/ACOLITE inventories, pairing audit and
extraction-failure audit all exist; the manifest records 1509 L1C, 1510 L2A,
1505 ACOLITE, 1466 exact-unique pairs and 48 failure rows; every recorded
freeze cross-check agrees. The manifest's own SHA256 is recorded, so the gate
is anchored to bytes rather than to filenames.

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

**Gate 5 — ACOLITE identity and settings.** Three things are kept apart:

- **A. stable source-code identity** — the Git commit. Verified only from
  *observed* evidence: `--acolite-source-root` and `--wrapper-root` are
  inspected read-only for `git rev-parse HEAD` and `git status --porcelain`.
  **A commit declared by the freeze is not observed evidence**; without an
  observation the gate is BLOCKED. A dirty worktree is recorded explicitly and
  blocks: arbitrary local modifications are not assumed harmless.
- **B. effective run settings** — verified per scene from the committed audit:
  `ancillary_data=True`, `s2_target_res=20`, `l2r_export_geotiff=True`,
  `l2w_export_geotiff=True`. The freeze's own `ancillary_data` requirement is
  read from the freeze rather than restated.
- **C. textual version metadata** — recorded, never used as identity (§6).

If effective settings verify but stable source identity cannot be observed, the
gate remains **BLOCKED**.

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
field source manifest, TIMESAT snapshot and external-input evidence paths with
SHA256s, `required_gate_ids` read from the freeze, all seven gate records with
their details, the observed ACOLITE and wrapper Git records, the TIMESAT
runtime validation, `n_pass`/`n_fail`/`n_blocked`, `gate_closure_complete`,
`performance_execution_eligible`, `performance_execution_authorized = false`,
the unresolved/blocking evidence list, scope assertions, and `payload_sha256`
over the canonical payload.

**Repository state is captured before any output file is created.** The earlier
satellite audit queried `git status` *after* writing its outputs, so its own new
files made the worktree look dirty in its own manifest. This protocol captures
commit and cleanliness first and records
`repository_state_captured_before_writing_outputs: true`. A final 7/7 PASS
artifact should be produced from a clean starting repository; if the tree is
already dirty at process start, that is recorded plainly rather than hidden.

## 10. Current evaluation against committed evidence

Run on the committed repository with no supplied source roots and no TIMESAT
probe, the outcome is **4/7 PASS, 0 FAIL, 3 BLOCKED**:

- gates 2, 3, 4 and 7 **PASS** from the committed v1.2 audit alone;
- gate 1 is **BLOCKED**: three of four committed field sources record no
  established licence, and no content SHA256 exists for any external satellite
  archive;
- gate 5 is **BLOCKED**: effective settings verify on all 1505 scenes, but
  stable ACOLITE and wrapper source identity has not been independently
  observed;
- gate 6 is **BLOCKED**: the registered TIMESAT runtime is not available here.

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

## 12. Running it

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
clean repository:

```
python scripts/42_vombsjon_execution_gate_preflight.py \
  --acolite-source-root /path/to/s2-inlandwater-ac/.external/acolite \
  --wrapper-root /path/to/s2-inlandwater-ac \
  --external-input-evidence path/to/vombsjon_external_input_evidence.json \
  --require-closure
```
