import json
import shutil
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from wind_screen.cli import run
from wind_screen.config import Config
from wind_screen.data import download_features, make_candidates, sha256


def test_fixture_end_to_end(tmp_path, config, candidates, layers, wind):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    candidates.to_file(inputs / "candidates.geojson", driver="GeoJSON")
    for name, layer in layers.items():
        layer.to_file(inputs / f"{name}.geojson", driver="GeoJSON")
    shutil.copy(wind, inputs / "wind_100m.tif")
    output = tmp_path / "result"
    ranked = run(config, inputs, output)
    assert len(pd.read_csv(output / "ranked.csv")) == 2
    assert len(list((output / "memos").glob("*.md"))) == 2
    assert len(gpd.read_file(output / "screening.gpkg", layer="candidates")) == 2
    assert json.loads((output / "run.json").read_text())["eligible_count"] == 2
    assert ranked.iloc[0].score > ranked.iloc[1].score
    with pytest.raises(ValueError, match="already exists"):
        run(config, inputs, output)


def test_public_snapshot_is_complete_and_ranks(tmp_path):
    manifest = json.loads(Path("data/ontario/sources.json").read_text())
    for name, digest in manifest["files"].items():
        assert sha256(Path("data/ontario") / name) == digest
    ranked = run(Config.load("config/bruce.json"), "data/ontario", tmp_path / "public")
    assert len(ranked) > 100
    assert ranked.eligible.sum() > 10
    assert ranked.iloc[0].wind_ms > 5
    assert ranked.iloc[0].grid_distance_m > 0
    assert ranked[~ranked.eligible].score.isna().all()


def test_candidates_cover_only_study_box():
    cfg = Config.load("config/bruce.json")
    cells = make_candidates(cfg)
    assert cells.site_id.is_unique
    assert cells.geometry.is_valid.all()
    assert cells.area.max() <= cfg.cell_size_m**2 + 1


def test_source_download_batches_ids_and_rejects_truncation(monkeypatch):
    calls = []

    def fake_json(url, params):
        calls.append(params)
        if params.get("returnIdsOnly"):
            return {"objectIds": list(range(201)), "objectIdFieldName": "OBJECTID"}
        ids = [int(i) for i in params["objectIds"].split(",")]
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"OBJECTID": i},
                    "geometry": {"type": "Point", "coordinates": [-81, 44]},
                }
                for i in ids
            ],
        }

    monkeypatch.setattr("wind_screen.data.get_json", fake_json)
    assert len(download_features("https://example.test", "1=1", (-82, 43, -80, 45))) == 201
    assert [len(c["objectIds"].split(",")) for c in calls[1:]] == [200, 1]

    def truncated(url, params):
        if params.get("returnIdsOnly"):
            return {"objectIds": [1, 2], "objectIdFieldName": "OBJECTID"}
        return {"features": [], "exceededTransferLimit": True}

    monkeypatch.setattr("wind_screen.data.get_json", truncated)
    with pytest.raises(ValueError, match="truncated"):
        download_features("https://example.test", "1=1", (-82, 43, -80, 45))


def test_increased_setbacks_require_a_new_download():
    from dataclasses import replace

    from wind_screen.data import validate_snapshot

    cfg = Config.load("config/bruce.json")
    candidates = gpd.read_file("data/ontario/candidates.geojson")
    validate_snapshot("data/ontario", candidates, cfg)
    with pytest.raises(ValueError, match="coverage is too small"):
        validate_snapshot(
            "data/ontario", candidates, replace(cfg, setbacks_m={**cfg.setbacks_m, "water": 10000})
        )


def test_changed_snapshot_cannot_keep_its_old_provenance(tmp_path):
    from wind_screen.data import validate_snapshot

    cfg = Config.load("config/bruce.json")
    candidates = gpd.read_file("data/ontario/candidates.geojson")
    shutil.copytree("data/ontario", tmp_path / "snapshot")
    with (tmp_path / "snapshot/roads.geojson").open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_snapshot(tmp_path / "snapshot", candidates, cfg)


def test_zero_eligible_sites_still_export(tmp_path, config, candidates, layers, wind):
    from dataclasses import replace

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    candidates.to_file(inputs / "candidates.geojson", driver="GeoJSON")
    layers["water"] = candidates[["geometry"]].copy()
    for name, layer in layers.items():
        layer.to_file(inputs / f"{name}.geojson", driver="GeoJSON")
    shutil.copy(wind, inputs / "wind_100m.tif")
    ranked = run(replace(config, min_usable_ha=1), inputs, tmp_path / "excluded")
    assert not ranked.eligible.any()
    assert list((tmp_path / "excluded/memos").glob("*")) == []
    assert len(gpd.read_file(tmp_path / "excluded/screening.gpkg", layer="usable_land")) == 0
