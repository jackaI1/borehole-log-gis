import pytest

from process_hydraulics.scenarios import thermal_expansion_relief

CASE = dict(
    overall_heat_transfer_w_m2_k=100,
    heat_transfer_area_m2=10,
    heat_source_temperature_k=353.15,
    liquid_temperature_k=313.15,
    saturation_temperature_at_relief_k=473.15,
    blocked_volume_m3=2,
    density_kg_m3=800,
    heat_capacity_j_kg_k=2000,
    volumetric_expansion_per_k=0.001,
    reference_water_density_kg_m3=1000,
)
SIZING = dict(
    inlet_kpa_abs=1101.325,
    backpressure_kpa_abs=101.325,
    vapor_pressure_kpa_abs=2,
    kd=0.65,
    kw=1,
    kc=1,
    kv=1,
)


def test_blocked_in_heat_exchanger_derives_load_and_sizes_relief():
    r = thermal_expansion_relief(**CASE, sizing_inputs=SIZING)
    # Independent energy/volume balance: 40 kW / 3.2 MJ/K = .0125 K/s;
    # .001/K * 2 m3 * .0125 K/s = .000025 m3/s = 1.5 L/min.
    assert r.heat_input_w == 40000
    assert r.heating_rate_k_s == pytest.approx(0.0125)
    assert r.flow_m3_s == pytest.approx(0.000025)
    assert r.flow_l_min == pytest.approx(1.5)
    assert r.mass_flow_kg_h == pytest.approx(72)
    assert r.specific_gravity == pytest.approx(0.8)
    assert r.sizing.area_mm2 == pytest.approx(0.768897035296, rel=1e-8)


def test_volume_changes_heating_rate_but_not_continuous_expansion_load():
    r = thermal_expansion_relief(**(CASE | dict(blocked_volume_m3=4)), sizing_inputs=SIZING)
    assert r.heating_rate_k_s == pytest.approx(0.00625)
    assert r.flow_l_min == pytest.approx(1.5)


def test_heat_input_and_expansion_coefficient_change_derived_area():
    r = thermal_expansion_relief(
        **(CASE | dict(heat_transfer_area_m2=20, volumetric_expansion_per_k=0.002)),
        sizing_inputs=SIZING,
    )
    assert r.flow_l_min == pytest.approx(6)
    assert r.sizing.area_mm2 == pytest.approx(3.07558814118555, rel=1e-8)


@pytest.mark.parametrize("key", CASE)
@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True])
def test_invalid_thermal_inputs_rejected(key, bad):
    with pytest.raises(ValueError):
        thermal_expansion_relief(**(CASE | {key: bad}), sizing_inputs=SIZING)


@pytest.mark.parametrize(
    "changes",
    [
        dict(liquid_temperature_k=353.15),
        dict(liquid_temperature_k=400),
        dict(saturation_temperature_at_relief_k=350),
        dict(saturation_temperature_at_relief_k=353.15),
    ],
)
def test_cooling_or_possible_boiling_requires_another_method(changes):
    with pytest.raises(ValueError):
        thermal_expansion_relief(**(CASE | changes), sizing_inputs=SIZING)


def test_computed_load_cannot_be_replaced_and_flashing_remains_rejected():
    with pytest.raises(ValueError):
        thermal_expansion_relief(**CASE, sizing_inputs=SIZING | dict(flow_l_min=999))
    with pytest.raises(ValueError):
        thermal_expansion_relief(**CASE, sizing_inputs=SIZING | dict(specific_gravity=1))
    with pytest.raises(ValueError):
        thermal_expansion_relief(**CASE, sizing_inputs=SIZING | dict(vapor_pressure_kpa_abs=200))


def test_unrepresentable_heat_duty_is_flagged():
    with pytest.raises(ValueError):
        thermal_expansion_relief(
            **(CASE | dict(overall_heat_transfer_w_m2_k=1e308)), sizing_inputs=SIZING
        )
