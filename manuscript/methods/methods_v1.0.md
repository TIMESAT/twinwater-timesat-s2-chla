## 2. Materials and Methods

### 2.1 Study design and evidence streams

The study combined two lakes with different observational roles (Fig. 1; Table 1). Lake Erken provided a dense daily chlorophyll-fluorescence (CHLF) record for examining temporal reconstruction under actual Sentinel-2 sampling. Lake Vombsjön provided an independent Sentinel-2 series for testing reconstruction choices that had been frozen in Erken. Four evidence streams were kept separate throughout.

1. **Erken dense-reference temporal reconstruction.** CHLF was sampled on usable Sentinel-2 dates, reconstructed from those dates, and evaluated against the withheld daily CHLF. The same variable was reconstructed and evaluated, so this stream isolates temporal sampling and reconstruction error from satellite retrieval error. It does not test retrieval accuracy.
2. **Erken satellite-index–CHLF observation-layer comparison.** Sentinel-2 red-edge indices from three processing levels were paired with CHLF on exact calendar dates. This stream examines whether observed indices carry chlorophyll-related information. It involves no reconstruction.
3. **Locked Vombsjön withheld-MCI transfer.** The frozen methods were applied to Vombsjön Maximum Chlorophyll Index (MCI) observations without retuning. Each reconstruction was evaluated against observed acquisitions withheld from it. This stream evaluates reconstruction in observed-proxy units and retains satellite observation uncertainty.
4. **Vombsjön sparse field proxy-consistency comparison.** Field chlorophyll-a (Chl-a) measurements were paired with observed MCI on exact calendar dates. They provide complementary proxy-consistency evidence only. They did not enter fitting or tuning and do not provide a daily reconstruction reference.

The evidence hierarchy was specified with the frozen designs. Primary quantitative evidence comprised Erken actual-mask reconstruction against withheld CHLF and Vombsjön ACOLITE reconstruction against withheld observed MCI. Secondary quantitative evidence comprised two analyses:
- Erken controlled-missingness experiments;
- Vombsjön observed-proxy peak timing, which could be evaluated only where the observed peak was identifiable.

Sensitivity analyses comprised official Level-2A (L2A) processing, a cross-validated double-logistic seasonal parameter, and alternative peak-timing tolerances. Level-1C (L1C) top-of-atmosphere processing served as a diagnostic baseline. The Vombsjön field pairs provided complementary descriptive proxy-consistency evidence, while the supplementary Erken seasonal-event analysis was treated as secondary/exploratory. The Erken observation-layer comparison provided separate lake-specific observed-proxy evidence and did not constitute a reconstruction test.

The two lakes differed in four respects:
- the reconstructed quantity (CHLF versus MCI);
- the evaluation reference (withheld dense daily values versus withheld observed acquisitions);
- error normalization;
- the unit of additional missingness (calendar-day windows versus blocks of observed acquisitions).

Numerical skill values were therefore not compared between lakes. The cross-lake comparison concerns whether metric-specific patterns of reliability persisted.

### 2.2 Lake Erken reference and Sentinel-2 observation mask

Lake Erken is a monitored Swedish lake with a Sentinel-2 reference coordinate at 59.84029° N, 18.625827° E. The reference dataset was supplied by the Swedish Infrastructure for Ecosystem Science (Erken Laboratory, 2026). It contains daily CHLF adjusted using laboratory chlorophyll measurements. The record spans 17 April 2019 to 30 November 2025 and contains 2,420 unique calendar dates. Within that interval there are no missing or duplicate dates and no non-finite or negative values. CHLF is reported in µg L⁻¹.

The provider's daily value is the 00:00 observation from higher-frequency sonde measurements, selected to reduce non-photochemical quenching. Measurement configurations changed during the record:
- 2019–2022: a YSI profiler from spring to autumn and a YSI sonde under ice;
- 2023–2025: the metadata include measurements from the Malma Island pumping system at approximately 3 m depth.

