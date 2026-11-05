"""Read an AGS4 subset or the BC Borehole Log Lithology CSV schema.

Unknown AGS groups are preserved by parse_ags, but not interpreted by the tool.
Row numbers always refer to physical source lines, including CSV quoted newlines.
"""

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

from pyproj import CRS

from .model import SPT, Dataset, Hole, Interval

LENGTHS = {"m": 1.0, "ft": 0.3048, "mm": 0.001}
REQUIRED_GROUPS = {"PROJ", "TRAN", "ABBR", "TYPE", "UNIT", "LOCA", "GEOL"}
BC_FIELDS = {
    "BOREHOLE_SITE_ID",
    "BOREHOLE_NAME",
    "LATITUDE",
    "LONGITUDE",
    "TOTAL_DEPTH",
    "FROM_UNIT_DEPTH",
    "TO_UNIT_DEPTH",
    "UNIT_DESCRIPTION",
}


@dataclass
class Group:
    headings: list[str] = field(default_factory=list)
    units: list[str] | None = None
    types: list[str] | None = None
    rows: list[tuple[int, dict]] = field(default_factory=list)


def parse_ags(path: Path):
    """Parse quoted CSV records and reject ambiguous structural corruption."""
    groups = {}
    group = None
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        for cells in reader:
            line = reader.line_num
            if not cells or all(not c for c in cells):
                continue
            tag, *values = cells
            if tag == "GROUP":
                if len(values) != 1 or not values[0] or values[0] in groups:
                    raise ValueError(f"line {line}: invalid or repeated GROUP")
                group = groups[values[0]] = Group()
                continue
            if group is None:
                raise ValueError(f"line {line}: record before GROUP")
            if tag == "HEADING":
                if group.headings or not values or len(set(values)) != len(values):
                    raise ValueError(f"line {line}: invalid or repeated HEADING")
                group.headings = values
                continue
            if not group.headings or len(values) != len(group.headings):
                raise ValueError(f"line {line}: row width does not match HEADING")
            if tag in {"UNIT", "TYPE"}:
                attr = tag.lower() + "s"
                if getattr(group, attr) is not None or group.rows:
                    raise ValueError(f"line {line}: misplaced or repeated {tag}")
                setattr(group, attr, values)
            elif tag == "DATA":
                group.rows.append((line, dict(zip(group.headings, values))))
            else:
                raise ValueError(f"line {line}: unsupported record tag {tag!r}")
    return groups


def number(ds, raw, group, row, hole, field):
    try:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError
        return value
    except (ValueError, TypeError):
        ds.issue("invalid_number", group, row, hole, f"{field}: expected a finite number, got {raw!r}")
        return None


