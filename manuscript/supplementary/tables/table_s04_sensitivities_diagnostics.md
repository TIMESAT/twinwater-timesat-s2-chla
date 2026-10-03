**Table S4. Sensitivities, processor diagnostics, timing tolerances and native-MCI companion metrics.**

Vombsjön processor calendars are independent; rows are not compared across processors. ACOLITE is the primary series, L2A a sensitivity and L1C a diagnostic. Peak timing refers to the maximum among quality-controlled observed MCI values within annual support, not the ecological bloom peak.

(A) Processor roles and support.

| Processor | Role | Observed dates, 2017–2026 | 2026 support ends | Scenarios (isolated / 2 / 3 / 4 acquisitions) | Peak-identifiable years |
|---|---|---:|---|---|---:|
| ACOLITE `rhos` | Primary | 335 | 3 August | 315 / 305 / 295 / 285 (1,200) | 10 |
| L2A BOA | Sensitivity | 419 | 20 September | 399 / 389 / 379 / 369 (1,536) | 9 |
| L1C TOA | Diagnostic | 408 | 11 August | 388 / 378 / 368 / 358 (1,492) | 10 |

(B) L2A and L1C metrics under isolated and four-acquisition withholding (LI / DL / SS).

| Processor, design | nRMSE | Withheld-date r | ±10-d success | Mean absolute peak error (d) |
|---|---|---|---|---|
| L2A, isolated | 0.177 / 0.174 / 0.193 | 0.680 / 0.696 / 0.662 | 0.667 / 0.556 / 0.444 | 21.6 / 20.9 / 27.1 |
| L2A, 4 acquisitions | 0.237 / 0.245 / 0.307 | 0.695 / 0.647 / 0.667 | 0.278 / 0.333 / 0.278 | 34.2 / 26.7 / 32.3 |
| L1C, isolated | 0.204 / 0.194 / 0.226 | 0.576 / 0.587 / 0.557 | 0.500 / 0.500 / 0.300 | 32.8 / 34.6 / 49.5 |
| L1C, 4 acquisitions | 0.262 / 0.276 / 0.329 | 0.619 / 0.527 / 0.623 | 0.275 / 0.300 / 0.350 | 43.7 / 38.4 / 38.0 |

(C) Cross-validated (`p_seapar` = 0; secondary sensitivity) versus default (`p_seapar` = 1) double logistic.

| Setting | Metric | CV-DL | Default DL |
|---|---|---|---|
| Erken, actual mask | nRMSE | 0.239 (0.207–0.273) | 0.250 (0.215–0.286) |
| Erken, actual mask | Daily trajectory r | 0.776 (0.732–0.817) | 0.742 (0.693–0.796) |
| Erken, actual mask | ±10-d success | 0.714 (0.425–1.000) | 0.571 (0.143–0.857) |
| Erken, actual mask | Absolute peak-date error (d) | 53.0 (2.4–115.9) | 54.4 (3.4–118.0) |
| Erken, actual mask | Absolute integral error (µg d L⁻¹) | 139.5 (68.2–250.3) | 126.0 (34.4–271.2) |
| Vombsjön ACOLITE, isolated / 2 / 3 / 4 acquisitions | nRMSE | 0.1694 / 0.2087 / 0.2415 / 0.2820 | 0.1701 / 0.2072 / 0.2384 / 0.2711 |
| Vombsjön ACOLITE, isolated / 2 / 3 / 4 acquisitions | Withheld-date r | 0.755 / 0.724 / 0.692 / 0.673 | 0.745 / 0.723 / 0.693 / 0.663 |
| Vombsjön ACOLITE, isolated / 2 / 3 / 4 acquisitions | ±10-d success | 0.500 / 0.400 / 0.333 / 0.350 | 0.400 / 0.400 / 0.433 / 0.325 |
| Vombsjön ACOLITE, isolated / 2 / 3 / 4 acquisitions | Mean absolute observed-proxy peak error (d) | 39.0 / 32.5 / 30.1 / 34.3 | 22.3 / 29.0 / 31.2 / 27.4 |

Peak errors are rounded half up to one decimal. Erken default-DL intervals in this panel come from the paired cross-validation analysis and differ slightly from Table S2A because of separate resample sub-seeds; point estimates are identical. No integral metric is evaluated for Vombsjön.

(D) ACOLITE peak-tolerance sensitivity, ±5 / ±10 / ±15 days (denominators 10 / 20 / 30 / 40 reference-eligible scenarios).

| Design | LI | DL | SS | CV-DL |
|---|---|---|---|---|
| Isolated | 0.200 / 0.400 / 0.600 | 0.100 / 0.400 / 0.400 | 0.100 / 0.300 / 0.500 | 0.300 / 0.500 / 0.500 |
| 2 acquisitions | 0.100 / 0.300 / 0.450 | 0.100 / 0.400 / 0.550 | 0.150 / 0.300 / 0.350 | 0.350 / 0.400 / 0.500 |
| 3 acquisitions | 0.133 / 0.300 / 0.400 | 0.200 / 0.433 / 0.633 | 0.233 / 0.300 / 0.367 | 0.267 / 0.333 / 0.567 |
| 4 acquisitions | 0.125 / 0.275 / 0.375 | 0.125 / 0.325 / 0.550 | 0.125 / 0.250 / 0.300 | 0.200 / 0.350 / 0.500 |

Four-acquisition values for the other processors (±5 / ±10 / ±15 days):

| Processor | LI | DL | SS |
|---|---|---|---|
| L2A | 0.167 / 0.278 / 0.417 | 0.111 / 0.333 / 0.500 | 0.194 / 0.278 / 0.333 |
| L1C | 0.100 / 0.275 / 0.375 | 0.100 / 0.300 / 0.500 | 0.225 / 0.350 / 0.525 |

(E) Native-MCI companion metrics (equal-year means; ×10⁻³).

| Processor | Method | Bias, isolated | Bias, 4 acquisitions | MAE, isolated | MAE, 4 acquisitions | RMSE, isolated | RMSE, 4 acquisitions |
|---|---|---:|---:|---:|---:|---:|---:|
| ACOLITE | LI | −0.091 | −0.088 | 2.075 | 2.542 | 2.075 | 2.966 |
| ACOLITE | Default DL | −0.110 | −0.025 | 2.140 | 2.838 | 2.140 | 3.278 |
| ACOLITE | SS | −0.078 | −0.033 | 2.362 | 3.475 | 2.362 | 3.949 |
| ACOLITE | CV-DL | −0.073 | 0.080 | 2.097 | 2.890 | 2.097 | 3.327 |
| L2A | LI | −0.059 | −0.002 | 2.614 | 2.887 | 2.614 | 3.388 |
| L2A | Default DL | −0.062 | 0.130 | 2.543 | 3.078 | 2.543 | 3.569 |
| L2A | SS | −0.097 | −0.105 | 2.862 | 3.874 | 2.862 | 4.441 |
| L1C | LI | −0.054 | −0.033 | 2.331 | 2.473 | 2.331 | 2.912 |
| L1C | Default DL | −0.058 | −0.014 | 2.209 | 2.614 | 2.209 | 3.074 |
| L1C | SS | −0.088 | −0.010 | 2.590 | 3.299 | 2.590 | 3.767 |

Isolated MAE equals isolated RMSE because each isolated scenario withholds one date. MCI is a reflectance-difference index without concentration units.
