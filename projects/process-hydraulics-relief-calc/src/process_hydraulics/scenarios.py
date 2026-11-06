"""A limited API 521 blocked-in-liquid thermal-expansion contingency.

Heat duty is derived from U A delta-T. The API 521 liquid thermal-expansion
balance derives the release rate, then API 520 sizes its effective relief area.
See docs/thermal-relief.md for reference, dimensional derivation and exclusions.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from .relief import LiquidSizing, size_liquid
from .validation import number

LIQUID_FACTOR_FIELDS = frozenset(
    {"inlet_kpa_abs", "backpressure_kpa_abs", "vapor_pressure_kpa_abs", "kd", "kw", "kc", "kv"}
)


@dataclass(frozen=True)
class ThermalRelief:
    heat_input_w: float
    heating_rate_k_s: float
    flow_m3_s: float
    flow_l_min: float
    mass_flow_kg_h: float
    specific_gravity: float
    sizing: LiquidSizing


def thermal_expansion_relief(
    *,
    overall_heat_transfer_w_m2_k: float,
    heat_transfer_area_m2: float,
    heat_source_temperature_k: float,
    liquid_temperature_k: float,
    saturation_temperature_at_relief_k: float,
    blocked_volume_m3: float,
    density_kg_m3: float,
    heat_capacity_j_kg_k: float,
    volumetric_expansion_per_k: float,
    reference_water_density_kg_m3: float,
    sizing_inputs: Mapping[str, float],
) -> ThermalRelief:
    """Derive liquid relief for a rigid, fully liquid-filled, blocked-in exchanger.

    Requires a heat source below liquid saturation temperature at relieving inlet
    pressure. No phase change, reaction, incoming flow, vessel expansion or heat
    loss is credited. Properties and maximum credible U/A/temperatures are inputs.
    """
    inputs = dict(
        overall_heat_transfer_w_m2_k=overall_heat_transfer_w_m2_k,
        heat_transfer_area_m2=heat_transfer_area_m2,
        heat_source_temperature_k=heat_source_temperature_k,
        liquid_temperature_k=liquid_temperature_k,
        saturation_temperature_at_relief_k=saturation_temperature_at_relief_k,
        blocked_volume_m3=blocked_volume_m3,
        density_kg_m3=density_kg_m3,
        heat_capacity_j_kg_k=heat_capacity_j_kg_k,
        volumetric_expansion_per_k=volumetric_expansion_per_k,
        reference_water_density_kg_m3=reference_water_density_kg_m3,
    )
    for name, value in inputs.items():
        number(name, value, positive=True)
    if heat_source_temperature_k <= liquid_temperature_k:
        raise ValueError("thermal-expansion case requires a heat source hotter than the liquid")
    if saturation_temperature_at_relief_k <= heat_source_temperature_k:
        raise ValueError(
            "heat source can reach liquid saturation at relieving pressure; "
            "boiling/two-phase assessment is required"
        )
    if not isinstance(sizing_inputs, Mapping) or set(sizing_inputs) != LIQUID_FACTOR_FIELDS:
        raise ValueError(
            "sizing_inputs must contain exactly inlet_kpa_abs, backpressure_kpa_abs, "
            "vapor_pressure_kpa_abs, kd, kw, kc and kv; load and gravity are derived"
        )
    heat = number(
        "derived heat_input_w",
        overall_heat_transfer_w_m2_k
        * heat_transfer_area_m2
        * (heat_source_temperature_k - liquid_temperature_k),
        positive=True,
    )
    thermal_capacity = number(
        "liquid thermal_capacity_j_k",
        density_kg_m3 * blocked_volume_m3 * heat_capacity_j_kg_k,
        positive=True,
    )
    rate = number("derived heating_rate_k_s", heat / thermal_capacity, positive=True)
    flow = number(
        "derived thermal flow_m3_s",
        volumetric_expansion_per_k * blocked_volume_m3 * rate,
        positive=True,
    )
    flow_l_min = number("derived flow_l_min", flow * 60000, positive=True)
    mass_flow = number("derived mass_flow_kg_h", flow * density_kg_m3 * 3600, positive=True)
    gravity = number(
        "derived specific_gravity", density_kg_m3 / reference_water_density_kg_m3, positive=True
    )
    sizing = size_liquid(flow_l_min=flow_l_min, specific_gravity=gravity, **sizing_inputs)
    return ThermalRelief(heat, rate, flow, flow_l_min, mass_flow, gravity, sizing)
