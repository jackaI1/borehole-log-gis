# Blocked-in exchanger: API 521 load into API 520 sizing

I use a fully liquid-filled exchanger as a worked overpressure contingency. Both liquid-side isolation valves have closed, but the warm utility still flows. The trapped liquid expands on heating and has no normal outlet. A relief path must release that expansion to limit further pressure rise. This is one credible scenario, not a conclusion that it governs fire, tube rupture or every other contingency.

Run the entire calculation:

```sh
hydraulics-calc examples/thermal-expansion.json --output thermal-note.md
```

[The generated note](thermal-calculation-note.md) contains the assumptions, derived heat duty, release rate, area and complete input record. `scenarios.py` passes its computed flow and density ratio directly to `relief.size_liquid`; the input format does not allow overriding either derived quantity.

## Reference and balance

[LESER Engineering](https://www.leser.com/-/media/files/engineering/leser_engineering.pdf), section 7.4.8.2, printed page 7.4-21 (PDF page 181), gives the API 521 thermal-expansion relation for trapped liquid that does not evaporate. Its US form is `q = β H / (500 G cp)` with q in US gpm, β in 1/°F, H in Btu/h and cp in Btu/(lb·°F). The SI form uses the same energy/volume balance, with the density conversion made explicit here:

```text
H = U A (Tsource - Tliquid)            [W = J/s]
dT/dt = H / (ρ V cp)                  [K/s]
Qrelief = β V dT/dt = β H / (ρ cp)     [m³/s]
Wrelief = ρ Qrelief × 3600             [kg/h]
```

U is the overall heat-transfer coefficient in W/(m²·K); A is the active area in m²; ρ is actual liquid density in kg/m³; V is trapped volume in m³; cp is specific heat in J/(kg·K); β is the **volumetric** expansion coefficient in 1/K. Do not use a metal's linear expansion coefficient. Multiplying m³/s by 60000 gives L/min. The supplied reference-water density defines G=ρ/ρwater for the downstream API 520 calculation. The handbook's SI conversion uses approximately 1000 kg/m³ for water; this example states that reference explicitly.

## Independent hand calculation

This is a synthetic oil case, with inputs chosen to make the energy balance easy to audit:

| Quantity | Input |
| --- | ---: |
| U | 100 W/(m²·K) |
| A | 10 m² |
| Utility / liquid temperature | 353.15 / 313.15 K |
| Saturation temperature at relieving inlet pressure | 473.15 K |
| Trapped volume | 2 m³ |
| Density / heat capacity | 800 kg/m³ / 2000 J/(kg·K) |
| Volumetric expansion coefficient | 0.001 1/K |
| Reference-water density | 1000 kg/m³ |

The duty is `100 × 10 × 40 = 40000 W`. The liquid thermal capacity is `800 × 2 × 2000 = 3200000 J/K`, so it heats at **0.0125 K/s**. The expansion rate is `0.001 × 2 × 0.0125 = 0.000025 m³/s`, or **1.5 L/min**. Multiplying by density and 3600 gives **72 kg/h**. The trapped volume cancels from the continuous expansion rate, although a larger volume heats more slowly; a test checks both effects.

For API 520 liquid sizing, P1=1101.325 kPa absolute, P2=101.325 kPa absolute, G=0.8, Kd=0.65 and Kw=Kc=Kv=1:

```text
Aeffective = 11.78 × 1.5 / 0.65 × sqrt(0.8/1000)
           = 0.768897035296 mm²
```

Tests compare every derived result to independent literal values and verify that doubling heat input doubles the release rate and area. The integration test edits the JSON area input and checks the changed note, rather than supplying a new release rate.

## Applicability and decisions still needed

The liquid is assumed fully trapped, single phase and well mixed, with constant properties at the relevant relieving condition. The supplied U, area and temperature difference must bound the credible heat duty; a nominal operating duty may not be conservative. No credit is taken for heat escaping to the surroundings or vessel expansion. Compressibility, elasticity and valve cycling are not modeled; this is the expansion-load balance once relieving conditions are reached, not a time-to-opening prediction.

The code requires `Tliquid < Tsource < Tsaturation_at_relief`. The second inequality is a conservative tool restriction so this worked scenario cannot heat to bulk boiling at relieving pressure. A hotter utility requires a separate vaporization/two-phase assessment. The supplied saturation temperature must correspond to the same liquid and P1 used for sizing. The API 520 liquid screen also requires vapor pressure at the relieving temperature below total backpressure; that does not establish absence of internal nozzle cavitation.

All numerical inputs must be finite and positive; intermediate loads must remain representable. The tool rejects unsupported conditions instead of applying a liquid-only thermal method to boiling service. These synthetic properties are not a property database.

The very small calculated opening is an effective minimum, not a purchasable valve recommendation. Actual valve and line sizing, viscosity and backpressure corrections, inlet losses, certified capacity, accumulation allowance and other credible scenarios need review against the applicable standard and manufacturer data. The implementation demonstrates one API 521 load calculation feeding API 520, not compliance with an entire plant relief study.
