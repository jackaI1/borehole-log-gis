"""Validated screening assumptions; setbacks are scenarios, not legal rules."""

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pyproj import CRS


@dataclass(frozen=True)
class Config:
    name: str = "Ontario wind screening"
    analysis_crs: str = "EPSG:26917"
    bbox_wgs84: tuple = (-81.65, 44.0, -81.25, 44.3)
    cell_size_m: float = 2000
    setbacks_m: dict = field(
        default_factory=lambda: {
            "roads": 100,
            "transmission": 150,
            "water": 120,
            "protected": 300,
        }
    )
    wind_floor_ms: float = 5
    wind_ceiling_ms: float = 9
    grid_limit_m: float = 20000
    min_usable_ha: float = 20
    max_constraint_fraction: float = 0.5
    min_wind_coverage: float = 0.95
    weights: dict = field(default_factory=lambda: {"wind": 0.5, "grid": 0.3, "usable": 0.2})
    top_sites: int = 3

    def __post_init__(self):
        crs = CRS(self.analysis_crs)
        if not crs.is_projected or any(a.unit_name != "metre" for a in crs.axis_info):
            raise ValueError("analysis_crs must be projected with metre units")
        if crs.to_epsg() in {3857, 3395}:
            raise ValueError("Use a local metric CRS, not a Mercator display projection")
        numeric = [
            self.cell_size_m,
            self.wind_floor_ms,
            self.wind_ceiling_ms,
            self.grid_limit_m,
            self.min_usable_ha,
            self.max_constraint_fraction,
            self.min_wind_coverage,
            *self.weights.values(),
            *self.setbacks_m.values(),
        ]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in numeric):
            raise ValueError("All numeric assumptions must be finite")
        if min(self.cell_size_m, self.grid_limit_m, self.min_usable_ha) <= 0:
            raise ValueError("Cell size, grid limit and usable area must be positive")
        if self.wind_floor_ms < 0 or self.wind_ceiling_ms <= self.wind_floor_ms:
            raise ValueError("Wind ceiling must exceed a non-negative floor")
        if set(self.setbacks_m) != {"roads", "transmission", "water", "protected"}:
            raise ValueError("Specify roads, transmission, water and protected setbacks")
        if min(self.setbacks_m.values()) < 0:
            raise ValueError("Setbacks cannot be negative")
        if set(self.weights) != {"wind", "grid", "usable"} or min(self.weights.values()) < 0:
            raise ValueError("Weights must be non-negative for wind, grid and usable")
        if not math.isclose(sum(self.weights.values()), 1, abs_tol=1e-9):
            raise ValueError("Weights must sum to one")
        if not 0 <= self.max_constraint_fraction <= 1 or not 0 < self.min_wind_coverage <= 1:
            raise ValueError("Overlap must be in [0,1] and coverage in (0,1]")
        if not isinstance(self.top_sites, int) or self.top_sites < 1:
            raise ValueError("top_sites must be a positive integer")
        if len(self.bbox_wgs84) != 4:
            raise ValueError("bbox_wgs84 needs west, south, east, north")
        west, south, east, north = self.bbox_wgs84
        if not (-95.2 <= west < east <= -74.0 and 41.6 <= south < north <= 57):
            raise ValueError("Study box must be within Ontario's geographic bounds")
        area = crs.area_of_use
        if area and not (
            area.west <= west < east <= area.east and area.south <= south < north <= area.north
        ):
            raise ValueError("Study box is outside the analysis CRS area of use")

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text()))

    def dump(self):
        return asdict(self)
