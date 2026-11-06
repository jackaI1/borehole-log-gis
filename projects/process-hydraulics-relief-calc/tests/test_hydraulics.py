import math

import pytest

from process_hydraulics.hydraulics import (
    Branch,
    Fluid,
    Network,
    ParallelStage,
    Pipe,
    PumpCurve,
    friction_factor,
    operating_point,
)

WATER = Fluid(density_kg_m3=1000, viscosity_pa_s=0.001)


def pipe(name="p", **changes):
    return Pipe(
        **(
            dict(name=name, length_m=10, diameter_m=0.01, roughness_m=0, fitting_k=0, elevation_m=0)
            | changes
        )
    )


def line(p):
    return Network((ParallelStage((Branch((p,)),)),))


def test_laminar_matches_hagen_poiseuille():
    # 128 mu L Q / (pi D^4), independent Hagen-Poiseuille reference.
    r = pipe().evaluate(1e-6, WATER)
    assert r.reynolds == pytest.approx(127.3239545)
    assert r.friction_pa == pytest.approx(40.74366543)
    assert r.friction_factor == pytest.approx(0.5026548246)


@pytest.mark.parametrize(
    "re,rough,want",
    [
        (100000, 0.001, 0.02217453594),
        (1000000, 0, 0.011645040998),
        (1000, 0, 0.064),
    ],
)
def test_darcy_factor_reference_roots(re, rough, want):
    assert friction_factor(re, rough) == pytest.approx(want, rel=1e-8)


def test_fittings_and_elevation_are_separate():
    r = pipe(fitting_k=2, elevation_m=3).evaluate(1e-6, WATER)
    assert r.fittings_pa == pytest.approx(0.1621138938)
    assert r.elevation_pa == pytest.approx(29419.95)
    assert r.total_pa == pytest.approx(29460.8557793)
    assert pipe(elevation_m=-3).evaluate(0, WATER).total_pa == pytest.approx(-29419.95)


def test_turbulent_water_textbook_style_case():
    # 100 m of D=0.1 m steel at 2 m/s, rho=998, mu=0.001, epsilon=0.045 mm.
    r = pipe(length_m=100, diameter_m=0.1, roughness_m=0.000045).evaluate(
        math.pi * 0.1**2 / 4 * 2, Fluid(998, 0.001)
    )
    assert r.friction_factor == pytest.approx(0.0185637607736078, rel=2e-6)
    assert r.friction_pa == pytest.approx(37053.2665041, rel=2e-6)


def test_parallel_branches_conserve_flow_and_equalize_pressure():
    # Laminar resistances L and 2L mean a 2:1 split, not an equal split.
    a = Branch((pipe("a", elevation_m=3),))
    b = Branch((pipe("b", length_m=20, elevation_m=3),))
    r = Network((ParallelStage((a, b)),)).evaluate(1.5e-6, WATER)
    assert [p.flow_m3_s for p in r.pipes] == pytest.approx([1e-6, 0.5e-6], rel=1e-7)
    assert r.pipes[0].total_pa == pytest.approx(r.pipes[1].total_pa, abs=1e-7)
    assert r.total_pa == pytest.approx(29460.69366543)
    assert r.head_m == pytest.approx(r.total_pa / 9806.65)


def test_series_stages_add_pressure_without_adding_branch_flows():
    s = ParallelStage((Branch((pipe("a"),)),))
    t = ParallelStage((Branch((pipe("b"), pipe("c"))),))
    r = Network((s, t)).evaluate(1e-6, WATER)
    assert r.total_pa == pytest.approx(122.23099629)
    assert all(p.flow_m3_s == pytest.approx(1e-6) for p in r.pipes)


def test_pump_intersection_is_interpolated_and_flagged():
    # Laminar system h=4154.697...*Q, pump 1-5e5*Q: root 1.98351816e-6.
    curve = PumpCurve(((0, 1), (2e-6, 0)))
    r = operating_point(line(pipe()), WATER, curve, (1.1e-6, 1.9e-6))
    assert r.flow_m3_s == pytest.approx(1.98351816e-6, rel=1e-7)
    assert r.pump_head_m == pytest.approx(r.system.head_m, abs=1e-8)
    assert not r.within_acceptable_flow
    assert curve.head_at(0.5e-6) == pytest.approx(0.75)


def test_pump_does_not_extrapolate_or_invent_intersection():
    curve = PumpCurve(((0, 1), (1e-6, 0.5)))
    with pytest.raises(ValueError, match="outside"):
        curve.head_at(2e-6)
    with pytest.raises(ValueError, match="intersection"):
        operating_point(line(pipe()), WATER, curve, (0, 1e-6))


