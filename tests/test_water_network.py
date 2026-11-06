import json

import numpy as np
import pandas as pd
import pytest
import wntr
from scipy.optimize import brentq

from borehole_gis.water_network import Criteria, check_network, create_demo, hazen_williams, run_solver


def simple_network(tmp_path, parallel=False):
    wn = wntr.network.WaterNetworkModel()
    wn.options.time.duration = 0
    wn.options.hydraulic.headloss = 'H-W'
    wn.add_reservoir('R', base_head=100)
    wn.add_junction('J', base_demand=.01, elevation=50)
    wn.add_pipe('P1', 'R', 'J', length=1000, diameter=.2, roughness=120)
    if parallel:
        wn.add_pipe('P2', 'R', 'J', length=700, diameter=.15, roughness=110)
    return wn, run_solver(wn, tmp_path / 'solver')


def test_single_pipe_solver_against_hand_hazen_williams(tmp_path):
    _, result = simple_network(tmp_path)
    loss = hazen_williams(.01, 1000, .2, 120)
    assert result.node['head'].loc[0, 'J'] == pytest.approx(100 - loss, abs=.02)
    assert result.link['flowrate'].loc[0, 'P1'] == pytest.approx(.01, rel=1e-5)


def test_looped_parallel_pair_flow_split_and_equal_head_loss(tmp_path):
    _, result = simple_network(tmp_path, parallel=True)
    q1 = brentq(lambda q: hazen_williams(q, 1000, .2, 120)
                - hazen_williams(.01 - q, 700, .15, 110), 0, .01)
    assert result.link['flowrate'].loc[0, 'P1'] == pytest.approx(q1, rel=.003)
    assert result.link['flowrate'].loc[0, 'P2'] == pytest.approx(.01 - q1, rel=.003)
    assert result.node['head'].loc[0, 'J'] == pytest.approx(100 - hazen_williams(q1, 1000, .2, 120), abs=.02)


def test_real_eps_fire_and_pump_curve(tmp_path):
    inp = create_demo(tmp_path / 'zone.inp')
    result = check_network(inp, tmp_path / 'report', Criteria(max_headloss_m_km=1))
    assert result['engine'] == 'EPANET 2.2 via WNTR'
    assert len(result['fire_scenarios']) == 3
    assert any(not row['passes'] for row in result['fire_scenarios'])
    assert min(row['min_residual_pressure_m'] for row in result['fire_scenarios']) < result['baseline_pressure_min_m']
    assert result['flagged_pipes'] > 0
    points = pd.read_csv(tmp_path / 'report/pumps.csv')
    assert len(points) == 97
    assert np.max(abs(points.gain_m - points.curve_gain_m)) < .01
    pressure = pd.read_csv(tmp_path / 'report/pressure_timeseries_m.csv')
    assert pressure.time_s.iloc[-1] == 86400
    assert (tmp_path / 'report/baseline/engine.rpt').is_file()
    assert json.loads((tmp_path / 'report/report.json').read_text())['duration_s'] == 86400
    with pytest.raises(ValueError, match='new or empty'):
        check_network(inp, tmp_path / 'report')


def test_thresholds_and_invalid_hydrants(tmp_path):
    with pytest.raises(ValueError):
        Criteria(min_pressure_m=90)
    with pytest.raises(ValueError):
        Criteria(max_velocity_m_s=float('nan'))
    inp = create_demo(tmp_path / 'zone.inp')
    with pytest.raises(ValueError, match='Hydrants'):
        check_network(inp, tmp_path / 'bad', hydrants=['unknown'])
    with pytest.raises(ValueError, match='positive'):
        check_network(inp, tmp_path / 'bad2', fire_flow_m3_s=-1)
