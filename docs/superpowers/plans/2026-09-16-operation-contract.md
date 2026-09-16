# OperationContract — contrat unique par op de pipeline (core-only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer, pour les 19 op de pipeline déjà livrées, les 5 structures parallèles indexées
par nom d'op (`OP_PARAMS`/`OP_KINDS`/`BINARY_OPS` dans `ops/schemas.py`, les deux `if/elif` de
`compiler.py`) par un type unique `OperationContract` et un registre unique `OPERATIONS`, sans
changer aucun comportement observable (même réponse `GET /pipelines/ops`, mêmes erreurs, aucune
route/tool/config touchée).

**Architecture:** Un nouveau module `core/app/pipelines/ops/contracts.py` porte le type
`OperationContract` (dataclass frozen, règle `is_copyleft ⇒ execution_model == "sidecar"` vérifiée
au constructeur) et le registre `OPERATIONS: dict[str, OperationContract]`. Les 11 fonctions de
compilation SQL DuckDB et les 4 fonctions de calcul de SRID de sortie restent **définies dans
`compiler.py`** (jamais dupliquées), extraites de leurs deux `if/elif` en fonctions privées
autonomes ; `contracts.py` les référence par nom pour construire `OPERATIONS`. `OP_KINDS`,
`OP_PARAMS`, `BINARY_OPS`, `parse_op_params()`, `ops_catalog()` deviennent des vues dérivées de
`OPERATIONS` — **déplacées dans `contracts.py`** (voir Écart n°1 ci-dessous, contrainte d'import
circulaire réelle, pas une préférence de style). `compile_transform_sql()`/`transform_output_srid()`
(signatures publiques inchangées) deviennent de fins wrappers qui résolvent le contrat de l'op dans
`OPERATIONS` et appellent son `.compile`/`.output_srid`.

**Tech Stack:** Python 3.12, dataclasses stdlib, Pydantic v2 (`BaseModel`), pytest.

## Écarts au texte de la spec, décidés en amont (piège CLAUDE.md n°3 — vérifié dans le code, pas supposé)

1. **`OP_KINDS`/`OP_PARAMS`/`BINARY_OPS`/`parse_op_params()`/`ops_catalog()` déménagent dans
   `contracts.py`, pas gardés dans `schemas.py` comme le texte de la spec (§3) le suggérait.**
   Raison : un import circulaire réel et non résolvable par ordonnancement.
   `contracts.py` a besoin, à son propre chargement, des classes Pydantic de `schemas.py`
   (`params_schema=TransformFilterParams`, etc.) — c'est un import de module au niveau fichier,
   nécessaire pour construire le dict `OPERATIONS`. Si `schemas.py` importait *en retour*
   `OPERATIONS`/`OP_KINDS`/etc. depuis `contracts.py` **au niveau module** (ce que demande le texte
   de la spec), les deux fichiers s'importeraient l'un l'autre au chargement — un cycle à 2 nœuds
   qu'aucun ordre d'import ne résout jamais de façon fiable en Python (vérifié par trace manuelle :
   selon lequel des deux fichiers un test importe en premier, l'un des deux sens lève
   `ImportError: cannot import name '...' from partially initialized module`). `schemas.py` garde
   donc **uniquement** les classes Pydantic (son rôle déjà déclaré par son propre docstring :
   « manifeste de params typé ») ; `contracts.py` devient le seul propriétaire du registre et du
   catalogue exposé par `GET /pipelines/ops`. 7 fichiers doivent changer leur chemin d'import en
   conséquence (Task 4, §3 ci-dessous) — c'est un renommage de chemin mécanique, aucun comportement
   ne change.
2. **La signature de `output_srid` gagne un paramètre `op: str`** (pas seulement
   `(params, *, input_srid, join_srid=None)` comme le texte de la spec §4 le montre). Raison : la
   fonction partagée par 3 op (`transform.intersection`/`transform.countWithin`/`transform.merge`)
   construit un message d'erreur qui nomme l'op fautive (`f"'{op}': input CRS ... differ"`,
   comportement existant à préserver à l'identique) — sans ce paramètre, un seul message d'erreur
   générique aurait remplacé 3 messages distincts, changement de comportement observable interdit
   par la spec §2. Toutes les fonctions `output_srid` (y compris celles qui n'en ont pas besoin)
   reçoivent ce paramètre pour garder un seul type de signature appelable génériquement — c'est la
   convention d'appel uniforme demandée par la spec §4, juste avec un paramètre de plus que prévu.
   `compile` n'a pas ce problème (aucune des 11 fonctions de compilation ne partage son corps avec
   une autre op) : sa signature reste exactement celle de la spec.

## Global Constraints

- **Aucun nouveau moteur câblé, aucune nouvelle op, aucun changement d'API publique** — spec §2
  « Hors périmètre ». `GET /pipelines/ops` doit répondre exactement comme avant (mêmes clés, mêmes
  valeurs) : diff `openapi.json`/`core-schema.d.ts` vide, à vérifier plutôt que supposer (piège
  CLAUDE.md n°1) — attendu vide de toute façon puisque ce plan ne touche aucune route ni aucun
  modèle Pydantic exposé.
- **Zéro fichier `shell/` touché.**
- **`transform.qgis` garde `compile=None`** — son exécution reste inline dans
  `app/pipelines/runtime.py::_execute_qgis_transform`/`_lock_down` (décision SP-15d préservée par
  SP-43, spec §1). Ce plan ne touche à aucune ligne de `runtime.py` en dehors de vérifications de
  non-régression (aucune modification n'y est prévue — le fichier n'apparaît dans aucune section
  Files ci-dessous).
- Docs et commentaires de code en français, identifiants en anglais (convention du dépôt).
- Commits conventionnels, un sujet par commit (`refactor(core): …`, `feat(core): …`, `docs: …`).
- `engine_license` est un texte **informatif, jamais parsé automatiquement** (spec §3) : aucun test
  n'en vérifie le contenu littéral sauf pour `transform.qgis` (spec §5, valeur vérifiée contre
  `docs/revue/matrice-couverture-fme.jsonl` ci-dessous, pas devinée).
- `mypy --strict` ne couvre pas `app.pipelines` (périmètre exact, vérifié dans
  `core/pyproject.toml` : `app/auth app/secrets app/analytics app/copilot app/admin_tools
  app/roles`) — aucune obligation `--strict` sur les fichiers de ce plan. `ruff check`/`ruff format
  --check`/`lint-imports` s'appliquent en revanche à tout `core/`.
