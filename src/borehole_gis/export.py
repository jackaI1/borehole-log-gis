import csv
import hashlib
import json
import textwrap
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import fiona
from pyproj import CRS, Transformer


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_report(ds, out, source, options):
    report = {
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "input_crs": ds.crs,
        "depth_unit": "m",
        "options": options,
        "holes": len(ds.holes),
        "intervals": len(ds.intervals),
        "spt_tests": len(ds.spts),
        "errors": ds.errors,
        "warnings": sum(i.severity == "warning" for i in ds.issues),
        "issues": [asdict(i) for i in ds.issues],
    }
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_csv(
        out / "issues.csv", ["severity", "code", "group", "row", "hole_id", "message"], report["issues"]
    )
    return report


def summaries(ds):
    """Summarize each hole and each exact source description, without inferring soil classes."""
    rows = []
    for h in ds.holes:
        grouped = defaultdict(list)
        for layer in ds.intervals:
            if layer.hole_id == h.id:
                grouped[layer.description].append(layer)
        for description, layers in grouped.items():
            rows.append(
                {
                    "hole_id": h.id,
                    "description": description,
                    "interval_count": len(layers),
                    "top_m": min(x.top for x in layers),
                    "base_m": max(x.base for x in layers),
                    "thickness_m": sum(x.base - x.top for x in layers),
                }
            )
    return rows


def export_tables(ds, out, output_crs):
    if ds.errors:
        raise ValueError("Resolve validation errors before exporting")
    crs = CRS.from_user_input(output_crs)
    if not crs.is_projected or abs(crs.axis_info[0].unit_conversion_factor - 1) > 1e-10:
        raise ValueError("Output CRS must be projected with metre units")
    transformer = Transformer.from_crs(ds.crs, crs, always_xy=True)
    # Preflight every point before opening an output file.
    points = [transformer.transform(h.x, h.y, errcheck=True) for h in ds.holes]
    schema = {
        "geometry": "Point",
        "properties": {
            "hole_id": "str",
            "final_m": "float",
            "logged_m": "float",
            "gap_m": "float",
            "spt_count": "int",
            "warnings": "int",
        },
    }
    with fiona.open(
        out / "boreholes.gpkg", "w", driver="GPKG", layer="boreholes", crs_wkt=crs.to_wkt(), schema=schema
    ) as sink:
        for h, (x, y) in zip(ds.holes, points):
            logged = sum(i.base - i.top for i in ds.intervals if i.hole_id == h.id)
            sink.write(
                {
                    "geometry": {"type": "Point", "coordinates": (x, y)},
                    "properties": {
                        "hole_id": h.id,
                        "final_m": h.final_depth,
                        "logged_m": logged,
                        "gap_m": max(0.0, h.final_depth - logged),
                        "spt_count": sum(s.hole_id == h.id for s in ds.spts),
                        "warnings": sum(i.hole_id == h.id and i.severity == "warning" for i in ds.issues),
                    },
                }
            )
    write_csv(
        out / "stratigraphy.csv",
        ["hole_id", "description", "interval_count", "top_m", "base_m", "thickness_m"],
        summaries(ds),
    )
    write_csv(
        out / "intervals.csv",
        ["hole_id", "top", "base", "description", "row"],
        [asdict(x) for x in ds.intervals],
    )
    write_csv(out / "spt.csv", ["hole_id", "depth", "n", "row", "remark"], [asdict(s) for s in ds.spts])


def plot_logs(ds, out):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    log_dir = out / "logs"
    log_dir.mkdir()
    index = []
    for h in ds.holes:
        layers = sorted((i for i in ds.intervals if i.hole_id == h.id), key=lambda i: i.top)
        tests = sorted((s for s in ds.spts if s.hole_id == h.id), key=lambda s: s.depth)
        # Safe filenames, even when a source ID includes slashes or other path characters.
        name = hashlib.sha256(h.id.encode()).hexdigest()[:16] + ".png"
        labels = [
            f"{i + 1}. {layer.top:g} to {layer.base:g} m\n" + textwrap.fill(layer.description, 49)
            for i, layer in enumerate(layers)
        ]
        line_counts = [label.count("\n") + 2 for label in labels]
        total_lines = sum(line_counts)
        fig, (soil, descriptions, spt) = plt.subplots(
            1, 3, figsize=(11, max(6, total_lines * 0.22)), gridspec_kw={"width_ratios": [0.8, 3, 1.3]}
        )
        spt.sharey(soil)
        descriptions.set_axis_off()
        descriptions.set_title("Soil / rock descriptions", loc="left")
        cursor = 1.0
        for label, count in zip(labels, line_counts):
            descriptions.text(0, cursor, label, va="top", fontsize=9, transform=descriptions.transAxes)
            cursor -= count / total_lines
        try:
            for i, layer in enumerate(layers):
                soil.add_patch(
                    Rectangle(
                        (0, layer.top),
                        1,
                        layer.base - layer.top,
                        facecolor=("#e9e1c6" if i % 2 == 0 else "#d3dfdc"),
                        edgecolor="#53676a",
                        linewidth=0.7,
                    )
                )
                soil.text(0.5, (layer.top + layer.base) / 2, str(i + 1), fontsize=8, va="center", ha="center")
            soil.set(
                xlim=(0, 1),
                ylim=(h.final_depth, 0),
                ylabel="Depth below ground (m)",
                title="Layers",
            )
            soil.set_xticks([])
            numeric = [s for s in tests if s.n is not None]
            for test in tests:
                if test.n is None:
                    spt.text(
                        0.03,
                        test.depth,
                        "N unavailable",
                        transform=spt.get_yaxis_transform(),
                        fontsize=7,
                        va="bottom",
                    )
            if numeric:
                spt.scatter([s.n for s in numeric], [s.depth for s in numeric], c="#b55832", zorder=3)
                for s in numeric:
                    spt.annotate(f" {s.n:g}", (s.n, s.depth), fontsize=8)
                spt.set_xlim(0, max(50, max(s.n for s in numeric) * 1.3))
            else:
                spt.text(
                    0.5,
                    0.5,
                    ("No numeric SPT N" if tests else "No SPT data"),
                    transform=spt.transAxes,
                    ha="center",
                )
                spt.set_xlim(0, 50)
            spt.set(xlabel="Uncorrected N (blows)", title="SPT tests")
            spt.grid(alpha=0.25)
            fig.suptitle(f"Borehole {h.id} | final depth {h.final_depth:g} m")
            fig.text(
                0.05,
                0.015,
                "Blank depths are unlogged. Descriptions and N-values are source observations.",
                fontsize=8,
            )
            fig.tight_layout(rect=(0, 0.04, 1, 0.95))
            fig.savefig(log_dir / name, dpi=150)
        finally:
            plt.close(fig)
        index.append({"hole_id": h.id, "file": str(Path("logs") / name)})
    write_csv(out / "logs.csv", ["hole_id", "file"], index)
