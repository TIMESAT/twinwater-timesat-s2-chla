# Figure 1 - Study design and evidence structure

**Figure 1. Study design and evidence structure.** (a) Erken's dense CHLF reference (2019-2025) supports a same-variable temporal reconstruction test under the actual Sentinel-2 observation mask and additional controlled random deletion or consecutive calendar-day deletion windows. This masking experiment does not independently validate satellite retrieval accuracy. Vombsjön (2017-2026) instead uses withheld QC-passed Sentinel-2 MCI observations as its primary quantitative reconstruction target. ACOLITE is the primary aquatic atmospheric-correction product; official L2A is a separate sensitivity and L1C TOA a diagnostic baseline, each on its own observation calendar. ACOLITE support in 2026 ends on 3 August. Sparse field Chl-a provides complementary exact-calendar-date fixed-polygon proxy-consistency evidence only; no valid same-day fixed-polygon pair exists in 2018 for any processor. (b) Erken evaluation precedes the frozen reconstruction design and locked Vombsjön transfer. Linear interpolation is the untuned baseline, default TIMESAT double logistic is the frozen benchmark (p_seapar=1), and TIMESAT smoothing spline uses the final Erken-selected transfer setting p_smooth=10. This final transfer setting was derived from the all-Erken frozen score, separately from the spline settings selected within individual Erken outer folds. CV double logistic (p_seapar=0) remains a separate sensitivity. No Vombsjön performance or field data were used to choose the transferred settings, and the transfer execution performed no retuning. (c) Primary quantitative reconstruction evidence is distinguished from secondary controlled-gap and conditionally identifiable observed-proxy peak-timing evidence, separate sensitivity/diagnostic evidence, and complementary/descriptive field consistency. The Vombsjön peak reference is the maximum of the available QC-passed observed MCI series within the fixed year support, not the true ecological bloom peak; ±10 days is the primary tolerance and ±5/±15 days are sensitivities. Field Chl-a is not daily reconstruction truth.

## Reproduction and scope

Run `python scripts/49_plot_study_design_evidence_structure.py` with Python >=3.11 and matplotlib >=3.7. The script uses committed blobs and verifies local bytes against eleven pinned source hashes. It performs metadata assertions and renders a conceptual vector schematic; it does not compute performance metrics or run any reconstruction. No CSV is required because the figure contains no quantitative result display.

Evidence-source commit: `579cc0951a53542769b22d24cfc4b764e7f0399c`. Dimensions: 7.48 x 5.60 inches; PNG: 600 dpi; vector PDF with embedded DejaVu Sans. All scientific source files remain unchanged.

## Scientific sources inspected

| Source | SHA256 |
| --- | --- |
| [docs/Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md](../../docs/Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md) | `bf2e06423ef256380e0446eef1f8a643347da722550906e5dd7732f6adcc7489` |
| [docs/Reconstruction_Analysis_Contract_v1.0.1.md](../../docs/Reconstruction_Analysis_Contract_v1.0.1.md) | `7a111b6e806d1914233481d7cb9bf99459bc74193330b5139c18257bd905046e` |
| [docs/RSE_Manuscript_Results_Synthesis_v1.0.md](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md) | `68a6269a05aad7979e386edb86bd023ec95f70fd89550e062df6dc4c520ee0cf` |
| [docs/Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md](../../docs/Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md) | `05295442489cb7775f183c99e58d9ab745e5bd8168d180c920e75e540b166861` |
| [docs/Vombsjon_Locked_Transfer_Execution_v1.0.md](../../docs/Vombsjon_Locked_Transfer_Execution_v1.0.md) | `87e9dadb7915b9c2a28e671467c82e5495b91bc2582ebbc17665fdaad59cdc61` |
| [config/erken_vomb_transfer_freeze_v1.1.json](../../config/erken_vomb_transfer_freeze_v1.1.json) | `477cb4890daa07073cc55c24a66150dd63a9cdf9b9c949756b08c01215dc0983` |
| [results/reliability_synthesis/v1.0.1/erken_reliability_report_v1.0.1.md](../../results/reliability_synthesis/v1.0.1/erken_reliability_report_v1.0.1.md) | `516f80fd0f4666f942af255eb035b7b84b8473d627ff400b054af65b01067b90` |
| [results/reliability_synthesis/v1.0/erken_reliability_actual_mask_year_method.csv](../../results/reliability_synthesis/v1.0/erken_reliability_actual_mask_year_method.csv) | `a09cfd20d60e74bfcbb2d90f2389420c0b1f4f6d4176a40e1b252b0c72d2fe9a` |
| [results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_manifest.json](../../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_manifest.json) | `d016221d4a6071536c3b17add5a6414e1f876872734d5cf352c7abb395b33652` |
| [results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_year_eligibility.csv](../../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_year_eligibility.csv) | `e0ccbb80786e3c9cc35f72d3e6fcb377e1f226b84c4addbab119dcda49ff01ba` |
| [results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_field_consistency.csv](../../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_field_consistency.csv) | `dce1779ce9d254bfc5c47e6d2a8384062fca04125bcc6f41e91bf6cdf65829c9` |

