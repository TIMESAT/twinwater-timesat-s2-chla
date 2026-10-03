# Figure S1

## Caption

Figure S1. Erken Sentinel-2 observation-mask window-size stability. (a) Usable observation dates in 2019–2025 for 1 × 1, 3 × 3 and 5 × 5 station-centred SCL windows under strict, preferred and relaxed pixel-count rules, with thresholds scaled to window size. (b) Number of inter-observation gaps longer than 10, 20, 30 and 45 days for each window under the preferred scaled rule. The 3 × 3 window with the preferred rule is the frozen primary observation mask; the 1 × 1 and 5 × 5 windows are spatial-rule diagnostics and were not used for reconstruction.

## Specification

Data: Spatial-rule diagnostics of the Erken SCL observation mask (1×1, 3×3, 5×5 windows; strict, preferred and relaxed rules). Every plotted value is read directly from a stored result table; no reconstruction, fitting, metric recomputation or inference is performed. Outputs: `figure_s01_observation_mask_stability.png` (600 dpi) and `figure_s01_observation_mask_stability.pdf`, 7.48 in wide, DejaVu Sans, method colours and markers matching the main-text figures. Reproduce with `python scripts/50_build_supplementary_figures.py`.
