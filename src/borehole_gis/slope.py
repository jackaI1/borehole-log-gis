"""Limit-equilibrium slope stability with Bishop's simplified method.

The soil layers come from a parsed borehole log. Strength values come from a
separate table matched to the log descriptions. A layer with no matching or
incomplete strength values is reported, never filled in with a guess.
"""

import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

GAMMA_W = 9.81  # kN/m3, unit weight of water
SEARCH_SAMPLES = 801  # points used to find where a circle daylights on the ground
BISHOP_TOLERANCE = 1e-6
BISHOP_MAX_ITER = 200
# Below this share of the slip mass weight, the driving moment is too small to give a meaningful FOS.
DRIVING_FRACTION_MIN = 1e-3


@dataclass(frozen=True)
class Strength:
    unit_weight: float | None = None  # kN/m3, total unit weight
    cohesion: float | None = None  # kPa, effective cohesion c'
    friction: float | None = None  # degrees, effective friction angle phi'

    @property
    def complete(self):
        return None not in (self.unit_weight, self.cohesion, self.friction)


@dataclass(frozen=True)
class Layer:
    name: str  # the borehole description
    top: float  # elevation, m
    base: float  # elevation, m
    strength: Strength
    material: str = ''  # the strength-table pattern that matched, if any
    note: str = ''


@dataclass
class Section:
    ground: list  # [(x, z), ...] from crest to toe, x increasing
    layers: list  # [Layer, ...] taken from the borehole, horizontal across the section
    bottom: float  # lowest elevation a slip surface may reach
    water: list | None = None  # [(x, z), ...] piezometric level, optional

    def __post_init__(self):
        _check_profile(self.ground, 'ground_surface')
        if self.water is not None:
            _check_profile(self.water, 'water_table')
        if self.bottom >= min(z for _, z in self.ground):
            raise ValueError('analysis bottom must be below the lowest ground point')


def _check_profile(points, label):
    if len(points) < 2 or any(b[0] <= a[0] for a, b in zip(points, points[1:])):
        raise ValueError(f'{label} needs at least two points with strictly increasing x')


@dataclass
class CircleResult:
    xc: float
    zc: float
    radius: float
    status: str = 'no_daylight'  # ok, missing_strength, no_daylight, not_contained, no_driving, not_converged
    fos: float | None = None
    entry: float | None = None
    exit: float | None = None
    slices: list = field(default_factory=list)
    missing: list = field(default_factory=list)


def _interp(points, x):
    xs = [p[0] for p in points]
    zs = [p[1] for p in points]
    return np.interp(x, xs, zs)


def _overlap(layer, zb, zt):
    return max(0.0, min(zt, layer.top) - max(zb, layer.base))


def _layer_at(layers, z):
    for layer in layers:
        if layer.base <= z <= layer.top:
            return layer
    return None


def _root(f, a, b):
    """Bisect a sign change of f between a and b."""
    positive_at_a = f(a) > 0
    for _ in range(60):
        m = (a + b) / 2
        if (f(m) > 0) == positive_at_a:
            a = m
        else:
            b = m
    return (a + b) / 2


def bishop_fos(slices, tol=BISHOP_TOLERANCE, max_iter=BISHOP_MAX_ITER):
    """Bishop's simplified factor of safety.

    Each slice is (W, alpha, b, u, c, phi): weight kN/m, base angle rad, width m,
    pore pressure kPa at the base, cohesion kPa, friction rad. Returns None when the
    iteration fails, the slice denominator is non-positive, or m_alpha goes non-positive.
    """
    driving = sum(W * math.sin(a) for W, a, _, _, _, _ in slices)
    if driving <= 0:
        return None
    fos = 1.5
    for _ in range(max_iter):
        numerator = 0.0
        for W, a, b, u, c, phi in slices:
            m_alpha = math.cos(a) + math.sin(a) * math.tan(phi) / fos
            if m_alpha <= 0:
                return None
            numerator += (c * b + (W - u * b) * math.tan(phi)) / m_alpha
        new = numerator / driving
        if new <= 0:
            return None
        if abs(new - fos) < tol:
            return new
        fos = new
    return None


