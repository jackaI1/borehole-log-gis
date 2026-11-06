from dataclasses import replace

import numpy as np
import pytest
import rasterio
from conftest import CRS, X, Y, frame
from shapely.geometry import LineString, box

from wind_screen.screen import constraint_buffers, score_components, screen, wind_stats


def test_buffer_is_metres_and_union_prevents_double_count(config, layers):
    layers["water"] = frame([box(X, Y, X + 100, Y + 100)])
    layers["protected"] = layers["water"].copy()
    cfg = replace(config, setbacks_m={**config.setbacks_m, "water": 20, "protected": 20})
    buffers, union = constraint_buffers(layers, cfg)
    assert buffers["water"].bounds == (X - 20, Y - 20, X + 120, Y + 120)
    assert union.area == pytest.approx(buffers["water"].area)
    assert union.area == pytest.approx(10000 + 400 * 20 + np.pi * 20**2, rel=0.001)


def test_line_buffer_width_and_zero_distance(config, layers):
    layers["roads"] = frame([LineString([(X, Y), (X + 100, Y)])])
    cfg = replace(config, setbacks_m={**config.setbacks_m, "roads": 10})
    buffers, _ = constraint_buffers(layers, cfg)
    assert buffers["roads"].bounds == (X - 10, Y - 10, X + 110, Y + 10)
    assert constraint_buffers(layers, config)[0]["roads"].is_empty


def test_mixed_crs_has_same_results(config, candidates, layers, wind):
    expected = screen(candidates, layers, wind, config)[0]
    geographic = {name: layer.to_crs(4326) for name, layer in layers.items()}
    actual = screen(candidates.to_crs(4326), geographic, wind, config)[0]
    for column in ["grid_distance_m", "wind_ms", "score", "usable_ha"]:
        np.testing.assert_allclose(expected[column], actual[column], atol=1e-5)
    assert actual.crs.to_epsg() == 26917


@pytest.mark.parametrize("kind", ["missing_crs", "duplicate_id", "empty", "invalid", "null"])
def test_bad_candidates_fail_clearly(kind, config, candidates, layers, wind):
    if kind == "missing_crs":
        candidates = candidates.set_crs(None, allow_override=True)
    elif kind == "duplicate_id":
        candidates["site_id"] = ["A", "A"]
    elif kind == "empty":
        candidates = candidates.iloc[:0]
    elif kind == "null":
        candidates.loc[0, "geometry"] = None
    else:
        from shapely.geometry import Polygon

        candidates.loc[0, "geometry"] = Polygon(
            [(X, Y), (X + 100, Y + 100), (X, Y + 100), (X + 100, Y), (X, Y)]
        )
    with pytest.raises(ValueError):
        screen(candidates, layers, wind, config)


def test_fully_constrained_site_cannot_rank(config, candidates, layers, wind):
    layers["water"] = frame([candidates.geometry.iloc[0]])
    result, usable, _ = screen(candidates, layers, wind, config)
    rejected = result.set_index("site_id").loc["A"]
    assert not rejected.eligible
    assert np.isnan(rejected.score)
    assert "too_little_usable_land" in rejected.reason
    assert rejected.constraint_fraction == 1
    assert usable.iloc[0].geometry.is_empty
    assert result.iloc[0].site_id == "B"


def test_partial_constraint_has_known_overlap_and_distance(config, candidates, layers, wind):
    layers["water"] = frame([box(X, Y, X + 25, Y + 100)])
    result = screen(candidates, layers, wind, config)[0].set_index("site_id")
    assert result.loc["A", "constraint_fraction"] == pytest.approx(0.25)
    assert result.loc["A", "usable_ha"] == pytest.approx(0.75)
    assert result.loc["A", "grid_distance_m"] == pytest.approx(125)
    assert result.loc["A", "score"] == pytest.approx(25 + 30 * (1 - 125 / 20000) + 15)


def test_known_score_and_clamping(config):
    assert score_components(7, 10000, 0.75, config) == pytest.approx((0.5, 0.5, 0.75, 55))
    assert score_components(10, 0, 1, config)[3] == 100
    assert score_components(0, 100000, 0, config)[3] == 0


def test_grid_limit_and_low_wind_rejections(config, candidates, layers, wind):
    far = screen(candidates, layers, wind, replace(config, grid_limit_m=50))[0]
    assert not far.eligible.any()
    assert far.reason.str.contains("grid_too_far").all()
    low = screen(candidates, layers, wind, replace(config, wind_floor_ms=8.5))[0]
    assert low.reason.str.contains("low_wind").all()


def test_deterministic_tie_break(config, candidates, layers, wind):
    candidates.loc[1, "geometry"] = candidates.loc[0, "geometry"]
    candidates["site_id"] = ["Z", "A"]
    result = screen(candidates, layers, wind, config)[0]
    assert result.site_id.tolist() == ["A", "Z"]
    assert result["rank"].tolist() == [1, 2]


def test_raster_mean_nodata_coverage_and_edge(wind):
    with rasterio.open(wind, "r+") as src:
        data = src.read(1)
        data[10:20, 10:15] = -9999
        src.write(data, 1)
    with rasterio.open(wind) as src:
        mean, coverage, count = wind_stats(src, box(X, Y, X + 100, Y + 100), CRS)
        assert (mean, coverage, count) == (7, 0.5, 50)
        # Half of these pixel centres lie outside the raster, so coverage must be 50%.
        assert wind_stats(src, box(X - 150, Y, X - 50, Y + 100), CRS)[1] == 0.5
        assert wind_stats(src, box(X - 500, Y, X - 400, Y + 100), CRS)[1] == 0
        assert np.isnan(wind_stats(src, box(X, Y, X + 1, Y + 1), CRS)[0])


def test_wind_coverage_rejects_missing_values(config, candidates, layers, wind):
    with rasterio.open(wind, "r+") as src:
        data = src.read(1)
        data[10:20, 10:15] = np.nan
        src.write(data, 1)
    result = screen(candidates, layers, wind, config)[0].set_index("site_id")
    assert "insufficient_wind_data" in result.loc["A", "reason"]
    assert np.isnan(result.loc["A", "score"])


def test_raster_scale_offset_and_different_crs(config, candidates, layers, wind, tmp_path):
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    path = tmp_path / "geographic.tif"
    with rasterio.open(wind) as src:
        transform, width, height = calculate_default_transform(
            src.crs, 4326, src.width, src.height, *src.bounds
        )
        profile = src.profile.copy()
        profile.update(crs="EPSG:4326", transform=transform, width=width, height=height)
        with rasterio.open(path, "w", **profile) as dst:
            reproject(rasterio.band(src, 1), rasterio.band(dst, 1), resampling=Resampling.nearest)
            dst.scales = (2,)
            dst.offsets = (1,)
    with rasterio.open(path) as src:
        mean, coverage, _ = wind_stats(src, candidates.iloc[0].geometry, CRS)
        assert mean == pytest.approx(15)
        assert coverage == 1


def test_empty_transmission_rejected(config, candidates, layers, wind):
    layers["transmission"] = frame([])
    with pytest.raises(ValueError, match="transmission: no features"):
        screen(candidates, layers, wind, config)
