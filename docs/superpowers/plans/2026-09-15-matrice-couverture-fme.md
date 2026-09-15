# Matrice de couverture FME→GeoStudio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produire un inventaire rejouable des transformers FME (`docs/revue/matrice-couverture-fme.jsonl` + rendu `.md`), avec un script de vérification mécanique (`core/scripts/fme_coverage_cli.py`) qui garantit que la colonne « déjà implémenté aujourd'hui » ne ment jamais.

**Architecture:** Un seul fichier CLI (pas de package, contrairement à `feature_health_cli.py` — le design impose délibérément « beaucoup plus simple ») : parsing JSONL → 3 règles de vérification mécanique contre le code réel du dépôt (`ops_catalog()`, `QGIS_ALGORITHMS`) → rendu markdown généré. Puis remplissage des données par recherche web, catégorie FME par catégorie FME.

**Tech Stack:** Python stdlib (`argparse`, `json`, `dataclasses`, `collections.Counter`), pytest, imports directs de `app.pipelines.ops.schemas`/`app.pipelines.ops.qgis_algorithms` (déjà sur le PYTHONPATH de pytest via `pythonpath = ["."]` dans `core/pyproject.toml`).

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-15-matrice-couverture-fme-design.md` — toute divergence avec ce plan se résout en faveur de la spec, à signaler en revue.
- **Aucune modification de `core/app/pipelines/`** — ce plan ne lit ces modules qu'en import, ne les modifie jamais.
- Politique de licence stricte : MIT/BSD/Apache/EDL uniquement pour tout nouveau moteur candidat. Le sidecar QGIS existant (50 algos, GPL) est une **exception historique figée** : aucun nouveau transformer FME n'y est routé dans ce plan.
- Taxonomie `coverage_status` fermée à 10 valeurs (cf. Task 1) — ne jamais en introduire une nouvelle sans revenir amender la spec.
- Pas de porte CI : `--check` n'est appelé dans aucun job de `ci.yml`.
- Document vivant, **pas de date dans le nom de fichier** : `docs/revue/matrice-couverture-fme.jsonl` / `.md`.
- Gotcha `PYTHONPATH=.` : la commande nue échoue en `ModuleNotFoundError` — documenté dans le docstring du script (pas seulement ici).
- Commits conventionnels (`feat(core): …`, `docs(revue): …`), un sujet par commit.
- TDD pour le script (Tasks 1-5) ; **pas de TDD sur le contenu des données** (Tasks 6-11, jugement humain/recherche, non testable unitairement) — leur porte de qualité est `--check` passant avant chaque commit.

---

### Task 1: Modèle `Row` + parsing JSONL

**Files:**
- Create: `core/scripts/fme_coverage_cli.py`
- Create: `core/tests/test_fme_coverage_cli.py`

**Interfaces:**
- Produces: `Row` (dataclass frozen, champs `fme_transformer: str`, `fme_category: str`, `fme_description: str`, `geostudio_equivalent: str | None`, `engine: str`, `engine_license: str`, `coverage_status: str`, `usage_frequency: str`, `notes: str`), `Row.from_dict(data: dict) -> Row`, `load_rows(path: pathlib.Path) -> list[Row]`, constante `_VALID_STATUSES: set[str]` (10 valeurs).

- [ ] **Step 1: Écrire le test qui échoue**

Créer `core/tests/test_fme_coverage_cli.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import json
import pathlib

import pytest

from scripts.fme_coverage_cli import Row, load_rows


def _write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


def test_load_rows_parses_valid_jsonl(tmp_path):
    path = tmp_path / "matrice.jsonl"
    _write_jsonl(
        path,
        [
            {
                "fme_transformer": "Reprojector",
                "fme_category": "Geometry",
                "fme_description": "Reprojects features",
                "geostudio_equivalent": "transform.reproject",
                "engine": "duckdb",
                "engine_license": "MIT",
                "coverage_status": "implemented",
                "usage_frequency": "courant",
                "notes": "",
            }
        ],
    )
    rows = load_rows(path)
    assert rows == [
        Row(
            fme_transformer="Reprojector",
            fme_category="Geometry",
            fme_description="Reprojects features",
            geostudio_equivalent="transform.reproject",
            engine="duckdb",
            engine_license="MIT",
            coverage_status="implemented",
            usage_frequency="courant",
            notes="",
        )
    ]


def test_load_rows_rejects_unknown_coverage_status(tmp_path):
    path = tmp_path / "matrice.jsonl"
    _write_jsonl(
        path,
        [
            {
                "fme_transformer": "X",
                "fme_category": "Geometry",
                "fme_description": "d",
                "geostudio_equivalent": None,
                "engine": "n/a",
                "engine_license": "",
                "coverage_status": "not_a_real_status",
                "usage_frequency": "inconnu",
                "notes": "",
            }
        ],
    )
    with pytest.raises(ValueError, match="coverage_status inconnu"):
        load_rows(path)


