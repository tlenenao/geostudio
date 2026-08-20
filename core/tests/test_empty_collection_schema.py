# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.collections.schemas import EmptyCollectionColumn, EmptyCollectionCreate


def test_accepts_a_valid_payload_with_known_sql_types():
    payload = EmptyCollectionCreate(
        title="Ma requête",
        columns=[
            EmptyCollectionColumn(name="commune", sqlType="text"),
            EmptyCollectionColumn(name="total", sqlType="integer"),
        ],
        geometryType="Point",
        srid=4326,
    )
    assert payload.columns[0].sqlType == "text"


def test_rejects_an_unknown_sql_type():
    with pytest.raises(ValidationError):
        EmptyCollectionColumn(name="x", sqlType="text); DROP TABLE users; --")


def test_rejects_an_unknown_geometry_type():
    with pytest.raises(ValidationError):
        EmptyCollectionCreate(title="t", columns=[], geometryType="NotAGeometry", srid=4326)


def test_geometry_type_and_srid_default_to_none():
    payload = EmptyCollectionCreate(title="t", columns=[])
    assert payload.geometryType is None
    assert payload.srid is None


@pytest.mark.parametrize("reserved_name", ["id", "tenant_id", "geom"])
def test_rejects_a_reserved_column_name(reserved_name):
    with pytest.raises(ValidationError):
        EmptyCollectionColumn(name=reserved_name, sqlType="text")
