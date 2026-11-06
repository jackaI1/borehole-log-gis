import csv
import json

import pytest

from borehole_gis.core_runs import CoreRun, assess_runs, export_core_runs, read_core_runs
from borehole_gis.model import Dataset, Hole, Interval


def dataset():
    return Dataset('EPSG:32617', [Hole('A', 0, 0, 10, 1)], [Interval('A', 0, 10, 'rock', 1)])


def test_calculation_and_join():
    row = assess_runs([CoreRun('A', 0, 1, (0.1, 0.3, 0.05), 4)], dataset())[0]
    assert row['rqd_percent'] == 40
    assert row['rqd_quality'] == 'poor'
    assert row['fractures_per_m'] == 4
    assert row['layers'][0]['description'] == 'rock'
    assert not row['review_flags']


def test_empty_and_overlaps():
    runs = [CoreRun('A', 0, 1, (), 0), CoreRun('A', 0.5, 1.5, (1.1,), 1)]
    first, second = assess_runs(runs, dataset())
    assert first['rqd_percent'] == 0
    assert first['rqd_quality'] == 'very poor'
    assert 'overlapping runs' in first['review_flags']
    assert 'recovery exceeds run length' in second['review_flags']
    assert second['rqd_quality'] is None



@pytest.mark.parametrize('piece,band', [(0.249, 'very poor'), (.25, 'poor'), (.5, 'fair'),
                                        (.75, 'good'), (.9, 'excellent'), (1, 'excellent')])
def test_standard_band_boundaries(piece, band):
    assert assess_runs([CoreRun('A', 0, 1, (piece,), 2)], dataset())[0]['rqd_quality'] == band


@pytest.mark.parametrize('run,flag', [
    (CoreRun('A', 1, 1, (), 0), 'invalid interval'),
    (CoreRun('A', 0, 1, (-.1,), 0), 'invalid piece length'),
    (CoreRun('A', 0, 1, (float('nan'),), 0), 'invalid piece length'),
    (CoreRun('A', 0, 1, (), -1), 'invalid fracture count'),
    (CoreRun('A', 0, 1, (), True), 'invalid fracture count'),
    (CoreRun('B', 0, 1, (), 0), 'unknown or ambiguous borehole'),
    (CoreRun('A', 9, 11, (), 0), 'beyond borehole depth'),
])
def test_implausible_runs_are_flagged(run, flag):
    assert flag in assess_runs([run], dataset())[0]['review_flags']


def test_recovery_over_100_is_flagged_even_if_rqd_under_100():
    row = assess_runs([CoreRun('A', 0, 1, (.5,) + (.09,) * 6, 3)], dataset())[0]
    assert row['rqd_percent'] == 50
    assert row['rqd_quality'] is None
    assert 'recovery exceeds run length' in row['review_flags']


def test_duplicate_instance_and_generator_overlap():
    run = CoreRun('A', 0, 1, (.1,), 0)
    assert all('overlapping runs' in r['review_flags'] for r in assess_runs(iter([run, run]), dataset()))
    assert not any(r['review_flags'] for r in assess_runs([run, CoreRun('A', 1, 2, (), 0)], dataset()))


def test_file_input_and_one_to_many_layer_export(tmp_path):
    path = tmp_path / 'core.json'
    path.write_text(json.dumps({'depth_unit': 'm', 'runs': [dict(hole_id='A', top_m=0, base_m=2,
                                                              pieces_m=[.1, .3, .05], fractures=4)]}))
    ds = dataset()
    ds.intervals = [Interval('A', 0, 1, 'sandstone', 1), Interval('A', 1, 10, 'shale', 2)]
    result = export_core_runs(read_core_runs(path), ds, tmp_path)
    assert result[0]['rqd_percent'] == 20
    rows = list(csv.DictReader((tmp_path / 'core_runs.csv').open()))
    assert len(rows) == 2
    assert {r['layer_description'] for r in rows} == {'sandstone', 'shale'}
    assert all(float(r['overlap_m']) == 1 for r in rows)
    assert rows[0]['hole_crs'] == 'EPSG:32617'
    path.write_text('{"depth_unit": "ft", "runs": []}')
    with pytest.raises(ValueError, match='depth_unit'):
        read_core_runs(path)
