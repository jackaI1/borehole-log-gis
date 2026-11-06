"""EPANET 2.2 pressure-zone checks using WNTR. WNTR quantities are SI."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import wntr


@dataclass(frozen=True)
class Criteria:
    min_pressure_m: float = 20.0
    max_pressure_m: float = 80.0
    max_velocity_m_s: float = 2.0
    max_headloss_m_km: float = 10.0
    fire_residual_m: float = 14.0
    pump_min_flow_m3_s: float = 0.005
    pump_max_flow_m3_s: float = 0.035
    pump_curve_tolerance_m: float = 0.1

    def __post_init__(self):
        if (not all(np.isfinite(v) and v > 0 for v in asdict(self).values())
                or self.min_pressure_m >= self.max_pressure_m
                or self.pump_min_flow_m3_s >= self.pump_max_flow_m3_s):
            raise ValueError("Criteria must be positive, finite and ordered")


def hazen_williams(flow_m3_s, length_m, diameter_m, coefficient):
    """SI Hazen-Williams friction loss (m); independent of the EPANET solver."""
    if (not all(np.isfinite(v) and v > 0 for v in [length_m, diameter_m, coefficient])
            or not np.isfinite(flow_m3_s)):
        raise ValueError("Hazen-Williams requires finite flow and positive length, diameter and C")
    return 10.67 * length_m * abs(flow_m3_s) ** 1.852 / (coefficient ** 1.852 * diameter_m ** 4.871)


def create_demo(path):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    wn = wntr.network.WaterNetworkModel()
    wn.options.time.duration = 86400
    wn.options.time.hydraulic_timestep = 900
    wn.options.time.report_timestep = 900
    wn.options.time.pattern_timestep = 3600
    wn.options.hydraulic.headloss = 'H-W'
    # Demand-driven fire tests expose pressure shortfalls for the requested flow.
    wn.options.hydraulic.demand_model = 'DDA'
    wn.add_pattern('daily', [0.6, 0.5, 0.5, 0.6, 0.8, 1.2, 1.5, 1.4, 1.1, 1, 0.9, 1,
                             1.1, 1, 0.9, 1, 1.2, 1.5, 1.4, 1.2, 1, 0.9, 0.8, 0.7])
    wn.add_reservoir('R', base_head=100, coordinates=(0, 0))
    for name, demand, elevation, xy in [('S', 0, 110, (50, 0)), ('A', .005, 120, (650, 0)),
                                         ('B', .008, 124, (1000, 350)), ('C', .004, 118, (600, 600))]:
        wn.add_junction(name, base_demand=demand, demand_pattern='daily', elevation=elevation, coordinates=xy)
    wn.add_curve('pump_curve', 'HEAD', [(0, 55), (.02, 45), (.04, 15)])
    wn.add_pump('PUMP', 'R', 'S', pump_type='HEAD', pump_parameter='pump_curve')
    for name, start, end, length, diameter in [('MAIN', 'S', 'A', 600, .2),
                                              ('AB', 'A', 'B', 500, .125),
                                              ('BC', 'B', 'C', 400, .125),
                                              ('CA', 'C', 'A', 600, .15)]:
        wn.add_pipe(name, start, end, length=length, diameter=diameter, roughness=120)
    path.parent.mkdir(parents=True, exist_ok=True)
    wntr.network.write_inpfile(wn, str(path), units='LPS', version=2.2)
    return path


def run_solver(network, directory):
    directory.mkdir(parents=True, exist_ok=True)
    result = wntr.sim.EpanetSimulator(network).run_sim(file_prefix=str(directory / 'engine'), version=2.2,
                                                     convergence_error=True)
    if result.error_code not in (None, 0):
        raise RuntimeError(f"EPANET simulation error: {result.error_code}")
    for frame in [result.node['pressure'], result.node['head'], result.link['flowrate']]:
        if frame.empty or not np.isfinite(frame.to_numpy()).all():
            raise RuntimeError("EPANET returned missing/nonfinite hydraulic results")
    return result


def check_network(inp, output, criteria=Criteria(), fire_flow_m3_s=0.015, hydrants=None):
    """Run 24 h baseline and one 2 h fire demand at a time; all nodes remain checked."""
    if not np.isfinite(fire_flow_m3_s) or fire_flow_m3_s <= 0:
        raise ValueError("Fire flow must be finite and positive")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be new or empty")
    wn = wntr.network.WaterNetworkModel(str(inp))
    if wn.options.hydraulic.headloss != 'H-W':
        raise ValueError("This workflow requires Hazen-Williams input")
    if wn.options.time.duration != 86400 or wn.options.time.pattern_timestep != 3600:
        raise ValueError("Use a 24-hour network with 1-hour pattern steps")
    if wn.options.time.pattern_start != 0 or wn.options.time.report_start != 0:
        raise ValueError("Pattern and report start must be zero")
    wn.options.hydraulic.demand_model = 'DDA'
    wn.options.time.hydraulic_timestep = 900
    wn.options.time.report_timestep = 900
    hydrants = list(hydrants) if hydrants is not None else [n for n in wn.junction_name_list
                                                         if wn.get_node(n).base_demand > 0]
    if not hydrants or len(set(hydrants)) != len(hydrants) or any(n not in wn.junction_name_list for n in hydrants):
        raise ValueError("Hydrants must be distinct known junctions")
    output.mkdir(parents=True, exist_ok=True)
    baseline = run_solver(wn, output / 'baseline')
    pressures = baseline.node['pressure'][wn.junction_name_list]
    node_rows = []
    for name in wn.junction_name_list:
        low, high = float(pressures[name].min()), float(pressures[name].max())
        flags = []
        if low < criteria.min_pressure_m:
            flags.append('low pressure')
        if high > criteria.max_pressure_m:
            flags.append('high pressure')
        node_rows.append(dict(node=name, min_pressure_m=low, max_pressure_m=high, flags='; '.join(flags)))
    pipe_rows, pump_rows = [], []
    for name, pipe in wn.pipes():
        flow = baseline.link['flowrate'][name].abs()
        velocity = float((flow / (np.pi * pipe.diameter ** 2 / 4)).max())
        loss = (baseline.node['head'][pipe.start_node_name] - baseline.node['head'][pipe.end_node_name]).abs()
        gradient = float((loss / pipe.length * 1000).max())
        flags = []
        if velocity > criteria.max_velocity_m_s:
            flags.append('high velocity')
        if gradient > criteria.max_headloss_m_km:
            flags.append('high head loss')
        pipe_rows.append(dict(pipe=name, peak_velocity_m_s=velocity, peak_headloss_m_km=gradient,
                              flags='; '.join(flags)))
    for name, pump in wn.pumps():
        if pump.pump_type != 'HEAD' or pump.base_speed != 1 or pump.speed_pattern_name is not None:
            raise ValueError('Operating-point checks require fixed unit-speed head-curve pumps')
        a, b, c = pump.get_head_curve_coefficients()
        curve = wn.get_curve(pump.pump_curve_name).points
        for instant, flow in baseline.link['flowrate'][name].items():
            head = float(baseline.node['head'].loc[instant, pump.end_node_name]
                         - baseline.node['head'].loc[instant, pump.start_node_name])
            expected = float(a - b * max(0, flow) ** c)
            flags = []
            if not criteria.pump_min_flow_m3_s <= flow <= criteria.pump_max_flow_m3_s:
                flags.append('outside operating flow range')
            if not min(v[0] for v in curve) <= flow <= max(v[0] for v in curve):
                flags.append('outside supplied pump curve')
            if abs(head - expected) > criteria.pump_curve_tolerance_m:
                flags.append('pump curve mismatch')
            pump_rows.append(dict(pump=name, time_s=int(instant), flow_m3_s=float(flow), gain_m=head,
                                  curve_gain_m=expected, flags='; '.join(flags)))
    fire_rows = []
    for hydrant in hydrants:
        scenario = wntr.network.WaterNetworkModel(str(inp))
        scenario.options.hydraulic.demand_model = 'DDA'
        scenario.options.time.hydraulic_timestep = 900
        scenario.options.time.report_timestep = 900
        pattern = [0] * 24
        pattern[6:8] = [1, 1]
        scenario.add_pattern('fire_check', pattern)
        scenario.get_node(hydrant).add_demand(fire_flow_m3_s, 'fire_check', 'Fire')
        result = run_solver(scenario, output / ('fire_' + hydrant))
        event = result.node['pressure'].loc[21600:27900, scenario.junction_name_list]
        minimum = float(event.min().min())
        critical = str(event.min().idxmin())
        fire_rows.append(dict(hydrant=hydrant, added_flow_m3_s=fire_flow_m3_s,
                              min_residual_pressure_m=minimum, critical_node=critical,
                              passes=minimum >= criteria.fire_residual_m))
    for name, rows in [('nodes', node_rows), ('pipes', pipe_rows), ('pumps', pump_rows), ('fire_flow', fire_rows)]:
        pd.DataFrame(rows).to_csv(output / f'{name}.csv', index=False)
    pressures.to_csv(output / 'pressure_timeseries_m.csv', index_label='time_s')
    report = {'engine': 'EPANET 2.2 via WNTR', 'criteria': asdict(criteria),
              'criteria_source': 'Illustrative screening thresholds, not a local design standard',
              'duration_s': 86400, 'baseline_pressure_min_m': float(pressures.min().min()),
              'flagged_nodes': sum(bool(r['flags']) for r in node_rows),
              'flagged_pipes': sum(bool(r['flags']) for r in pipe_rows),
              'flagged_pump_points': sum(bool(r['flags']) for r in pump_rows),
              'fire_scenarios': fire_rows,
              'limitation': 'Demand-driven fire checks impose requested flow; negative pressure means infeasible supply.'}
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report
