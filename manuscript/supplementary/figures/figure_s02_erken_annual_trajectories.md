# Figure S2

## Caption

Figure S2. Annual Erken dense-reference trajectories and actual-mask reconstructions, 2019–2025. Each panel shows daily CHLF (dense reference), actual-mask Sentinel-2 input dates, and the linear-interpolation, default TIMESAT double-logistic and TIMESAT smoothing-spline reconstructions within that year's common support; dotted lines mark the common-support boundaries. The smoothing spline uses each year's outer-fold smoothing value, shown in the panel title. Asterisks mark the boundary-truncated common support in 2019 and 2025, whose common-support maxima are not interpreted as full-year maxima. Y-axis limits vary among years to preserve within-year detail.

## Specification

Data: Stored actual-mask daily reconstructions and dense CHLF reference within common support; outer-fold spline values as stored. Every plotted value is read directly from a stored result table; no reconstruction, fitting, metric recomputation or inference is performed. Outputs: `figure_s02_erken_annual_trajectories.png` (600 dpi) and `figure_s02_erken_annual_trajectories.pdf`, 7.48 in wide, DejaVu Sans, method colours and markers matching the main-text figures. Reproduce with `python scripts/50_build_supplementary_figures.py`.
