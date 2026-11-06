# Input guide

Start with [transfer.json](../examples/transfer.json). JSON does not allow comments; put explanations in `assumptions`, `scenario` and `factor_basis`.

## Case and piping

| Field | Meaning and limits |
| --- | --- |
| `title` | Nonempty calculation name |
| `assumptions` | Nonempty array of nonempty explanations |
| `fluid.density_kg_m3` | Constant liquid density, positive kg/m³ |
| `fluid.viscosity_pa_s` | Dynamic viscosity, positive Pa·s; 1 cP = 0.001 Pa·s |
| `flow_m3_s` | Requested network flow, nonnegative m³/s; 1 L/s = 0.001 m³/s |
| `network.stages` | Nonempty array of stages connected in series |
| `stages[].branches` | Nonempty array of branches connected in parallel |
| `branches[].pipes` | Nonempty array of pipes connected in series |
| `pipes[].name` | Nonempty name, unique throughout network |
| `length_m`, `diameter_m` | Positive pipe length and inside diameter in m |
| `roughness_m` | Nonnegative absolute wall roughness in m; roughness/diameter ≤ 0.05 |
| `fitting_k` | Nonnegative total dimensionless K at that pipe's velocity |
| `elevation_m` | Outlet elevation minus inlet elevation, m; may be negative |

Every branch in one parallel stage must have the same sum of elevation changes (within 1e-9 m). There are no withdrawals within a stage and no reverse branch flows. Required network pressure is the sum of stage pressure differences; parallel paths share pressure difference and must not be added together.

Boundary pressures are equal at large reservoirs with negligible velocity in the example. To model unequal boundary pressures, add their pressure difference to the external head requirement separately; this input format does not provide a boundary-pressure field. Include entrance, exit and reducer losses in K values with the correct reference velocity. Property changes, developing flow and compressible piping are outside scope. K values are treated as constant, including in laminar flow, which can be a poor approximation for real fittings at low Reynolds numbers.

Reynolds numbers in [2300, 4000) are rejected for final results. Search trials use a continuous interpolation to cross this interval, then recheck every final pipe without it. Re > 1e8 is rejected, even if encountered only in a pump/parallel search bracket: reduce the supplied bracket or use a model with a wider validated range. At zero flow, pressure consists of elevation only; reported f=0 is a no-flow sentinel.

## Pump

`pump` is optional and requires a network. `points` is an array of `[flow_m3_s, head_m]` pairs with at least two points. Flow is nonnegative and strictly increasing; head is nonnegative and strictly decreasing. The tool uses piecewise linear interpolation and searches only between the first and last flow. No intersection is an error.

`acceptable_flow_m3_s` is `[minimum, maximum]`, nonnegative and ordered. This supplied range does not alter the curve; the operating point is flagged if outside it. It does not establish an efficiency range, minimum continuous stable flow or cavitation margin without suitable manufacturer data.

## Relief

`gas_relief` and `liquid_relief` are optional. Each contains `scenario` (why relief is needed and how the required load was obtained), `factor_basis` (why the supplied coefficients apply), and `inputs` (the numbers below). Both text fields are mandatory. A case must include at least a network or one relief calculation, including the derived thermal case below. Relief-only cases need no hydraulic fields.

| Gas input | Unit or limit |
| --- | --- |
| `mass_flow_kg_h` | Positive required gas mass release, kg/h |
| `temperature_k` | Positive absolute relieving temperature, K; °C + 273.15 |
| `molecular_weight_kg_kmol` | Positive molar mass, kg/kmol |
| `k` | Isentropic exponent; tool scope 1 < k ≤ 1.67 |
| `compressibility` | Supplied Z at relieving conditions; tool scope 0.2 ≤ Z ≤ 2 |
| `inlet_kpa_abs` | Positive relieving pressure at valve inlet, kPa absolute |
| `backpressure_kpa_abs` | Positive total downstream pressure, kPa absolute |
| `kd`, `kb`, `kc` | Explicit discharge, gas backpressure and rupture-disk combination factors, each (0, 1] |

The absolute backpressure ratio must not exceed the calculated critical ratio. The k and Z bounds are conservative implementation limits, not universal ranges defined by API. The equations do not validate the underlying thermodynamic property model or suitability for a particular vapor.

| Liquid input | Unit or limit |
| --- | --- |
| `flow_l_min` | Positive required liquid release, L/min |
| `specific_gravity` | Positive density relative to water at the reference basis used for sizing |
| `inlet_kpa_abs`, `backpressure_kpa_abs` | Positive kPa absolute; inlet greater than backpressure |
| `vapor_pressure_kpa_abs` | Positive vapor pressure at relieving temperature; must be below backpressure |
| `kd`, `kw`, `kc`, `kv` | Explicit discharge, liquid backpressure, combination and viscosity factors, each (0, 1] |

`kv` must correspond to the chosen effective orifice and viscosity. If it is unknown, establish it using the applicable standard and manufacturer procedure; this tool does not silently assume 1. The vapor-pressure comparison rejects obvious flashing at discharge. It cannot establish absence of cavitation inside the valve.

Pressure conversion is deliberate: **P1_abs = set_pressure_gauge × (1 + overpressure_fraction) + atmospheric_pressure_abs** for a case where that overpressure allowance is applicable. P2 is total absolute backpressure. Do not add atmospheric pressure twice or automatically use a 10% allowance. The supplied allowance, set pressure and load must come from the actual contingency assessment.

Unknown or duplicate keys, booleans in numeric fields and NaN/Infinity are errors. Inputs must be finite; cases beyond floating-point representability are rejected. No default relief coefficients, unit guessing or automatic valve selection are provided.

## Derived thermal-expansion relief

The optional `thermal_relief` section contains `scenario`, `factor_basis`, `load_inputs` and `sizing_inputs`. It can run without any other calculation sections; see [thermal-expansion.json](../examples/thermal-expansion.json) and the [worked contingency](thermal-relief.md).

`load_inputs` requires positive, finite `overall_heat_transfer_w_m2_k`, `heat_transfer_area_m2`, `heat_source_temperature_k`, `liquid_temperature_k`, `saturation_temperature_at_relief_k`, `blocked_volume_m3`, `density_kg_m3`, `heat_capacity_j_kg_k`, `volumetric_expansion_per_k` and `reference_water_density_kg_m3`. The last two use 1/K and kg/m³. Saturation temperature must be supplied at the same relieving pressure as P1. Require liquid temperature < heat-source temperature < saturation temperature, otherwise the supported heating/nonboiling case does not apply.

`sizing_inputs` contains exactly the liquid pressure and correction fields: `inlet_kpa_abs`, `backpressure_kpa_abs`, `vapor_pressure_kpa_abs`, `kd`, `kw`, `kc`, `kv`. Flow and specific gravity are calculated by the thermal module and cannot be supplied or overridden here. The report shows heat input in W, heating rate in K/s, release in L/min and kg/h, and final area in mm².
