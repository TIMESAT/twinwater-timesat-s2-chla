# TIMESAT × Sentinel-2 × chlorophyll reconstruction

This repository supports a two-lake *Remote Sensing of Environment*-oriented
project on the metric-specific reliability of seasonal chlorophyll-sensitive
time-series reconstruction under incomplete Sentinel-2 sampling.

The repository currently contains a completed **Lake Erken** evidence package
and manuscript draft. The broader active plan also requires a final
reliability synthesis, a second Erken-only freeze, and locked transfer
validation in **Lake Vombsjön**. Those stages have not been completed.

## Start here

| Need | Entry point |
|---|---|
| Working rules and reading order | [`AGENTS.md`](AGENTS.md) |
| Single active scientific plan | [`docs/Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md`](docs/Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md) |
| Current completed/pending/verification status | [`docs/STATUS.md`](docs/STATUS.md) |
| Data, evidence, and external-file boundaries | [`docs/DATA_INVENTORY.md`](docs/DATA_INVENTORY.md) |
| Frozen primary reconstruction rules | [`docs/Reconstruction_Analysis_Contract_v1.0.1.md`](docs/Reconstruction_Analysis_Contract_v1.0.1.md) |
| Accepted decisions | [`docs/decisions.md`](docs/decisions.md) |
| Concise study architecture | [`docs/experiment_design.md`](docs/experiment_design.md) |
| Current Erken manuscript | [`manuscript/README.md`](manuscript/README.md) |

The Project Master is the only active project plan. `docs/STATUS.md` is the
progress ledger; README files and historical phase labels are not planning
authorities.

## Current evidence boundary

Completed Erken work includes:

- strict reference-data QC and open-water characterization;
- Sentinel-2 SCL inventory, spatial support, frozen date mask, and temporal
  join;
- the seven-year actual-mask reconstruction benchmark for linear
  interpolation, TIMESAT double logistic, and TIMESAT smoothing spline;
- 2,800 random-deletion masks and 5,746 consecutive-gap windows;
- secondary event recovery and double-logistic `p_seapar` sensitivity;
- real L1C, official L2A, and ACOLITE observation extraction and frozen
  observation selection;
- exact-date Erken NDCI/MCI–CHLF analysis and processing-baseline audit; and
- a verified Erken-only Markdown/DOCX manuscript package.

The active master still requires:

1. an empirical, metric-specific reliability synthesis with year-aware
   uncertainty;
2. a dated second freeze of the Erken-supported transfer workflow;
3. a governed Vombsjön raw satellite/matchup audit; and
4. locked Vombsjön transfer validation without retuning.

See [`docs/STATUS.md`](docs/STATUS.md) for the evidence behind each state and
for unresolved external-data questions.

## Scientific boundaries

- Erken is the dense/high-frequency temporal-reference development site. Its
  CHLF record is not literal daily Sentinel-2 surface Chl-*a* truth.
- Vombsjön is reserved for locked out-of-domain transfer and extreme-regime
  stress testing. Its results must not be used to retune Erken-derived rules.
- Field reference, observed satellite proxy, and reconstructed daily estimate
  remain separate layers.
- The primary benchmark is linear interpolation, TIMESAT double logistic, and
  TIMESAT smoothing spline. Seasonal metrics and evaluation support are
  method-independent.
- The current manuscript reports Erken only. It must not be described as a
  completed two-lake transfer study.

## ChatGPT Project handoff

Repository: [TIMESAT/twinwater-timesat-s2-chla](https://github.com/TIMESAT/twinwater-timesat-s2-chla)

For a ChatGPT Project, use the repository as the shared code/evidence source
and begin with `AGENTS.md`. The minimum active reading set is the Project
Master, `docs/STATUS.md`, the Reconstruction Contract, `docs/decisions.md`,
`docs/DATA_INVENTORY.md`, and the manuscript README/source map. Do not upload
older masters or inventories as competing active instructions; keep external
Vombsjön files explicitly labelled external until their identity and
availability are verified.

## Environment and verification

Python 3.11 or newer is required.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest
```

The TIMESAT analyses use a separately managed frozen runtime containing
`timesat==4.4.1` and `timesat-cli==1.9.2`. External-runtime tests are skipped
unless that interpreter is supplied. Historical run commands and phase-level
stopping rules are documented beside their protocols and result namespaces;
do not rerun a frozen analysis merely to refresh documentation.

The current manuscript can be audited without rerunning scientific analyses:

```bash
python scripts/32_validate_manuscript.py
```

## Data and outputs

The raw SITES Erken CSV and Sentinel-2/ACOLITE archives are external runtime
inputs and are not committed. Small canonical processed data, derived tables,
figures, frozen configurations, and provenance manifests are versioned in the
repository. See [`docs/DATA_INVENTORY.md`](docs/DATA_INVENTORY.md) for exact
roles and locations.

The Erken source dataset is provided by the Swedish Infrastructure for
Ecosystem Science (SITES), PID `11676.1/M1prtGTFmw9w1asYJ3xZDQM8`, under CC BY
4.0. Required acknowledgement:

> This study has been made possible by data provided by the Swedish
> Infrastructure for Ecosystem Science (SITES).

Repository code is covered by [`LICENSE`](LICENSE); external datasets retain
their own licences and attribution requirements.
