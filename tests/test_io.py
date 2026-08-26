from pathlib import Path

import pandas as pd
import pytest

from twinwater_timesat.io import ErkenIngestionError, read_erken_csv


def write_source(path: Path, table: str) -> None:
    path.write_text("TITLE: synthetic\nCOMMENT: test\n####\n" + table, encoding="utf-8")


def test_metadata_header_and_explicit_date_parsing(tmp_path: Path) -> None:
    source = tmp_path / "erken.csv"
    write_source(
        source,
        "TIMESTAMP,CHLF,PRESENCE_ICE\n2020-02-28,1.25,0\n2020-02-29,2.5,1\n",
    )
    result = read_erken_csv(source)

    assert result.header_line_number == 4
    assert result.data["date"].tolist() == [pd.Timestamp("2020-02-28"), pd.Timestamp("2020-02-29")]
    assert result.data["doy"].tolist() == [59, 60]
    assert result.data["CHLF"].tolist() == [1.25, 2.5]
    assert result.data["ice_free"].tolist() == [True, False]


def test_invalid_date_fails_clearly(tmp_path: Path) -> None:
    source = tmp_path / "erken.csv"
    write_source(source, "TIMESTAMP,CHLF,PRESENCE_ICE\n02/29/2020,1.0,0\n")

    with pytest.raises(ErkenIngestionError, match="YYYY-MM-DD"):
        read_erken_csv(source)


def test_duplicate_dates_are_preserved(tmp_path: Path) -> None:
    source = tmp_path / "erken.csv"
    write_source(
        source,
        "TIMESTAMP,CHLF,PRESENCE_ICE\n2021-01-01,1.0,0\n2021-01-01,2.0,0\n",
    )
    result = read_erken_csv(source)

    assert len(result.data) == 2
    assert result.data["date"].duplicated(keep=False).all()


def test_ambiguous_multiple_headers_fail(tmp_path: Path) -> None:
    source = tmp_path / "erken.csv"
    source.write_text(
        "TIMESTAMP,CHLF,PRESENCE_ICE\nTIMESTAMP,CHLF,PRESENCE_ICE\n",
        encoding="utf-8",
    )
    with pytest.raises(ErkenIngestionError, match="exactly one"):
        read_erken_csv(source)