- Aucune tâche de ce plan ne peut s'exécuter en parallèle des autres : Task 2 modifie le fichier que
  Task 3 modifie ensuite, Task 4 dépend des fonctions privées extraites par Tasks 2 et 3, Task 5
  dépend de tout ce qui précède. **Exécuter dans l'ordre, jamais en parallèle.**

---

## File Structure

- **Create** `core/app/pipelines/ops/contracts.py` — `OperationContract` (Task 1), puis `OPERATIONS`
  + `OP_KINDS`/`OP_PARAMS`/`BINARY_OPS`/`parse_op_params`/`_user_facing_description`/`ops_catalog`
  déménagés depuis `schemas.py` (Task 4).
- **Create** `core/tests/test_pipeline_ops_contracts.py` — règle copyleft⇒sidecar (Task 1) ; 19 clés
  + métadonnées `transform.qgis` (Task 4).
- **Modify** `core/app/pipelines/compiler.py` — extraction des 11 fonctions `_compile_*` (Task 2) et
  des 4 fonctions `_output_srid_*` (Task 3) ; wrappers `compile_transform_sql`/
  `transform_output_srid` rebranchés sur `OPERATIONS` (Task 4).
- **Modify** `core/app/pipelines/ops/schemas.py` — retrait de `OP_KINDS`/`OP_PARAMS`/`BINARY_OPS`/
  `parse_op_params`/`_user_facing_description`/`ops_catalog`, docstring de tête mis à jour (Task 4).
- **Modify** `core/app/pipelines/routes.py`, `core/app/pipelines/config_validation.py`,
  `core/scripts/fme_coverage_cli.py`, `core/tests/test_pipeline_ops_schemas.py` — chemin d'import
  `app.pipelines.ops.schemas` → `app.pipelines.ops.contracts` pour les seuls noms déménagés (Task 4).
- **Modify** `CLAUDE.md` — entrée de clôture `### Livré` (Task 5).

---

### Task 1: `OperationContract` — type et règle copyleft⇒sidecar

**Files:**
- Create: `core/app/pipelines/ops/contracts.py`
- Create: `core/tests/test_pipeline_ops_contracts.py`

**Interfaces:**
- Produit : `OperationContract` (dataclass frozen), champs `op: str`, `kind: Literal["reader",
  "transform", "writer"]`, `params_schema: type[BaseModel]`, `accepts_secondary_input: bool = False`,
  `engine: str | None = None`, `engine_license: str | None = None`, `is_copyleft: bool = False`,
  `execution_model: Literal["in_process", "sidecar"] = "in_process"`, `compile: Callable[..., str] |
  None = None`, `output_srid: Callable[..., int] | None = None`. Lève `ValueError` à la construction
  si `is_copyleft=True` et `execution_model != "sidecar"`. Consommé par Task 4 (construction du
  registre `OPERATIONS`) — aucune autre tâche de ce plan n'en dépend avant Task 4.

- [ ] **Step 1: Write the failing tests**

Créer `core/tests/test_pipeline_ops_contracts.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.pipelines.ops.contracts import OperationContract
from app.pipelines.ops.schemas import TransformFilterParams


def test_copyleft_engine_requires_sidecar_execution_model():
    with pytest.raises(ValueError, match="execution_model='sidecar'"):
        OperationContract(
            op="transform.fake-copyleft",
            kind="transform",
            params_schema=TransformFilterParams,
            engine="fake-gpl-engine",
            is_copyleft=True,
            execution_model="in_process",
        )


def test_copyleft_engine_with_sidecar_execution_model_is_accepted():
    contract = OperationContract(
        op="transform.fake-copyleft",
        kind="transform",
        params_schema=TransformFilterParams,
        engine="fake-gpl-engine",
        is_copyleft=True,
        execution_model="sidecar",
    )
    assert contract.execution_model == "sidecar"
    assert contract.is_copyleft is True


def test_non_copyleft_engine_defaults_to_in_process_and_no_copyleft():
    contract = OperationContract(
        op="transform.filter",
        kind="transform",
        params_schema=TransformFilterParams,
    )
    assert contract.execution_model == "in_process"
    assert contract.is_copyleft is False
    assert contract.engine is None
    assert contract.compile is None
    assert contract.output_srid is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_pipeline_ops_contracts.py -v`
