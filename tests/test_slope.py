import json
import math
from pathlib import Path

import numpy as np
import pytest

from borehole_gis import slope as S
from borehole_gis.model import Dataset, Hole, Interval
from borehole_gis.readers import read_ags
from borehole_gis.slope_cli import main

ROOT = Path(__file__).resolve().parents[1]


def homogeneous(strength, water=None, ground=None, bottom=-40.0):
    ground = ground or [(-30.0, 10.0), (0.0, 10.0), (10.0, 5.0), (40.0, 5.0)]
    layers = [S.Layer('CLAY', 10.0, -40.0, strength, material='CLAY')]
    return S.Section(ground=ground, layers=layers, bottom=bottom, water=water)


def test_bishop_matches_infinite_slope_closed_form():
    # Identical slices along a plane dipping at beta reproduce Skempton's infinite slope:
    # FS = c'/(gamma z sin b cos b) + tan(phi')/tan(b), with z the vertical depth.
    beta = math.atan(0.5)
    c, phi, gamma, z = 5.0, math.radians(30), 20.0, 2.0
    slices = [(gamma * z * 1.0, beta, 1.0, 0.0, c, phi) for _ in range(20)]
    expected = c / (gamma * z * math.sin(beta) * math.cos(beta)) + math.tan(phi) / math.tan(beta)
    assert S.bishop_fos(slices) == pytest.approx(expected, rel=1e-6)


def test_bishop_pore_pressure_reduces_factor_of_safety():
    beta = math.atan(0.5)
    dry = [(40.0, beta, 1.0, 0.0, 0.0, math.radians(30))] * 10
    wet = [(40.0, beta, 1.0, 10.0, 0.0, math.radians(30))] * 10
    assert S.bishop_fos(wet) < S.bishop_fos(dry)


def test_bishop_returns_none_without_driving_moment():
    assert S.bishop_fos([(10.0, -0.3, 1.0, 0.0, 5.0, 0.4)]) is None


def test_phi_zero_factor_equals_cohesion_over_moment_identity():
    # With phi = 0 Bishop's simplified method reduces to FS = c * sum(b/cos a) / sum(W sin a),
    # which is exact moment equilibrium for a circle. Check it against the printed slice table.
    section = homogeneous(S.Strength(19.0, 10.0, 0.0))
    found = S.search(section, np.arange(-6, 12, 2.0), np.arange(6, 20, 2.0), np.arange(4, 14, 2.0))
    crit = found.critical
    assert crit is not None
    length = sum(s['width'] / math.cos(math.radians(s['alpha_deg'])) for s in crit.slices)
    driving = sum(s['weight_kN_per_m'] * math.sin(math.radians(s['alpha_deg'])) for s in crit.slices)
    assert crit.fos == pytest.approx(10.0 * length / driving, rel=1e-9)


def test_taylor_chart_stability_number_for_45_degree_slope():
    # Taylor (1937) chart, undrained clay (phi = 0), 1V:1H cut, deep base: the critical stability number
    # Ns = c / (gamma H) is about 0.181. The grid search must land on that critical value.
    H, c, gamma = 10.0, 10.0, 20.0
    ground = [(-40.0, 10.0), (0.0, 10.0), (10.0, 0.0), (60.0, 0.0)]
    layers = [S.Layer('CLAY', 10.0, -50.0, S.Strength(gamma, c, 0.0), material='CLAY')]
    section = S.Section(ground=ground, layers=layers, bottom=-50.0)
    found = S.search(section, np.arange(0, 12.5, 2.5), np.arange(17.5, 27.5, 2.5), np.linspace(44, 48, 5))
    assert found.critical is not None
    stability_number = c / (gamma * H) / found.critical.fos
    assert stability_number == pytest.approx(0.181, rel=0.005)


