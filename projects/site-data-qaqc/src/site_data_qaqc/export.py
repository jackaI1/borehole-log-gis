"""Portable database, QGIS layers and offline site reports."""

import hashlib
import json
import re
import sqlite3
import textwrap
from pathlib import Path

import geopandas as gpd
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from . import __version__

COLORS = {
    "exceeds": "#b33b32",
    "indeterminate": "#c58a19",
    "no_guideline": "#706685",
    "at_or_below": "#28766d",
    "below_limit": "#427caf",
}
RESULT_COLUMNS = [
    "record_id",
    "site_id",
    "borehole_id",
    "sample_id",
    "sample_date",
    "matrix",
    "analyte",
    "value",
    "detection_limit",
    "censored",
    "qualifier",
    "unit",
    "basis",
    "duplicate_of",
    "depth_top_m",
    "depth_bottom_m",
    "lithology",
    "x",
    "y",
    "source_crs",
    "longitude",
    "latitude",
    "guideline_id",
    "guideline_value",
    "screening",
    "exceedance_ratio",
]
AUDIT_COLUMNS = ["record_id", "source_file", "source_sha256", "source_row", "raw_json", "reason"]
ISSUE_COLUMNS = ["record_id", "severity", "code", "message"]
DUPLICATE_COLUMNS = [
    "duplicate_id",
    "original_id",
    "rpd",
    "status",
    "limit_percent",
    "dl_multiplier",
]
BOREHOLE_COLUMNS = [
    "record_id",
    "site_id",
    "borehole_id",
    "depth_top_m",
    "depth_bottom_m",
    "lithology",
    "sample_id",
    "sample_date",
    "matrix",
    "analyte",
    "result_display",
    "unit",
    "screening",
    "guideline_value",
    "source_file",
    "source_row",
]


