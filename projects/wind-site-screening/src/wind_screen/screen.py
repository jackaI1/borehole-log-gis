"""Metric setbacks, raster statistics and an auditable site-ranking model."""

import math

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import CRS
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds
from shapely import union_all
from shapely.geometry import GeometryCollection

from .config import Config

POLYGONS = {"Polygon", "MultiPolygon"}
LINES = {"LineString", "MultiLineString"}


def prepare(frame, crs, name, allowed, allow_empty=False):
    if frame.crs is None:
        raise ValueError(f"{name}: missing CRS; assign the source CRS before screening")
    if not allow_empty and frame.empty:
        raise ValueError(f"{name}: no features")
    if frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise ValueError(f"{name}: null or empty geometry")
    if not frame.geometry.is_valid.all():
        raise ValueError(f"{name}: invalid geometry; repair and inspect it before screening")
    if not frame.geom_type.isin(allowed).all():
        raise ValueError(f"{name}: expected {sorted(allowed)}")
    result = frame.to_crs(crs).copy().reset_index(drop=True)
    if not result.geometry.is_valid.all() or not np.isfinite(result.total_bounds).all():
        if not result.empty:
            raise ValueError(f"{name}: projection produced invalid coordinates")
    return result


def constraint_buffers(layers, config):
    """Union overlapping buffers once, avoiding duplicate constraint area."""
    buffered = {}
    for name, distance in config.setbacks_m.items():
        frame = prepare(
            layers[name],
            config.analysis_crs,
            name,
            LINES if name in {"roads", "transmission"} else POLYGONS,
            allow_empty=name != "transmission",
        )
        if distance == 0 and name in {"roads", "transmission"}:
            geom = GeometryCollection()
        else:
            geom = union_all(frame.geometry.buffer(distance).values)
        buffered[name] = geom
    return buffered, union_all(list(buffered.values()))


def wind_stats(src, geometry, geometry_crs):
    """Mean of native pixel centres in usable land, including outside-raster pixels as missing.

    A boundless window keeps the denominator honest for parcels crossing the raster edge.
    Native scale/offset metadata is applied. Invalid, nodata and negative speeds are missing.
    """
    if src.crs is None:
        raise ValueError("Wind raster is missing its CRS")
    if geometry.is_empty:
        return math.nan, 0.0, 0
    shape = gpd.GeoSeries([geometry], crs=geometry_crs).to_crs(src.crs).iloc[0]
    if src.transform.b != 0 or src.transform.d != 0:
        raise ValueError("Reproject rotated wind rasters to a north-up grid first")
    bounds_window = from_bounds(*shape.bounds, src.transform)
    col = math.floor(bounds_window.col_off)
    row = math.floor(bounds_window.row_off)
    width = math.ceil(bounds_window.col_off + bounds_window.width) - col
    height = math.ceil(bounds_window.row_off + bounds_window.height) - row
    if width * height > 4_000_000:
        raise ValueError("Parcel raster window exceeds 4 million pixels; subdivide the parcel")
    window = Window(col, row, width, height)
    inside = geometry_mask(
        [shape], out_shape=(height, width), transform=src.window_transform(window), invert=True
    )
    total = int(inside.sum())
    if total == 0:
        return math.nan, 0.0, 0
    values = src.read(1, window=window, boundless=True, masked=True)
    scaled = np.asarray(values.data, dtype=float) * src.scales[0] + src.offsets[0]
    valid = inside & ~np.ma.getmaskarray(values) & np.isfinite(scaled) & (scaled >= 0)
    # Explicit footprint check also covers datasets that have no nodata metadata.
    rows, cols = np.indices(inside.shape)
    valid &= (cols + col >= 0) & (cols + col < src.width)
    valid &= (rows + row >= 0) & (rows + row < src.height)
    count = int(valid.sum())
    mean = float(scaled[valid].mean()) if count else math.nan
    return mean, count / total, count