def test_load_rows_reports_malformed_json_with_line_number(tmp_path):
    path = tmp_path / "matrice.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"matrice\.jsonl:1"):
        load_rows(path)
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_fme_coverage_cli.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'scripts.fme_coverage_cli'`

- [ ] **Step 3: Écrire l'implémentation minimale**

Créer `core/scripts/fme_coverage_cli.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Matrice de couverture FME→GeoStudio (design 2026-09-15) — CLI léger, sans
scoring ni porte CI, patron simplifié de scripts/feature_health_cli.py.

    PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --check
    PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --write

La commande nue échoue en ModuleNotFoundError sans PYTHONPATH=. — même
gotcha que feature_health_cli.py/export_openapi.py, à ne pas répéter une 3e
fois sans avertissement inline.

--check vérifie mécaniquement les 3 règles du design (cf. docs/superpowers/
specs/2026-09-15-matrice-couverture-fme-design.md) contre le code réel du
dépôt (`app.pipelines.ops.schemas.ops_catalog`, `app.pipelines.ops.
qgis_algorithms.QGIS_ALGORITHMS`) — jamais contre une copie déclarée dans le
JSONL lui-même. --write régénère docs/revue/matrice-couverture-fme.md depuis
le JSONL. Pas de porte CI : --check n'est appelé dans aucun job de ci.yml,
ce n'est pas une surface produit."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import dataclass

JSONL = "docs/revue/matrice-couverture-fme.jsonl"
RENDERED_MD = "docs/revue/matrice-couverture-fme.md"

_VALID_STATUSES = {
    "implemented",
    "planned_duckdb",
    "planned_gdal",
    "planned_pdal",
    "planned_otb",
    "planned_rust",
    "qgis_frozen",
    "license_blocked",
    "out_of_scope",
    "unknown",
}


@dataclass(frozen=True)
class Row:
    fme_transformer: str
    fme_category: str
    fme_description: str
    geostudio_equivalent: str | None
    engine: str
    engine_license: str
    coverage_status: str
    usage_frequency: str
    notes: str

    @staticmethod
    def from_dict(data: dict) -> "Row":
        status = data["coverage_status"]
        if status not in _VALID_STATUSES:
            raise ValueError(
                f"{data.get('fme_transformer', '?')!r} : coverage_status "
                f"inconnu {status!r}"
            )
        return Row(
            fme_transformer=data["fme_transformer"],
            fme_category=data["fme_category"],
            fme_description=data["fme_description"],
            geostudio_equivalent=data.get("geostudio_equivalent"),
            engine=data["engine"],
            engine_license=data["engine_license"],
            coverage_status=status,
            usage_frequency=data["usage_frequency"],
            notes=data.get("notes", ""),
        )


def load_rows(path: pathlib.Path) -> list[Row]:
    rows: list[Row] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno} : JSON invalide ({exc})") from exc
        rows.append(Row.from_dict(data))
    return rows
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_fme_coverage_cli.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/scripts/fme_coverage_cli.py core/tests/test_fme_coverage_cli.py
git commit -m "feat(core): ajoute le parsing JSONL de la matrice de couverture FME"
```

---

### Task 2: Règle de vérification 1 — `implemented`/`duckdb` contre `ops_catalog()`

**Files:**
- Modify: `core/scripts/fme_coverage_cli.py`
- Modify: `core/tests/test_fme_coverage_cli.py`

**Interfaces:**
- Consumes: `Row` (Task 1)
- Produces: `check_rows(rows: list[Row], *, ops: dict, qgis_algorithms: dict) -> list[str]`

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `core/tests/test_fme_coverage_cli.py` :

```python
from scripts.fme_coverage_cli import check_rows


def _row(**overrides) -> Row:
    base = dict(
        fme_transformer="Reprojector",
        fme_category="Geometry",
        fme_description="d",
        geostudio_equivalent="transform.reproject",
        engine="duckdb",
        engine_license="MIT",
        coverage_status="implemented",
        usage_frequency="courant",
        notes="",
    )
    base.update(overrides)
    return Row(**base)


def test_check_rows_accepts_existing_duckdb_op():
    rows = [_row(geostudio_equivalent="transform.reproject")]
    errors = check_rows(rows, ops={"transform.reproject": {}}, qgis_algorithms={})
    assert errors == []