Original values were retained together with a broad pre-2023 versus 2023-onward provenance label, which was not interpreted as a causal instrument change. The series is a dense pelagic chlorophyll temporal reference. It carries its own measurement, depth and spatial-support uncertainty and is not equivalent to satellite surface chlorophyll.

The source records ice presence, and 1,950 dates were classified as open water. Ice-covered dates remained part of the reference record but lay outside the satellite-observable evaluation domain. The record begins and ends during open water. Therefore 2019 and 2025 were treated as boundary-truncated years and evaluated only over their observed common support. Their common-support maxima were not interpreted as full-calendar-year maxima.

The local archive contained 950 Sentinel-2 Level-2A products on 926 unique dates within the reference interval (Drusch et al., 2012). Scene quality was assessed at the station coordinate from each product's native Scene Classification Layer (SCL). SCL was used only to define observation availability; it did not select a reflectance product. A centred 3 × 3 window on the 20 m grid (60 × 60 m) was frozen as the primary neighbourhood.

A product passed when its 3 × 3 window met all of the following conditions:
- at least eight water pixels;
- no more than one pixel in an obviously invalid class;
- no persistent non-water or class-2 pixel;
- a centre pixel that was not in an obviously invalid class.

The rule was selected from the SCL observation process alone, without reference to CHLF, spectral-index values or reconstruction results. The calendar date was the temporal observation unit. A date was usable when at least one same-day product passed, and it contributed one observation. The rule retained 307 unique usable dates. Intersecting these dates with open water and finite CHLF produced 288 actual-mask sparse inputs across seven years. All reconstruction methods received identical date–value pairs. Alternative window sizes and the full SCL class logic are reported in the Supplementary Information.

For each year, common support comprised open-water dates from the first through the last sparse input. Disconnected open-water segments within that interval were kept separate. No method received credit for extrapolation outside these limits, and later controlled-missingness experiments did not move them.

### 2.3 Reconstruction methods and Erken evaluation

The benchmark contained three reconstruction methods.

- **Linear interpolation** was a fixed, untuned baseline between retained dates, without extrapolation.
- **TIMESAT double logistic** used the effective defaults of TIMESAT 4.4.1 accessed through timesat-cli 1.9.2 (Jönsson and Eklundh, 2004), including the default seasonal parameter `p_seapar = 1`. The full effective-default configuration was captured as an immutable snapshot before any performance output was generated. A runtime mismatch with that snapshot caused failure rather than silent adoption.
- **TIMESAT smoothing spline** used the fixed candidate grid {0, 1, 3, 10, 30, 100, 300, 1000}.

The spline smoothing parameter was selected by nested leave-one-year-out evaluation. For each outer test year, each candidate reconstructed each of the other six years separately from that year's sparse inputs. Candidates were scored by the equal-year mean of the six year-level normalized root-mean-square errors (nRMSE). The held-out test year's dense reference was excluded from its spline-parameter selection; dense CHLF from the training years entered only this predefined candidate-scoring procedure, and seasonal metrics did not enter tuning. A candidate that failed in any training year was ineligible, and exact ties favoured the smaller smoothing value. The selected values for 2019–2025 were 10, 100, 100, 10, 10, 3 and 10, respectively.

Each reconstruction received only its sparse input dates and values. Method failures, non-convergence and unavailable metrics were retained and reported rather than removed from denominators. Negative reconstructed values were retained without clipping.

Erken evaluation used only common-support dates that were open water, had a finite reference value, and had not been supplied as sparse inputs. Pointwise metrics were bias, mean absolute error (MAE), root-mean-square error (RMSE) and nRMSE, with errors defined as reconstruction minus reference. Erken nRMSE was normalized by the dense reference itself:

`nRMSE_y = RMSE_y / (Q95_y − Q05_y)`

