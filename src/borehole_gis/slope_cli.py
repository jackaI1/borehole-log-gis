"""Command-line slope stability check on a parsed borehole log."""

import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Find the lowest Bishop factor of safety over circular slip surfaces"
    )
    parser.add_argument('--log', required=True, type=Path, help='Borehole log (AGS or BC CSV)')
    parser.add_argument('--format', choices=['ags', 'bc-csv'], required=True)
    parser.add_argument('--crs', help='AGS coordinate CRS, e.g. EPSG:27700. Never inferred.')
    parser.add_argument('--depth-unit', choices=['m', 'ft', 'mm'], help='Required for BC CSV')
    parser.add_argument('--strengths', required=True, type=Path, help='Strength table CSV')
    parser.add_argument('--section', required=True, type=Path, help='Slope section JSON')
    parser.add_argument('--out', required=True, type=Path, help='New or empty output directory')
    parser.add_argument('--slices', type=int, default=30, help='Slices per slip surface')
    args = parser.parse_args(argv)
    if args.format == 'ags' and not args.crs:
        parser.error('--crs is required for AGS')
    if args.format == 'bc-csv' and not args.depth_unit:
        parser.error('--depth-unit is required for CSV; the BC source documents metres')
    if args.slices < 5:
        parser.error('--slices must be at least 5')
    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        parser.error('--out must be a new or empty directory; existing results are preserved')

    from .readers import read_ags, read_bc_csv
    from .slope import analyse
    from .validate import validate

    try:
        dataset = (
            read_ags(args.log, args.crs) if args.format == 'ags' else read_bc_csv(args.log, args.depth_unit)
        )
        validate(dataset)
        if dataset.errors:
            print(f'Log has {dataset.errors} errors; fix them first (see borehole-gis issues.csv)')
            return 2
        report = analyse(dataset, args.strengths, args.section, args.out, slices=args.slices)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'Slope check failed: {exc}', file=sys.stderr)
        return 2
    print(json.dumps({k: report[k] for k in ('status', 'fos', 'critical_surface', 'surfaces')}, indent=2))
    if report['status'] != 'complete':
        print(f'Partial: {report["surfaces_not_evaluated_missing_strength"]} surfaces not evaluated. '
              f'Missing strength: {", ".join(report["missing_strength_layers"])}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
