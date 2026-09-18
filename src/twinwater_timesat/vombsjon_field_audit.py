from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET


AUDIT_VERSION = "vombsjon_field_input_audit_v1.0"
VERIFICATION_DATE = "2026-09-18"
STARTING_COMMIT = "b3aeb4e782d74f7b6ce7d08bad28e61ee9c66a4f"

CSV_COLUMNS = [
    "date",
    "year",
    "chla_fluorometry_ug_L",
    "cyanobacteria_pct_ALA",
    "diatom_dinoflagellate_pct_ALA",
    "green_algae_pct_ALA",
    "cryptomonads_pct_ALA",
    "gps_lat_measured",
    "gps_lon_measured",
    "gps_raw_N",
    "gps_raw_E",
    "distance_measured_to_nominal_m",
    "matchup_lat",
    "matchup_lon",
    "coordinate_source_for_matchup",
    "coordinate_qc",
    "nominal_station_lat",
    "nominal_station_lon",
    "echo_depth_m",
    "integrated_sample_depth_m",
    "wind",
    "field_notes",
    "dicyano_chla_fluorometry_ug_L",
    "chla_Dryad_vs_DiCyano",
    "canonical_chla_source",
    "metadata_source",
]

SOURCE_SPECS = [
    {
        "request_filename": "Vombsjon_S2_field_matchup_master(1).csv",
        "actual_supplied_filename": "Vombsjon_S2_field_matchup_master.csv",
        "repository_path": "data/sources/vombsjon/Vombsjon_S2_field_matchup_master.csv",
        "sha256": "115f0ae9dd3545f889c86e2cb0875ef69107db4038dfdb0772fd2e57f6281d37",
        "source": (
            "User-supplied harmonized table; internal provenance columns identify "
            "EW_Data_All_dryad.xlsx Table5, a 2019-2020 DiCyano comparison, and "
            "Metadata_Vombsjon_SR.xlsx"
        ),
        "intended_use": (
            "Canonical Vomb field Chl-a table, coordinate provenance, and future "
            "lake-specific field-satellite matchup audit"
        ),
        "licence_status": (
            "Not stated in the CSV; Dryad dataset licence not independently verified "
            "from the supplied files"
        ),
    },
    {
        "request_filename": "Metadata_Vombsjon_SR.xlsx",
        "actual_supplied_filename": "Metadata_Vombsjon_SR.xlsx",
        "repository_path": "data/sources/vombsjon/Metadata_Vombsjon_SR.xlsx",
        "sha256": "a210a425bd2387721600232b1f69edf3e7770885439de1ed7aff1e8c51ca2f50",
        "source": "User-supplied field metadata workbook with 2019 and 2020 sheets",
        "intended_use": "Dates, echo depth, measured GPS, wind, and field-note provenance",
        "licence_status": "No licence statement found in the workbook",
    },
    {
        "request_filename": "Vombsjon_Dryad_README.md",
        "actual_supplied_filename": "Vombsjon_Dryad_README.md",
        "repository_path": "data/sources/vombsjon/Vombsjon_Dryad_README.md",
        "sha256": "1255ec2520166547c9207071cfb957da61ed55e7f4fbd238c4cbb55d90ab4aed",
        "source": "User-supplied README associated with the Rabow et al. Dryad data package",
        "intended_use": "Dataset table definitions, missing-value conventions, and provenance",
        "licence_status": (
            "README states that Table 3 data are CC BY and separately hosted; it does "
            "not state a licence for the README or full supplied package"
        ),
    },
    {
        "request_filename": "Rabow_2025_Harmful_Algae.pdf",
        "actual_supplied_filename": "Rabow_2025_Harmful_Algae.pdf",
        "repository_path": "references/vombsjon/Rabow_2025_Harmful_Algae.pdf",
        "sha256": "d25b67cb4a6ec021f417b895e6b59cf189d6759f505402d9e6f417c5fcc79bf8",
        "source": (
            "Rabow et al. (2025), Harmful Algae 142, 102787, "
            "doi:10.1016/j.hal.2024.102787"
        ),
        "intended_use": "Sampling design, laboratory Chl-a method, site context, and 2018 regime",
        "licence_status": "CC BY 4.0 stated on article page 1",
    },
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ").strip()
    if text == "-":
        return ""
    return re.sub(r"\s+", " ", text)


def _float_or_none(value: Any) -> float | None:
    text = _normalize_text(value)
    if not text:
        return None
    return float(text)


def _excel_date(value: Any) -> date | None:
    if value is None or _normalize_text(value) == "":
        return None
    if isinstance(value, (int, float)):
        return date(1899, 12, 30) + timedelta(days=int(value))
    text = _normalize_text(value)
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    return None


def _column_from_cell_reference(reference: str) -> str:
    match = re.match(r"([A-Z]+)", reference)
    if not match:
        raise ValueError(f"Invalid XLSX cell reference: {reference}")
    return match.group(1)


def read_simple_xlsx(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Read the small source workbook using only the Python standard library.

    The source contains shared strings and scalar numeric cells only. This parser
    intentionally returns values without saving or normalizing the workbook.
    """

    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    office_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    with zipfile.ZipFile(path) as archive:
        strings_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        shared_strings = [
            "".join(node.text or "" for node in item.findall(f".//{{{main_ns}}}t"))
            for item in strings_root.findall(f"{{{main_ns}}}si")
        ]

        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationships = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationships_root.findall(f"{{{rel_ns}}}Relationship")
        }

        sheets: dict[str, list[dict[str, Any]]] = {}
        for sheet in workbook_root.findall(f".//{{{main_ns}}}sheet"):
            sheet_name = sheet.attrib["name"]
            relationship_id = sheet.attrib[f"{{{office_rel_ns}}}id"]
            target = relationships[relationship_id]
            sheet_path = target if target.startswith("xl/") else f"xl/{target}"
            sheet_root = ET.fromstring(archive.read(sheet_path))
            rows: list[dict[str, Any]] = []
            for row in sheet_root.findall(f".//{{{main_ns}}}row"):
                values: dict[str, Any] = {"_row": int(row.attrib["r"])}
                for cell in row.findall(f"{{{main_ns}}}c"):
                    column = _column_from_cell_reference(cell.attrib["r"])
                    value_node = cell.find(f"{{{main_ns}}}v")
                    if value_node is None or value_node.text is None:
                        value: Any = None
                    elif cell.attrib.get("t") == "s":
                        value = shared_strings[int(value_node.text)]
                    else:
                        number = float(value_node.text)
                        value = int(number) if number.is_integer() else number
                    values[column] = value
                rows.append(values)
            sheets[sheet_name] = rows
    return sheets


def read_metadata_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for sheet_name, rows in read_simple_xlsx(path).items():
        for row in rows:
            if row["_row"] < 3:
                continue
            record_date = _excel_date(row.get("A"))
            if record_date is None or record_date.year != int(sheet_name):
                continue
            records.append(
                {
                    "date": record_date.isoformat(),
                    "year": record_date.year,
                    "sheet": sheet_name,
                    "sheet_row": row["_row"],
                    "echo_depth_m": _float_or_none(row.get("B")),
                    "gps_raw_N": _normalize_text(row.get("C")),
                    "gps_raw_E": _normalize_text(row.get("D")),
                    "wind": _normalize_text(row.get("E")),
                    "field_notes": _normalize_text(row.get("F")),
                }
            )
    return records


def parse_gps_coordinate(value: Any) -> tuple[float, str]:
    if isinstance(value, (int, float)):
        return float(value), "decimal_degrees"
    text = _normalize_text(value)
    if not text:
        raise ValueError("GPS coordinate is missing")
    tokens = text.replace("°", " ").replace("′", " ").replace("\"", " ").split()
    numbers = [float(token) for token in tokens]
    if len(numbers) == 1:
        return numbers[0], "decimal_degrees"
    if len(numbers) == 2:
        degrees, minutes = numbers
        return degrees + minutes / 60.0, "degrees_decimal_minutes"
    if len(numbers) == 3:
        degrees, minutes, seconds = numbers
        return degrees + minutes / 60.0 + seconds / 3600.0, "degrees_minutes_seconds"
    raise ValueError(f"Unsupported GPS coordinate format: {value!r}")


def haversine_m(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    radius_m = 6_371_000.0
    phi_a = math.radians(latitude_a)
    phi_b = math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    term = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2.0) ** 2
    )
    return 2.0 * radius_m * math.asin(math.sqrt(term))


def _coordinate_candidate_minute_36(raw_longitude: str) -> float | None:
    tokens = raw_longitude.split()
    if len(tokens) != 3 or tokens[1] != "35":
        return None
    return float(tokens[0]) + 36.0 / 60.0 + float(tokens[2]) / 3600.0


def read_field_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != CSV_COLUMNS:
            raise ValueError(f"Unexpected Vomb field CSV columns: {reader.fieldnames}")
        rows = list(reader)
    return rows


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def build_source_manifest(repo_root: Path) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for spec in SOURCE_SPECS:
        path = repo_root / spec["repository_path"]
        actual_hash = sha256_file(path)
        if actual_hash != spec["sha256"]:
            raise ValueError(f"Source checksum mismatch for {path}: {actual_hash}")
        manifest.append(
            {
                **spec,
                "size_bytes": path.stat().st_size,
                "verification_date": VERIFICATION_DATE,
                "byte_preserved": "yes",
            }
        )
    return manifest


def audit_field_inputs(repo_root: Path) -> dict[str, Any]:
    csv_path = repo_root / SOURCE_SPECS[0]["repository_path"]
    xlsx_path = repo_root / SOURCE_SPECS[1]["repository_path"]
    rows = read_field_csv(csv_path)
    metadata_records = read_metadata_records(xlsx_path)
    metadata_by_date = {record["date"]: record for record in metadata_records}

    dates = [date.fromisoformat(row["date"]) for row in rows]
    year_counts = Counter(item.year for item in dates)
    duplicate_dates = sorted(value for value, count in Counter(row["date"] for row in rows).items() if count > 1)
    missing_counts = {
        column: sum(_normalize_text(row[column]) == "" for row in rows) for column in CSV_COLUMNS
    }

    summary_rows: list[dict[str, Any]] = []

    def add_summary(category: str, metric: str, value: Any, status: str, note: str = "") -> None:
        summary_rows.append(
            {"category": category, "metric": metric, "value": value, "status": status, "note": note}
        )

    add_summary("dataset", "row_count", len(rows), "pass" if len(rows) == 54 else "fail")
    add_summary("dataset", "date_min", min(dates).isoformat(), "pass")
    add_summary("dataset", "date_max", max(dates).isoformat(), "pass")
    add_summary("dataset", "duplicate_date_count", len(duplicate_dates), "pass" if not duplicate_dates else "fail")
    for year, expected in ((2018, 6), (2019, 22), (2020, 26)):
        add_summary(
            "dataset",
            f"rows_{year}",
            year_counts[year],
            "pass" if year_counts[year] == expected else "fail",
        )
    add_summary("unit", "chla_fluorometry_ug_L", "micrograms per litre", "confirmed_from_header_and_paper")
    add_summary("unit", "ALA_composition", "percent", "confirmed_from_header_and_README")
    add_summary("unit", "echo_depth_m", "metres of lake water at sampling position", "confirmed_from_XLSX")
    add_summary("unit", "integrated_sample_depth_m", "metres below surface as 0-2 or 0-6", "confirmed_from_paper")
    add_summary(
        "unit",
        "coordinates",
        "N/E geographic degrees converted to decimal degrees",
        "conversion_verified_datum_label_requires_confirmation",
    )
    for column in CSV_COLUMNS:
        add_summary("missingness", column, missing_counts[column], "reported")

    chla_values = [float(row["chla_fluorometry_ug_L"]) for row in rows]
    if not all(math.isfinite(value) and value >= 0.0 for value in chla_values):
        raise ValueError("Chl-a contains a negative or non-finite value")
    add_summary("range", "chla_fluorometry_ug_L_min", min(chla_values), "reported")
    add_summary("range", "chla_fluorometry_ug_L_max", max(chla_values), "reported")

    expected_depth_by_year = {2018: "0-2", 2019: "0-6", 2020: "0-6"}
    depth_mismatches = [
        row["date"]
        for row in rows
        if row["integrated_sample_depth_m"] != expected_depth_by_year[int(row["year"])]
    ]
    add_summary(
        "sampling_depth",
        "year_specific_integrated_depth_mismatch_count",
        len(depth_mismatches),
        "pass" if not depth_mismatches else "fail",
    )

    dicyano_counts = Counter(row["chla_Dryad_vs_DiCyano"] for row in rows)
    add_summary("provenance", "Dryad_DiCyano_exact_matches", dicyano_counts["exact_match"], "pass")
    add_summary(
        "provenance",
        "Dryad_dates_not_in_2019_2020_DiCyano_file",
        dicyano_counts["not_in_DiCyano_2019_2020_file"],
        "reported_2018_only",
    )

    date_audit_rows: list[dict[str, Any]] = []
    metadata_discrepancy_count = 0
    for row in rows:
        record_date = date.fromisoformat(row["date"])
        metadata = metadata_by_date.get(row["date"])
        discrepancies: list[str] = []
        if record_date.year in (2019, 2020):
            if metadata is None:
                discrepancies.append("date_missing_from_XLSX")
            else:
                csv_echo = _float_or_none(row["echo_depth_m"])
                metadata_echo = metadata["echo_depth_m"]
                if csv_echo is None and metadata_echo is not None or csv_echo is not None and metadata_echo is None:
                    discrepancies.append("echo_depth_missingness")
                elif csv_echo is not None and not math.isclose(csv_echo, metadata_echo, abs_tol=1e-12):
                    discrepancies.append("echo_depth_value")
                for csv_field, metadata_field in (
                    ("gps_raw_N", "gps_raw_N"),
                    ("gps_raw_E", "gps_raw_E"),
                    ("wind", "wind"),
                    ("field_notes", "field_notes"),
                ):
                    if _normalize_text(row[csv_field]) != _normalize_text(metadata[metadata_field]):
                        discrepancies.append(csv_field)
        metadata_status = "not_applicable_2018" if record_date.year == 2018 else "match" if not discrepancies else "mismatch"
        metadata_discrepancy_count += bool(discrepancies)
        date_audit_rows.append(
            {
                "date": row["date"],
                "year": row["year"],
                "chla_fluorometry_ug_L": row["chla_fluorometry_ug_L"],
                "metadata_row_present": "yes" if metadata else "no",
                "metadata_sheet": metadata["sheet"] if metadata else "",
                "metadata_sheet_row": metadata["sheet_row"] if metadata else "",
                "metadata_comparison_status": metadata_status,
                "metadata_discrepancies": ";".join(discrepancies),
                "echo_depth_m": row["echo_depth_m"],
                "integrated_sample_depth_m": row["integrated_sample_depth_m"],
                "coordinate_source_for_matchup": row["coordinate_source_for_matchup"],
                "coordinate_qc": row["coordinate_qc"],
                "matchup_lat": row["matchup_lat"],
                "matchup_lon": row["matchup_lon"],
                "field_notes_present": "yes" if _normalize_text(row["field_notes"]) else "no",
            }
        )
    add_summary(
        "XLSX_crosscheck",
        "CSV_2019_2020_rows_with_metadata_discrepancy",
        metadata_discrepancy_count,
        "pass" if metadata_discrepancy_count == 0 else "fail",
    )

    csv_date_set = set(row["date"] for row in rows)
    metadata_only_dates = sorted(record["date"] for record in metadata_records if record["date"] not in csv_date_set)
    add_summary(
        "XLSX_crosscheck",
        "metadata_dates_not_in_field_chla_CSV",
        ";".join(metadata_only_dates),
        "reported",
        "2019-05-02 has field metadata but is not a canonical Chl-a observation",
    )

    coordinate_rows: list[dict[str, Any]] = []
    coordinate_formats: Counter[str] = Counter()
    coordinate_mismatch_count = 0
    distance_mismatch_count = 0
    for row in rows:
        if not _normalize_text(row["gps_raw_N"]):
            continue
        parsed_latitude, latitude_format = parse_gps_coordinate(row["gps_raw_N"])
        parsed_longitude, longitude_format = parse_gps_coordinate(row["gps_raw_E"])
        coordinate_format = latitude_format if latitude_format == longitude_format else f"{latitude_format}+{longitude_format}"
        coordinate_formats[coordinate_format] += 1
        csv_latitude = float(row["gps_lat_measured"])
        csv_longitude = float(row["gps_lon_measured"])
        coordinate_difference = max(abs(parsed_latitude - csv_latitude), abs(parsed_longitude - csv_longitude))
        coordinate_matches = coordinate_difference <= 1e-9
        coordinate_mismatch_count += not coordinate_matches
        nominal_latitude = float(row["nominal_station_lat"])
        nominal_longitude = float(row["nominal_station_lon"])
        recomputed_distance = haversine_m(parsed_latitude, parsed_longitude, nominal_latitude, nominal_longitude)
        supplied_distance = float(row["distance_measured_to_nominal_m"])
        distance_difference = abs(recomputed_distance - supplied_distance)
        distance_matches = distance_difference <= 0.02
        distance_mismatch_count += not distance_matches
        candidate_longitude = _coordinate_candidate_minute_36(row["gps_raw_E"])
        candidate_distance = (
            haversine_m(parsed_latitude, candidate_longitude, nominal_latitude, nominal_longitude)
            if candidate_longitude is not None
            else None
        )
        flagged = row["coordinate_source_for_matchup"] == "measured_GPS_flagged_unresolved"
        coordinate_rows.append(
            {
                "date": row["date"],
                "gps_raw_N": row["gps_raw_N"],
                "gps_raw_E": row["gps_raw_E"],
                "format": coordinate_format,
                "parsed_latitude": f"{parsed_latitude:.12f}",
                "parsed_longitude": f"{parsed_longitude:.12f}",
                "csv_gps_lat_measured": row["gps_lat_measured"],
                "csv_gps_lon_measured": row["gps_lon_measured"],
                "conversion_matches_csv": "yes" if coordinate_matches else "no",
                "recomputed_distance_to_nominal_m": f"{recomputed_distance:.6f}",
                "csv_distance_to_nominal_m": row["distance_measured_to_nominal_m"],
                "distance_matches_csv": "yes" if distance_matches else "no",
                "coordinate_source_for_matchup": row["coordinate_source_for_matchup"],
                "coordinate_qc": row["coordinate_qc"],
                "matchup_lat": row["matchup_lat"],
                "matchup_lon": row["matchup_lon"],
                "hypothetical_longitude_if_minute_36": (
                    f"{candidate_longitude:.12f}" if candidate_longitude is not None else ""
                ),
                "hypothetical_distance_if_minute_36_m": (
                    f"{candidate_distance:.6f}" if candidate_distance is not None else ""
                ),
                "audit_status": "flagged_unresolved_do_not_correct" if flagged else "ok",
            }
        )
    for coordinate_format, count in sorted(coordinate_formats.items()):
        add_summary("coordinates", f"format_{coordinate_format}", count, "reported")
    add_summary(
        "coordinates",
        "parsed_coordinate_mismatch_count",
        coordinate_mismatch_count,
        "pass" if coordinate_mismatch_count == 0 else "fail",
    )
    add_summary(
        "coordinates",
        "distance_recalculation_mismatch_count",
        distance_mismatch_count,
        "pass" if distance_mismatch_count == 0 else "fail",
    )
    flagged_dates = sorted(
        row["date"] for row in rows if row["coordinate_source_for_matchup"] == "measured_GPS_flagged_unresolved"
    )
    add_summary("coordinates", "unresolved_coordinate_dates", ";".join(flagged_dates), "retain_QC_no_correction")

    nominal_rows = [row for row in rows if row["coordinate_source_for_matchup"] == "paper_nominal_station"]
    measured_rows = [row for row in rows if row["coordinate_source_for_matchup"] == "measured_GPS"]
    flagged_rows = [row for row in rows if row["coordinate_source_for_matchup"] == "measured_GPS_flagged_unresolved"]
    nominal_matchup_errors = [
        row["date"]
        for row in nominal_rows
        if row["matchup_lat"] != row["nominal_station_lat"] or row["matchup_lon"] != row["nominal_station_lon"]
    ]
    measured_matchup_errors = [
        row["date"]
        for row in measured_rows
        if row["matchup_lat"] != row["gps_lat_measured"] or row["matchup_lon"] != row["gps_lon_measured"]
    ]
    flagged_matchup_errors = [
        row["date"] for row in flagged_rows if row["matchup_lat"] or row["matchup_lon"]
    ]
    add_summary("coordinates", "paper_nominal_station_rows", len(nominal_rows), "reported")
    add_summary("coordinates", "measured_GPS_rows", len(measured_rows), "reported")
    add_summary("coordinates", "flagged_measured_GPS_rows", len(flagged_rows), "reported")
    add_summary(
        "coordinates",
        "matchup_coordinate_rule_violation_count",
        len(nominal_matchup_errors) + len(measured_matchup_errors) + len(flagged_matchup_errors),
        "pass" if not nominal_matchup_errors and not measured_matchup_errors and not flagged_matchup_errors else "fail",
    )

    return {
        "source_manifest": build_source_manifest(repo_root),
        "summary_rows": summary_rows,
        "date_audit_rows": date_audit_rows,
        "coordinate_rows": coordinate_rows,
        "core": {
            "row_count": len(rows),
            "year_counts": dict(sorted(year_counts.items())),
            "date_min": min(dates).isoformat(),
            "date_max": max(dates).isoformat(),
            "duplicate_dates": duplicate_dates,
            "missing_counts": missing_counts,
            "metadata_records": len(metadata_records),
            "metadata_only_dates": metadata_only_dates,
            "metadata_discrepancy_count": metadata_discrepancy_count,
            "coordinate_formats": dict(sorted(coordinate_formats.items())),
            "coordinate_mismatch_count": coordinate_mismatch_count,
            "distance_mismatch_count": distance_mismatch_count,
            "flagged_dates": flagged_dates,
        },
    }


def _report_markdown(audit: dict[str, Any]) -> str:
    core = audit["core"]
    coordinate_by_date = {row["date"]: row for row in audit["coordinate_rows"]}
    flagged_lines = []
    for flagged_date in core["flagged_dates"]:
        item = coordinate_by_date[flagged_date]
        flagged_lines.append(
            f"- `{flagged_date}`: source `{item['gps_raw_N']}, {item['gps_raw_E']}` converts to "
            f"`{item['parsed_latitude']}, {item['parsed_longitude']}` and is about "
            f"{float(item['recomputed_distance_to_nominal_m']):.1f} m from the nominal station. "
            f"Changing longitude minutes from 35 to 36 would produce "
            f"`{item['hypothetical_longitude_if_minute_36']}` and about "
            f"{float(item['hypothetical_distance_if_minute_36_m']):.1f} m, but this is only a "
            "diagnostic candidate and was not applied."
        )

    hashes = "\n".join(
        f"| `{item['repository_path']}` | `{item['sha256']}` | {item['size_bytes']} | {item['licence_status']} |"
        for item in audit["source_manifest"]
    )
    return f"""# Vombsjön field-input audit v1.0

**Audit date:** {VERIFICATION_DATE}
**Starting commit:** `{STARTING_COMMIT}`
**Scope:** field-source intake and input verification only. No Sentinel-2 product audit and no Vomb reconstruction performance were run.

## Source identity

All four repository files are byte-identical to the readable user-supplied files. The requested CSV name included `(1)`, but the available file was already named `Vombsjon_S2_field_matchup_master.csv`; the actual filename was retained as the canonical repository name.

| Repository file | SHA256 | Bytes | Licence information actually verified |
|---|---|---:|---|
{hashes}

The article states that its underlying manuscript dataset is available from Dryad at <https://doi.org/10.5061/dryad.02v6wwq7s>. The supplied files do not establish the exact Dryad version or a package-wide data licence, so those remain unverified. Article page 1 explicitly states CC BY 4.0 for the PDF.

## Confirmed field-table facts

- The canonical CSV contains **{core['row_count']} unique observation dates** from **{core['date_min']} to {core['date_max']}**: 2018 = {core['year_counts'][2018]}, 2019 = {core['year_counts'][2019]}, and 2020 = {core['year_counts'][2020]}. There are no duplicate dates.
- `chla_fluorometry_ug_L` has no missing values and ranges from 0.896 to 125.7 µg L⁻¹. The paper reports laboratory fluorometry with a TD-700 fluorometer.
- All 48 observations from 2019-2020 are labelled exact matches to the DiCyano comparison file; the six 2018 observations are explicitly outside that comparison file.
- The metadata workbook contains 23 dated rows in 2019 and 26 in 2020. Every one of the 48 canonical 2019-2020 Chl-a dates matches the workbook date, echo depth, raw GPS, wind and field notes. `2019-05-02` is a metadata-only field occasion and is not a canonical Chl-a record.
- The 23 measured coordinate records use three formats: decimal degrees ({core['coordinate_formats'].get('decimal_degrees', 0)}), degrees plus decimal minutes ({core['coordinate_formats'].get('degrees_decimal_minutes', 0)}), and degrees-minutes-seconds ({core['coordinate_formats'].get('degrees_minutes_seconds', 0)}). All convert to the decimal values stored in the CSV, and all supplied distances to the nominal station reproduce within 0.02 m using a haversine calculation.
- The CSV separates actual measured GPS (21 usable matchup rows), nominal-station fallback (31 rows), and two unresolved measured-GPS rows whose matchup coordinates remain blank. The fixed nominal station is 55.6775 N, 13.60889 E.
- The paper reports a roughly 7 m-deep sampling site and the XLSX `Echo depth` records the local lake depth (6.6-9.0 m where present). This is distinct from the integrated sampling interval: 0-2 m in 2018 and 0-6 m in 2019-2020. The CSV preserves that year-specific distinction on every row.
- The paper reports sampling every two weeks from late June to mid-September in 2018, then weekly from May to October in 2019-2020. It describes volume-integrated tube sampling and laboratory fluorometric Chl-a analysis. The supplied README identifies Table 5 as the Chl-a fluorometry and AlgaeLabAnalyser community-composition table.

## Issues and impact

{chr(10).join(flagged_lines)}

These source values remain unchanged. The two records retain their field Chl-a values and remain available for field-series/ecological use, but an actual-GPS-centred satellite matchup is unavailable until the longitude notation is confirmed. They must not be silently moved to the nominal station or to a hypothetical corrected coordinate.

Other incompleteness is explicit rather than repaired: measured GPS is absent on 31 dates, echo depth is absent on nine dates (all six 2018 dates plus 2019-05-08, 2019-07-30, and 2020-05-06), and AlgaeLabAnalyser composition is absent on 2018-06-25. These gaps do not remove any of the 54 fluorometric Chl-a observations. Wind, notes and the field metadata workbook are unavailable for the six 2018 dates.

## Still to verify

1. Confirm with the original field record or data authors whether the longitude minutes on 2020-06-10 and 2020-06-24 are 35 or 36. Preserve both original strings and QC flags regardless of any later governed correction.
2. Confirm the coordinate reference/datum terminology for the handheld GPS records. The supplied N/E strings and paper coordinates support the documented angular conversions, but the source files do not provide a machine-readable CRS declaration.
3. Verify the exact Dryad dataset version and licence applicable to the CSV/XLSX/README. The article is CC BY 4.0, but that does not by itself prove the data-file licence.
4. Supply and audit the Vomb Sentinel-2 product inventory and ACOLITE outputs. No satellite product was supplied in this intake, so scene identity, processing baseline, ROI coverage, QA, ACOLITE versions/settings, and same-day deduplication remain pending.

## Analysis boundary

This audit completes field-material intake and verification only. It does not change the frozen MCI/ACOLITE choice, spatial support, QC, scaling, holdout design, TIMESAT settings, metrics or failure rules. It does not calculate Vomb reconstruction performance.
"""


def write_audit_outputs(repo_root: Path) -> dict[str, Path]:
    audit = audit_field_inputs(repo_root)
    output_root = repo_root / "results/vombsjon/field_input_audit/v1.0"
    output_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "source_manifest": output_root / "vombsjon_field_source_manifest.csv",
        "summary": output_root / "vombsjon_field_audit_summary.csv",
        "dates": output_root / "vombsjon_field_date_audit.csv",
        "coordinates": output_root / "vombsjon_field_coordinate_audit.csv",
        "report": output_root / "vombsjon_field_input_audit_report.md",
        "manifest": output_root / "vombsjon_field_input_audit_manifest.json",
    }

    _write_csv(
        paths["source_manifest"],
        [
            "request_filename",
            "actual_supplied_filename",
            "repository_path",
            "sha256",
            "size_bytes",
            "source",
            "intended_use",
            "licence_status",
            "verification_date",
            "byte_preserved",
        ],
        audit["source_manifest"],
    )
    _write_csv(paths["summary"], ["category", "metric", "value", "status", "note"], audit["summary_rows"])
    _write_csv(
        paths["dates"],
        [
            "date",
            "year",
            "chla_fluorometry_ug_L",
            "metadata_row_present",
            "metadata_sheet",
            "metadata_sheet_row",
            "metadata_comparison_status",
            "metadata_discrepancies",
            "echo_depth_m",
            "integrated_sample_depth_m",
            "coordinate_source_for_matchup",
            "coordinate_qc",
            "matchup_lat",
            "matchup_lon",
            "field_notes_present",
        ],
        audit["date_audit_rows"],
    )
    _write_csv(
        paths["coordinates"],
        [
            "date",
            "gps_raw_N",
            "gps_raw_E",
            "format",
            "parsed_latitude",
            "parsed_longitude",
            "csv_gps_lat_measured",
            "csv_gps_lon_measured",
            "conversion_matches_csv",
            "recomputed_distance_to_nominal_m",
            "csv_distance_to_nominal_m",
            "distance_matches_csv",
            "coordinate_source_for_matchup",
            "coordinate_qc",
            "matchup_lat",
            "matchup_lon",
            "hypothetical_longitude_if_minute_36",
            "hypothetical_distance_if_minute_36_m",
            "audit_status",
        ],
        audit["coordinate_rows"],
    )
    paths["report"].write_text(_report_markdown(audit), encoding="utf-8")

    output_hashes = {
        str(path.relative_to(repo_root)): sha256_file(path)
        for key, path in paths.items()
        if key != "manifest"
    }
    implementation_paths = [
        repo_root / "src/twinwater_timesat/vombsjon_field_audit.py",
        repo_root / "scripts/39_audit_vombsjon_field_sources.py",
        repo_root / "scripts/40_validate_vombsjon_field_audit.py",
        repo_root / "tests/test_vombsjon_field_audit.py",
    ]
    manifest = {
        "schema_version": "vombsjon_field_input_audit_manifest_v1",
        "audit_version": AUDIT_VERSION,
        "audit_date": VERIFICATION_DATE,
        "starting_commit": STARTING_COMMIT,
        "scope": "field_source_intake_and_input_verification_only",
        "field_material_audit_complete": True,
        "satellite_product_audit_complete": False,
        "vomb_reconstruction_performance_run": False,
        "frozen_transfer_settings_changed": False,
        "inputs": {
            item["repository_path"]: item["sha256"] for item in audit["source_manifest"]
        },
        "implementation": {
            str(path.relative_to(repo_root)): sha256_file(path) for path in implementation_paths
        },
        "outputs": output_hashes,
        "core_audit": audit["core"],
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return paths


def validate_written_audit(repo_root: Path) -> dict[str, Any]:
    output_root = repo_root / "results/vombsjon/field_input_audit/v1.0"
    manifest_path = output_root / "vombsjon_field_input_audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = audit_field_inputs(repo_root)

    recomputed_core = json.loads(json.dumps(audit["core"], sort_keys=True))
    if manifest["core_audit"] != recomputed_core:
        raise ValueError("Stored Vomb field audit core does not match recomputed audit")
    for relative_path, expected_hash in manifest["inputs"].items():
        actual_hash = sha256_file(repo_root / relative_path)
        if actual_hash != expected_hash:
            raise ValueError(f"Input checksum mismatch: {relative_path}")
    for relative_path, expected_hash in manifest["implementation"].items():
        actual_hash = sha256_file(repo_root / relative_path)
        if actual_hash != expected_hash:
            raise ValueError(f"Implementation checksum mismatch: {relative_path}")
    for relative_path, expected_hash in manifest["outputs"].items():
        actual_hash = sha256_file(repo_root / relative_path)
        if actual_hash != expected_hash:
            raise ValueError(f"Output checksum mismatch: {relative_path}")

    expected_core = {
        "row_count": 54,
        "year_counts": {2018: 6, 2019: 22, 2020: 26},
        "duplicate_dates": [],
        "metadata_only_dates": ["2019-05-02"],
        "metadata_discrepancy_count": 0,
        "coordinate_mismatch_count": 0,
        "distance_mismatch_count": 0,
        "flagged_dates": ["2020-06-10", "2020-06-24"],
    }
    for key, expected_value in expected_core.items():
        if audit["core"][key] != expected_value:
            raise ValueError(f"Unexpected audit result for {key}: {audit['core'][key]}")
    return manifest
