# SPDX-License-Identifier: Apache-2.0
import pytest

from app.bbox import parse_bbox_floats


def test_none_and_valid():
    assert parse_bbox_floats(None) is None
    assert parse_bbox_floats("0,1,2,3") == (0.0, 1.0, 2.0, 3.0)


def test_antimeridian_bbox_is_accepted():
    assert parse_bbox_floats("170,-10,-170,10") == (170.0, -10.0, -170.0, 10.0)


@pytest.mark.parametrize(
    "raw", ["1,2,3", "a,b,c,d", "nan,0,1,1", "0,0,inf,1", "0,0,181,1", "0,-91,1,1"]
)
def test_malformed_non_finite_or_out_of_bounds_raises(raw):
    with pytest.raises(ValueError):
        parse_bbox_floats(raw)


def test_bounds_check_can_be_disabled_for_projected_crs():
    assert parse_bbox_floats("100000,6000000,200000,7000000", check_bounds=False) is not None
