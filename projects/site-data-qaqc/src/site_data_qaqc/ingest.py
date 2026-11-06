"""Strict, row-preserving adapters for legacy delimited laboratory exports."""

import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime
from pathlib import Path

from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError, ProjError

ALIASES = {
    "site_id": ["site", "site id", "project"],
    "borehole_id": ["borehole", "bh", "well", "location"],
    "sample_id": ["sample", "sample id", "lab id"],
    "sample_date": ["date", "sampled", "sampling date"],
    "matrix": ["medium", "media"],
    "analyte": ["parameter", "chemical"],
    "result": ["value", "concentration"],
    "unit": ["units"],
    "detection_limit": ["dl", "mdl", "reporting limit"],
    "qualifier": ["flag", "lab qualifier"],
    "duplicate_of": ["parent", "duplicate of"],
    "x": ["easting", "longitude"],
    "y": ["northing", "latitude"],
    "crs": ["epsg"],
    "depth_top_m": ["top m", "from m"],
    "depth_bottom_m": ["bottom m", "to m"],
    "lithology": ["soil description", "material"],
    "basis": ["weight basis"],
}
REQUIRED = [
    "site_id",
    "borehole_id",
    "sample_id",
    "sample_date",
    "matrix",
    "analyte",
    "result",
    "unit",
    "x",
    "y",
    "depth_top_m",
    "depth_bottom_m",
]
ANALYTES = {"as": "arsenic", "arsenic": "arsenic", "benzene": "benzene"}
FACTORS = {
    "groundwater": {"mg/l": 1, "ug/l": 0.001, "ng/l": 0.000001, "g/l": 1000},
    "soil": {"mg/kg": 1, "ug/g": 1, "ug/kg": 0.001, "g/kg": 1000},
}


class InputError(ValueError):
    """An input table cannot be interpreted without guessing."""


def key(value):
    return re.sub(r"[\s_]+", " ", value.strip().lower())


def number(value):
    # Decimal commas are accepted in semicolon/tab exports; thousands separators are not.
    value = value.strip().replace(",", ".")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
        raise ValueError(f"not a finite number: {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("number must be finite")
    return result


def date(value):
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError("date must be YYYY-MM-DD, YYYY/MM/DD or DD-Mon-YYYY")


def read_table(path: Path, encoding="utf-8-sig"):
    """Return raw records, never silently drop malformed lines or rename collisions."""
    content = path.read_bytes()
    text = content.decode(encoding)
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0] if text else "", delimiters=",;\t|")
    except csv.Error as exc:
        raise InputError(
            f"{path.name}: cannot detect a comma, semicolon, tab or pipe table"
        ) from exc
    reader = csv.reader(io.StringIO(text), dialect, strict=True)
    try:
        headers = next(reader)
    except StopIteration as exc:
        raise InputError(f"{path.name}: empty table") from exc
    lookup = {key(alias): name for name, aliases in ALIASES.items() for alias in [name, *aliases]}
    canonical = [lookup.get(key(h), h.strip()) for h in headers]
    if len(set(canonical)) != len(canonical):
        raise InputError(f"{path.name}: duplicate or colliding column names")
    missing = set(REQUIRED) - set(canonical)
    if missing:
        raise InputError(f"{path.name}: missing columns: {', '.join(sorted(missing))}")
    fingerprint = hashlib.sha256(content).hexdigest()
    rows = []
    for values in reader:
        line = reader.line_num
        if not values or all(not v.strip() for v in values):
            continue
        if len(values) != len(headers):
            raise InputError(
                f"{path.name}:{line}: expected {len(headers)} cells, got {len(values)}"
            )
        raw = dict(zip(headers, values, strict=True))
        rows.append(
            {
                "source_file": path.name,
                "source_sha256": fingerprint,
                "source_row": line,
                "raw_json": json.dumps(raw, ensure_ascii=False),
                "values": dict(zip(canonical, [v.strip() for v in values], strict=True)),
            }
        )
    return rows


