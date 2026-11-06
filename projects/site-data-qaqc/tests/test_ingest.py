import csv

import pytest

from site_data_qaqc.ingest import InputError, normalize, number, read_table


def test_units_dates_and_coordinates(raw):
    r = normalize(raw(sample_date="14-Sep-2026"), "EPSG:26917")
    assert r["value"] == pytest.approx(0.020)
    assert r["detection_limit"] == pytest.approx(0.001)
    assert r["unit"] == "mg/L"
    assert r["sample_date"] == "2026-09-14"
    assert r["longitude"] == pytest.approx(-80.379, abs=0.001)
    assert r["latitude"] == pytest.approx(43.712, abs=0.002)
    assert r["source_row"] == 2


@pytest.mark.parametrize(
    "unit,value,expected",
    [
        ("µg/L", "20", 0.02),
        ("μg/L", "20", 0.02),
        ("mg/L", "0,020", 0.02),
        ("ng/L", "20000", 0.02),
        ("g/L", "0.00002", 0.02),
    ],
)
def test_water_conversions(raw, unit, value, expected):
    r = normalize(raw(unit=unit, result=value, detection_limit=""), "EPSG:26917")
    assert r["value"] == pytest.approx(expected)


@pytest.mark.parametrize(
    "unit,value,expected",
    [("mg/kg", "12", 12), ("ug/g", "12", 12), ("ug/kg", "12000", 12), ("g/kg", "0.012", 12)],
)
def test_dry_soil_conversion(raw, unit, value, expected):
    r = normalize(
        raw(matrix="soil", basis="dry", unit=unit, result=value, detection_limit=""), "EPSG:26917"
    )
    assert r["value"] == expected
    assert r["basis"] == "dry"


@pytest.mark.parametrize(
    "result,dl,qualifier",
    [("<2", "", ""), ("ND", "2", ""), ("2", "2", "U"), ("<=2", "2", ""), ("N/D", "2", "")],
)
def test_nondetect_is_null_not_zero(raw, result, dl, qualifier):
    r = normalize(raw(result=result, detection_limit=dl, qualifier=qualifier), "EPSG:26917")
    assert r["value"] is None
    assert r["censored"] == 1
    assert r["detection_limit"] == 0.002


@pytest.mark.parametrize(
    "changes,match",
    [
        ({"sample_id": ""}, "missing field"),
        ({"unit": "ppm"}, "unsupported"),
        ({"unit": "mg/kg"}, "unsupported"),
        ({"matrix": "sediment"}, "matrix"),
        ({"result": "-1"}, "negative"),
        ({"result": "NaN"}, "finite"),
        ({"result": "1e999"}, "finite"),
        ({"result": "1e308", "unit": "g/L"}, "overflow"),
        ({"detection_limit": "-2"}, "positive"),
        ({"result": "ND", "detection_limit": ""}, "needs"),
        ({"result": "<2", "detection_limit": "1"}, "disagrees"),
        ({"qualifier": "R"}, "unsupported qualifier"),
        ({"sample_date": "09/10/26"}, "date"),
        ({"sample_date": "2026-02-30"}, "date"),
        ({"depth_top_m": "-1"}, "depth"),
        ({"depth_bottom_m": "0.5"}, "depth"),
        ({"matrix": "soil", "unit": "mg/kg", "basis": "wet"}, "dry weight"),
        ({"x": "181", "y": "43", "crs": "EPSG:4326"}, "bounds"),
        ({"x": "-90000000"}, "area of use"),
    ],
)
def test_invalid_rows_are_not_guessed(raw, changes, match):
    with pytest.raises(ValueError, match=match):
        normalize(raw(**changes), "EPSG:26917")


def test_explicit_geographic_crs(raw):
    r = normalize(raw(x="-80.38", y="43.71", crs="EPSG:4326"), "EPSG:26917")
    assert (r["longitude"], r["latitude"]) == (-80.38, 43.71)


@pytest.mark.parametrize("value", ["inf", "1,000.2", "1 000", "", "--2"])
def test_invalid_numbers(value):
    with pytest.raises(ValueError):
        number(value)


def test_legacy_aliases_multiline_bom(raw, tmp_path):
    v = raw()["values"]
    v["lithology"] = "sand\nwith silt"
    v["site"] = v.pop("site_id")
    path = tmp_path / "legacy.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, list(v), delimiter=";")
        writer.writeheader()
        writer.writerow(v)
    records = read_table(path)
    assert len(records) == 1
    assert records[0]["values"]["site_id"] == "Test Site"
    assert records[0]["values"]["lithology"] == "sand\nwith silt"
    assert records[0]["source_row"] == 3


def test_colliding_headers(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("site,site_id\na,b\n")
    with pytest.raises(InputError, match="colliding"):
        read_table(path)


def test_missing_schema(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("site,sample\na,b\n")
    with pytest.raises(InputError, match="missing columns"):
        read_table(path)


@pytest.mark.parametrize("result", ["<<2", "<==2"])
def test_malformed_nondetect_operators_are_rejected(raw, result):
    with pytest.raises(ValueError):
        normalize(raw(result=result, detection_limit=""), "EPSG:26917")
