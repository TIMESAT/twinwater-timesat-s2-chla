**Table S2. Erken actual-mask companion metrics and robustness.**

(A) Equal-year estimates (95% whole-year interval). All metrics: 7 of 7 years available, no reconstruction failures.

| Metric | LI | DL | SS |
|---|---|---|---|
| nRMSE | 0.203 (0.154–0.250) | 0.250 (0.216–0.286) | 0.223 (0.186–0.257) |
| MAE (µg L⁻¹) | 2.044 (1.354–2.833) | 3.053 (2.328–3.815) | 2.312 (1.733–3.010) |
| RMSE (µg L⁻¹) | 4.353 (2.735–6.114) | 5.331 (3.820–6.854) | 4.721 (3.278–6.280) |
| Daily trajectory r | 0.864 (0.817–0.911) | 0.742 (0.693–0.795) | 0.830 (0.800–0.863) |
| Absolute peak-date error (d) | 34.6 (1.6–91.1) | 54.4 (3.3–118.7) | 54.6 (4.4–117.9) |
| Peak success ±5 d | 0.571 (0.143–0.857) | 0.571 (0.143–0.857) | 0.429 (0.143–0.857) |
| Peak success ±10 d | 0.714 (0.429–1.000) | 0.571 (0.143–0.857) | 0.571 (0.143–0.857) |
| Peak success ±15 d | 0.714 (0.286–1.000) | 0.714 (0.429–1.000) | 0.714 (0.429–1.000) |
| Absolute peak-magnitude error (µg L⁻¹) | 18.02 (5.75–31.41) | 28.90 (16.64–40.44) | 22.89 (11.50–34.19) |
| Normalized peak-magnitude error | 0.797 (0.233–1.439) | 1.304 (0.774–1.851) | 1.039 (0.560–1.575) |
| Absolute integral error (µg d L⁻¹) | 157.5 (86.6–245.8) | 126.0 (34.3–271.8) | 187.1 (131.5–256.8) |
| Absolute relative integral error | 0.092 (0.056–0.134) | 0.077 (0.024–0.154) | 0.113 (0.086–0.146) |

(B) Annual bias (µg L⁻¹; reconstruction minus reference). Asterisk: boundary-truncated common support.

| Year | LI | DL | SS |
|---|---:|---:|---:|
| 2019* | −1.916 | −2.649 | −1.836 |
| 2020 | −0.448 | −0.027 | −0.552 |
| 2021 | 0.401 | 0.650 | 0.629 |
| 2022 | −0.800 | −0.297 | −0.886 |
| 2023 | 0.523 | 0.394 | 0.754 |
| 2024 | −0.163 | −0.228 | −0.513 |
| 2025* | 1.149 | −0.084 | 1.278 |

Annual bias is given for traceability. No equal-year bias estimate was formed.

(C) Paired contrasts: mean advantage of the first-named method (positive favours it), 95% paired whole-year interval; years favouring first / second method / tied.

| Metric | LI vs DL | LI vs SS | SS vs DL |
|---|---|---|---|
| nRMSE | 0.047 (0.016–0.084); 7/0/0 | 0.019 (0.007–0.033); 6/1/0 | 0.028 (0.004–0.053); 5/2/0 |
| MAE | 1.009 (0.664–1.344); 7/0/0 | 0.268 (0.105–0.453); 7/0/0 | 0.741 (0.450–0.962); 6/1/0 |
| RMSE | 0.978 (0.302–1.769); 7/0/0 | 0.368 (0.094–0.672); 6/1/0 | 0.610 (0.143–1.114); 5/2/0 |
| Daily trajectory r | 0.122 (0.052–0.197); 7/0/0 | 0.034 (0.015–0.056); 7/0/0 | 0.088 (0.033–0.146); 6/1/0 |
| Normalized peak magnitude | 0.507 (0.236–0.799); 7/0/0 | 0.242 (0.084–0.455); 7/0/0 | 0.265 (0.102–0.411); 6/1/0 |
| Absolute peak-date error (d) | 19.8 (−0.2–54.2); 5/2/0 | 20.0 (1.6–54.0); 6/1/0 | −0.2 (−5.3–4.7); 3/3/1 |
| Peak success ±10 d | 0.143 (0.000–0.429); 1/0/6 | 0.143 (0.000–0.429); 1/0/6 | 0.000 (−0.429–0.429); 1/1/5 |
| Absolute integral error (µg d L⁻¹) | −31.5 (−113.8–53.8); 3/4/0 | 29.6 (10.4–46.9); 6/1/0 | −61.1 (−143.8–33.3); 1/6/0 |

(D) Leave-one-year-out directional stability: range of the paired advantage across seven single-year omissions; whether every omission keeps the full-record direction.

| Metric | LI vs DL | LI vs SS | SS vs DL |
|---|---|---|---|
| nRMSE | 0.035–0.054; yes | 0.015–0.023; yes | 0.020–0.035; yes |
| Daily trajectory r | 0.098–0.140; yes | 0.024–0.038; yes | 0.070–0.104; yes |
| Normalized peak magnitude | 0.408–0.591; yes | 0.148–0.276; yes | 0.211–0.332; yes |
| Absolute peak-date error (d) | 3.1–23.9; yes | 3.3–23.5; yes | −2.1–1.8; no |
| Peak success ±10 d | 0.000–0.167; one tie, no reversal | 0.000–0.167; one tie, no reversal | −0.167–0.167; no |
| Absolute integral error (µg d L⁻¹) | −64.3 to −0.8; yes | 23.7–37.2; yes | −101.5 to −31.3; yes |

MAE and RMSE contrasts keep their direction in all omissions for all pairs. Point estimates in (A) are descriptive; (C) and (D) are paired contrasts.