Here Q95_y and Q05_y are the 95th and 5th percentiles of the daily CHLF reference over the common support of year y. When this scale was zero or non-finite, nRMSE was unavailable, and no stabilizing constant was added. Outcomes were first reduced to one value per method and year. Equal-year summaries then averaged the available annual values, so dense daily values were not treated as independent seasonal replicates.

The primary timing target was the global maximum within each year's common support. Its definition was applied identically to the reference and to each reconstruction:
- a contiguous equal-height plateau was assigned its temporal midpoint;
- non-contiguous equal global maxima made peak timing unavailable;
- a reference maximum on a support boundary was flagged and not treated as an ordinarily identifiable peak.

Signed and absolute peak-date errors were recorded. The primary tolerance criterion for timing success was an absolute error of at most 10 calendar days, with 5- and 15-day tolerances as sensitivities. A failed or unavailable reconstructed peak in a reference-eligible year counted as a non-success.

Three further measures were recorded:
- **Peak magnitude:** signed and absolute error, plus normalized absolute peak-magnitude error on the same Q95 − Q05 scale.
- **Common-support integral:** daily trapezoidal integration within each contiguous open-water segment, summed across segments without bridging non-open-water intervals.
- **Trajectory agreement:** Pearson correlation between reconstructed and reference daily trajectories over identical eligible common-support dates, used as a supporting measure alongside magnitude-sensitive error.

Uncertainty in Erken equal-year summaries was represented by 10,000 percentile bootstrap resamples of whole years. The same sampled years were used for all methods within a comparison, so method pairing was preserved.

### 2.4 Controlled missingness and Erken observation-layer comparison

Controlled missingness experiments started from each year's actual-mask sparse inputs. They added missingness to the observed sampling pattern rather than replacing it with an idealized revisit sequence. The first and last sparse inputs of each year were protected, so artificial deletion did not alter common-support boundaries. All methods received identical artificial masks.

**Random deletion.** Deterministic random deletion removed 10%, 20%, 30% or 50% of each year's interior sparse inputs. There were 100 replicates per year and deletion level, giving 2,800 masks.

**Consecutive windows.** Exhaustive consecutive-gap experiments slid 10-, 20-, 30- and 45-day calendar windows through each year's common support. A window was retained when it met all of the following conditions:
- it lay entirely within one contiguous open-water segment;
- it removed no support endpoint;
- it removed at least one sparse input.

This produced 5,746 windows. Each window recorded its duration, the number of sparse inputs removed, its relative position within the segment, and whether it contained the reference global peak.

Hidden-gap activity was summarized for consecutive windows as

`A_gap = Σ_(t=a+1,...,b) |C_t − C_(t−1)| / (Q95_y − Q05_y)`

for a window [a, b], where C_t is the daily reference. The sum includes only day-to-day transitions lying wholly inside the window. A_gap was computed from the dense reference that had been deliberately hidden from the reconstruction. It is therefore a retrospective, descriptive characterization of the concealed dynamics. It is not available inside a real, unknown observation gap and is not an operational predictor. A_gap was analysed as a continuous variable; its association with reconstruction error was summarized, for each method and window duration, by the within-year Spearman correlation between A_gap and scenario nRMSE, averaged with equal year weight. Low, medium and high activity classes, defined by tertiles within each window duration, were used only for display.

Random-deletion masks were characterized by deletion level rather than A_gap. Scenario outcomes were first averaged within each year and stratum (deletion level, window duration, activity class or peak containment) before equal-year summaries were formed; peak-timing success used reference-eligible scenarios as its denominator, with a failed or unavailable reconstructed peak counted as a non-success. No method was retuned by scenario: each year's spline setting was inherited from its outer-fold actual-mask selection, and the other two methods remained fixed. Deterministic seeding and other implementation details are given in the Supplementary Information.

The Erken observation-layer comparison was conducted separately, because the reconstruction experiment sampled CHLF itself and involved no satellite retrieval. It used three reflectance products:
- Level-1C top-of-atmosphere reflectance;
- official Level-2A bottom-of-atmosphere reflectance;
- ACOLITE surface reflectance (`rhos`; Vanhellemont and Ruddick, 2018).

