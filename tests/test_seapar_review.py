from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from twinwater_timesat.phase3_contract import sha256_file
from twinwater_timesat.seapar_actual import CV_METHOD, DEFAULT_METHOD
from twinwater_timesat.seapar_review import (
    FIGURE_FILENAMES,
    _draw_year,
    _save,
    build_phase5_plotting_table,
    load_phase5_review_sources,
)


ROOT = Path(__file__).resolve().parents[1]


def test_phase5_review_sources_are_frozen_and_complete() -> None:
    sources = load_phase5_review_sources(ROOT)
    assert len(sources["events"]) == 18
    assert sources["selected"] == {year: 0.0 for year in range(2019, 2026)}
    assert int(
        sources["old"]
        .drop_duplicates(["outer_test_year", "date"])[
            "s2_openwater_reference_candidate"
        ]
        .sum()
    ) == 288


def test_phase5_plotting_table_has_all_series() -> None:
    sources = load_phase5_review_sources(ROOT)
    table = build_phase5_plotting_table(sources["old"], sources["new"])
    daily_count = len(sources["new"])
    assert len(table[table["series_type"].eq("daily_reference")]) == daily_count
    assert len(table[table["series_type"].eq("actual_sparse_s2_input")]) == 288
    methods = table[table["series_type"].eq("reconstruction")]
    assert len(methods) == daily_count * 4
    assert set(methods["method"]) == {
        "linear_interpolation",
        "timesat_smoothing_spline",
        DEFAULT_METHOD,
        CV_METHOD,
    }


def test_phase5_figure_inventory_is_exact() -> None:
    assert len(FIGURE_FILENAMES) == 30
    assert len(set(FIGURE_FILENAMES)) == 30


def test_phase5_plot_is_byte_deterministic(tmp_path: Path) -> None:
    sources = load_phase5_review_sources(ROOT)
    table = build_phase5_plotting_table(sources["old"], sources["new"])
    paths = [tmp_path / "one.png", tmp_path / "two.png"]
    for path in paths:
        fig, ax = plt.subplots(figsize=(8, 4), constrained_layout=True)
        _draw_year(ax, table, 2020, selected=0.0)
        _save(fig, path)
    assert sha256_file(paths[0]) == sha256_file(paths[1])
