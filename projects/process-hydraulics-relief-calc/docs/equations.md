# Equations and worked checks

These are preliminary calculations of minimum effective discharge area. They are not certified capacities, valve selection or proof of compliance with every installation requirement.

## Pipe pressure

For each constant-diameter pipe:

```text
v = 4 Q / (π D²)                     [m/s]
Re = ρ v D / μ                       [dimensionless]
ΔPfriction = f (L/D) ρv²/2            [Pa]
ΔPfittings = ΣK ρv²/2                [Pa]
ΔPelevation = ρg Δz                  [Pa]
ΔPtotal = ΔPfriction + ΔPfittings + ΔPelevation
```

Q is m³/s, D and L are m, ρ is kg/m³, μ is Pa·s and g is 9.80665 m/s². Positive Δz is uphill. f is the **Darcy** friction factor; it is four times the Fanning factor. At Re < 2300, f=64/Re. At Re ≥ 4000:

```text
1/√f = -2 log10(ε/(3.7D) + 2.51/(Re√f))
```

The implementation iterates in 1/√f to a change below 1e-12, with a 100-iteration cap. Re ≤ 1e8 and ε/D ≤ 0.05 are implementation bounds. Reported transitional flow is rejected. The pipe-flow model follows the Darcy-Weisbach and Colebrook relations described in the [University of Manchester pipe and network calculation references](https://personalpages.manchester.ac.uk/staff/david.d.apsley/hydraulics/hydcalc.htm).

Two independent textbook-style checks in `tests/test_hydraulics.py`:

- Laminar flow: μ=0.001 Pa·s, L=10 m, D=0.01 m, Q=1e-6 m³/s. Hagen-Poiseuille gives ΔP=128 μLQ/(πD⁴)=**40.74366543 Pa**. Darcy-Weisbach with f=64/Re must give the same value.
- Turbulent flow: ρ=998 kg/m³, μ=0.001 Pa·s, D=0.1 m, L=100 m, v=2 m/s, ε=0.000045 m. Re=199600. An independently evaluated high-precision Colebrook root is f=**0.0185637607736078**, so ΔP=**37053.2665041 Pa** without fittings or elevation.

The series/parallel solver finds a common friction-plus-fitting pressure loss for each parallel stage. Each branch is inverted with a bracketed bisection; their flows must sum to the total. Common elevation pressure is added once per stage. The pump search solves Hsystem(Q)-Hpump(Q)=0, using the same bracketed approach. Bisection terminates at a bracket width of 1e-10 times its current upper value or one floating-point spacing at that value. Final parallel flow and loss residuals must agree within 1e-8 relative tolerance; failed checks raise an error. Searches may use transitional interpolation; every final pipe is recalculated strictly.

## Gas relief

The metric API 520 Part I critical-gas form is:

```text
A = W / (C Kd P1 Kb Kc) × √(T Z / M)
C = 0.03948 × √[k × (2/(k+1))^((k+1)/(k-1))]
critical ratio = (2/(k+1))^(k/(k-1))
require P2/P1 ≤ critical ratio
```

A is mm²; W is kg/h; T is K; M is kg/kmol; P1 and P2 are **kPa absolute**. Z, k and correction factors are dimensionless. The coefficient 0.03948 applies only to these units. The code uses logarithms for stable evaluation as k approaches 1.

For a worked gas check, I use the supplied properties in LESER's example 7.4.9.1: W=4200 kg/h, T=328.15 K, M=28.03 kg/kmol, k=1.19, Z=0.712 and Kd=0.975, Kb=Kc=1. Converting the stated gauge pressures with 101.325 kPa atmospheric pressure gives P1=55×100×1.10+101.325=6151.325 kPa absolute and P2=10×100+101.325=1101.325 kPa absolute.

```text
C = 0.02552706197
P2/P1 = 0.1790386624 < critical ratio 0.5664259586
A = 4200 / (0.02552706197 × 0.975 × 6151.325 × 1 × 1)
    × √(328.15 × 0.712 / 28.03)
  = 79.20266978 mm²
```

The handbook prints 0.122 in² (78.70952 mm²); the test allows 1% against that printed result and separately checks the independently calculated metric value tightly. Its displayed US-unit substitution evaluates to about 0.12263 in², so its final printed value is truncated. Metric coefficient and unit-conversion rounding also contribute a small difference. I retain the metric equation result rather than tune a coefficient to the printed area.

## Liquid relief

The nonflashing-liquid metric form is:

```text
A = 11.78 Q / (Kd Kw Kc Kv) × √[G/(P1-P2)]
```

A is mm²; Q is **L/min**; G is specific gravity relative to water; P1 and P2 are kPa absolute. Kd is discharge coefficient, Kw is liquid backpressure correction, Kc is the rupture-disk combination factor and Kv is the viscosity correction. None is inferred by the tool.

My worked liquid check uses LESER example 7.4.9.5: Q=5 L/s=300 L/min, G=1.26, P1=1201.325 kPa absolute, P2=101.325 kPa absolute, Kd=0.65, Kw=Kc=1. The uncorrected area, with Kv=1, is **184.0103 mm²**, agreeing with the printed preliminary 0.285 in². The published final iteration supplies Kv=0.789:

```text
A = 11.78 × 300 / (0.65 × 1 × 1 × 0.789) × √(1.26/1100)
  = 233.2196371 mm²
```

This agrees within 0.3% with the printed 0.362 in². The code does not perform the manufacturer's iterative orifice selection or claim that Kv=0.789 applies to other liquids. The example's 0.01 kPa absolute vapor pressure is an explicitly synthetic input for the discharge flashing screen.

## Sources and scope

- [LESER Engineering, chapter 7](https://www.leser.com/-/media/files/engineering/leser_engineering.pdf), section 7.4 on API sizing, gas example 7.4.9.1 (printed page 7.4-28; PDF page 188) and liquid example 7.4.9.5 (printed page 7.4-31; PDF page 191). This manufacturer handbook identifies API 520's 2020 edition as its basis. I reproduce the numerical checks, not the manufacturer's valve recommendation.
- [Emerson Pressure Relief Valve Engineering Handbook](https://www.documentation.emersonprocess.com/intradoc-cgi/groups/public/documents/catalog/mdaz/nzk1/~edisp/prv-handbook.pdf), chapter 6, metric gas and liquid sizing forms. This cross-checks the unit-specific constants.
- [API 520 Part I publication page](https://www.apiwebstore.org/standards/520__Part_1), for the standard's sizing and selection scope. The full standard and applicable errata are not bundled here.
- [API 521 overview](https://www.api.org/products-and-services/standards/important-standards-announcements/standard521), for overpressure scenarios, required relieving rates and disposal systems. The [thermal-expansion worked case](thermal-relief.md) derives one required load from heat-transfer inputs and feeds it into API 520. Other scenarios and supplied loads require separate assessment; this does not establish compliance with the whole standard.

Backpressure being below the critical ratio does not establish that Kb=1 applies to a particular valve. P2 greater than vapor pressure does not establish absence of internal cavitation. Use actual properties at relieving conditions, compatible effective-area coefficients and manufacturer correction factors. Review accumulation, inlet losses, outlet losses and disposal arrangements separately before selecting equipment.