Bands B4, B5 and B6 were extracted on a common 20 m grid, and no empirical cross-baseline correction was applied. The Normalized Difference Chlorophyll Index (NDCI) was computed as (B5 − B4)/(B5 + B4) (Mishra and Mishra, 2012). MCI was computed as B5 minus a baseline interpolated between B4 and B6 at 705 nm, using nominal wavelengths of 665, 705 and 740 nm (Gower et al., 2005). Both indices were calculated at pixel level. An observation required at least six valid pixels in the 3 × 3 window, and its value was the median of the valid pixel-level indices.

The calendar date was the only CHLF matchup key. Nearest-date substitution and temporal interpolation were not permitted. For each index, the primary comparison used processor-shared support, meaning dates that met all of the following conditions:
- exact L1C–L2A–ACOLITE source alignment;
- open water;
- finite same-day CHLF;
- eligibility for that index in all three products.

The three products were therefore compared against identical CHLF dates. The primary association measure was the Spearman correlation between each index and raw CHLF. Uncertainty was estimated from 10,000 percentile bootstrap resamples of whole calendar years. Products were compared descriptively, and no processor winner was declared. This comparison assessed the relevance of the observed indices to chlorophyll variability. It did not define an absolute Chl-a calibration and did not assume spatial or depth equivalence between satellite and in situ observations. Radiometric offset handling and a secondary leave-one-year-out regression are reported in the Supplementary Information.

### 2.5 Locked transfer from Erken to Vombsjön

The reconstruction choices carried to Vombsjön were fixed, using Erken evidence, in a dated, machine-readable transfer freeze before Vombsjön reconstruction performance was inspected. Vombsjön performance and field observations were not used for reconstruction tuning, and the transfer execution performed no retuning. A later pre-performance amendment (v1.1) changed only the spatial support of the field comparison (Section 2.7); it altered no reconstruction setting.

The three primary methods were transferred unchanged in role:
- **Linear interpolation** remained the untuned baseline.
- **Default TIMESAT double logistic** retained `p_seapar = 1` and the frozen effective-default snapshot.
- **TIMESAT smoothing spline** used `p_smooth = 10`. This value was obtained by applying the original candidate grid, scoring rule, candidate-failure rule and smaller-value tie-break to all seven Erken years with equal year weight. It coincides with the most frequent outer-fold selection but was not chosen on that basis. Because it uses all Erken years, this final setting is not itself an independent Erken validation.

All seven training-only outer folds of the separately reported double-logistic sensitivity selected `p_seapar = 0`. This cross-validated setting was carried forward as a sensitivity only and did not replace the default benchmark.

Several further elements were inherited from Erken:
- **Primary proxy.** MCI was designated the primary observed proxy on the basis of the Erken observation-layer comparison. It was treated throughout as a satellite proxy rather than absolute Chl-a.
- **Observation rules.** The six-of-nine valid-pixel rule and the calendar date as the observation unit were carried forward.
- **Fitting constraints.** Separate fitting by calendar year, no extrapolation beyond support, retention of failures and no clipping of negative values were carried forward.
- **Peak rules.** The global-peak plateau, ambiguity and boundary rules, the ±10-day primary tolerance criterion and the ±5- and ±15-day tolerance sensitivities were carried forward where applicable.

Elements specific to the Vombsjön satellite series were frozen at the same stage and are described in Section 2.6. These comprise the fixed station target, training-only scaling, the withholding design and the observed-proxy metrics.

ACOLITE `rhos` was designated the primary processing product according to the study's pre-specified role for a primary aquatic atmospheric correction. The designation did not rest on evidence that ACOLITE outperformed the other products: Erken MCI association intervals overlapped across processors, and no processor winner was declared. Official L2A and L1C MCI were retained as a separate sensitivity and a diagnostic baseline, respectively. Each was evaluated on its own observation calendar, without pooling, fallback between products or cross-calibration.

