# Figure S3

## Caption

Figure S3. Extended Erken controlled-missingness results. (a) Equal-year nRMSE and (b) ±10-day global-peak timing success under random deletion of 10%, 20%, 30% and 50% of interior actual-mask inputs. (c) ±10-day success for 10-, 20-, 30- and 45-day calendar-day deletion windows with the reference global peak outside (open symbols) or inside (filled symbols) the window; intervals are omitted for legibility. (d) Equal-year within-year Spearman correlation between $A_{\mathrm{gap}}$ and nRMSE by window duration. Bars show 95% whole-year bootstrap intervals. $A_{\mathrm{gap}}$ is computed retrospectively from the hidden dense reference and is unavailable inside a real observation gap.

## Specification

Data: Equal-year controlled-missingness summaries and whole-year bootstrap intervals as stored. Every plotted value is read directly from a stored result table; no reconstruction, fitting, metric recomputation or inference is performed. Outputs: `figure_s03_controlled_missingness_extended.png` (600 dpi) and `figure_s03_controlled_missingness_extended.pdf`, 7.48 in wide, DejaVu Sans, method colours and markers matching the main-text figures. Reproduce with `python scripts/50_build_supplementary_figures.py`.
