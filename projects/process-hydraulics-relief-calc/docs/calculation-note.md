# Calculation note: Water transfer line with two process branches

Preliminary study calculation. This is not a certified valve selection or an approval to operate equipment.

## Supplied assumptions

- Synthetic study case, not data from an operating plant.
- Water is Newtonian and incompressible with constant properties; reservoirs have negligible surface velocity and equal pressure.
- K values are assumed totals for clean, fully open fittings at each pipe's own velocity; verify against the actual fittings supplier.
- All pipes are full and single phase. Pump curve is illustrative at fixed speed; acceptable flow range is supplied, not inferred.
- Gas and liquid relief cases are independent worked checks, not relief loads derived from the water-transfer operating point.
- The thermal-expansion exchanger is an independent synthetic relief scenario with its load derived from heat input; it is not connected to the water-transfer pump model.

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

## Network at requested flow

Flow: **0.008 m³/s**. Required pressure: **94350.8 Pa**. Required head: **9.64038 m**.

Parallel branch pressures are shared. Only the stage pressures add in series; adding all pipe rows would double-count parallel paths.

| Stage | Shared pressure change (Pa) |
| --- | ---: |
| 1 | 3894.69 |
| 2 | 58498.5 |
| 3 | 31957.6 |

| Pipe | Flow (m³/s) | Speed (m/s) | Re | Darcy f | Friction (Pa) | Fittings (Pa) | Elevation (Pa) | Total (Pa) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| common inlet | 0.008 | 1.01859 | 101655 | 0.0200755 | 3118.1 | 776.59 | 0 | 3894.69 |
| process A | 0.00338895 | 1.02129 | 66251 | 0.0222074 | 8001.91 | 1561.41 | 48935.2 | 58498.5 |
| process B | 0.00461105 | 0.91734 | 73240.4 | 0.0214565 | 7883.66 | 1679.66 | 48935.2 | 58498.5 |
| common outlet | 0.008 | 1.01859 | 101655 | 0.0200755 | 2078.73 | 517.727 | 29361.1 | 31957.6 |

## Pump operating point

**FLAG: OUTSIDE supplied acceptable flow range.**

Pump head: **14.646 m**. Curve points are linearly interpolated without extrapolation.

Flow: **0.016677 m³/s**. Required pressure: **143341 Pa**. Required head: **14.646 m**.

Parallel branch pressures are shared. Only the stage pressures add in series; adding all pipe rows would double-count parallel paths.

| Stage | Shared pressure change (Pa) |
| --- | ---: |
| 1 | 15833.1 |
| 2 | 87591.2 |
| 3 | 39916.5 |

| Pipe | Flow (m³/s) | Speed (m/s) | Re | Darcy f | Friction (Pa) | Fittings (Pa) | Elevation (Pa) | Total (Pa) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| common inlet | 0.016677 | 2.12338 | 211914 | 0.0184579 | 12458.3 | 3374.8 | 0 | 15833.1 |
| process A | 0.00706086 | 2.12785 | 138034 | 0.0203802 | 31878 | 6778.04 | 48935.2 | 87591.2 |
| process B | 0.00961614 | 1.91307 | 152740 | 0.0196192 | 31351 | 7305.04 | 48935.2 | 87591.2 |
| common outlet | 0.016677 | 2.12338 | 211914 | 0.0184579 | 8305.56 | 2249.87 | 29361.1 | 39916.5 |

## Gas relief

Independent critical-gas worked check based on LESER example 7.4.9.1. The supplied ethylene release rate is 4200 kg/h; scenario selection and required load are engineering inputs, not calculated by this tool.

Factor basis: Preliminary effective-area Kd=0.975, Kb=1 and Kc=1 as in the published check. No rupture disk. Gas properties are supplied at relieving conditions.

Minimum effective area: **79.2027 mm²**.

API 520 Part I critical gas equation: A = W sqrt(T Z/M)/(C Kd P1 Kb Kc). C = 0.03948 sqrt(k (2/(k+1))^((k+1)/(k-1))).

Metric C: 0.025527062; absolute P2/P1: 0.17903866; critical ratio: 0.56642596. Critical-flow check passes.

## Liquid relief

Independent viscous-liquid worked check based on LESER example 7.4.9.5: supplied glycerin flow 5 L/s = 300 L/min. A complete API 521 contingency assessment is outside this example.

Factor basis: Effective-area Kd=0.65, Kw=1, Kc=1. Supplied Kv=0.789 corresponds to the published G-orifice iteration; this tool does not infer Kv or select an orifice. Vapor pressure 0.01 kPa absolute is a synthetic nonflashing-screen input, not a property prediction.

Minimum effective area: **233.22 mm²**.

API 520 Part I liquid equation: A = 11.78 Q sqrt(G/(P1-P2))/(Kd Kw Kc Kv).

