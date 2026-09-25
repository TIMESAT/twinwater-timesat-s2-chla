# Vombsjön raw satellite/product and matchup audit protocol v1.2

**Status: implemented, not yet executed on the corrected ACOLITE archive.**

**Classification: external execution and provenance correction. This is NOT a
scientific amendment.**

**Scientific authority is unchanged.** v1.2 inherits every scientific rule from
[`Vombsjon_Satellite_Input_Audit_Protocol_v1.1.md`](Vombsjon_Satellite_Input_Audit_Protocol_v1.1.md),
which remains the substantive protocol and is preserved unchanged. Read it for
the audit's actual content; this note records only what v1.2 changes and why.

**Executable configuration:** [`config/vombsjon_satellite_input_audit_v1.2.yaml`](../config/vombsjon_satellite_input_audit_v1.2.yaml).

**Governing freeze:** [`config/erken_vomb_transfer_freeze_v1.1.json`](../config/erken_vomb_transfer_freeze_v1.1.json),
**unchanged**. No frozen value was rewritten for v1.2.

**Predecessor:** [`config/vombsjon_satellite_input_audit_v1.1.yaml`](../config/vombsjon_satellite_input_audit_v1.1.yaml)
and its committed outputs under
[`results/vombsjon/satellite_input_audit/v1.1/`](../results/vombsjon/satellite_input_audit/v1.1/),
both preserved as immutable historical provenance.

## 1. What changed

Nothing in the science. One thing in the external input.

The Vombsjön ACOLITE archive that v1.1 audited had been produced with
`ancillary_data=False`, while `config/erken_vomb_transfer_freeze_v1.1.json`
already required `ancillary_data=True`. The external processing therefore did
not conform to a freeze that predated it. The archive has been reprocessed on
the HPC server from the **same** frozen ACOLITE source commit
`64a02ff386e2985eef68ae00198b38e04f3c4a1f`, with:

| Setting | v1.1 archive | v1.2 archive | Freeze requires |
|---|---|---|---|
| `ancillary_data` | `False` | **`True`** | `True` |
| `s2_target_res` | 20 | 20 | 20 |
| `polygon_clip` | true | true | true |
| ACOLITE source commit | `64a02ff3…` | `64a02ff3…` | `64a02ff3…` |

The correction brings the *execution* into conformance with the existing
freeze. It does not alter the freeze, and no frozen value was relaxed to
accommodate the old archive.

## 2. What did not change

Byte-identical between the v1.1 and v1.2 configurations: `field_source`,
`fixed_target`, `field_polygon`, `field_gps_sensitivity`, `products`, `grid`,
`radiometry`, `native_qa`, `pairing`, `acolite`, `indices`, `observation`,
`same_day` and `field_matchup`.

Concretely, all of these are unchanged: MCI and its wavelengths, the fixed
nominal-station 3×3 temporal reconstruction target and its 6-of-9 rule, the
fixed pelagic polygon and its two-thirds fractional support rule, the SAFE
native-QA classification, the ACOLITE flag layout and hard-invalid set,
same-day reduction, the field matchup logic, and the ACOLITE/L2A/L1C processor
roles.

Only `audit_version`, `status`, the `amendment` block, the new
`execution_correction` block, the protocol pointer, `outputs.root` and one
added protected prefix differ.

## 3. Governance boundary

- **No Vombsjön performance was inspected before this correction.** No
  reconstruction, withheld-observation analysis, reconstruction metric,
  regression, correlation or processor selection informed it.
- **No scientific parameter was selected or changed.** The correction was
  forced by a pre-existing frozen requirement, not chosen from any result.
- v1.1 is **preserved**, remains loadable as historical provenance, and its
  outputs remain immutable. A v1.2 run cannot write into the v1.1 namespace:
  each audit version is pinned to one output root in code, and
  `results/vombsjon/satellite_input_audit/v1.1` is additionally listed as a
  protected prefix.
- v1.0 remains preserved and non-executable.

## 4. ACOLITE version-string nuance

ACOLITE reports a version string such as
`Generic GitHub Clone c2026-08-19T22:04:44`. The `cYYYY-MM-DDTHH:MM:SS`
timestamp is generated from the **local `.git/HEAD` filesystem mtime of the
checkout**, not from the Git commit identity. Two checkouts of the same commit
therefore print different strings, and the reprocessed archive prints a
different timestamp from the one recorded in the freeze.

**The Git commit is the stable source identity; the `c…` timestamp is
environment and checkout metadata.** The freeze's
`acolite_version_string` is therefore **deliberately not rewritten** to match
the new checkout, and a differing timestamp is not evidence of a different
ACOLITE source. The stable identity, `64a02ff386e2985eef68ae00198b38e04f3c4a1f`,
is unchanged and is what the execution-gate closure should check.

The audit records whatever the run files actually declare and reports anything
undeclared as `not_verifiable_from_supplied_files`; it does not assert that the
observed version string equals the frozen one.

## 5. Expected archive properties

Operator-reported for the reprocessed archive, recorded in the v1.2
configuration as reported values and **re-derived independently by the audit
run**:

- 1,509 product directories;
- 1,509 settings files declaring `ancillary_data=True`;
- 1,505 scenes with `L2R rhos` GeoTIFFs;
- 1,505 scenes with `L2W l2_flags`;
- 4 scenes without GeoTIFF outputs.

Those same four scenes lacked GeoTIFF outputs in the v1.1 archive, so the gap
predates the reprocessing and is not caused by `ancillary_data=True`. The audit
records them as explicit unavailabilities and never substitutes NetCDF or
another processor.

These figures are operator-reported and are not verified from this repository
until the v1.2 run writes its own inventory.

## 6. Outputs

`results/vombsjon/satellite_input_audit/v1.2/`, with the same 15 products as
v1.1 (see the v1.1 protocol, §11). The v1.2 manifest additionally records the
`execution_correction` block, names v1.1 as its superseded predecessor, and
carries the audit-version registry.

## 7. Running it

```
python scripts/41_vombsjon_satellite_input_audit.py \
  --config config/vombsjon_satellite_input_audit_v1.2.yaml \
  --l1c-root /projects/eko/fs7/pers/ZC/TWIN_water/S2L1C/T33UVB \
  --l2a-root /projects/eko/fs7/pers/ZC/TWIN_water/S2L2A/T33UVB \
  --acolite-root /projects/eko/fs7/pers/ZC/TWIN_water/ACOLITE_VOMBSJON \
  --output-root results/vombsjon/satellite_input_audit/v1.2 \
  --require-real-archive
```

`--config` and `--output-root` may both be omitted: v1.2 is the default
configuration and each configuration declares its own output root.

## 8. Next gate

Unchanged from v1.1 §13. This audit is an input audit; completing it does not
authorize performance execution. The next stage is the locked-transfer
preflight and execution-gate closure, which should now verify the ACOLITE
identity against the **Git commit** rather than the version-string timestamp,
and confirm `ancillary_data=True` in the audited archive. No regression,
correlation, ranking or performance model is fitted by this audit.
