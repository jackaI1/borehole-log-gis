"""Run generated HEC-RAS models on a Windows runner with HEC-RAS 6.6 installed."""

import argparse
import json
from pathlib import Path

from borehole_gis.river import run_workflow

parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
print(json.dumps(run_workflow(args.out), indent=2))
