import json

import numpy as np
import pandas as pd
import pytest

from borehole_gis.pumping import (
    analyze,
    fit_cooper_jacob,
    fit_theis,
    load_observations,
    residual_theis,
    theis,
)


def write_observations(tmp_path, times, values, **extra):
    frame = pd.DataFrame({'timestamp': [str(pd.Timestamp('2026-01-01T00:00:00Z') + pd.Timedelta(seconds=float(t)))
                                       for t in times], 'drawdown': values, **extra})
    path = tmp_path / 'drawdown.csv'
    frame.to_csv(path, index=False)
    metadata = {'start': '2026-01-01T00:00:00Z', 'rate': 10, 'rate_unit': 'L/s',
                'radius': 20, 'radius_unit': 'm', 'drawdown_unit': 'm'}
    return path, metadata


def test_theis_independent_well_function_value():
    # Abramowitz & Stegun E1(1) = 0.219383934395520; choose u=1.
    assert theis(100, .01, 20, .001, .001) == pytest.approx(.01 / (4 * np.pi * .001) * .219383934395520)


def test_known_parameters_noise_and_confidence_intervals():
    times = np.geomspace(1, 100000, 90)
    true = theis(times, .01, 20, .001, .0002)
    noise = np.random.default_rng(2026).normal(0, .005, len(times))
    result = fit_theis(times, true + noise, .01, 20)
    assert result['transmissivity_m2_s'] == pytest.approx(.001, rel=.01)
    assert result['storativity'] == pytest.approx(.0002, rel=.03)
    assert result['ci95_T_m2_s'][0] < .001 < result['ci95_T_m2_s'][1]
    assert result['ci95_S'][0] < result['storativity'] < result['ci95_S'][1]
    assert result['ci95_S'][1] - result['ci95_S'][0] < .00001
    assert result['rmse_m'] < .006
    assert not result['flags']


def test_published_groundwater_project_straight_line_example():
    # Woessner, Stringer & Poeter, section 8.3, Figure 33 worked example.
    # These are two points on the published straight line, not invented field data.
    # Q=2610 L/min, r=600 m; s(10 min)=1.32 m, s(100 min)=4.85 m.
    result = fit_cooper_jacob([600, 6000], [1.32, 4.85], 2.610 / 60, 600)
    assert result['transmissivity_m2_day'] == pytest.approx(194.9, rel=.003)
    # The printed t0=2.8 min and S=2e-6 do not agree with these endpoints.
    # Their intercept gives t0=4.227 min and S=3.573e-6; retain that discrepancy.
    assert result['storativity'] == pytest.approx(3.57281e-6, rel=1e-5)
    assert result['ci95_S'] is None
    assert 'too few late-time points: need at least 5' in result['flags']


def test_recovery_superposition_and_fit():
    duration = 600
    after = np.geomspace(.1, 20000, 80)
    values = residual_theis(after, duration, .01, 20, .001, .0002)
    assert values[0] > values[-1] > 0
    assert values[0] == pytest.approx(theis(after[0] + duration, .01, 20, .001, .0002), rel=1e-6)
    result = fit_theis(after + duration, values, .01, 20, duration)
    assert result['transmissivity_m2_s'] == pytest.approx(.001, rel=1e-5)
    assert result['storativity'] == pytest.approx(.0002, rel=1e-5)


def test_barometric_correction_and_report(tmp_path):
    times = np.geomspace(1, 100000, 70)
    pressure = 101.3 + .5 * np.sin(np.arange(len(times)))
    expected = theis(times, .01, 20, .001, .0002)
    observed = expected + .65 * (pressure - 101.3) * 1000 / (1000 * 9.80665)
    path, meta = write_observations(tmp_path, times, observed, barometric_pressure=pressure)
    meta.update(pressure_unit='kPa', reference_pressure=101.3, barometric_efficiency=.65)
    obs = load_observations(path, meta)
    assert obs.corrected_m == pytest.approx(expected, abs=1e-7)
    result = analyze(path, meta, tmp_path / 'results')
    assert result['theis']['transmissivity_m2_s'] == pytest.approx(.001, rel=1e-5)
    assert result['cooper_jacob']['points'] > 10
    assert not result['cooper_jacob']['flags']
    assert (tmp_path / 'results/diagnostic.png').stat().st_size > 5000
    assert json.loads((tmp_path / 'results/report.json').read_text())['barometric_correction']['applied']
    with pytest.raises(ValueError, match='new or empty'):
        analyze(path, meta, tmp_path / 'results')


@pytest.mark.parametrize('change', ['naive', 'duplicate', 'reverse', 'before', 'nan', 'unit', 'rate', 'pressure'])
def test_invalid_observations(tmp_path, change):
    path, meta = write_observations(tmp_path, [1, 2, 3], [0, .1, .2])
    frame = pd.read_csv(path)
    if change == 'naive':
        meta['start'] = '2026-01-01'
    elif change == 'duplicate':
        frame.loc[1, 'timestamp'] = frame.loc[0, 'timestamp']
    elif change == 'reverse':
        frame = frame.iloc[::-1]
    elif change == 'before':
        meta['start'] = '2026-01-02T00:00:00Z'
    elif change == 'nan':
        frame.loc[0, 'drawdown'] = np.nan
    elif change == 'unit':
        meta['rate_unit'] = 'gallons?'
    elif change == 'rate':
        meta['rate'] = -1
    elif change == 'pressure':
        meta['barometric_efficiency'] = .5
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        load_observations(path, meta)


def test_feet_day_units_and_recovery_csv(tmp_path):
    path, meta = write_observations(tmp_path, [61, 62, 63], [1, 2, 3])
    meta.update(rate=864, rate_unit='m3/day', radius=20 / .3048, radius_unit='ft', drawdown_unit='ft',
                stop='2026-01-01T00:01:00Z')
    obs = load_observations(path, meta)
    assert obs.rate_m3_s == pytest.approx(.01)
    assert obs.radius_m == pytest.approx(20)
    assert obs.corrected_m == pytest.approx(np.array([1, 2, 3]) * .3048)
    meta['stop'] = '2026-01-01T00:01:02Z'
    with pytest.raises(ValueError, match='shutoff'):
        load_observations(path, meta)


def test_poor_fit_and_early_time_warnings(tmp_path):
    times = np.geomspace(.01, 1, 10)
    path, meta = write_observations(tmp_path, times, theis(times, .01, 20, .001, .0002))
    result = analyze(path, meta, tmp_path / 'early')
    assert 'too few late-time points' in result['cooper_jacob']['flags']
    bad = fit_theis(np.geomspace(1, 10000, 20), np.tile([1, 3], 10), .01, 20)
    assert 'poor fit: R-squared below 0.98' in bad['flags']
    assert fit_cooper_jacob([1, 10, 100], [3, 2, 1], .01, 20)['flags'] == ['nonpositive late-time slope']


def test_nonphysical_straight_line_is_flagged_without_infinite_parameters():
    result = fit_cooper_jacob([1, 10, 100], [1000, 1001, 1002], .01, 20)
    assert result['flags'] == ['straight-line parameters outside supported T/S bounds']
    json.dumps(result, allow_nan=False)
