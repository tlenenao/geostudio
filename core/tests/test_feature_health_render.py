# SPDX-License-Identifier: Apache-2.0
"""Rendus Markdown et HTML du bilan (SP-61, spec §7.1).

Propriété centrale : les deux sorties viennent de la **même source dans le même
passage** — elles ne peuvent pas se contredire parce qu'aucune n'est écrite à
la main."""

import json
import pathlib
import re

from scripts.feature_health import render_html, render_md
from scripts.feature_health.model import Feature, SubScore

REPO = pathlib.Path(__file__).resolve().parents[2]


def _row(identifier="f1", health=60.0, priority="haute", priority_source="amorcage-sp42"):
    feature = Feature(
        identifier=identifier,
        domain="Catalogue",
        name="Lister les items",
        proofs=("core/app/items/routes.py",),
        rest=("GET /v1/items",),
        mcp=(),
        shell=(),
        public=(),
        priority=priority,
        priority_source=priority_source,
        raw={},
    )
    return {
        "feature": feature,
        "sante": health,
        "sous_scores": {
            "tests": SubScore(94.2, {"core/app/items/routes.py": "94.2 % de lignes couvertes"}),
            "atteignabilite": SubScore(100.0, {"GET /v1/items": "montée"}),
            "garde": SubScore(50.0, {"GET /v1/items": "authentification seule"}),
            "dette": SubScore(80.0, {"REV-042": "important"}),
        },
        "qualite": {
            "typage_strict": False,
            "exemptions_de_couches": [],
            "eslint_disable": [],
            "echappatoires_de_typage": [],
        },
        "rang": 120.0,
    }


def test_markdown_carries_one_row_per_feature():
    output = render_md.render([_row("a"), _row("b")], previous={}, date="2026-09-07")
    assert output.count("| Catalogue |") == 2


def test_markdown_shows_health_and_priority_in_separate_columns():
    output = render_md.render([_row()], previous={}, date="2026-09-07")
    header = next(line for line in output.splitlines() if line.startswith("| Domaine"))
    assert "Santé" in header and "Priorité" in header
    assert "note globale" not in output.lower()


def test_markdown_shows_the_delta_against_the_previous_snapshot():
    output = render_md.render([_row(health=60.0)], previous={"f1": 48.0}, date="2026-09-07")
    assert "+12" in output


def test_html_embeds_its_data_as_json():
    output = render_html.render([_row()], previous={}, date="2026-09-07", commit="abc123")
    payload = re.search(
        r'<script type="application/json" id="bilan-data">(.*?)</script>', output, re.S
    )
    assert payload is not None
    data = json.loads(payload.group(1))
    assert data["fonctionnalites"][0]["id"] == "f1"
    assert data["fonctionnalites"][0]["sous_scores"]["garde"]["valeur"] == 50.0
    assert data["commit"] == "abc123"


def test_html_has_no_external_dependency_but_the_font_stylesheet():
    """Contrainte de forme héritée de l'artefact : un seul fichier, aucune
    étape de compilation, aucun CDN de librairie (spec §7.1)."""
    output = render_html.render([_row()], previous={}, date="2026-09-07", commit="abc")
    assert "<script src=" not in output
    external = re.findall(r'<link[^>]+href="(https?://[^"]+)"', output)
    assert external == [
        "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,"
        "400;9..144,500;9..144,600;9..144,700&family=Public+Sans:wght@400;500;"
        "600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
    ]


def test_html_keeps_the_dark_theme_of_the_reference_artefact():
    output = render_html.render([_row()], previous={}, date="2026-09-07", commit="abc")
    assert "@media (prefers-color-scheme: dark)" in output
    assert '[data-theme="dark"]' in output


def test_html_and_markdown_never_diverge():
    rows = [_row("a", health=60.0), _row("b", health=90.0)]
    markdown = render_md.render(rows, previous={}, date="2026-09-07")
    html = render_html.render(rows, previous={}, date="2026-09-07", commit="abc")
    data = json.loads(re.search(r'id="bilan-data">(.*?)</script>', html, re.S).group(1))
    from_html = {item["id"]: item["sante"] for item in data["fonctionnalites"]}
    from_md = {
        match.group(1): float(match.group(2))
        for match in re.finditer(r"\| `([a-z0-9-]+)` \| ([0-9.]+) \|", markdown)
    }
    assert from_html == from_md


def test_markdown_flags_a_priority_never_manually_reviewed():
    # REV-180 : la (grande) majorité des priorités vient de l'amorçage SP-42,
    # jamais revue manuellement — rien ne le signalait avant ce correctif.
    output = render_md.render(
        [_row(priority_source="amorcage-sp42")], previous={}, date="2026-09-07"
    )
    row_line = next(line for line in output.splitlines() if line.startswith("| Catalogue |"))
    assert "(amorcée)" in row_line


def test_markdown_does_not_flag_a_manually_reviewed_priority():
    output_declaree = render_md.render(
        [_row(priority_source="declaree")], previous={}, date="2026-09-07"
    )
    output_sp61 = render_md.render(
        [_row(priority_source="manuel-sp61")], previous={}, date="2026-09-07"
    )
    for output in (output_declaree, output_sp61):
        row_line = next(line for line in output.splitlines() if line.startswith("| Catalogue |"))
        assert "(amorcée)" not in row_line


def test_html_javascript_distinguishes_reviewed_priority_sources():
    # bilan.js (REV-180) : seules les priorités jamais revues manuellement
    # ("amorcage-sp42" et tout futur amorçage automatique — tout ce qui
    # n'est ni "declaree" ni "manuel-sp61") sont nuancées visuellement.
    output = render_html.render([_row()], previous={}, date="2026-09-07", commit="abc")
    assert '"declaree"' in output
    assert '"manuel-sp61"' in output
    assert "encore amorc" in output.lower()


def test_the_committed_html_is_a_single_self_contained_file():
    """Le produit livré, pas seulement la fonction de rendu."""
    output = (REPO / "docs/revue/bilan-fonctionnalites.html").read_text(encoding="utf-8")
    assert "<style>" in output and 'id="bilan-data"' in output
    assert "node_modules" not in output
