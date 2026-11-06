# Input contract and review decisions

I use one row per chemical measurement. I chose a narrow, explicit contract so that an unknown unit or an ambiguous date becomes a review item instead of an invisible guess. A wide laboratory sheet needs to be unpivoted into this long form before import. Comma, semicolon, tab and pipe separators are detected from the header; UTF-8 with or without a byte-order mark is the default. Use `--encoding cp1252` for a Windows export. Thousands separators are unsupported; decimal commas are accepted in quoted CSV cells or semicolon/tab tables.

## Fields

Column names are case-insensitive, surrounding spaces are removed, and underscores and spaces are interchangeable. All aliases are in `ingest.py`; extra columns are retained in the original-row JSON.

| Canonical field | Common aliases | Meaning |
| --- | --- | --- |
| `site_id` | site, project | Invented site identifier |
| `borehole_id` | bh, well, location | Borehole or monitoring well |
| `sample_id` | sample, lab id | Sample identifier, separate from borehole |
| `sample_date` | date, sampled | YYYY-MM-DD, YYYY/MM/DD or DD-Mon-YYYY |
| `matrix` | medium, media | groundwater/GW/water or soil |
| `analyte` | parameter, chemical | Chemical name; As becomes arsenic |
| `result` | value, concentration | Non-negative number, `<number`, `<=number`, ND, N/D or U |
| `unit` | units | Water: g/L, mg/L, ug/L, ng/L; soil: g/kg, mg/kg, ug/g, ug/kg |
| `detection_limit` | dl, mdl, reporting limit | Positive number in the same unit as the result |
| `qualifier` | flag, lab qualifier | Optional U/ND (non-detect) or J (estimated); other codes need review |
| `duplicate_of` | parent, duplicate of | Original sample ID for a field duplicate |
| `x`, `y` | easting/northing, longitude/latitude | Coordinate pair; x is always easting/longitude |
| `crs` | epsg | Coordinate reference system, such as EPSG:26917 or EPSG:4326 |
| `depth_top_m`, `depth_bottom_m` | from m/to m, top m/bottom m | Sample interval below ground in metres |
| `lithology` | material, soil description | Optional field description of material |
| `basis` | weight basis | Soil requires explicit dry or dry weight |

Everything through `unit`, the coordinates and both depths are required. A detected result without a detection limit is retained with a warning; a non-detect without a usable bound is rejected. Coordinate system is taken from the row, otherwise `--crs` (default NAD83 / UTM 17N, EPSG:26917). I check transformation success, geographic bounds and the declared system's area of use. These checks cannot detect a plausible coordinate entered in the wrong system.

I retain the source filename, SHA-256 content hash, physical line at the end of the CSV record, original cells and a numeric record ID. IDs are assigned in input order and identify rows within one run. The hash disambiguates files sharing a name. Blank lines are ignored; broken quoting, unequal cell counts, missing columns and colliding aliases stop the whole run without publishing partial output.

## Units, non-detects and screening

Water results become mg/L. Soil results become mg/kg dry weight; ug/g is numerically equivalent. I reject ppm because its interpretation depends on the sample, and I do not invent a moisture correction for wet soil.

A non-detect means the laboratory could not reliably measure below a bound. I store its concentration as SQL NULL and the bound as `detection_limit`, never as zero or half the limit. For `<2` or a numeric U-qualified result, that number is the bound. An independently supplied DL must agree with it. ND needs an explicit DL. `<=` is handled conservatively as an upper bound too. A J result stays numeric and gets an estimate warning.

| Status | Decision |
| --- | --- |
| `exceeds` | Detected concentration strictly greater than the guideline |
| `at_or_below` | Detected concentration at or below it; equality does not exceed |
| `below_limit` | Non-detect bound at or below guideline; no exceedance demonstrated |
| `indeterminate` | Non-detect bound above guideline; the method is insufficiently sensitive |
| `no_guideline` | No bundled value for this matrix and chemical; no clean result implied |

The three sourced comparisons and their scope are in [guidelines.md](guidelines.md). Map colours describe chemical screening only. Precision failures, estimated values and other QA issues still require the separate issue report, even when a point is green.

## Duplicate precision

I match `duplicate_of` to an original sample in the same site, date, matrix and chemical. I require the same borehole and depth interval and coordinates within 0.00001 degrees on each axis (about a metre here). Self-links and chains are invalid. An absent original is an explicit `missing_parent` check, not a pass. Repeated site/sample/date/matrix/chemical keys quarantine every conflicting row. Results for one sample event with conflicting borehole, depth or coordinates are also quarantined.

Relative percent difference (RPD) measures the disagreement between two measurements:

`RPD = 100 × |original - duplicate| / ((original + duplicate) / 2)`

I compare normalized values only when both are detected and each is strictly above five times its own DL. Otherwise the check is labelled `censored`, `missing_detection_limit` or `near_detection_limit`; two zeros therefore do not earn a precision pass. The default RPD limit is 30%, with equality passing. This is my configurable demonstration policy, not a universal laboratory acceptance rule. `--rpd-limit` and `--dl-multiplier` set it, and the report records the choices. The example 0.018 and 0.030 mg/L pair has an RPD of 50%, so it fails.

## Outputs and database design

`site_data.sqlite` has `records` (original rows and dispositions), `results` (standardized analytical rows), `guidelines` (value and source), `issues` (review findings) and `duplicates` (pair decisions). Primary/foreign keys preserve lineage; check constraints enforce depth and censoring rules. `exceedances` and `review_queue` are SQL views. This is a fresh import package per run, not an incremental database updater.

`standardized.csv`, `rejected.csv`, `issues.csv`, `duplicates.csv` and `borehole_log.csv` give the same decisions in tables. The borehole table sorts sample intervals by site, borehole and depth and preserves both chemical and source-row details. It is a sample log, not inferred stratigraphy or a complete drilling record.

GeoPandas writes `samples.gpkg` with WGS84 (EPSG:4326) layers `sample_results` (one feature per chemical), `sample_points` (one per sample event/interval) and `exceedances`. Individual samples and depths may share coordinates. Point summaries include exceedance and indeterminate counts; worst screening status wins. `sample_points.geojson` is another portable view. Each site's PNG uses a local UTM projection in metres and pairs locations with sampled depth intervals. More severe markers draw last so a green result cannot cover a red one. No online basemap is required.

`summary.json` records input hashes, counts, rule settings and safe filenames for each site's CSV and PNG. The site filename includes a hash to avoid name collisions. Output is staged and published only on success, and an existing output directory is refused. Exit codes: 0 = exported, 1 = input or execution failure, 2 = `--strict` exported successfully but found at least one issue. Strict mode counts all warnings, including exceedances and unsupported comparisons.

I keep the full dataset in memory, and the figures are intended for a handful of boreholes per site. This is a reproducible review tool for small site tables; a large archive would need chunked loading and paginated logs.
