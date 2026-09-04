"""Frozen 3x3 spatial summaries, QA-only attrition and Phase 6A audit tables.

The primary spatial statistic is the median of valid pixel-level index values
inside the frozen station-centred 3x3 support. Diagnostics are retained
alongside it so a later human freeze has the evidence it needs.

The attrition table exists to let the human freeze the final minimum
valid-pixel criterion before any field-matchup analysis. Nothing here selects
that threshold, and nothing here declares one threshold scientifically
superior.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


NO_VALID_PIXELS = "no_valid_pixels_in_frozen_3x3_window"


def summarize_index_window(
    values: np.ndarray,
    valid: np.ndarray,
    *,
    prefix: str,
    window_pixel_count: int,
) -> dict[str, Any]:
    """Summarize valid pixel-level index values inside the frozen window.

    The median is the primary statistic. Mean, SD, IQR, minimum and maximum are
    retained as diagnostics. When no pixel is valid, every statistic is ``None``
    rather than a substituted value.
    """

    array = np.asarray(values, dtype="float64")
    mask = np.asarray(valid).astype(bool) & np.isfinite(array)
    selected = array[mask]
    count = int(selected.size)

    summary: dict[str, Any] = {
        f"{prefix}_valid_pixel_count": count,
        f"{prefix}_valid_pixel_fraction": (
            count / window_pixel_count if window_pixel_count else None
        ),
        f"{prefix}_median": None,
        f"{prefix}_mean": None,
        f"{prefix}_SD": None,
        f"{prefix}_IQR": None,
        f"{prefix}_min": None,
        f"{prefix}_max": None,
    }
    if count == 0:
        return summary

    q25, q75 = np.quantile(selected, [0.25, 0.75], method="linear")
    summary[f"{prefix}_median"] = float(np.median(selected))
    summary[f"{prefix}_mean"] = float(np.mean(selected))
    # Sample standard deviation is undefined for a single pixel; report None
    # rather than a zero that would look like agreement between pixels.
    summary[f"{prefix}_SD"] = float(np.std(selected, ddof=1)) if count > 1 else None
    summary[f"{prefix}_IQR"] = float(q75 - q25)
    summary[f"{prefix}_min"] = float(np.min(selected))
    summary[f"{prefix}_max"] = float(np.max(selected))
    return summary


def qa_failure_counts(
    layers: Mapping[str, Any], *, window_pixel_count: int
) -> dict[str, Any]:
    """Return native QA failure counts and fractions, keeping band provenance.

    Two families of column are emitted:

    * ``qa_<band>_<reason>`` for a band-specific condition, so the output never
      erases the fact that a flag came from B4, B5 or B6; and
    * ``qa_<reason>``, the union of that reason across bands, which supplies the
      canonical schema field while remaining derivable from the per-band
      columns.
    """

    counts: dict[str, Any] = {}
    aggregated: dict[str, np.ndarray] = {}

    def _fraction(count: int) -> float | None:
        return count / window_pixel_count if window_pixel_count else None

    for key, layer in sorted(layers.items()):
        flags = np.asarray(getattr(layer, "flags", layer)).astype(bool)
        reason = str(getattr(layer, "name", key))
        band = getattr(layer, "band", None)

        count = int(np.count_nonzero(flags))
        counts[f"qa_{key}"] = count
        counts[f"qa_{key}_fraction"] = _fraction(count)
        if band is not None:
            counts[f"qa_{key}_band"] = band

        existing = aggregated.get(reason)
        aggregated[reason] = flags if existing is None else (existing | flags)

    for reason, flags in sorted(aggregated.items()):
        key = f"qa_{reason}"
        if key in counts:
            continue
        count = int(np.count_nonzero(flags))
        counts[key] = count
        counts[f"{key}_fraction"] = _fraction(count)
    return counts


def attrition_table(
    rows: Sequence[Mapping[str, Any]],
    *,
    thresholds: Sequence[int],
    count_columns: Mapping[str, str],
    group_columns: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Build a QA-only attrition table over pre-specified valid-pixel thresholds.

    ``count_columns`` maps a reported label (for example ``NDCI``) to the column
    holding its valid pixel count. Rows whose count is missing are reported as
    unavailable rather than being treated as zero-valid or dropped.
    """

    table: list[dict[str, Any]] = []
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(column) for column in group_columns)
        groups.setdefault(key, []).append(row)

    for key in sorted(groups, key=lambda item: tuple(str(part) for part in item)):
        members = groups[key]
        for label, column in count_columns.items():
            for threshold in thresholds:
                available = [
                    row for row in members if _finite_int(row.get(column)) is not None
                ]
                passing = [
                    row
                    for row in available
                    if _finite_int(row.get(column)) >= int(threshold)
                ]
                entry: dict[str, Any] = {
                    column_name: value
                    for column_name, value in zip(group_columns, key)
                }
                entry.update(
                    {
                        "index": label,
                        "minimum_valid_pixels": int(threshold),
                        "n_records": len(members),
                        "n_records_with_valid_pixel_count": len(available),
                        "n_records_unavailable": len(members) - len(available),
                        "n_passing": len(passing),
                        "pass_fraction_of_available": (
                            len(passing) / len(available) if available else None
                        ),
                        "pass_fraction_of_all_records": (
                            len(passing) / len(members) if members else None
                        ),
                        "threshold_status": "PILOT_NOT_SELECTED",
                    }
                )
                table.append(entry)
    return table