@pytest.mark.parametrize("re", [2300, 3000, 3999.99])
def test_transition_rejected(re):
    with pytest.raises(ValueError, match="transitional"):
        friction_factor(re, 0)


def test_final_network_and_pump_cannot_hide_transition():
    q = 3000 * math.pi * 0.01 * 0.001 / (4 * 1000)
    n = line(pipe())
    with pytest.raises(ValueError, match="transitional"):
        n.evaluate(q, WATER)
    # Constant-ish system-crossing curve chosen at a transitional flow.
    with pytest.raises(ValueError, match="transitional"):
        operating_point(n, WATER, PumpCurve(((q * 0.9, 100), (q * 1.1, 0))), (0, q * 2))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True])
def test_invalid_fluid_or_flow_is_not_calculated(bad):
    with pytest.raises(ValueError):
        Fluid(bad, 0.001)
    with pytest.raises(ValueError):
        line(pipe()).evaluate(bad, WATER)


def test_geometry_topology_and_model_limits_checked():
    with pytest.raises(ValueError):
        pipe(diameter_m=0)
    with pytest.raises(ValueError, match="roughness"):
        pipe(roughness_m=0.001)
    with pytest.raises(ValueError, match="elevation"):
        ParallelStage((Branch((pipe("a"),)), Branch((pipe("b", elevation_m=1),))))
    with pytest.raises(ValueError):
        Branch(())
    with pytest.raises(ValueError):
        Network(())
    with pytest.raises(ValueError, match="unique"):
        Network((ParallelStage((Branch((pipe(), pipe())),)),))
    with pytest.raises(ValueError):
        friction_factor(1e9, 0)
    with pytest.raises(ValueError):
        PumpCurve(((0, 1), (1, 2)))


def test_pump_head_must_be_nonnegative():
    with pytest.raises(ValueError):
        PumpCurve(((0, 1), (1, -1)))


def test_tiny_parallel_flow_retains_relative_mass_balance():
    a = Branch((pipe("a"),))
    b = Branch((pipe("b", length_m=2e1),))
    r = Network((ParallelStage((a, b)),)).evaluate(1.5e-18, WATER)
    assert [p.flow_m3_s for p in r.pipes] == pytest.approx([1e-18, 0.5e-18], rel=1e-7, abs=0)


@pytest.mark.parametrize("large_diameter", [0.3, 1])
def test_strongly_unequal_laminar_branches_keep_mass_and_energy(large_diameter):
    a = Branch((pipe("narrow", diameter_m=0.002),))
    b = Branch((pipe("wide", diameter_m=large_diameter),))
    r = Network((ParallelStage((a, b)),)).evaluate(1e-6, WATER)
    # Hagen-Poiseuille parallel resistances: conductance proportional to D^4/L.
    expected_narrow = 1e-6 * 0.002**4 / (0.002**4 + large_diameter**4)
    expected_pressure = 128 * 0.001 * 10 * 1e-6 / (math.pi * (0.002**4 + large_diameter**4))
    assert sum(p.flow_m3_s for p in r.pipes) == pytest.approx(1e-6, rel=1e-8)
    assert r.pipes[0].flow_m3_s == pytest.approx(expected_narrow, rel=1e-8, abs=0)
    assert r.pipes[0].total_pa == pytest.approx(r.pipes[1].total_pa, rel=1e-8, abs=0)
    assert r.total_pa == pytest.approx(expected_pressure, rel=1e-8, abs=0)


@pytest.mark.parametrize("changes", [dict(length_m=1e308), dict(elevation_m=1e308)])
def test_nonfinite_hydraulic_results_are_flagged(changes):
    with pytest.raises(ValueError):
        pipe(diameter_m=0.1, **changes).evaluate(0.001, WATER)


def test_total_network_overflow_is_flagged():
    # Each static elevation pressure is finite; their series sum is not.
    stages = tuple(ParallelStage((Branch((pipe(str(i), elevation_m=1e304),)),)) for i in range(3))
    with pytest.raises(ValueError):
        Network(stages).evaluate(0, WATER)


def test_unrepresentable_cross_section_is_flagged():
    with pytest.raises(ValueError):
        pipe(diameter_m=1e-200).evaluate(0.001, WATER)


@pytest.mark.parametrize("flow", [1e-4, 1e-2])
def test_unequal_branches_balance_even_with_wide_search_bracket(flow):
    stage = ParallelStage(
        (Branch((pipe("narrow", diameter_m=0.002),)), Branch((pipe("wide", diameter_m=0.3),)))
    )
    r = Network((stage,)).evaluate(flow, WATER)
    assert sum(p.flow_m3_s for p in r.pipes) == pytest.approx(flow, rel=1e-8)
    assert r.pipes[0].total_pa == pytest.approx(r.pipes[1].total_pa, rel=1e-8, abs=0)