def evaluate_circle(section, xc, zc, radius, slices=30):
    """Factor of safety for one circular slip surface through the section."""
    result = CircleResult(xc, zc, radius)
    gx = [p[0] for p in section.ground]
    x0, x1 = gx[0], gx[-1]
    lo, hi = max(x0, xc - radius), min(x1, xc + radius)
    if hi <= lo:
        return result

    def arc(x):
        return zc - math.sqrt(max(radius * radius - (x - xc) ** 2, 0.0))

    def ground(x):
        return float(_interp(section.ground, x))

    def gap(x):
        return ground(x) - arc(x)

    xs = np.linspace(lo, hi, SEARCH_SAMPLES)
    arcs = zc - np.sqrt(np.maximum(radius * radius - (xs - xc) ** 2, 0.0))
    inside = _interp(section.ground, xs) > arcs
    idx = np.flatnonzero(inside)
    if idx.size == 0:
        return result
    breaks = np.flatnonzero(np.diff(idx) > 1)
    starts = np.concatenate(([0], breaks + 1))
    ends = np.concatenate((breaks, [idx.size - 1]))
    first, last = max(zip(starts, ends), key=lambda se: idx[se[1]] - idx[se[0]])
    i0, i1 = idx[first], idx[last]
    if i0 == 0 or i1 == len(xs) - 1:
        result.status = 'not_contained'  # the arc would leave the section
        return result
    entry = _root(gap, xs[i0 - 1], xs[i0])
    exit_ = _root(gap, xs[i1], xs[i1 + 1])
    result.entry, result.exit = entry, exit_
    seg = np.linspace(entry, exit_, 2001)
    if float(np.min(zc - np.sqrt(np.maximum(radius * radius - (seg - xc) ** 2, 0.0)))) <= section.bottom + 1e-3:
        result.status = 'not_contained'  # the slip surface goes below the logged depth
        return result

    width = (exit_ - entry) / slices
    missing = set()
    rows = []
    for i in range(slices):
        xm = entry + (i + 0.5) * width
        top = ground(xm)
        base = arc(xm)
        height = top - base
        weight_per_m = 0.0
        covered = 0.0
        for layer in section.layers:
            ov = _overlap(layer, base, top)
            if ov > 0:
                covered += ov
                if not layer.strength.complete:
                    missing.add(layer.material or layer.name)
                else:
                    weight_per_m += layer.strength.unit_weight * ov
        if covered < height - 1e-6:
            missing.add('unlogged interval')
        base_layer = _layer_at(section.layers, base - 1e-6)
        if base_layer is None:
            missing.add('unlogged interval')
        elif not base_layer.strength.complete:
            missing.add(base_layer.material or base_layer.name)
        # Positive where the slip base dips toward the toe: gravity drives those slices.
        sin_a = (xc - xm) / radius
        pore = 0.0
        if section.water is not None:
            water_z = min(float(_interp(section.water, xm)), top)
            pore = GAMMA_W * max(0.0, water_z - base)
        rows.append({
            'x_mid': xm, 'width': width, 'top': top, 'base': base,
            'alpha_deg': math.degrees(math.asin(sin_a)), 'weight_kN_per_m': width * weight_per_m,
            'pore_pressure_kPa': pore, 'base_layer': base_layer.name if base_layer else '',
            'cohesion_kPa': base_layer.strength.cohesion if base_layer and base_layer.strength.complete else None,
            'friction_deg': base_layer.strength.friction if base_layer and base_layer.strength.complete else None,
            'sin_a': sin_a,
        })
    result.slices = rows
    if missing:
        result.status = 'missing_strength'
        result.missing = sorted(missing)
        return result

    driving = sum(r['weight_kN_per_m'] * r['sin_a'] for r in rows)
    total_weight = sum(r['weight_kN_per_m'] for r in rows)
    if driving <= DRIVING_FRACTION_MIN * total_weight:
        result.status = 'no_driving'  # the mass sits upslope of the centre: nothing drives it to slide
        return result

    bishop_slices = [
        (r['weight_kN_per_m'], math.asin(r['sin_a']), width, r['pore_pressure_kPa'],
         r['cohesion_kPa'], math.radians(r['friction_deg']))
        for r in rows
    ]
    fos = bishop_fos(bishop_slices)
    if fos is None:
        result.status = 'not_converged'
        return result
    result.status = 'ok'
    result.fos = fos
    return result


@dataclass
class SearchResult:
    critical: CircleResult | None
    results: list

    def counts(self):
        out = {}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out


def search(section, centres_x, centres_z, radii, slices=30):
    """Evaluate every centre/radius combination and keep the lowest complete FOS."""
    results = []
    for xc in centres_x:
        for zc in centres_z:
            for radius in radii:
                results.append(evaluate_circle(section, float(xc), float(zc), float(radius), slices))
    complete = [r for r in results if r.status == 'ok']
    critical = min(complete, key=lambda r: r.fos) if complete else None
    return SearchResult(critical, results)


