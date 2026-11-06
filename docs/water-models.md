# Ground and water checks

I added these checks because I wanted to learn how to connect the ground records in this project with water calculations I could inspect. The examples are synthetic. They are not records of a real site and are not suitable for design without measured inputs, calibration and professional review.

## Core runs

A core run is one drilled interval. Rock Quality Designation (RQD) is the total length of sound core pieces at least 10 cm long, divided by drilled length, expressed as a percentage. I use the logged natural fracture count divided by drilled length for fracture frequency. I need the logger to distinguish natural fractures from drilling breaks and decide which pieces are sound; I cannot infer either from lengths alone.

```sh
uv sync --extra dev --extra water
uv run borehole-gis samples/bgs_bh01.ags --format ags --crs EPSG:27700 \
  --output-crs EPSG:27700 --core-runs samples/core_runs.json --out build/core
```

The sample core runs are invented observations joined to the public BH01 log by ID and overlapping depth. They are not BGS core measurements. `core_runs.json` declares metre units and gives each run's `hole_id`, `top_m`, `base_m`, `pieces_m` and `fractures`. The first run has a 1 m drilled length and pieces of 0.10, 0.30 and 0.05 m: 40% RQD, 45% recovery and 4 fractures/m. Empty recovery gives 0% RQD. The sample also deliberately includes overlapping runs and 110% recovery.

