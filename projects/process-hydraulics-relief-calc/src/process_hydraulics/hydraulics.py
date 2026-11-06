"""Steady incompressible Darcy-Weisbach series/parallel networks, in SI units.

Numerical searches use a labeled transitional interpolation only to locate roots.
Every reported solution is re-evaluated strictly and rejects transitional flow.
"""

from dataclasses import dataclass
from math import isclose, log10, pi, ulp

from .validation import number, text

G = 9.80665


def friction_factor(reynolds: float, relative_roughness: float, *, _search=False) -> float:
    """Darcy (not Fanning) factor: 64/Re or iterative Colebrook.

    Supported: 0 < Re < 2300 or 4000 <= Re <= 1e8; 0 <= epsilon/D <= .05.
    """
    number("Reynolds number", reynolds, positive=True, maximum=1e8)
    number("relative roughness", relative_roughness, minimum=0, maximum=0.05)
    if reynolds < 2300:
        return 64 / reynolds
    if reynolds < 4000:
        if not _search:
            raise ValueError(f"transitional flow: Re={reynolds:.8g} is in [2300, 4000)")
        t = (reynolds - 2300) / 1700
        return (1 - t) * 64 / 2300 + t * friction_factor(4000, relative_roughness)
    # Iterate x=1/sqrt(f), with a bounded convergence check.
    x = 7.0
    for _ in range(100):
        nxt = -2 * log10(relative_roughness / 3.7 + 2.51 * x / reynolds)
        if abs(nxt - x) < 1e-12:
            return 1 / nxt**2
        x = nxt
    raise ValueError("Colebrook iteration failed to converge")


@dataclass(frozen=True)
class Fluid:
    density_kg_m3: float
    viscosity_pa_s: float

    def __post_init__(self):
        number("density_kg_m3", self.density_kg_m3, positive=True)
        number("viscosity_pa_s", self.viscosity_pa_s, positive=True)


@dataclass(frozen=True)
class PipeResult:
    name: str
    flow_m3_s: float
    velocity_m_s: float
    reynolds: float
    friction_factor: float
    friction_pa: float
    fittings_pa: float
    elevation_pa: float

    @property
    def total_pa(self):
        return self.friction_pa + self.fittings_pa + self.elevation_pa


@dataclass(frozen=True)
class Pipe:
    name: str
    length_m: float
    diameter_m: float
    roughness_m: float
    fitting_k: float
    elevation_m: float

    def __post_init__(self):
        text("pipe name", self.name)
        number("length_m", self.length_m, positive=True)
        number("diameter_m", self.diameter_m, positive=True)
        number("pipe cross-sectional area_m2", self.area_m2, positive=True)
        number("roughness_m", self.roughness_m, minimum=0)
        number("relative roughness", self.roughness_m / self.diameter_m, maximum=0.05)
        number("fitting_k", self.fitting_k, minimum=0)
        number("elevation_m", self.elevation_m)

    @property
    def area_m2(self):
        return pi / 4 * self.diameter_m * self.diameter_m

    def evaluate(self, flow_m3_s: float, fluid: Fluid, *, _search=False) -> PipeResult:
        number("flow_m3_s", flow_m3_s, minimum=0)
        velocity = flow_m3_s / self.area_m2
        number("calculated velocity_m_s", velocity, positive=flow_m3_s > 0)
        re = fluid.density_kg_m3 * velocity * self.diameter_m / fluid.viscosity_pa_s
        number("calculated Reynolds number", re, positive=flow_m3_s > 0)
        f = friction_factor(re, self.roughness_m / self.diameter_m, _search=_search) if re else 0
        dynamic = fluid.density_kg_m3 / 2 * velocity * velocity
        number("calculated dynamic pressure_pa", dynamic, positive=flow_m3_s > 0)
        result = PipeResult(
            self.name,
            flow_m3_s,
            velocity,
            re,
            f,
            f * self.length_m / self.diameter_m * dynamic,
            self.fitting_k * dynamic,
            fluid.density_kg_m3 * G * self.elevation_m,
        )
        for label, value in [
            ("friction", result.friction_pa),
            ("fittings", result.fittings_pa),
            ("elevation", result.elevation_pa),
            ("pipe total", result.total_pa),
        ]:
            number(f"calculated {label} pressure_pa", value)
        return result


@dataclass(frozen=True)
class Branch:
    pipes: tuple[Pipe, ...]

    def __post_init__(self):
        if not self.pipes or any(not isinstance(p, Pipe) for p in self.pipes):
            raise ValueError("branch requires one or more Pipe objects")

    @property
    def elevation_m(self):
        return number("branch elevation_m", sum(p.elevation_m for p in self.pipes))

    def loss_pa(self, flow, fluid):
        results = [p.evaluate(flow, fluid, _search=True) for p in self.pipes]
        return number("branch loss_pa", sum(r.friction_pa + r.fittings_pa for r in results))


def _bisect_increasing(function, target, lo, hi):
    """Root in a monotone bracket; tolerance follows the converged root scale."""
    f_lo, f_hi = function(lo), function(hi)
    if not f_lo <= target <= f_hi:
        raise ValueError("no root within supplied bracket")
    if target == f_lo:
        return lo
    if target == f_hi:
        return hi
    # A worst-case initial bracket can be many orders larger than the root.
    # 1100 iterations cover even subnormal binary64 brackets; normal cases take ~35.
    for _ in range(1100):
        mid = lo + (hi - lo) / 2
        if function(mid) < target:
            lo = mid
        else:
            hi = mid
        if hi - lo <= max(hi * 1e-10, ulp(hi)):
            return lo + (hi - lo) / 2
    raise ValueError("root search failed to converge")


