# Erken real Sentinel-2 QA and data-availability findings

> DRAFT — QA-only audit. No CHLF was inspected. No index-versus-field
> performance, retrieval calibration, L1C-vs-L2A scientific ranking,
> reconstruction result or TIMESAT result is produced here.

## Counts

| quantity | value |
|---|---|
| candidate_dates | 926 |
| dates_without_l2a_representative | 619 |
| exact_l1c_l2a_pairs | 306 |
| extraction_rows | 1233 |
| failure_rows | 658 |
| frozen_representative_l2a_dates | 307 |
| qa_inventory_rows | 22070 |
| unmatched_or_ambiguous_dates | 1 |


## L1C/L2A pairing outcomes

| pairing status | dates |
|---|---|
| ambiguous_multiple_candidates | 1 |
| exact_unique | 306 |
| no_l2a_representative_for_date | 619 |


## Valid-pixel distribution in the frozen 3x3 window

| level | index | valid pixels | records |
|---|---|---|---|
| L1C | NDCI | 0 | 19 |
| L1C | NDCI | 2 | 1 |
| L1C | NDCI | 8 | 5 |
| L1C | NDCI | 9 | 281 |
| L1C | MCI | 0 | 19 |
| L1C | MCI | 2 | 1 |
| L1C | MCI | 8 | 5 |
| L1C | MCI | 9 | 281 |
| L1C | common_B456 | 0 | 19 |
| L1C | common_B456 | 2 | 1 |
| L1C | common_B456 | 8 | 5 |
| L1C | common_B456 | 9 | 281 |
| L2A | NDCI | 0 | 22 |
| L2A | NDCI | 1 | 1 |
| L2A | NDCI | 2 | 1 |
| L2A | NDCI | 6 | 1 |
| L2A | NDCI | 7 | 1 |
| L2A | NDCI | 8 | 7 |
| L2A | NDCI | 9 | 274 |
| L2A | MCI | 0 | 19 |
| L2A | MCI | 2 | 1 |
| L2A | MCI | 8 | 5 |
| L2A | MCI | 9 | 282 |
| L2A | common_B456 | 0 | 19 |
| L2A | common_B456 | 2 | 1 |
| L2A | common_B456 | 8 | 5 |
| L2A | common_B456 | 9 | 282 |


## QA-only attrition at the pre-specified thresholds

| level | index | min valid pixels | records with count | passing | pass fraction | status |
|---|---|---|---|---|---|---|
| L1C | NDCI | 9 | 306 | 281 | 0.9183 | PILOT_NOT_SELECTED |
| L1C | NDCI | 8 | 306 | 286 | 0.9346 | PILOT_NOT_SELECTED |
| L1C | NDCI | 6 | 306 | 286 | 0.9346 | PILOT_NOT_SELECTED |
| L1C | NDCI | 5 | 306 | 286 | 0.9346 | PILOT_NOT_SELECTED |
| L1C | MCI | 9 | 306 | 281 | 0.9183 | PILOT_NOT_SELECTED |
| L1C | MCI | 8 | 306 | 286 | 0.9346 | PILOT_NOT_SELECTED |
| L1C | MCI | 6 | 306 | 286 | 0.9346 | PILOT_NOT_SELECTED |
| L1C | MCI | 5 | 306 | 286 | 0.9346 | PILOT_NOT_SELECTED |
| L1C | common_B456 | 9 | 306 | 281 | 0.9183 | PILOT_NOT_SELECTED |
| L1C | common_B456 | 8 | 306 | 286 | 0.9346 | PILOT_NOT_SELECTED |
| L1C | common_B456 | 6 | 306 | 286 | 0.9346 | PILOT_NOT_SELECTED |
| L1C | common_B456 | 5 | 306 | 286 | 0.9346 | PILOT_NOT_SELECTED |
| L2A | NDCI | 9 | 307 | 274 | 0.8925 | PILOT_NOT_SELECTED |
| L2A | NDCI | 8 | 307 | 281 | 0.9153 | PILOT_NOT_SELECTED |
| L2A | NDCI | 6 | 307 | 283 | 0.9218 | PILOT_NOT_SELECTED |
| L2A | NDCI | 5 | 307 | 283 | 0.9218 | PILOT_NOT_SELECTED |
| L2A | MCI | 9 | 307 | 282 | 0.9186 | PILOT_NOT_SELECTED |
| L2A | MCI | 8 | 307 | 287 | 0.9349 | PILOT_NOT_SELECTED |
| L2A | MCI | 6 | 307 | 287 | 0.9349 | PILOT_NOT_SELECTED |
| L2A | MCI | 5 | 307 | 287 | 0.9349 | PILOT_NOT_SELECTED |
| L2A | common_B456 | 9 | 307 | 282 | 0.9186 | PILOT_NOT_SELECTED |
| L2A | common_B456 | 8 | 307 | 287 | 0.9349 | PILOT_NOT_SELECTED |
| L2A | common_B456 | 6 | 307 | 287 | 0.9349 | PILOT_NOT_SELECTED |
| L2A | common_B456 | 5 | 307 | 287 | 0.9349 | PILOT_NOT_SELECTED |
|  | NDCI | 9 | 0 | 0 |  | PILOT_NOT_SELECTED |
|  | NDCI | 8 | 0 | 0 |  | PILOT_NOT_SELECTED |
|  | NDCI | 6 | 0 | 0 |  | PILOT_NOT_SELECTED |
|  | NDCI | 5 | 0 | 0 |  | PILOT_NOT_SELECTED |
|  | MCI | 9 | 0 | 0 |  | PILOT_NOT_SELECTED |
|  | MCI | 8 | 0 | 0 |  | PILOT_NOT_SELECTED |
|  | MCI | 6 | 0 | 0 |  | PILOT_NOT_SELECTED |
|  | MCI | 5 | 0 | 0 |  | PILOT_NOT_SELECTED |
|  | common_B456 | 9 | 0 | 0 |  | PILOT_NOT_SELECTED |
|  | common_B456 | 8 | 0 | 0 |  | PILOT_NOT_SELECTED |
|  | common_B456 | 6 | 0 | 0 |  | PILOT_NOT_SELECTED |
|  | common_B456 | 5 | 0 | 0 |  | PILOT_NOT_SELECTED |


## Failures retained

| failure reason | records |
|---|---|
| l1c_not_extracted: ambiguous_multiple_candidates | 1 |
| no_frozen_representative_l2a_product_for_date | 619 |
| no_valid_pixels_after_qa_in_frozen_3x3_window | 38 |


## Stopping rule

The final minimum valid-pixel criterion is **not selected here**. This
audit exists so the human can freeze it before any field-matchup
analysis begins. No threshold is declared scientifically superior.