def read_ags(path: Path, crs: str):
    ds = Dataset(CRS.from_user_input(crs).to_string())
    groups = parse_ags(path)
    for name in sorted(REQUIRED_GROUPS - groups.keys()):
        ds.issue("missing_group", name, 0, "", f"Required group {name} is absent")
    for name, g in groups.items():
        if not g.headings or g.units is None or g.types is None:
            ds.issue("missing_metadata", name, 0, "", "HEADING, UNIT and TYPE records are required")
        if name in REQUIRED_GROUPS and not g.rows:
            ds.issue("empty_group", name, 0, "", "Required group has no DATA records")
    specs = {
        "LOCA": ("LOCA_ID", "LOCA_NATE", "LOCA_NATN", "LOCA_FDEP"),
        "GEOL": ("LOCA_ID", "GEOL_TOP", "GEOL_BASE", "GEOL_DESC"),
        "ISPT": ("LOCA_ID", "ISPT_TOP", "ISPT_NVAL"),
    }
    unit_defs = {r.get("UNIT_UNIT") for _, r in groups.get("UNIT", Group()).rows}
    type_defs = {r.get("TYPE_TYPE") for _, r in groups.get("TYPE", Group()).rows}
    for name, g in groups.items():
        for heading, unit in zip(g.headings, g.units or []):
            if unit and unit not in unit_defs:
                ds.issue("undefined_unit", name, 0, "", f"{heading}: unit {unit!r} missing from UNIT")
        for heading, dtype in zip(g.headings, g.types or []):
            if dtype and dtype not in type_defs:
                ds.issue("undefined_type", name, 0, "", f"{heading}: type {dtype!r} missing from TYPE")
    coordinate_crs = CRS.from_user_input(crs)
    for name, fields in specs.items():
        if name not in groups:
            continue
        g = groups[name]
        missing = set(fields) - set(g.headings)
        if missing:
            ds.issue("missing_heading", name, 0, "", f"Missing headings: {', '.join(sorted(missing))}")
            continue
        units = dict(zip(g.headings, g.units or []))
        factors = {}
        for f in fields:
            if f in {"LOCA_ID", "GEOL_DESC"}:
                continue
            unit = units.get(f, "")
            if f in {"LOCA_NATE", "LOCA_NATN"}:
                # Coordinates remain in the explicitly declared CRS; do not rescale silently.
                axis = coordinate_crs.axis_info[0]
                ok = (
                    coordinate_crs.is_projected
                    and unit in LENGTHS
                    and abs(LENGTHS[unit] - axis.unit_conversion_factor) < 1e-10
                )
                if not ok:
                    ds.issue("coordinate_unit", name, 0, "", f"{f}: {unit!r} does not match projected CRS")
                factors[f] = 1.0
            elif f == "ISPT_NVAL":
                if unit not in {"", "-"}:
                    ds.issue("invalid_unit", name, 0, "", f"{f} must be dimensionless")
                factors[f] = 1.0
            elif unit not in LENGTHS:
                ds.issue("invalid_unit", name, 0, "", f"{f}: unsupported length unit {unit!r}")
            else:
                factors[f] = LENGTHS[unit]
        if len(factors) != len(fields) - (2 if name == "GEOL" else 1):
            continue
        for line, row in g.rows:
            hole = row["LOCA_ID"].strip()
            vals = {
                f: number(ds, row[f], name, line, hole, f)
                for f in factors
                if not (f == "ISPT_NVAL" and not row[f].strip())
            }
            if name == "ISPT" and "ISPT_NVAL" not in vals:
                ds.issue(
                    "missing_spt_n",
                    name,
                    line,
                    hole,
                    "No numeric N-value; retained source test remark, no N-value inferred",
                    "warning",
                )
            if any(v is None for v in vals.values()):
                continue
            vals = {f: v * factors[f] for f, v in vals.items()}
            if name == "LOCA":
                ds.holes.append(Hole(hole, vals["LOCA_NATE"], vals["LOCA_NATN"], vals["LOCA_FDEP"], line))
            elif name == "GEOL":
                ds.intervals.append(
                    Interval(hole, vals["GEOL_TOP"], vals["GEOL_BASE"], row["GEOL_DESC"], line)
                )
            else:
                ds.spts.append(
                    SPT(hole, vals["ISPT_TOP"], vals.get("ISPT_NVAL"), line, row.get("ISPT_REP", ""))
                )
    return ds


def read_bc_csv(path: Path, depth_unit: str):
    """BC native fields, with caller-confirmed depth units. Coordinates are lon/lat."""
    if depth_unit not in LENGTHS:
        raise ValueError(f"Unsupported depth unit: {depth_unit}")
    ds = Dataset("EPSG:4326")
    factor = LENGTHS[depth_unit]
    seen = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if not reader.fieldnames or BC_FIELDS - set(reader.fieldnames):
            raise ValueError(f"BC CSV requires: {', '.join(sorted(BC_FIELDS))}")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Duplicate CSV headings")
        for row in reader:
            line = reader.line_num
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"line {line}: inconsistent CSV row width")
            site, name = row["BOREHOLE_SITE_ID"].strip(), row["BOREHOLE_NAME"].strip()
            hole = f"{site}:{name}" if site and name else ""
            vals = {
                f: number(ds, row[f], "CSV", line, hole, f)
                for f in ("LONGITUDE", "LATITUDE", "TOTAL_DEPTH", "FROM_UNIT_DEPTH", "TO_UNIT_DEPTH")
            }
            if any(v is None for v in vals.values()):
                continue
            x, y = vals["LONGITUDE"], vals["LATITUDE"]
            final = vals["TOTAL_DEPTH"] * factor
            metadata = (x, y, final)
            if hole in seen and seen[hole] != metadata:
                ds.issue(
                    "conflicting_location", "CSV", line, hole, "Coordinates or total depth differ across rows"
                )
            if hole not in seen:
                ds.holes.append(Hole(hole, x, y, final, line))
                seen[hole] = metadata
            ds.intervals.append(
                Interval(
                    hole,
                    vals["FROM_UNIT_DEPTH"] * factor,
                    vals["TO_UNIT_DEPTH"] * factor,
                    row["UNIT_DESCRIPTION"],
                    line,
                )
            )
    if not ds.holes:
        ds.issue("empty_dataset", "CSV", 0, "", "No readable boreholes")
    return ds
