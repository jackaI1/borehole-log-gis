import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "process_hydraulics", *map(str, args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=os.environ | {"PYTHONPATH": str(ROOT / "src")},
        timeout=30,
    )


def load_case():
    return json.loads((ROOT / "examples/transfer.json").read_text())


def test_full_working_cli_generates_auditable_note(tmp_path):
    output = tmp_path / "note.md"
    result = run_cli("examples/transfer.json", "--output", output)
    assert result.returncode == 0, result.stderr
    note = output.read_text()
    assert "79.2027" in note
    assert "233.22" in note
    assert "process A" in note and "process B" in note
    assert "OUTSIDE supplied acceptable flow range" in note
    assert "Colebrook" in note
    assert "No rupture disk" in note
    raw = note.split("```json\n")[1].split("\n```")[0]
    assert json.loads(raw) == load_case()


def test_note_is_reproducible():
    result = run_cli("examples/transfer.json")
    assert result.returncode == 0, result.stderr
    assert result.stdout == (ROOT / "docs/calculation-note.md").read_text()


def test_edited_input_changes_real_result(tmp_path):
    case = load_case()
    case["gas_relief"]["inputs"]["mass_flow_kg_h"] *= 2
    input_file = tmp_path / "custom.json"
    input_file.write_text(json.dumps(case))
    result = run_cli(input_file)
    assert result.returncode == 0, result.stderr
    assert "158.405" in result.stdout


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c.update(flow_m3_s=-1),
        lambda c: c["fluid"].update(viscosity_pa_s=True),
        lambda c: c["network"]["stages"][1]["branches"][0]["pipes"][0].update(elevation_m=99),
        lambda c: c["gas_relief"]["inputs"].update(backpressure_kpa_abs=6000),
        lambda c: c["liquid_relief"]["inputs"].update(vapor_pressure_kpa_abs=200),
        lambda c: c["gas_relief"].pop("factor_basis"),
        lambda c: c["fluid"].update(density_kg_m3_typo=998),
        lambda c: c.update(units="imperial"),
        lambda c: c.update(assumptions=[]),
        lambda c: c["pump"].update(points="bad"),
    ],
)
def test_invalid_cases_fail_without_replacing_note(tmp_path, mutation):
    case = load_case()
    mutation(case)
    input_file = tmp_path / "bad.json"
    input_file.write_text(json.dumps(case))
    output = tmp_path / "note.md"
    output.write_text("previous calculation")
    result = run_cli(input_file, "--output", output)
    assert result.returncode == 2
    assert "error:" in result.stderr
    assert not result.stdout
    assert output.read_text() == "previous calculation"


@pytest.mark.parametrize("raw", ['{"title":"a","title":"b"}', '{"title":NaN}', "[]", "{oops"])
def test_malformed_and_ambiguous_json_is_rejected(tmp_path, raw):
    input_file = tmp_path / "bad.json"
    input_file.write_text(raw)
    assert run_cli(input_file).returncode == 2


def test_missing_file_and_same_input_output_path(tmp_path):
    assert run_cli(tmp_path / "missing.json").returncode == 2
    p = tmp_path / "input.json"
    original = json.dumps(load_case())
    p.write_text(original)
    assert run_cli(p, "--output", p).returncode == 2
    assert p.read_text() == original


def test_relief_only_case_works(tmp_path):
    c = load_case()
    for key in ["fluid", "network", "flow_m3_s", "pump", "liquid_relief", "thermal_relief"]:
        c.pop(key)
    p = tmp_path / "gas.json"
    p.write_text(json.dumps(c))
    result = run_cli(p)
    assert result.returncode == 0, result.stderr
    assert "79.2027" in result.stdout


def test_extreme_geometry_never_writes_infinite_note(tmp_path):
    case = load_case()
    case["network"]["stages"][0]["branches"][0]["pipes"][0]["length_m"] = 1e308
    input_file = tmp_path / "overflow.json"
    input_file.write_text(json.dumps(case))
    output = tmp_path / "note.md"
    result = run_cli(input_file, "--output", output)
    assert result.returncode == 2
    assert not output.exists()


def thermal_case():
    from test_scenarios import CASE, SIZING

    return {
        "title": "Blocked-in liquid heat exchanger",
        "assumptions": [
            "Synthetic fully liquid-filled rigid exchanger with both liquid isolation valves shut, warm utility still flowing, and no other inlet or outlet."
        ],
        "thermal_relief": {
            "scenario": "Blocked-in cold side heated by a warmer utility; liquid expands and must be relieved.",
            "factor_basis": "Synthetic constant properties at relief, explicit liquid coefficients, no credited heat loss or vessel expansion.",
            "load_inputs": CASE.copy(),
            "sizing_inputs": SIZING.copy(),
        },
    }


def test_thermal_contingency_load_flows_into_sizing_and_note(tmp_path):
    p = tmp_path / "thermal.json"
    p.write_text(json.dumps(thermal_case()))
    r = run_cli(p)
    assert r.returncode == 0, r.stderr
    assert "40000 W" in r.stdout and "1.5 L/min" in r.stdout
    assert "72 kg/h" in r.stdout and "0.768897 mm²" in r.stdout
    assert "API 521" in r.stdout and "API 520" in r.stdout
    case = thermal_case()
    case["thermal_relief"]["load_inputs"]["heat_transfer_area_m2"] *= 2
    p.write_text(json.dumps(case))
    r = run_cli(p)
    assert r.returncode == 0, r.stderr
    assert "3 L/min" in r.stdout and "1.53779 mm²" in r.stdout


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c["thermal_relief"]["load_inputs"].update(saturation_temperature_at_relief_k=350),
        lambda c: c["thermal_relief"]["sizing_inputs"].update(flow_l_min=100),
        lambda c: c["thermal_relief"]["load_inputs"].update(heat_transfer_area_m2_typo=1),
    ],
)
def test_unsupported_thermal_case_never_writes_note(tmp_path, mutation):
    c = thermal_case()
    mutation(c)
    p = tmp_path / "invalid-thermal.json"
    p.write_text(json.dumps(c))
    note = tmp_path / "note.md"
    assert run_cli(p, "--output", note).returncode == 2
    assert not note.exists()


def test_standalone_thermal_example_note_is_reproducible():
    r = run_cli("examples/thermal-expansion.json")
    assert r.returncode == 0, r.stderr
    assert r.stdout == (ROOT / "docs/thermal-calculation-note.md").read_text()
