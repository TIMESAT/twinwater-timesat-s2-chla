# Erken real Sentinel-2 native QA inventory audit

> DRAFT — QA/data-availability description only. No CHLF, no
> index-versus-field performance, no L1C/L2A scientific ranking, no
> reconstruction result.

Native QA asset records: 22070.

## Mask families by processing level

| level | QA family | records | present | declared resolution (m) | scope |
|---|---|---|---|---|---|
| L1C | CLASSI | 306 | 306 | unstated | product-level |
| L1C | CLDPRB | 306 | 0 | unstated | n/a |
| L1C | CLOUDS | 306 | 0 | unstated | n/a |
| L1C | DEFECT | 306 | 0 | unstated | n/a |
| L1C | DETFOO | 3978 | 3978 | unstated | band-specific |
| L1C | NODATA | 306 | 0 | unstated | n/a |
| L1C | QUALIT | 3978 | 3978 | unstated | band-specific |
| L1C | SATURA | 306 | 0 | unstated | n/a |
| L1C | SNWPRB | 306 | 0 | unstated | n/a |
| L1C | TECQUA | 306 | 0 | unstated | n/a |
| L2A | CLASSI | 307 | 307 | unstated | product-level |
| L2A | CLDPRB | 614 | 614 | 20;60 | product-level |
| L2A | CLOUDS | 307 | 0 | unstated | n/a |
| L2A | DEFECT | 307 | 0 | unstated | n/a |
| L2A | DETFOO | 3991 | 3991 | unstated | band-specific |
| L2A | NODATA | 307 | 0 | unstated | n/a |
| L2A | QUALIT | 3991 | 3991 | unstated | band-specific |
| L2A | SATURA | 307 | 0 | unstated | n/a |
| L2A | SCL | 614 | 614 | 20;60 | product-level |
| L2A | SNWPRB | 614 | 614 | 20;60 | product-level |
| L2A | TECQUA | 307 | 0 | unstated | n/a |


## Missing or unsupported mask families

| level | QA family | status | records |
|---|---|---|---|
| L1C | CLDPRB | absent | 306 |
| L1C | CLOUDS | absent | 306 |
| L1C | DEFECT | absent | 306 |
| L1C | NODATA | absent | 306 |
| L1C | SATURA | absent | 306 |
| L1C | SNWPRB | absent | 306 |
| L1C | TECQUA | absent | 306 |
| L2A | CLOUDS | absent | 307 |
| L2A | DEFECT | absent | 307 |
| L2A | NODATA | absent | 307 |
| L2A | SATURA | absent | 307 |
| L2A | TECQUA | absent | 307 |


## Layout differences by processing baseline and platform

| processing baseline | platform | products |
|---|---|---|
| N0500 | S2A | 131 |
| N0500 | S2B | 146 |
| N0509 | S2B | 2 |
| N0510 | S2A | 86 |
| N0510 | S2B | 100 |
| N0511 | S2A | 50 |
| N0511 | S2B | 66 |
| N0511 | S2C | 32 |


## Grid handling actually applied

| layer | observed native pixel size (m) | alignment | records |
|---|---|---|---|
| B4 | 10 | block_mean_reduce_x2 | 306 |
| B4 | 20 | native_target_grid | 307 |
| B5 | 20 | native_target_grid | 613 |
| B6 | 20 | native_target_grid | 613 |
| classi_product | 60 | exact_footprint_expand_x3 | 613 |
| qualit_b04 | 10 | any_invalid_reduce_x2 | 613 |
| qualit_b05 | 20 | native_target_grid | 613 |
| qualit_b06 | 20 | native_target_grid | 613 |
| scl | 20 | native_target_grid | 613 |


Absence of a mask family is recorded, never treated as clean; affected
observations carry `native_qa_incomplete`.
