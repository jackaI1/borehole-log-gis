# Running another comparison

I start with the included snapshot before changing settings. `uv sync --extra dev --locked` installs the locked packages. `uv run wind-screen --help` lists the three commands.

## Outputs

`run --output <new-folder>` writes a complete run:

| File | What I use it for |
| --- | --- |
| `ranked.csv` | Sort passing candidates and inspect rejection reasons |
| `screening.gpkg` | Candidate polygons, remaining land, source features and setback zones |
| `wind_100m.tif` | The same wind values used in the calculation |
| `run.json` | Input hashes, original public-source manifest and all settings |
| `memos/*.md` | A brief assessment of each top passing site, including missing checks |

`qgis <run-folder> --python <QGIS-Python>` adds `wind-screening.qgs`, its style attachment, `screening-map.pdf` and `screening-map.png`. Keep the entire run folder together. The eight QGIS layers can be toggled separately; the candidate attribute table includes the calculated scores. Turn off candidate fills and setback zones to inspect the underlying wind raster. The saved A4 landscape layout includes a scale bar, grid-north note, legend, scenario settings and source credit.

## QGIS's Python

A normal `pip install qgis` is not the QGIS desktop runtime. I use an interpreter installed with QGIS. On Linux:

```sh
sudo apt-get update
sudo apt-get install python3-qgis fonts-dejavu-core
uv run wind-screen qgis outputs/my-screen --python /usr/bin/python3
/usr/bin/python3 scripts/check_qgis.py outputs/my-screen
```

For macOS or Linux I can also install [micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html) and use the included environment file:

```sh
micromamba create -y -f environment-qgis.yml
micromamba run -n wind-screen-qgis python -c 'import sys; print(sys.executable)'
# Use the printed absolute interpreter path below.
uv run wind-screen qgis outputs/my-screen --python /absolute/path/to/env/bin/python
```

The exporter and checker add Conda's `share/qgis/python` binding directory automatically and run without a GUI window. On Windows, use the QGIS/OSGeo4W Python environment to run `src/wind_screen/qgis_export.py outputs/my-screen` directly. I validated the example with QGIS 3.44 and CI also checks the Ubuntu-packaged QGIS runtime.

## Parcel inputs

The included candidate file is generated from 2 km squares clipped to the study box. It is not an ownership dataset. I can replace it using `--candidates path/to/parcels.geojson`. A vector file must have:

- A known source CRS (coordinate reference system), valid polygon or multipolygon geometry and a unique non-empty `site_id`.
- Coordinates inside the configured analysis CRS's area of use.
- Coverage by the source layers and wind raster. Small parcels with no native pixel centres cannot receive a wind estimate.

The program copies no owner information into the output: it keeps `site_id` and calculated attributes only. I still choose a non-personal identifier. If I supply my own context layers, I place them in an input folder named `roads.geojson`, `transmission.geojson`, `water.geojson`, `protected.geojson` and `wind_100m.tif`. Empty roads, water or park files must still record their CRS; transmission must contain at least one line. Wind must be a north-up, single-resource raster in m/s, with CRS and nodata metadata. Raster scale and offset are respected. I use a suitable local projected CRS with metre units, not Web Mercator.

## Refreshing public sources

I change `bbox_wgs84` to west, south, east, north in longitude and latitude and select a local analysis CRS. Then:

```sh
uv run wind-screen fetch --config my-config.json --output data/new-snapshot
uv run wind-screen run --config my-config.json --inputs data/new-snapshot --output outputs/new-run
```

`fetch` uses a grid-distance halo around transmission and a setback halo around the other features, plus 1 km of extra margin. It downloads feature IDs first, then small batches, and fails if a batch is incomplete. Rasterio reads only the requested native-grid window from the public Canada GeoTIFF using HTTP byte ranges. It never synthesizes replacement wind values after a service failure. A fetch requires an empty directory; a failed partial fetch can be inspected and retried in another empty folder.

The snapshot manifest records URLs, source filters, query bounds, download time and SHA-256 hashes. `run` verifies those hashes and checks query coverage against the candidates and new settings. Increasing a buffer or grid limit far enough requires a fresh download. The wind raster must still cover at least the configured fraction of each candidate's remaining pixels. Custom inputs without `sources.json` are allowed, but their completeness and attribution are my responsibility; every file is still hashed in `run.json`.
