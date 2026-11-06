"""Review nearby flood results alongside borehole locations, without predicting groundwater."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd


def nearby_flooding(boreholes_gpkg: Path, results_gpkg: Path, output_csv: Path,
                    return_period: int = 100, distance_m: float = 100):
    if not np.isfinite(distance_m) or distance_m <= 0:
        raise ValueError('Search distance must be finite and positive')
    if output_csv.exists():
        raise FileExistsError('Existing borehole screening output is preserved')
    holes = gpd.read_file(boreholes_gpkg, layer='boreholes')
    nodes = gpd.read_file(results_gpkg, layer=f'nodes_{return_period}yr')
    if (nodes.crs is None or not nodes.crs.is_projected or
            any(axis.unit_name != 'metre' for axis in nodes.crs.axis_info) or holes.crs is None):
        raise ValueError('Results need a projected metre CRS and boreholes need a declared CRS')
    required = {'node_id', 'kind', 'layer', 'peak_depth_m', 'flood_volume_m3'}
    if 'hole_id' not in holes or not required <= set(nodes):
        raise ValueError('Use the borehole-gis and swmm-batch exported layers')
    if holes.hole_id.duplicated().any() or nodes.node_id.duplicated().any():
        raise ValueError('Feature IDs must be unique')
    if any(g is None or g.is_empty or g.geom_type != 'Point' or not g.is_valid for g in [*holes.geometry, *nodes.geometry]):
        raise ValueError('Screening requires valid nonempty point geometry')
    for column in ['peak_depth_m', 'flood_volume_m3']:
        if not np.isfinite(nodes[column]).all() or (nodes[column] < 0).any():
            raise ValueError('Flood result depths and volumes must be finite and nonnegative')
    holes = holes.to_crs(nodes.crs)
    nodes = nodes.loc[(nodes.layer == 'surface') & (nodes.kind == 'junction')]
    rows = []
    for hole in holes.itertuples():
        near = nodes.copy()
        near['distance_m'] = near.geometry.distance(hole.geometry)
        near = near.loc[near.distance_m <= distance_m].sort_values(['distance_m', 'node_id'])
        # Retain all nearby nodes: the closest one need not have the greatest flooding.
        if near.empty:
            rows.append({'hole_id': hole.hole_id, 'return_period_yr': return_period,
                         'review': 'no surface node within search radius'})
        for node in near.itertuples():
            rows.append({'hole_id': hole.hole_id, 'return_period_yr': return_period,
                         'surface_node_id': node.node_id, 'distance_m': float(node.distance_m),
                         'peak_surface_depth_m': float(node.peak_depth_m),
                         'lost_flood_volume_m3': float(node.flood_volume_m3),
                         'review': 'near modeled overflow' if node.flood_volume_m3 > 0 else 'near modeled surface route'})
    frame = pd.DataFrame(rows, columns=['hole_id', 'return_period_yr', 'surface_node_id', 'distance_m',
                                      'peak_surface_depth_m', 'lost_flood_volume_m3', 'review'])
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_csv, index=False)
    return frame
