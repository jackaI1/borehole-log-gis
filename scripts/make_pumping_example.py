"""Regenerate tiny, explicitly synthetic pumping and recovery examples."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from borehole_gis.pumping import residual_theis, theis

output = Path('samples/pumping')
output.mkdir(parents=True, exist_ok=True)
start = pd.Timestamp('2026-01-01T00:00:00Z')
metadata = {'start': str(start), 'rate': 10, 'rate_unit': 'L/s', 'radius': 20,
            'radius_unit': 'm', 'drawdown_unit': 'm', 'pressure_unit': 'kPa',
            'reference_pressure': 101.3, 'barometric_efficiency': .65}
for mode in ['pumping', 'recovery']:
    elapsed = np.geomspace(1, 100000, 70)
    if mode == 'recovery':
        drawdown = residual_theis(elapsed, 600, .01, 20, .001, .0002)
        elapsed += 600
    else:
        drawdown = theis(elapsed, .01, 20, .001, .0002)
    rng = np.random.default_rng(2026)
    pressure = 101.3 + .5 * np.sin(np.arange(70))
    observed = drawdown + .65 * (pressure - 101.3) / 9.80665 + rng.normal(0, .003, 70)
    pd.DataFrame({'timestamp': [str(start + pd.Timedelta(seconds=float(t))) for t in elapsed],
                  'drawdown': observed, 'barometric_pressure': pressure}).to_csv(
                      output / ('drawdown.csv' if mode == 'pumping' else 'recovery.csv'), index=False)
    meta = dict(metadata)
    if mode == 'recovery':
        meta['stop'] = str(start + pd.Timedelta(seconds=600))
    (output / f'{mode}.json').write_text(json.dumps(meta, indent=2) + '\n')
(output / 'source.json').write_text(json.dumps({
    'synthetic': True, 'generator': 'scripts/make_pumping_example.py',
    'parameters': {'T_m2_s': .001, 'S': .0002, 'Q_m3_s': .01, 'radius_m': 20},
    'noise': 'Independent Gaussian drawdown noise, sd 0.003 m, seed 2026; sinusoidal pressure',
    'field_data': False}, indent=2) + '\n')