The freezes were staged and should be read as such:
- The primary Erken reconstruction contract was frozen before the first Erken performance comparison.
- The supplementary seasonal-event protocol was frozen after the global-maximum results had been inspected. It is therefore secondary and exploratory.
- The double-logistic seasonal-parameter sensitivity was specified after the primary Erken results had been inspected but before its own results were generated. It is a secondary sensitivity.
- The transfer freeze preceded inspection of Vombsjön reconstruction performance.

### 2.6 Vombsjön satellite MCI series and withholding experiment

Lake Vombsjön is a eutrophic lake in southern Sweden with a surface area of 11.8 km², a mean depth of 6.6 m and a maximum depth of 16 m (Rabow et al., 2025). The Vombsjön transfer used Sentinel-2 MCI from three processing levels, each treated as a separate series. ACOLITE surface reflectance (`rhos`; Vanhellemont and Ruddick, 2018) formed the primary series according to the frozen study design. Official L2A bottom-of-atmosphere reflectance was a separate processing sensitivity, and L1C top-of-atmosphere reflectance was a diagnostic baseline. Each processor kept its own observation calendar, so the three calendars are independent and unmatched. Series were not pooled, missing products were not replaced by another processor, and no cross-calibration between processing levels was applied.

The temporal target was a fixed 3 × 3 window on the 20 m grid centred on the nominal station at 55.6775° N, 13.60889° E. The window did not move between dates. MCI was calculated at pixel level as

`MCI = B5 − [B4 + ((705 − 665)/(740 − 665)) × (B6 − B4)]`

using the nominal B4, B5 and B6 wavelengths of 665, 705 and 740 nm (Gower et al., 2005). An observation required valid B4, B5 and B6 in at least six of the nine pixels, and its value was the median of the valid pixel-level MCI values. When more than one eligible product of the same processor was available on a calendar date, the observation-level medians were reduced to their median. Each date therefore contributed one observation.

Pixel validity followed each product's native quality assessment. The official SAFE products used their band-quality and cloud/snow classification masks together with a water-class requirement from the paired L2A SCL. ACOLITE used its own flag layer. An observation was unavailable when a required quality family was missing, and invalid pixels were not filled. Negative reflectance and negative MCI values were retained without clipping.

The analysis season was the calendar year. Support extended from the first to the last quality-controlled observation of each year. There was no cross-year fitting and no extrapolation beyond the retained training dates. Vombsjön support was defined by observation availability, not by an independently mapped open-water period. Observed support in 2026 was partial and ended on 3 August for ACOLITE, 20 September for L2A and 11 August for L1C. All support boundaries were retained as observed rather than aligned across processors.

Each calendar year was fitted separately. Day 366 was to be excluded under the frozen TIMESAT setting; no eligible observation fell on day 366, so no date was removed. The frozen TIMESAT configuration expects inputs within a fixed absolute range, whereas MCI is small and signed. For both TIMESAT methods, each year and withholding scenario therefore applied a positive affine transformation fitted to the retained training observations only, mapping their minimum to 1000 and their maximum to 9000. Withheld values never entered this transformation. Predictions were transformed back to native MCI units before any evaluation. Scenarios with a constant or non-finite training range were unavailable for all methods.

Withholding scenarios were enumerated exhaustively within each processor and year. A year was eligible when it contained at least eight dates with valid observations, and every scenario had to retain at least six training observations. The first and last observations of each year were always retained. Two designs were used:
- **Isolated withholding:** each internal observation was withheld once.
- **Consecutive withholding:** every internal sequence of two, three or four consecutive observed acquisitions was withheld.

These blocks are defined by the number of observed acquisitions. Their calendar duration varies with the observation calendar. Within a processor, all methods received identical training and withheld dates. Settings were never adjusted by scenario.