def test_check_rows_rejects_unknown_duckdb_op():
    rows = [_row(geostudio_equivalent="transform.nonexistent")]
    errors = check_rows(rows, ops={"transform.reproject": {}}, qgis_algorithms={})
    assert len(errors) == 1
    assert "transform.nonexistent" in errors[0]
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_fme_coverage_cli.py -v`
Expected: FAIL avec `ImportError: cannot import name 'check_rows'`

- [ ] **Step 3: Écrire l'implémentation minimale**

Ajouter à `core/scripts/fme_coverage_cli.py` :

```python
def check_rows(rows: list[Row], *, ops: dict, qgis_algorithms: dict) -> list[str]:
    errors: list[str] = []
    for row in rows:
        if row.coverage_status == "implemented" and row.engine == "duckdb":
            if row.geostudio_equivalent not in ops:
                errors.append(
                    f"{row.fme_transformer!r} : geostudio_equivalent "
                    f"{row.geostudio_equivalent!r} n'existe pas dans ops_catalog()"
                )
    return errors
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_fme_coverage_cli.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/scripts/fme_coverage_cli.py core/tests/test_fme_coverage_cli.py
git commit -m "feat(core): vérifie les op DuckDB implémentés contre ops_catalog()"
```

---

### Task 3: Règle de vérification 2 — `qgis_frozen` contre `QGIS_ALGORITHMS`

**Files:**
- Modify: `core/scripts/fme_coverage_cli.py`
- Modify: `core/tests/test_fme_coverage_cli.py`

**Interfaces:**
- Consumes: `check_rows` (Task 2, étendue ici)
- Produces: `check_rows` étendue (même signature, règle 2 ajoutée)

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `core/tests/test_fme_coverage_cli.py` :

```python
def test_check_rows_accepts_existing_qgis_algorithm():
    rows = [
        _row(
            engine="qgis",
            coverage_status="qgis_frozen",
            geostudio_equivalent="gdal:contour",
        )
    ]
    errors = check_rows(rows, ops={}, qgis_algorithms={"gdal:contour": {}})
    assert errors == []


def test_check_rows_rejects_unknown_qgis_algorithm():
    rows = [
        _row(
            engine="qgis",
            coverage_status="qgis_frozen",
            geostudio_equivalent="qgis:doesnotexist",
        )
    ]
    errors = check_rows(rows, ops={}, qgis_algorithms={"gdal:contour": {}})
    assert len(errors) == 1
    assert "qgis:doesnotexist" in errors[0]
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_fme_coverage_cli.py -v`
Expected: FAIL — `test_check_rows_rejects_unknown_qgis_algorithm` échoue (`errors == []` au lieu de longueur 1), la règle qgis n'existe pas encore.

- [ ] **Step 3: Écrire l'implémentation minimale**

Remplacer le corps de `check_rows` dans `core/scripts/fme_coverage_cli.py` :

```python
def check_rows(rows: list[Row], *, ops: dict, qgis_algorithms: dict) -> list[str]:
    errors: list[str] = []
    for row in rows:
        if row.coverage_status == "implemented" and row.engine == "duckdb":
            if row.geostudio_equivalent not in ops:
                errors.append(
                    f"{row.fme_transformer!r} : geostudio_equivalent "
                    f"{row.geostudio_equivalent!r} n'existe pas dans ops_catalog()"
                )
        if row.engine == "qgis":
            if row.geostudio_equivalent not in qgis_algorithms:
                errors.append(
                    f"{row.fme_transformer!r} : geostudio_equivalent "
                    f"{row.geostudio_equivalent!r} n'existe pas dans QGIS_ALGORITHMS"
                )
    return errors
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_fme_coverage_cli.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add core/scripts/fme_coverage_cli.py core/tests/test_fme_coverage_cli.py
git commit -m "feat(core): vérifie les algorithmes QGIS gelés contre QGIS_ALGORITHMS"
```

---

### Task 4: Règle de vérification 3 — rejet des moteurs pas encore intégrés marqués `implemented`

**Files:**
- Modify: `core/scripts/fme_coverage_cli.py`
- Modify: `core/tests/test_fme_coverage_cli.py`

**Interfaces:**
- Consumes: `check_rows` (Task 3, étendue ici)
- Produces: `check_rows` étendue (même signature, règle 3 ajoutée) — dernière règle du design, `check_rows` est complète après cette tâche.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `core/tests/test_fme_coverage_cli.py` :

```python
def test_check_rows_rejects_premature_gdal_engine_claim():
    rows = [
        _row(
            engine="gdal",
            coverage_status="implemented",
            geostudio_equivalent="reader.gdal.whatever",
        )
    ]
    errors = check_rows(rows, ops={}, qgis_algorithms={})
    assert len(errors) == 1
    assert "gdal" in errors[0]


def test_check_rows_rejects_premature_rust_engine_claim():
    rows = [
        _row(
            engine="rust:geo",
            coverage_status="implemented",
            geostudio_equivalent="transform.something",
        )
    ]
    errors = check_rows(rows, ops={}, qgis_algorithms={})
    assert len(errors) == 1
    assert "rust:geo" in errors[0]


