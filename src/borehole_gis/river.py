"""Generated HEC-RAS steady profiles and independent energy-equation checks.

Model generation/extraction/hand checks work anywhere. Execution uses the real
HEC-RAS 6.6 controller on a disposable Windows GitHub Actions runner only.
"""

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from scipy.optimize import brentq, minimize_scalar

BASE = 'Results/Steady/Output/Output Blocks/Base Output/Steady Profiles'
FLOWS = {'2yr': 5.0, '10yr': 15.0, '100yr': 35.0}
STATIONS = [600, 500, 400, 300, 200, 100, 0]
SLOPE = .001
MANNING_N = .03


def section_properties(depth):
    """10 m bottom, 2 m vertical banks, floodplain side slopes 5H:3V.

    Sum subsection conveyance as HEC-RAS does at the two bank stations.
    Vertical bank faces contribute perimeter only up to the 2 m bank height.
    """
    if not np.isfinite(depth) or not 0 < depth <= 5:
        raise ValueError('Depth must be positive and within the 5 m section')
    channel_area = 10 * depth
    channel_k = channel_area * (channel_area / (10 + 2 * min(depth, 2))) ** (2 / 3) / MANNING_N
    extra = max(0, depth - 2)
    bank_area = .5 * (5 / 3) * extra ** 2
    bank_perimeter = extra * np.sqrt(1 + (5 / 3) ** 2)
    bank_k = bank_area * (bank_area / bank_perimeter) ** (2 / 3) / MANNING_N if extra else 0
    area = channel_area + 2 * bank_area
    conveyance = channel_k + 2 * bank_k
    # alpha corrects kinetic energy for unequal velocities in the subsections.
    weighted = channel_k ** 3 / channel_area ** 2
    if bank_area:
        weighted += 2 * bank_k ** 3 / bank_area ** 2
    alpha = weighted * area ** 2 / conveyance ** 3
    return area, conveyance, alpha


def normal_depth(flow, slope=SLOPE):
    if not np.isfinite(flow) or flow <= 0 or not np.isfinite(slope) or slope <= 0:
        raise ValueError('Flow and slope must be finite and positive')
    return brentq(lambda depth: section_properties(depth)[1] * np.sqrt(slope) - flow, .0001, 5)


def standard_step(flow, downstream_depth, downstream_bed, upstream_bed, length):
    """Solve upstream energy = downstream energy + friction (average conveyance).

    No structure loss is approximated here. Only adjacent ordinary sections are
    compared; the pair containing the culvert is explicitly excluded.
    """
    if not np.isfinite(length) or length <= 0 or not np.isfinite(flow) or flow <= 0:
        raise ValueError('Flow and reach length must be positive')
    area_dn, k_dn, alpha_dn = section_properties(downstream_depth)
    energy_dn = downstream_bed + downstream_depth + alpha_dn * (flow / area_dn) ** 2 / (2 * 9.80665)
    def energy(depth):
        area, k, alpha = section_properties(depth)
        return upstream_bed + depth + alpha * (flow / area) ** 2 / (2 * 9.80665)
    def residual(depth):
        _, k_up, _ = section_properties(depth)
        loss = (flow / ((k_up + k_dn) / 2)) ** 2 * length
        return energy(depth) - energy_dn - loss
    critical = minimize_scalar(energy, bounds=(.001, 4.999), method='bounded').x
    return brentq(residual, critical + .00001, 4.999)


def _write(path, lines):
    # HEC-RAS legacy text uses Windows newlines, independently of the host OS.
    path.write_bytes(('\r\n'.join(lines) + '\r\n').encode('ascii'))


def _fixed(values):
    return [''.join(f'{v:8.3f}' for v in values[i:i + 10]) for i in range(0, len(values), 10)]


