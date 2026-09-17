# Frozen Erken observation selection

This namespace contains the deterministic post-pilot application of Decision
017. The primary station-centred 3×3 / 20 m observation threshold is at least
6 of 9 valid pixels, applied equally to L1C, official L2A and ACOLITE and
separately to NDCI, MCI and common-B456 support.

The unified CSV keeps one row per frozen Phase 6A candidate date and method:
926 dates × 3 methods = 2,778 rows. Unavailable, ambiguous and below-threshold
observations remain explicit rather than being deleted.

Generate from the repository root with:

```bash
python scripts/28_erken_phase6_observation_selection.py
```

The generator reads only the committed Phase 6A/6B QA and index tables and
rejects inputs containing CHLF or `PRESENCE_ICE`. No field matchup, processor
ranking, reconstruction or TIMESAT analysis is performed here.

Governance:

- `docs/Erken_Sentinel2_Observation_Selection_Protocol_v1.0.md`
- `config/erken_s2_observation_selection_v1.0.yaml`
- Decision 017 in `docs/decisions.md`
