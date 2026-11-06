# wind-site-screening

I built a wind-site screening tool to learn how the underlying idea works. This is a learning project.

## Run my example

I use Python 3.11 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/) to install the Python packages. The small public-data snapshot is included, so this run needs no data account or live map service.

```sh
uv sync --extra dev --locked
uv run wind-screen run --output outputs/my-screen
```

That writes `ranked.csv`, `screening.gpkg` (one file containing the map layers), `wind_100m.tif`, `run.json` and three Markdown feasibility notes in `memos/`. The table includes the wind speed, distance to a mapped hydro line, fraction of land removed, each score component and any reason a cell was excluded. Excluded cells have no score or rank. Each note explains the numbers and the next questions I would investigate.

To generate the styled QGIS project, PDF and map preview for a new run, I use a Python interpreter that includes QGIS. This is separate from the small Python environment above:

```sh
# With micromamba installed, this provides QGIS's Python bindings.
micromamba create -y -f environment-qgis.yml
uv run wind-screen qgis outputs/my-screen \
  --python "$HOME/micromamba/envs/wind-screen-qgis/bin/python"
```

The environment location depends on the micromamba installation. On Ubuntu, `sudo apt-get install python3-qgis fonts-dejavu-core` provides `/usr/bin/python3` for the `--python` argument. I explain other setups and the map checks in [the usage guide](docs/usage.md).

## Change the comparison

I copy [`config/bruce.json`](config/bruce.json), edit the assumptions, then pass `--config my-config.json` to the commands. My defaults leave 100 m around roads, 150 m around hydro lines, 120 m around water and 300 m around provincial parks. These are **screening assumptions I chose**, not verified regulatory setbacks.

```sh
uv run wind-screen run --config my-config.json --output outputs/another-scenario
# Optional: use your own polygon file with a unique site_id and a recorded coordinate system.
uv run wind-screen run --candidates my-parcels.geojson --output outputs/my-parcels
# Refresh public data into a new folder for a new study area or wider setbacks.
uv run wind-screen fetch --config my-config.json --output data/new-snapshot
uv run wind-screen run --config my-config.json --inputs data/new-snapshot \
  --output outputs/new-area
```

I keep previous runs intact: output folders must be new. The snapshot includes extra data outside the study area so features just across its edge still count. The tool checks input hashes and refuses a scenario that extends beyond that coverage. For other Ontario locations, I also change the local coordinate system, which tells the program how map coordinates translate to metres.

## What the score means

I use GeoPandas for the shapes and rasterio for the wind raster, a grid of wind-speed values. I transform the vector layers into NAD83 / UTM zone 17N (`EPSG:26917`) before measuring distances and areas. Overlapping setbacks count only once. Wind values are averaged at the native pixel centres on the land left after setbacks; missing values and pixels outside the raster reduce coverage.

The default score is out of 100: 50% wind resource, 30% proximity to a mapped hydro line and 20% fraction of land outside setbacks. Wind increases from zero credit at 5 m/s to full credit at 9 m/s. Grid distance decreases from full credit at zero metres to zero at 20 km. I exclude areas with less than 20 usable hectares, more than 50% constrained land, less than 95% wind coverage, wind below 5 m/s or a line farther than 20 km. The weights, thresholds and shortlist length are configurable. [The calculation notes](docs/method.md) give the formulas and edge cases.

## Data and limits

I use public Ontario roads, hydro lines, water bodies and regulated provincial parks, together with an Ontario crop of the Global Wind Atlas 4.0 wind-speed raster at 100 m height. The example was downloaded on November 5, 2026. [Sources, licences, attribution and download details](docs/data.md) accompany a machine-readable [`sources.json`](data/ontario/sources.json) with exact file hashes.

The example areas are generated study cells. I can screen supplied land parcels, but I have not checked ownership or land availability. The Ontario hydro-line layer is an early grid-distance proxy: it does not establish voltage, present operating status, connection access or spare capacity, and its catalogue describes older source records. A nearby line is not a connection offer. Wind is modelled, not measured at these sites. This screen also leaves out homes and noise, aviation, wildlife, some wetlands, slope, Indigenous rights and consultation, municipal requirements, turbine spacing and economics. I would resolve those before treating any area as feasible.

## Tests and limits

There are 4 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `wind-site-screening-ci.yml`.