Vombsjön evaluation was defined in observed MCI units and differs from the Erken dense-reference evaluation. Evaluation dates were the withheld dates at which the observation and the predictions of all three primary methods were finite. If any primary method failed, that scenario's paired primary metrics were unavailable. Errors were defined as prediction minus observation. Native-MCI bias, MAE and RMSE were computed for each scenario. nRMSE divided the scenario RMSE by the Q95 − Q05 range of that scenario's retained training observations, with no stabilizing constant. An invalid scale made only nRMSE unavailable.

Scenario metrics were averaged within each processor, year, design, block size and method. Annual RMSE was therefore the mean of scenario RMSEs. Equal-year estimates averaged the available annual values. Because the Vombsjön scale is derived from sparse retained observations rather than a dense withheld reference, its nRMSE is not numerically comparable with Erken nRMSE.

Trajectory correlation was evaluated at withheld dates. A date could be withheld in several overlapping scenarios, so repeated predictions were first collapsed to their median within each year, design, block size, method and date. Pearson correlation between these collapsed predictions and the observed MCI was calculated for each year when at least three dates were available and both series varied. Annual correlations were averaged arithmetically, without a Fisher transformation. These correlations describe agreement at withheld observation dates, not agreement with a dense daily trajectory.

Conditional observed-proxy peak timing was evaluated as a secondary, conditionally identifiable metric within each processor series. The reference was the global maximum among quality-controlled observed MCI values within the annual support, assigned under the frozen plateau, ambiguity and boundary rules. A reference maximum at a support boundary was not identifiable. A scenario was eligible for peak evaluation only when it withheld the date of that observed maximum. The reconstructed daily global maximum was located over the same support, and signed and absolute calendar-day errors were recorded. Continuous peak-error summaries required identifiable peaks from all three primary methods.

Within this metric, the primary tolerance criterion for success was an absolute error of at most 10 days, with 5- and 15-day tolerances as sensitivities. All eligible scenarios formed the success denominator. A fitting failure or an unavailable reconstructed peak counted as a non-success. This measure describes timing relative to the observed satellite-proxy maximum; it does not describe timing of an unobserved ecological bloom peak. No seasonal integral was evaluated for Vombsjön, because no dense reference exists against which an integral could be assessed.

### 2.7 Vombsjön field proxy-consistency comparison

