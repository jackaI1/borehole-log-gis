"""Confined-aquifer pumping and recovery analysis. Internal units are metres and seconds."""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.special import exp1
from scipy.stats import t as student_t

LENGTH = {"m": 1.0, "ft": 0.3048}
RATE = {"m3/s": 1.0, "L/s": 0.001, "L/min": 0.001 / 60, "m3/day": 1 / 86400}
PRESSURE = {"Pa": 1.0, "kPa": 1000.0, "hPa": 100.0}


def positive(value, name):
    if isinstance(value, bool) or not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def theis(time_s, rate_m3_s, radius_m, transmissivity_m2_s, storativity):
    """s = Q E1(r² S / 4 T t) / 4 pi T. Requires an observation well."""
    time_s = np.asarray(time_s, dtype=float)
    if not np.all(np.isfinite(time_s)) or np.any(time_s <= 0):
        raise ValueError("Elapsed times must be finite and positive")
    q, r, tr, s = [positive(v, n) for v, n in zip(
        [rate_m3_s, radius_m, transmissivity_m2_s, storativity], ["rate", "radius", "T", "S"])]
    return q / (4 * np.pi * tr) * exp1(r * r * s / (4 * tr * time_s))


def residual_theis(after_stop_s, duration_s, rate_m3_s, radius_m, transmissivity_m2_s, storativity):
    """Superpose continued pumping and equal negative pumping after shutoff."""
    positive(duration_s, "pumping duration")
    return (theis(np.asarray(after_stop_s) + duration_s, rate_m3_s, radius_m,
                  transmissivity_m2_s, storativity)
            - theis(after_stop_s, rate_m3_s, radius_m, transmissivity_m2_s, storativity))


@dataclass
class Observations:
    time_s: np.ndarray
    drawdown_m: np.ndarray
    corrected_m: np.ndarray
    rate_m3_s: float
    radius_m: float
    duration_s: float | None
    correction: dict