## Exact statements and evidence mapping

### Panel (a)

- ‘2019-2025’; ‘Dense CHLF / reference’. Erken dense CHLF reference and seven saved actual-mask years, 2019-2025. Sources: [Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md](../../docs/Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md), [Reconstruction_Analysis_Contract_v1.0.1.md](../../docs/Reconstruction_Analysis_Contract_v1.0.1.md), [erken_reliability_actual_mask_year_method.csv](../../results/reliability_synthesis/v1.0/erken_reliability_actual_mask_year_method.csv).
- ‘Actual Sentinel-2 / observation mask /  / Controlled gaps: / random deletion; / consecutive / calendar-day / windows’; ‘Reconstruction vs / withheld dense / CHLF reference’; ‘Same-variable / temporal evaluation’. Same-variable reconstruction experiment: actual Sentinel-2 timing masks CHLF; additional random deletion and consecutive calendar-day windows are controlled missingness experiments. Sources: [Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md](../../docs/Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md), [Reconstruction_Analysis_Contract_v1.0.1.md](../../docs/Reconstruction_Analysis_Contract_v1.0.1.md), [RSE_Manuscript_Results_Synthesis_v1.0.md](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md), [erken_reliability_report_v1.0.1.md](../../results/reliability_synthesis/v1.0.1/erken_reliability_report_v1.0.1.md).
- ‘2017-2026’; ‘Sentinel-2 MCI’; ‘Withhold observed / acquisitions: / isolated or blocks’; ‘Reconstruction vs / withheld observed / MCI’. 2017-2026 observed MCI; primary validation withholds isolated or consecutive observed acquisitions (not consecutive calendar days). Sources: [erken_vomb_transfer_freeze_v1.1.json](../../config/erken_vomb_transfer_freeze_v1.1.json), [Vombsjon_Locked_Transfer_Execution_v1.0.md](../../docs/Vombsjon_Locked_Transfer_Execution_v1.0.md), [vombsjon_transfer_year_eligibility.csv](../../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_year_eligibility.csv), [RSE_Manuscript_Results_Synthesis_v1.0.md](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md).
- ‘ACOLITE: primary / aquatic correction’; ‘Official L2A: sensitivity / L1C TOA: diagnostic’. ACOLITE primary aquatic atmospheric correction; official L2A separate sensitivity; L1C TOA diagnostic baseline. Sources: [erken_vomb_transfer_freeze_v1.1.json](../../config/erken_vomb_transfer_freeze_v1.1.json), [Vombsjon_Locked_Transfer_Execution_v1.0.md](../../docs/Vombsjon_Locked_Transfer_Execution_v1.0.md), [RSE_Manuscript_Results_Synthesis_v1.0.md](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md).
- ‘2026: partial support / to 3 Aug (ACOLITE)’. ACOLITE 2026 support ends 3 August; saved observed support is 10 January to 3 August. Sources: [vombsjon_transfer_year_eligibility.csv](../../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_year_eligibility.csv), [RSE_Manuscript_Results_Synthesis_v1.0.md](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md).
- ‘Sparse field Chl-a / Exact-date proxy / consistency only’; ‘2018: no valid same-day fixed-polygon field pair’. Sparse field Chl-a provides complementary exact-calendar-date fixed-polygon proxy consistency; no valid 2018 pair for any processor. Sources: [erken_vomb_transfer_freeze_v1.1.json](../../config/erken_vomb_transfer_freeze_v1.1.json), [vombsjon_transfer_field_consistency.csv](../../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_field_consistency.csv), [RSE_Manuscript_Results_Synthesis_v1.0.md](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md).