def score_components(wind, grid_distance, usable_fraction, config):
    wind_score = float(
        np.clip(
            (wind - config.wind_floor_ms) / (config.wind_ceiling_ms - config.wind_floor_ms), 0, 1
        )
    )
    grid_score = float(np.clip(1 - grid_distance / config.grid_limit_m, 0, 1))
    usable_score = float(np.clip(usable_fraction, 0, 1))
    score = 100 * (
        config.weights["wind"] * wind_score
        + config.weights["grid"] * grid_score
        + config.weights["usable"] * usable_score
    )
    return wind_score, grid_score, usable_score, score


def screen(candidates, layers, wind_path, config: Config):
    candidates = prepare(candidates, config.analysis_crs, "candidates", POLYGONS)
    if "site_id" not in candidates or candidates.site_id.isna().any():
        raise ValueError("Candidates need a non-null site_id")
    candidates["site_id"] = candidates.site_id.astype(str)
    if candidates.site_id.duplicated().any() or candidates.site_id.str.strip().eq("").any():
        raise ValueError("Candidate site_id values must be unique and non-empty")
    if not CRS(config.analysis_crs).area_of_use:
        raise ValueError("Use a CRS with a known geographic area of use")
    bounds = candidates.to_crs(4326).total_bounds
    area = CRS(config.analysis_crs).area_of_use
    if not (
        area.west <= bounds[0] <= bounds[2] <= area.east
        and area.south <= bounds[1] <= bounds[3] <= area.north
    ):
        raise ValueError("Candidates are outside the analysis CRS area of use")
    buffers, constraints = constraint_buffers(layers, config)
    transmission = prepare(
        layers["transmission"], config.analysis_crs, "transmission", LINES
    ).geometry.union_all()
    records, usable_geometries = [], []
    with rasterio.open(wind_path) as src:
        for site in candidates.itertuples():
            geom = site.geometry
            usable = geom.difference(constraints)
            usable_geometries.append(usable)
            fraction = float(np.clip(1 - usable.area / geom.area, 0, 1))
            wind, coverage, count = wind_stats(src, usable, config.analysis_crs)
            distance = float(usable.distance(transmission)) if not usable.is_empty else math.nan
            reasons = []
            if usable.area / 10000 < config.min_usable_ha:
                reasons.append("too_little_usable_land")
            if fraction > config.max_constraint_fraction:
                reasons.append("constraint_overlap")
            if coverage < config.min_wind_coverage or not math.isfinite(wind):
                reasons.append("insufficient_wind_data")
            elif wind < config.wind_floor_ms:
                reasons.append("low_wind")
            if not math.isfinite(distance) or distance > config.grid_limit_m:
                reasons.append("grid_too_far")
            wind_s, grid_s, usable_s, score = score_components(wind, distance, 1 - fraction, config)
            records.append(
                {
                    "site_id": site.site_id,
                    "area_ha": geom.area / 10000,
                    "usable_ha": usable.area / 10000,
                    "constraint_fraction": fraction,
                    "wind_ms": wind,
                    "wind_coverage": coverage,
                    "wind_pixels": count,
                    "grid_distance_m": distance,
                    "wind_component": wind_s,
                    "grid_component": grid_s,
                    "usable_component": usable_s,
                    "eligible": not reasons,
                    "reason": ";".join(reasons),
                    "score": score if not reasons else math.nan,
                }
            )
    result = gpd.GeoDataFrame(records, geometry=candidates.geometry, crs=config.analysis_crs)
    result = result.sort_values(
        ["eligible", "score", "site_id"], ascending=[False, False, True], na_position="last"
    )
    result["rank"] = [i + 1 if ok else None for i, ok in enumerate(result.eligible)]
    result["rank"] = result["rank"].astype("Int64")
    usable = gpd.GeoDataFrame(
        {"site_id": candidates.site_id}, geometry=usable_geometries, crs=config.analysis_crs
    )
    return result.reset_index(drop=True), usable, buffers
