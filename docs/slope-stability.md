# Slope stability check: details

This note covers the inputs, method, outputs and validation for `site-slope`. The short version is in the [README](../README.md).

## Inputs

1. **Borehole log**: AGS4 or BC CSV, read and validated by the same code as `borehole-gis`. The log is not accepted if validation fails.
2. **Strength table** (`strengths.csv`): one row per soil description. `pattern` is matched as a whole word, case-insensitively, inside the logged description. The longest matching pattern wins. If two patterns of the same length match with different values, the layer is flagged as ambiguous.

   | column | unit |
   |---|---|
   | `pattern` | text |
   | `unit_weight_kn_m3` | kN/m³, total unit weight |
   | `cohesion_kpa` | kPa, effective cohesion c′ |
   | `friction_deg` | degrees, effective friction angle φ′ |

   Leave a value blank if you do not have it. Blank values stay blank. The tool never fills them in.
3. **Section** (`section.json`): the borehole name and its ground elevation, the ground surface as `[x, z]` points from crest to toe, an optional water table as `[x, z]` points, the lowest depth the slip surface may reach, and the grid of circle centres and radii to search.

The sample in `samples/slope/` is illustrative. Its geometry, datum and strength values are invented for the example and are not measured at the BGS site.

## Method

- **Slip surfaces**: circles. For each centre and radius in the search grid, the code finds where the circle leaves the ground surface (entry and exit points). The part of the circle above the ground is ignored.
- **Slices**: the mass above the circle is cut into 30 vertical slices by default. For each slice the code finds the layer at the slip base, and the weight from every layer it crosses.
- **Factor of safety (FOS)**: Bishop's simplified method, solved by iteration:

  FS = Σ [c′b + (W − ub) tan φ′] / m_α ÷ Σ W sin α, where m_α = cos α + sin α tan φ′ / FS

  W is slice weight, b slice width, α base angle, u pore pressure at the base, c′ and φ′ strength at the base.
- **Water**: pore pressure is γw × (water level − slip base) for each slice, where the water level is above the base. Slice weight uses total unit weight. This is a total-weight approach with pore pressure, not a full effective-stress model with buoyancy.
- **Critical surface**: the lowest FOS among surfaces that are complete (every crossed layer has strength values, and the arc stays inside the logged depth).

## Outputs

`site-slope` writes a new folder with:

- `report.json`: status, FOS, the critical circle, how many surfaces were tried and how many were excluded, and any warnings.
- `surfaces.csv`: every circle tried, its status and FOS.
- `critical_slices.csv`: the slices of the critical circle, with weight, base angle and pore pressure.
- `layers.csv`: each logged layer, its elevations and the strength values matched to it.
- `section.png`: the cross-section with the critical circle, water table and layers coloured by strength row. Layers with missing strength are grey and hatched.

Status values:

- `complete`: every surface was evaluated, and the critical FOS is shown.
- `partial`: some surfaces were excluded because they cross layers without strength values. The FOS is shown only for the surfaces that were evaluated, and the report lists the missing layers.
- `no_complete_surface`: no surface could be evaluated. No FOS is reported.

Exit code `0` means the run completed. `2` means input, validation or output failed.

## Validation

Checks are in `tests/test_slope.py`:

- **Infinite slope (closed form)**: identical slices on a plane dipping at β reproduce Skempton's infinite-slope result, FS = c′/(γz sin β cos β) + tan φ′ / tan β. The Bishop routine matches this to 1e-6.
- **Taylor chart (φ = 0)**: for a 45° (1V:1H) undrained clay cut, Taylor's (1937) chart gives a stability number Ns = c/(γH) of about 0.181. The grid search returns Ns = 0.181 within 0.5%. A wider grid gives the same value, so the critical circle is not cut off by the grid edge.
- **φ = 0 identity**: with φ = 0 the method reduces to FS = c Σ(b / cos α) / Σ(W sin α), which is moment equilibrium for a circle.
- **Monotonic behaviour**: doubling cohesion doubles the FOS when φ = 0. A water table lowers the FOS when φ > 0. Pore pressure lowers the FOS.
- **Slice convergence**: 30 and 120 slices agree within 1%.
- **Missing values**: a layer without strength is reported as `missing_strength` and is never assigned a guess.
- **Recorded sample run**: the illustrative sample gives FOS 1.4948 (complete run). The test checks that value to 1e-3, so a change in the algorithm shows up.

## Limits

- Circular slip surfaces only. Non-circular surfaces (for example, along a weak layer) need a method such as Spencer or Morgenstern-Price, which this tool does not implement.
- Bishop's simplified method does not satisfy all force and moment equilibrium conditions. It is standard for circles, but it is not a full equilibrium solution.
- Strength is one set of effective parameters per layer. There is no seismic loading, no anisotropy, no reinforcement, and no consolidation or staged construction.
- The search is a grid, so it finds the lowest surface on that grid. A finer grid may find a lower FOS. Widen the grid until the critical result stops changing.
- Layer boundaries are taken from the borehole and assumed horizontal across the section. In the real world a single borehole cannot show the variation across a slope.
- The result is an educational and screening check. It is not a design calculation and must not be used for a real slope without a qualified geotechnical engineer's review.

## Running the tests

```sh
uv run pytest -q tests/test_slope.py
```
