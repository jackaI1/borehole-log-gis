"""Download small, attributed public-data subsets. Never invent missing source data."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import requests
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import box

from .config import Config

LIO = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/"
WIND = "https://gwa.cdn.nazkamapps.com/country_tifs_v4/CAN_wind-speed_100m.tif"
SOURCES = {
    "transmission": (LIO + "LIO_Open05/MapServer/11", "CLASS_SUBTYPE = 'Hydro Line'"),
    "roads": (
        "https://services1.arcgis.com/TJH5KDher0W13Kgo/arcgis/rest/services/"
        "Ontario_Road_Network_Composite_Service_GeoHub_View_EN/FeatureServer/5",
        "1=1",
    ),
    "water": (LIO + "LIO_Open01/MapServer/25", "1=1"),
    "protected": (LIO + "LIO_Open03/MapServer/4", "1=1"),
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_json(url, params):
    response = requests.get(url, params=params, timeout=90)
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise ValueError(f"Public data service error: {result['error']}")
    return result


def download_features(url, where, bounds):
    """Query IDs first and fetch bounded batches so record limits cannot truncate data."""
    query = {
        "f": "json",
        "where": where,
        "geometryType": "esriGeometryEnvelope",
        "geometry": ",".join(map(str, bounds)),
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "returnIdsOnly": "true",
    }
    ids = get_json(url + "/query", query)
    if "objectIds" not in ids:
        raise ValueError("Source did not return object IDs")
    object_ids = sorted(ids["objectIds"] or [])
    features = []
    for start in range(0, len(object_ids), 200):
        batch = object_ids[start : start + 200]
        result = get_json(
            url + "/query",
            {
                "f": "geojson",
                "objectIds": ",".join(map(str, batch)),
                "outFields": ids["objectIdFieldName"],
                "outSR": 4326,
                "returnGeometry": "true",
            },
        )
        if result.get("exceededTransferLimit") or len(result.get("features", [])) != len(batch):
            raise ValueError("Source truncated or changed during download; retry the refresh")
        features.extend(result["features"])
    if not features:
        return gpd.GeoDataFrame({"source_id": []}, geometry=[], crs=4326)
    frame = gpd.GeoDataFrame.from_features(features, crs=4326)
    frame = frame.rename(columns={ids["objectIdFieldName"]: "source_id"})
    return frame[["source_id", "geometry"]]


def make_candidates(config):
    """Generate study cells, explicitly not cadastral property or ownership records."""
    aoi = gpd.GeoSeries([box(*config.bbox_wgs84)], crs=4326).to_crs(config.analysis_crs).iloc[0]
    xmin, ymin, xmax, ymax = aoi.bounds
    cells = []
    for x in np.arange(xmin, xmax, config.cell_size_m):
        for y in np.arange(ymin, ymax, config.cell_size_m):
            geom = box(x, y, x + config.cell_size_m, y + config.cell_size_m).intersection(aoi)
            if geom.area > 1:
                cells.append(geom)
    return gpd.GeoDataFrame(
        {"site_id": [f"BC-{i:03d}" for i in range(1, len(cells) + 1)]},
        geometry=cells,
        crs=config.analysis_crs,
    )


def fetch_data(config: Config, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError("Refresh into an empty directory to preserve the existing snapshot")
    candidates = make_candidates(config)
    candidates.to_file(directory / "candidates.geojson", driver="GeoJSON")
    aoi = gpd.GeoSeries([box(*config.bbox_wgs84)], crs=4326).to_crs(config.analysis_crs)
    records = []
    for name, (url, where) in SOURCES.items():
        # Grid queries need the full scoring radius. Other layers need their setbacks.
        halo = (
            max(config.grid_limit_m, config.setbacks_m[name]) + 1000
            if name == "transmission"
            else config.setbacks_m[name] + 1000
        )
        bounds = aoi.buffer(halo).to_crs(4326).total_bounds.tolist()
        print(f"Fetching {name}", flush=True)
        frame = download_features(url, where, bounds)
        path = directory / f"{name}.geojson"
        frame.to_file(path, driver="GeoJSON")
        records.append(
            {
                "layer": name,
                "url": url,
                "where": where,
                "bbox_wgs84": bounds,
                "features": len(frame),
                "license": "Open Government Licence - Ontario",
            }
        )
    print("Reading the Ontario window from the public wind GeoTIFF", flush=True)
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        GDAL_HTTP_TIMEOUT="90",
    ):
        with rasterio.open(WIND) as src:
            bounds = transform_bounds(4326, src.crs, *config.bbox_wgs84, densify_pts=21)
            # Expand outward, preserving the native pixel grid and values.
            window = from_bounds(*bounds, src.transform)
            col, row = np.floor([window.col_off, window.row_off]).astype(int)
            right = int(np.ceil(window.col_off + window.width))
            bottom = int(np.ceil(window.row_off + window.height))
            window = rasterio.windows.Window(col, row, right - col, bottom - row)
            values = src.read(1, window=window)
            profile = src.profile.copy()
            profile.update(
                width=values.shape[1],
                height=values.shape[0],
                transform=src.window_transform(window),
                compress="deflate",
            )
            with rasterio.open(directory / "wind_100m.tif", "w", **profile) as dst:
                dst.write(values, 1)
                dst.scales, dst.offsets = src.scales, src.offsets
                dst.update_tags(
                    source=WIND,
                    units="m/s",
                    hub_height_m="100",
                    attribution="Global Wind Atlas 4.0, DTU / World Bank / Vortex / ESMAP",
                )
    records.append(
        {
            "layer": "wind",
            "url": WIND,
            "license": "CC BY 4.0",
            "hub_height_m": 100,
            "units": "m/s",
            "operation": "native-grid window only",
        }
    )
    manifest = {
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "config": config.dump(),
        "sources": records,
        "candidate_note": "Generated 2 km study cells, not legal land parcels",
        "files": {p.name: sha256(p) for p in sorted(directory.iterdir()) if p.is_file()},
    }
    (directory / "sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def validate_snapshot(directory, candidates, config):
    """Verify provenance and query halos before a changed scenario uses the snapshot."""
    manifest_path = Path(directory) / "sources.json"
    if not manifest_path.exists():
        # Custom local data can be used without the public-source manifest.
        return None
    manifest = json.loads(manifest_path.read_text())
    for name, digest in manifest["files"].items():
        if Path(name).name != name or sha256(Path(directory) / name) != digest:
            raise ValueError(f"Snapshot checksum mismatch: {name}")
    if candidates.crs is None:
        raise ValueError("Candidates have no CRS")
    if candidates.empty:
        raise ValueError("Candidates have no features")
    # A rectangle around the parcels is conservative for irregular custom parcels.
    envelope = gpd.GeoSeries(
        [box(*candidates.to_crs(config.analysis_crs).total_bounds)], crs=config.analysis_crs
    )
    source_by_name = {entry["layer"]: entry for entry in manifest["sources"]}
    for name, setback in config.setbacks_m.items():
        needed = max(setback, config.grid_limit_m) if name == "transmission" else setback
        bounds = envelope.buffer(needed).to_crs(4326).total_bounds
        available = source_by_name[name]["bbox_wgs84"]
        if not (
            available[0] <= bounds[0]
            and available[1] <= bounds[1]
            and bounds[2] <= available[2]
            and bounds[3] <= available[3]
        ):
            raise ValueError(f"Snapshot {name} coverage is too small; fetch data for this scenario")
    return manifest
