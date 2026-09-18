# Experiment design

This file is a concise orientation to the study architecture and its current
execution state. The sole active scientific plan is
[`Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md`](Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md),
the exact primary Erken rules are frozen in
[`Reconstruction_Analysis_Contract_v1.0.1.md`](Reconstruction_Analysis_Contract_v1.0.1.md),
and current progress is tracked only in [`STATUS.md`](STATUS.md).

## Scientific question

Which seasonal characteristics of chlorophyll-sensitive Sentinel-2 time
series can be reconstructed reliably under irregular observation and
cloud-gap conditions, under what gap conditions, and how well do those
conclusions transfer to a contrasting lake without retuning?

## Fixed two-lake architecture

**Lake Erken** is the dense/high-frequency temporal-reference development
domain. It supports realistic masking, year-blocked parameter selection,
controlled missingness, and reconstruction evaluation. Erken CHLF is a
pelagic temporal reference, not literal daily Sentinel-2 surface Chl-*a*
truth and not a transferable absolute Chl-*a* calibration.

**Lake Vombsjön** is the locked external-transfer and extreme-regime stress
test. Temporal methods, settings, masks, metrics, and tolerances must be frozen
from Erken-only evidence before Vombsjön performance is inspected. Vombsjön
must not be used to retune the confirmatory workflow.

## Data layers

1. **Field/reference layer:** Erken daily CHLF and, later, Vombsjön field
   Chl-*a*, each with its own spatial, depth, and measurement limitations.
2. **Observed satellite layer:** acquisition identity, QA, reflectance, NDCI,
   MCI, and usable observation dates. These are observed quantities/proxies,
   not reconstructed daily values.
3. **Reconstruction layer:** linear interpolation, TIMESAT double logistic,
   and TIMESAT smoothing-spline daily estimates. These are model outputs,
   never “daily satellite observations.”

Retrieval/observation uncertainty and temporal-reconstruction uncertainty are
evaluated separately before they are interpreted together.

## Frozen Erken benchmark

The primary benchmark uses exactly:

1. linear interpolation;
2. TIMESAT double logistic with frozen effective defaults; and
3. TIMESAT smoothing spline with the grid
   `{0, 1, 3, 10, 30, 100, 300, 1000}`.

All methods use the same 288 actual-mask sparse inputs and the same
method-independent common support. The seven outer folds are calendar years
2019–2025. Spline selection uses only the six outer-training years, with
equal-year mean withheld-date nRMSE; daily values are not treated as
independent ecological replicates.

The primary timing candidate is the common-support global peak date, with a
10-day reliability criterion and 5-/15-day sensitivities. Point-wise errors,
peak magnitude, trajectory agreement, and common-support integral remain
separate outcomes. Onset/end are not primary outputs.

Controlled experiments begin from the frozen actual-mask inputs. They add
10/20/30/50% random deletion or exhaustive internal 10/20/30/45-day gaps.
Consecutive gaps retain objective position, global-peak containment, and the
frozen continuous within-gap activity measure; the hidden reference is used
only to characterize validation gaps, never as model input.

## Validation sequence and current state

| Validation layer | Design | Current state |
|---|---|---|
| A. Lake-specific observation/proxy evidence | Exact-date observed Sentinel-2 proxy versus field reference, within lake | **Erken completed.** Vomb field sources are committed and audited; Vomb Sentinel-2 products and proxy matchups remain pending. |
| B. Pure temporal reconstruction in Erken | Mask daily CHLF at actual usable Sentinel-2 dates, reconstruct, and compare with withheld daily reference | **Completed** for the three primary methods. |
| C. Controlled missingness in Erken | Random deletion and exhaustive consecutive gaps, with year-aware interpretation | **Completed, including the versioned year-aware reliability synthesis.** |
| Supplementary event analysis | Frozen major-event detection and one-to-one matching | **Completed, secondary/exploratory.** It does not replace the primary global-peak metric. |
| Supplementary double-logistic sensitivity | Training-only LOYO selection of `p_seapar` | **Completed, secondary sensitivity.** It reached a hard human-review gate and is not a new primary result. |
| D. Locked Vombsjön transfer | Withheld Sentinel-2 as primary quantitative test; sparse field Chl-*a* as complementary ecological check | **Pending.** The second freeze and field-source audit are complete; the external satellite/product audit remains the execution gate. |

## Current interpretation boundary

The completed manuscript under [`manuscript/`](../manuscript/) reports the
Erken benchmark and observation-layer evidence. It does not report a Vombsjön
transfer. The Phase 4 and Phase 5 syntheses are descriptive and explicitly
stop before selecting a final inferential model, universal threshold, or
transfer workflow.

The reliability synthesis and Erken-only second transfer freeze are complete.
The supplied Vomb field sources are also committed and audited. The remaining
original-plan sequence is:

1. verify and audit the external Vomb Sentinel-2 and atmospheric-correction
   products and materialize the governed observation/matchup inventory;
2. execute the locked Vomb transfer without retuning; and
3. integrate the two-lake evidence and update the manuscript claims.

## Review-suggestion rule

Scientific review suggestions do not become project tasks automatically.
Compare them with the active master and classify them as **original-plan
pending**, **necessary correction**, or **optional enhancement**. A necessary
correction requires evidence and the applicable versioned change control; an
optional enhancement remains uncommitted unless explicitly accepted. The
current classifications are recorded in [`STATUS.md`](STATUS.md).
