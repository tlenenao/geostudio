# SPDX-License-Identifier: Apache-2.0
"""Mode de fraîcheur du bilan (REV-181).

`--check` (déjà existant) calcule les planchers de santé/priorité — il ne dit
rien sur le fait que `docs/revue/bilan-fonctionnalites.{html,md}` committés
aient bien été régénérés après le dernier changement de code/inventaire.
`--check-fresh` est un mode DIFFÉRENT : il recalcule les deux rendus en
mémoire et les diffe contre les fichiers committés.

Piège évité (pas un détail d'implémentation, une propriété vérifiée) : le
journal `historique-sante.jsonl` a déjà avancé d'un cran par rapport à
l'état qui a produit le rendu committé — `history.append_snapshot()` est
appelé par `--write` dans le même passage qui écrit `previous`. Recalculer
`previous` via `history.last_snapshot()` à `--check-fresh` donnerait donc le
**nouveau** relevé, pas l'ancien, et ferait toujours matcher un delta à zéro.
`_extract_committed_metadata` reconstruit `previous` directement depuis le
rendu committé (`previous[id] = sante - delta`), jamais depuis le journal."""

import pathlib

from scripts import feature_health_cli
from scripts.feature_health import render_html, render_md
from scripts.feature_health.model import Feature, SubScore


def _row(identifier="f1", health=60.0, priority="haute"):
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
        priority_source="declaree",
        raw={},
    )
    return {
        "feature": feature,
        "sante": health,
        "sous_scores": {
            "tests": SubScore(94.2, {}),
            "atteignabilite": SubScore(100.0, {}),
            "garde": SubScore(50.0, {}),
            "dette": SubScore(80.0, {}),
        },
        "qualite": {
            "typage_strict": False,
            "exemptions_de_couches": [],
            "eslint_disable": [],
            "echappatoires_de_typage": [],
        },
        "rang": 120.0,
    }


def _write_committed(repo: pathlib.Path, rows, *, previous, date, commit) -> None:
    (repo / "docs/revue").mkdir(parents=True, exist_ok=True)
    (repo / "docs/revue/bilan-fonctionnalites.md").write_text(
        render_md.render(rows, previous=previous, date=date), encoding="utf-8"
    )
    (repo / "docs/revue/bilan-fonctionnalites.html").write_text(
        render_html.render(rows, previous=previous, date=date, commit=commit), encoding="utf-8"
    )


def test_check_fresh_passes_when_nothing_changed(tmp_path):
    rows = [_row("a", health=60.0), _row("b", health=80.0)]
    _write_committed(tmp_path, rows, previous={"a": 48.0}, date="2026-09-07", commit="abc123")
    assert feature_health_cli._check_fresh(rows, tmp_path) == 0


def test_check_fresh_fails_when_a_health_score_drifted(tmp_path):
    rows = [_row("a", health=60.0), _row("b", health=80.0)]
    _write_committed(tmp_path, rows, previous={"a": 48.0}, date="2026-09-07", commit="abc123")
    drifted = [_row("a", health=61.0), _row("b", health=80.0)]
    assert feature_health_cli._check_fresh(drifted, tmp_path) == 1


def test_check_fresh_fails_when_the_markdown_was_hand_edited_without_regenerating(tmp_path):
    rows = [_row("a", health=60.0)]
    _write_committed(tmp_path, rows, previous={}, date="2026-09-07", commit="abc123")
    md_path = tmp_path / "docs/revue/bilan-fonctionnalites.md"
    md_path.write_text(md_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert feature_health_cli._check_fresh(rows, tmp_path) == 1


def test_extract_committed_metadata_reconstructs_previous_from_the_delta(tmp_path):
    # Propriété centrale du module : previous vient du rendu committé
    # (sante - delta), jamais de history.last_snapshot() (qui aurait déjà
    # avancé d'un cran, cf. docstring du module).
    rows = [_row("a", health=60.0)]
    _write_committed(tmp_path, rows, previous={"a": 48.0}, date="2026-09-07", commit="abc123")
    date, commit, previous = feature_health_cli._extract_committed_metadata(tmp_path)
    assert date == "2026-09-07"
    assert commit == "abc123"
    assert previous == {"a": 48.0}
