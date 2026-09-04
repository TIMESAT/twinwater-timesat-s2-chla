# Phase 6A — Erken real Sentinel-2 L1C / official ESA L2A observation pilot

**Status of this namespace: implemented but not yet executed on real data.**

This directory is the isolated Phase 6A output namespace. Phase 3, 4 and 5
outputs are never written here and are never modified by this pilot; the
pipeline refuses to write outside `results/phase6a/`.

## Why this directory is empty of results

The real Sentinel-2 SAFE archive is on the Linux/HPC server, not on the
development machine where the pipeline was written. No L1C or L2A archive root
was reachable in that environment, so:

- **no real SAFE product was processed;**
- **no synthetic scientific output was generated;**
- the pipeline was exercised only with minimal controlled fixtures in
  `tests/phase6a_fixtures.py`, which live in pytest temporary directories and
  are never written here.

Running the pilot without an archive root prints an explicit `STOP:` and exits
without writing anything.

## Real-data run

On the Linux server, from
`/projects/eko/fs7/pers/ZC/Core/Github/twinwater-timesat-s2-chla`:

```bash
python scripts/26_erken_phase6a_real_s2_pilot.py \
  --l1c-root /path/to/Erken/L1C \
  --l2a-root /path/to/Erken/L2A \
  --output-root results/phase6a \
  --require-real-archive
```

The two archive roots are runtime inputs; they are never committed and never
appear in any output. `ERKEN_S2_L1C_ROOT` and `ERKEN_S2_L2A_ROOT` can be used
instead of the flags.

## What the real run will write here

| File | Content |
|---|---|
| `erken_l1c_l2a_pairing_audit.csv` | every frozen candidate date, including pairing failures |
| `qa/erken_l1c_l2a_native_qa_inventory.csv` | native QA assets actually present per product |
| `erken_real_s2_product_extraction_master.csv` | per-product reflectance/QA/index master |
| `erken_real_s2_date_observation_master.csv` | date-level L1C/L2A observation master |
| `qa/erken_real_s2_qa_attrition.csv` | QA-only attrition at 9/9, ≥8/9, ≥6/9, ≥5/9 |
| `qa/erken_real_s2_qa_attrition_annual.csv` | the same attrition by year |
| `qa/erken_real_s2_baseline_platform_qa_audit.csv` | attrition by processing baseline and platform |
| `erken_real_s2_pilot_provenance.json` | portable provenance manifest |
| `erken_real_s2_pilot_failures.csv` | explicit failure/run audit |

## Stopping rule

The first real-data run stops after these QA/availability outputs. It does not
inspect CHLF, does not compute index-versus-field performance, does not rank
L1C against L2A, and does not run TIMESAT. The human must review the attrition
evidence and freeze the final minimum valid-pixel threshold before any
field-matchup analysis begins.

Governance: `docs/Erken_Real_S2_L1C_L2A_Observation_Pilot_Protocol_v1.0.md`
(DRAFT) and `config/erken_real_s2_l1c_l2a_observation_pilot_v1.0.yaml` (DRAFT).
