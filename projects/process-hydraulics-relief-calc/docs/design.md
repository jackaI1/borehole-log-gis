# Calculation model

This tool compares a pump with the pressure needed to move a liquid through a network, then calculates preliminary relief areas for a specified gas or liquid release. It uses explicit units and writes a reproducible calculation note.

## Choices

A general node-and-edge solver could cover arbitrary meshes but would hide more nonlinear convergence decisions. A single straight-pipe calculator would miss flow splitting. I chose a composable series/parallel network: each parallel stage shares inlet and outlet, each branch contains pipes in series, and multiple stages can be connected in series. This covers transfer lines, split process branches and common headers. It explicitly excludes arbitrary cross-connected meshes.

Pipe results separate Darcy friction, supplied fitting K losses and elevation. The fluid is steady, Newtonian, incompressible and single phase, with constant density and dynamic viscosity. Boundary pressures are at reservoirs with negligible velocity; terminal entrance/exit K losses must be supplied. Branch elevations must agree within each parallel stage. Laminar flow uses 64/Re; turbulent flow uses an iterated Colebrook equation. Transitional Reynolds numbers 2300 to 4000 are flagged, including within root searches; a numerical search can use a labeled interpolation to locate a trial point, but no reported solution may contain transitional pipe flow.

A strictly decreasing tabulated pump head curve uses linear interpolation only. A bracketed search finds its intersection with required system head, without extrapolation. The operating point must meet the supplied acceptable flow range; NPSH and efficiency are outside this model.

Gas relief uses the API 520 Part I critical-flow equation only, checks the absolute backpressure ratio, and requires explicit discharge, backpressure and combination correction factors. Liquid relief uses the nonflashing equation with explicit viscosity and backpressure correction factors, plus vapor pressure to screen flashing. This screening cannot establish absence of nozzle cavitation. API 521 thermal expansion is implemented for a blocked-in, fully liquid-filled heat exchanger: U A delta-T derives heat input, then beta H/(rho cp) derives the release rate fed to API 520 liquid sizing. The utility must remain below saturation temperature at relieving pressure. Other API 521 scenarios and loads remain supplied engineering inputs, recorded with their rationale. The package does not assert API certification or generate relief loads from fire scenarios.

Input numbers must be finite, with positive physical properties and valid ranges. Relative roughness above 0.05 and turbulent Re above 1e8 are outside this implementation. Reports preserve every input and warn about model limits. A JSON CLI accepts edited examples, returns exit code 2 on invalid inputs and emits Markdown notes only after all calculations succeed.

Tests will compare laminar flow to Hagen-Poiseuille, Colebrook values to independent roots, parallel mass/energy balance, pump interpolation/intersection, and relief areas to hand calculations and manufacturer examples. CI runs these checks and verifies the committed note can be regenerated.
