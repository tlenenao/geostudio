# SPDX-License-Identifier: Apache-2.0
"""ARC-27 : parsing XLSForm — fidélité (30 questions), rapport sans perte silencieuse, bornes."""

import io
import zipfile

import pytest
from openpyxl import Workbook

from app.xlsform import parser
from app.xlsform.parser import XlsFormError, parse_xlsform, to_cel


def _book(survey, choices=(), settings=None, extra_sheets=0):
    wb = Workbook()
    ws = wb.active
    ws.title = "survey"
    for r in survey:
        ws.append(list(r))
    if choices:
        c = wb.create_sheet("choices")
        for r in choices:
            c.append(list(r))
    if settings:
        s = wb.create_sheet("settings")
        for r in settings:
            s.append(list(r))
    for i in range(extra_sheets):
        wb.create_sheet(f"x{i}")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


HEAD = ("type", "name", "label", "hint", "required", "relevant", "constraint", "constraint_message")


def _thirty():
    rows = [HEAD]
    rows.append(("text", "nom", "Nom", "Votre nom", "yes", None, None, None))
    rows.append(
        ("integer", "age", "Âge", None, "yes", None, ". >= 0 and . <= 120", "Âge entre 0 et 120")
    )
    rows.append(("decimal", "surface", "Surface", None, None, None, ". > 0", "Surface positive"))
    rows.append(("date", "jour", "Date", None, None, None, None, None))
    rows.append(("datetime", "horodatage", "Horodatage", None, None, None, None, None))
    rows.append(("select_one etat", "etat", "État", None, "yes", None, None, None))
    rows.append(
        ("text", "motif", "Motif de dégradation", None, None, "${etat} = 'degrade'", None, None)
    )
    rows.append(
        (
            "integer",
            "gravite",
            "Gravité",
            None,
            None,
            "${etat} != 'bon' and ${age} > 18",
            None,
            None,
        )
    )
    rows.append(("select_multiple usages", "usages", "Usages", None, None, None, None, None))
    rows.append(("geopoint", "position", "Position", None, "yes", None, None, None))
    rows.append(("image", "photo", "Photo", None, None, None, None, None))
    rows.append(("acknowledge", "ok", "Je confirme", None, None, None, None, None))
    rows.append(("time", "heure", "Heure", None, None, None, None, None))
    for i in range(14, 31):
        rows.append(("text", f"champ_{i}", f"Champ {i}", None, None, None, None, None))
    return _book(
        rows,
        choices=[
            ("list_name", "name", "label"),
            ("etat", "bon", "Bon"),
            ("etat", "degrade", "Dégradé"),
            ("etat", "hs", "Hors service"),
            ("usages", "a", "A"),
            ("usages", "b", "B"),
        ],
        settings=[("form_title", "form_id"), ("Inspection des bancs", "bancs")],
    )


def test_thirty_questions_import_without_loss():
    plan = parse_xlsform(_thirty())
    assert plan.title == "Inspection des bancs"
    assert plan.geometry_type == "Point"
    by = {f["name"]: f for f in plan.form_fields}
    # 30 questions : 29 champs de formulaire + la géopoint (devenue géométrie de la collection)
    assert len(plan.form_fields) + 1 == 30
    types = {c["name"]: c["sqlType"] for c in plan.columns}
    assert types["nom"] == "text"
    assert types["age"] == "integer"
    assert types["surface"] == "double precision"
    assert types["jour"] == "date"
    assert types["horodatage"] == "timestamptz"
    assert types["ok"] == "boolean"
    assert by["photo"]["type"] == "attachment"
    assert plan.attachment_fields == [{"key": "photo", "label": "Photo"}]
    # liste de choix -> domaine
    assert plan.field_domains["etat"] == {"type": "list", "values": ["bon", "degrade", "hs"]}
    # relevant -> CEL
    assert by["motif"]["visibleWhen"] == "etat == 'degrade'"
    assert by["gravite"]["visibleWhen"] == "etat != 'bon' && age > 18"
    # required, hint, ordre
    assert by["nom"]["required"] is True and by["nom"]["hint"] == "Votre nom"
    assert [f["order"] for f in plan.form_fields] == sorted(f["order"] for f in plan.form_fields)
    # constraint -> règles ARC-14
    rules = {r["field"]: r for r in plan.attribute_rules}
    assert rules["age"]["expression"] == "age >= 0 && age <= 120"
    assert rules["age"]["message"] == "Âge entre 0 et 120"
    assert rules["surface"]["kind"] == "constraint"
    # rien de perdu en silence : les approximations sont déclarées
    msgs = " | ".join(r.message for r in plan.report)
    assert "choix multiple" in msgs and "heure stockée comme texte" in msgs
    assert not [r for r in plan.report if r.code == "not_ported"]


