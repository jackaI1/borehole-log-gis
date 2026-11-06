# Calculation note: Blocked-in liquid exchanger thermal relief

Preliminary study calculation. This is not a certified valve selection or an approval to operate equipment.

## Supplied assumptions

- Synthetic nonboiling liquid filled exchanger; all temperatures and properties are supplied for the stated relieving condition.
- The heat-transfer inputs represent a conservative credible duty for this contingency. Other contingencies need separate assessment.

## API 521 blocked-in-liquid thermal expansion

Blocked-in cold side of a liquid-filled exchanger: both liquid isolation valves are shut while the warmer utility continues flowing. Thermal expansion is credible because the trapped liquid has no normal outlet; this calculation evaluates that contingency only, without claiming it governs all other cases.

Factor and contingency basis: Synthetic oil properties at relieving conditions, with the lowest credible liquid temperature and maximum credible U and heat-transfer area for this case. Rigid fully filled volume; no heat-loss or vessel-expansion credit, reaction, inflow or phase change. Saturation temperature is supplied at the same relieving inlet pressure; the utility is cooler than this temperature. Kd=0.65 and Kw=Kc=Kv=1 are explicit preliminary effective-area assumptions, to be verified for the actual valve and low-viscosity liquid.

Rigid fully liquid-filled exchanger, liquid isolation valves closed, heat source still active. No incoming flow, reaction, heat-loss credit or vessel-expansion credit. The supplied heat-source temperature is below saturation temperature at relieving inlet pressure; boiling screen passes.

Heat balance: H = U A (Tsource - Tliquid); dT/dt = H/(ρ V cp). API 521 thermal-expansion balance: Q = β V dT/dt = β H/(ρ cp). This derives the required liquid load before API 520 sizing.

Derived heat input: **40000 W**. Heating rate: **0.0125 K/s**.

Derived relief load: **1.5 L/min**, **72 kg/h** (2.5e-05 m³/s). Derived specific gravity: **0.8**.

API 520 Part I: A = 11.78 Q sqrt(G/(P1-P2))/(Kd Kw Kc Kv). Q and G come directly from the thermal calculation and cannot be overridden.

Minimum effective area: **0.768897 mm²**; pressure difference: **1000 kPa**. The liquid flashing screen also passes; nozzle cavitation still requires review.

This evaluates one thermal-expansion contingency. It does not establish that thermal expansion governs over fire, tube rupture or other credible cases. A very small calculated area is not a recommendation to buy a valve that small.

## Model and units

Steady single-phase Newtonian liquid hydraulics: ΔP = (f L/D + ΣK) ρv²/2 + ρgΔz, g = 9.80665 m/s². Darcy f = 64/Re below 2300; Colebrook above or at 4000. Re in [2300, 4000) is rejected in reported results. Root searches may cross a linear transitional interpolation; every final pipe result is checked strictly.

Hydraulic inputs: m, m³/s, kg/m³, Pa·s and dimensionless K. Reservoir boundary velocities are negligible. Terminal entrance and exit losses must be included in supplied K. Positive elevation consumes pressure. Relative roughness > 0.05 and Re > 1e8 are unsupported.

Relief inputs: kg/h, K, kg/kmol, L/min, dimensionless factors and kPa absolute. Areas are minimum effective areas in mm². Gas scope: critical flow, 1 < k ≤ 1.67 and 0.2 ≤ Z ≤ 2. Liquid scope: supplied viscosity correction and nonflashing service. Factors must be in (0, 1].

## Limits and required review

API 521 thermal-expansion loads are calculated only for the supported blocked-in liquid heat-exchanger case. Other scenario selection and loads remain supplied inputs. This tool does not determine fire loads, accumulation allowances, inlet-line loss limits, disposal-system backpressure or certified capacity. Final valve selection requires manufacturer data and an engineering review. It does not cover steam, two-phase relief, noncritical gas flow, arbitrary meshed pipe networks, NPSH, pump efficiency or cavitation assessment.

Equation sources and worked checks: [equations.md](https://github.com/jackaI1/process-hydraulics-relief-calc/blob/main/docs/equations.md).

## Complete input record

```json
{
  "title": "Blocked-in liquid exchanger thermal relief",
  "assumptions": [
    "Synthetic nonboiling liquid filled exchanger; all temperatures and properties are supplied for the stated relieving condition.",
    "The heat-transfer inputs represent a conservative credible duty for this contingency. Other contingencies need separate assessment."
  ],
  "thermal_relief": {
    "scenario": "Blocked-in cold side of a liquid-filled exchanger: both liquid isolation valves are shut while the warmer utility continues flowing. Thermal expansion is credible because the trapped liquid has no normal outlet; this calculation evaluates that contingency only, without claiming it governs all other cases.",
    "factor_basis": "Synthetic oil properties at relieving conditions, with the lowest credible liquid temperature and maximum credible U and heat-transfer area for this case. Rigid fully filled volume; no heat-loss or vessel-expansion credit, reaction, inflow or phase change. Saturation temperature is supplied at the same relieving inlet pressure; the utility is cooler than this temperature. Kd=0.65 and Kw=Kc=Kv=1 are explicit preliminary effective-area assumptions, to be verified for the actual valve and low-viscosity liquid.",
    "load_inputs": {
      "overall_heat_transfer_w_m2_k": 100,
      "heat_transfer_area_m2": 10,
      "heat_source_temperature_k": 353.15,
      "liquid_temperature_k": 313.15,
      "saturation_temperature_at_relief_k": 473.15,
      "blocked_volume_m3": 2,
      "density_kg_m3": 800,
      "heat_capacity_j_kg_k": 2000,
      "volumetric_expansion_per_k": 0.001,
      "reference_water_density_kg_m3": 1000
    },
    "sizing_inputs": {
      "inlet_kpa_abs": 1101.325,
      "backpressure_kpa_abs": 101.325,
      "vapor_pressure_kpa_abs": 2,
      "kd": 0.65,
      "kw": 1,
      "kc": 1,
      "kv": 1
    }
  }
}
```
