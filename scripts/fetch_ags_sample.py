"""Extract public BH01 observations, without project contacts, from a pinned BGS example.

Only the selected original observation cells are retained. The five administration
and dictionary groups are new minimal metadata describing this excerpt.
"""

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

COMMIT = "b223b48803d8feb07897ae468b455842cbf1790d"
URL = (
    f"https://raw.githubusercontent.com/BritishGeologicalSurvey/pyagsapi/{COMMIT}/test/files/real/"
    "19-1316%20-%202020-03-02%201554%20-%20Final%20-%201.ags"
)
FIELDS = {
    "LOCA": ["LOCA_ID", "LOCA_NATE", "LOCA_NATN", "LOCA_FDEP"],
    "GEOL": ["LOCA_ID", "GEOL_TOP", "GEOL_BASE", "GEOL_DESC"],
    "ISPT": ["LOCA_ID", "ISPT_TOP", "ISPT_NVAL", "ISPT_REP"],
}


def main():
    with urlopen(URL, timeout=60) as response:
        raw = response.read()
    selected = {k: {"rows": []} for k in FIELDS}
    group, headings = None, []
    for row in csv.reader(io.StringIO(raw.decode("utf-8-sig"))):
        if not row:
            continue
        if row[0] == "GROUP":
            group = row[1]
        elif row[0] == "HEADING":
            headings = row[1:]
        elif group in FIELDS:
            cells = dict(zip(headings, row[1:]))
            values = [cells[f] for f in FIELDS[group]]
            if row[0] in {"UNIT", "TYPE"}:
                selected[group][row[0]] = values
            elif row[0] == "DATA" and cells["LOCA_ID"] == "BH01":
                selected[group]["rows"].append(values)
    path = Path("samples/bgs_bh01.ags")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, quoting=csv.QUOTE_ALL)

        def write_group(name, fields, units, types, rows):
            writer.writerow(["GROUP", name])
            writer.writerow(["HEADING", *fields])
            writer.writerow(["UNIT", *units])
            writer.writerow(["TYPE", *types])
            for values in rows:
                writer.writerow(["DATA", *values])
            writer.writerow([])

        write_group(
            "PROJ",
            ["PROJ_ID", "PROJ_NAME"],
            ["", ""],
            ["ID", "X"],
            [["BGS-EXCERPT", "Public BH01 observation excerpt"]],
        )
        write_group("TRAN", ["TRAN_ISNO", "TRAN_AGS"], ["", ""], ["X", "X"], [["1", "4.0"]])
        write_group(
            "ABBR",
            ["ABBR_HDNG", "ABBR_CODE", "ABBR_DESC"],
            ["", "", ""],
            ["X", "X", "X"],
            [["LOCA_TYPE", "RO", "Rotary open hole (source method)"]],
        )
        write_group(
            "TYPE",
            ["TYPE_TYPE", "TYPE_DESC"],
            ["", ""],
            ["X", "X"],
            [["ID", "Identifier"], ["X", "Text"], ["2DP", "Two decimal places"], ["0DP", "Integer"]],
        )
        write_group("UNIT", ["UNIT_UNIT", "UNIT_DESC"], ["", ""], ["X", "X"], [["m", "metres"]])
        for name, fields in FIELDS.items():
            g = selected[name]
            write_group(name, fields, g["UNIT"], g["TYPE"], g["rows"])
    provenance = {
        "publisher": "British Geological Survey / UKRI",
        "source_url": URL,
        "source_commit": COMMIT,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "hole_id": "BH01",
        "coordinate_crs": "EPSG:27700",
        "license": "Open Government Licence v3.0",
        "license_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "license_evidence": "https://britishgeologicalsurvey.github.io/pyagsapi/#example-files",
        "attribution": "Contains data supplied by Natural Environment Research Council. "
        "Contains public sector information licensed under the Open Government Licence v3.0.",
        "transformations": "Selected BH01 LOCA, GEOL and ISPT cells unchanged. Other fields omitted. "
        "PROJ, TRAN, ABBR, TYPE and UNIT replaced with excerpt metadata. "
        "Not a full copy of the original AGS submission.",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    path.with_suffix(".source.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("Saved public BH01: 6 intervals, 5 SPT records (2 without numerical N-values)")


if __name__ == "__main__":
    main()
