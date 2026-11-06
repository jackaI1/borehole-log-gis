import pytest

from process_hydraulics.relief import size_gas, size_liquid

GAS = dict(
    mass_flow_kg_h=4200,
    temperature_k=328.15,
    molecular_weight_kg_kmol=28.03,
    k=1.19,
    compressibility=0.712,
    inlet_kpa_abs=6151.325,
    backpressure_kpa_abs=1101.325,
    kd=0.975,
    kb=1,
    kc=1,
)
LIQUID = dict(
    flow_l_min=300,
    specific_gravity=1.26,
    inlet_kpa_abs=1201.325,
    backpressure_kpa_abs=101.325,
    vapor_pressure_kpa_abs=0.01,
    kd=0.65,
    kw=1,
    kc=1,
    kv=1,
)


def test_gas_leser_7491_manufacturer_example():
    # LESER 7.4.9.1: 0.122 in^2 published effective minimum area, rounded.
    r = size_gas(**GAS)
    assert r.area_mm2 == pytest.approx(0.122 * 645.16, rel=0.01)
    assert r.area_mm2 == pytest.approx(79.2026697804, rel=1e-10)
    assert r.critical_pressure_ratio == pytest.approx(0.566425958603, rel=1e-7)
    assert r.backpressure_ratio == pytest.approx(0.179038662402, rel=1e-7)


def test_liquid_leser_7495_inviscid_first_step():
    # LESER 7.4.9.5: 0.285 in^2 before viscosity correction.
    r = size_liquid(**LIQUID)
    assert r.area_mm2 == pytest.approx(0.285 * 645.16, rel=0.003)
    assert r.differential_kpa == 1100


def test_liquid_viscosity_correction_matches_published_final_step():
    # Kv=0.789 supplied for selected G effective orifice, not guessed from pipe Re.
    r = size_liquid(**(LIQUID | dict(kv=0.789)))
    assert r.area_mm2 == pytest.approx(0.362 * 645.16, rel=0.003)


def test_simple_hand_calculated_areas_and_corrections():
    r = size_liquid(
        **(LIQUID | dict(flow_l_min=100, specific_gravity=1, inlet_kpa_abs=1101.325, kd=1))
    )
    assert r.area_mm2 == pytest.approx(37.25163108)
    base = size_gas(**GAS).area_mm2
    assert size_gas(**(GAS | dict(kb=0.8, kc=0.9))).area_mm2 == pytest.approx(base / 0.72)
    base = size_liquid(**LIQUID).area_mm2
    assert size_liquid(**(LIQUID | dict(kw=0.8, kc=0.9, kv=0.7))).area_mm2 == pytest.approx(
        base / (0.8 * 0.9 * 0.7)
    )


def test_subcritical_gas_is_flagged():
    with pytest.raises(ValueError, match="critical"):
        size_gas(**(GAS | dict(backpressure_kpa_abs=5000)))


def test_choked_boundary_and_pressure_order():
    critical = 0.566425958603
    assert size_gas(**(GAS | dict(backpressure_kpa_abs=6151.325 * (critical - 1e-6)))).area_mm2 > 0
    with pytest.raises(ValueError):
        size_gas(**(GAS | dict(backpressure_kpa_abs=6151.325 * (critical + 1e-6))))
    with pytest.raises(ValueError):
        size_gas(**(GAS | dict(backpressure_kpa_abs=7000)))


def test_flashing_screen_and_liquid_pressure_order():
    for changes in [
        dict(vapor_pressure_kpa_abs=101.325),
        dict(vapor_pressure_kpa_abs=1300),
        dict(backpressure_kpa_abs=1300),
    ]:
        with pytest.raises(ValueError):
            size_liquid(**(LIQUID | changes))


@pytest.mark.parametrize("key", GAS)
@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan"), True])
def test_gas_invalid_inputs(key, bad):
    with pytest.raises(ValueError):
        size_gas(**(GAS | {key: bad}))


@pytest.mark.parametrize("key", LIQUID)
@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan"), True])
def test_liquid_invalid_inputs(key, bad):
    with pytest.raises(ValueError):
        size_liquid(**(LIQUID | {key: bad}))


@pytest.mark.parametrize(
    "changes",
    [
        dict(k=1),
        dict(k=2),
        dict(kd=1.01),
        dict(kb=1.01),
        dict(kc=1.01),
        dict(compressibility=0.1),
        dict(compressibility=3),
    ],
)
def test_gas_scope_limits(changes):
    with pytest.raises(ValueError):
        size_gas(**(GAS | changes))


@pytest.mark.parametrize("key", ["kd", "kw", "kc", "kv"])
def test_liquid_coefficients_cannot_exceed_one(key):
    with pytest.raises(ValueError):
        size_liquid(**(LIQUID | {key: 1.01}))


def test_near_isothermal_gas_uses_stable_limit():
    r = size_gas(**(GAS | {"k": 1.0000000000000002}))
    assert r.critical_pressure_ratio == pytest.approx(0.606530659713, rel=1e-10)
    assert r.c_metric == pytest.approx(0.0239458304455, rel=1e-10)


def test_underflowing_correction_product_is_flagged():
    with pytest.raises(ValueError):
        size_liquid(**(LIQUID | {"kd": 1e-200, "kw": 1e-200}))