def _finite_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return int(numeric)


def collapse_to_date_observations(
    product_rows: Sequence[Mapping[str, Any]],
    *,
    level: str,
    index_prefixes: Sequence[str] = ("NDCI", "MCI"),
) -> list[dict[str, Any]]:
    """Collapse product-level rows to the frozen calendar-date observation unit.

    The frozen mask already selects one representative L2A product per usable
    date, so this collapse carries that representative through rather than
    re-selecting. Dates without a usable product are retained with their
    failure reason.
    """

    by_date: dict[str, list[Mapping[str, Any]]] = {}
    for row in product_rows:
        by_date.setdefault(str(row.get("date")), []).append(row)

    collapsed: list[dict[str, Any]] = []
    for date in sorted(by_date):
        members = by_date[date]
        chosen = members[0]
        entry: dict[str, Any] = {
            "date": date,
            "year": chosen.get("year"),
            "product_level": level,
            "n_products_considered": len(members),
        }
        for column in (
            "product_id",
            "sensing_datetime",
            "platform",
            "tile",
            "orbit",
            "processing_baseline",
            "l1c_pairing_status",
            "l2a_representative_status",
            "scl_gate_pass",
            "native_qa_incomplete",
            "failure_reason",
        ):
            entry[column] = chosen.get(column)
        for prefix in index_prefixes:
            for suffix in (
                "_valid_pixel_count",
                "_valid_pixel_fraction",
                "_median",
                "_mean",
                "_SD",
                "_IQR",
                "_min",
                "_max",
            ):
                column = f"{prefix}{suffix}"
                entry[column] = chosen.get(column)
        entry["common_B456_valid_count"] = chosen.get("common_B456_valid_count")
        collapsed.append(entry)
    return collapsed


