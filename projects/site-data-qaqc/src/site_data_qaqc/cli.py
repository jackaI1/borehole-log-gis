"""Batch command: produce reviewable outputs, then optionally fail on QA findings."""

import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path

from .export import export
from .ingest import InputError, read_table
from .qaqc import assess


def run(inputs, output, crs="EPSG:26917", encoding="utf-8-sig", rpd_limit=30, dl_multiplier=5):
    output = Path(output).absolute()
    if output.exists():
        raise InputError(f"output already exists: {output}; choose a fresh directory")
    raw = []
    for path in inputs:
        raw.extend(read_table(Path(path), encoding))
    if not raw:
        raise InputError("no data records found")
    bundle = assess(raw, crs, rpd_limit, dl_multiplier)
    # A complete, empty review package is useful even when every record is rejected.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".site-qaqc-", dir=output.parent) as tmp:
        stage = Path(tmp) / "package"
        summary = export(
            bundle,
            stage,
            {"default_crs": crs, "rpd_limit_percent": rpd_limit, "dl_multiplier": dl_multiplier},
        )
        os.rename(stage, output)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Standardize and screen synthetic groundwater/soil tables"
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="long-format CSV/TSV tables")
    parser.add_argument("--out", required=True, type=Path, help="new output directory")
    parser.add_argument(
        "--crs", default="EPSG:26917", help="coordinate system when a row omits crs"
    )
    parser.add_argument("--encoding", default="utf-8-sig", help="input encoding, e.g. cp1252")
    parser.add_argument("--rpd-limit", type=float, default=30)
    parser.add_argument("--dl-multiplier", type=float, default=5)
    parser.add_argument(
        "--strict", action="store_true", help="exit 2 after export if any QA issue exists"
    )
    args = parser.parse_args(argv)
    try:
        summary = run(
            args.inputs, args.out, args.crs, args.encoding, args.rpd_limit, args.dl_multiplier
        )
    except (InputError, ValueError, OSError, csv.Error) as exc:
        print(f"site-qaqc: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"output": str(args.out), **summary["counts"], "screening": summary["screening"]},
            indent=2,
        )
    )
    return 2 if args.strict and summary["counts"]["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