@dataclass(frozen=True)
class ParallelStage:
    branches: tuple[Branch, ...]

    def __post_init__(self):
        if not self.branches or any(not isinstance(b, Branch) for b in self.branches):
            raise ValueError("parallel stage requires one or more Branch objects")
        z = self.branches[0].elevation_m
        if any(not isclose(b.elevation_m, z, abs_tol=1e-9, rel_tol=0) for b in self.branches):
            raise ValueError("parallel branches must have the same endpoint elevation change")

    def _solve(self, flow, fluid, *, _search):
        if flow == 0 or len(self.branches) == 1:
            flows = [flow] * len(self.branches)
        else:
            # Maximum branch loss at total Q guarantees an upper pressure bracket.
            maxima = [b.loss_pa(flow, fluid) for b in self.branches]

            def split(loss):
                return [
                    flow
                    if loss >= limit
                    else _bisect_increasing(lambda q, b=branch: b.loss_pa(q, fluid), loss, 0, flow)
                    for branch, limit in zip(self.branches, maxima, strict=True)
                ]

            common_loss = _bisect_increasing(lambda dp: sum(split(dp)), flow, 0, max(maxima))
            flows = split(common_loss)
            if not isclose(sum(flows), flow, rel_tol=1e-8, abs_tol=0):
                raise ValueError("parallel solver failed flow conservation")
            losses = [b.loss_pa(q, fluid) for b, q in zip(self.branches, flows, strict=True)]
            if any(not isclose(loss, common_loss, rel_tol=1e-8, abs_tol=0) for loss in losses):
                raise ValueError("parallel solver failed pressure balance")
        pipes = tuple(
            p.evaluate(q, fluid, _search=_search)
            for b, q in zip(self.branches, flows, strict=True)
            for p in b.pipes
        )
        first_count = len(self.branches[0].pipes)
        pressure = number("stage pressure_pa", sum(r.total_pa for r in pipes[:first_count]))
        return pressure, pipes


@dataclass(frozen=True)
class NetworkResult:
    flow_m3_s: float
    total_pa: float
    head_m: float
    stage_pressure_pa: tuple[float, ...]
    pipes: tuple[PipeResult, ...]


@dataclass(frozen=True)
class Network:
    stages: tuple[ParallelStage, ...]

    def __post_init__(self):
        if not self.stages or any(not isinstance(s, ParallelStage) for s in self.stages):
            raise ValueError("network requires one or more ParallelStage objects")
        names = [p.name for s in self.stages for b in s.branches for p in b.pipes]
        if len(names) != len(set(names)):
            raise ValueError("pipe names must be unique in the network")

    def evaluate(self, flow_m3_s, fluid, *, _search=False):
        number("flow_m3_s", flow_m3_s, minimum=0)
        results = [s._solve(flow_m3_s, fluid, _search=_search) for s in self.stages]
        dp = number("network pressure_pa", sum(r[0] for r in results))
        head = number("network head_m", dp / (fluid.density_kg_m3 * G))
        return NetworkResult(
            flow_m3_s,
            dp,
            head,
            tuple(r[0] for r in results),
            tuple(p for r in results for p in r[1]),
        )


@dataclass(frozen=True)
class PumpCurve:
    points: tuple[tuple[float, float], ...]

    def __post_init__(self):
        if len(self.points) < 2:
            raise ValueError("pump curve requires at least two (flow_m3_s, head_m) points")
        for point in self.points:
            if len(point) != 2:
                raise ValueError("pump curve point requires flow and head")
            number("pump flow_m3_s", point[0], minimum=0)
            number("pump head_m", point[1], minimum=0)
        for (q0, h0), (q1, h1) in zip(self.points, self.points[1:], strict=False):
            if q1 <= q0 or h1 >= h0:
                raise ValueError("pump flows must increase and heads must strictly decrease")

    def head_at(self, flow_m3_s):
        number("pump flow_m3_s", flow_m3_s, minimum=0)
        if not self.points[0][0] <= flow_m3_s <= self.points[-1][0]:
            raise ValueError("flow outside pump curve; extrapolation is unsupported")
        for (q0, h0), (q1, h1) in zip(self.points, self.points[1:], strict=False):
            if flow_m3_s <= q1:
                return h0 + (h1 - h0) * (flow_m3_s - q0) / (q1 - q0)
        raise ValueError("flow outside pump curve")


@dataclass(frozen=True)
class OperatingPoint:
    flow_m3_s: float
    pump_head_m: float
    within_acceptable_flow: bool
    system: NetworkResult


def operating_point(
    network: Network, fluid: Fluid, curve: PumpCurve, acceptable_flow_m3_s: tuple[float, float]
) -> OperatingPoint:
    if len(acceptable_flow_m3_s) != 2:
        raise ValueError("acceptable_flow_m3_s requires [minimum, maximum]")
    low, high = acceptable_flow_m3_s
    number("acceptable minimum flow", low, minimum=0)
    number("acceptable maximum flow", high, minimum=low)
    lo, hi = curve.points[0][0], curve.points[-1][0]

    def residual(q):
        return network.evaluate(q, fluid, _search=True).head_m - curve.head_at(q)

    if residual(lo) > 0 or residual(hi) < 0:
        raise ValueError("no pump/system intersection within supplied pump curve")
    q = _bisect_increasing(residual, 0, lo, hi)
    # Strict re-evaluation rejects transition even if the root search crossed it.
    system = network.evaluate(q, fluid)
    return OperatingPoint(q, curve.head_at(q), low <= q <= high, system)