def test_check_rows_accepts_planned_status_for_new_engine():
    rows = [
        _row(
            engine="gdal",
            coverage_status="planned_gdal",
            geostudio_equivalent="reader.gdal.whatever",
        )
    ]
    errors = check_rows(rows, ops={}, qgis_algorithms={})
    assert errors == []
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_fme_coverage_cli.py -v`
Expected: FAIL — les deux tests `rejects_premature_*` échouent (`errors == []` au lieu de longueur 1), la règle 3 n'existe pas encore.

- [ ] **Step 3: Écrire l'implémentation minimale**

Remplacer le corps de `check_rows` dans `core/scripts/fme_coverage_cli.py` :

```python
_NOT_YET_INTEGRATED_ENGINES = ("gdal", "pdal", "otb")


def check_rows(rows: list[Row], *, ops: dict, qgis_algorithms: dict) -> list[str]:
    errors: list[str] = []
    for row in rows:
        if row.coverage_status == "implemented" and row.engine == "duckdb":
            if row.geostudio_equivalent not in ops:
                errors.append(
                    f"{row.fme_transformer!r} : geostudio_equivalent "
                    f"{row.geostudio_equivalent!r} n'existe pas dans ops_catalog()"
                )
        if row.engine == "qgis":
            if row.geostudio_equivalent not in qgis_algorithms:
                errors.append(
                    f"{row.fme_transformer!r} : geostudio_equivalent "
                    f"{row.geostudio_equivalent!r} n'existe pas dans QGIS_ALGORITHMS"
                )
        if row.coverage_status == "implemented" and (
            row.engine in _NOT_YET_INTEGRATED_ENGINES or row.engine.startswith("rust:")
        ):
            errors.append(
                f"{row.fme_transformer!r} : coverage_status=implemented avec "
                f"engine={row.engine!r}, mais ce moteur n'est pas encore intégré "
                "dans core/app/pipelines/ — utiliser planned_* jusqu'à ce que le "
                "sous-projet moteur correspondant ait livré"
            )
    return errors
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_fme_coverage_cli.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add core/scripts/fme_coverage_cli.py core/tests/test_fme_coverage_cli.py
git commit -m "feat(core): rejette toute couverture prématurée par un moteur pas encore intégré"
```

---

### Task 5: Rendu markdown + CLI `--check`/`--write`

**Files:**
- Modify: `core/scripts/fme_coverage_cli.py`
- Modify: `core/tests/test_fme_coverage_cli.py`

**Interfaces:**
- Consumes: `Row`, `load_rows`, `check_rows` (Tasks 1-4), `app.pipelines.ops.schemas.ops_catalog() -> dict[str, dict]`, `app.pipelines.ops.qgis_algorithms.QGIS_ALGORITHMS: dict[str, dict]` (imports réels du cœur, déjà vérifiés dans cette session)
- Produces: `render_md(rows: list[Row]) -> str`, `main(argv: list[str]) -> int`

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `core/tests/test_fme_coverage_cli.py` :

```python
from scripts.fme_coverage_cli import main, render_md


def test_render_md_contains_summary_and_detail():
    rows = [_row()]
    rendered = render_md(rows)
    assert "Reprojector" in rendered
    assert "`implemented`" in rendered
    assert "`duckdb`" in rendered


def _make_repo(tmp_path, rows) -> pathlib.Path:
    revue = tmp_path / "docs" / "revue"
    revue.mkdir(parents=True)
    _write_jsonl(revue / "matrice-couverture-fme.jsonl", rows)
    return tmp_path


def test_main_check_passes_with_real_ops_catalog(tmp_path):
    repo = _make_repo(
        tmp_path,
        [
            {
                "fme_transformer": "Reprojector",
                "fme_category": "Geometry",
                "fme_description": "d",
                "geostudio_equivalent": "transform.reproject",
                "engine": "duckdb",
                "engine_license": "MIT",
                "coverage_status": "implemented",
                "usage_frequency": "courant",
                "notes": "",
            }
        ],
    )
    assert main(["--repo", str(repo), "--check"]) == 0


def test_main_check_fails_on_unknown_op(tmp_path):
    repo = _make_repo(
        tmp_path,
        [
            {
                "fme_transformer": "Bogus",
                "fme_category": "Geometry",
                "fme_description": "d",
                "geostudio_equivalent": "transform.does_not_exist",
                "engine": "duckdb",
                "engine_license": "MIT",
                "coverage_status": "implemented",
                "usage_frequency": "courant",
                "notes": "",
            }
        ],
    )
    assert main(["--repo", str(repo), "--check"]) == 1


