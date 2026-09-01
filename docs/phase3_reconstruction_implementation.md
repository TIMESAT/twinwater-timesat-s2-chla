# Phase 3 reconstruction implementation

## Authority and scope

Phase 3 implements the scientific rules in
`Reconstruction_Analysis_Contract_v1.0.1.md` under the project scope in
`Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md`. Their exact
SHA256 values are frozen in
`config/reconstruction_analysis_contract_v1.0.1.json`; loading the contract
fails if either file is absent or changed. The implementation-task document is
also retained verbatim under `docs/`.

This delivery stops at implementation and pre-performance validation. It does
not contain an Erken method comparison, ranking, performance figure, Vombsjön
result, or performance-driven parameter choice.

## Contract-to-code map

| Frozen rule | Implementation | Validation |
|---|---|---|
| Sections 2 and 3: 2019–2025, seven outer folds, six inner years, and 288 authoritative actual-mask dates | `phase3_contract.py` fixes the years and folds. `reconstruction_support.py` audits the existing Phase 2B-1 candidate field and refuses to regenerate it. | `test_phase3_contract.py` checks the exact folds, total and annual sparse counts, and rejection of a changed source flag. |
| Section 3: method-independent common support and no extrapolation | `reconstruction_support.py` constructs `open_water ∩ [first sparse,last sparse]`, labels physical open-water segments, and defines withheld evaluation dates. | Boundary/day/segment counts for every real year and outside-domain exclusions are tested. Artificial-mask boundary preservation is checked in unit tests and the preflight manifest. |
| Section 4: exactly linear, TIMESAT double logistic, and TIMESAT smoothing spline | `timesat_adapter.py` implements fixed in-boundary linear interpolation and a checked external TIMESAT interface. `reconstruction_benchmark.py` sends an identical date/value table to all methods. | Adapter tests check no extrapolation, the exact method set, and the cross-method sparse-input checksum. |
| Section 4.2: frozen unmodified effective double-logistic defaults | `config/timesat_double_logistic_defaults_v4.4.1.json` records package versions, source commits, source/build hashes, every source default, every effective runtime value, and a self-checksum. `timesat_adapter.py` compares the active runtime before each request and fails on mismatch. | Snapshot self-validation, external runtime validation, and synthetic double-logistic/spline smoke tests are required by the preflight CLI. Only supplied sparse data enter the core request. |
| Sections 4.3 and 5: exact spline grid and nested year-blocked selection | `spline_selection.py` drops the outer year before any reconstruction or metric call, evaluates every grid value separately in six training years, averages six year-level withheld-date nRMSE values equally, invalidates a candidate after any failed year, and breaks exact ties toward smaller smoothing. | Tests cover grid rejection, outer-reference mutation, equal weighting, tie handling, candidate-year failure, all-candidate failure, and the prohibition on seasonal tuning metrics. |
| Section 6: point-wise dates and bias/MAE/RMSE/nRMSE | `reconstruction_metrics.py` uses only common-support, open-water, finite-reference, non-sparse dates. The denominator is the common-support reference `Q95-Q05` using NumPy's documented `linear` quantile method. Missing predictions and invalid scales remain explicit. | Tests verify eligibility, complete required support, exact denominator use, and no epsilon stabilization. |
| Sections 7 and 8: method-independent seasonal metrics and peak reliability | `reconstruction_metrics.py` applies one definition to all methods: global common-support maximum, contiguous-plateau midpoint, non-contiguous equal-maximum ambiguity, boundary flags, peak magnitude, segment-wise trapezoidal integral, Pearson correlation, and 5/10/15-day flags. | Tests cover plateau midpoint, ambiguity, boundary status, disconnected integration, and the frozen timing thresholds. No onset/end or secondary-event detector exists. |
| Section 9: failures and implausibility | `ReconstructionResult`, `evaluate_method_result`, and metric status/reason columns preserve missing/non-finite results and TIMESAT diagnostics. Negative values are counted and retained without clipping. | Tests confirm negative retention, unavailable metric reasons, and failed-method rows. |
| Section 10.2: random deletion | `controlled_gaps.py` uses the exact rounding rule, seed formula, `Generator(PCG64(seed))`, no-replacement sampling of sorted interior dates, protected endpoints, and all 100 replicates at 10/20/30/50%. | Tests check formulas, determinism, ordering, endpoint protection, lack of `A_gap`, and the real total of 2,800 manifests. |
| Sections 10.3–10.5: exhaustive consecutive gaps and `A_gap` | `controlled_gaps.py` slides every 10/20/30/45-day daily window within one physical support segment, excludes endpoint deletion and zero-removal cases, and records all frozen position/activity fields. `A_gap` includes only internal transitions and uses the yearly scale. | Tests cover exact durations, discontinuities, endpoints, zero-removal exclusion, internal-transition arithmetic, invalid scale, and the real total of 5,746 windows. |
| Section 10.6: no per-gap spline retuning | Controlled-gap manifests are configuration-only in this task. The actual-mask outer-fold selection is the sole implemented source for a future controlled-gap smoothing setting. | No controlled-gap performance execution is exposed by the preflight CLI. |
| Sections 11–13: reliability products and provenance | Preflight CSVs retain mask identifiers, dates, counts, density/gap diagnostics, position/activity fields, years, seeds and RNG metadata. `phase3_benchmark.py` is ready to retain code/input/TIMESAT checksums, folds, selected smoothing, statuses, curves, residuals, and year-method metrics. | Deterministic table hashes and an immutable manifest checksum are generated. No inferential reliability model or universal threshold is introduced. |
| Section 14: twelve pre-performance gates | `phase3_preflight.py` and `scripts/08_erken_phase3_preflight.py` validate all gates and write deterministic CSV/JSON products without running Erken reconstructions. | The committed gate manifest records all twelve gates as passed and both performance booleans as false. |

## Frozen TIMESAT runtime

The frozen implementation uses:

- TIMESAT core `4.4.1`, source tag `v4.4.1`, commit
  `b20844140bf38543349552341212609fa18b24b1`;
- `timesat-cli` `1.9.2`, source tag `v1.9.2`, commit
  `258b50565b322d9f5bafd9df9b822c80ca09a847`;
- defaults-snapshot payload SHA256
  `175a8fec6ae4a05495f342d4f78b54f7d44561b9a3f7c47a379eef2dbfef447b`.

The project environment and compiled TIMESAT environment are deliberately
separate. Supply the latter interpreter with `--timesat-python` or
`TIMESAT_PYTHON`. The runtime gate checks package versions, Python-module
hashes, source defaults, effective parameters, and a registered same-platform
binary checksum when one is present. An unregistered build can be identified
by source/version checks, while a registered build with a different checksum
fails.

## Commands and execution boundary

Run implementation-only validation:

```bash
TIMESAT_PYTHON=/path/to/frozen/timesat/python \
  python scripts/08_erken_phase3_preflight.py
pytest
```

The preflight writes six deterministic tables and one JSON manifest under
`results/phase3/preflight/`. Current frozen counts are 2,420 master dates, 288
sparse inputs, seven folds, 2,800 random masks, and 5,746 eligible consecutive
windows.

`scripts/09_erken_phase3_benchmark.py` is the future actual-performance entry
point. It refuses to run unless `--execute-performance` is supplied, verifies
the stored manifest checksum, regenerates all gates against the current input
and TIMESAT runtime, and requires an exact manifest match before making the
first reconstruction call. It was not executed for this implementation task.
