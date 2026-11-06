"""Strict JSON input and reproducible Markdown calculation notes."""

import argparse
import inspect
import json
import sys
from dataclasses import fields
from pathlib import Path

from .hydraulics import Branch, Fluid, Network, ParallelStage, Pipe, PumpCurve, operating_point
from .relief import size_gas, size_liquid
from .scenarios import LIQUID_FACTOR_FIELDS, thermal_expansion_relief
from .validation import number, text


def _object(value, label, required, optional=()):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(optional)
    if missing or unknown:
        raise ValueError(f"{label}: missing {sorted(missing)}, unknown {sorted(unknown)}")
    return value


def _array(value, label):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty array")
    return value


def _dataclass(cls, value):
    return cls(**_object(value, cls.__name__, [f.name for f in fields(cls)]))


def _network(data):
    data = _object(data, "network", ["stages"])
    stages = []
    for stage in _array(data["stages"], "stages"):
        stage = _object(stage, "stage", ["branches"])
        branches = []
        for branch in _array(stage["branches"], "branches"):
            branch = _object(branch, "branch", ["pipes"])
            branches.append(
                Branch(tuple(_dataclass(Pipe, p) for p in _array(branch["pipes"], "pipes")))
            )
        stages.append(ParallelStage(tuple(branches)))
    return Network(tuple(stages))


def _hydraulic_table(result):
    lines = [
        f"Flow: **{result.flow_m3_s:.6g} m³/s**. Required pressure: "
        f"**{result.total_pa:.6g} Pa**. Required head: **{result.head_m:.6g} m**.",
        "",
        "Parallel branch pressures are shared. Only the stage pressures add in series; "
        "adding all pipe rows would double-count parallel paths.",
        "",
        "| Stage | Shared pressure change (Pa) |",
        "| --- | ---: |",
    ]
    lines += [f"| {i} | {dp:.6g} |" for i, dp in enumerate(result.stage_pressure_pa, 1)]
    lines += [
        "",
        "| Pipe | Flow (m³/s) | Speed (m/s) | Re | Darcy f | Friction (Pa) | "
        "Fittings (Pa) | Elevation (Pa) | Total (Pa) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for p in result.pipes:
        name = p.name.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {name} | {p.flow_m3_s:.6g} | {p.velocity_m_s:.6g} | {p.reynolds:.6g} "
            f"| {p.friction_factor:.6g} | {p.friction_pa:.6g} | {p.fittings_pa:.6g} "
            f"| {p.elevation_pa:.6g} | {p.total_pa:.6g} |"
        )
    return lines