### Panel (b)

- ‘Erken evaluation / Year-blocked selection’; ‘Frozen reconstruction design’; ‘Before Vomb performance’. Erken year-blocked evaluation precedes the final Erken-only freeze and Vombsjön performance inspection. Sources: [Reconstruction_Analysis_Contract_v1.0.1.md](../../docs/Reconstruction_Analysis_Contract_v1.0.1.md), [Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md](../../docs/Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md), [erken_vomb_transfer_freeze_v1.1.json](../../config/erken_vomb_transfer_freeze_v1.1.json).
- ‘Locked transfer: Vombsjön / No retuning / No field data used for tuning’. Locked Vombsjön transfer used no parameter tuning and no field data for tuning. Sources: [erken_vomb_transfer_freeze_v1.1.json](../../config/erken_vomb_transfer_freeze_v1.1.json), [Vombsjon_Locked_Transfer_Execution_v1.0.md](../../docs/Vombsjon_Locked_Transfer_Execution_v1.0.md), [vombsjon_transfer_manifest.json](../../results/vombsjon/locked_transfer/v1.0/vombsjon_transfer_manifest.json).
- ‘CV double logistic: sensitivity only / p_seapar = 0’. CV double logistic p_seapar=0 is a separately reported sensitivity, not a replacement for the frozen default primary benchmark. Sources: [erken_vomb_transfer_freeze_v1.1.json](../../config/erken_vomb_transfer_freeze_v1.1.json), [Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md](../../docs/Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md), [erken_reliability_report_v1.0.1.md](../../results/reliability_synthesis/v1.0.1/erken_reliability_report_v1.0.1.md).
- ‘Linear interpolation’ / ‘Untuned baseline’. Sources: [freeze v1.1](../../config/erken_vomb_transfer_freeze_v1.1.json), [freeze protocol](../../docs/Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md).
- ‘TIMESAT double logistic’ / ‘Frozen default benchmark’. Sources: [freeze v1.1](../../config/erken_vomb_transfer_freeze_v1.1.json), [freeze protocol](../../docs/Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md).
- ‘TIMESAT smoothing spline’ / ‘Erken-selected p_smooth = 10’. Sources: [freeze v1.1](../../config/erken_vomb_transfer_freeze_v1.1.json), [freeze protocol](../../docs/Erken_Vomb_Transfer_Freeze_Protocol_v1.0.md).
- The freeze is the final transfer design, not a claim that every Erken outer fold used p_smooth=10. The three method markers retain the established blue circle, orange square, and green triangle, in frozen primary order.

### Panel (c)

- ‘Erken actual mask vs / withheld CHLF / Vombsjön ACOLITE vs / withheld observed MCI’. Primary quantitative targets: withheld dense-reference CHLF under the Erken actual mask, and withheld observed MCI from Vombsjön ACOLITE. Sources: [RSE_Manuscript_Results_Synthesis_v1.0.md](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md), [Reconstruction_Analysis_Contract_v1.0.1.md](../../docs/Reconstruction_Analysis_Contract_v1.0.1.md), [erken_vomb_transfer_freeze_v1.1.json](../../config/erken_vomb_transfer_freeze_v1.1.json).
- ‘Erken controlled gaps / Vombsjön observed-proxy / peak timing (conditional)’. Secondary quantitative evidence: Erken controlled gaps and conditionally identifiable Vombsjön observed-proxy peak timing. Sources: [RSE_Manuscript_Results_Synthesis_v1.0.md](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md), [Reconstruction_Analysis_Contract_v1.0.1.md](../../docs/Reconstruction_Analysis_Contract_v1.0.1.md), [erken_vomb_transfer_freeze_v1.1.json](../../config/erken_vomb_transfer_freeze_v1.1.json).
- ‘Official L2A sensitivity / L1C TOA diagnostic / CV-DL sensitivity / ±5 / ±15-day peak tolerances’. Separate L2A and CV-DL sensitivities, L1C diagnostic baseline, and ±5/±15-day peak-tolerance sensitivities. Sources: [RSE_Manuscript_Results_Synthesis_v1.0.md](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md), [erken_vomb_transfer_freeze_v1.1.json](../../config/erken_vomb_transfer_freeze_v1.1.json).
- ‘Field Chl-a: exact-date / proxy consistency / No daily reconstruction truth’; ‘Processor calendars / remain independent’. Exact-date field Chl-a proxy consistency is complementary/descriptive, not daily reconstruction truth; processors retain their own calendars. Sources: [RSE_Manuscript_Results_Synthesis_v1.0.md](../../docs/RSE_Manuscript_Results_Synthesis_v1.0.md), [erken_vomb_transfer_freeze_v1.1.json](../../config/erken_vomb_transfer_freeze_v1.1.json), [Vombsjon_Locked_Transfer_Execution_v1.0.md](../../docs/Vombsjon_Locked_Transfer_Execution_v1.0.md).

