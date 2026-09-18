# Vombsjön field-input audit v1.0

**Audit date:** 2026-09-18
**Starting commit:** `b3aeb4e782d74f7b6ce7d08bad28e61ee9c66a4f`
**Scope:** field-source intake and input verification only. No Sentinel-2 product audit and no Vomb reconstruction performance were run.

## Source identity

All four repository files are byte-identical to the readable user-supplied files. The requested CSV name included `(1)`, but the available file was already named `Vombsjon_S2_field_matchup_master.csv`; the actual filename was retained as the canonical repository name.

| Repository file | SHA256 | Bytes | Licence information actually verified |
|---|---|---:|---|
| `data/sources/vombsjon/Vombsjon_S2_field_matchup_master.csv` | `115f0ae9dd3545f889c86e2cb0875ef69107db4038dfdb0772fd2e57f6281d37` | 18278 | Not stated in the CSV; Dryad dataset licence not independently verified from the supplied files |
| `data/sources/vombsjon/Metadata_Vombsjon_SR.xlsx` | `a210a425bd2387721600232b1f69edf3e7770885439de1ed7aff1e8c51ca2f50` | 23363 | No licence statement found in the workbook |
| `data/sources/vombsjon/Vombsjon_Dryad_README.md` | `1255ec2520166547c9207071cfb957da61ed55e7f4fbd238c4cbb55d90ab4aed` | 2220 | README states that Table 3 data are CC BY and separately hosted; it does not state a licence for the README or full supplied package |
| `references/vombsjon/Rabow_2025_Harmful_Algae.pdf` | `d25b67cb4a6ec021f417b895e6b59cf189d6759f505402d9e6f417c5fcc79bf8` | 3252316 | CC BY 4.0 stated on article page 1 |

The article states that its underlying manuscript dataset is available from Dryad at <https://doi.org/10.5061/dryad.02v6wwq7s>. The supplied files do not establish the exact Dryad version or a package-wide data licence, so those remain unverified. Article page 1 explicitly states CC BY 4.0 for the PDF.

## Confirmed field-table facts

- The canonical CSV contains **54 unique observation dates** from **2018-06-25 to 2020-10-29**: 2018 = 6, 2019 = 22, and 2020 = 26. There are no duplicate dates.
- `chla_fluorometry_ug_L` has no missing values and ranges from 0.896 to 125.7 µg L⁻¹. The paper reports laboratory fluorometry with a TD-700 fluorometer.
- All 48 observations from 2019-2020 are labelled exact matches to the DiCyano comparison file; the six 2018 observations are explicitly outside that comparison file.
- The metadata workbook contains 23 dated rows in 2019 and 26 in 2020. Every one of the 48 canonical 2019-2020 Chl-a dates matches the workbook date, echo depth, raw GPS, wind and field notes. `2019-05-02` is a metadata-only field occasion and is not a canonical Chl-a record.
- The 23 measured coordinate records use three formats: decimal degrees (4), degrees plus decimal minutes (2), and degrees-minutes-seconds (17). All convert to the decimal values stored in the CSV, and all supplied distances to the nominal station reproduce within 0.02 m using a haversine calculation.
- The CSV separates actual measured GPS (21 usable matchup rows), nominal-station fallback (31 rows), and two unresolved measured-GPS rows whose matchup coordinates remain blank. The fixed nominal station is 55.6775 N, 13.60889 E.
- The paper reports a roughly 7 m-deep sampling site and the XLSX `Echo depth` records the local lake depth (6.6-9.0 m where present). This is distinct from the integrated sampling interval: 0-2 m in 2018 and 0-6 m in 2019-2020. The CSV preserves that year-specific distinction on every row.
- The paper reports sampling every two weeks from late June to mid-September in 2018, then weekly from May to October in 2019-2020. It describes volume-integrated tube sampling and laboratory fluorometric Chl-a analysis. The supplied README identifies Table 5 as the Chl-a fluorometry and AlgaeLabAnalyser community-composition table.

## Issues and impact

- `2020-06-10`: source `55 40 41, 13 35 32` converts to `55.678055555556, 13.592222222222` and is about 1046.8 m from the nominal station. Changing longitude minutes from 35 to 36 would produce `13.608888888889` and about 61.8 m, but this is only a diagnostic candidate and was not applied.
- `2020-06-24`: source `55 40 42, 13 35 35` converts to `55.678333333333, 13.593055555556` and is about 997.1 m from the nominal station. Changing longitude minutes from 35 to 36 would produce `13.609722222222` and about 106.3 m, but this is only a diagnostic candidate and was not applied.

These source values remain unchanged. The two records retain their field Chl-a values and remain available for field-series/ecological use, but an actual-GPS-centred satellite matchup is unavailable until the longitude notation is confirmed. They must not be silently moved to the nominal station or to a hypothetical corrected coordinate.

Other incompleteness is explicit rather than repaired: measured GPS is absent on 31 dates, echo depth is absent on nine dates (all six 2018 dates plus 2019-05-08, 2019-07-30, and 2020-05-06), and AlgaeLabAnalyser composition is absent on 2018-06-25. These gaps do not remove any of the 54 fluorometric Chl-a observations. Wind, notes and the field metadata workbook are unavailable for the six 2018 dates.

## Still to verify

1. Confirm with the original field record or data authors whether the longitude minutes on 2020-06-10 and 2020-06-24 are 35 or 36. Preserve both original strings and QC flags regardless of any later governed correction.
2. Confirm the coordinate reference/datum terminology for the handheld GPS records. The supplied N/E strings and paper coordinates support the documented angular conversions, but the source files do not provide a machine-readable CRS declaration.
3. Verify the exact Dryad dataset version and licence applicable to the CSV/XLSX/README. The article is CC BY 4.0, but that does not by itself prove the data-file licence.
4. Supply and audit the Vomb Sentinel-2 product inventory and ACOLITE outputs. No satellite product was supplied in this intake, so scene identity, processing baseline, ROI coverage, QA, ACOLITE versions/settings, and same-day deduplication remain pending.

## Analysis boundary

This audit completes field-material intake and verification only. It does not change the frozen MCI/ACOLITE choice, spatial support, QC, scaling, holdout design, TIMESAT settings, metrics or failure rules. It does not calculate Vomb reconstruction performance.