I preserve observed arithmetic, even if recovery exceeds the drilled length, and flag it for review instead of capping it to 100%. I withhold the quality band when recovery is implausible. Other flags cover invalid depths, pieces or counts, unknown holes and depths beyond the borehole. Quality bands are very poor below 25%, poor from 25 to below 50%, fair from 50 to below 75%, good from 75 to below 90%, and excellent from 90 to 100%. These follow the [USACE rock foundation manual, Table 2-1](https://www.publications.usace.army.mil/Portals/76/Publications/EngineerManuals/EM_1110-1-2908.pdf).

`core_runs.json` in the output preserves one assessed record per run. `core_runs.csv` has one row per run/layer intersection, including borehole coordinates, CRS, total depth and intersected layer thickness. Runs with no matching layer remain visible. Do not sum repeated run metrics across the layer rows. Core review flags do not stop the original log export; malformed core file input does return exit code 2.

## Pumping and recovery

A pumping test measures how far water levels fall while a nearby well pumps at a constant rate. Transmissivity, T, describes how easily the aquifer transmits water; storativity, S, describes the water released for a change in water level. I fit observations at a known distance from the pumping well.

```sh
uv run site-water pumping --csv samples/pumping/drawdown.csv \
  --metadata samples/pumping/pumping.json --out build/pumping
uv run site-water pumping --csv samples/pumping/recovery.csv \
  --metadata samples/pumping/recovery.json --out build/recovery
```

I open `report.json` for estimates and warnings, `diagnostic.png` for drawdown against log time and residuals, and `observations.csv` for every original, corrected and fitted value. Each output folder must be new or empty. The command returns 0 when an analysis is written, even if the report flags a poor fit. An input or solver failure returns 2.

The CSV requires `timestamp` and `drawdown`, with positive drawdown meaning a water-level decline. Every timestamp, including the metadata start and stop, needs a UTC offset. Duplicate, out-of-order and pre-start observations are rejected. Metadata declares `rate`, `rate_unit`, `radius`, `radius_unit`, `drawdown_unit` and `start`. Supported lengths are m/ft; rates are m3/s, L/s, L/min and m3/day. All internal calculations use metres and seconds.

If the CSV has `barometric_pressure`, metadata must declare `pressure_unit` (Pa, kPa or hPa), `reference_pressure` and `barometric_efficiency` between 0 and 1. I subtract `BE * (pressure - reference) / (1000 * 9.80665)` from observed drawdown. This assumes the supplied observations still contain the aquifer's pressure response. It is not a second atmospheric compensation for an absolute-pressure logger. BE must come from an independent pre-test calibration; I do not estimate it from the pumping curve or silently interpolate pressure readings.

Theis uses `s = Q E1(r² S / (4 T t)) / (4 pi T)`, where E1 is the exponential integral. I solve for log(T), log(S) with bounded least squares, then propagate the covariance into approximate 95% confidence intervals. The model assumes a homogeneous confined aquifer, a fully penetrating well, constant rate and no nearby boundaries. The intervals assume independent drawdown errors; they do not include model bias or uncertainty in rate, radius or barometric calibration.

Cooper-Jacob approximates the late part of the Theis curve as a line against log time. I select observations with Theis-estimated `u <= 0.01` and any supplied `late_time_s` cutoff, then recheck u using the fitted line. I flag fewer than five late points, nonpositive slopes, poor fits (R² below 0.98), parameter bounds and ill-conditioned fits. For recovery, metadata supplies `stop`, and the CSV must contain only post-stop readings. I fit residual drawdown as the difference between continued pumping and an equal negative pumping rate starting at shutoff. Late recovery alone may not identify S; unavailable confidence intervals are explicit. I use analytic parameter sensitivities to avoid falsely narrow intervals caused by subtracting nearly equal late-recovery responses.

The 70-point examples add small noise and pressure variation to T=0.001 m²/s and S=0.0002. Regenerate them with `uv run python scripts/make_pumping_example.py`. Source metadata is committed beside the CSV files.

For an external arithmetic check, I use the [Groundwater Project section 8.3 worked Cooper-Jacob example](https://books.gw-project.org/an-introduction-to-hydraulic-testing-in-hydrogeology/chapter/computing-t-and-s-from-hydraulic-test-data-using-the-theis-method/): 2610 L/min, a 600 m observation radius, and line endpoints of 1.32 m at 10 minutes and 4.85 m at 100 minutes. The calculated T agrees with the printed 194.9 m²/day within 0.3%. The endpoints imply S=3.573e-6, while the book separately quotes an intercept of 2.8 minutes and S near 2e-6. Those values are inconsistent, so my test records the discrepancy instead of changing the data. The two printed points do not provide a confidence interval or enough late points for a field interpretation. Recovery equations are also documented in [USGS Open-File Report 02-197](https://pubs.usgs.gov/of/2002/ofr02197/documentation.pdf).

## Water distribution

I use EPANET, the free pipe-network solver, through WNTR, its Python interface, to check a small pressure zone. It contains a reservoir, fixed-speed pump, four junctions and a loop of pipes. The model includes hourly water-use changes over 24 hours.

```sh
uv run site-water water-demo --inp build/water/zone.inp
uv run site-water water --inp build/water/zone.inp --out build/water/results
```

The second command reloads the actual EPANET input file and uses 15-minute hydraulic and report steps. I can replace it with my own 24-hour Hazen-Williams model with one-hour demand patterns. `--hydrants A B C` selects fire-demand nodes; otherwise I use junctions with a positive base demand. `--fire-flow-l-s 15` sets the extra two-hour demand at each hydrant, one hydrant per scenario, between hours 6 and 8. All junctions remain checked, so the lowest pressure can be somewhere other than the burning location.

`nodes.csv` lists pressure extremes; `pipes.csv` lists maximum speed and friction loss per kilometre with criterion violations; `pumps.csv` checks each operating point against the supplied pump curve and flow range. `fire_flow.csv` identifies the lowest residual pressure and its location. `report.json`, engine reports, binary results and pressure time series remain available for inspection.

The default screening criteria are 20 to 80 m pressure head, pipe speed up to 2 m/s, pipe head loss up to 10 m/km, at least 14 m residual fire pressure, pump flow between 5 and 35 L/s and a 0.1 m pump-curve tolerance. These are stated example thresholds, not a municipal design standard. `--criteria criteria.json` accepts fields from the `Criteria` dataclass to replace thresholds. This synthetic network intentionally fails pressure checks. Demand-driven analysis imposes the requested flow; a negative fire pressure means that flow cannot be physically supplied. I report it as a failure rather than claim the pump delivers it. There is no water-quality or surge analysis.

Tests compare EPANET with independent SI Hazen-Williams friction loss for one pipe and a parallel loop, where I separately solve the flow split and equal head loss. The pump test checks head gain against the fitted head-flow curve. [EPA's WNTR hydraulic documentation](https://usepa.github.io/WNTR/hydraulics.html) explains the solver and demand-model choices. WNTR 1.4 still imports `pkg_resources` and `six`, so the extra includes six and pins setuptools below 81.

## Sewer and surface drainage

The [SWMM runner](../projects/swmm-flood-batch-runner/) reads GeoPandas map layers and a DEM, an elevation grid, to create linked sewer pipes and downhill surface channels. It runs the real EPA dynamic-wave solver for three illustrative storms. The reports distinguish surface water travelling through the model from flooding lost outside it and check both mass balance and solver convergence.

After exporting boreholes and running the storm batch, I can make a nearby-results review table:

```sh
cd projects/swmm-flood-batch-runner
uv run swmm-batch boreholes --boreholes ../../build/bc/boreholes.gpkg \
  --results outputs/demo/results/results.gpkg --output outputs/borehole-flood-review.csv \
  --return-period 100 --distance 100
```

I use inputs that actually cover the same site and keep the original CRS declarations. The command transforms boreholes to the drainage model's metre grid, keeps every nearby surface node, and keeps holes with no nearby result. The supplied public boreholes and synthetic drainage catchment are in different locations, so they correctly produce no nearby match. Distance is for organizing review; it does not predict groundwater infiltration, borehole inundation or ground stability. A nearest node is not a flood-extent polygon.

## River profiles and a crossing

HEC-RAS calculates water-surface elevations along a river. I generate an entirely synthetic 600 m channel, three illustrative return-period flows (5, 15 and 35 m³/s), and a road crossing with a 5 m by 2 m, 30 m long concrete box culvert. The geometry includes 2 m banks and sloping floodplains. I also generate the same channel without the crossing as a control.

Model generation, extraction and independent calculations are ordinary Python and run on this Mac without opening an app. The actual HEC-RAS solve is delegated to a disposable Windows GitHub Actions runner with HEC-RAS 6.6 installed silently from USACE. I never install or open it on this Mac. With an existing HEC-RAS 6.6 installation on Windows:

```sh
uv sync --extra dev --extra water
uv run python scripts/run_river.py --out build/river
```

`channel.prj`, `.g01`, `.f01` and `.p01` preserve the generated project, geometry, steady discharges and boundary conditions. The controller computes the current plan and is closed in `finally`. I extract named profiles and station identities from the engine's HDF result file and reject missing, duplicate or invalid results. `profiles.csv` and `comparison.csv` retain every water level, bank-overtopping flag and comparison difference.

My independent calculations use Manning's equation for the downstream normal-depth boundary and the standard-step energy equation between ordinary cross-sections, including subsection conveyance and velocity-head correction. The pair spanning the culvert is excluded from the hand channel comparison because its entrance, barrel, outlet and road-overflow losses require the structure solver. I still extract and flag the actual upstream and downstream culvert profiles. The no-crossing control checks all pairs; the crossing model checks the remaining pairs against a 0.06 m tolerance. A bank-overtopping flag means the water is above the 2 m bank, not a mapped flood extent. This is steady 1D screening, not unsteady routing or a calibrated flood study.

The published [USACE Linux notes](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS_66_Linux_Build_Release_Notes.pdf) explain that Linux compute inputs ordinarily originate in a Windows preprocessing run. I use the Windows CI controller to generate and validate the complete model directly. The small generator writes the documented HEC-RAS text record format; it does not substitute a hand calculator for the real engine.

The [saved result tables](examples/river-comparisons.csv) and [run provenance](examples/river-report.json) come from an actual HEC-RAS 6.6 CI run. All 39 ordinary-channel comparisons differ from the independent calculation by less than 0.00052 m. The crossing raises the water at station 300 by 0.77, 1.67 and 1.48 m for the three flows. Eleven section/profile combinations overtop the banks in the culvert model, compared with seven in the control.

## Verification

```sh
uv run pytest -q
uv run ruff check .
uv build
cd projects/swmm-flood-batch-runner
uv run pytest -q
```

The 108 root tests cover the original borehole exports, core intervals, synthetic pumping and recovery parameter fits, unit/time errors, barometric correction, a published straight-line example, actual EPANET solves, HDF extraction and hand river calculations. GitHub Actions runs it on Python 3.11 through 3.13, renders the existing QGIS examples on Ubuntu and publishes pumping, pressure-zone and HEC-RAS outputs. The 47-test SWMM suite runs the actual engine, including mass balance, adverse terrain and a smaller time-step comparison. Model outputs with warnings stay visible; green CI means the checks behaved as expected, not that every example passes design criteria.
