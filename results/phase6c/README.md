# Phase 6C — Erken Sentinel-2 index–CHLF matchup analysis

Phase 6C evaluates exact-same-date Erken NDCI/MCI observations against the
canonical daily CHLF reference. It consumes the frozen Phase 6B unified
observation-selection table and does not alter its 6/9 threshold, QA rules,
spatial support or source products.

Primary comparisons use metric-specific common support across L1C, official
L2A and ACOLITE. Secondary method-specific support is retained separately and
cannot be used as a direct method ranking.

Run from the repository root:

```bash
python scripts/29_erken_phase6c_chlf_matchup.py
```

Governance:

- `docs/Erken_Sentinel2_CHLF_Matchup_Analysis_Protocol_v1.0.md`
- `config/erken_s2_chlf_matchup_analysis_v1.0.yaml`
- Decision 018 in `docs/decisions.md`

The interpreted results, limitations and stopping conclusion are recorded in
`docs/Erken_Phase6C_CHLF_Analysis_Record_2026-09-17.md`.

This phase stops after Erken observation-layer association and exploratory
LOYO proxy validation. It does not run reconstruction, TIMESAT or Vombsjön.
