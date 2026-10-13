# SPDX-License-Identifier: Apache-2.0
"""ARC-28 : symbologie déclarative -> règles -> SLD 1.1 validé contre le XSD OGC
(schémas vendus hors-ligne dans tests/fixtures/ogc_schemas)."""

import re
from pathlib import Path

import pytest
import xmlschema

from app.styles import model
from app.styles.model import default_style, select_rule, style_from_symbology
from app.styles.sld import style_to_sld

SCHEMAS = Path(__file__).parent / "fixtures" / "ogc_schemas" / "schemas.opengis.net"
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def sld_schema():
    ns = {
        "http://www.opengis.net/sld": SCHEMAS / "sld/1.1.0/StyledLayerDescriptor.xsd",
        "http://www.opengis.net/se": SCHEMAS / "se/1.1.0/FeatureStyle.xsd",
        "http://www.opengis.net/ogc": SCHEMAS / "filter/1.1.0/filter.xsd",
        "http://www.opengis.net/gml": SCHEMAS / "gml/3.1.1/base/feature.xsd",
    }
    return xmlschema.XMLSchema(
        str(ns["http://www.opengis.net/sld"]),
        locations={k: str(v) for k, v in ns.items()},
        allow="local",
        validation="lax",  # GML 3.1.1 : restrictions que xmlschema juge illégales (hors SLD)
    )


CATEGORICAL = {
    "field": "type",
    "mode": "categorical",
    "palette": "categorical-b",
    "domain": {"kind": "categorical", "values": ["a", "b & <c>", "d"]},
    "computedAt": "2026-01-01",
}
CLASSED = {
    "field": "pop",
    "mode": "numeric",
    "palette": "sequential-warm",
    "classification": {"method": "quantile", "classes": 3},
    "domain": {"kind": "numeric-classed", "breaks": [0, 10, 100, 1000]},
    "computedAt": "2026-01-01",
}
CONTINUOUS = {
    "field": "pop",
    "mode": "numeric",
    "palette": "sequential-blue",
    "domain": {"kind": "numeric", "min": 0, "max": 70},
    "computedAt": "2026-01-01",
}
SIX = [
    ("polygon", {"color": CATEGORICAL, "opacity": 50}),
    (
        "polygon",
        {
            "color": CLASSED,
            "stroke": {"color": {"fixed": "#112233"}, "width": {"fixed": 2}, "style": "dashed"},
        },
    ),
    ("polygon", {"color": CONTINUOUS}),
    ("line", {"color": CATEGORICAL}),
    ("point", {"size": {"field": "pop", "domain": {"min": 1, "max": 100}, "computedAt": "x"}}),
    ("point", None),
]


@pytest.mark.parametrize(("kind", "sym"), SIX)
def test_sld_valide_contre_xsd(sld_schema, kind, sym):
    xml = style_to_sld(style_from_symbology(sym, kind), layer_name="communes", title="Communes <1>")
    sld_schema.validate(xml)  # lève XMLSchemaValidationError si non conforme


def test_sld_echappe_les_valeurs():
    xml = style_to_sld(style_from_symbology({"color": CATEGORICAL}, "polygon"), layer_name="x")
    assert "b &amp; &lt;c&gt;" in xml and "b & <c>" not in xml


def test_sld_a_un_filtre_par_classe_et_un_repli():
    xml = style_to_sld(style_from_symbology({"color": CATEGORICAL}, "polygon"), layer_name="x")
    assert xml.count("<ogc:PropertyIsEqualTo>") == 3 and "<se:ElseFilter/>" in xml


def test_selection_de_regle():
    st = style_from_symbology({"color": CLASSED}, "polygon")
    assert select_rule(st, {"pop": 5}).fill != select_rule(st, {"pop": 50}).fill
    assert select_rule(st, {"pop": 5000}) is select_rule(
        st, {"pop": 999}
    )  # dernière classe ouverte
    cat = style_from_symbology({"color": CATEGORICAL}, "polygon")
    assert select_rule(cat, {"type": "zzz"}).title == "autres"


@pytest.mark.parametrize(
    "bad",
    [
        {"color": {"field": "x", "domain": {"kind": "categorical", "values": []}}},
        {"color": {"field": "x", "domain": {"kind": "numeric-classed", "breaks": [1, 1, 1]}}},
        {"color": {"field": "x", "domain": {"kind": "numeric", "min": "a", "max": 2}}},
        {"color": "rouge", "opacity": "beaucoup", "stroke": 3, "size": []},
        "n'importe quoi",
    ],
)
def test_symbologie_invalide_retombe_sur_le_defaut(bad):
    assert style_from_symbology(bad, "polygon").rules == default_style("polygon").rules


def test_palettes_miroir_du_shell():
    ts = (REPO / "shell/src/builder/widgets/palette.ts").read_text()
    for name, cols in model.CATEGORICAL.items():
        assert all(c in ts for c in cols), name
    for name, (low, high) in model.SEQUENTIAL.items():
        assert re.search(rf'"{name}":\s*{{[^}}]*{low}[^}}]*{high}', ts), name


def test_route_export_sld(sld_schema):
    from fastapi.testclient import TestClient

    from app.auth.dependency import get_current_user
    from app.main import create_app

    app = create_app()
    c = TestClient(app)
    body = {"symbology": {"color": CATEGORICAL}, "geometryKind": "polygon", "name": "communes"}
    assert c.post("/v1/styles/sld", json=body).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: object()
    r = c.post("/v1/styles/sld", json=body)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.ogc.sld+xml")
    sld_schema.validate(r.text)
    assert c.post("/v1/styles/sld", json={**body, "name": ""}).status_code == 422


def test_xsd_rejette_un_sld_casse(sld_schema):
    """Falsification : le validateur échoue bien sur un SLD non conforme."""
    xml = style_to_sld(default_style("polygon"), layer_name="x")
    with pytest.raises(xmlschema.XMLSchemaValidationError):
        sld_schema.validate(xml.replace("se:Fill>", "se:Fil>"))