Expected: 3 ERROR — `ModuleNotFoundError: No module named 'app.pipelines.ops.contracts'` (le module
n'existe pas encore).

- [ ] **Step 3: Write minimal implementation**

Créer `core/app/pipelines/ops/contracts.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Contrat unique par op de pipeline (schéma/moteur/licence/modèle
d'exécution/compilateur/règle de SRID de sortie) — design
docs/superpowers/specs/2026-09-16-operation-contract-design.md.

Remplace, pour les 19 op de pipeline déjà livrées, les 5 structures
parallèles indexées par nom d'op qui existaient jusqu'ici
(app.pipelines.ops.schemas::OP_PARAMS/OP_KINDS/BINARY_OPS,
app.pipelines.compiler::compile_transform_sql/transform_output_srid) : le
registre OPERATIONS (construit par une tâche ultérieure de ce même
chantier, cf. plan) devient la seule source, ces structures en deviennent
des vues dérivées, définies dans CE module (pas dans ops/schemas.py — un
import circulaire réel l'interdit, cf. Écarts au texte de la spec du plan).

Règle non négociable, vérifiée à la CONSTRUCTION de chaque contrat (donc à
chaque import de ce module, pas seulement par un test dédié) :
généralisation de la décision SP-15d déjà en vigueur pour QGIS — un moteur
copyleft (is_copyleft=True) exige un modèle d'exécution sidecar, jamais de
bindings in-process."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


@dataclass(frozen=True)
class OperationContract:
    op: str
    kind: Literal["reader", "transform", "writer"]
    params_schema: type[BaseModel]
    accepts_secondary_input: bool = False
    engine: str | None = None
    engine_license: str | None = None
    is_copyleft: bool = False
    execution_model: Literal["in_process", "sidecar"] = "in_process"
    compile: Callable[..., str] | None = None
    output_srid: Callable[..., int] | None = None

    def __post_init__(self) -> None:
        if self.is_copyleft and self.execution_model != "sidecar":
            raise ValueError(
                f"'{self.op}': moteur copyleft ({self.engine}) exige "
                "execution_model='sidecar'"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_pipeline_ops_contracts.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/ops/contracts.py core/tests/test_pipeline_ops_contracts.py
git commit -m "feat(core): ajoute OperationContract (règle copyleft⇒sidecar)"
```

---

### Task 2: extraire les 11 fonctions de compilation de `compile_transform_sql`

**Files:**
- Modify: `core/app/pipelines/compiler.py:78-191`
- Test: `core/tests/test_pipeline_compiler.py` (aucune modification — sert de filet de
  non-régression)

**Interfaces:**
- Produit : 11 fonctions privées, signature uniforme `(params: dict, *, input_view: str, join_view:
  str | None = None, input_srid: int | None = None) -> str` : `_compile_filter`, `_compile_select`,
  `_compile_derive`, `_compile_aggregate`, `_compile_join`, `_compile_buffer`, `_compile_reproject`,
  `_compile_intersection`, `_compile_count_within`, `_compile_h3_aggregate`, `_compile_merge`.
  Consommées par Task 4 (`contracts.py::OPERATIONS`, champ `compile=`).
- `compile_transform_sql(op, params, *, input_view, join_view=None, input_srid=None) -> str` garde
  exactement sa signature et son comportement (même `if/elif`, chaque branche appelle maintenant la
  fonction privée correspondante au lieu d'inliner son corps) — **aucun test existant ne doit
  changer**.

Ceci est un refactor pur (comportement identique, prouvé par la suite déjà existante). Pas de
nouveau test à écrire : `test_pipeline_compiler.py` couvre déjà chacune des 11 branches
individuellement (`test_compile_filter`, `test_compile_select_with_rename`, `test_compile_derive`,
`test_compile_aggregate`, `test_compile_join`, `test_compile_join_without_join_view_raises`,
`test_compile_buffer_native_unit`, `test_compile_buffer_meters_unit_uses_correct_axis_order`,
`test_compile_reproject_uses_correct_axis_order`, `test_compile_intersection_default_keeps_left_geometry`,
`test_compile_intersection_output_geometry_intersection`, `test_compile_count_within_intersects_default`,
`test_compile_count_within_custom_column_and_contains_predicate`,
`test_compile_h3_aggregate_groups_nearby_points`,
`test_compile_h3_aggregate_with_no_metrics_has_no_trailing_comma`, `test_compile_merge`,
`test_compile_merge_without_join_view_raises`, `test_compile_unknown_transform_op_raises`).

- [ ] **Step 1: Run the existing suite to record the baseline**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_pipeline_compiler.py -v`
Expected: tous les tests de compilation passent (baseline avant refactor — noter le compte exact
affiché).

- [ ] **Step 2: Extraire les 11 fonctions, remplacer le corps de `compile_transform_sql`**

Dans `core/app/pipelines/compiler.py`, remplacer les lignes 78-191 (la fonction
`compile_transform_sql` complète) par :

```python
def _compile_filter(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformFilterParams.model_validate(params)
    return f"SELECT * FROM {_qi(input_view)} WHERE ({p.expr})"


def _compile_select(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformSelectParams.model_validate(params)
    cols = ", ".join(
        f"{_qi(src)} AS {_qi(dst)}" if dst else _qi(src) for src, dst in p.columns.items()
    )
    return f"SELECT {cols} FROM {_qi(input_view)}"


def _compile_derive(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformDeriveParams.model_validate(params)
    return f"SELECT *, ({p.expr}) AS {_qi(p.column)} FROM {_qi(input_view)}"


def _compile_aggregate(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformAggregateParams.model_validate(params)
    group_cols = ", ".join(_qi(c) for c in p.groupBy)
    metric_cols = ", ".join(f"({expr}) AS {_qi(name)}" for name, expr in p.metrics.items())
    select_cols = ", ".join(filter(None, [group_cols, metric_cols]))
    group_clause = f" GROUP BY {group_cols}" if group_cols else ""
    return f"SELECT {select_cols} FROM {_qi(input_view)}{group_clause}"


def _compile_join(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformJoinParams.model_validate(params)
    assert join_view is not None, "transform.join requires join_view"
    join_kw = "LEFT JOIN" if p.how == "left" else "JOIN"
    return f"SELECT * FROM {_qi(input_view)} {join_kw} {_qi(join_view)} USING ({_qi(p.on)})"


def _compile_buffer(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformBufferParams.model_validate(params)
    if p.unit == "native":
        return (
            f"SELECT * EXCLUDE (geometry), ST_Buffer(geometry, {p.distance}) AS geometry "
            f"FROM {_qi(input_view)}"
        )
    assert input_srid is not None, "transform.buffer(unit='meters') requires input_srid"
    # always_xy=true est obligatoire ici : cf. plan Global Constraints
    # (sans lui, ST_Transform applique l'ordre d'axe EPSG (lat,lng) pour
    # EPSG:4326 et intervertit x/y silencieusement — vérifié contre un
    # DuckDB réel).
    src = f"'EPSG:{input_srid}'"
    return (
        f"SELECT * EXCLUDE (geometry), "
        f"ST_Transform(ST_Buffer(ST_Transform(geometry, {src}, 'EPSG:3857', true), "
        f"{p.distance}), 'EPSG:3857', {src}, true) AS geometry FROM {_qi(input_view)}"
    )


def _compile_reproject(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformReprojectParams.model_validate(params)
    assert input_srid is not None, "transform.reproject requires input_srid"
    return (
        f"SELECT * EXCLUDE (geometry), "
        f"ST_Transform(geometry, 'EPSG:{input_srid}', '{p.targetCrs}', true) AS geometry "
        f"FROM {_qi(input_view)}"
    )


def _compile_intersection(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformIntersectionParams.model_validate(params)
    assert join_view is not None, "transform.intersection requires join_view"
    join_kw = "LEFT JOIN" if p.how == "left" else "JOIN"
    geom_expr = (
        "t.geometry" if p.outputGeometry == "left" else "ST_Intersection(t.geometry, o.geometry)"
    )
    return (
        f"SELECT t.* EXCLUDE (geometry), {geom_expr} AS geometry "
        f"FROM {_qi(input_view)} t {join_kw} {_qi(join_view)} o "
        f"ON ST_Intersects(t.geometry, o.geometry)"
    )


def _compile_count_within(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformCountWithinParams.model_validate(params)
    assert join_view is not None, "transform.countWithin requires join_view"
    if p.predicate == "intersects":
        predicate_expr = "ST_Intersects(t.geometry, o.geometry)"
    else:  # contains
        predicate_expr = "ST_Contains(o.geometry, t.geometry)"
    return (
        f"SELECT t.* EXCLUDE (geometry), t.geometry, COUNT(o.geometry) AS {_qi(p.countColumn)} "
        f"FROM {_qi(input_view)} t LEFT JOIN {_qi(join_view)} o "
        f"ON {predicate_expr} GROUP BY ALL"
    )


def _compile_h3_aggregate(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformH3AggregateParams.model_validate(params)
    h3_expr = (
        f"h3_latlng_to_cell(ST_Y(ST_Centroid(geometry)), "
        f"ST_X(ST_Centroid(geometry)), {p.resolution})"
    )
    select_parts = [
        f"{h3_expr} AS h3Cell",
        f"ST_GeomFromText(h3_cell_to_boundary_wkt({h3_expr})) AS geometry",
    ]
    metric_cols = ", ".join(f"({expr}) AS {_qi(name)}" for name, expr in p.metrics.items())
    if metric_cols:
        select_parts.append(metric_cols)
    return f"SELECT {', '.join(select_parts)} FROM {_qi(input_view)} GROUP BY h3Cell"


def _compile_merge(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    TransformMergeParams.model_validate(params)  # forme seulement, aucun autre champ à lire
    assert join_view is not None, "transform.merge requires join_view"
    return f"SELECT * FROM {_qi(input_view)} UNION ALL BY NAME SELECT * FROM {_qi(join_view)}"


_TRANSFORM_COMPILERS: dict[str, Callable[..., str]] = {
    "transform.filter": _compile_filter,
    "transform.select": _compile_select,
    "transform.derive": _compile_derive,
    "transform.aggregate": _compile_aggregate,
    "transform.join": _compile_join,
    "transform.buffer": _compile_buffer,
    "transform.reproject": _compile_reproject,
    "transform.intersection": _compile_intersection,
    "transform.countWithin": _compile_count_within,
    "transform.h3Aggregate": _compile_h3_aggregate,
    "transform.merge": _compile_merge,
}


def compile_transform_sql(
    op: str,
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    compiler_fn = _TRANSFORM_COMPILERS.get(op)
    if compiler_fn is None:
        raise ValueError(f"'{op}' is not a transform op")
    return compiler_fn(params, input_view=input_view, join_view=join_view, input_srid=input_srid)
```

Ajouter l'import manquant en tête de fichier (`Callable` est utilisé par `_TRANSFORM_COMPILERS`) :
dans le bloc d'imports existant (ligne 11), ajouter avant `from app.configs.schemas import ...` :

```python
from collections.abc import Callable

from app.configs.schemas import PipelineEdge, PipelineNode
```

Note : `_TRANSFORM_COMPILERS` est un dict intermédiaire, **temporaire à cette tâche** — Task 4 le
remplacera par le dispatch via `OPERATIONS` (spec §4) et le supprimera. Il existe ici uniquement
pour que ce refactor reste vérifiable de façon autonome, sans dépendre de `contracts.py` qui n'a pas
encore le registre complet.

- [ ] **Step 3: Run tests to verify identical behavior**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_pipeline_compiler.py -v`
Expected: même nombre de tests passés qu'au Step 1, aucune régression, aucun changement de message
d'erreur (en particulier `test_compile_unknown_transform_op_raises` doit toujours passer avec le
message `"not a transform op"`, inchangé).

- [ ] **Step 4: Commit**

```bash
git add core/app/pipelines/compiler.py
git commit -m "refactor(core): extrait les 11 fonctions de compilation de compile_transform_sql"
```

---

### Task 3: extraire les 4 fonctions de calcul de SRID de sortie de `transform_output_srid`

**Files:**
- Modify: `core/app/pipelines/compiler.py` (fonction `transform_output_srid`, ajoutée à la suite de
  Task 2)
- Test: `core/tests/test_pipeline_compiler.py` (aucune modification — filet de non-régression)

**Interfaces:**
- Produit : 4 fonctions privées, signature uniforme `(params: dict, *, op: str, input_srid: int,
  join_srid: int | None = None) -> int` : `_output_srid_reproject`, `_output_srid_reconcile_join`
  (partagée par `transform.intersection`/`transform.countWithin`/`transform.merge`, comme dans le
  code réel actuel — même branche `if op in (...)`),  `_output_srid_h3_aggregate`,
  `_output_srid_qgis`. Consommées par Task 4 (`contracts.py::OPERATIONS`, champ `output_srid=`).
  Le paramètre `op` (Écart n°2 du plan) sert uniquement au message d'erreur de
  `_output_srid_reconcile_join` — les 3 autres fonctions le reçoivent mais l'ignorent, pour garder
  une signature strictement identique appelable génériquement.
- `transform_output_srid(op, params, *, input_srid, join_srid=None) -> int` garde exactement sa
  signature et son comportement (passthrough silencieux par défaut, `ValueError` sur mésaccord de
  CRS) — **aucun test existant ne doit changer**.

- [ ] **Step 1: Run the existing suite to record the baseline**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_pipeline_compiler.py -k output_srid -v`
Expected: tous les tests `output_srid` passent (baseline avant refactor).

- [ ] **Step 2: Extraire les 4 fonctions, remplacer le corps de `transform_output_srid`**

Dans `core/app/pipelines/compiler.py`, remplacer la fonction `transform_output_srid` (dernière
fonction du fichier après Task 2) par :

```python
def _output_srid_reproject(
    params: dict,
    *,
    op: str,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    p = TransformReprojectParams.model_validate(params)
    return int(p.targetCrs.rsplit(":", 1)[1])


def _output_srid_reconcile_join(
    params: dict,
    *,
    op: str,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    assert join_srid is not None, f"{op} requires join_srid"
    if input_srid != join_srid:
        raise ValueError(
            f"'{op}': input CRS (EPSG:{input_srid}) and joined collection CRS "
            f"(EPSG:{join_srid}) differ — insert transform.reproject first"
        )
    return input_srid


def _output_srid_h3_aggregate(
    params: dict,
    *,
    op: str,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    if input_srid != 4326:
        raise ValueError(
            f"'transform.h3Aggregate' requires EPSG:4326 input (got EPSG:{input_srid}) "
            "— insert transform.reproject first"
        )
    return 4326


def _output_srid_qgis(
    params: dict,
    *,
    op: str,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    p = TransformQgisParams.model_validate(params)
    return int(p.outputSrid.rsplit(":", 1)[1]) if p.outputSrid is not None else input_srid


_TRANSFORM_OUTPUT_SRID: dict[str, Callable[..., int]] = {
    "transform.reproject": _output_srid_reproject,
    "transform.intersection": _output_srid_reconcile_join,
    "transform.countWithin": _output_srid_reconcile_join,
    "transform.merge": _output_srid_reconcile_join,
    "transform.h3Aggregate": _output_srid_h3_aggregate,
    "transform.qgis": _output_srid_qgis,
}


def transform_output_srid(
    op: str,
    params: dict,
    *,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    """SRID de sortie d'un nœud transform, calculé sans connexion DuckDB
    (pur, comme compile_transform_sql). Lève ValueError si les deux entrées
    d'une op spatiale binaire ne partagent pas le même CRS — design §2/§3.3/
    §3.4/§3.5 : aucune réconciliation implicite, jamais un résultat spatial
    silencieusement faux. runtime.py convertit ce ValueError en
    PipelineRuntimeError avant de le laisser remonter."""
    output_srid_fn = _TRANSFORM_OUTPUT_SRID.get(op)
    if output_srid_fn is None:
        return input_srid  # passthrough — comportement déjà existant : pas
        # de branche d'erreur pour un op inconnu, contrairement à
        # compile_transform_sql (vérifié dans le code réel avant ce plan).
    return output_srid_fn(params, op=op, input_srid=input_srid, join_srid=join_srid)
```

Note : `_TRANSFORM_OUTPUT_SRID` est, comme `_TRANSFORM_COMPILERS` (Task 2), un dict intermédiaire
**temporaire à cette tâche** — Task 4 le remplace par le dispatch via `OPERATIONS` et le supprime.

- [ ] **Step 3: Run tests to verify identical behavior**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_pipeline_compiler.py -v`
Expected: tous les tests du fichier passent (compilation + output_srid), même compte qu'avant Task 2
+ Task 3 cumulées, aucune régression.

- [ ] **Step 4: Commit**

```bash
git add core/app/pipelines/compiler.py
git commit -m "refactor(core): extrait les 4 fonctions de calcul de SRID de sortie"
```

---

### Task 4: construire `OPERATIONS`, rebrancher les wrappers, déménager le registre dans `contracts.py`

**Files:**
- Modify: `core/app/pipelines/ops/contracts.py` (ajout après la classe `OperationContract` de Task 1)
- Modify: `core/app/pipelines/compiler.py` (remplace `_TRANSFORM_COMPILERS`/`_TRANSFORM_OUTPUT_SRID`
  par un dispatch via `OPERATIONS`)
- Modify: `core/app/pipelines/ops/schemas.py:1-15,231-323` (retrait du registre, classes inchangées)
- Modify: `core/app/pipelines/routes.py:17`
- Modify: `core/app/pipelines/config_validation.py:22`
- Modify: `core/scripts/fme_coverage_cli.py:14,192-193`
- Modify: `core/tests/test_pipeline_ops_schemas.py:5-12,443`
- Modify: `core/tests/test_pipeline_ops_contracts.py` (ajout après les tests de Task 1)

**Interfaces:**
- Produit : `OPERATIONS: dict[str, OperationContract]` (19 entrées), `OP_KINDS: dict[str, str]`,
  `OP_PARAMS: dict[str, type[BaseModel]]`, `BINARY_OPS: set[str]`, `parse_op_params(op: str, params:
  dict) -> BaseModel`, `ops_catalog() -> dict[str, dict]` — tous dans
  `app.pipelines.ops.contracts` (pas `app.pipelines.ops.schemas`, cf. Écart n°1 du plan).
- Consomme : les 15 fonctions privées de Tasks 2 et 3, les 18 classes Pydantic de `schemas.py`
  (inchangées).

**Vérification préalable de la licence QGIS** (piège CLAUDE.md n°3 — ne pas deviner la chaîne) :

```bash
cd /home/lenen/projets/geostudio && grep -o '"engine": "qgis"[^}]*"engine_license": "[^"]*"' \
  docs/revue/matrice-couverture-fme.jsonl | grep -o '"engine_license": "[^"]*"' | sort -u
```

Résultat attendu (déjà vérifié en amont de ce plan) : `"engine_license": "GPL-2.0-or-later (QGIS)"`
— exactement 1 valeur, utilisée par les 19 lignes `"engine": "qgis"` de la matrice. C'est la valeur à
utiliser ci-dessous, verbatim.

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `core/tests/test_pipeline_ops_contracts.py` :

```python
def test_operations_registry_has_exactly_the_nineteen_known_ops():
    from app.pipelines.ops.contracts import OPERATIONS

    assert set(OPERATIONS) == {
        "reader.collection",
        "transform.filter",
        "transform.select",
        "transform.derive",
        "transform.aggregate",
        "transform.join",
        "transform.buffer",
        "transform.reproject",
        "transform.intersection",
        "transform.countWithin",
        "transform.h3Aggregate",
        "transform.qgis",
        "writer.collection",
        "writer.export",
        "writer.dataset",
        "reader.connector.rest",
        "reader.connector.postgres",
        "reader.connector.snowflake",
        "transform.merge",
    }


def test_qgis_operation_contract_declares_copyleft_sidecar_metadata():
    from app.pipelines.ops.contracts import OPERATIONS

    contract = OPERATIONS["transform.qgis"]
    assert contract.engine == "qgis"
    assert contract.engine_license == "GPL-2.0-or-later (QGIS)"
    assert contract.is_copyleft is True
    assert contract.execution_model == "sidecar"
    assert contract.compile is None
    assert contract.output_srid is not None


def test_connector_and_writer_ops_are_not_classified_by_engine():
    from app.pipelines.ops.contracts import OPERATIONS

    for op in (
        "reader.collection",
        "reader.connector.rest",
        "reader.connector.postgres",
        "reader.connector.snowflake",
        "writer.collection",
        "writer.export",
        "writer.dataset",
    ):
        contract = OPERATIONS[op]
        assert contract.engine is None
        assert contract.is_copyleft is False
        assert contract.execution_model == "in_process"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_pipeline_ops_contracts.py -v`
Expected: les 3 tests de Task 1 passent toujours, les 3 nouveaux échouent en
`ImportError: cannot import name 'OPERATIONS'` (le registre n'existe pas encore).

- [ ] **Step 3: Construire `OPERATIONS` dans `contracts.py`**

D'abord, insérer les deux nouveaux imports dans le bloc d'imports **existant en tête de fichier**
(ruff E402 interdit un import de module après du code exécutable — ces imports ne doivent PAS être
ajoutés plus bas dans le fichier). Remplacer le bloc d'imports actuel de
`core/app/pipelines/ops/contracts.py` :

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
```

par :

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from app.pipelines import compiler as _compiler
from app.pipelines.ops.schemas import (
    ReaderCollectionParams,
    ReaderConnectorPostgresParams,
    ReaderConnectorRestParams,
    ReaderConnectorSnowflakeParams,
    TransformAggregateParams,
    TransformBufferParams,
    TransformCountWithinParams,
    TransformDeriveParams,
    TransformFilterParams,
    TransformH3AggregateParams,
    TransformIntersectionParams,
    TransformJoinParams,
    TransformMergeParams,
    TransformQgisParams,
    TransformReprojectParams,
    TransformSelectParams,
    WriterCollectionParams,
    WriterDatasetParams,
    WriterExportParams,
)
```

Ensuite, ajouter à la fin de `core/app/pipelines/ops/contracts.py` (après la classe
`OperationContract`) :

```python
OPERATIONS: dict[str, OperationContract] = {
    "reader.collection": OperationContract(
        op="reader.collection",
        kind="reader",
        params_schema=ReaderCollectionParams,
    ),
    "transform.filter": OperationContract(
        op="transform.filter",
        kind="transform",
        params_schema=TransformFilterParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_filter,
    ),
    "transform.select": OperationContract(
        op="transform.select",
        kind="transform",
        params_schema=TransformSelectParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_select,
    ),
    "transform.derive": OperationContract(
        op="transform.derive",
        kind="transform",
        params_schema=TransformDeriveParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_derive,
    ),
    "transform.aggregate": OperationContract(
        op="transform.aggregate",
        kind="transform",
        params_schema=TransformAggregateParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_aggregate,
    ),
    "transform.join": OperationContract(
        op="transform.join",
        kind="transform",
        params_schema=TransformJoinParams,
        accepts_secondary_input=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_join,
    ),
    "transform.buffer": OperationContract(
        op="transform.buffer",
        kind="transform",
        params_schema=TransformBufferParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_buffer,
    ),
    "transform.reproject": OperationContract(
        op="transform.reproject",
        kind="transform",
        params_schema=TransformReprojectParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_reproject,
        output_srid=_compiler._output_srid_reproject,
    ),
    "transform.intersection": OperationContract(
        op="transform.intersection",
        kind="transform",
        params_schema=TransformIntersectionParams,
        accepts_secondary_input=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_intersection,
        output_srid=_compiler._output_srid_reconcile_join,
    ),
    "transform.countWithin": OperationContract(
        op="transform.countWithin",
        kind="transform",
        params_schema=TransformCountWithinParams,
        accepts_secondary_input=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_count_within,
        output_srid=_compiler._output_srid_reconcile_join,
    ),
    "transform.h3Aggregate": OperationContract(
        op="transform.h3Aggregate",
        kind="transform",
        params_schema=TransformH3AggregateParams,
        engine="duckdb",
        engine_license="MIT (DuckDB) + Apache-2.0 (extension communautaire h3)",
        compile=_compiler._compile_h3_aggregate,
        output_srid=_compiler._output_srid_h3_aggregate,
    ),
    "transform.qgis": OperationContract(
        op="transform.qgis",
        kind="transform",
        params_schema=TransformQgisParams,
        engine="qgis",
        engine_license="GPL-2.0-or-later (QGIS)",
        is_copyleft=True,
        execution_model="sidecar",
        output_srid=_compiler._output_srid_qgis,
    ),
    "writer.collection": OperationContract(
        op="writer.collection",
        kind="writer",
        params_schema=WriterCollectionParams,
    ),
    "writer.export": OperationContract(
        op="writer.export",
        kind="writer",
        params_schema=WriterExportParams,
    ),
    "writer.dataset": OperationContract(
        op="writer.dataset",
        kind="writer",
        params_schema=WriterDatasetParams,
    ),
    "reader.connector.rest": OperationContract(
        op="reader.connector.rest",
        kind="reader",
        params_schema=ReaderConnectorRestParams,
    ),
    "reader.connector.postgres": OperationContract(
        op="reader.connector.postgres",
        kind="reader",
        params_schema=ReaderConnectorPostgresParams,
    ),
    "reader.connector.snowflake": OperationContract(
        op="reader.connector.snowflake",
        kind="reader",
        params_schema=ReaderConnectorSnowflakeParams,
    ),
    "transform.merge": OperationContract(
        op="transform.merge",
        kind="transform",
        params_schema=TransformMergeParams,
        accepts_secondary_input=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_merge,
        output_srid=_compiler._output_srid_reconcile_join,
    ),
}

OP_KINDS: dict[str, str] = {op: c.kind for op, c in OPERATIONS.items()}
OP_PARAMS: dict[str, type[BaseModel]] = {op: c.params_schema for op, c in OPERATIONS.items()}

# Op dont la seconde entrée peut venir soit d'un paramètre `withCollectionId`,
# soit d'une arête `role="secondary"` (design SP-15g §2.2/§4.2). Exporté
# (pas `_`-préfixé) : importé directement par app.pipelines.config_validation,
# même package app.pipelines, aucune frontière de couches à traverser.
BINARY_OPS: set[str] = {op for op, c in OPERATIONS.items() if c.accepts_secondary_input}


def parse_op_params(op: str, params: dict) -> BaseModel:
    model = OP_PARAMS.get(op)
    if model is None:
        raise ValueError(f"unknown op '{op}'")
    return model.model_validate(params)


def _user_facing_description(description: str) -> str:
    """N'expose que le premier paragraphe d'un docstring de classe (avant le
    premier saut de ligne vide) comme description utilisateur du catalogue.

    Correctif revue finale GAP-16 (Important I2) : `model_json_schema()`
    reprend tel quel le docstring Python complet d'une classe de params dans
    sa clé `description` — pour 5 op (les connecteurs + transform.qgis/
    transform.merge), ce docstring contient du jargon développeur (noms de
    classes, chemins de module, renvois "design §n"/"SPnn") qui n'a rien à
    faire dans le tooltip de palette lu par
    shell/src/builder/pipeline/PipelinePalette.tsx. Le docstring de classe
    reste une documentation développeur complète (paragraphes suivants) ;
    seul le premier paragraphe — rédigé pour être compris par l'auteur d'un
    pipeline — atteint le catalogue exposé par GET /pipelines/ops."""
    return description.split("\n\n", 1)[0].strip()


def ops_catalog() -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for op, model in OP_PARAMS.items():
        schema = model.model_json_schema()
        if schema.get("description"):
            schema["description"] = _user_facing_description(schema["description"])
        catalog[op] = {
            "kind": OP_KINDS[op],
            "paramsSchema": schema,
            "acceptsSecondaryInput": op in BINARY_OPS,
        }
    return catalog
```

- [ ] **Step 4: Rebrancher les wrappers de `compiler.py` sur `OPERATIONS`**

Dans `core/app/pipelines/compiler.py`, remplacer le dict `_TRANSFORM_COMPILERS` et la fonction
`compile_transform_sql` (ajoutés par Task 2) par :

```python
def compile_transform_sql(
    op: str,
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    from app.pipelines.ops.contracts import OPERATIONS

    contract = OPERATIONS.get(op)
    if contract is None or contract.compile is None:
        raise ValueError(f"'{op}' is not a transform op")
    return contract.compile(
        params, input_view=input_view, join_view=join_view, input_srid=input_srid
    )
```

Remplacer le dict `_TRANSFORM_OUTPUT_SRID` et la fonction `transform_output_srid` (ajoutés par
Task 3) par :

```python
def transform_output_srid(
    op: str,
    params: dict,
    *,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    """SRID de sortie d'un nœud transform, calculé sans connexion DuckDB
    (pur, comme compile_transform_sql). Lève ValueError si les deux entrées
    d'une op spatiale binaire ne partagent pas le même CRS — design §2/§3.3/
    §3.4/§3.5 : aucune réconciliation implicite, jamais un résultat spatial
    silencieusement faux. runtime.py convertit ce ValueError en
    PipelineRuntimeError avant de le laisser remonter."""
    from app.pipelines.ops.contracts import OPERATIONS

    contract = OPERATIONS.get(op)
    if contract is None or contract.output_srid is None:
        return input_srid  # passthrough — comportement déjà existant, aucune
        # branche d'erreur pour un op inconnu, contrairement à
        # compile_transform_sql.
    return contract.output_srid(params, op=op, input_srid=input_srid, join_srid=join_srid)
```

L'import `from app.pipelines.ops.contracts import OPERATIONS` est **local à chaque fonction**, pas
au niveau module — c'est le patron déjà en vigueur dans ce dépôt pour rompre un cycle d'import réel
entre deux modules qui ont besoin l'un de l'autre (`app.pipelines.registries` documente exactement ce
patron pour `READERS`/`WRITERS`) : `contracts.py` importe `compiler` au niveau module (pour les
fonctions `_compile_*`/`_output_srid_*`) ; si `compiler.py` importait `contracts` au niveau module en
retour, les deux fichiers s'importeraient l'un l'autre au chargement, un cycle non résolu par aucun
ordre d'import (vérifié par trace manuelle avant ce plan).

`Callable` (importé pour `_TRANSFORM_COMPILERS`/`_TRANSFORM_OUTPUT_SRID` à Tasks 2/3) n'est plus
utilisé dans `compiler.py` après ce Step — retirer l'import `from collections.abc import Callable`
ajouté par Task 2 (sinon `ruff check` lève F401 unused import).

- [ ] **Step 5: Trimmer `ops/schemas.py`**

Remplacer le docstring de module (lignes 1-15) par :

```python
# SPDX-License-Identifier: Apache-2.0
"""Manifestes de params typés (Pydantic) par op de pipeline : 8 op de
données pures livrées en Phase 1 (SP-15a), + 5 op de transformation
spatiale étage 1, 1 writer (`writer.dataset`) et 3 connecteurs livrés
ensuite. Chaque classe ci-dessous est publiée en JSON Schema par
`app.pipelines.ops.contracts.ops_catalog()` (GET /pipelines/ops) — le
registre par op (kind/moteur/licence/compilateur/catalogue) vit dans ce
module contracts.py, pas ici : ce fichier ne fait plus que fournir les
classes de forme des params, importées par contracts.py pour construire
`OPERATIONS` (chantier OperationContract, docs/superpowers/specs/
2026-09-16-operation-contract-design.md).

filter.expr/derive.expr/aggregate.metrics[*]/h3Aggregate.metrics[*] sont des
chaînes SQL DuckDB bornées, PAS du CEL (correction du design SP-15a §5.1 —
aucun moteur CEL ne tourne côté serveur) : elles ne sont validées
syntaxiquement qu'à l'exécution (app.pipelines.expr_validation), jamais ici
— ce module ne valide que la FORME des params, pas la sémantique des
expressions."""
```

Retirer entièrement le bloc allant de `OP_KINDS: dict[str, str] = {` jusqu'à la fin du fichier
(l'ancienne fonction `ops_catalog()`) — c'est-à-dire tout ce qui suit la dernière classe
(`ReaderConnectorSnowflakeParams`, qui reste). Le fichier se termine désormais sur la classe
`ReaderConnectorSnowflakeParams` (plus aucun code après elle).

- [ ] **Step 6: Mettre à jour les 4 chemins d'import qui pointaient vers les symboles déménagés**

Dans `core/app/pipelines/routes.py`, remplacer :

```python
from app.pipelines.ops.schemas import ops_catalog
```

par :

```python
from app.pipelines.ops.contracts import ops_catalog
```

Dans `core/app/pipelines/config_validation.py`, remplacer :

```python
from app.pipelines.ops.schemas import BINARY_OPS, OP_PARAMS
```

par :

```python
from app.pipelines.ops.contracts import BINARY_OPS, OP_PARAMS
```

Dans `core/scripts/fme_coverage_cli.py`, remplacer le docstring de module ligne 12-14 :

```
--check vérifie mécaniquement les 3 règles du design (cf. docs/superpowers/
specs/2026-09-15-matrice-couverture-fme-design.md) contre le code réel du
dépôt (`app.pipelines.ops.schemas.ops_catalog`, `app.pipelines.ops.
```

par :

```
--check vérifie mécaniquement les 3 règles du design (cf. docs/superpowers/
specs/2026-09-15-matrice-couverture-fme-design.md) contre le code réel du
dépôt (`app.pipelines.ops.contracts.ops_catalog`, `app.pipelines.ops.
```

et, dans la même fonction (autour de la ligne 192-193) :

```python
        from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS
        from app.pipelines.ops.schemas import ops_catalog
```

par (ordre alphabétique isort : `contracts` avant `qgis_algorithms`) :

```python
        from app.pipelines.ops.contracts import ops_catalog
        from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS
```

Dans `core/tests/test_pipeline_ops_schemas.py`, remplacer le bloc d'import (lignes 5-12) :

```python
from app.pipelines.ops.schemas import (
    OP_KINDS,
    OP_PARAMS,
    WriterCollectionParams,
    WriterDatasetParams,
    ops_catalog,
    parse_op_params,
)
```

par :

```python
from app.pipelines.ops.contracts import OP_KINDS, OP_PARAMS, ops_catalog, parse_op_params
from app.pipelines.ops.schemas import WriterCollectionParams, WriterDatasetParams
```

et, dans `test_binary_ops_set_matches_catalog_flag` (ligne 443), remplacer :

```python
    from app.pipelines.ops.schemas import BINARY_OPS
```

par :

```python
    from app.pipelines.ops.contracts import BINARY_OPS
```

- [ ] **Step 7: Run tests to verify they pass**

Run:
```bash
cd core && PYTHONPATH=. uv run pytest \
  tests/test_pipeline_ops_contracts.py \
  tests/test_pipeline_ops_schemas.py \
  tests/test_pipeline_compiler.py \
  tests/test_pipeline_routes.py \
  tests/test_pipeline_config_validation.py \
  tests/test_pipeline_runtime.py \
  tests/test_pipeline_connector_runtime.py \
  tests/test_fme_coverage_cli.py \
  -v
```
Expected: tous passed, y compris les 6 nouveaux tests de `test_pipeline_ops_contracts.py` (3 de
Task 1 + 3 de ce Step) et `test_get_pipelines_ops_returns_all_nineteen`
(`test_pipeline_routes.py`) — la réponse JSON de `GET /v1/pipelines/ops` doit lister exactement les
mêmes 19 op qu'avant ce plan.

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/ops/contracts.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/schemas.py core/app/pipelines/routes.py \
  core/app/pipelines/config_validation.py core/scripts/fme_coverage_cli.py \
  core/tests/test_pipeline_ops_schemas.py core/tests/test_pipeline_ops_contracts.py
git commit -m "refactor(core): OPERATIONS devient la source unique du registre d'op de pipeline"
```

---

### Task 5: portes de qualité et clôture

**Files:**
- Modify: `CLAUDE.md` (section `### Livré`)

**Interfaces:** aucune — tâche de vérification et de documentation, ne change aucun comportement de
code.

- [ ] **Step 1: Suite complète `core`**

Run: `cd core && PYTHONPATH=. uv run pytest -q`
Expected: aucune régression par rapport au dernier compte connu de `CLAUDE.md` (`## Commandes`) —
noter le compte réel obtenu (passed/skipped/failed) pour l'entrée de clôture au Step 5. Si des
échecs apparaissent, vérifier d'abord s'ils sont préexistants (`git stash`, rejouer le même test sur
l'état d'avant ce plan) avant de les imputer à ce plan — piège CLAUDE.md n°9/n°12.

- [ ] **Step 2: Lint et frontières de modules**

Run:
```bash
cd core && uv run ruff check . && uv run ruff format --check .
cd core && uv run lint-imports
```
Expected: les deux verts, sans nouvelle exemption dans `[tool.importlinter]` (aucune n'est attendue
— `contracts.py` et `compiler.py` sont tous deux dans le même layer `app.pipelines` du contrat de
couches, vérifié en amont de ce plan).

- [ ] **Step 3: Diff OpenAPI/types TS — attendu vide**

Run:
```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
git diff --stat core/openapi.json
cd ../shell && npm run gen:api-types
git diff --stat shell/src/api/generated/core-schema.d.ts
```
Expected: aucun des deux `git diff --stat` ne montre de changement (ce plan ne touche aucune route
ni aucun modèle Pydantic exposé par l'API REST/MCP). Si un diff apparaît, ne pas commiter tant que la
cause n'est pas comprise — ce serait un signe qu'un changement de comportement observable a fuité
hors de ce plan.

- [ ] **Step 4: `git diff --stat -- shell/` — attendu vide**

Run: `git diff --stat origin/dev...HEAD -- shell/`
Expected: vide — ce plan ne touche aucun fichier `shell/` (spec §2, Global Constraints).

- [ ] **Step 5: Entrée de clôture dans `CLAUDE.md`**

Ajouter, dans `CLAUDE.md`, une nouvelle entrée à la **toute fin** de la section `### Livré` (après la
dernière entrée existante, `priorite-moyenne-sante-90`) — c'est là que les entrées les plus récentes
sont ajoutées (vérifié : la section n'est pas strictement chronologique par date de SP, mais chaque
nouvel ajout va en dernier). Même style que les entrées voisines (une ligne de titre en gras, suivie
du détail vérifié en session — chiffres réels des Steps 1-4 ci-dessus, pas recopiés d'une autre
exécution). Structure attendue (à remplir avec les valeurs réellement mesurées, jamais devinées) :

```markdown
- **OperationContract** — remplace, pour les 19 op de pipeline déjà
  livrées, les 5 structures parallèles indexées par nom d'op
  (`app.pipelines.ops.schemas::OP_PARAMS`/`OP_KINDS`/`BINARY_OPS`,
  `app.pipelines.compiler::compile_transform_sql`/`transform_output_srid`)
  par un type unique `OperationContract` (schéma/moteur/licence/modèle
  d'exécution/compilateur/règle de SRID de sortie) et un registre unique
  `app.pipelines.ops.contracts::OPERATIONS` — spec
  `docs/superpowers/specs/2026-09-16-operation-contract-design.md`. Règle
  généralisée et testée : licence copyleft ⇒ modèle d'exécution `sidecar`
  obligatoire (`transform.qgis`, seul moteur externe existant, vérifié
  conforme). Comportement externe inchangé, prouvé par la suite existante
  (`test_pipeline_compiler.py` vert sans aucune modification) — diff
  `openapi.json`/`core-schema.d.ts` vide, zéro fichier `shell/` touché.
  **Écart au texte de la spec, nécessaire (import circulaire réel)** :
  `OP_KINDS`/`OP_PARAMS`/`BINARY_OPS`/`parse_op_params`/`ops_catalog`
  déménagent dans `contracts.py` plutôt que rester dans `schemas.py` —
  `contracts.py` a besoin des classes Pydantic de `schemas.py` au niveau
  module pour construire `OPERATIONS` ; l'inverse (schemas.py import
  contracts.py au niveau module pour ses vues dérivées) aurait fermé un
  cycle à 2 nœuds non résolvable par aucun ordre d'import — vérifié par
  trace manuelle avant d'écrire le plan. `schemas.py` ne porte plus que les
  classes Pydantic de forme des params. **Hors périmètre, explicitement
  (spec §2)** : aucun nouveau moteur câblé (GDAL/PDAL/OTB/Rust), aucune
  nouvelle op, licence des 7 op readers/writers/connecteurs. Suite finale :
  [chiffres réels core, à remplir avec le résultat du Step 1] ;
  ruff/ruff format/lint-imports verts ; diff openapi.json/core-schema.d.ts
  vide (vérifié) ; `git diff --stat -- shell/` vide (vérifié).
```

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: clôture du chantier OperationContract"
```