## Role and verification details

- The hierarchy follows the manuscript synthesis: Erken actual-mask and Vombsjön ACOLITE withheld-MCI comparisons are primary quantitative evidence; Erken controlled gaps and conditionally identifiable observed-MCI peak timing are secondary quantitative evidence.
- Official L2A, CV-DL, and peak tolerances are separately labelled sensitivities. L1C is diagnostic. The shared sensitivity/diagnostic box groups reporting roles without pooling processors or comparing their performance.
- Field Chl-a is complementary/descriptive proxy-consistency evidence at exact calendar dates. Fixed-polygon field support differs from the nominal-station temporal reconstruction target; exact-date matching does not establish the acquisition-minus-sampling time interval or vertical equivalence.
- Assertions verify all seven Erken actual-mask years, all ten eligible ACOLITE transfer years, the primary method order/roles and final spline parameter, processor roles, observed-acquisition holdout units, field rules and tuning flags, and observed-peak role/tolerances.
- All 18 saved 2018 field-date-by-processor records are unavailable pairs (six field dates for each processor). ACOLITE 2026 metadata records support from 2026-01-10 to 2026-08-03. These are availability checks, not new scientific analyses.

## Claims intentionally not made

- Independent retrieval validation from the Erken masking experiment; a universally best reconstruction method; or independently verified denoising.
- Absolute Chl-a from MCI; daily Vombsjön field truth; field validation of reconstructed daily trajectories, unobserved ecological peaks, onset/end, or integral accuracy.
- ACOLITE superiority, shared/pooled processor calendars, or a matched-calendar Vombsjön processor ranking.
- Equivalence between consecutive observed-acquisition blocks and consecutive calendar-day gaps; full annual ACOLITE coverage in 2026; or valid contemporaneous polygon field validation in 2018.
- New performance estimates, uncertainty intervals, statistical significance, or thresholds.

## Visual inspection notes

- Automatic rendering checks passed for 39 text objects: all text stays inside the canvas, boxed text stays within its assigned box with inset margins, and text bounding boxes do not overlap.
- The final PNG was visually reviewed at full page width and reduced manuscript size, and the exported PDF was independently rendered for review. Text, markers, and arrowheads are legible, with no clipping or overlap.
- Downward arrows connect only temporal observation/evaluation chains and the Erken-to-freeze-to-transfer sequence. The isolated field and CV-DL boxes have no arrows into method fitting or selection. Lake colors encode lake roles; method colors appear only on explicit method markers. Evidence-box emphasis encodes the planned evidence hierarchy, not processor performance.
- The 2018 limitation and 2026 support note fit in the schematic. Detailed peak-reference, spatial/vertical representativeness, and final-versus-outer-fold spline qualifications are in the caption/report to keep the graphic compact. No requested scientific statement was omitted because it could not be verified.

## Output SHA256

| Output | SHA256 |
| --- | --- |
| [figure_01_study_design_evidence_structure.pdf](figure_01_study_design_evidence_structure.pdf) | `4727cb1f356adc5edc18bbecea6d17b4e4c9cd06265186ba5c350c108a56ec78` |
| [figure_01_study_design_evidence_structure.png](figure_01_study_design_evidence_structure.png) | `486820caf2bbdc7e9da31a87e98f983b12a19001f5da28a8917bb4d06c1a39d1` |

The report's own hash is not embedded in itself. Only the Figure 1 script and PDF/PNG/Markdown production files are changed.
