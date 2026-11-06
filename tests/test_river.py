import json

import h5py
import numpy as np
import pytest

from borehole_gis.river import (
    BASE,
    FLOWS,
    STATIONS,
    compare_profiles,
    extract_profiles,
    generate_project,
    normal_depth,
    run_hecras,
    section_properties,
    standard_step,
)


def write_hdf(path, missing=False):
    attrs = np.array([(b'Study', b'Main', str(s).encode()) for s in STATIONS],
                     dtype=[('River', 'S16'), ('Reach', 'S16'), ('RS', 'S16')])
    with h5py.File(path, 'w') as f:
        f.create_dataset('Geometry/Cross Sections/Attributes', data=attrs)
        f.create_dataset(BASE + '/Profile Names', data=np.array(list(FLOWS), dtype='S16'))
        values = [[100 + s * .001 + normal_depth(q) for s in STATIONS] for q in FLOWS.values()]
        f.create_dataset(BASE + '/Cross Sections/Water Surface', data=np.array(values)[:, :6] if missing else values)


def test_manning_hand_value_and_standard_step():
    area, k, alpha = section_properties(1)
    assert area == 10
    assert k == pytest.approx(10 * (10 / 12) ** (2 / 3) / .03)
    assert alpha == pytest.approx(1)
    flow = k * np.sqrt(.001)
    assert normal_depth(flow) == pytest.approx(1)
    assert standard_step(flow, 1, 100, 100.1, 100) == pytest.approx(1, abs=1e-7)


def test_generated_model_contains_real_culvert_and_three_profiles(tmp_path):
    path = generate_project(tmp_path / 'model')
    assert path.is_file()
    assert b'\r\n' in path.read_bytes()
    assert 'SI Units' in path.read_text()
    geom = path.with_suffix('.g01').read_text()
    assert geom.count('#Sta/Elev=') == 7
    assert 'Culvert=2,5,2,30' in geom
    assert 'Number of Profiles= 3' in path.with_suffix('.f01').read_text()
    assert json.loads((path.parent / 'inputs.json').read_text())['synthetic']
    with pytest.raises(ValueError, match='new or empty'):
        generate_project(path.parent)


def test_hdf_extraction_comparison_and_overtopping(tmp_path):
    path = tmp_path / 'test.hdf'
    write_hdf(path)
    frame = extract_profiles(path)
    assert len(frame) == 21
    comparison = compare_profiles(frame, crossing=False)
    assert comparison.comparison_passes.all()
    assert comparison.difference_m.abs().max() < .0001
    assert comparison.floodplain_overtopped.any()
    crossing = compare_profiles(frame, crossing=True)
    assert len(crossing.dropna(subset=['difference_m'])) == 18
    with h5py.File(path, 'r+') as f:
        f[BASE + '/Cross Sections/Water Surface'][0, 0] += .3
    comparison = compare_profiles(extract_profiles(path), crossing=False)
    assert not comparison.comparison_passes.all()


def test_extraction_rejects_wrong_dimensions_and_missing_station(tmp_path):
    path = tmp_path / 'bad.hdf'
    write_hdf(path, missing=True)
    with pytest.raises(ValueError, match='dimensions'):
        extract_profiles(path)
    write_hdf(path)
    with h5py.File(path, 'r+') as f:
        ds = f['Geometry/Cross Sections/Attributes']
        row = ds[0]
        row['RS'] = b'999'
        ds[0] = row
    with pytest.raises(ValueError, match='Missing expected'):
        extract_profiles(path)


def test_macos_never_launches_hecras(tmp_path):
    import sys
    if sys.platform != 'win32':
        with pytest.raises(RuntimeError, match='Windows CI'):
            run_hecras(tmp_path / 'channel.prj')
