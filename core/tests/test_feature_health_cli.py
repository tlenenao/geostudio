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


# `floor_median` est volontairement abaissé à 40.0 dans les deux tests
# « passants » ci-dessous : une seule ligne à 90.0/82.6 donnerait une médiane
# sous un plancher réaliste, et l'échec de médiane masquerait la propriété
# réellement testée (le plancher par priorité).
def test_check_fails_a_medium_priority_feature_under_its_own_floor(capsys):
    from scripts.feature_health.scoring import Thresholds

    rows = [_row(identifier="f1", health=85.0, priority="moyenne")]
    thresholds = Thresholds(
        weights={"tests": 0.30, "atteignabilite": 0.25, "garde": 0.25, "dette": 0.20},
        floor_high_priority=90.0,
        floor_medium_priority=90.0,
        floor_median=96.0,
    )
    exit_code = feature_health_cli._check(rows, thresholds)
    assert exit_code == 1
    assert "f1 : santé 85.0 < plancher 90.0" in capsys.readouterr().err


def test_check_passes_a_medium_priority_feature_at_its_floor(capsys):
    from scripts.feature_health.scoring import Thresholds

    rows = [_row(identifier="f1", health=90.0, priority="moyenne")]
    thresholds = Thresholds(
        weights={"tests": 0.30, "atteignabilite": 0.25, "garde": 0.25, "dette": 0.20},
        floor_high_priority=90.0,
        floor_medium_priority=90.0,
        floor_median=40.0,
    )
    assert feature_health_cli._check(rows, thresholds) == 0


def test_check_exempts_a_named_medium_priority_exception(capsys):
    """`catalogue-mes-vues-signets` (spec §4.bis) reste durablement sous le
    plancher moyenne — sans cette exception nommée, --check échouerait pour
    toujours sur cette seule ligne, contrairement à l'intention documentée
    (exception assumée, pas une régression à corriger)."""
    from scripts.feature_health.scoring import Thresholds

    rows = [_row(identifier="catalogue-mes-vues-signets", health=82.6, priority="moyenne")]
    thresholds = Thresholds(
        weights={"tests": 0.30, "atteignabilite": 0.25, "garde": 0.25, "dette": 0.20},
        floor_high_priority=90.0,
        floor_medium_priority=90.0,
        floor_median=40.0,
        exceptions_medium_priority=frozenset({"catalogue-mes-vues-signets"}),
    )
    assert feature_health_cli._check(rows, thresholds) == 0
    assert capsys.readouterr().err == ""


def test_check_exception_does_not_apply_outside_priorite_moyenne(capsys):
    """L'exception nommée n'exempte que `priorite: moyenne` — un même
    identifiant listé mais déclaré `priorite: haute` (simple édition JSONL,
    aucun changement de code) doit rester gardé par le plancher haute
    priorité, pas silencieusement dispensé de tout plancher (piège de
    gate erosion identifié en revue finale de Task 12)."""
    from scripts.feature_health.scoring import Thresholds

    rows = [_row(identifier="catalogue-mes-vues-signets", health=50.0, priority="haute")]
    thresholds = Thresholds(
        weights={"tests": 0.30, "atteignabilite": 0.25, "garde": 0.25, "dette": 0.20},
        floor_high_priority=90.0,
        floor_medium_priority=90.0,
        floor_median=40.0,
        exceptions_medium_priority=frozenset({"catalogue-mes-vues-signets"}),
    )
    assert feature_health_cli._check(rows, thresholds) == 1
    assert "catalogue-mes-vues-signets" in capsys.readouterr().err