def calculate_note(case):
    """Validate and calculate a complete note before writing any output."""
    _object(
        case,
        "case",
        ["title", "assumptions"],
        ["fluid", "network", "flow_m3_s", "pump", "gas_relief", "liquid_relief", "thermal_relief"],
    )
    text("title", case["title"])
    for assumption in _array(case["assumptions"], "assumptions"):
        text("assumption", assumption)
    if not any(k in case for k in ["network", "gas_relief", "liquid_relief", "thermal_relief"]):
        raise ValueError("case requires a network or relief calculation")
    if "network" not in case and any(k in case for k in ["fluid", "flow_m3_s", "pump"]):
        raise ValueError("fluid, flow and pump require a network")
    lines = [
        f"# Calculation note: {case['title']}",
        "",
        "Preliminary study calculation. This is not a certified valve selection or "
        "an approval to operate equipment.",
        "",
        "## Supplied assumptions",
        "",
    ]
    lines += [f"- {a}" for a in case["assumptions"]]
    if "thermal_relief" in case:
        item = _object(
            case["thermal_relief"],
            "thermal_relief",
            ["scenario", "factor_basis", "load_inputs", "sizing_inputs"],
        )
        text("thermal scenario", item["scenario"])
        text("thermal factor_basis", item["factor_basis"])
        required = set(inspect.signature(thermal_expansion_relief).parameters) - {"sizing_inputs"}
        load_inputs = _object(item["load_inputs"], "thermal load_inputs", required)
        sizing_inputs = _object(
            item["sizing_inputs"], "thermal sizing_inputs", LIQUID_FACTOR_FIELDS
        )
        thermal = thermal_expansion_relief(**load_inputs, sizing_inputs=sizing_inputs)
        lines += [
            "",
            "## API 521 blocked-in-liquid thermal expansion",
            "",
            item["scenario"],
            "",
            "Factor and contingency basis: " + item["factor_basis"],
            "",
            "Rigid fully liquid-filled exchanger, liquid isolation valves closed, "
            "heat source still active. No incoming flow, reaction, heat-loss credit or "
            "vessel-expansion credit. The supplied heat-source temperature is below "
            "saturation temperature at relieving inlet pressure; boiling screen passes.",
            "",
            "Heat balance: H = U A (Tsource - Tliquid); dT/dt = H/(ρ V cp). "
            "API 521 thermal-expansion balance: Q = β V dT/dt = β H/(ρ cp). "
            "This derives the required liquid load before API 520 sizing.",
            "",
            f"Derived heat input: **{thermal.heat_input_w:.6g} W**. "
            f"Heating rate: **{thermal.heating_rate_k_s:.6g} K/s**.",
            "",
            f"Derived relief load: **{thermal.flow_l_min:.6g} L/min**, "
            f"**{thermal.mass_flow_kg_h:.6g} kg/h** "
            f"({thermal.flow_m3_s:.6g} m³/s). "
            f"Derived specific gravity: **{thermal.specific_gravity:.6g}**.",
            "",
            "API 520 Part I: A = 11.78 Q sqrt(G/(P1-P2))/(Kd Kw Kc Kv). "
            "Q and G come directly from the thermal calculation and cannot be overridden.",
            "",
            f"Minimum effective area: **{thermal.sizing.area_mm2:.6g} mm²**; "
            f"pressure difference: **{thermal.sizing.differential_kpa:.6g} kPa**. "
            "The liquid flashing screen also passes; nozzle cavitation still requires review.",
            "",
            "This evaluates one thermal-expansion contingency. It does not establish "
            "that thermal expansion governs over fire, tube rupture or other credible cases. "
            "A very small calculated area is not a recommendation to buy a valve that small.",
        ]
    lines += [
        "",
        "## Model and units",
        "",
        "Steady single-phase Newtonian liquid hydraulics: "
        "ΔP = (f L/D + ΣK) ρv²/2 + ρgΔz, g = 9.80665 m/s². "
        "Darcy f = 64/Re below 2300; Colebrook above or at 4000. "
        "Re in [2300, 4000) is rejected in reported results. "
        "Root searches may cross a linear transitional interpolation; "
        "every final pipe result is checked strictly.",
        "",
        "Hydraulic inputs: m, m³/s, kg/m³, Pa·s and dimensionless K. "
        "Reservoir boundary velocities are negligible. Terminal entrance and exit "
        "losses must be included in supplied K. Positive elevation consumes pressure. "
        "Relative roughness > 0.05 and Re > 1e8 are unsupported.",
        "",
        "Relief inputs: kg/h, K, kg/kmol, L/min, dimensionless factors and kPa absolute. "
        "Areas are minimum effective areas in mm². Gas scope: critical flow, "
        "1 < k ≤ 1.67 and 0.2 ≤ Z ≤ 2. Liquid scope: supplied viscosity correction "
        "and nonflashing service. Factors must be in (0, 1].",
    ]
    if "network" in case:
        for required in ["fluid", "flow_m3_s"]:
            if required not in case:
                raise ValueError(f"network requires {required}")
        fluid = _dataclass(Fluid, case["fluid"])
        network = _network(case["network"])
        number("flow_m3_s", case["flow_m3_s"], minimum=0)
        result = network.evaluate(case["flow_m3_s"], fluid)
        lines += ["", "## Network at requested flow", "", *_hydraulic_table(result)]
        if "pump" in case:
            pump = _object(case["pump"], "pump", ["points", "acceptable_flow_m3_s"])
            points = _array(pump["points"], "pump points")
            for point in points:
                if not isinstance(point, list) or len(point) != 2:
                    raise ValueError("pump points must be [flow_m3_s, head_m] pairs")
            acceptable = _array(pump["acceptable_flow_m3_s"], "acceptable_flow_m3_s")
            curve = PumpCurve(tuple(tuple(p) for p in points))
            op = operating_point(network, fluid, curve, tuple(acceptable))
            status = (
                "Within supplied acceptable flow range"
                if op.within_acceptable_flow
                else "FLAG: OUTSIDE supplied acceptable flow range"
            )
            lines += [
                "",
                "## Pump operating point",
                "",
                f"**{status}.**",
                "",
                f"Pump head: **{op.pump_head_m:.6g} m**. "
                "Curve points are linearly interpolated without extrapolation.",
                "",
                *_hydraulic_table(op.system),
            ]
    for key, function in [("gas_relief", size_gas), ("liquid_relief", size_liquid)]:
        if key not in case:
            continue
        item = _object(case[key], key, ["scenario", "factor_basis", "inputs"])
        text(f"{key} scenario", item["scenario"])
        text(f"{key} factor_basis", item["factor_basis"])
        inputs = _object(item["inputs"], f"{key} inputs", inspect.signature(function).parameters)
        r = function(**inputs)
        lines += [
            "",
            "## " + ("Gas relief" if key == "gas_relief" else "Liquid relief"),
            "",
            item["scenario"],
            "",
            "Factor basis: " + item["factor_basis"],
            "",
            f"Minimum effective area: **{r.area_mm2:.6g} mm²**.",
        ]
        if key == "gas_relief":
            lines += [
                "",
                "API 520 Part I critical gas equation: "
                "A = W sqrt(T Z/M)/(C Kd P1 Kb Kc). "
                "C = 0.03948 sqrt(k (2/(k+1))^((k+1)/(k-1))).",
                "",
                f"Metric C: {r.c_metric:.8g}; absolute P2/P1: {r.backpressure_ratio:.8g}; "
                f"critical ratio: {r.critical_pressure_ratio:.8g}. Critical-flow check passes.",
            ]
        else:
            lines += [
                "",
                "API 520 Part I liquid equation: A = 11.78 Q sqrt(G/(P1-P2))/(Kd Kw Kc Kv).",
                "",
                f"Pressure difference: {r.differential_kpa:.6g} kPa. "
                "P2 > vapor pressure screen passes; this does not rule out nozzle "
                "cavitation. Kv is supplied and must be verified for the selected orifice.",
            ]
    lines += [
        "",
        "## Limits and required review",
        "",
        "API 521 thermal-expansion loads are calculated only for the supported blocked-in "
        "liquid heat-exchanger case. Other scenario selection and loads remain supplied inputs. "
        "This tool does not determine fire loads, accumulation allowances, inlet-line "
        "loss limits, disposal-system backpressure or certified capacity. "
        "Final valve selection requires manufacturer data and an engineering review. "
        "It does not cover steam, two-phase relief, noncritical gas flow, arbitrary "
        "meshed pipe networks, NPSH, pump efficiency or cavitation assessment.",
        "",
        "Equation sources and worked checks: "
        "[equations.md](https://github.com/jackaI1/process-hydraulics-relief-calc/blob/main/docs/equations.md).",
        "",
        "## Complete input record",
        "",
        "```json",
        json.dumps(case, indent=2, ensure_ascii=False, allow_nan=False),
        "```",
        "",
    ]
    return "\n".join(lines)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Calculate liquid pipe losses and API 520 relief areas"
    )
    parser.add_argument("input", type=Path, help="JSON case, using explicit unit suffixes")
    parser.add_argument(
        "--output", type=Path, help="write Markdown note; default is standard output"
    )
    args = parser.parse_args(argv)
    try:
        if args.output and args.input.resolve() == args.output.resolve():
            raise ValueError("input and output must be different files")
        case = json.loads(
            args.input.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
        note = calculate_note(case)
        if args.output:
            args.output.write_text(note, encoding="utf-8")
        else:
            sys.stdout.write(note)
    except (OSError, ValueError, TypeError, OverflowError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
