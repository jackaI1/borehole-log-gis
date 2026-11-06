"""Preliminary API 520 Part I areas, using metric equations.

Sources and worked examples: docs/equations.md. No valve is selected here.
Correction factors must be explicitly supplied for the service and valve.
"""

from dataclasses import dataclass
from math import exp, log1p, sqrt

from .validation import number


def _factors(**factors):
    for name, value in factors.items():
        number(name, value, positive=True, maximum=1)


@dataclass(frozen=True)
class GasSizing:
    area_mm2: float
    c_metric: float
    critical_pressure_ratio: float
    backpressure_ratio: float


def size_gas(
    *,
    mass_flow_kg_h: float,
    temperature_k: float,
    molecular_weight_kg_kmol: float,
    k: float,
    compressibility: float,
    inlet_kpa_abs: float,
    backpressure_kpa_abs: float,
    kd: float,
    kb: float,
    kc: float,
) -> GasSizing:
    """Critical gas/vapor flow: A=W sqrt(T Z/M)/(C Kd P1 Kb Kc).

    A in mm², W in kg/h, T in K, M in kg/kmol, P1/P2 in kPa absolute.
    Implementation scope: 1 < k <= 1.67, 0.2 <= Z <= 2.0. These are
    conservative tool limits, not a claim that API defines a universal Z range.
    """
    for name, value in dict(
        mass_flow_kg_h=mass_flow_kg_h,
        temperature_k=temperature_k,
        molecular_weight_kg_kmol=molecular_weight_kg_kmol,
        inlet_kpa_abs=inlet_kpa_abs,
        backpressure_kpa_abs=backpressure_kpa_abs,
    ).items():
        number(name, value, positive=True)
    number("k", k, minimum=1, maximum=1.67)
    if k == 1:
        raise ValueError("k must be greater than 1")
    number("compressibility", compressibility, minimum=0.2, maximum=2)
    _factors(kd=kd, kb=kb, kc=kc)
    log_ratio = -log1p((k - 1) / 2)
    critical = exp(k * log_ratio / (k - 1))
    ratio = backpressure_kpa_abs / inlet_kpa_abs
    if ratio > critical:
        raise ValueError(
            f"gas is not critical flow: P2/P1={ratio:.8g} > {critical:.8g}; "
            "subcritical sizing is unsupported"
        )
    c = 0.03948 * sqrt(k * exp((k + 1) * log_ratio / (k - 1)))
    area = mass_flow_kg_h * sqrt(temperature_k * compressibility / molecular_weight_kg_kmol)
    denominator = c * kd * inlet_kpa_abs * kb * kc
    number("gas sizing denominator", denominator, positive=True)
    area /= denominator
    number("calculated area_mm2", area, positive=True)
    return GasSizing(area, c, critical, ratio)


@dataclass(frozen=True)
class LiquidSizing:
    area_mm2: float
    differential_kpa: float


def size_liquid(
    *,
    flow_l_min: float,
    specific_gravity: float,
    inlet_kpa_abs: float,
    backpressure_kpa_abs: float,
    vapor_pressure_kpa_abs: float,
    kd: float,
    kw: float,
    kc: float,
    kv: float,
) -> LiquidSizing:
    """Nonflashing liquid: A=11.78 Q sqrt(G/(P1-P2))/(Kd Kw Kc Kv).

    A in mm², Q in L/min, G relative to water, P1/P2/Pv in kPa absolute.
    Kv is a supplied viscosity correction, not inferred from pipe Reynolds number.
    P2 > Pv is only a flashing screen; nozzle cavitation needs separate review.
    """
    for name, value in dict(
        flow_l_min=flow_l_min,
        specific_gravity=specific_gravity,
        inlet_kpa_abs=inlet_kpa_abs,
        backpressure_kpa_abs=backpressure_kpa_abs,
        vapor_pressure_kpa_abs=vapor_pressure_kpa_abs,
    ).items():
        number(name, value, positive=True)
    _factors(kd=kd, kw=kw, kc=kc, kv=kv)
    if inlet_kpa_abs <= backpressure_kpa_abs:
        raise ValueError("liquid inlet pressure must exceed backpressure")
    if backpressure_kpa_abs <= vapor_pressure_kpa_abs:
        raise ValueError(
            "flashing screen failed: backpressure must exceed vapor pressure; "
            "use a two-phase method"
        )
    differential = inlet_kpa_abs - backpressure_kpa_abs
    denominator = kd * kw * kc * kv
    number("liquid sizing denominator", denominator, positive=True)
    area = 11.78 * flow_l_min * sqrt(specific_gravity / differential) / denominator
    number("calculated area_mm2", area, positive=True)
    return LiquidSizing(area, differential)
