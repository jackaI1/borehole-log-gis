# process-hydraulics-relief-calc

I built a pipe-flow and relief-valve calculator to learn how the underlying idea works. This is a learning project.

The bundled calculations use illustrative pipe and relief-sizing inputs.

## Try it

With Python 3.10 or newer installed, clone this repository and run:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
hydraulics-calc examples/transfer.json --output calculation-note.md
```

Open `calculation-note.md` in a text editor or Markdown viewer. On Windows, activate the environment with `.venv\Scripts\activate` instead. The installed package has no runtime dependencies.

The example has a common inlet, two unequal process branches, and a common outlet eight metres higher. At 8 L/s it needs **94.351 kPa** of pressure. The illustrative pump would actually settle at **16.677 L/s and 14.646 m of head**, above the supplied acceptable range of 6 to 16 L/s. Head means pressure expressed as the height of liquid the pump can lift.

The same note contains two independent relief checks: **79.203 mm² for gas** and **233.220 mm² for viscous liquid**. These checks use supplied release rates. A third check derives **1.5 L/min (72 kg/h)** of thermal expansion from **40 kW** of heat input, then calculates **0.768897 mm²** of minimum relief area. These independent relief examples are separate from the water-transfer pump model.

## Change a calculation

Copy `examples/transfer.json`, edit its numbers and assumptions, and pass the copy to the same command. Each field names its unit: pipe lengths and inside diameters are in metres, flow is in cubic metres per second, and viscosity is in pascal-seconds. A litre per second is `0.001` m³/s. Relief pressures use **kPa absolute**, including atmospheric pressure, rather than pressure measured above the atmosphere.

Each network stage contains parallel branches, and each branch contains pipes in series. A single branch represents a common header. All branches in a stage must end at the same elevation. Each pipe's `fitting_k` is the supplied total loss coefficient for its fittings, calculated using that pipe's velocity. I used assumed K values in the example; actual fitting data needs to come from a suitable reference or supplier.

A relief-only file can omit the network, fluid, flow and pump sections. The [input guide](docs/inputs.md) explains every field. Missing fields, misspelled keys, nonfinite numbers, impossible pressures and unsupported regimes return an error with exit code 2. The tool calculates the complete note before replacing an output file.

## What the calculations do

I use Darcy-Weisbach for pipe pressure loss and iterate the Colebrook equation for turbulent friction. Those equations connect flow speed, pipe size and wall roughness to pressure loss. Slow laminar flow uses `64/Re`, where the Reynolds number, `Re`, distinguishes flow regimes. I reject transitional flow from 2300 up to 4000 rather than present a guessed final result. Parallel branch flows satisfy equal pressure changes and conservation of flow.

The pump check finds where the required system head meets a decreasing, tabulated pump curve. It interpolates between supplied points and refuses to extrapolate. The note shows both the requested flow and the calculated operating point, with pressure loss separated into wall friction, fittings and elevation.

For relief sizing, I implemented the published **API 520 Part I** metric equations for critical gas flow and nonflashing liquid flow. Critical gas flow means the valve throat has reached its limiting flow speed; the code checks the downstream-to-upstream pressure ratio. Liquid sizing accepts an explicit viscosity correction instead of borrowing one from the pipe calculation. [Equations and worked checks](docs/equations.md) show the substitutions, units and manufacturer references.

**API 521** deals with why overpressure happens and how much fluid must be released. I implemented its blocked-in-liquid thermal-expansion balance: heat input comes from the exchanger area, heat-transfer coefficient and temperature difference, and the resulting liquid expansion becomes the required relief load. The tool feeds that calculated rate directly into API 520 liquid sizing. [The worked contingency](docs/thermal-relief.md) explains the assumptions and the boiling screen; run it alone with `hydraulics-calc examples/thermal-expansion.json --output thermal-note.md`. I record supplied loads and their basis for the other examples. I do not claim that this tool completes a plant relief study or certifies a valve. It does not calculate fire loads, steam or two-phase relief, arbitrary meshed networks, pump suction requirements or nozzle cavitation. Final valve selection needs the current standard, manufacturer data and engineering review.

## Use from Python

```python
from process_hydraulics.hydraulics import Fluid, Pipe

water = Fluid(density_kg_m3=998, viscosity_pa_s=0.001)
pipe = Pipe(
    name="transfer", length_m=100, diameter_m=0.1, roughness_m=0.000045, fitting_k=2, elevation_m=5
)
result = pipe.evaluate(flow_m3_s=0.008, fluid=water)
print(f"Pressure required: {result.total_pa / 1000:.3f} kPa")
```

The package separates the hydraulic model, relief equations and JSON/report interface in `src/process_hydraulics/`. [Model choices](docs/design.md) explain the series/parallel scope and numerical searches.

## Tests and limits

There are 4 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: (removed workflow).

The relocated workflow did not complete successfully within the migration batch. Local test sources remain available.
