from dataclasses import replace

import pytest

from wind_screen.config import Config


@pytest.mark.parametrize(
    "change",
    [
        {"analysis_crs": "EPSG:4326"},
        {"analysis_crs": "EPSG:2263"},
        {"analysis_crs": "EPSG:26918"},
        {"cell_size_m": 0},
        {"grid_limit_m": -1},
        {"weights": {"wind": 0.5, "grid": 0.5, "usable": 0.5}},
        {"wind_ceiling_ms": 4},
        {"min_wind_coverage": 0},
        {"max_constraint_fraction": 1.1},
        {"top_sites": 0},
        {"wind_floor_ms": float("nan")},
        {"setbacks_m": {"water": -1}},
        {"bbox_wgs84": (-81, 44, -82, 45)},
    ],
)
def test_invalid_assumptions(change):
    with pytest.raises(ValueError):
        replace(Config(), **change)


def test_checked_in_config():
    cfg = Config.load("config/bruce.json")
    assert cfg.analysis_crs == "EPSG:26917"
    assert sum(cfg.weights.values()) == 1


def test_display_mercator_is_not_a_distance_crs():
    with pytest.raises(ValueError, match="Mercator"):
        Config(analysis_crs="EPSG:3857")
