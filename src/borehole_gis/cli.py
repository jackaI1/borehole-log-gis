import argparse
import csv
import json
import sys
from pathlib import Path

from fiona.errors import FionaError
from pyproj import CRS
from pyproj.exceptions import ProjError

from .export import export_tables, plot_logs, write_report
from .model import Dataset
from .readers import read_ags, read_bc_csv
from .validate import validate


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check borehole logs and export QGIS-ready files")
    parser.add_argument("input", type=Path)
    parser.add_argument("--format", choices=["ags", "bc-csv"], required=True)
    parser.add_argument("--crs", help="AGS coordinate CRS, e.g. EPSG:27700. Never inferred.")
    parser.add_argument("--depth-unit", choices=["m", "ft", "mm"], help="Required for BC CSV")
    parser.add_argument("--out", required=True, type=Path, help="New or empty output directory")
    parser.add_argument("--output-crs", default="EPSG:3005", help="Projected metre CRS for exported map")
    parser.add_argument("--tolerance", type=float, default=0.001, help="Depth comparison tolerance in metres")
    parser.add_argument("--strict", action="store_true", help="Also block export on warnings")
    args = parser.parse_args(argv)
    if args.format == "ags" and not args.crs:
        parser.error("--crs is required for AGS")
    if args.format == "bc-csv" and not args.depth_unit:
        parser.error("--depth-unit is required for CSV; the BC source documents metres")
    if not args.input.is_file():
        parser.error("input file does not exist")
    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        parser.error("--out must be a new or empty directory; existing results are preserved")
    args.out.mkdir(parents=True, exist_ok=True)
    options = {
        "format": args.format,
        "input_depth_unit": args.depth_unit,
        "output_crs": args.output_crs,
        "tolerance_m": args.tolerance,
        "strict": args.strict,
    }
    try:
        ds = (
            read_ags(args.input, args.crs)
            if args.format == "ags"
            else read_bc_csv(args.input, args.depth_unit)
        )
        validate(ds, args.tolerance)
    except (ValueError, csv.Error, OSError, ProjError) as exc:
        ds = Dataset(args.crs or "EPSG:4326")
        ds.issue("input_error", "FILE", 0, "", str(exc))
    try:
        output_crs = CRS.from_user_input(args.output_crs)
        if not output_crs.is_projected or abs(output_crs.axis_info[0].unit_conversion_factor - 1) > 1e-10:
            raise ValueError("Output CRS must be projected with metre units")
    except (ValueError, ProjError) as exc:
        ds.issue("output_crs", "EXPORT", 0, "", str(exc))
    report = write_report(ds, args.out, args.input, options)
    if ds.errors or (args.strict and ds.issues):
        print(f"Blocked: {report['errors']} errors, {report['warnings']} warnings. See {args.out}/issues.csv")
        return 2
    try:
        export_tables(ds, args.out, args.output_crs)
        plot_logs(ds, args.out)
    except (ValueError, OSError, ProjError, FionaError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 2
    (args.out / "manifest.json").write_text(
        json.dumps(
            {"files": sorted(str(p.relative_to(args.out)) for p in args.out.rglob("*") if p.is_file())},
            indent=2,
        )
        + "\n"
    )
    print(
        f"Exported {len(ds.holes)} boreholes, {len(ds.intervals)} intervals, {len(ds.spts)} SPT tests; "
        f"{report['warnings']} warnings. Results: {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
