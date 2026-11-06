"""Small command line interface for fetching, screening and exporting QGIS maps."""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import geopandas as gpd

from .config import Config
from .data import fetch_data, sha256, validate_snapshot
from .screen import screen


def write_memos(ranked, output, config):
    directory = output / "memos"
    directory.mkdir()
    for site in ranked[ranked.eligible].head(config.top_sites).itertuples():
        filename = f"{site.rank:02d}-" + re.sub(r"[^A-Za-z0-9_-]", "_", site.site_id)[:80] + ".md"
        (directory / filename).write_text(
            f"# {site.site_id}: preliminary feasibility note\n\n"
            f"I would review this area next: rank {site.rank}, score {site.score:.2f}/100. "
            "This is a desktop shortlist, not an approval or a turbine design.\n\n"
            f"Of {site.area_ha:.1f} ha, {site.usable_ha:.1f} ha remains after "
            "the scenario setbacks "
            f"({site.constraint_fraction:.1%} constrained). The native wind pixels on that land "
            f"average {site.wind_ms:.2f} m/s at 100 m above ground; "
            f"{site.wind_coverage:.1%} of the sampled pixel centres have valid data "
            f"({site.wind_pixels} pixels). The shortest straight-line distance from the remaining "
            f"land to a mapped hydro line is {site.grid_distance_m:.0f} m.\n\n"
            f"The normalized components are wind {site.wind_component:.3f}, "
            f"grid {site.grid_component:.3f} and usable fraction {site.usable_component:.3f}. "
            f"Weights: {json.dumps(config.weights, sort_keys=True)}. "
            f"Scenario setbacks in metres: {json.dumps(config.setbacks_m, sort_keys=True)}.\n\n"
            "I would first check land tenure and whether the remaining land forms useful "
            "connected patches. I would then confirm line voltage, substation access and spare "
            "capacity with the grid operator, and measure wind on site. A short mapped distance "
            "does not establish a connection route or available capacity.\n\n"
            "The example candidates are study cells, not legal parcels. Ontario hydro-line "
            "data does not establish voltage or operating status. This screen omits homes and "
            "noise receptors, wetlands outside the water layer, wildlife, aviation, slope, "
            "Indigenous rights and consultation, municipal rules, wake losses and economics. "
            "The setback values are adjustable assumptions, not verified regulatory distances. "
            "No land acquisition, construction or financial decision follows from this rank.\n\n"
            "Sources and exact input hashes: `../run.json`. Source attribution: "
            "Ontario open data and Global Wind Atlas 4.0 (DTU, World Bank, Vortex, ESMAP).\n"
        )


def run(config, inputs, output, candidates_path=None):
    inputs, output = Path(inputs).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Output already exists; choose a new directory to preserve previous runs")
    candidate_path = (
        Path(candidates_path).resolve() if candidates_path else inputs / "candidates.geojson"
    )
    candidates = gpd.read_file(candidate_path)
    source_manifest = validate_snapshot(inputs, candidates, config)
    layers = {name: gpd.read_file(inputs / f"{name}.geojson") for name in config.setbacks_m}
    ranked, usable, buffers = screen(candidates, layers, inputs / "wind_100m.tif", config)
    output.mkdir(parents=True)
    ranked.drop(columns="geometry").to_csv(output / "ranked.csv", index=False, float_format="%.6f")
    gpkg = output / "screening.gpkg"
    ranked.to_file(gpkg, layer="candidates", driver="GPKG")
    usable[~usable.is_empty].to_file(gpkg, layer="usable_land", driver="GPKG")
    for name, frame in layers.items():
        frame.to_crs(config.analysis_crs).to_file(gpkg, layer=name, driver="GPKG")
    buffer_frame = gpd.GeoDataFrame(
        {"constraint": list(buffers)}, geometry=list(buffers.values()), crs=config.analysis_crs
    )
    buffer_frame[~buffer_frame.is_empty].to_file(gpkg, layer="setbacks", driver="GPKG")
    shutil.copyfile(inputs / "wind_100m.tif", output / "wind_100m.tif")
    manifest = {
        "config": config.dump(),
        "candidate_count": len(ranked),
        "eligible_count": int(ranked.eligible.sum()),
        "candidate_sha256": sha256(candidate_path),
        "inputs": {p.name: sha256(p) for p in sorted(inputs.iterdir()) if p.is_file()},
        "source_manifest": source_manifest,
    }
    (output / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")
    write_memos(ranked, output, config)
    print(
        json.dumps(
            {
                "candidates": len(ranked),
                "eligible": int(ranked.eligible.sum()),
                "output": str(output),
            },
            indent=2,
        )
    )
    return ranked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="Refresh an Ontario snapshot into an empty folder")
    fetch.add_argument("--config", default="config/bruce.json")
    fetch.add_argument("--output", required=True)
    analyze = sub.add_parser("run", help="Rank candidates and write maps-ready results")
    analyze.add_argument("--config", default="config/bruce.json")
    analyze.add_argument("--inputs", default="data/ontario")
    analyze.add_argument("--output", default="outputs/bruce")
    analyze.add_argument("--candidates", help="Optional polygon file with a unique site_id and CRS")
    qgis = sub.add_parser("qgis", help="Build a styled QGIS project and A4 printable map")
    qgis.add_argument("directory")
    qgis.add_argument(
        "--python", default="python3", help="Python interpreter with PyQGIS installed"
    )
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            fetch_data(Config.load(args.config), args.output)
        elif args.command == "run":
            run(Config.load(args.config), args.inputs, args.output, args.candidates)
        else:
            subprocess.run(
                [args.python, str(Path(__file__).with_name("qgis_export.py")), args.directory],
                check=True,
            )
    except (ValueError, OSError) as error:
        parser.exit(2, f"wind-screen: {error}\n")
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)


if __name__ == "__main__":
    main()