def write_rows(
    rows: Sequence[Mapping[str, Any]],
    path: str | Path,
    *,
    fieldnames: Sequence[str] | None = None,
) -> Path:
    """Write audit rows as UTF-8 CSV with a stable, union-of-keys header."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if fieldnames is None:
        ordered: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        fieldnames = ordered or ["empty"]

    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})
    return destination


def failure_rows(
    rows: Iterable[Mapping[str, Any]], *, reason_column: str = "failure_reason"
) -> list[dict[str, Any]]:
    """Extract the explicit failure records, preserving every failed date."""

    failures: list[dict[str, Any]] = []
    for row in rows:
        reason = row.get(reason_column)
        if reason in (None, ""):
            continue
        failures.append(dict(row))
    return failures


# ---------------------------------------------------------------------------
# Concise Markdown audits
# ---------------------------------------------------------------------------


def _tally(rows: Sequence[Mapping[str, Any]], column: str) -> dict[Any, int]:
    counts: dict[Any, int] = {}
    for row in rows:
        value = row.get(column)
        counts[value] = counts.get(value, 0) + 1
    return counts


def _markdown_table(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    if not rows:
        return "_No rows._\n"
    lines = [
        "| " + " | ".join(str(cell) for cell in header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |"
        )
    return "\n".join(lines) + "\n"


def render_native_qa_audit(
    qa_rows: Sequence[Mapping[str, Any]],
    extraction_rows: Sequence[Mapping[str, Any]],
) -> str:
    """Describe the native QA assets actually found across the real archive.

    Purely descriptive: available L1C/L2A mask families, resolutions, band-
    specific versus product-level QA, layout differences by processing baseline
    and platform, and missing or unsupported mask families. No scientific
    performance claim is made or implied.
    """

    lines = [
        "# Erken real Sentinel-2 native QA inventory audit",
        "",
        "> DRAFT — QA/data-availability description only. No CHLF, no",
        "> index-versus-field performance, no L1C/L2A scientific ranking, no",
        "> reconstruction result.",
        "",
        f"Native QA asset records: {len(qa_rows)}.",
        "",
        "## Mask families by processing level",
        "",
    ]

    families = sorted(
        {(str(row.get("product_level")), str(row.get("qa_family"))) for row in qa_rows}
    )
    table: list[list[Any]] = []
    for level, family in families:
        members = [
            row
            for row in qa_rows
            if str(row.get("product_level")) == level
            and str(row.get("qa_family")) == family
        ]
        present = [row for row in members if row.get("asset_status") == "present"]
        resolutions = sorted(
            {
                row.get("declared_resolution_m")
                for row in present
                if row.get("declared_resolution_m") is not None
            }
        )
        band_specific = sorted(
            {bool(row.get("band_specific")) for row in present if row.get("band_specific") is not None}
        )
        table.append(
            [
                level,
                family,
                len(members),
                len(present),
                ";".join(str(value) for value in resolutions) or "unstated",
                "band-specific"
                if band_specific == [True]
                else "product-level"
                if band_specific == [False]
                else "mixed"
                if band_specific
                else "n/a",
            ]
        )
    lines.append(
        _markdown_table(
            [
                "level",
                "QA family",
                "records",
                "present",
                "declared resolution (m)",
                "scope",
            ],
            table,
        )
    )

    lines += ["", "## Missing or unsupported mask families", ""]
    gaps = [
        row
        for row in qa_rows
        if row.get("asset_status") not in (None, "present")
    ]
    gap_table = [
        [
            key[0],
            key[1],
            key[2],
            count,
        ]
        for key, count in sorted(
            _tally(
                [
                    {
                        "k": (
                            str(row.get("product_level")),
                            str(row.get("qa_family")),
                            str(row.get("asset_status")),
                        )
                    }
                    for row in gaps
                ],
                "k",
            ).items()
        )
    ]
    lines.append(
        _markdown_table(["level", "QA family", "status", "records"], gap_table)
    )

    lines += ["", "## Layout differences by processing baseline and platform", ""]
    layout_rows = [
        [baseline, platform, count]
        for (baseline, platform), count in sorted(
            _tally(
                [
                    {
                        "k": (
                            str(row.get("processing_baseline")),
                            str(row.get("platform")),
                        )
                    }
                    for row in extraction_rows
                    if row.get("processing_baseline")
                ],
                "k",
            ).items()
        )
    ]
    lines.append(
        _markdown_table(["processing baseline", "platform", "products"], layout_rows)
    )

    alignment_rows: list[list[Any]] = []
    for column in sorted(
        {
            key
            for row in extraction_rows
            for key in row
            if key.endswith("_grid_alignment")
        }
    ):
        size_column = column.replace("_grid_alignment", "_native_pixel_size_m")
        for value, count in sorted(
            _tally(extraction_rows, column).items(), key=lambda item: str(item[0])
        ):
            if value is None:
                continue
            sizes = sorted(
                {
                    row.get(size_column)
                    for row in extraction_rows
                    if row.get(column) == value and row.get(size_column) is not None
                }
            )
            alignment_rows.append(
                [
                    column.removeprefix("qa_").removesuffix("_grid_alignment"),
                    ";".join(f"{float(size):g}" for size in sizes) or "unrecorded",
                    value,
                    count,
                ]
            )
    lines += ["", "## Grid handling actually applied", ""]
    lines.append(
        _markdown_table(
            ["layer", "observed native pixel size (m)", "alignment", "records"],
            alignment_rows,
        )
    )

    lines += [
        "",
        "Absence of a mask family is recorded, never treated as clean; affected",
        "observations carry `native_qa_incomplete`.",
        "",
    ]
    return "\n".join(lines)


def render_qa_findings(
    extraction_rows: Sequence[Mapping[str, Any]],
    pairing_rows: Sequence[Mapping[str, Any]],
    attrition_rows: Sequence[Mapping[str, Any]],
    counts: Mapping[str, Any],
) -> str:
    """Summarize QA and data availability before any scientific performance.

    Reports counts, pairing outcomes, valid-pixel distributions and attrition at
    the pre-specified thresholds so a human can freeze the final minimum
    valid-pixel criterion. It never declares a threshold superior and never
    compares L1C with L2A scientifically.
    """

    lines = [
        "# Erken real Sentinel-2 QA and data-availability findings",
        "",
        "> DRAFT — QA-only audit. No CHLF was inspected. No index-versus-field",
        "> performance, retrieval calibration, L1C-vs-L2A scientific ranking,",
        "> reconstruction result or TIMESAT result is produced here.",
        "",
        "## Counts",
        "",
    ]
    lines.append(
        _markdown_table(
            ["quantity", "value"],
            [[key, counts.get(key)] for key in sorted(counts)],
        )
    )

    lines += ["", "## L1C/L2A pairing outcomes", ""]
    lines.append(
        _markdown_table(
            ["pairing status", "dates"],
            [
                [status, count]
                for status, count in sorted(
                    _tally(pairing_rows, "l1c_pairing_status").items(),
                    key=lambda item: str(item[0]),
                )
            ],
        )
    )

    lines += ["", "## Valid-pixel distribution in the frozen 3x3 window", ""]
    distribution: list[list[Any]] = []
    for level in sorted({str(row.get("product_level")) for row in extraction_rows}):
        members = [
            row for row in extraction_rows if str(row.get("product_level")) == level
        ]
        for label, column in (
            ("NDCI", "ndci_valid_pixel_count"),
            ("MCI", "mci_valid_pixel_count"),
            ("common_B456", "common_B456_valid_count"),
        ):
            values = [
                _finite_int(row.get(column))
                for row in members
                if _finite_int(row.get(column)) is not None
            ]
            for pixels in range(0, 10):
                matching = sum(1 for value in values if value == pixels)
                if matching:
                    distribution.append([level, label, pixels, matching])
    lines.append(
        _markdown_table(
            ["level", "index", "valid pixels", "records"], distribution
        )
    )

    lines += ["", "## QA-only attrition at the pre-specified thresholds", ""]
    lines.append(
        _markdown_table(
            [
                "level",
                "index",
                "min valid pixels",
                "records with count",
                "passing",
                "pass fraction",
                "status",
            ],
            [
                [
                    row.get("product_level"),
                    row.get("index"),
                    row.get("minimum_valid_pixels"),
                    row.get("n_records_with_valid_pixel_count"),
                    row.get("n_passing"),
                    None
                    if row.get("pass_fraction_of_available") is None
                    else f"{float(row['pass_fraction_of_available']):.4f}",
                    row.get("threshold_status"),
                ]
                for row in attrition_rows
            ],
        )
    )

    lines += ["", "## Failures retained", ""]
    lines.append(
        _markdown_table(
            ["failure reason", "records"],
            [
                [reason, count]
                for reason, count in sorted(
                    _tally(
                        [
                            row
                            for row in extraction_rows
                            if row.get("failure_reason")
                        ],
                        "failure_reason",
                    ).items(),
                    key=lambda item: str(item[0]),
                )
            ],
        )
    )

    lines += [
        "",
        "## Stopping rule",
        "",
        "The final minimum valid-pixel criterion is **not selected here**. This",
        "audit exists so the human can freeze it before any field-matchup",
        "analysis begins. No threshold is declared scientifically superior.",
        "",
    ]
    return "\n".join(lines)


def write_markdown(text: str, path: str | Path) -> Path:
    """Write a Markdown audit document, creating parent directories."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination
