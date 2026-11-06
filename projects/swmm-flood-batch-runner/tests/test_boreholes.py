import geopandas as gpd
import pytest
from shapely.geometry import Point

from swmm_batch.boreholes import nearby_flooding
from swmm_batch.cli import main


def inputs(tmp_path):
    holes, results = tmp_path / 'holes.gpkg', tmp_path / 'results.gpkg'
    gpd.GeoDataFrame({'hole_id': ['A', 'B']}, geometry=[Point(0, 0), Point(1000, 0)], crs=32617).to_file(
        holes, layer='boreholes', driver='GPKG')
    gpd.GeoDataFrame({'node_id': ['S_A', 'S_B', 'N_A', 'S_OUT'], 'layer': ['surface', 'surface', 'sewer', 'surface'],
                      'peak_depth_m': [.1, .25, 2, 0], 'flood_volume_m3': [0, 10, 20, 0]},
                     geometry=[Point(5, 0), Point(10, 0), Point(0, 0), Point(1, 0)], crs=32617).to_file(
                         results, layer='nodes_100yr', driver='GPKG')
    return holes, results


def test_all_nearby_nodes_and_unmatched_holes_are_preserved(tmp_path):
    holes, results = inputs(tmp_path)
    frame = nearby_flooding(holes, results, tmp_path / 'screening.csv', distance_m=50)
    assert len(frame) == 3
    assert list(frame.loc[frame.hole_id == 'A', 'surface_node_id']) == ['S_A', 'S_B']
    assert 'no surface node within search radius' in set(frame.review)
    assert 'near modeled overflow' in set(frame.review)
    assert frame.distance_m.iloc[0] == pytest.approx(5)
    with pytest.raises(FileExistsError):
        nearby_flooding(holes, results, tmp_path / 'screening.csv')


def test_cli_and_crs_conversion(tmp_path):
    holes, results = inputs(tmp_path)
    frame = gpd.read_file(holes, layer='boreholes').to_crs(4326)
    frame.to_file(holes, layer='boreholes', driver='GPKG')
    assert main(['boreholes', '--boreholes', str(holes), '--results', str(results),
                 '--output', str(tmp_path / 'join.csv')]) == 0


def test_invalid_distance_and_missing_crs(tmp_path):
    holes, results = inputs(tmp_path)
    with pytest.raises(ValueError, match='positive'):
        nearby_flooding(holes, results, tmp_path / 'bad.csv', distance_m=float('nan'))
    frame = gpd.read_file(results, layer='nodes_100yr').to_crs(4326)
    frame.to_file(results, layer='nodes_100yr', driver='GPKG')
    with pytest.raises(ValueError, match='metre'):
        nearby_flooding(holes, results, tmp_path / 'bad.csv')
