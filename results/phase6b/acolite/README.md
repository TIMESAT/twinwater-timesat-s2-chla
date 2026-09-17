# Erken ACOLITE extraction

This namespace contains the completed real-data ACOLITE observation-layer
extraction products. The committed run discovered 1,358 ACOLITE product
directories and found 306 products in the exact Phase 6A comparison subset;
236 of those have at least one valid 3×3 index pixel and 70 have none after
the configured ACOLITE QA.

The extractor consumes already-generated ACOLITE GeoTIFFs; it does not run or
reimplement atmospheric correction. Every discovered ACOLITE product is
extracted, including products outside the 2019–2025 Phase 6A interval. The
committed Phase 6A pairing audit annotates the exact comparison subset without
discarding other ACOLITE dates.

Expected server layout:

```text
ACOLITE_ERKEN/
  S2A_MSIL1C_.../
    acolite/
      *_L2R_rhos_665.tif
      *_L2R_rhos_704.tif
      *_L2R_rhos_740.tif
      *_L2W_l2_flags.tif
      run.json
      acolite-settings.txt
```

Run from the repository root on the server:

```bash
export ERKEN_ACOLITE_ROOT="/projects/eko/fs7/pers/ZC/TWIN_water/ACOLITE_ERKEN"
python scripts/27_erken_phase6b_acolite_extraction.py \
  --output-root results/phase6b/acolite \
  --require-real-archive
```

The program stops after extraction, QA, NDCI/MCI construction and QA-only
attrition reporting. It does not inspect CHLF, perform field matchup, compare
processor performance, or run TIMESAT.

The later minimum-valid-pixel decision is frozen separately at at least 6/9
for the primary 3×3 window. It is applied without rewriting these historical
extraction products by `scripts/28_erken_phase6_observation_selection.py`.
