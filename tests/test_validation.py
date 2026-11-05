import pytest

from borehole_gis.model import SPT, Dataset, Hole, Interval
from borehole_gis.validate import validate


def dataset(layers=((0, 10),)):
    return Dataset(
        "EPSG:4326",
        holes=[Hole("A", -123, 49, 10, 2)],
        intervals=[Interval("A", a, b, "sand", 3 + n) for n, (a, b) in enumerate(layers)],
    )


def codes(ds):
    return [i.code for i in validate(ds).issues]


@pytest.mark.parametrize(
    "layers,expected",
    [
        (((0, 4), (4, 10)), []),
        (((4, 10), (0, 4)), []),
        (((0, 4), (5, 10)), ["gap"]),
        (((1, 9),), ["gap", "gap"]),
        (((0, 5), (4, 10)), ["overlap"]),
        (((0, 10), (1, 2), (3, 4)), ["overlap", "overlap"]),
        (((0, 10), (0, 10)), ["overlap"]),
        (((0, 11),), ["beyond_final_depth"]),
        (((-1, 10),), ["invalid_interval", "missing_log"]),
        (((0, 0),), ["invalid_interval", "missing_log"]),
        (((5, 2),), ["invalid_interval", "missing_log"]),
        (((0, 4), (4.0005, 10)), []),
        ((), ["missing_log"]),
    ],
)
def test_interval_continuity(layers, expected):
    assert codes(dataset(layers)) == expected


@pytest.mark.parametrize("tolerance", [-1, float("nan"), float("inf")])
def test_bad_tolerance(tolerance):
    with pytest.raises(ValueError):
        validate(dataset(), tolerance)


def test_duplicate_blank_and_invalid_holes():
    ds = dataset()
    ds.holes += [Hole("A", -123, 49, 10, 4), Hole("", -123, 95, -1, 5)]
    assert {"duplicate_hole", "blank_id", "coordinate_range", "final_depth"} <= set(codes(ds))


def test_orphans():
    ds = dataset()
    ds.intervals.append(Interval("B", 0, 10, "clay", 10))
    ds.spts.append(SPT("B", 2, 4, 11))
    assert codes(ds) == ["orphan_interval", "orphan_spt"]


@pytest.mark.parametrize(
    "depth,n,expected",
    [
        (-1, 10, ["spt_depth"]),
        (11, 10, ["spt_depth"]),
        (0, 0, []),
        (10, 20, []),
        (3, -1, ["spt_n"]),
        (3, 1.5, ["spt_n"]),
        (3, None, []),
    ],
)
def test_spt(depth, n, expected):
    ds = dataset()
    ds.spts = [SPT("A", depth, n, 4)]
    assert codes(ds) == expected


def test_duplicate_spt_and_empty_description():
    ds = dataset()
    ds.intervals[0].description = ""
    ds.spts = [SPT("A", 3, 10, 4), SPT("A", 3, 10, 5)]
    assert codes(ds) == ["empty_description", "duplicate_spt"]
