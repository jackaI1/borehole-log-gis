# Data I used

The committed snapshot is a small public subset around Bruce County, Ontario, downloaded on **November 5, 2026**. It lets the example and tests run without relying on the availability of a live service. The download command and exact queries are implemented in `src/wind_screen/data.py` and recorded in `data/ontario/sources.json`.

| Input | Public source | Snapshot content | Licence |
| --- | --- | --- | --- |
| Wind | [Global Wind Atlas 4.0](https://globalwindatlas.info/) | Native-grid crop of the Canada mean wind-speed raster, 100 m above ground, m/s | [CC BY 4.0 and GWA terms](https://globalwindatlas.info/about/TermsOfUse) |
| Hydro lines | [Ontario Utility Line](https://data.ontario.ca/dataset/utility-line) | 24 line features, filtered to `CLASS_SUBTYPE = 'Hydro Line'`; other utilities excluded | [Open Government Licence - Ontario](https://www.ontario.ca/page/open-government-licence-ontario) |
| Roads | [Ontario Road Network Composite](https://data.ontario.ca/dataset/ontario-road-network-orn-composite) | 1,823 source segments | Open Government Licence - Ontario |
| Water | [Ontario Hydro Network Waterbody](https://data.ontario.ca/dataset/ontario-hydro-network-waterbody) | 700 polygons, including Lake Huron near the west edge | Open Government Licence - Ontario |
| Parks | [Provincial Park Regulated](https://data.ontario.ca/dataset/provincial-park-regulated) | 1 regulated park polygon intersecting the query box | Open Government Licence - Ontario |
| Candidates | My generated grid | 289 clipped 2 km study cells with `BC-` identifiers | MIT, as a project-generated dataset |

The wind crop is a real public model raster, not a raster painted from invented values. Its direct source is `https://gwa.cdn.nazkamapps.com/country_tifs_v4/CAN_wind-speed_100m.tif`, reached from the atlas download API. Only the small study window is read and committed; no wind values are interpolated or changed. It has 161 columns and 121 rows at 0.0025 degrees per pixel. The source is geographic, so physical pixel dimensions vary with latitude. The wind field represents a long-term modelled resource, not a recent weather forecast or on-site mast measurement.

Hydro-line queries cover the study area plus the full 20 km grid-distance range and a 1 km margin. Other layers cover their setback distances plus a 1 km margin. The source features are retained whole, so there can be features outside the map frame. Only public feature IDs and geometry are retained. Full source attributes, road addresses and names are not copied. Download sizes and query counts can change when the public services update.

The Ontario utility-line catalogue describes source records from 1977 to 2008. Downloading it in 2026 does not make those lines a current engineering inventory. The Hydro Line category is a mapped electrical-network proxy for early transmission proximity. It does not distinguish confirmed high-voltage transmission from distribution, and the snapshot does not establish voltage, operating status or grid capacity. I keep that uncertainty on the map and in every memo rather than treating distance as a connection guarantee. For a serious study I would replace it with a verified operator transmission inventory.

## Attribution

Contains information licensed under the Open Government Licence - Ontario. The Ontario data is supplied by the Government of Ontario through Geospatial Ontario / Land Information Ontario. I have subset the source data and generated derived buffers and rankings; those results are my own and do not imply Ontario's endorsement.

Data obtained from the Global Wind Atlas version 4.0, a free, web-based application developed, owned and operated by the Technical University of Denmark (DTU). The Global Wind Atlas version 4.0 is released in partnership with the World Bank Group, utilizing data provided by Vortex, using funding provided by the Energy Sector Management Assistance Program (ESMAP). For additional information: https://globalwindatlas.info . My adaptation is a small geographic crop and derived screening statistics; no endorsement by those organizations is implied.

The project code's MIT licence does not replace these source-data licences. Preserve the source credits when reusing the snapshot or the example map.
