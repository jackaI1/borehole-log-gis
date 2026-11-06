import csv
import json
import sqlite3
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pyogrio
import pytest

from site_data_qaqc.cli import main, run
from site_data_qaqc.export import site_slug
from site_data_qaqc.ingest import InputError

DATA = sorted(Path("data/synthetic").glob("*.csv"))


def write_row(path, raw):
    v = raw["values"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, list(v))
        w.writeheader()
        w.writerow(v)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo") / "results"
    summary = run(DATA, out)
    return out, summary


def test_seeded_end_to_end_counts_and_traceability(demo):
    out, summary = demo
    assert summary["counts"]["results"] == 17
    assert summary["counts"]["rejected"] == 6
    assert summary["screening"]["exceeds"] == 7
    assert summary["duplicate_status"] == {"pass": 2, "fail": 1, "censored": 1, "missing_parent": 1}
    with sqlite3.connect(out / "site_data.sqlite") as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        rpd, status = db.execute(
            "SELECT d.rpd, d.status FROM duplicates d JOIN results r ON d.duplicate_id=r.record_id "
            "WHERE r.sample_id='GW-01-D'"
        ).fetchone()
        assert rpd == pytest.approx(50)
        assert status == "fail"
        assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 23
        assert db.execute("SELECT count(*) FROM exceedances").fetchone()[0] == 7
        assert (
            db.execute(
                "SELECT count(*) FROM results WHERE censored=1 AND value IS NOT NULL"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute("SELECT count(*) FROM review_queue").fetchone()[0]
            == summary["counts"]["issues"]
        )
        row = db.execute(
            "SELECT raw_json FROM records JOIN results USING(record_id) WHERE sample_id='GW-01' AND analyte='arsenic'"
        ).fetchone()
        assert json.loads(row[0])["value"] == "18"
        db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE results SET depth_bottom_m=-1")


def test_gis_layers_roundtrip_and_crs(demo):
    out, summary = demo
    layers = {name for name, _ in pyogrio.list_layers(out / "samples.gpkg")}
    assert layers == {"sample_results", "sample_points", "exceedances"}
    results = gpd.read_file(out / "samples.gpkg", layer="sample_results")
    exceeds = gpd.read_file(out / "samples.gpkg", layer="exceedances")
    assert results.crs.to_epsg() == 4326
    assert len(results) == summary["counts"]["results"]
    assert len(exceeds) == 7
    assert set(exceeds.screening) == {"exceeds"}
    assert results.geometry.is_valid.all()
    assert results.geometry.x.between(-81, -80).all()
    points = gpd.read_file(out / "sample_points.geojson")
    assert points.exceedance_count.sum() == 7
    assert points.indeterminate_count.sum() == 1
    assert len(points) < len(results)


def test_borehole_reports_and_figures_close(demo):
    out, summary = demo
    assert len(summary["sites"]) == 2
    for site in summary["sites"].values():
        image = out / site["figure"]
        assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert image.stat().st_size > 10000
        with (out / site["table"]).open() as f:
            rows = list(csv.DictReader(f))
        assert rows
        assert all(float(r["depth_bottom_m"]) > float(r["depth_top_m"]) for r in rows)
    assert plt.get_fignums() == []
    with (out / "borehole_log.csv").open() as f:
        assert len(list(csv.DictReader(f))) == 17


def test_all_rejected_still_exports_audit(raw, tmp_path):
    path = tmp_path / "bad.csv"
    write_row(path, raw(unit="ppm"))
    out = tmp_path / "report"
    summary = run([path], out)
    assert summary["counts"]["results"] == 0
    assert summary["counts"]["rejected"] == 1
    assert summary["sites"] == {}
    assert len(gpd.read_file(out / "samples.gpkg", layer="sample_results")) == 0
    assert (out / "rejected.csv").stat().st_size > 100


def test_cli_strict_exports_before_exit_2(raw, tmp_path, capsys):
    path = tmp_path / "bad.csv"
    write_row(path, raw(unit="ppm"))
    out = tmp_path / "strict"
    assert main([str(path), "--out", str(out), "--strict"]) == 2
    assert json.loads(capsys.readouterr().out)["rejected"] == 1
    assert (out / "site_data.sqlite").exists()


def test_output_reuse_preserves_original(demo):
    out, _ = demo
    before = (out / "summary.json").read_bytes()
    with pytest.raises(InputError, match="already exists"):
        run(DATA, out)
    assert (out / "summary.json").read_bytes() == before


def test_export_failure_cleans_stage(raw, tmp_path, monkeypatch):
    path = tmp_path / "valid.csv"
    write_row(path, raw())

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("site_data_qaqc.cli.export", fail)
    assert main([str(path), "--out", str(tmp_path / "out")]) == 1
    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".site-qaqc-*"))


def test_no_exceedances_still_has_empty_layer(raw, tmp_path):
    path = tmp_path / "clean.csv"
    write_row(path, raw(result="2"))
    out = tmp_path / "out"
    assert main([str(path), "--out", str(out)]) == 0
    assert len(gpd.read_file(out / "samples.gpkg", layer="exceedances")) == 0


def test_malformed_input_has_no_partial_output(raw, tmp_path):
    path = tmp_path / "bad.csv"
    write_row(path, raw())
    with path.open("a") as f:
        f.write("only,two\n")
    with pytest.raises(InputError, match="cells"):
        run([path], tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_unreadable_file_is_actionable(tmp_path, capsys):
    assert main([str(tmp_path / "missing.csv"), "--out", str(tmp_path / "out")]) == 1
    assert "No such file" in capsys.readouterr().err


def test_site_filenames_are_confined_and_collision_resistant():
    assert "/" not in site_slug("../../private")
    assert site_slug("A B") != site_slug("A-B")
