# SPDX-License-Identifier: Apache-2.0
"""Rendu HTML du bilan — le produit de suivi central (SP-61, spec §7.1).

Contraintes de forme héritées de l'artefact SP-42, à conserver : un seul
fichier, aucune étape de compilation, données embarquées en
`<script type="application/json">`, CSS et JS inline, une seule dépendance
externe (Google Fonts, avec pile de repli réelle), thème clair/sombre par
`prefers-color-scheme` **et** `[data-theme]` explicite. Pas de CDN de
librairie, pas de graphique tiers."""

from __future__ import annotations

import json
import pathlib
import statistics
from collections.abc import Iterable

ASSETS = pathlib.Path(__file__).parent / "assets"
FONTS = (
    "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,"
    "400;9..144,500;9..144,600;9..144,700&family=Public+Sans:wght@400;500;"
    "600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
)


def _payload(rows, previous, date, commit) -> dict:
    features = []
    for row in rows:
        feature = row["feature"]
        health = row["sante"]
        features.append(
            {
                "id": feature.identifier,
                "domaine": feature.domain,
                "fonctionnalite": feature.name,
                "sante": health,
                "delta": (
                    None
                    if health is None or feature.identifier not in previous
                    else round(health - previous[feature.identifier], 1)
                ),
                "priorite": feature.priority,
                "priorite_source": feature.priority_source,
                "sous_scores": {
                    name: {"valeur": score.value, "preuve": score.evidence}
                    for name, score in row["sous_scores"].items()
                },
                "qualite": row["qualite"],
                "rang": row["rang"],
                "preuve": list(feature.proofs),
                "surfaces": {
                    "rest": list(feature.rest),
                    "mcp": list(feature.mcp),
                    "shell": list(feature.shell),
                },
            }
        )
    measured = [item["sante"] for item in features if item["sante"] is not None]
    return {
        "date": date,
        "commit": commit,
        "sante_mediane": statistics.median(measured) if measured else None,
        "fonctionnalites": sorted(features, key=lambda item: item["rang"], reverse=True),
    }


def render(rows: Iterable[dict], *, previous: dict[str, float], date: str, commit: str) -> str:
    payload = _payload(list(rows), previous, date, commit)
    css = (ASSETS / "bilan.css").read_text(encoding="utf-8")
    script = (ASSETS / "bilan.js").read_text(encoding="utf-8")
    body = (ASSETS / "bilan-body.html").read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return (
        "<!doctype html><html><head><meta charset=utf8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        "<title>Bilan GeoStudio</title>"
        f'<link rel="stylesheet" href="{FONTS}">'
        f"<style>{css}</style></head><body>\n"
        f"{body}\n"
        f'<script type="application/json" id="bilan-data">{data}</script>\n'
        f"<script>{script}</script>\n"
        "</body></html>\n"
    )