def normalize(raw, default_crs):
    """One long-format row becomes one canonical analytical result, or an explicit rejection."""
    v = raw["values"]
    for name in REQUIRED:
        if not v.get(name):
            raise ValueError(f"missing field: {name}")
    matrix = {
        "gw": "groundwater",
        "water": "groundwater",
        "ground water": "groundwater",
        "groundwater": "groundwater",
        "soil": "soil",
    }.get(v["matrix"].lower())
    if not matrix:
        raise ValueError("matrix must be groundwater/GW/water or soil")
    unit = v["unit"].lower().replace("µ", "u").replace("μ", "u").replace(" ", "")
    if unit not in FACTORS[matrix]:
        raise ValueError(f"unsupported {matrix} unit: {v['unit']}")
    factor = FACTORS[matrix][unit]
    qualifier = v.get("qualifier", "").upper()
    if qualifier not in ("", "U", "ND", "J"):
        raise ValueError(f"unsupported qualifier: {qualifier}")
    result = v["result"].upper().strip()
    censored = result.startswith("<") or result in ("ND", "N/D", "U") or qualifier in ("U", "ND")
    dl = number(v["detection_limit"]) * factor if v.get("detection_limit") else None
    if dl is not None and dl <= 0:
        raise ValueError("detection limit must be positive")
    if censored:
        bound_text = re.sub(r"^<=?\s*", "", result, count=1)
        bound = None if bound_text in ("ND", "N/D", "U") else number(bound_text) * factor
        if bound is not None and dl is not None and not math.isclose(bound, dl, rel_tol=1e-9):
            raise ValueError("non-detect bound disagrees with detection limit")
        dl = bound if bound is not None else dl
        if dl is None or dl <= 0:
            raise ValueError("non-detect needs a positive detection limit")
        value = None
    else:
        value = number(result) * factor
        if value < 0:
            raise ValueError("negative concentration")
    if any(n is not None and not math.isfinite(n) for n in (value, dl)):
        raise ValueError("unit conversion overflow")
    top, bottom = number(v["depth_top_m"]), number(v["depth_bottom_m"])
    if top < 0 or bottom <= top:
        raise ValueError("depth interval must satisfy 0 <= top < bottom (metres)")
    basis = v.get("basis", "").lower()
    if matrix == "soil" and basis not in ("dry", "dry weight"):
        raise ValueError(
            "soil requires explicit dry weight basis; no wet-to-dry conversion guessed"
        )
    try:
        source_crs = CRS.from_user_input(v.get("crs") or default_crs)
    except CRSError as exc:
        raise ValueError("invalid coordinate reference system") from exc
    x, y = number(v["x"]), number(v["y"])
    if source_crs.is_geographic and not (-180 <= x <= 180 and -90 <= y <= 90):
        raise ValueError("geographic coordinates outside longitude/latitude bounds")
    try:
        lon, lat = Transformer.from_crs(source_crs, 4326, always_xy=True).transform(
            x, y, errcheck=True
        )
    except ProjError as exc:
        raise ValueError("coordinates outside the CRS projection domain / area of use") from exc
    area = source_crs.area_of_use
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("coordinates do not transform to a valid point")
    if area and not (
        area.south <= lat <= area.north
        and (
            area.west <= lon <= area.east
            if area.west <= area.east
            else lon >= area.west or lon <= area.east
        )
    ):
        raise ValueError("coordinates fall outside the declared CRS area of use")
    out = {k: raw[k] for k in ("source_file", "source_sha256", "source_row", "raw_json")}
    out.update(
        {
            k: v.get(k, "")
            for k in ("site_id", "borehole_id", "sample_id", "duplicate_of", "lithology")
        }
    )
    out.update(
        sample_date=date(v["sample_date"]),
        matrix=matrix,
        analyte=ANALYTES.get(v["analyte"].lower(), v["analyte"].lower()),
        value=value,
        detection_limit=dl,
        censored=int(censored),
        qualifier=qualifier,
        unit="mg/L" if matrix == "groundwater" else "mg/kg",
        basis="dry" if matrix == "soil" else "",
        x=x,
        y=y,
        source_crs=source_crs.to_string(),
        longitude=lon,
        latitude=lat,
        depth_top_m=top,
        depth_bottom_m=bottom,
    )
    return out
