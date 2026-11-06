"""Calculate core quality without hiding questionable field observations."""


from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class CoreRun:
    hole_id: str
    top_m: float
    base_m: float
    pieces_m: tuple[float, ...]
    fractures: int


def assess_runs(runs, dataset):
    """Return one row per run and overlapping source layers, with review flags.

    RQD counts recovered pieces at least 0.1 m long divided by drilled length.
    Fracture frequency is the logged count divided by drilled length.
    """
    runs = list(runs)
    rows = []
    for run_index, run in enumerate(runs):
        flags = []
        holes = [h for h in dataset.holes if h.id == run.hole_id]
        valid = (isfinite(run.top_m) and isfinite(run.base_m)
                 and run.top_m >= 0 and run.base_m > run.top_m)
        pieces_valid = all(isfinite(p) and p >= 0 for p in run.pieces_m)
        count_valid = isinstance(run.fractures, int) and not isinstance(run.fractures, bool) and run.fractures >= 0
        if not valid:
            flags.append('invalid interval')
        if not pieces_valid:
            flags.append('invalid piece length')
        if not count_valid:
            flags.append('invalid fracture count')
        if len(holes) != 1:
            flags.append('unknown or ambiguous borehole')
        elif valid and run.base_m > holes[0].final_depth:
            flags.append('beyond borehole depth')
        if valid and any(other_index != run_index and other.hole_id == run.hole_id
                         and isfinite(other.top_m) and isfinite(other.base_m)
                         and other.top_m < run.base_m and run.top_m < other.base_m
                         for other_index, other in enumerate(runs)):
            flags.append('overlapping runs')
        length = run.base_m - run.top_m if valid else None
        recovered = sum(run.pieces_m) if pieces_valid else None
        if length and recovered is not None and recovered > length + 1e-9:
            flags.append('recovery exceeds run length')
        rqd = 100 * sum(p for p in run.pieces_m if p >= 0.1) / length if length and pieces_valid else None
        freq = run.fractures / length if length and count_valid else None
        quality = None
        if rqd is not None and rqd <= 100 + 1e-7 and 'recovery exceeds run length' not in flags:
            quality = ('very poor' if rqd < 25 else 'poor' if rqd < 50 else
                       'fair' if rqd < 75 else 'good' if rqd < 90 else 'excellent')
        layers = [i for i in dataset.intervals if valid and i.hole_id == run.hole_id
                  and i.top < run.base_m and run.top_m < i.base]
        rows.append({'hole_id': run.hole_id, 'top_m': run.top_m if isfinite(run.top_m) else None,
                     'base_m': run.base_m if isfinite(run.base_m) else None,
                     'recovered_m': recovered, 'rqd_percent': rqd, 'rqd_quality': quality,
                     'fractures_per_m': freq, 'review_flags': flags,
                     'layers': [{'top_m': i.top, 'base_m': i.base, 'description': i.description}
                                for i in layers]})
    return rows


def read_core_runs(path):
    """Read explicit metre lengths, keeping missing fields as input errors."""
    import json

    content = json.loads(path.read_text())
    if not isinstance(content, dict) or content.get('depth_unit') != 'm':
        raise ValueError('Core-run JSON must declare depth_unit: m')
    if not isinstance(content.get('runs'), list):
        raise ValueError('Core-run JSON must contain a runs array')
    runs = []
    for row in content['runs']:
        if not isinstance(row, dict) or set(row) != {'hole_id', 'top_m', 'base_m', 'pieces_m', 'fractures'}:
            raise ValueError('Each run requires hole_id, top_m, base_m, pieces_m and fractures')
        if (not isinstance(row['hole_id'], str) or not isinstance(row['pieces_m'], list)
                or any(isinstance(v, bool) or not isinstance(v, (float, int))
                       for v in [row['top_m'], row['base_m'], *row['pieces_m']])):
            raise ValueError('Core depths and pieces must be numeric metre lengths')
        runs.append(CoreRun(row['hole_id'], row['top_m'], row['base_m'], tuple(row['pieces_m']), row['fractures']))
    return runs


def export_core_runs(runs, dataset, output):
    """Export one row per run/layer intersection; preserve runs with no match."""
    import csv
    import json

    rows = assess_runs(runs, dataset)
    with (output / 'core_runs.json').open('w') as handle:
        json.dump(rows, handle, indent=2, allow_nan=False)
        handle.write('\n')
    fields = ['run_index', 'hole_id', 'hole_x', 'hole_y', 'hole_crs', 'hole_final_depth_m',
              'top_m', 'base_m', 'recovered_m', 'rqd_percent', 'rqd_quality', 'fractures_per_m',
              'review_flags', 'layer_top_m', 'layer_base_m', 'layer_description', 'overlap_m']
    with (output / 'core_runs.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(rows, 1):
            hole = [h for h in dataset.holes if h.id == row['hole_id']]
            base = {key: value for key, value in row.items() if key != 'layers'}
            base['review_flags'] = '; '.join(row['review_flags'])
            base.update(run_index=index, hole_crs=dataset.crs)
            if len(hole) == 1:
                base.update(hole_x=hole[0].x, hole_y=hole[0].y, hole_final_depth_m=hole[0].final_depth)
            for layer in row['layers'] or [None]:
                joined = base.copy()
                if layer:
                    joined.update(layer_top_m=layer['top_m'], layer_base_m=layer['base_m'],
                                  layer_description=layer['description'],
                                  overlap_m=min(row['base_m'], layer['base_m']) - max(row['top_m'], layer['top_m']))
                writer.writerow(joined)
    return rows