def utc_timestamp(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError("Every timestamp must include a UTC offset")
    return stamp.tz_convert("UTC")


def load_observations(csv_path: Path, metadata: dict):
    """Reject reordered/duplicate timestamps; never interpolate pressure observations.

    A positive pressure change lowers observed head and increases drawdown.
    Subtract BE * (p-p_reference)/(rho*g) from that observed drawdown.
    BE must come from an independent pre-test calibration, not this pumping fit.
    """
    frame = pd.read_csv(csv_path)
    if not {"timestamp", "drawdown"} <= set(frame):
        raise ValueError("CSV requires timestamp and drawdown columns")
    try:
        depth_scale = LENGTH[metadata["drawdown_unit"]]
        rate = positive(metadata["rate"], "rate") * RATE[metadata["rate_unit"]]
        radius = positive(metadata["radius"], "radius") * LENGTH[metadata["radius_unit"]]
    except KeyError as exc:
        raise ValueError(f"Missing or unsupported unit/metadata: {exc}") from exc
    start = utc_timestamp(metadata["start"])
    stamps = [utc_timestamp(v) for v in frame.timestamp]
    elapsed = np.array([(v - start).total_seconds() for v in stamps])
    if len(elapsed) < 3 or not np.all(np.diff(elapsed) > 0) or np.any(elapsed <= 0):
        raise ValueError("Need >=3 strictly increasing timestamps after pumping starts")
    drawdown = pd.to_numeric(frame.drawdown, errors="raise").to_numpy(dtype=float) * depth_scale
    if not np.isfinite(drawdown).all():
        raise ValueError("Drawdown must be finite")
    corrected = drawdown.copy()
    correction = {"applied": False}
    if "barometric_pressure" in frame:
        try:
            scale = PRESSURE[metadata["pressure_unit"]]
            efficiency = float(metadata["barometric_efficiency"])
            reference = float(metadata["reference_pressure"]) * scale
        except KeyError as exc:
            raise ValueError("Pressure requires units, independent BE and a reference pressure") from exc
        pressure = pd.to_numeric(frame.barometric_pressure, errors="raise").to_numpy(dtype=float) * scale
        if (not np.isfinite(efficiency) or not 0 <= efficiency <= 1 or not np.isfinite(reference)
                or reference <= 0 or not np.isfinite(pressure).all() or np.any(pressure <= 0)):
            raise ValueError("Pressure must be positive and BE must be between 0 and 1")
        corrected -= efficiency * (pressure - reference) / (1000 * 9.80665)
        correction = {"applied": True, "efficiency": efficiency, "reference_pressure_pa": reference,
                      "formula": "corrected = observed - BE*(p-p_ref)/(1000*9.80665)"}
    elif "barometric_efficiency" in metadata:
        raise ValueError("Barometric correction requested but pressure observations are absent")
    duration = None
    if "stop" in metadata:
        duration = positive((utc_timestamp(metadata["stop"]) - start).total_seconds(), "duration")
        if np.any(elapsed <= duration):
            raise ValueError("Recovery CSV must contain only times strictly after shutoff")
    return Observations(elapsed, drawdown, corrected, rate, radius, duration, correction)


def fit_metrics(observed, predicted):
    residual = predicted - observed
    ss = float(residual @ residual)
    total = float(np.sum((observed - np.mean(observed)) ** 2))
    return {"rmse_m": float(np.sqrt(ss / len(observed))),
            "r_squared": 1 - ss / total if total > 0 else None}


def parameter_report(log_parameters, covariance, degrees):
    values = np.exp(log_parameters)
    intervals = None
    if covariance is not None and degrees > 0 and np.isfinite(covariance).all():
        spread = student_t.ppf(0.975, degrees) * np.sqrt(np.maximum(0, covariance.diagonal()))
        # Do not emit infinite intervals or imply late recovery identifies S.
        if np.all(spread < 30):
            intervals = np.exp(np.column_stack((log_parameters - spread, log_parameters + spread))).tolist()
    return {"transmissivity_m2_s": float(values[0]), "transmissivity_m2_day": float(values[0] * 86400),
            "storativity": float(values[1]), "ci95_T_m2_s": intervals[0] if intervals else None,
            "ci95_S": intervals[1] if intervals else None}


def fit_theis(times, drawdown, rate, radius, duration=None):
    times, drawdown = np.asarray(times), np.asarray(drawdown)
    predictor = (lambda tr, s: theis(times, rate, radius, tr, s)) if duration is None else (
        lambda tr, s: residual_theis(times - duration, duration, rate, radius, tr, s))
    def residual(log_values):
        return predictor(*np.exp(log_values)) - drawdown
    result = least_squares(residual, np.log([0.001, 0.0001]),
                           bounds=(np.log([1e-9, 1e-10]), np.log([1, 1])),
                           xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=3000)
    degrees = len(times) - 2
    covariance = None
    condition = float(np.linalg.cond(result.jac))
    if degrees > 0 and condition < 1e6:
        covariance = np.linalg.pinv(result.jac.T @ result.jac) * np.sum(result.fun ** 2) / degrees
    report = parameter_report(result.x, covariance, degrees)
    report.update(fit_metrics(drawdown, predictor(*np.exp(result.x))))
    report.update({"points": len(times), "converged": bool(result.success),
                   "jacobian_condition": condition if np.isfinite(condition) else None})
    flags = []
    if not result.success or np.any(result.active_mask):
        flags.append("fit failed or reached parameter bounds")
    if covariance is None or report["ci95_S"] is None:
        flags.append("parameters poorly identified; confidence intervals unavailable")
    if report["r_squared"] is None or report["r_squared"] < 0.98:
        flags.append("poor fit: R-squared below 0.98")
    report["flags"] = flags
    return report


def fit_cooper_jacob(times, drawdown, rate, radius):
    """Fit natural log time; propagate slope/intercept covariance into log(T),log(S)."""
    times, drawdown = np.asarray(times, dtype=float), np.asarray(drawdown, dtype=float)
    if len(times) < 2 or len(times) != len(drawdown) or np.any(times <= 0):
        raise ValueError("Cooper-Jacob needs at least two positive times and paired drawdowns")
    design = np.column_stack((np.log(times), np.ones(len(times))))
    if np.linalg.matrix_rank(design) < 2:
        raise ValueError("Cooper-Jacob needs distinct times")
    slope, intercept = np.linalg.lstsq(design, drawdown, rcond=None)[0]
    if slope <= 0:
        return {"flags": ["nonpositive late-time slope"], "points": len(times)}
    tr = rate / (4 * np.pi * slope)
    log_s = np.log(4 * np.exp(-np.euler_gamma) * tr / radius ** 2) - intercept / slope
    degrees = len(times) - 2
    predicted = design @ [slope, intercept]
    covariance = None
    if degrees > 0:
        cov_line = np.linalg.inv(design.T @ design) * np.sum((predicted - drawdown) ** 2) / degrees
        jac = np.array([[-1 / slope, 0], [-1 / slope + intercept / slope ** 2, -1 / slope]])
        covariance = jac @ cov_line @ jac.T
    report = parameter_report(np.array([np.log(tr), log_s]), covariance, degrees)
    report.update(fit_metrics(drawdown, predicted))
    max_u = radius ** 2 * report["storativity"] / (4 * tr * times.min())
    report.update({"points": len(times), "max_u": float(max_u), "flags": []})
    if max_u > 0.01:
        report["flags"].append("late-time assumption fails: u exceeds 0.01")
    if len(times) < 5:
        report["flags"].append("too few late-time points: need at least 5")
    if report["r_squared"] is None or report["r_squared"] < 0.98:
        report["flags"].append("poor straight-line fit")
    return report


def analyze(csv_path, metadata, output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be new or empty")
    obs = load_observations(Path(csv_path), metadata)
    result = fit_theis(obs.time_s, obs.corrected_m, obs.rate_m3_s, obs.radius_m, obs.duration_s)
    report = {"mode": "recovery" if obs.duration_s else "pumping", "units": "m, s, m3/s",
              "barometric_correction": obs.correction, "theis": result,
              "assumptions": "Constant rate, confined homogeneous aquifer, fully penetrating observation well; no boundaries"}
    predicted = (theis(obs.time_s, obs.rate_m3_s, obs.radius_m,
                       result["transmissivity_m2_s"], result["storativity"]) if obs.duration_s is None else
                 residual_theis(obs.time_s - obs.duration_s, obs.duration_s, obs.rate_m3_s,
                                obs.radius_m, result["transmissivity_m2_s"], result["storativity"]))
    if obs.duration_s is None:
        # Select with Theis, then check again against the fitted straight line.
        threshold = positive(metadata.get("late_time_s", 1), "late_time_s")
        u = obs.radius_m ** 2 * result["storativity"] / (4 * result["transmissivity_m2_s"] * obs.time_s)
        selected = (u <= 0.01) & (obs.time_s >= threshold)
        report["cooper_jacob"] = (fit_cooper_jacob(obs.time_s[selected], obs.corrected_m[selected],
                                                 obs.rate_m3_s, obs.radius_m) if selected.sum() >= 2 else
                                  {"points": int(selected.sum()), "flags": ["too few late-time points"]})
    else:
        selected = np.zeros(len(obs.time_s), dtype=bool)
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"elapsed_s": obs.time_s, "observed_m": obs.drawdown_m, "corrected_m": obs.corrected_m,
                  "theis_m": predicted, "residual_m": obs.corrected_m - predicted,
                  "late_time_selected": selected}).to_csv(output / "observations.csv", index=False)
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(8, 7))
    axes[0].semilogx(obs.time_s, obs.drawdown_m, ".", label="Observed")
    axes[0].semilogx(obs.time_s, obs.corrected_m, ".", label="Barometric corrected")
    axes[0].semilogx(obs.time_s, predicted, label="Theis residual" if obs.duration_s else "Theis")
    axes[0].set_ylabel("Drawdown (m)")
    axes[0].legend()
    axes[1].semilogx(obs.time_s, obs.corrected_m - predicted, ".")
    axes[1].axhline(0, color="black", lw=0.5)
    axes[1].set(xlabel="Time since pumping started (s, log scale)", ylabel="Residual (m)")
    fig.tight_layout()
    fig.savefig(output / "diagnostic.png", dpi=130)
    plt.close(fig)
    return report
