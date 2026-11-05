import csv
import json
import subprocess
import sys
from pathlib import Path

import fiona
import pytest
from PIL import Image
from pyproj import Transformer

from borehole_gis.cli import main
from borehole_gis.export import export_tables, summaries
from borehole_gis.model import Dataset, Hole, Interval
from borehole_gis.readers import read_bc_csv
from borehole_gis.validate import validate

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def test_full_workflow(tmp_path):
    out = tmp_path / "results"
    assert (
        main(
            [str(SAMPLES / "bc_boreholes.csv"), "--format", "bc-csv", "--depth-unit", "m", "--out", str(out)]
        )
        == 0
    )
    report = json.loads((out / "validation.json").read_text())
    assert (report["holes"], report["intervals"], report["errors"], report["warnings"]) == (4, 17, 0, 1)
    with fiona.open(out / "boreholes.gpkg", layer="boreholes") as layer:
        assert len(layer) == 4 and layer.crs.to_epsg() == 3005
        features = list(layer)
        expected = Transformer.from_crs(4326, 3005, always_xy=True).transform(-123.106944, 49.271139)
        assert features[0]["geometry"]["coordinates"] == pytest.approx(expected)
        assert sorted(f["properties"]["gap_m"] for f in features) == pytest.approx([0, 0, 0, 1])
    assert len(list(csv.DictReader((out / "intervals.csv").open()))) == 17
    assert len(list(csv.DictReader((out / "stratigraphy.csv").open()))) == 17
    assert len(list(csv.DictReader((out / "logs.csv").open()))) == 4
    for image in (out / "logs").glob("*.png"):
        with Image.open(image) as img:
            assert img.width >= 1000
    manifest = json.loads((out / "manifest.json").read_text())
    assert "boreholes.gpkg" in manifest["files"]


def test_spt_workflow(tmp_path):
    assert (
        main(
            [
                str(SAMPLES / "bgs_bh01.ags"),
                "--format",
                "ags",
                "--crs",
                "EPSG:27700",
                "--output-crs",
                "EPSG:27700",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    rows = list(csv.DictReader((tmp_path / "spt.csv").open()))
    assert len(rows) == 5 and rows[0]["n"] == "17.0" and rows[-1]["n"] == ""
    assert rows[-1]["remark"]


def test_strict_blocks_warning(tmp_path):
    assert (
        main(
            [
                str(SAMPLES / "bc_boreholes.csv"),
                "--format",
                "bc-csv",
                "--depth-unit",
                "m",
                "--strict",
                "--out",
                str(tmp_path),
            ]
        )
        == 2
    )
    assert (tmp_path / "issues.csv").exists()
    assert not (tmp_path / "boreholes.gpkg").exists()


def test_invalid_input_report(tmp_path):
    source = tmp_path / "broken.ags"
    source.write_text('"GROUP","LOCA"\n"HEADING","A","B"\n"DATA","x"\n')
    out = tmp_path / "out"
    assert main([str(source), "--format", "ags", "--crs", "EPSG:27700", "--out", str(out)]) == 2
    report = json.loads((out / "validation.json").read_text())
    assert report["issues"][0]["code"] == "input_error"
    assert not (out / "boreholes.gpkg").exists()


def test_errors_block_export(tmp_path):
    ds = validate(read_bc_csv(SAMPLES / "bc_boreholes.csv", "m"))
    ds.issue("example_error", "CSV", 1, "", "bad input")
    with pytest.raises(ValueError, match="Resolve validation errors"):
        export_tables(ds, tmp_path, "EPSG:3005")


@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:2263"])
def test_reject_non_metre_output(tmp_path, crs):
    ds = validate(read_bc_csv(SAMPLES / "bc_boreholes.csv", "m"))
    with pytest.raises(ValueError, match="metre units"):
        export_tables(ds, tmp_path, crs)


def test_summary_preserves_descriptions():
    ds = Dataset(
        "EPSG:4326",
        [Hole("A", -123, 49, 10, 2)],
        [
            Interval("A", 0, 2, "Sand, silty", 3),
            Interval("A", 2, 5, "clay", 4),
            Interval("A", 5, 10, "Sand, silty", 5),
        ],
    )
    row = summaries(ds)[0]
    assert row["thickness_m"] == 7 and row["interval_count"] == 2
    assert row["description"] == "Sand, silty"


def test_preserves_previous_results(tmp_path):
    existing = tmp_path / "notes.txt"
    existing.write_text("keep me")
    with pytest.raises(SystemExit):
        main(
            [
                str(SAMPLES / "bc_boreholes.csv"),
                "--format",
                "bc-csv",
                "--depth-unit",
                "m",
                "--out",
                str(tmp_path),
            ]
        )
    assert existing.read_text() == "keep me"


def test_cli_requires_explicit_units(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "borehole_gis.cli",
            str(SAMPLES / "bc_boreholes.csv"),
            "--format",
            "bc-csv",
            "--out",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "--depth-unit is required" in result.stderr
