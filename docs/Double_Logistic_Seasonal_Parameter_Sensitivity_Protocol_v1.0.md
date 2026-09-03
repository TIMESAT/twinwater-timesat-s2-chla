# Double-Logistic Seasonal-Parameter Sensitivity Protocol v1.0

**Status:** FROZEN before any real sensitivity performance  
**Analysis class:** `secondary_sensitivity_double_logistic_seasonal_parameter`  
**Starting commit:** `ce2fd7d5fa039584ccb1f6f0751dc46acedd0be1`  
**Parent contract:** `Reconstruction_Analysis_Contract_v1.0.1`  
**Parent event protocol:** `Seasonal_Event_Detection_and_Matching_Protocol_v1.0`

## 1. Purpose and status

This secondary sensitivity analysis asks whether allowing training-only
selection of the TIMESAT double-logistic seasonal parameter `p_seapar`
materially changes trajectory fidelity, seasonal-event recovery, or
controlled-gap reliability relative to the already inspected primary analysis,
which used the frozen default `p_seapar = 1`.

This analysis cannot replace, relabel, or revise the primary analysis. All
original Phase 3 and Phase 4 scientific outputs remain immutable.

## 2. Frozen candidate grid and runtime gate

The only allowed candidates, in evaluation order, are:

`0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0`

No adaptive refinement is allowed. Before real Erken sensitivity performance,
the frozen TIMESAT 4.4.1 / timesat-cli 1.9.2 runtime must materialize each
candidate as a float64 `p_seapar` array, demonstrate exact equality between the
requested and effective value, and pass one synthetic double-logistic smoke
test for every candidate. Any rejection, failure, or coercion stops the
workflow. Runtime versions and source/binary checksums are recorded.

The original frozen default remains `p_seapar = 1` and is always labelled as
the default, never as a cross-validated result.

## 3. Training-only LOYO selection

Outer test years are 2019 through 2025. For each outer year, exclude that year
completely and evaluate all 11 candidates separately in each of the six
remaining training years using that year's frozen actual-mask sparse inputs.
Evaluation uses the same withheld daily-reference dates, common support, and
method-independent yearly scale as the parent contract:

`Scale_y = Q95(C_y) - Q05(C_y)`

For every candidate and training year, compute nRMSE using the existing Phase 3
point-wise metric. Average the six yearly nRMSE values with equal year weight.
A candidate is ineligible if reconstruction or required nRMSE fails in any
training year. Select the eligible candidate with the smallest stored
equal-year mean nRMSE. For an exact stored-precision tie, select the larger
`p_seapar`, representing the simpler/fewer-season configuration. If every
candidate is ineligible in a fold, stop before downstream performance.

Event recovery, global-peak timing, magnitude error, integral error,
controlled-gap results, original default-DL performance, and held-out-year
reference values are forbidden selection inputs. Mutation of the excluded
outer reference must not change the selected parameter.

## 4. Actual-mask and event sensitivity

Apply each outer fold's selected `p_seapar` once to its held-out year and label
the new method `timesat_double_logistic_cv_seapar`. Reuse the saved primary
Linear, Spline, and default-DL results for comparison. Do not rerun or retune
those methods.

Actual-mask metrics are exactly the existing contract metrics: bias, MAE,
RMSE, nRMSE, frozen global-peak timing and magnitude metrics, common-support
integral metrics, Pearson correlation, negative-value diagnostics, and explicit
reconstruction status/failure diagnostics.

Event analysis uses exactly the frozen 18 Erken reference events, the existing
amplitude-agnostic reconstructed-peak detector, same-year/same-segment matching,
the ±15-day one-to-one matching rule, magnitude-independent assignment, and
5/10/15-day success thresholds. Events are never used for tuning.

No method winner or ranking is generated.

## 5. Controlled-gap sensitivity

Use the existing immutable 2,800 random-deletion and 5,746 consecutive-gap
masks. Their raw SHA256 values must match the frozen Phase 3 and Phase 4
manifests before execution. For the new method only, apply the year-specific
Phase S1 selection unchanged to every scenario in that year.

`p_seapar` must never be reselected by scenario, deletion fraction, gap
duration, gap position, `A_gap`, event recovery, or any controlled-gap result.
Linear, Spline, and default-DL comparison values are read from the saved primary
outputs. The frozen Spline selections, endpoint protection, segment boundaries,
mask identities, no-deduplication rule, support, and `A_gap` definition remain
unchanged. Failures remain explicit.

## 6. Descriptive synthesis and hard stop

Phase S5 reports factual, year-aware comparisons of default DL and CV-selected
DL alongside saved Linear and Spline results. It includes actual-mask metrics,
event recovery, selected-parameter response curves, controlled-gap summaries,
failure/negative diagnostics, and review figures. Thousands of masks are not
treated as independent lake-years. No inferential model, universal gap
threshold, method ranking, or manuscript-level superiority claim is allowed.

Stop after the Phase S5 review packet at the hard human gate.

## 7. Non-interference and forbidden scope

This protocol does not change the parent reconstruction contract, parent event
protocol, TIMESAT defaults snapshot, frozen spline grid/selections, masks,
sparse-input dates, support rules, tolerances, reconstruction repair rules, or
any original Phase 3/4 output. No Vombsjön data, result, or performance may be
opened or inspected in this workflow.

Any runtime grid failure/coercion, leakage, tuning-rule violation, parent-output
checksum change, reference-event change, new repair-rule requirement, or failed
audit stops the workflow immediately.
