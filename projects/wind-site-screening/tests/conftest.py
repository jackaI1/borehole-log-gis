from dataclasses import replace

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, box

from wind_screen.config import Config

CRS = "EPSG:26917"
X, Y = 500000, 4900000


def frame(geometries, **columns):
    return gpd.GeoDataFrame(columns, geometry=geometries, crs=CRS)


@pytest.fixture
def config():
    return replace(
        Config(),
        min_usable_ha=0.01,
        setbacks_m={"roads": 0, "transmission": 0, "water": 0, "protected": 0},
    )


@pytest.fixture
def candidates():
    return frame(
        [box(X, Y, X + 100, Y + 100), box(X + 200, Y, X + 300, Y + 100)], site_id=["A", "B"]
    )


@pytest.fixture
def layers():
    return {
        "transmission": frame([LineString([(X - 100, Y - 100), (X - 100, Y + 300)])]),
        "roads": frame([LineString([(X - 500, Y), (X - 500, Y + 100)])]),
        "water": frame([]),
        "protected": frame([]),
    }


@pytest.fixture
def wind(tmp_path):
    path = tmp_path / "wind.tif"
    data = np.full((30, 50), 7, dtype="float32")
    data[:, 30:] = 8
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=50,
        height=30,
        count=1,
        dtype="float32",
        crs=CRS,
        transform=from_origin(X - 100, Y + 200, 10, 10),
        nodata=-9999,
    ) as dst:
        dst.write(data, 1)
    return path
