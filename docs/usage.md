# Inputs, outputs and checking limits

## BC CSV

Use the full native field names, not shapefile-truncated names:

```text
BOREHOLE_SITE_ID,BOREHOLE_NAME,LATITUDE,LONGITUDE,TOTAL_DEPTH,FROM_UNIT_DEPTH,TO_UNIT_DEPTH,UNIT_DESCRIPTION
```

One row represents one layer. A borehole key combines site ID and borehole name, so separate holes at the same site do not collapse together. All rows for that key must agree on coordinates and total depth. Extra fields are ignored. Blank or nonfinite numeric cells are errors. Latitude and longitude are in decimal degrees, in that order in the CSV; transformations always use longitude as x. This adapter is specific to this BC schema, not every provincial CSV.

`--depth-unit m|ft|mm` is mandatory. The original BC source specifies metres; feet and millimetres are useful for explicitly converted copies. Do not select another unit to make a failed check pass.

## AGS4

[AGS 4.1.1 specification](https://www.ags.org.uk/content/uploads/2022/02/AGS4-v-4.1.1-2022.pdf) describes the complete exchange format. This project checks a useful subset:

| Group | Fields read | Purpose |
| --- | --- | --- |
| PROJ, TRAN, ABBR, TYPE, UNIT | Presence, nonempty data, metadata; UNIT_UNIT and TYPE_TYPE definitions | Project / transfer / abbreviation / dictionary context |
| LOCA | LOCA_ID, LOCA_NATE, LOCA_NATN, LOCA_FDEP | Hole coordinates and final depth |
| GEOL | LOCA_ID, GEOL_TOP, GEOL_BASE, GEOL_DESC | Layer intervals and descriptions |
| ISPT (optional) | LOCA_ID, ISPT_TOP, ISPT_NVAL, optional ISPT_REP | Test depth, raw N-value, original remark |

Every group needs one HEADING, UNIT and TYPE record with matching widths. Duplicate groups or headings, malformed quoting, and misplaced metadata are rejected with a line number. Unknown groups are structurally parsed and checked for unit/type definitions, but their observations and relationships are not interpreted. Field-level AGS status rules, abbreviation references, laboratory groups, sample keys, method compliance, date rules, DICT extensions, and every version's data dictionary are outside this tool. Use the [BGS AGS utilities](https://www.bgs.ac.uk/technologies/geotechnical-data-services/) for complete standards validation before submission.

Depth fields may use `m`, `ft`, or `mm`; they convert to metres independently. Coordinates stay in their original grid. Their unit must match the explicitly supplied projected `--crs` in both coordinate columns. Geographic AGS LOCA_LAT/LOCA_LON, local grids without a known CRS, and coordinate swapping are not inferred. CRS plausibility checks cannot establish that the driller recorded the correct location. Use a suitable local output grid; the BC default is not appropriate for the UK example.

SPT N-values are raw, nonnegative integer blow counts. Missing numeric N-values are retained as missing with warnings and original remarks, including refusal descriptions. No N60 or overburden corrections, refusal conversion, or bearing-capacity calculations are made. The plot marks test depth, not a test interval.

## Validation decisions

The default depth tolerance is 0.001 m (`--tolerance`), applied after unit conversion. Differences within tolerance are treated as coincident boundaries. Negative depths and zero or reversed intervals are always errors. Layers are sorted by top depth for continuity checks; the source row number is preserved. Coverage begins at ground level (0 m) and ends at the declared final depth. A running maximum base prevents nested overlaps from creating false gaps.

Overlaps block export, including exact duplicate layers. Gaps at the surface, inside the log, and at the bottom are warnings. Missing geology for a hole, an interval beyond final depth, duplicate holes, orphan layers/tests, inconsistent location rows, invalid units, negative/noninteger N-values and duplicate test depths are errors. Empty descriptions and missing N-values are warnings. `--strict` blocks either severity.

Rows with invalid numbers are omitted from the in-memory records but remain in the error report; the entire export is then blocked. Issues include severity, code, group, physical ending line of the CSV record, hole ID and a readable message. File/group-level problems use row 0. JSON includes the input SHA-256 and options so a report can be traced back to its exact input. Source files are never edited.

## Output files

| File | Contents |
| --- | --- |
| validation.json / issues.csv | Counts, options, source hash, errors and warnings |
| boreholes.gpkg | One point per hole, explicit projected CRS and depth / coverage attributes |
| stratigraphy.csv | Thickness and top/base envelope per exact source description per hole |
| intervals.csv | Individual intervals in metres and original row numbers |
| spt.csv | Tests in metres, original uncorrected N-value or blank, and source remark |
| logs.csv / logs/*.png | Safe hashed filename index and graphical logs |
| manifest.json | Files from a completed data export |
| boreholes.qgz / map.pdf / map.png | QGIS project and layout, created by the separate map script |

The summary's top/base values are an envelope: repeated material can appear at separated depths. Thickness is the sum of its intervals, excluding gaps. No summary implies a continuous layer. Gap thickness on the map is total depth minus summed logged thickness; sub-tolerance boundary differences may affect the last decimals. Large logs can produce tall images; inspect the original interval table alongside them.

QGIS styling separates holes with warnings from those without warnings. The map does not show subsurface boundaries or interpolate between boreholes. The north indicator uses grid north; the script keeps map rotation at zero. No online tiles are needed. Keep the project beside its GeoPackage when sharing it. The QGIS script requires the completed manifest and refuses reports containing errors.
