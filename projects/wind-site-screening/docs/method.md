# How I calculate the shortlist

This is a comparative desktop screen. I use fixed thresholds so adding another candidate does not change an existing candidate's score. The defaults are deliberately editable and are not a regulatory interpretation.

## Geometry and distance

All vectors must declare their source CRS. I reject null, empty and invalid geometries rather than silently repairing their shape. The target CRS must be projected in metres; I reject Mercator display projections and candidates outside the CRS's published area of use. Bruce County uses EPSG:26917. Other Ontario locations need an appropriate local CRS and an updated study box.

For each context layer I buffer by its configured distance, then union all buffers. For water and parks, a zero setback still excludes the polygon itself. For roads and lines, zero means no area buffer. Unioning before intersection prevents double counting overlapping restrictions.

For candidate polygon P and union of exclusions C:

- Remaining land U = P minus C.
- Constraint fraction = 1 - area(U) / area(P).
- Remaining hectares = area(U) / 10,000.
- Grid distance = the minimum straight-line distance between U and any mapped hydro-line geometry.

Distance is measured from remaining land, not the candidate centre. It can be shorter than the connection from a practical turbine location. No routing, substation capacity, line-voltage check or interconnection engineering is implied. Fragmented remaining land is allowed at this stage; the memo calls for reviewing connected patches.

## Wind sampling

I transform U into the wind raster's own CRS and use native pixel centres inside it. The mean is the arithmetic mean of valid speeds at those centres, after applying stored raster scale and offset. Nodata, NaN, infinite and negative values are missing. Pixels outside the raster are included in the coverage denominator but never in the mean. This prevents an area half outside the raster from appearing fully covered. A polygon containing no pixel centres has zero coverage and no wind estimate. I do not substitute an interpolated value or a centroid sample.

The GWA crop preserves its original geographic pixel grid. Pixel areas vary slightly with latitude; the unweighted centre mean is an approximation for this small study area. It is not a bankable energy-yield calculation. The wind height is 100 m above ground, not the raster pixel size. The native angular resolution is recorded in the GeoTIFF; the atlas describes approximately 250 m horizontal resolution.

## Eligibility and scores

Before ranking, I check remaining hectares, constraint fraction, valid wind coverage, the wind floor and the maximum line distance. Failure reasons remain in the CSV as `too_little_usable_land`, `constraint_overlap`, `insufficient_wind_data`, `low_wind` or `grid_too_far`. Several reasons can apply at once. A rejected site receives a blank score and rank.

For eligible sites, with clamp(x) meaning limit x to the interval [0, 1]:

```
wind_component   = clamp((mean_wind - wind_floor) / (wind_ceiling - wind_floor))
grid_component   = clamp(1 - grid_distance / grid_limit)
usable_component = 1 - constraint_fraction
score = 100 * (wind_weight * wind_component
             + grid_weight * grid_component
             + usable_weight * usable_component)
```

Weights must be non-negative and sum to one. At the defaults, 7 m/s, a 10 km line distance and 75% remaining land give 55 points. I sort by descending score, then ascending `site_id` to break ties deterministically. I rank only eligible sites and write notes for the configured number at the top. All-zero-eligibility runs still produce inspectable outputs and an empty memo folder.

## Reproducibility and limits

`run.json` records all input file hashes and the settings actually used. The example CSV stores six decimal places, while calculations use full precision. GeoPackage and QGIS timestamps and layer IDs can differ between runs; the calculated rankings should match for the same locked environment and input snapshot. CI checks actual output generation, not just helper functions, and separately tests the saved QGIS layout with real data providers.

I have not modelled buildings and noise receptors, property access, Indigenous rights and consultation, wildlife, all wetlands, aviation, slope, turbine spacing, wake effects, detailed grid connections or economics. A cell can pass this screen and still be impossible to develop. The source hydro lines also have older records and no established voltage or current operational status. I use the rank to decide what to investigate next.
