"""Depth continuity is measured from ground surface to declared final depth."""

import math
from collections import defaultdict

from pyproj import Transformer
from pyproj.exceptions import ProjError


def validate(ds, tolerance=0.001):
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Depth tolerance must be finite and nonnegative")
    holes = {}
    transform = Transformer.from_crs(ds.crs, "EPSG:4326", always_xy=True)
    for h in ds.holes:
        if not h.id:
            ds.issue("blank_id", "LOCA", h.row, h.id, "Borehole ID is blank")
        if h.id in holes:
            ds.issue("duplicate_hole", "LOCA", h.row, h.id, "Duplicate borehole ID")
        holes[h.id] = h
        if h.final_depth <= 0:
            ds.issue("final_depth", "LOCA", h.row, h.id, "Final depth must be positive")
        try:
            lon, lat = transform.transform(h.x, h.y, errcheck=True)
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError
        except (ValueError, ProjError):
            ds.issue(
                "coordinate_range",
                "LOCA",
                h.row,
                h.id,
                "Coordinates cannot be placed on Earth in declared CRS",
            )
    by_hole = defaultdict(list)
    for layer in ds.intervals:
        if layer.hole_id not in holes:
            ds.issue("orphan_interval", "GEOL", layer.row, layer.hole_id, "No matching borehole")
            continue
        if layer.top < 0 or layer.base <= layer.top:
            ds.issue("invalid_interval", "GEOL", layer.row, layer.hole_id, "Require 0 <= top < base")
            continue
        if layer.base > holes[layer.hole_id].final_depth + tolerance:
            ds.issue("beyond_final_depth", "GEOL", layer.row, layer.hole_id, "Interval exceeds final depth")
        if not layer.description.strip():
            ds.issue("empty_description", "GEOL", layer.row, layer.hole_id, "No soil description", "warning")
        by_hole[layer.hole_id].append(layer)
    for hole_id, h in holes.items():
        cursor = 0.0
        layers = sorted(by_hole[hole_id], key=lambda layer: (layer.top, layer.base))
        if not layers:
            ds.issue("missing_log", "GEOL", h.row, hole_id, "No valid geological intervals")
            continue
        for layer in layers:
            if layer.top > cursor + tolerance:
                ds.issue(
                    "gap",
                    "GEOL",
                    layer.row,
                    hole_id,
                    f"Unlogged depth {cursor:g} to {layer.top:g} m",
                    "warning",
                )
            elif layer.top < cursor - tolerance:
                ds.issue(
                    "overlap",
                    "GEOL",
                    layer.row,
                    hole_id,
                    f"Interval starts at {layer.top:g} m before previous coverage ends at {cursor:g} m",
                )
            # A nested interval must not shorten coverage and create a false gap.
            cursor = max(cursor, layer.base)
        if cursor < h.final_depth - tolerance:
            ds.issue(
                "gap", "GEOL", h.row, hole_id, f"Unlogged depth {cursor:g} to {h.final_depth:g} m", "warning"
            )
    seen_spts = set()
    for spt in ds.spts:
        if spt.hole_id not in holes:
            ds.issue("orphan_spt", "ISPT", spt.row, spt.hole_id, "No matching borehole")
            continue
        if spt.depth < 0 or spt.depth > holes[spt.hole_id].final_depth + tolerance:
            ds.issue("spt_depth", "ISPT", spt.row, spt.hole_id, "Test depth is outside borehole")
        if spt.n is not None and (spt.n < 0 or not float(spt.n).is_integer()):
            ds.issue("spt_n", "ISPT", spt.row, spt.hole_id, "SPT N must be a nonnegative integer")
        key = (spt.hole_id, spt.depth)
        if key in seen_spts:
            ds.issue("duplicate_spt", "ISPT", spt.row, spt.hole_id, "Duplicate test depth")
        seen_spts.add(key)
    return ds
