"""Download complete logs for four fixed BC boreholes, using only public log fields.

Uses the native BC column names. No owner names, contacts, or property records.
Run from the repo root; writes only the two named sample files.
"""

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

SERVICE = "https://delivery.maps.gov.bc.ca/arcgis/rest/services/whse/bcgw_pub_whse_waste/MapServer/1/query"
FIELDS = [
    "BOREHOLE_SITE_ID",
    "BOREHOLE_NAME",
    "BOREHOLE_LITHOLOGY_ID",
    "LATITUDE",
    "LONGITUDE",
    "TOTAL_DEPTH",
    "FROM_UNIT_DEPTH",
    "TO_UNIT_DEPTH",
    "UNIT_DESCRIPTION",
]


def main():
    params = {
        "f": "json",
        "where": "BOREHOLE_SITE_ID IN (13,17,21,28)",
        "outFields": ",".join(FIELDS),
        "returnGeometry": "false",
        "orderByFields": "BOREHOLE_SITE_ID,BOREHOLE_NAME,FROM_UNIT_DEPTH",
        "resultRecordCount": 1000,
    }
    url = SERVICE + "?" + urlencode(params)
    with urlopen(url, timeout=90) as response:
        data = json.load(response)
    if "error" in data or data.get("exceededTransferLimit"):
        raise RuntimeError("Incomplete service response; sample was not written")
    rows = [f["attributes"] for f in data["features"]]
    if not rows:
        raise RuntimeError("No sample rows returned")
    target = Path("samples/bc_boreholes.csv")
    target.parent.mkdir(exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    provenance = {
        "title": "Borehole Log Lithology Public View",
        "publisher": "Province of British Columbia",
        "catalogue": "https://catalogue.data.gov.bc.ca/dataset/1956d690-b196-4be2-b82b-263491326a28",
        "license": "Open Government Licence - British Columbia",
        "license_url": "https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc",
        "query_url": url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "rows": len(rows),
        "depth_units": "m",
        "coordinate_crs": "EPSG:4326",
        "transformations": "Selected fields and rows only; native values and descriptions unchanged.",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    target.with_suffix(".source.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Saved {len(rows)} intervals from the BC public service")


if __name__ == "__main__":
    main()
