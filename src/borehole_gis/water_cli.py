"""File-based commands for pumping and pressure-zone analysis."""

import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description='Analyze pumping observations or check an EPANET pressure zone')
    sub = parser.add_subparsers(dest='command', required=True)
    pumping = sub.add_parser('pumping', help='Fit observations with explicit metadata')
    pumping.add_argument('--csv', type=Path, required=True)
    pumping.add_argument('--metadata', type=Path, required=True)
    pumping.add_argument('--out', type=Path, required=True)
    demo = sub.add_parser('water-demo', help='Write a synthetic 24-hour EPANET model')
    demo.add_argument('--inp', type=Path, required=True)
    water = sub.add_parser('water', help='Run a 24-hour EPANET model and fire scenarios')
    water.add_argument('--inp', type=Path, required=True)
    water.add_argument('--out', type=Path, required=True)
    water.add_argument('--criteria', type=Path, help='JSON fields of Criteria, thresholds in metres and seconds')
    water.add_argument('--fire-flow-l-s', type=float, default=15)
    water.add_argument('--hydrants', nargs='+')
    args = parser.parse_args(argv)
    try:
        if args.command == 'pumping':
            from .pumping import analyze
            report = analyze(args.csv, json.loads(args.metadata.read_text()), args.out)
        elif args.command == 'water-demo':
            from .water_network import create_demo
            print(create_demo(args.inp))
            return 0
        else:
            from .water_network import Criteria, check_network
            criteria = Criteria(**json.loads(args.criteria.read_text())) if args.criteria else Criteria()
            report = check_network(args.inp, args.out, criteria, args.fire_flow_l_s / 1000, args.hydrants)
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        print(f'Analysis failed: {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
