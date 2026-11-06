import json

import pytest


@pytest.fixture
def raw():
    def make(**changes):
        values = dict(
            site_id="Test Site",
            borehole_id="BH1",
            sample_id="S1",
            sample_date="2026-09-14",
            matrix="GW",
            analyte="As",
            result="20",
            unit="ug/L",
            detection_limit="1",
            x="550000",
            y="4840000",
            depth_top_m="1",
            depth_bottom_m="2",
            lithology="sand",
        )
        values.update(changes)
        return dict(
            source_file="test.csv",
            source_sha256="a" * 64,
            source_row=2,
            raw_json=json.dumps(values),
            values=values,
        )

    return make
