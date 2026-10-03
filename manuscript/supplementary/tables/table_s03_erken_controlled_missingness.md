**Table S3. Erken controlled-missingness details.**

(A) Random deletion of interior actual-mask inputs (700 masks per level). Equal-year estimates (95% whole-year interval).

| Level | nRMSE LI | nRMSE DL | nRMSE SS | ±10-d success LI | ±10-d success DL | ±10-d success SS |
|---|---|---|---|---|---|---|
| 10% | 0.209 (0.162–0.252) | 0.253 (0.221–0.288) | 0.228 (0.192–0.259) | 0.694 (0.401–0.977) | 0.577 (0.161–0.861) | 0.589 (0.271–0.883) |
| 20% | 0.217 (0.176–0.254) | 0.258 (0.226–0.291) | 0.236 (0.204–0.264) | 0.659 (0.353–0.936) | 0.579 (0.183–0.864) | 0.596 (0.317–0.864) |
| 30% | 0.225 (0.189–0.257) | 0.265 (0.240–0.295) | 0.243 (0.214–0.269) | 0.634 (0.327–0.904) | 0.594 (0.240–0.879) | 0.614 (0.341–0.867) |
| 50% | 0.247 (0.220–0.273) | 0.288 (0.267–0.312) | 0.275 (0.244–0.306) | 0.579 (0.317–0.811) | 0.566 (0.270–0.836) | 0.581 (0.329–0.803) |

(B) Consecutive calendar-day deletion windows.

| Duration (windows; inputs removed) | nRMSE LI | nRMSE DL | nRMSE SS | ±10-d success (LI / DL / SS) |
|---|---|---|---|---|
| 10 d (1,379; 1–5) | 0.208 (0.161–0.250) | 0.253 (0.219–0.288) | 0.227 (0.193–0.259) | 0.690 / 0.578 / 0.589 |
| 20 d (1,525; 1–8) | 0.214 (0.170–0.254) | 0.257 (0.224–0.291) | 0.235 (0.203–0.264) | 0.668 / 0.575 / 0.592 |
| 30 d (1,475; 1–11) | 0.221 (0.179–0.259) | 0.263 (0.232–0.296) | 0.246 (0.215–0.275) | 0.650 / 0.559 / 0.593 |
| 45 d (1,367; 1–14) | 0.238 (0.198–0.277) | 0.289 (0.263–0.318) | 0.280 (0.243–0.315) | 0.610 / 0.482 / 0.547 |

(C) Hidden-gap activity: within-year Spearman correlation between A_gap and nRMSE (equal-year, seven years), with A_gap tertile cuts.

| Duration | A_gap tertile cuts (observed range) | LI | DL | SS |
|---|---|---|---|---|
| 10 d | 0.162 / 0.641 (0.007–6.456) | 0.273 (0.045–0.511) | 0.360 (0.248–0.484) | 0.197 (−0.028–0.420) |
| 20 d | 0.410 / 1.531 (0.025–11.128) | 0.367 (0.103–0.635) | 0.400 (0.306–0.489) | 0.240 (−0.003–0.498) |
| 30 d | 0.747 / 2.555 (0.049–15.484) | 0.421 (0.162–0.679) | 0.464 (0.385–0.544) | 0.309 (0.082–0.543) |
| 45 d | 1.260 / 4.190 (0.271–17.289) | 0.532 (0.276–0.731) | 0.416 (0.264–0.547) | 0.464 (0.312–0.618) |

45-day activity-class nRMSE (low / medium / high; 456 / 455 / 456 windows): LI 0.216 / 0.237 / 0.273; DL 0.274 / 0.282 / 0.317; SS 0.246 / 0.282 / 0.316.

(D) Peak containment: ±10-day success with the reference global peak outside / inside the window.

| Duration (windows outside / inside) | LI | DL | SS |
|---|---|---|---|
| 10 d (1,320 / 59) | 0.705 / 0.390 | 0.578 / 0.571 | 0.589 / 0.602 |
| 20 d (1,403 / 122) | 0.707 / 0.286 | 0.581 / 0.521 | 0.594 / 0.564 |
| 30 d (1,303 / 172) | 0.706 / 0.288 | 0.575 / 0.462 | 0.590 / 0.574 |
| 45 d (1,122 / 245) | 0.704 / 0.252 | 0.517 / 0.387 | 0.563 / 0.445 |

A_gap is computed retrospectively from the hidden dense reference and is not available inside a real observation gap; it is not an operational predictor. Overlapping windows are nested within years and are not independent seasonal replicates.