The Vombsjön field record, obtained from the Dryad dataset associated with Rabow et al. (2025) (https://doi.org/10.5061/dryad.02v6wwq7s), comprised 54 sampling dates: 6 in 2018, 22 in 2019 and 26 in 2020. Chl-a was measured by laboratory fluorometry on water-column-integrated samples (Rabow et al., 2025). The integration interval was 0–2 m in 2018 and 0–6 m in 2019–2020 (Rabow et al., 2025). Measured GPS coordinates were available on 23 dates. Of these, 21 passed coordinate quality control. Two dates, 10 June and 24 June 2020, carry an unresolved longitude discrepancy in the source data and were retained without correction. The remaining 31 dates have no measured coordinate. No field sampling clock times were available.

Satellite values for the field comparison came from one fixed pelagic sampling area, not from the nominal-station window used for the temporal series. The area was the unbuffered convex hull of the 21 quality-controlled GPS coordinates plus the nominal station as an anchor. It was identical on every field date and did not depend on any date's own coordinate. Dates without accepted GPS, including the two unresolved dates, contributed no vertex but remained eligible for comparison. No nominal-point fallback was used.

Pixels whose centres fell inside the area on the common 20 m grid were summarized by the median of their valid pixel-level MCI. An observation required at least two-thirds of the area's pixels to be valid, and native quality rules were applied as for the temporal series. Same-day products were reduced as in Section 2.6. The fixed area and its validity rule were adopted in a pre-performance amendment to the field-comparison support. That amendment left the temporal target and all reconstruction settings unchanged.

Field and satellite observations were paired on exact calendar dates, with zero temporal tolerance and no nearest-date substitution. Valid pairs numbered 7 for ACOLITE (four in 2019 and three in 2020), 9 for L2A and 9 for L1C. No processor had a valid pair in 2018. Field values were loaded only after the temporal reconstruction evaluation was complete and never entered fitting, tuning or method selection.

The paired records were examined descriptively as complementary evidence of proxy consistency. No calibration, regression or correlation was calculated. Integrated-water-column samples were not assumed equivalent to satellite-surface Chl-a. Exact-date pairing does not resolve the remaining differences in horizontal support, vertical support and sampling time. Polygon geometry, pixel counts, reasons for unavailable pairs and a secondary actual-GPS 3 × 3 sensitivity are reported in the Supplementary Information.

### 2.8 Sensitivity and uncertainty analyses

The cross-validated double logistic was a secondary sensitivity to the default seasonal parameter. In Erken, `p_seapar` was selected for each outer test year from the grid 0.0–1.0 in steps of 0.1. Selection used only the remaining training years and the same equal-year nRMSE criterion as the spline; exact ties favoured the larger value. The selected value was applied unchanged to the held-out year and to its controlled-missingness scenarios. All seven folds selected `p_seapar = 0`, which was carried to Vombsjön as a separately reported sensitivity. It was evaluated on the primary common dates only where its own fit succeeded and never altered primary denominators.

For peak-timing analyses in both lakes, ±10 days was the primary tolerance criterion, with ±5 and ±15 days as sensitivities. In Vombsjön, official L2A and L1C were evaluated with the same withholding designs and estimators as ACOLITE, but each on its own calendar and support. Differences between processors therefore combine processing with observation availability, so the design does not support a processor ranking.

The calendar year was the unit of replication in both lakes. Daily values and overlapping scenarios were treated as nested observations, not independent seasons. Erken equal-year uncertainty used 10,000 percentile bootstrap resamples of whole years. The same sampled years were used for all methods within a comparison, giving paired method contrasts. Erken paired year-level differences were used to qualify method contrasts (Section 3.2), and leave-one-year-out re-summaries describing their stability are reported in the Supplementary Information.

Vombsjön uncertainty also used 10,000 whole-year percentile bootstrap resamples, drawn separately for each processor, withholding design and block size. Within each such stratum, the same sampled years were reused across methods and metrics, and unavailable annual estimates were carried through each draw. Intervals were not reported for strata with fewer than two available years. No paired inference across processors and no Vombsjön leave-one-year-out analysis were performed.

A supplementary Erken analysis of multiple seasonal events was specified after the global-maximum results had been inspected. It is reported as exploratory in the Supplementary Information and does not replace the global-peak evaluation.

### 2.9 Reproducibility and provenance

Analysis rules were recorded in versioned human- and machine-readable files at the stage to which they applied:
- the Erken reconstruction contract;
- the supplementary event and double-logistic sensitivity protocols;
- the Erken observation-layer protocols;
- the Erken-only transfer freeze and its pre-performance amendment;
- the Vombsjön transfer execution specification.

Later changes were made only through new versions, with predecessors preserved.

The TIMESAT 4.4.1 and timesat-cli 1.9.2 runtimes were pinned to recorded source revisions, and their effective double-logistic defaults were captured in a frozen configuration snapshot. Execution was conditional on the runtime matching that snapshot and passing synthetic checks, including positive-affine equivariance of both TIMESAT reconstructions.

Machine-readable manifests record code revisions and SHA256 checksums of inputs, configurations, the execution specification and outputs. The Vombsjön transfer manifest records native MCI units, the processor roles, the absence of parameter tuning and of field data in tuning, and completion of a separate validation of the saved outputs. That validation covered scenario coverage, training-only scaling, paired masks, metric and aggregation calculations, peak denominators and field-comparison support.

All Vombsjön scenario–method fits completed. Computational completion was recorded separately from scientific reliability, and successful curve generation was not interpreted as evidence that a reconstructed property was preserved.
