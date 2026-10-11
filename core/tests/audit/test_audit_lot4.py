# SPDX-License-Identifier: Apache-2.0
"""Reproducteurs de bugs confirmés (audit lot 4). Chaque test échoue tant que le bug existe."""

import pathlib
import re

import pytest
import yaml

from app.collections.introspection import ColumnInfo, TableInfo
from app.configs.schemas import MapLayer, PopupConfig
from app.features.routes import parse_bbox
from app.features.validation import validate_feature

REPO = pathlib.Path(__file__).resolve().parents[3]


def _info(geom_type: str) -> TableInfo:
    return TableInfo(
        table_name="t",
        pk_column="id",
        geometry_column="geom",
        geometry_type=geom_type,
        srid=4326,
        columns=[ColumnInfo(name="titre", type="string", required=False)],
    )


def _feat(geom):
    return {"type": "Feature", "properties": {}, "geometry": geom}


def test_mixed_geometry_collection_accepts_point():
    errs = validate_feature(_info("GEOMETRY"), _feat({"type": "Point", "coordinates": [0, 0]}))
    assert errs == []


def test_polygon_collection_accepts_multipolygon():
    geom = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]}
    assert validate_feature(_info("Polygon"), _feat(geom)) == []


def test_bbox_out_of_range_rejected():
    with pytest.raises(Exception):  # noqa: B017
        parse_bbox("0,0,1,95")


def test_bbox_nan_rejected():
    with pytest.raises(Exception):  # noqa: B017
        parse_bbox("nan,0,1,1")


@pytest.mark.xfail(
    strict=True,
    reason="REV-audit: worker prod garde CORE_BASE_URL localhost (docker-compose.prod.yml:253)",
)
def test_prod_worker_overrides_core_base_url():
    prod = yaml.safe_load((REPO / "docker-compose.prod.yml").read_text())
    env = prod["services"]["worker"].get("environment") or {}
    assert "CORE_BASE_URL" in env


@pytest.mark.xfail(
    strict=True,
    reason="REV-audit: install.sh ne couple pas profils export/appexport aux flags (install.sh:248)",  # noqa: E501
)
@pytest.mark.parametrize("flag", ["CORE_EXPORT_ENABLED", "CORE_APPEXPORT_ENABLED"])
def test_install_sets_capability_flag(flag):
    src = (REPO / "scripts/install.sh").read_text()
    assert re.search(rf"set_env_var\s+{flag}\b", src)


@pytest.mark.xfail(strict=True, reason="REV-audit: MapLayer.timeField rejeté 422 (schemas.py:122)")
def test_maplayer_accepts_timefield():
    MapLayer.model_validate({"id": "l", "title": "t", "kind": "vector", "timeField": "d"})


@pytest.mark.xfail(
    strict=True, reason="REV-audit: PopupConfig.attachmentField rejeté 422 (schemas.py:113)"
)
def test_popupconfig_accepts_attachmentfield():
    PopupConfig.model_validate({"attachmentField": "f"})