def test_main_write_renders_markdown(tmp_path):
    repo = _make_repo(
        tmp_path,
        [
            {
                "fme_transformer": "Reprojector",
                "fme_category": "Geometry",
                "fme_description": "d",
                "geostudio_equivalent": "transform.reproject",
                "engine": "duckdb",
                "engine_license": "MIT",
                "coverage_status": "implemented",
                "usage_frequency": "courant",
                "notes": "",
            }
        ],
    )
    assert main(["--repo", str(repo), "--write"]) == 0
    rendered = (repo / "docs" / "revue" / "matrice-couverture-fme.md").read_text(
        encoding="utf-8"
    )
    assert "Reprojector" in rendered
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_fme_coverage_cli.py -v`
Expected: FAIL avec `ImportError: cannot import name 'render_md'` (et `main`)

- [ ] **Step 3: Écrire l'implémentation minimale**

D'abord, ajouter `from collections import Counter` aux imports en tête de
`core/scripts/fme_coverage_cli.py`, triés comme `ruff`/`isort` les
attendent (`import X` d'abord par ordre alphabétique, puis `from X import
Y` par ordre alphabétique) — un import ajouté au milieu du fichier lèverait
E402 à `ruff check` :

```python
import argparse
import json
import pathlib
import sys
from collections import Counter
from dataclasses import dataclass
```

Puis ajouter à la suite de `check_rows` :

```python
def render_md(rows: list[Row]) -> str:
    lines = ["# Matrice de couverture FME→GeoStudio", ""]
    lines.append(f"{len(rows)} transformers FME recensés.")
    lines.append("")
    lines.append("## Résumé par statut")
    lines.append("")
    lines.append("| Statut | Nombre |")
    lines.append("|---|---|")
    status_counts = Counter(row.coverage_status for row in rows)
    for status in sorted(status_counts):
        lines.append(f"| `{status}` | {status_counts[status]} |")
    lines.append("")
    lines.append("## Résumé par moteur")
    lines.append("")
    lines.append("| Moteur | Nombre |")
    lines.append("|---|---|")
    engine_counts = Counter(row.engine for row in rows)
    for engine in sorted(engine_counts):
        lines.append(f"| `{engine}` | {engine_counts[engine]} |")
    lines.append("")
    lines.append("## Détail")
    lines.append("")
    lines.append(
        "| Transformer FME | Catégorie | Équivalent GeoStudio | Moteur | "
        "Licence | Statut | Fréquence | Notes |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in sorted(rows, key=lambda r: (r.fme_category, r.fme_transformer)):
        lines.append(
            "| "
            + " | ".join(
                [
                    row.fme_transformer,
                    row.fme_category,
                    row.geostudio_equivalent or "",
                    row.engine,
                    row.engine_license,
                    f"`{row.coverage_status}`",
                    row.usage_frequency,
                    row.notes,
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="..", type=pathlib.Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args(argv)
    repo = arguments.repo.resolve()
    rows = load_rows(repo / JSONL)

    if arguments.write:
        (repo / RENDERED_MD).write_text(render_md(rows), encoding="utf-8")
        print(f"{len(rows)} lignes — {RENDERED_MD} régénéré.")

    if arguments.check:
        from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS
        from app.pipelines.ops.schemas import ops_catalog

        errors = check_rows(rows, ops=ops_catalog(), qgis_algorithms=QGIS_ALGORITHMS)
        for error in errors:
            print(f"ERREUR : {error}", file=sys.stderr)
        if errors:
            return 1
        print(f"{len(rows)} lignes vérifiées, aucune erreur.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_fme_coverage_cli.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add core/scripts/fme_coverage_cli.py core/tests/test_fme_coverage_cli.py
git commit -m "feat(core): rendu markdown et CLI --check/--write de la matrice FME"
```

---

## Méthode de catégorisation (référence, répétée intégralement dans chaque tâche de données ci-dessous)

Pour chaque transformer FME trouvé, dans cet ordre :

1. **Un op GeoStudio existant couvre-t-il déjà ce besoin ?** Les 19 op actuels
   (`core/app/pipelines/ops/schemas.py::OP_PARAMS`) : `reader.collection`,
   `reader.connector.rest`, `reader.connector.postgres`,
   `reader.connector.snowflake`, `transform.filter`, `transform.select`,
   `transform.derive`, `transform.aggregate`, `transform.join`,
   `transform.buffer`, `transform.reproject`, `transform.intersection`,
   `transform.countWithin`, `transform.h3Aggregate`, `transform.merge`,
   `transform.qgis`, `writer.collection`, `writer.export`, `writer.dataset`.
   Si oui → `coverage_status="implemented"`, `engine="duckdb"`,
   `geostudio_equivalent`=le nom exact de l'op.
2. **Sinon, l'allowlist QGIS gelée couvre-t-elle ce besoin PRÉCIS ?**
   (`core/app/pipelines/ops/qgis_algorithms.json`, 50 entrées, ex.
   `"gdal:contour"`, `"native:dissolve"` — consulter le fichier réel, ne pas
   deviner). Si oui → `coverage_status="qgis_frozen"`, `engine="qgis"`,
   `geostudio_equivalent`=l'id exact de l'algorithme. **Règle stricte** :
   jamais pour un besoin absent de ces 50 entrées, même si QGIS saurait
   probablement le faire — ce cas va en 3.
3. **Sinon, juger le meilleur moteur candidat futur** :
   - opération relationnelle/attributaire/SQL-compatible → `planned_duckdb`
   - lecture/écriture de format géospatial, opération vecteur générique →
     `planned_gdal`
   - nuage de points/LiDAR → `planned_pdal`
   - télédétection raster avancée (classification, indices spectraux,
     pansharpening…) → `planned_otb`
   - besoin spécifique sans bon candidat GDAL/PDAL/OTB mais avec une crate
     Rust mature connue → `planned_rust`, noter la crate dans `engine`
     (ex. `"rust:geo"`)
   - seule bonne implémentation open-source connue = GPL/propriétaire →
     `license_blocked`, documenter la licence trouvée dans `engine_license`
   - transformer sans rapport avec la géospatiale (EDI, ODBC legacy,
     notifications, bases propriétaires métier) → `out_of_scope`
   - recherche insuffisante pour trancher → `unknown`

## Format d'une ligne (rappel, cf. Task 1 pour le schéma complet)

```json
{"fme_transformer": "...", "fme_category": "...", "fme_description": "...", "geostudio_equivalent": "..." ou null, "engine": "duckdb|gdal|pdal|otb|rust:<crate>|qgis|n/a", "engine_license": "...", "coverage_status": "...", "usage_frequency": "courant|niche|inconnu", "notes": "..."}
```

Pour `out_of_scope`/`unknown` : `"engine": "n/a"`, `"engine_license": ""`
(chaîne vide, jamais `null`), `"geostudio_equivalent": null`. Pour
`license_blocked` : `"engine_license"` doit documenter la licence bloquante
réellement trouvée (ex. `"GPL-3.0"`), jamais rester vide.

---

### Task 6: Peuplement — Lecture/écriture de formats (Readers/Writers)

**Files:**
- Create: `docs/revue/matrice-couverture-fme.jsonl`

**Interfaces:**
- Consumes: `check_rows`/`load_rows` (Task 5) via `fme_coverage_cli.py --check`
- Produces: le fichier `docs/revue/matrice-couverture-fme.jsonl` (créé ici, complété par les Tasks 7-11)

- [ ] **Step 1: Rechercher la catégorie FME « Readers/Writers » (formats)**

Utiliser WebSearch/WebFetch sur la documentation publique de Safe Software
(galerie de transformers, `safe.com/transformers` et pages de format
associées). Objectif : lister les formats de lecture/écriture géospatiaux
et attributaires les plus documentés (viser au moins 30 entrées distinctes —
non exhaustif par construction, cf. spec §Risques et limites).

- [ ] **Step 2: Catégoriser chaque transformer trouvé**

Appliquer la « Méthode de catégorisation » ci-dessus à chaque format
trouvé. Repère utile : GeoStudio a déjà plusieurs formats d'import réels
côté module d'ingestion (GeoJSON, CSV, GPKG, Shapefile, XLSX, KML/KMZ,
GeoParquet, JSON Lines, GML, XML générique — cf. `core/app/ingestion/`,
vérifier la liste exacte dans le code plutôt que de se fier à ce résumé) —
un format déjà couvert par l'ingestion GeoStudio n'est PAS la même chose
qu'un op de pipeline (`reader.collection` etc.) : ne pas confondre les
deux, ce plan ne catégorise que par rapport au catalogue d'op de pipeline
(`ops_catalog()`) et à l'allowlist QGIS, jamais par rapport au module
`ingestion`.

- [ ] **Step 3: Créer le fichier JSONL avec les lignes trouvées**

Créer `docs/revue/matrice-couverture-fme.jsonl`, une ligne JSON par
transformer, au format de la section « Format d'une ligne » ci-dessus.

- [ ] **Step 4: Vérifier avec le script**

Run: `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --repo .. --check`
Expected: `N lignes vérifiées, aucune erreur.` (aucune erreur imprimée sur stderr)

Si des erreurs apparaissent, corriger les lignes fautives avant de continuer
(jamais commiter avec `--check` en échec).

- [ ] **Step 5: Commit**

```bash
git add docs/revue/matrice-couverture-fme.jsonl
git commit -m "docs(revue): peuple la matrice FME — formats readers/writers"
```

---

### Task 7: Peuplement — Géométrie + Système de coordonnées/reprojection

**Files:**
- Modify: `docs/revue/matrice-couverture-fme.jsonl`

**Interfaces:**
- Consumes: fichier existant (Task 6), `fme_coverage_cli.py --check`
- Produces: lignes supplémentaires ajoutées (append) au même fichier

- [ ] **Step 1: Rechercher les catégories FME « Geometry » et « Coordinate System »**

Utiliser WebSearch/WebFetch sur la doc publique FME. Viser au moins 30
transformers distincts pour ces deux catégories combinées.

- [ ] **Step 2: Catégoriser chaque transformer trouvé**

Appliquer la « Méthode de catégorisation » ci-dessus. Repère utile :
GeoStudio a déjà 5 op spatiaux dans le catalogue (`transform.buffer`,
`transform.reproject`, `transform.intersection`, `transform.countWithin`,
`transform.h3Aggregate`) et 50 algorithmes QGIS gelés couvrant beaucoup
d'opérations géométriques classiques (dissolve, buffer, clip, union…) —
vérifier `core/app/pipelines/ops/qgis_algorithms.json` avant de conclure
`planned_gdal`/`planned_otb`.

- [ ] **Step 3: Ajouter les lignes au fichier JSONL existant**

Ajouter (append, ne pas écraser) les nouvelles lignes à
`docs/revue/matrice-couverture-fme.jsonl`.

- [ ] **Step 4: Vérifier avec le script**

Run: `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --repo .. --check`
Expected: `N lignes vérifiées, aucune erreur.`

- [ ] **Step 5: Commit**

```bash
git add docs/revue/matrice-couverture-fme.jsonl
git commit -m "docs(revue): peuple la matrice FME — géométrie et reprojection"
```

---

### Task 8: Peuplement — Attributs + Chaînes de caractères + Manipulation de schéma

**Files:**
- Modify: `docs/revue/matrice-couverture-fme.jsonl`

**Interfaces:**
- Consumes: fichier existant (Tasks 6-7), `fme_coverage_cli.py --check`
- Produces: lignes supplémentaires ajoutées (append) au même fichier

- [ ] **Step 1: Rechercher les catégories FME « Attribute », « String/Text », « Schema/Feature Type »**

Utiliser WebSearch/WebFetch sur la doc publique FME. Viser au moins 30
transformers distincts pour ces catégories combinées.

- [ ] **Step 2: Catégoriser chaque transformer trouvé**

Appliquer la « Méthode de catégorisation » ci-dessus. Repère utile :
`transform.derive`, `transform.select`, `transform.aggregate` couvrent déjà
une bonne partie des manipulations attributaires génériques via SQL DuckDB
borné (cf. `core/app/pipelines/expr_validation.py`) — beaucoup de
transformers de cette famille devraient tomber en `implemented`
(`engine="duckdb"`) s'ils se ramènent à une expression SQL, ou
`planned_duckdb` sinon.

- [ ] **Step 3: Ajouter les lignes au fichier JSONL existant**

Ajouter (append) les nouvelles lignes à
`docs/revue/matrice-couverture-fme.jsonl`.

- [ ] **Step 4: Vérifier avec le script**

Run: `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --repo .. --check`
Expected: `N lignes vérifiées, aucune erreur.`

- [ ] **Step 5: Commit**

```bash
git add docs/revue/matrice-couverture-fme.jsonl
git commit -m "docs(revue): peuple la matrice FME — attributs, texte et schéma"
```

---

### Task 9: Peuplement — Filtrage & routage + Contrôle de flux

**Files:**
- Modify: `docs/revue/matrice-couverture-fme.jsonl`

**Interfaces:**
- Consumes: fichier existant (Tasks 6-8), `fme_coverage_cli.py --check`
- Produces: lignes supplémentaires ajoutées (append) au même fichier

- [ ] **Step 1: Rechercher les catégories FME « Filtering & Routing » et « Workflow/Logic »**

Utiliser WebSearch/WebFetch sur la doc publique FME (transformers type
Tester, Router, FeatureMerger conditionnel, etc.). Viser au moins 25
transformers distincts.

- [ ] **Step 2: Catégoriser chaque transformer trouvé**

Appliquer la « Méthode de catégorisation » ci-dessus. Repère utile :
`transform.filter` couvre le filtrage conditionnel générique (SQL DuckDB
borné). Le pipeline GeoStudio est une **topologie linéaire+join
uniquement** (`core/app/pipelines/compiler.py::predecessor_id` — un seul
prédécesseur non-secondaire par nœud) : un transformer FME de routage
multi-branches conditionnel complexe (type Router avec sorties multiples)
n'a probablement PAS d'équivalent 1:1 aujourd'hui → `planned_duckdb` avec
une note explicite sur cette limite de topologie, jamais `implemented`.

- [ ] **Step 3: Ajouter les lignes au fichier JSONL existant**

Ajouter (append) les nouvelles lignes à
`docs/revue/matrice-couverture-fme.jsonl`.

- [ ] **Step 4: Vérifier avec le script**

Run: `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --repo .. --check`
Expected: `N lignes vérifiées, aucune erreur.`

- [ ] **Step 5: Commit**

```bash
git add docs/revue/matrice-couverture-fme.jsonl
git commit -m "docs(revue): peuple la matrice FME — filtrage, routage et contrôle de flux"
```

---

### Task 10: Peuplement — Bases de données/Intégrations + Services web

**Files:**
- Modify: `docs/revue/matrice-couverture-fme.jsonl`

**Interfaces:**
- Consumes: fichier existant (Tasks 6-9), `fme_coverage_cli.py --check`
- Produces: lignes supplémentaires ajoutées (append) au même fichier

- [ ] **Step 1: Rechercher les catégories FME « Database »/« Integrations »/« Web Services »**

Utiliser WebSearch/WebFetch sur la doc publique FME. Viser au moins 30
transformers/connecteurs distincts.

- [ ] **Step 2: Catégoriser chaque transformer trouvé**

Appliquer la « Méthode de catégorisation » ci-dessus. Repère utile :
GeoStudio a déjà 3 connecteurs (`reader.connector.rest` via dlt,
`reader.connector.postgres`, `reader.connector.snowflake`, compatible
Redshift sans code dédié — cf. `core/app/pipelines/connector_runtime.py`)
— un connecteur de base de données propriétaire supplémentaire (Oracle,
SQL Server, etc.) est probablement `planned_duckdb` si DuckDB/dlt sait déjà
s'y connecter, sinon `unknown`. Un connecteur SaaS propriétaire tiers sans
rapport géospatial (CRM, ERP) → `out_of_scope`.

- [ ] **Step 3: Ajouter les lignes au fichier JSONL existant**

Ajouter (append) les nouvelles lignes à
`docs/revue/matrice-couverture-fme.jsonl`.

- [ ] **Step 4: Vérifier avec le script**

Run: `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --repo .. --check`
Expected: `N lignes vérifiées, aucune erreur.`

- [ ] **Step 5: Commit**

```bash
git add docs/revue/matrice-couverture-fme.jsonl
git commit -m "docs(revue): peuple la matrice FME — bases de données et services web"
```

---

### Task 11: Peuplement — Raster/Imagerie + Nuages de points/LiDAR

**Files:**
- Modify: `docs/revue/matrice-couverture-fme.jsonl`

**Interfaces:**
- Consumes: fichier existant (Tasks 6-10), `fme_coverage_cli.py --check`
- Produces: lignes supplémentaires ajoutées (append) au même fichier

- [ ] **Step 1: Rechercher les catégories FME « Raster »/« Imagery » et « Point Cloud »/« LiDAR »**

Utiliser WebSearch/WebFetch sur la doc publique FME. Viser au moins 25
transformers distincts pour ces deux catégories combinées.

- [ ] **Step 2: Catégoriser chaque transformer trouvé**

Appliquer la « Méthode de catégorisation » ci-dessus. Repère utile :
GeoStudio n'a aujourd'hui **aucun** op de pipeline raster ni nuage de
points — un transformer raster avancé (classification, indices spectraux)
va normalement en `planned_otb` ; un transformer nuage de points va en
`planned_pdal` ; une simple reprojection ou un buffer raster générique
pourrait déjà être couvert par un des 50 algos QGIS gelés (vérifier le
fichier réel avant de conclure).

- [ ] **Step 3: Ajouter les lignes au fichier JSONL existant**

Ajouter (append) les nouvelles lignes à
`docs/revue/matrice-couverture-fme.jsonl`.

- [ ] **Step 4: Vérifier avec le script**

Run: `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --repo .. --check`
Expected: `N lignes vérifiées, aucune erreur.`

- [ ] **Step 5: Commit**

```bash
git add docs/revue/matrice-couverture-fme.jsonl
git commit -m "docs(revue): peuple la matrice FME — raster, imagerie et nuages de points"
```

---

### Task 12: Rendu final + validation de bout en bout

**Files:**
- Create: `docs/revue/matrice-couverture-fme.md` (généré, pas écrit à la main)
- Modify: aucun autre fichier

**Interfaces:**
- Consumes: `docs/revue/matrice-couverture-fme.jsonl` complet (Tasks 6-11), `fme_coverage_cli.py --write`/`--check`

- [ ] **Step 1: Vérifier l'intégralité du fichier une dernière fois**

Run: `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --repo .. --check`
Expected: `N lignes vérifiées, aucune erreur.` (N = somme des lignes des Tasks 6-11, viser au moins 170 au total)

Si des erreurs apparaissent (contradiction introduite par une tâche
précédente, ex. deux tâches ayant indépendamment marqué un même besoin
`implemented` avec des `geostudio_equivalent` différents), les corriger
avant de continuer.

- [ ] **Step 2: Générer le rendu markdown**

Run: `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --repo .. --write`
Expected: `N lignes — docs/revue/matrice-couverture-fme.md régénéré.`

- [ ] **Step 3: Relire le rendu généré**

Ouvrir `docs/revue/matrice-couverture-fme.md`, vérifier que le résumé par
statut et par moteur est cohérent (ex. le nombre de `qgis_frozen` ne
dépasse jamais 50 — l'allowlist gelée réelle), et que la table de détail
liste bien toutes les lignes.

- [ ] **Step 4: Lancer la suite de tests complète du script une dernière fois**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_fme_coverage_cli.py -v`
Expected: PASS (14 tests, inchangé depuis Task 5 — cette tâche ne touche
pas le code du script)

- [ ] **Step 5: Commit**

```bash
git add docs/revue/matrice-couverture-fme.md
git commit -m "docs(revue): régénère le rendu de la matrice de couverture FME"
```
