import csv
import hashlib
import json
from pathlib import Path

import pytest

from borehole_gis.readers import parse_ags, read_ags, read_bc_csv
from borehole_gis.validate import validate

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture
def ags_text():
    return (SAMPLES / "bgs_bh01.ags").read_text()


def changed(tmp_path, text):
    path = tmp_path / "test.ags"
    path.write_text(text)
    return path


def test_public_ags():
    ds = validate(read_ags(SAMPLES / "bgs_bh01.ags", "EPSG:27700"))
    assert ds.errors == 0
    assert len(ds.holes) == 1 and len(ds.intervals) == 6 and len(ds.spts) == 5
    assert ds.spts[0].n == 17
    assert ds.spts[-1].n is None and ds.spts[-1].remark
    assert [i.code for i in ds.issues] == ["missing_spt_n", "missing_spt_n"]


def test_public_bc():
    ds = validate(read_bc_csv(SAMPLES / "bc_boreholes.csv", "m"))
    assert ds.errors == 0 and len(ds.holes) == 4 and len(ds.intervals) == 17
    assert len(ds.issues) == 1 and ds.issues[0].code == "gap"
    assert "4.9 to 5.9" in ds.issues[0].message


@pytest.mark.parametrize("sample", ["bc_boreholes.csv", "bgs_bh01.ags"])
def test_provenance_checksum(sample):
    path = SAMPLES / sample
    meta = json.loads(path.with_suffix(".source.json").read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["sha256"]
    assert meta["license"] and (meta.get("query_url") or meta.get("source_url"))


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda s: s.replace('"GROUP","PROJ"', '"GROUP","OTHER"'), "missing_group"),
        (lambda s: s.replace('"GEOL_BASE"', '"GEOL_END"'), "missing_heading"),
        (lambda s: s.replace('"UNIT","","m","m",""', '"UNIT","","fathom","m",""'), "invalid_unit"),
        (lambda s: s.replace('"UNIT","","m","m","m"', '"UNIT","","ft","m","m"'), "coordinate_unit"),
        (lambda s: s.replace('"DATA","BH01","1.00","17"', '"DATA","BH01","NaN","17"'), "invalid_number"),
        (lambda s: s.replace('"2DP","2DP","X"', '"UNKNOWN","2DP","X"'), "undefined_type"),
    ],
)
def test_ags_validation_failures(tmp_path, ags_text, mutation, code):
    text = mutation(ags_text)
    assert text != ags_text
    ds = validate(read_ags(changed(tmp_path, text), "EPSG:27700"))
    assert code in [i.code for i in ds.issues]
    assert ds.errors


@pytest.mark.parametrize(
    "text",
    [
        '"DATA","x"\n',
        '"GROUP","GEOL"\n"HEADING","A","A"\n',
        '"GROUP","GEOL"\n"GROUP","GEOL"\n',
        '"GROUP","GEOL"\n"HEADING","A","B"\n"DATA","1"\n',
        '"GROUP","GEOL"\n"HEADING","A"\n"UNIT",""\n"UNIT",""\n',
        '"GROUP","GEOL"\n"HEADING","A"\n"OTHER",""\n',
        '"GROUP","GEOL"\n"HEADING","A"\n"DATA","x"\n"TYPE","X"\n',
    ],
)
def test_structural_corruption(tmp_path, text):
    with pytest.raises(ValueError):
        parse_ags(changed(tmp_path, text))


def test_quoted_multiline_csv(tmp_path):
    path = changed(
        tmp_path,
        '\ufeff"GROUP","GEOL"\n"HEADING","GEOL_DESC"\n'
        '"UNIT",""\n"TYPE","X"\n"DATA","sand, with ""clay""\nand gravel"\n',
    )
    row, values = parse_ags(path)["GEOL"].rows[0]
    assert row == 6 and values["GEOL_DESC"] == 'sand, with "clay"\nand gravel'


def test_ags_depth_conversion(tmp_path, ags_text):
    # Change only GEOL depth metadata, leaving coordinates and hole depth in metres.
    text = ags_text.replace('"UNIT","","m","m",""', '"UNIT","","ft","ft",""')
    text = text.replace('"DATA","m","metres"', '"DATA","m","metres"\n"DATA","ft","feet"')
    ds = read_ags(changed(tmp_path, text), "EPSG:27700")
    assert ds.intervals[0].base == pytest.approx(0.2 * 0.3048)
    assert ds.holes[0].final_depth == 6


def test_csv_units_and_conflicting_location(tmp_path):
    path = tmp_path / "bc.csv"
    rows = list(csv.DictReader((SAMPLES / "bc_boreholes.csv").open()))
    rows[1]["LATITUDE"] = "50"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    ds = read_bc_csv(path, "ft")
    assert ds.holes[0].final_depth == pytest.approx(5.5 * 0.3048)
    assert "conflicting_location" in [i.code for i in ds.issues]


@pytest.mark.parametrize("raw", ["", "NaN", "inf", "not a number"])
def test_invalid_csv_numbers(tmp_path, raw):
    path = tmp_path / "bad.csv"
    path.write_text((SAMPLES / "bc_boreholes.csv").read_text().replace("49.271139", raw, 1))
    ds = read_bc_csv(path, "m")
    assert ds.errors and ds.issues[0].row == 2


def test_csv_missing_heading(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("id,top,base\nA,0,1\n")
    with pytest.raises(ValueError, match="BC CSV requires"):
        read_bc_csv(path, "m")
