"""Screening and duplicate policies are explicit and independently inspectable."""

import json
import math
from collections import defaultdict
from importlib.resources import files

from pyproj.exceptions import CRSError, ProjError

from .ingest import normalize


def load_guidelines():
    return json.loads(files("site_data_qaqc").joinpath("guidelines.json").read_text())


def screen(row, guidelines):
    guideline = next(
        (g for g in guidelines if (g["matrix"], g["analyte"]) == (row["matrix"], row["analyte"])),
        None,
    )
    row.update(
        guideline_id=None, guideline_value=None, screening="no_guideline", exceedance_ratio=None
    )
    if guideline:
        threshold = guideline["value"]
        row.update(guideline_id=guideline["guideline_id"], guideline_value=threshold)
        if row["censored"]:
            row["screening"] = (
                "indeterminate" if row["detection_limit"] > threshold else "below_limit"
            )
        else:
            row["screening"] = "exceeds" if row["value"] > threshold else "at_or_below"
            ratio = row["value"] / threshold
            row["exceedance_ratio"] = ratio if math.isfinite(ratio) else None


def assess(raw_rows, default_crs="EPSG:26917", rpd_limit=30.0, dl_multiplier=5.0):
    if not math.isfinite(rpd_limit) or rpd_limit < 0:
        raise ValueError("RPD limit must be finite and non-negative")
    if not math.isfinite(dl_multiplier) or dl_multiplier < 1:
        raise ValueError("detection-limit multiplier must be finite and >= 1")
    accepted, rejected, issues, duplicates = [], [], [], []
    guidelines = load_guidelines()

    def issue(row, code, message, severity="warning"):
        issues.append(
            {"record_id": row["record_id"], "code": code, "severity": severity, "message": message}
        )

    for record_id, raw in enumerate(raw_rows, 1):
        audit = {k: raw[k] for k in ("source_file", "source_sha256", "source_row", "raw_json")}
        audit["record_id"] = record_id
        try:
            row = normalize(raw, default_crs)
        except (ValueError, CRSError, ProjError) as exc:
            audit["reason"] = str(exc)
            rejected.append(audit)
            issue(audit, "invalid_record", str(exc), "error")
            continue
        row["record_id"] = record_id
        accepted.append(row)
    # Reject every member of a repeated natural key, rather than keep whichever file came first.
    groups = defaultdict(list)
    for row in accepted:
        groups[
            (row["site_id"], row["sample_id"], row["sample_date"], row["matrix"], row["analyte"])
        ].append(row)
    repeated = {r["record_id"] for group in groups.values() if len(group) > 1 for r in group}
    events = defaultdict(list)
    for row in accepted:
        events[(row["site_id"], row["sample_id"], row["sample_date"], row["matrix"])].append(row)
    inconsistent = set()
    for event in events.values():
        first = event[0]
        if any(
            any(r[k] != first[k] for k in ("borehole_id", "depth_top_m", "depth_bottom_m"))
            or abs(r["longitude"] - first["longitude"]) > 1e-5
            or abs(r["latitude"] - first["latitude"]) > 1e-5
            for r in event
        ):
            inconsistent.update(r["record_id"] for r in event)
    clean = []
    for row in accepted:
        if row["record_id"] in repeated or row["record_id"] in inconsistent:
            code = "duplicate_key" if row["record_id"] in repeated else "inconsistent_sample"
            reason = (
                "repeated site/sample/date/matrix/analyte key; all conflicting rows quarantined"
                if code == "duplicate_key"
                else "sample event has conflicting borehole, depth or coordinates; all rows quarantined"
            )
            rejected.append(
                {
                    k: row[k]
                    for k in ("record_id", "source_file", "source_sha256", "source_row", "raw_json")
                }
                | {"reason": reason}
            )
            issue(row, code, reason, "error")
        else:
            clean.append(row)
    accepted = clean
    for row in accepted:
        screen(row, guidelines)
        if row["detection_limit"] is None:
            issue(row, "missing_detection_limit", "No DL: duplicate precision cannot be assessed")
        elif not row["censored"] and row["value"] < row["detection_limit"]:
            issue(
                row,
                "below_detection_limit",
                "Detected value below DL; review laboratory qualification",
            )
        if row["qualifier"] == "J":
            issue(row, "estimated_result", "J-qualified result is an estimate; comparison retained")
        if row["screening"] in ("exceeds", "indeterminate", "no_guideline"):
            issue(row, row["screening"], "Screening status: " + row["screening"])
        if not row["duplicate_of"]:
            continue
        candidates = [
            r
            for r in accepted
            if r["site_id"] == row["site_id"]
            and r["sample_id"] == row["duplicate_of"]
            and r["analyte"] == row["analyte"]
            and r["matrix"] == row["matrix"]
            and r["sample_date"] == row["sample_date"]
        ]
        pair = {
            "duplicate_id": row["record_id"],
            "original_id": None,
            "rpd": None,
            "status": "missing_parent",
            "limit_percent": rpd_limit,
            "dl_multiplier": dl_multiplier,
        }
        if len(candidates) == 1:
            original = candidates[0]
            pair["original_id"] = original["record_id"]
            if original["duplicate_of"] or original["record_id"] == row["record_id"]:
                pair["status"] = "invalid_parent"
            elif any(
                original[k] != row[k] for k in ("borehole_id", "depth_top_m", "depth_bottom_m")
            ):
                pair["status"] = "incompatible_interval"
            elif (
                abs(original["longitude"] - row["longitude"]) > 1e-5
                or abs(original["latitude"] - row["latitude"]) > 1e-5
            ):
                pair["status"] = "incompatible_location"
            elif original["censored"] or row["censored"]:
                pair["status"] = "censored"
            elif original["detection_limit"] is None or row["detection_limit"] is None:
                pair["status"] = "missing_detection_limit"
            elif (
                original["value"] <= dl_multiplier * original["detection_limit"]
                or row["value"] <= dl_multiplier * row["detection_limit"]
            ):
                pair["status"] = "near_detection_limit"
            else:
                a, b = original["value"], row["value"]
                # Scale first to avoid overflow for large but finite concentrations.
                scale = max(a, b)
                pair["rpd"] = 200 * abs(a / scale - b / scale) / (a / scale + b / scale)
                pair["status"] = "fail" if pair["rpd"] > rpd_limit else "pass"
        elif len(candidates) > 1:
            pair["status"] = "ambiguous_parent"
        duplicates.append(pair)
        if pair["status"] != "pass":
            issue(row, "duplicate_" + pair["status"], "Duplicate check: " + pair["status"])
    return {
        "results": accepted,
        "rejected": rejected,
        "issues": issues,
        "duplicates": duplicates,
        "guidelines": guidelines,
    }