Pressure difference: 1100 kPa. P2 > vapor pressure screen passes; this does not rule out nozzle cavitation. Kv is supplied and must be verified for the selected orifice.

## Limits and required review

API 521 thermal-expansion loads are calculated only for the supported blocked-in liquid heat-exchanger case. Other scenario selection and loads remain supplied inputs. This tool does not determine fire loads, accumulation allowances, inlet-line loss limits, disposal-system backpressure or certified capacity. Final valve selection requires manufacturer data and an engineering review. It does not cover steam, two-phase relief, noncritical gas flow, arbitrary meshed pipe networks, NPSH, pump efficiency or cavitation assessment.

Equation sources and worked checks: [equations.md](https://github.com/jackaI1/process-hydraulics-relief-calc/blob/main/docs/equations.md).

## Complete input record

```json
{
  "title": "Water transfer line with two process branches",
  "assumptions": [
    "Synthetic study case, not data from an operating plant.",
    "Water is Newtonian and incompressible with constant properties; reservoirs have negligible surface velocity and equal pressure.",
    "K values are assumed totals for clean, fully open fittings at each pipe's own velocity; verify against the actual fittings supplier.",
    "All pipes are full and single phase. Pump curve is illustrative at fixed speed; acceptable flow range is supplied, not inferred.",
    "Gas and liquid relief cases are independent worked checks, not relief loads derived from the water-transfer operating point.",
    "The thermal-expansion exchanger is an independent synthetic relief scenario with its load derived from heat input; it is not connected to the water-transfer pump model."
  ],
  "fluid": {
    "density_kg_m3": 998,
    "viscosity_pa_s": 0.001
  },
  "flow_m3_s": 0.008,
  "network": {
    "stages": [
      {
        "branches": [
          {
            "pipes": [
              {
                "name": "common inlet",
                "length_m": 30,
                "diameter_m": 0.1,
                "roughness_m": 4.5e-05,
                "fitting_k": 1.5,
                "elevation_m": 0
              }
            ]
          }
        ]
      },
      {
        "branches": [
          {
            "pipes": [
              {
                "name": "process A",
                "length_m": 45,
                "diameter_m": 0.065,
                "roughness_m": 4.5e-05,
                "fitting_k": 3,
                "elevation_m": 5
              }
            ]
          },
          {
            "pipes": [
              {
                "name": "process B",
                "length_m": 70,
                "diameter_m": 0.08,
                "roughness_m": 4.5e-05,
                "fitting_k": 4,
                "elevation_m": 5
              }
            ]
          }
        ]
      },
      {
        "branches": [
          {
            "pipes": [
              {
                "name": "common outlet",
                "length_m": 20,
                "diameter_m": 0.1,
                "roughness_m": 4.5e-05,
                "fitting_k": 1,
                "elevation_m": 3
              }
            ]
          }
        ]
      }
    ]
  },
  "pump": {
    "points": [
      [
        0,
        30
      ],
      [
        0.008,
        26
      ],
      [
        0.016,
        16
      ],
      [
        0.024,
        0
      ]
    ],
    "acceptable_flow_m3_s": [
      0.006,
      0.016
    ]
  },
  "gas_relief": {
    "scenario": "Independent critical-gas worked check based on LESER example 7.4.9.1. The supplied ethylene release rate is 4200 kg/h; scenario selection and required load are engineering inputs, not calculated by this tool.",
    "factor_basis": "Preliminary effective-area Kd=0.975, Kb=1 and Kc=1 as in the published check. No rupture disk. Gas properties are supplied at relieving conditions.",
    "inputs": {
      "mass_flow_kg_h": 4200,
      "temperature_k": 328.15,
      "molecular_weight_kg_kmol": 28.03,
      "k": 1.19,
      "compressibility": 0.712,
      "inlet_kpa_abs": 6151.325,
      "backpressure_kpa_abs": 1101.325,
      "kd": 0.975,
      "kb": 1,
      "kc": 1
    }
  },
  "liquid_relief": {
    "scenario": "Independent viscous-liquid worked check based on LESER example 7.4.9.5: supplied glycerin flow 5 L/s = 300 L/min. A complete API 521 contingency assessment is outside this example.",
    "factor_basis": "Effective-area Kd=0.65, Kw=1, Kc=1. Supplied Kv=0.789 corresponds to the published G-orifice iteration; this tool does not infer Kv or select an orifice. Vapor pressure 0.01 kPa absolute is a synthetic nonflashing-screen input, not a property prediction.",
    "inputs": {
      "flow_l_min": 300,
      "specific_gravity": 1.26,
      "inlet_kpa_abs": 1201.325,
      "backpressure_kpa_abs": 101.325,
      "vapor_pressure_kpa_abs": 0.01,
      "kd": 0.65,
      "kw": 1,
      "kc": 1,
      "kv": 0.789
    }
  },
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