def test_unsupported_items_are_reported_never_silently_dropped():
    survey = [
        HEAD + ("default", "calculation"),
        ("text", "a", "A", None, None, "today() > ${b}", "regex(., '^[0-9]+$')", None, "x", None),
        ("text", "b", "B", None, None, None, None, None, None, None),
        ("calculate", "c", "C", None, None, None, None, None, None, "${b}"),
        ("note", "n", "Note", None, None, None, None, None, None, None),
        ("begin_repeat", "r", "R", None, None, None, None, None, None, None),
        ("text", "in_rep", "Dans repeat", None, None, None, None, None, None, None),
        ("end_repeat", None, None, None, None, None, None, None, None, None),
        ("geopoint", "g1", "G1", None, None, None, None, None, None, None),
        ("geopoint", "g2", "G2", None, None, None, None, None, None, None),
        ("hologram", "h", "H", None, None, None, None, None, None, None),
    ]
    plan = parse_xlsform(_book(survey))
    rep = {(r.name, r.code): r.message for r in plan.report}
    assert "relevant non porté" in rep[("a", "not_ported")] or any(
        r.name == "a" and "relevant" in r.message for r in plan.report
    )
    assert any(r.name == "a" and "constraint" in r.message for r in plan.report)
    assert any(r.name == "a" and "default" in r.message for r in plan.report)
    for n in ("c", "n", "r", "in_rep", "g2", "h"):
        assert any(r.name == n for r in plan.report), n
    assert "visibleWhen" not in next(f for f in plan.form_fields if f["name"] == "a")
    assert plan.attribute_rules == []


def test_names_are_sanitized_and_reserved_names_renamed():
    survey = [HEAD, ("text", "id", "Id", *[None] * 5), ("text", "a-b.c", "ABC", *[None] * 5)]
    plan = parse_xlsform(_book(survey))
    names = [c["name"] for c in plan.columns]
    assert names == ["id_q", "a_b_c"]
    assert sum(r.code == "renamed" for r in plan.report) == 2


@pytest.mark.parametrize(
    "xpath,cel",
    [
        ("${a} = 'x' or ${b} = 'y'", "a == 'x' || b == 'y'"),
        ("not(${a} = 'x')", "!(a == 'x')"),
        ("selected(${a}, 'x')", "(a == 'x')"),
        ("${n} >= 0.5", "n >= 0.5"),
        ("${a} = 'a = b and c'", "a == 'a = b and c'"),
    ],
)
def test_to_cel(xpath, cel):
    names = {"a": "a", "b": "b", "n": "n"}
    assert to_cel(xpath, names) == cel


def test_to_cel_rejects_unknown_references_and_functions():
    for bad in ("${zz} = 1", "today() = 1", "${a} div 2 = 1"):
        with pytest.raises(Exception):  # noqa: B017 - _Unsupported est interne
            to_cel(bad, {"a": "a"})


# --- fichier non fiable ---------------------------------------------------------------------


def test_not_an_xlsform_and_garbage_are_clean_errors():
    with pytest.raises(XlsFormError):
        parse_xlsform(b"pas un zip")
    wb = Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(XlsFormError, match="survey"):
        parse_xlsform(buf.getvalue())


def test_bounds(monkeypatch):
    with pytest.raises(XlsFormError, match="volumineux"):
        parse_xlsform(b"x" * (parser.MAX_BYTES + 1))
    monkeypatch.setattr(parser, "MAX_SURVEY_ROWS", 3)
    rows = [HEAD] + [("text", f"q{i}", "Q", *[None] * 5) for i in range(10)]
    with pytest.raises(XlsFormError, match="lignes"):
        parse_xlsform(_book(rows))
    monkeypatch.setattr(parser, "MAX_SHEETS", 2)
    with pytest.raises(XlsFormError, match="feuilles"):
        parse_xlsform(_book([HEAD, ("text", "q", "Q", *[None] * 5)], extra_sheets=3))
    monkeypatch.setattr(parser, "MAX_CELL", 5)
    with pytest.raises(XlsFormError, match="trop longue"):
        parse_xlsform(_book([HEAD, ("text", "q", "x" * 50, *[None] * 5)]))


def test_decompressed_size_bomb_is_refused(monkeypatch):
    monkeypatch.setattr(parser, "MAX_UNCOMPRESSED", 100)
    with pytest.raises(XlsFormError, match="décompressé"):
        parse_xlsform(_thirty())


def test_formulas_are_never_evaluated():
    wb = Workbook()
    ws = wb.active
    ws.title = "survey"
    ws.append(list(HEAD))
    ws.append(["text", "q", "=1+1", None, None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    plan = parse_xlsform(buf.getvalue())
    # data_only : une formule jamais calculée (pas de cache Excel) vaut vide, jamais 2
    assert plan.form_fields[0]["label"] in ("q", "=1+1")
    assert plan.form_fields[0]["label"] != "2"


def test_xxe_payload_is_refused_cleanly():
    good = _book([HEAD, ("text", "q", "Q", *[None] * 5)])
    src = zipfile.ZipFile(io.BytesIO(good))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.endswith("sheet1.xml"):
                data = (
                    b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
                    + data
                )
            dst.writestr(item, data)
    # defusedxml (via openpyxl) refuse l'entité : erreur propre, jamais de contenu local lu
    with pytest.raises(XlsFormError, match="illisible"):
        parse_xlsform(out.getvalue())
