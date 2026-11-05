# Public data and reproducibility

## BC logs

Source: Province of British Columbia, [Borehole Log Lithology Public View](https://catalogue.data.gov.bc.ca/dataset/1956d690-b196-4be2-b82b-263491326a28), feature class `WHSE_WASTE.SITE_BOREHOLE_LITHOLOGY_SVW`. The catalogue's column comments specify metres for TOTAL_DEPTH, FROM_UNIT_DEPTH and TO_UNIT_DEPTH; LATITUDE and LONGITUDE are decimal degrees. The ArcGIS geometry is BC Albers, but the sample uses the latitude/longitude attributes, not that geometry.

Contains information licensed under the [Open Government Licence - British Columbia](https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc). Neither the Province nor BGS endorses this project. Public observations can contain errors and should be checked against original records before interpretation.

The refresh script requests complete records for fixed site IDs 13, 17, 21 and 28, ordered by site, borehole name and top depth. It selects nine public log fields, leaving out contacts, ownership and property records. It checks the transfer-limit flag so it will not silently save a truncated log. Source cells are not rounded or repaired. JSON provenance records the exact query, UTC retrieval time, row count and SHA-256. A refresh can legitimately change results if the upstream dataset changes.

```sh
uv run python scripts/fetch_bc_sample.py
```

The included sample has four holes, 17 layers and one gap of 1.0 m (4.9 to 5.9 m). It contains no SPT observations. The SPT column in its plots therefore says “No SPT data”.

## BGS AGS excerpt

Source: [BGS pyagsapi public example files](https://britishgeologicalsurvey.github.io/pyagsapi/#example-files), file `19-1316 - 2020-03-02 1554 - Final - 1.ags`, pinned to commit `b223b48803d8feb07897ae468b455842cbf1790d`.

Contains data supplied by Natural Environment Research Council. Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

The script extracts BH01's original coordinates, final depth, all six geological intervals and all five SPT records. Numeric and text observation cells remain unchanged, including blank N-values and source test remarks. The source uses British National Grid coordinates (`EPSG:27700`). The excerpt omits unrelated groups, project contacts and other fields. It writes fresh PROJ, TRAN, ABBR, TYPE and UNIT groups describing the excerpt. These administration records are sample metadata, not original project information or a claim of full AGS compliance. Provenance includes the original file's SHA-256, the excerpt's SHA-256, the pinned source URL and the transformation notes.

```sh
uv run python scripts/fetch_ags_sample.py
```

Tests use committed samples offline. Neither fetching script runs automatically during tests or normal use. Do not use a current upstream response to overwrite expected results just to make a test pass.