def generate_project(directory, crossing=True):
    """Generate explicit geometry, flows, boundaries and plan, with no GUI input."""
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Model directory must be new or empty')
    directory.mkdir(parents=True, exist_ok=True)
    geometry = ['Geom Title=Synthetic channel and box culvert', 'Program Version=6.60',
                'Viewing Rectangle=0,650,50,-50', '', 'River Reach=Study           ,Main            ',
                'Reach XY= 2', '             600               0               0               0', '']
    for station in STATIONS:
        bed = 100 + SLOPE * station
        geometry += [f'Type RM Length L Ch R = 1 ,{station},100,100,100',
                     '#Sta/Elev= 6', *_fixed([0, bed + 5, 5, bed + 2, 5, bed, 15, bed, 15, bed + 2, 20, bed + 5]),
                     '#Mann= 3 , 0 , 0', *_fixed([0, .03, 0, 5, .03, 0, 15, .03, 0]),
                     'Bank Sta=5,15', 'XS Rating Curve= 0 ,0', 'Exp/Cntr=0,0',
                     'XS HTab Horizontal Distribution= 5 , 5 , 5', '']
        if station == 300 and crossing:
            geometry += ['Type RM Length L Ch R = 2 ,250,,,',
                         'BEGIN DESCRIPTION:', 'Synthetic 5 m by 2 m concrete box, 30 m barrel.', 'END DESCRIPTION:',
                         'Bridge Culvert-0,0,1,-1, 0',
                         'Deck Dist Width WeirC Skew NumUp NumDn MinLoCord MaxHiCord MaxSubmerge Is_Ogee',
                         '35,30,1.7,0, 2, 2, 103.5, , 0.95, 0, 0,0,,',
                         *_fixed([0, 20]), *_fixed([103.5, 103.5]), '                ',
                         *_fixed([0, 20]), *_fixed([103.5, 103.5]), '                ',
                         'Culvert=2,5,2,30,0.013,0.5,1,10,1,100.265,10,100.235,10,Box,0,35',
                         *_fixed([10, 10]), 'BC Culvert Barrel=1,Barrel 1,0', 'Culvert Bottom n=0.013',
                         'BC Design=,, 0 ,, 0 ,,,,,,', 'BC HTab HWMax=105', 'BC Use User HTab Curves=0', '']
    _write(directory / 'channel.g01', geometry)
    flow_lines = ['Flow Title=Illustrative return-period flows', 'Program Version=6.60', 'Number of Profiles= 3',
                  'Profile Names=' + ','.join(FLOWS), 'River Rch & RM=Study           ,Main            ,600',
                  *_fixed(list(FLOWS.values()))]
    for index in range(1, 4):
        flow_lines += [f'Boundary for River Rch & Prof#=Study           ,Main            , {index}',
                       'Up Type= 0', 'Dn Type= 3', f'Dn Slope={SLOPE}']
    _write(directory / 'channel.f01', flow_lines)
    _write(directory / 'channel.p01', [
        'Plan Title=Steady channel profiles', 'Program Version=6.60', 'Short Identifier=Profiles',
        'Simulation Date=,,,', 'Geom File=g01', 'Flow File=f01', 'Subcritical Flow',
        'Std Step Tol=0.001', 'Critical Tol=0.001', 'Num of Std Step Trials=40', 'Max Error Tol=0.03',
        'Friction Slope Method=1', 'Parabolic Critical Depth', 'CheckData=True',
        'Run HTab=1', 'Run UNet=0', 'Run Sediment=0', 'Run PostProcess=1', 'Run WQNet=0',
        'Run RASMapper=0', 'Write HDF5 File=1', 'Write Detailed=1', 'Echo Output=False'])
    _write(directory / 'channel.prj', ['Proj Title=Synthetic channel screening', 'Current Plan=p01',
                                       'Default Exp/Contr=0,0', 'SI Units', 'Geom File=g01',
                                       'Flow File=f01', 'Plan File=p01'])
    manifest = {'synthetic': True, 'units': 'SI', 'flows_m3_s': FLOWS,
                'stations_m': STATIONS, 'crossing': crossing, 'bank_height_m': 2,
                'bed_elevation': '100 + 0.001 * river_station_m', 'roughness': MANNING_N}
    (directory / 'inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return directory / 'channel.prj'


def run_hecras(project):
    """Run only on a Windows CI runner; release the owned controller in finally."""
    if sys.platform != 'win32':
        raise RuntimeError('HEC-RAS execution runs on Windows CI; no desktop app is launched on this host')
    import win32com.client
    controller = win32com.client.DispatchEx('RAS66.HECRASController')
    try:
        controller.Project_Open(str(Path(project).resolve()))
        # Blocking compute waits for the actual engine, not a timer or a cached file.
        result = controller.Compute_CurrentPlan(None, None, True)
        if not result[0]:
            raise RuntimeError('HEC-RAS reported an unsuccessful computation')
        print('HEC-RAS compute result:', str(result)[:2500])
        hdf = Path(project).with_suffix('.p01.hdf')
        if not hdf.is_file():
            raise RuntimeError('HEC-RAS produced no steady-result HDF file')
    finally:
        controller.QuitRas()
    return hdf


def extract_profiles(hdf):
    """Require explicit profile names and geometry identities, no positional guessing."""
    def decode(value):
        return value.decode().strip() if isinstance(value, bytes) else str(value).strip()
    with h5py.File(hdf, 'r') as handle:
        profiles = [decode(v) for v in handle[BASE + '/Profile Names'][...].ravel()]
        values = handle[BASE + '/Cross Sections/Water Surface'][...]
        attr_path = 'Results/Steady/Output/Geometry Info/Cross Section Attributes'
        if attr_path not in handle:
            attr_path = 'Geometry/Cross Sections/Attributes'
        attributes = handle[attr_path][...]
        fields = attributes.dtype.names or ()
        rs_field = next((f for f in fields if f in ('RS', 'River Station', 'Station')), None)
        if not {'River', 'Reach'} <= set(fields) or rs_field is None or values.shape != (len(profiles), len(attributes)):
            raise ValueError('Unexpected HEC-RAS profile dimensions or station field')
        rows = []
        for profile, elevations in zip(profiles, values):
            if profile not in FLOWS:
                raise ValueError(f'Unexpected profile: {profile}')
            for attributes_row, elevation in zip(attributes, elevations):
                if decode(attributes_row['River']) != 'Study' or decode(attributes_row['Reach']) != 'Main':
                    raise ValueError('Unexpected river/reach identity')
                station = float(decode(attributes_row[rs_field]).rstrip('*'))
                if not np.isfinite(elevation) or elevation < -1000:
                    raise ValueError('Invalid water-surface result')
                rows.append({'profile': profile, 'river_station_m': station, 'water_surface_m': float(elevation)})
    frame = pd.DataFrame(rows)
    if frame.duplicated(['profile', 'river_station_m']).any():
        raise ValueError('Duplicate profile/station result')
    if set(profiles) != set(FLOWS) or any(set(group.river_station_m) != set(STATIONS)
                                         for _, group in frame.groupby('profile')):
        raise ValueError('Missing expected profile or cross-section')
    return frame


def compare_profiles(frame, crossing=True, tolerance_m=.06):
    rows = []
    for profile, group in frame.groupby('profile'):
        indexed = group.set_index('river_station_m')
        flow = FLOWS[profile]
        for station in sorted(STATIONS):
            elevation = float(indexed.loc[station, 'water_surface_m'])
            bed = 100 + SLOPE * station
            expected = None
            method = 'culvert pair excluded from hand energy check'
            if station == 0:
                expected = bed + normal_depth(flow)
                method = 'Manning downstream boundary'
            elif station != 300 or not crossing:
                downstream = station - 100
                depth = float(indexed.loc[downstream, 'water_surface_m']) - (100 + SLOPE * downstream)
                expected = bed + standard_step(flow, depth, 100 + SLOPE * downstream, bed, 100)
                method = 'standard step, average conveyance'
            error = elevation - expected if expected is not None else None
            rows.append({'profile': profile, 'river_station_m': station, 'flow_m3_s': flow,
                         'water_surface_m': elevation, 'hand_water_surface_m': expected, 'comparison': method,
                         'difference_m': error, 'comparison_passes': abs(error) <= tolerance_m if error is not None else None,
                         'floodplain_overtopped': elevation > bed + 2})
    return pd.DataFrame(rows)


def run_workflow(output):
    """Two real runs distinguish culvert backwater from uniform-channel verification."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    reports, frames = {}, {}
    for name, crossing in [('control', False), ('culvert', True)]:
        project = generate_project(output / name, crossing)
        hdf = run_hecras(project)
        frame = extract_profiles(hdf)
        frame.to_csv(output / name / 'profiles.csv', index=False)
        frames[name] = frame
        comparison = compare_profiles(frame, crossing)
        comparison.to_csv(output / name / 'comparison.csv', index=False)
        checked = comparison.dropna(subset=['difference_m'])
        reports[name] = {'profiles': len(FLOWS), 'cross_sections': len(STATIONS),
                         'comparisons': len(checked), 'max_difference_m': float(checked.difference_m.abs().max()),
                         'all_comparisons_pass': bool(checked.comparison_passes.all()),
                         'overtopped_sections': int(comparison.floodplain_overtopped.sum())}
        if not reports[name]['all_comparisons_pass']:
            raise AssertionError(f'{name}: HEC-RAS differs from hand calculation: {reports[name]}')
    paired = frames['culvert'].merge(frames['control'], on=['profile', 'river_station_m'],
                                      suffixes=('_culvert', '_control'))
    upstream = paired.loc[paired.river_station_m == 300]
    backwater = dict(zip(upstream.profile, upstream.water_surface_m_culvert - upstream.water_surface_m_control))
    if not all(value > 0.01 for value in backwater.values()):
        raise AssertionError('The modeled culvert did not produce the expected upstream backwater')
    reports['culvert']['upstream_backwater_m'] = backwater
    (output / 'report.json').write_text(json.dumps(reports, indent=2) + '\n')
    return reports