def test_phi_zero_factor_scales_with_cohesion_and_ignores_water():
    circle = (4.0, 16.0, 9.0)
    dry = S.evaluate_circle(homogeneous(S.Strength(19.0, 10.0, 0.0)), *circle)
    doubled = S.evaluate_circle(homogeneous(S.Strength(19.0, 20.0, 0.0)), *circle)
    wet = S.evaluate_circle(homogeneous(S.Strength(19.0, 10.0, 0.0), water=[(-30, 9.0), (40, 9.0)]), *circle)
    assert dry.status == 'ok'
    assert doubled.fos == pytest.approx(2 * dry.fos, rel=1e-9)
    assert wet.fos == pytest.approx(dry.fos, rel=1e-9)


def test_water_table_lowers_factor_of_safety_with_friction():
    circle = (4.0, 16.0, 9.0)
    dry = S.evaluate_circle(homogeneous(S.Strength(19.0, 8.0, 26.0)), *circle)
    wet = S.evaluate_circle(homogeneous(S.Strength(19.0, 8.0, 26.0), water=[(-30, 9.0), (40, 9.0)]), *circle)
    assert wet.fos < dry.fos


def test_slice_count_converges():
    section = homogeneous(S.Strength(19.0, 8.0, 26.0))
    coarse = S.evaluate_circle(section, 4.0, 16.0, 9.0, slices=30)
    fine = S.evaluate_circle(section, 4.0, 16.0, 9.0, slices=120)
    assert abs(coarse.fos - fine.fos) / fine.fos < 0.01


def test_layer_without_strength_is_flagged_not_guessed():
    section = homogeneous(S.Strength())
    result = S.evaluate_circle(section, 4.0, 16.0, 9.0)
    assert result.status == 'missing_strength'
    assert result.fos is None
    assert result.missing == ['CLAY']
    found = S.search(section, [4.0], [16.0], [9.0])
    assert found.critical is None
    assert found.counts() == {'missing_strength': 1}


def test_search_skips_surfaces_through_unknown_layer():
    # Upper clay has values; a weak layer at depth has none. Surfaces touching only the upper clay still count.
    layers = [
        S.Layer('CLAY', 10.0, 2.0, S.Strength(19.0, 8.0, 26.0), material='CLAY'),
        S.Layer('BOULDER', 2.0, -40.0, S.Strength(), material='BOULDER', note='no strength row'),
    ]
    section = S.Section(ground=[(-30.0, 10.0), (0.0, 10.0), (10.0, 5.0), (40.0, 5.0)], layers=layers,
                        bottom=-40.0)
    found = S.search(section, np.arange(-4, 8, 2.0), np.arange(6, 16, 1.0), np.arange(3, 12, 1.0))
    assert found.counts().get('missing_strength', 0) > 0
    assert found.critical is not None
    assert found.critical.missing == []
    assert found.critical.fos > 0


def test_strength_table_keeps_blanks_missing(tmp_path):
    path = tmp_path / 'strengths.csv'
    path.write_text('pattern,unit_weight_kn_m3,cohesion_kpa,friction_deg\n'
                    'CLAY,19.5,8,26\nBOULDER,,,\n', encoding='utf-8')
    rows = dict(S.load_strengths(path))
    assert rows['CLAY'] == S.Strength(19.5, 8.0, 26.0)
    assert rows['BOULDER'] == S.Strength(None, None, None)
    assert not rows['BOULDER'].complete


@pytest.mark.parametrize('body, message', [
    ('pattern,unit_weight_kn_m3,cohesion_kpa\nCLAY,19,8\n', 'needs columns'),
    ('pattern,unit_weight_kn_m3,cohesion_kpa,friction_deg\nCLAY,-1,8,26\n', 'invalid unit_weight_kn_m3'),
    ('pattern,unit_weight_kn_m3,cohesion_kpa,friction_deg\nCLAY,19,8,95\n', 'invalid friction_deg'),
    ('pattern,unit_weight_kn_m3,cohesion_kpa,friction_deg\n ,19,8,26\n', 'pattern is empty'),
])
def test_strength_table_rejects_bad_values(tmp_path, body, message):
    path = tmp_path / 'bad.csv'
    path.write_text(body, encoding='utf-8')
    with pytest.raises(ValueError, match=message):
        S.load_strengths(path)