def load_strengths(path):
    """Read strength rows: pattern matched inside the log description, then values.

    Blank values stay missing (None). They are never filled in.
    """
    required = {'pattern', 'unit_weight_kn_m3', 'cohesion_kpa', 'friction_deg'}
    rows = []
    with open(path, newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        if not required <= set(reader.fieldnames or []):
            raise ValueError(f'strength table needs columns: {", ".join(sorted(required))}')
        for line_no, row in enumerate(reader, start=2):
            pattern = row['pattern'].strip().upper()
            if not pattern:
                raise ValueError(f'strength row {line_no}: pattern is empty')
            strength = Strength(
                _number(row['unit_weight_kn_m3'], line_no, 'unit_weight_kn_m3', positive=True),
                _number(row['cohesion_kpa'], line_no, 'cohesion_kpa'),
                _number(row['friction_deg'], line_no, 'friction_deg', upper=90),
            )
            rows.append((pattern, strength))
    if not rows:
        raise ValueError('strength table has no rows')
    return rows


def _number(text, line_no, field_name, positive=False, upper=None):
    text = (text or '').strip()
    if not text:
        return None
    value = float(text)
    if not math.isfinite(value) or value < 0 or (positive and value == 0) or (upper and value >= upper):
        raise ValueError(f'strength row {line_no}: invalid {field_name} {text}')
    return value


def _match_layer(interval, elevation, key, strengths):
    """Pick the strength row whose whole-word pattern is longest. A tie with different values is ambiguous."""
    top, base = elevation - interval.top, elevation - interval.base
    matches = [(pattern, strength) for pattern, strength in strengths
               if re.search(rf'\b{re.escape(pattern)}\b', key)]
    if not matches:
        return Layer(interval.description, top, base, Strength(), note='no strength row')
    longest = max(len(pattern) for pattern, _ in matches)
    best = [(pattern, strength) for pattern, strength in matches if len(pattern) == longest]
    if len({strength for _, strength in best}) > 1:
        return Layer(interval.description, top, base, Strength(), note='several strength rows match')
    pattern, strength = best[0]
    return Layer(interval.description, top, base, strength, material=pattern)


def layers_for_hole(dataset, hole_id, elevation, strengths):
    """Turn one borehole's intervals into elevation layers with matched strengths."""
    holes = [h for h in dataset.holes if h.id == hole_id]
    if len(holes) != 1:
        raise ValueError(f'borehole {hole_id!r} must appear exactly once in the log')
    hole = holes[0]
    intervals = sorted((i for i in dataset.intervals if i.hole_id == hole_id), key=lambda i: i.top)
    if not intervals:
        raise ValueError(f'borehole {hole_id!r} has no logged intervals')
    layers = []
    for interval in intervals:
        key = interval.description.strip().upper()
        layer = _match_layer(interval, elevation, key, strengths)
        layers.append(layer)
    return layers, hole


def load_section(path, dataset, strengths):
    """Build the Section from the JSON file and the borehole it names."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    hole_id = data['borehole']
    elevation = float(data['borehole_elevation'])
    layers, hole = layers_for_hole(dataset, hole_id, elevation, strengths)
    bottom = float(data['analysis_bottom'])
    if bottom < elevation - hole.final_depth - 1e-6:
        raise ValueError('analysis_bottom is below the depth logged in the borehole')
    section = Section(
        ground=[(float(x), float(z)) for x, z in data['ground_surface']],
        layers=layers,
        bottom=bottom,
        water=[(float(x), float(z)) for x, z in data['water_table']] if data.get('water_table') else None,
    )
    return section, data


def _linspace(spec):
    start, stop, count = spec
    return np.linspace(float(start), float(stop), int(count))


def analyse(dataset, strengths_path, section_path, out, slices=30):
    """Run the search, write the output files and return the report."""
    strengths = load_strengths(strengths_path)
    section, data = load_section(section_path, dataset, strengths)
    grid = data.get('search', {})
    found = search(
        section,
        _linspace(grid.get('centres_x', [-2, 26, 15])),
        _linspace(grid.get('centres_z', [96, 120, 13])),
        _linspace(grid.get('radii', [4, 22, 10])),
        slices=slices,
    )
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    counts = found.counts()
    excluded = sum(n for status, n in counts.items() if status == 'missing_strength')
    missing_layers = sorted({m for r in found.results for m in r.missing})
    crit = found.critical

    with (out / 'layers.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['description', 'top_elevation_m', 'base_elevation_m', 'thickness_m',
                         'unit_weight_kn_m3', 'cohesion_kpa', 'friction_deg', 'status'])
        for layer in section.layers:
            s = layer.strength
            writer.writerow([layer.name, round(layer.top, 3), round(layer.base, 3),
                             round(layer.top - layer.base, 3), s.unit_weight, s.cohesion, s.friction,
                             'complete' if s.complete else (layer.note or 'incomplete strength')])

    with (out / 'surfaces.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['centre_x_m', 'centre_z_m', 'radius_m', 'status', 'fos', 'entry_x_m', 'exit_x_m',
                         'missing'])
        for r in found.results:
            writer.writerow([round(r.xc, 3), round(r.zc, 3), round(r.radius, 3), r.status,
                             None if r.fos is None else round(r.fos, 4),
                             None if r.entry is None else round(r.entry, 3),
                             None if r.exit is None else round(r.exit, 3), '; '.join(r.missing)])

    slice_rows = crit.slices if crit else []
    with (out / 'critical_slices.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['x_mid_m', 'width_m', 'top_m', 'base_m', 'alpha_deg', 'weight_kN_per_m',
                         'pore_pressure_kPa', 'base_layer', 'cohesion_kpa', 'friction_deg'])
        for r in slice_rows:
            writer.writerow([round(r['x_mid'], 3), round(r['width'], 4), round(r['top'], 3),
                             round(r['base'], 3), round(r['alpha_deg'], 3), round(r['weight_kN_per_m'], 3),
                             round(r['pore_pressure_kPa'], 3), r['base_layer'], r['cohesion_kPa'],
                             r['friction_deg']])

    if crit is None:
        status = 'no_complete_surface'
    elif excluded:
        status = 'partial'
    else:
        status = 'complete'
    report = {
        'method': "Bishop's simplified method, circular slip surfaces, total weight with pore pressure",
        'status': status,
        'fos': None if crit is None else round(crit.fos, 4),
        'critical_surface': None if crit is None else {
            'centre_x_m': round(crit.xc, 3), 'centre_z_m': round(crit.zc, 3),
            'radius_m': round(crit.radius, 3), 'entry_x_m': round(crit.entry, 3),
            'exit_x_m': round(crit.exit, 3), 'slices': slices,
        },
        'surfaces': len(found.results),
        'surface_status_counts': counts,
        'surfaces_not_evaluated_missing_strength': excluded,
        'missing_strength_layers': missing_layers,
        'water_table': section.water is not None,
        'warnings': [
            f'{excluded} surfaces were not evaluated because they cross layers without complete strength values'
        ] if excluded else [],
    }
    (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    plot_section(section, crit, out / 'section.png', report)
    return report


def plot_section(section, crit, path, report):
    import matplotlib

    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    # Colour follows the strength row, in fixed order. Missing strength is grey and hatched.
    palette = ['#0072B2', '#E69F00', '#009E73', '#CC79A7']
    order = {}
    for layer in section.layers:
        if layer.strength.complete and layer.material not in order:
            order[layer.material] = palette[len(order) % len(palette)]
    grey = '#8C8C8C'

    gx = np.linspace(section.ground[0][0], section.ground[-1][0], 400)
    ground = _interp(section.ground, gx)
    fig, ax = plt.subplots(figsize=(9, 5))
    handles = []
    for layer in section.layers:
        lo = np.maximum(layer.base, section.bottom)
        hi = np.minimum(layer.top, ground)
        if layer.strength.complete:
            colour, hatch, label = order[layer.material], None, layer.material
        else:
            colour, hatch, label = grey, '//', f'{layer.material or "unmatched"}: strength missing'
        ax.fill_between(gx, lo, hi, where=hi > lo, facecolor=colour, edgecolor='white', hatch=hatch,
                        linewidth=0.6, alpha=0.85)
        if label not in [h.get_label() for h in handles]:
            handles.append(Patch(facecolor=colour, edgecolor='white', hatch=hatch, label=label))
    ax.plot(gx, ground, color='#222222', linewidth=2)
    if section.water is not None:
        wx = np.linspace(gx[0], gx[-1], 200)
        ax.plot(wx, _interp(section.water, wx), color='#1f4e79', linestyle='--', linewidth=1.5)
        handles.append(plt.Line2D([], [], color='#1f4e79', linestyle='--', label='Water table'))
    if crit is not None:
        arc_x = np.linspace(crit.entry, crit.exit, 200)
        arc_z = crit.zc - np.sqrt(np.maximum(crit.radius ** 2 - (arc_x - crit.xc) ** 2, 0))
        ax.plot(arc_x, arc_z, color='black', linewidth=2.2)
        ax.plot(crit.xc, crit.zc, marker='+', color='black', markersize=8)
        ax.set_title(f'Critical circle: FOS = {crit.fos:.2f} (Bishop simplified)', loc='left')
    else:
        ax.set_title('No surface with complete strength values', loc='left')
    if report['status'] == 'partial':
        ax.text(0.99, 0.02, 'Surfaces through grey layers were not evaluated', transform=ax.transAxes,
                ha='right', va='bottom', fontsize=8, color='#444444')
    ax.set_xlabel('Distance along section (m)')
    ax.set_ylabel('Elevation (m)')
    ax.set_aspect('equal', adjustable='datalim')
    ax.set_ylim(section.bottom - 1.0, float(ground.max()) + 6.0)
    ax.grid(axis='y', color='#dddddd', linewidth=0.6)
    ax.legend(handles=handles, loc='upper right', frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
