import pytest

from site_data_qaqc.qaqc import assess


@pytest.mark.parametrize(
    "result,dl,status",
    [
        ("11", "1", "exceeds"),
        ("10", "1", "at_or_below"),
        ("<10", "10", "below_limit"),
        ("<11", "11", "indeterminate"),
        ("ND", "2", "below_limit"),
    ],
)
def test_screening_boundary_and_censoring(raw, result, dl, status):
    bundle = assess([raw(result=result, detection_limit=dl)])
    assert bundle["results"][0]["screening"] == status


def test_missing_guideline_does_not_mean_clean(raw):
    bundle = assess([raw(analyte="copper")])
    assert bundle["results"][0]["screening"] == "no_guideline"
    assert bundle["results"][0]["guideline_id"] is None
    assert bundle["issues"][0]["code"] == "no_guideline"


def test_soil_threshold_uses_dry_mass(raw):
    bundle = assess(
        [raw(matrix="soil", unit="ug/kg", basis="dry", result="13000", detection_limit="100")]
    )
    r = bundle["results"][0]
    assert r["value"] == 13
    assert r["guideline_value"] == 12
    assert r["screening"] == "exceeds"


@pytest.mark.parametrize(
    "value,dl,status,rpd",
    [
        ("30", "1", "fail", 40),
        ("22", "1", "pass", 200 * 2 / 42),
        ("<2", "2", "censored", None),
        ("4", "1", "near_detection_limit", None),
        ("0", "1", "near_detection_limit", None),
        ("22", "", "missing_detection_limit", None),
    ],
)
def test_duplicate_precision_policy(raw, value, dl, status, rpd):
    bundle = assess(
        [raw(), raw(sample_id="D1", duplicate_of="S1", result=value, detection_limit=dl)]
    )
    pair = bundle["duplicates"][0]
    assert pair["status"] == status
    assert pair["rpd"] == (None if rpd is None else pytest.approx(rpd))


def test_duplicate_unit_normalization_and_configurable_threshold(raw):
    rows = [
        raw(),
        raw(sample_id="D1", duplicate_of="S1", result="0.03", unit="mg/L", detection_limit="0.001"),
    ]
    pair = assess(rows, rpd_limit=40)["duplicates"][0]
    assert pair["rpd"] == pytest.approx(40)
    assert pair["status"] == "pass"


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"duplicate_of": "missing"}, "missing_parent"),
        ({"duplicate_of": "D1"}, "invalid_parent"),
        ({"depth_top_m": "0"}, "incompatible_interval"),
        ({"x": "550100"}, "incompatible_location"),
        ({"sample_date": "2026-09-15"}, "missing_parent"),
    ],
)
def test_bad_duplicate_links(raw, changes, status):
    params = dict(sample_id="D1", duplicate_of="S1")
    params.update(changes)
    bundle = assess([raw(), raw(**params)])
    assert bundle["duplicates"][0]["status"] == status


def test_duplicate_chains_are_not_precision_pairs(raw):
    rows = [raw(), raw(sample_id="D1", duplicate_of="S1"), raw(sample_id="D2", duplicate_of="D1")]
    assert assess(rows)["duplicates"][1]["status"] == "invalid_parent"


def test_repeated_natural_keys_quarantine_all_conflicts(raw):
    bundle = assess([raw(), raw(result="100"), raw(sample_id="D1", duplicate_of="S1")])
    assert len(bundle["results"]) == 1
    assert len(bundle["rejected"]) == 2
    assert bundle["duplicates"][0]["status"] == "missing_parent"
    assert {i["code"] for i in bundle["issues"]} == {
        "duplicate_key",
        "duplicate_missing_parent",
        "exceeds",
    }


def test_rejections_preserve_source_and_reason(raw):
    bundle = assess([raw(unit="ppm"), raw(crs="EPSG:999999")])
    assert len(bundle["rejected"]) == 2
    assert bundle["rejected"][0]["source_row"] == 2
    assert '"unit": "ppm"' in bundle["rejected"][0]["raw_json"]
    assert "unsupported" in bundle["rejected"][0]["reason"]


def test_estimates_and_missing_dl_are_reviewed(raw):
    b = assess([raw(result="0.5", qualifier="J"), raw(sample_id="S2", detection_limit="")])
    assert {i["code"] for i in b["issues"]} >= {
        "estimated_result",
        "below_detection_limit",
        "missing_detection_limit",
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rpd_limit": -1},
        {"rpd_limit": float("nan")},
        {"dl_multiplier": 0},
        {"dl_multiplier": float("inf")},
    ],
)
def test_invalid_policy(raw, kwargs):
    with pytest.raises(ValueError):
        assess([raw()], **kwargs)


@pytest.mark.parametrize(
    "changes", [{"borehole_id": "BH2"}, {"depth_bottom_m": "3"}, {"x": "550100"}]
)
def test_sample_event_cannot_have_conflicting_metadata(raw, changes):
    bundle = assess([raw(), raw(analyte="benzene", **changes)])
    assert bundle["results"] == []
    assert len(bundle["rejected"]) == 2
    assert {i["code"] for i in bundle["issues"]} == {"inconsistent_sample"}