def test_ambiguous_description_is_flagged():
    ds = Dataset('EPSG:27700', holes=[Hole('X', 0, 0, 5.0, 1)],
                 intervals=[Interval('X', 0.0, 5.0, 'sandy CLAY and SILT', 2)])
    strengths = [('CLAY', S.Strength(19, 8, 26)), ('SILT', S.Strength(18, 2, 28))]
    layers, _ = S.layers_for_hole(ds, 'X', 100.0, strengths)
    assert layers[0].note == 'several strength rows match'
    assert not layers[0].strength.complete


def test_longest_whole_word_pattern_wins():
    ds = Dataset('EPSG:27700', holes=[Hole('X', 0, 0, 5.0, 1)],
                 intervals=[Interval('X', 0.0, 5.0, 'MADE GROUND: Grey sandy GRAVEL', 2)])
    strengths = [('GRAVEL', S.Strength(20, 0, 34)), ('MADE GROUND', S.Strength(18, 0, 30))]
    layers, _ = S.layers_for_hole(ds, 'X', 100.0, strengths)
    assert layers[0].material == 'MADE GROUND'


def test_section_rejects_bad_geometry():
    with pytest.raises(ValueError, match='increasing x'):
        S.Section(ground=[(0.0, 10.0), (0.0, 9.0)], layers=[], bottom=0.0)
    with pytest.raises(ValueError, match='below the lowest ground point'):
        S.Section(ground=[(0.0, 10.0), (5.0, 9.0)], layers=[], bottom=9.5)


def test_circle_below_logged_depth_is_not_contained():
    section = homogeneous(S.Strength(19.0, 8.0, 26.0), bottom=4.5)
    result = S.evaluate_circle(section, 4.0, 16.0, 12.0)  # lowest point at 4.0 m, below the 4.5 m bottom
    assert result.status == 'not_contained'


def test_sample_run_writes_outputs_and_matches_recorded_value(tmp_path):
    out = tmp_path / 'slope'
    code = main([
        '--log', str(ROOT / 'samples' / 'bgs_bh01.ags'), '--format', 'ags', '--crs', 'EPSG:27700',
        '--strengths', str(ROOT / 'samples' / 'slope' / 'strengths.csv'),
        '--section', str(ROOT / 'samples' / 'slope' / 'section.json'), '--out', str(out),
    ])
    assert code == 0
    report = json.loads((out / 'report.json').read_text())
    assert report['status'] == 'complete'
    # Recorded output of this code on the illustrative sample inputs (see docs/slope-stability.md).
    assert report['fos'] == pytest.approx(1.4948, abs=1e-3)
    assert (out / 'section.png').stat().st_size > 10_000
    assert (out / 'surfaces.csv').read_text().count('\n') == report['surfaces'] + 1


def test_cli_refuses_existing_output(tmp_path):
    out = tmp_path / 'slope'
    out.mkdir()
    (out / 'keep.txt').write_text('x')
    with pytest.raises(SystemExit) as exc:
        main(['--log', str(ROOT / 'samples' / 'bgs_bh01.ags'), '--format', 'ags', '--crs', 'EPSG:27700',
              '--strengths', str(ROOT / 'samples' / 'slope' / 'strengths.csv'),
              '--section', str(ROOT / 'samples' / 'slope' / 'section.json'), '--out', str(out)])
    assert exc.value.code == 2


def test_section_depth_guard_uses_logged_hole(tmp_path):
    ds = read_ags(ROOT / 'samples' / 'bgs_bh01.ags', 'EPSG:27700')
    strengths = S.load_strengths(ROOT / 'samples' / 'slope' / 'strengths.csv')
    data = json.loads((ROOT / 'samples' / 'slope' / 'section.json').read_text())
    data['analysis_bottom'] = 80.0
    path = tmp_path / 'section.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='below the depth logged'):
        S.load_section(path, ds, strengths)
