from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from twinwater_timesat.phase3_contract import sha256_file
from twinwater_timesat.seasonal_events import EXPECTED_EVENT_TIMES
from twinwater_timesat.trajectory_review import (
    FIGURE_FILENAMES,
    METHOD_LABELS,
    SOURCE_PATHS,
    _draw_year,
    _save,
    build_plotting_table,
    load_frozen_plot_sources,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FROZEN_SHA256 = {
    "daily_trajectories": (
        "60cd1ef8427d52dce4f03f7dcc0d93dbced4c88fe607dd6cbbf726dcaf26ce62"
    ),
    "reference_events": (
        "b52dfd94a9c899ddc8b5bffd07df7961cf9cb60dec6e0c5c3a4fb7176e415efc"
    ),
    "actual_mask_event_metrics": (
        "77b24eb928c3f12f6644ac6c8162c3181de0635994315c3dc1eb14bee60caf53"
    ),
}


def test_frozen_plot_sources_are_exact_and_actual_mask_has_288_inputs() -> None:
    sources = load_frozen_plot_sources(ROOT)
    for name, expected in EXPECTED_FROZEN_SHA256.items():
        assert sources["source_sha256"][name] == expected
    assert sources["events"]["event_id"].tolist() == [
        event_id for event_id, _ in EXPECTED_EVENT_TIMES
    ]
    unique_daily = sources["daily"].drop_duplicates(["outer_test_year", "date"])
    assert unique_daily["s2_openwater_reference_candidate"].sum() == 288


def test_plotting_table_contains_all_frozen_series_and_event_annotations() -> None:
    sources = load_frozen_plot_sources(ROOT)
    table = build_plotting_table(sources["daily"], sources["events"])
    daily_count = len(
        sources["daily"].drop_duplicates(["outer_test_year", "date"])
    )
    assert len(table[table["series_type"].eq("daily_reference")]) == daily_count
    assert len(table[table["series_type"].eq("actual_sparse_s2_input")]) == 288
    reconstructed = table[table["series_type"].eq("reconstruction")]
    assert len(reconstructed) == daily_count * 3
    assert set(reconstructed["method"]) == set(METHOD_LABELS)
    annotated = table.loc[table["is_reference_event"], "reference_event_id"]
    assert set(annotated) == {event_id for event_id, _ in EXPECTED_EVENT_TIMES}


def test_required_figure_inventory_is_complete_and_unique() -> None:
    assert len(FIGURE_FILENAMES) == 24
    assert len(set(FIGURE_FILENAMES)) == 24
    assert "erken_actual_mask_trajectories_overview_2019_2025.png" in FIGURE_FILENAMES
    for year in range(2019, 2026):
        assert f"erken_actual_mask_trajectory_{year}.png" in FIGURE_FILENAMES
        assert f"erken_actual_mask_trajectory_events_{year}.png" in FIGURE_FILENAMES


def test_event_plot_has_reference_and_matched_event_legend_entries() -> None:
    sources = load_frozen_plot_sources(ROOT)
    table = build_plotting_table(sources["daily"], sources["events"])
    figure, axis = plt.subplots()
    _draw_year(
        axis,
        table,
        2020,
        events=sources["events"],
        matches=sources["matches"],
    )
    _, labels = axis.get_legend_handles_labels()
    assert "Frozen reference event" in labels
    for method in METHOD_LABELS.values():
        assert f"{method} matched event" in labels
    plt.close(figure)


def test_same_figure_is_byte_deterministic(tmp_path: Path) -> None:
    sources = load_frozen_plot_sources(ROOT)
    table = build_plotting_table(sources["daily"], sources["events"])
    paths = [tmp_path / "first.png", tmp_path / "second.png"]
    for path in paths:
        figure, axis = plt.subplots(figsize=(8, 4), constrained_layout=True)
        _draw_year(axis, table, 2019)
        _save(figure, path)
    assert sha256_file(paths[0]) == sha256_file(paths[1])


def test_source_files_are_not_review_outputs() -> None:
    assert all(
        not path.startswith("results/phase4/review/")
        for path in SOURCE_PATHS.values()
    )