def database(bundle, path):
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
        CREATE TABLE records (
            record_id INTEGER PRIMARY KEY, source_file TEXT NOT NULL, source_sha256 TEXT NOT NULL,
            source_row INTEGER NOT NULL, raw_json TEXT NOT NULL,
            disposition TEXT NOT NULL CHECK(disposition IN ('accepted','rejected')), reason TEXT);
        CREATE TABLE guidelines (
            guideline_id TEXT PRIMARY KEY, matrix TEXT NOT NULL, analyte TEXT NOT NULL,
            value REAL NOT NULL CHECK(value > 0), unit TEXT NOT NULL, context TEXT NOT NULL,
            source_url TEXT NOT NULL, checked_on TEXT NOT NULL, UNIQUE(matrix, analyte));
        CREATE TABLE results (
            record_id INTEGER PRIMARY KEY REFERENCES records(record_id),
            site_id TEXT NOT NULL, borehole_id TEXT NOT NULL, sample_id TEXT NOT NULL,
            sample_date TEXT NOT NULL, matrix TEXT NOT NULL, analyte TEXT NOT NULL,
            value REAL CHECK(value >= 0), detection_limit REAL CHECK(detection_limit > 0),
            censored INTEGER NOT NULL CHECK(censored IN (0,1)), qualifier TEXT, unit TEXT NOT NULL,
            basis TEXT, duplicate_of TEXT, depth_top_m REAL NOT NULL CHECK(depth_top_m >= 0),
            depth_bottom_m REAL NOT NULL CHECK(depth_bottom_m > depth_top_m), lithology TEXT,
            x REAL NOT NULL, y REAL NOT NULL, source_crs TEXT NOT NULL,
            longitude REAL NOT NULL, latitude REAL NOT NULL,
            guideline_id TEXT REFERENCES guidelines(guideline_id), guideline_value REAL,
            screening TEXT NOT NULL, exceedance_ratio REAL,
            CHECK((censored=1 AND value IS NULL AND detection_limit IS NOT NULL) OR
                  (censored=0 AND value IS NOT NULL)),
            UNIQUE(site_id, sample_id, sample_date, matrix, analyte));
        CREATE TABLE issues (
            record_id INTEGER NOT NULL REFERENCES records(record_id), severity TEXT NOT NULL,
            code TEXT NOT NULL, message TEXT NOT NULL);
        CREATE TABLE duplicates (
            duplicate_id INTEGER PRIMARY KEY REFERENCES results(record_id),
            original_id INTEGER REFERENCES results(record_id), rpd REAL,
            status TEXT NOT NULL, limit_percent REAL NOT NULL, dl_multiplier REAL NOT NULL);
        CREATE INDEX results_site ON results(site_id, borehole_id, depth_top_m);
        CREATE INDEX issues_record ON issues(record_id);
        CREATE VIEW exceedances AS SELECT * FROM results WHERE screening='exceeds';
        CREATE VIEW review_queue AS SELECT records.source_file, records.source_row, issues.*
            FROM issues JOIN records USING(record_id);
        """)
        records = [
            {k: r.get(k) for k in AUDIT_COLUMNS} | {"disposition": status}
            for name, status in (("results", "accepted"), ("rejected", "rejected"))
            for r in bundle[name]
        ]
        for table, rows, columns in [
            ("records", records, [*AUDIT_COLUMNS, "disposition"]),
            ("guidelines", bundle["guidelines"], list(bundle["guidelines"][0])),
            ("results", bundle["results"], RESULT_COLUMNS),
            ("issues", bundle["issues"], ISSUE_COLUMNS),
            ("duplicates", bundle["duplicates"], DUPLICATE_COLUMNS),
        ]:
            db.executemany(
                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                [[r.get(c) for c in columns] for r in rows],
            )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def site_slug(site):
    readable = re.sub(r"[^A-Za-z0-9_-]+", "-", site).strip("-")[:48] or "site"
    return readable + "-" + hashlib.sha256(site.encode()).hexdigest()[:8]


def make_points(gdf):
    columns = [
        "site_id",
        "sample_id",
        "sample_date",
        "matrix",
        "borehole_id",
        "depth_top_m",
        "depth_bottom_m",
    ]
    points = []
    for _, group in gdf.groupby(columns, sort=True):
        first = group.iloc[0]
        status = next(s for s in COLORS if s in set(group.screening))
        points.append(
            {
                **{c: first[c] for c in columns},
                "screening": status,
                "result_count": len(group),
                "exceedance_count": int((group.screening == "exceeds").sum()),
                "indeterminate_count": int((group.screening == "indeterminate").sum()),
                "geometry": first.geometry,
            }
        )
    return gpd.GeoDataFrame(
        points,
        columns=[
            *columns,
            "screening",
            "result_count",
            "exceedance_count",
            "indeterminate_count",
            "geometry",
        ],
        crs=gdf.crs,
    )


def site_figure(site, points, results, path):
    projected = points.to_crs(points.estimate_utm_crs() or "EPSG:3857")
    fig, (map_ax, log_ax) = plt.subplots(1, 2, figsize=(13, 7), layout="constrained")
    try:
        for status, color in reversed(list(COLORS.items())):
            subset = projected[projected.screening == status]
            if not subset.empty:
                subset.plot(ax=map_ax, color=color, markersize=65, edgecolor="white", zorder=3)
        # Label each borehole once. Multiple samples at one location deliberately overlap.
        for _, point in projected.drop_duplicates("borehole_id").iterrows():
            map_ax.annotate(
                point.borehole_id,
                (point.geometry.x, point.geometry.y),
                xytext=(6, 6),
                textcoords="offset points",
                fontsize=9,
            )
        map_ax.ticklabel_format(useOffset=False, style="plain")
        map_ax.set(
            xlabel="Easting (m)",
            ylabel="Northing (m)",
            title="Sampling locations | " + projected.crs.to_string(),
        )
        map_ax.margins(0.25)
        map_ax.grid(alpha=0.2)
        holes = sorted(results.borehole_id.unique())
        for i, hole in enumerate(holes):
            samples = results[results.borehole_id == hole]
            for (top, bottom), interval in samples.groupby(["depth_top_m", "depth_bottom_m"]):
                status = next(s for s in COLORS if s in set(interval.screening))
                log_ax.plot(
                    [i, i], [top, bottom], lw=12, color=COLORS[status], solid_capstyle="butt"
                )
                label = textwrap.fill(", ".join(sorted(set(interval.sample_id))), width=20)
                material = "/".join(sorted(set(interval.lithology) - {""}))
                log_ax.annotate(
                    label + ("\n" + material if material else ""),
                    (i, (top + bottom) / 2),
                    xytext=(10, 0),
                    textcoords="offset points",
                    fontsize=7,
                    va="center",
                )
        log_ax.set(
            xticks=range(len(holes)),
            xticklabels=holes,
            ylabel="Depth below ground (m)",
            title="Sampled intervals (not a geological interpretation)",
            xlim=(-0.5, len(holes) + 0.4),
        )
        log_ax.set_ylim(float(results.depth_bottom_m.max()) * 1.05, 0)
        log_ax.grid(axis="y", alpha=0.2)
        handles = [
            Line2D([0], [0], marker="o", linestyle="", color=color, label=status.replace("_", " "))
            for status, color in COLORS.items()
        ]
        fig.legend(handles=handles, loc="outside lower center", ncol=5, frameon=False)
        fig.suptitle(
            f"{site} | Synthetic site screening\nReview flagged records before interpretation",
            fontsize=14,
        )
        fig.savefig(path, dpi=150)
    finally:
        plt.close(fig)


def export(bundle, out: Path, policy):
    out.mkdir(parents=True, exist_ok=True)
    database(bundle, out / "site_data.sqlite")
    results = pd.DataFrame(
        bundle["results"], columns=[*RESULT_COLUMNS, "source_file", "source_row"]
    )
    results.to_csv(out / "standardized.csv", index=False)
    pd.DataFrame(bundle["rejected"], columns=AUDIT_COLUMNS).to_csv(
        out / "rejected.csv", index=False
    )
    pd.DataFrame(bundle["issues"], columns=ISSUE_COLUMNS).to_csv(out / "issues.csv", index=False)
    pd.DataFrame(bundle["duplicates"], columns=DUPLICATE_COLUMNS).to_csv(
        out / "duplicates.csv", index=False
    )
    gdf = gpd.GeoDataFrame(
        results, geometry=gpd.points_from_xy(results.longitude, results.latitude), crs=4326
    )
    points = make_points(gdf)
    gpkg = out / "samples.gpkg"
    for name, layer in (
        ("sample_results", gdf),
        ("sample_points", points),
        ("exceedances", gdf[gdf.screening == "exceeds"]),
    ):
        layer.to_file(gpkg, layer=name, driver="GPKG", engine="pyogrio")
    # GeoJSON is also available for viewers which do not read GeoPackage.
    points.to_file(out / "sample_points.geojson", driver="GeoJSON", engine="pyogrio")
    boreholes = results.copy()
    boreholes["result_display"] = [
        f"<{r.detection_limit:g}" if r.censored else f"{r.value:g}" for r in results.itertuples()
    ]
    boreholes = boreholes.sort_values(
        ["site_id", "borehole_id", "depth_top_m", "sample_date", "analyte"]
    )
    boreholes[BOREHOLE_COLUMNS].to_csv(out / "borehole_log.csv", index=False)
    sites = {}
    report_dir = out / "sites"
    report_dir.mkdir()
    for site in sorted(results.site_id.unique()):
        slug = site_slug(site)
        site_rows = boreholes[boreholes.site_id == site]
        site_rows[BOREHOLE_COLUMNS].to_csv(report_dir / f"{slug}.csv", index=False)
        if not site_rows.empty:
            site_figure(site, points[points.site_id == site], site_rows, report_dir / f"{slug}.png")
        sites[site] = {"table": f"sites/{slug}.csv", "figure": f"sites/{slug}.png"}
    counts = {k: len(bundle[k]) for k in ("results", "rejected", "issues", "duplicates")}
    summary = {
        "tool_version": __version__,
        "counts": counts,
        "screening": results.screening.value_counts().sort_index().to_dict(),
        "duplicate_status": pd.Series([r["status"] for r in bundle["duplicates"]], dtype=str)
        .value_counts()
        .to_dict(),
        "policy": policy,
        "sites": sites,
        "inputs": sorted(
            {
                (r["source_file"], r["source_sha256"])
                for name in ("results", "rejected")
                for r in bundle[name]
            }
        ),
        "note": "Synthetic demonstration. Groundwater uses drinking-water screening; soil assumes residential/parkland dry weight. No regulatory compliance determination.",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    return summary
