# SP-43 — Refactorisation structurelle : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer les 6 classes de duplication mécanique identifiées par la spec
SP-43 (mapping kind→privilège à 4 sites, `toFrontLayer()` sans filet, boilerplate
de job dupliqué 5x, fixture E2E de collection incomplète, ~24 colonnes
modèle/Alembic divergentes, convention `aria-expanded` non câblée) puis découper
les 3 fichiers les plus mélangés du dépôt (`itemClient.ts`, `mcp/tools.py`,
`pipelines/runtime.py`) derrière des façades stables, dans l'ordre du moins au
plus risqué défini par la spec.

**Architecture:** 10 tâches = les 10 étapes du §5 de la spec, dans le même
ordre (chaque étape nomme son propre filet de test, à poser **avant** de
toucher le code qu'elle protège). Aucune tâche ne change de comportement
fonctionnel observable — uniquement des déplacements de code et des ajouts de
filets, conformément au §7 (hors périmètre) de la spec.

**Tech Stack:** Python/FastAPI + SQLAlchemy + Alembic + pytest (cœur),
TypeScript/React + Vitest + Playwright (shell), DuckDB (pipelines).

**Document source :**
`docs/superpowers/specs/2026-09-04-sp43-refactorisation-structurelle-design.md`
(sections citées : §1 motivation, §3 abstractions, §5 ordre, §6 risques, §7
hors périmètre).

## Global Constraints

- **Aucun changement de comportement fonctionnel.** Chaque tâche ne fait que
  déplacer du code ou ajouter un filet — toute correction de bug métier est
  hors périmètre (spec §7).
- **TDD / filet-avant-code** : chaque tâche pose son filet de test (nouveau ou
  vérifié existant) **avant** de toucher le code qu'elle protège — jamais après.
- Commits **conventional**, un sujet par commit, français dans les messages
  (`refactor(core): ...`, `test(core): ...`, `refactor(shell): ...`).
- **Suite complète rejouée avant de clore chaque tâche** — jamais un
  sous-ensemble (piège CLAUDE.md n°6) : `cd core && uv run pytest`,
  `cd shell && npm run test`, et pour les tâches qui touchent aux routes/UI
  observables, `npm run e2e`.
- **Toute migration testée sur base non vide, dans les deux sens** (piège
  CLAUDE.md n°8) — upgrade puis downgrade puis re-upgrade sur une base jetable
  contenant déjà des lignes.
- **Tout filet de test ajouté doit être vérifié par falsification** (piège
  CLAUDE.md n°10) : injecter délibérément le défaut visé, confirmer que le
  test échoue, puis retirer l'injection — jamais supposer qu'un filet marche
  parce qu'il passe.
- **Régénérer la spec OpenAPI + types TS** uniquement si une route ou un
  modèle de réponse change (piège CLAUDE.md n°1) — diff **vide** attendu et
  légitime pour les Tâches 1, 2, 5, 6, 10 (déplacement interne, aucune forme
  de réponse HTTP ne change).
- **Hors périmètre explicite (spec §7)**, à ne pas toucher dans ce plan :
  `shell/src/api/types.ts`, `core/app/analytics/aggregate.py`,
  `core/app/harvest/routes.py`, `shell/src/builder/widgets/mapSymbology.ts`,
  les 5 tests `@pytest.mark.qgis` eux-mêmes (déjà exécutés avec succès par
  SP-44, jalon M14 atteint), les 3 divergences déjà tranchées le 2026-09-01
  (hauteur `h-9`, `Button` du kit vs `<button>` natif, principe
  `aria-expanded` — seule son **application mécanique** est reprise en Tâche
  7), la question `<main>`/`<aside>`/`<div>` (déjà tranchée SP-30f), et le
  reste des 43 trouvailles `confirme` non retenues par la spec (backlog
  `docs/revue/2026-09-04-backlog.md`).
- **Conteneur `postgis-test` non tracké par Alembic** : après toute migration
  qui ajoute des colonnes, un `ALTER TABLE` manuel peut être nécessaire sur ce
  conteneur avant de rejouer la suite (CLAUDE.md, suivi récurrent).

---

## Task 1 (Étape 0) : comparateur modèle SQLAlchemy ↔ schéma Alembic

Filet transverse — **aucune tâche suivante qui touche un modèle SQLAlchemy
(Tâche 5) ne doit commencer avant que ce filet existe et soit vérifié par
falsification.** Risque : nul (ajout pur, aucun code existant modifié).

**Files:**
- Create: `core/tests/test_model_alembic_parity.py`
- Test: lui-même (c'est le filet)

**Interfaces:**
- Consumes: le patron de fixture de
  `core/tests/test_attachments_migration_alembic.py` /
  `test_metadata_migration_alembic.py` (base jetable Postgres, `Config()` sans
  fichier ini) ; `core/tests/conftest.py` (fixture `pg_engine`, qui utilise
  `Base.metadata.create_all()` — **PAS** `alembic upgrade head` — donc ne peut
  pas servir de base pour ce test).
- Produces: rien consommé par le code de production ; sert de garde-fou
  d'exécution pour la Tâche 5 (le futur `uv run pytest
  core/tests/test_model_alembic_parity.py` doit être vert avant et après
  chaque colonne corrigée).

- [ ] **Step 1 : localiser le nom exact de la base déclarative partagée**

Cette information n'a pas été confirmée par la recherche préalable — la
localiser avant d'écrire le test :

```bash
grep -rn "declarative_base\|^Base = \|class Base" core/app --include=*.py
```

Attendu : une seule définition centrale (probablement `core/app/db.py` ou
`core/app/database.py`), importée par tous les `models.py` du dépôt via
`from app.db import Base` (ou chemin équivalent trouvé par le grep). Utiliser
ce chemin exact dans le test ci-dessous — ne pas deviner.

- [ ] **Step 2 : lire le patron de fixture existant**

```bash
sed -n '1,60p' core/tests/test_metadata_migration_alembic.py
```

Réutiliser à l'identique : la fixture `throwaway_database_url` (crée
`sp4x_migration_<uuid8>`, active `postgis`/`vector`/`pg_trgm`, détruit en
`finally`), et la construction de `Config()` **sans fichier ini** (passer
`Config("alembic.ini")` désactive silencieusement des loggers d'autres
modules via `fileConfig(disable_existing_loggers=True)` — piège déjà payé une
fois).

- [ ] **Step 3 : écrire le test de parité**

```python
# core/tests/test_model_alembic_parity.py
"""Compare le schéma réel produit par `alembic upgrade head` au schéma déclaré
par les modèles SQLAlchemy (Base.metadata) — filet transverse de SP-43 Étape 0.
Sans lui, un `server_default=` ajouté en migration mais oublié sur le
`mapped_column` correspondant (ou l'inverse) est invisible : la suite pytest
construit son schéma via `Base.metadata.create_all()` (jamais via Alembic),
donc un défaut qui n'existe qu'en production migrée ne peut jamais être vu
par aucun autre test du dépôt (cf. F-tests-01, sp42-findings.jsonl)."""

import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.db import Base  # chemin exact confirmé par le Step 1

pytestmark = pytest.mark.postgis

CORE_DIR = None  # résolu ci-dessous, cf. test_metadata_migration_alembic.py


def _alembic_config(db_url: str) -> Config:
    from pathlib import Path

    core_dir = Path(__file__).resolve().parents[1]
    cfg = Config()
    cfg.set_main_option("script_location", str(core_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_model_metadata_matches_migrated_schema(throwaway_database_url):
    cfg = _alembic_config(throwaway_database_url)
    command.upgrade(cfg, "head")

    engine = sa.create_engine(throwaway_database_url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        diff = compare_metadata(ctx, Base.metadata)

    # Filtrer les types PostGIS/pgvector (géométrie, vector) : leur
    # représentation SQLAlchemy générique diffère toujours du type natif
    # Postgres et ne constitue jamais un vrai écart de schéma.
    ignored_kinds = {"geometry", "vector"}
    real_diff = [
        d
        for d in diff
        if not (
            d[0] == "modify_type"
            and (
                getattr(d[6], "__visit_name__", "") in ignored_kinds
                or getattr(d[5], "__visit_name__", "") in ignored_kinds
            )
        )
    ]
    assert real_diff == [], (
        "Schéma migré (Alembic head) et Base.metadata divergent : "
        f"{real_diff}\nCorriger le server_default= manquant côté modèle "
        "OU la migration manquante côté Alembic — ne jamais supprimer ce "
        "test pour faire passer un diff réel."
    )
```

- [ ] **Step 4 : lancer le test, s'attendre à un résultat NON VIDE (le diff réel actuel)**

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -v
```

Attendu : le test **échoue**, listant les colonnes divergentes recensées par
la Tâche 5 (~24 colonnes). C'est le comportement correct à ce stade — le
filet fonctionne, il détecte l'écart réel qui n'est pas encore corrigé.

- [ ] **Step 5 : falsifier le filet (vérifier qu'il détecte bien un nouveau cas)**

Reproduire la preuve de `F-tests-01` : ajouter temporairement une colonne
sans migration sur un modèle qui n'a **aucune** divergence connue (ex.
`core/app/items/models.py`, ajouter `sp43_probe: Mapped[str] = mapped_column(String, default="x")` juste après un champ existant), relancer le test, confirmer un nouvel écart apparaît nommément pour `sp43_probe`, puis **retirer** l'ajout.

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -v -k model_metadata
# vérifier "sp43_probe" apparaît dans le diff avant de retirer l'injection
git diff core/app/items/models.py  # confirmer le retrait complet avant de continuer
```

- [ ] **Step 6 : commit**

```bash
git add core/tests/test_model_alembic_parity.py
git commit -m "$(cat <<'EOF'
test(core): ajoute le comparateur modèle SQLAlchemy vs schéma Alembic migré

Filet transverse SP-43 Étape 0 : compare_metadata() contre une base
réellement migrée (alembic upgrade head), jamais couvert jusqu'ici car
la suite pytest construit son schéma via Base.metadata.create_all().
EOF
)"
```

Ce test reste **rouge** jusqu'à la fin de la Tâche 5 — c'est attendu, ne pas
le neutraliser (`xfail`/skip) entre les deux tâches.

---

## Task 2 (Étape 1) : registre kind→privilège unique

Ferme la classe de bug qui a coûté 3 réouvertures (spec §1.1). Risque : bas.

**Files:**
- Create: `core/app/roles/kind_registry.py`
- Modify: `core/app/configs/routes.py:127-144`
- Modify: `core/app/mcp/tools.py` (import + `_require_config_privilege`,
  lignes 195-210)
- Modify: `core/app/tileset3d/routes.py` (lignes 110, 182)
- Modify: `core/app/pipelines/routes.py:56-79`
  (`_require_data_manage_if_pipeline_writes_dataset`)
- Test: `core/tests/test_kind_registry.py` (nouveau), vérifier
  `core/tests/test_configs_privilege_guard.py`,
  `core/tests/test_mcp_configs_privilege_guard.py` restent verts inchangés.

**Interfaces:**
- Consumes: `core/app/roles/privileges.py::Privilege` (18 valeurs, énumérées
  ci-dessous), `core/app/roles/guards.py::require_privilege(session, user,
  privilege: str) -> None`.
- Produces: `core/app/roles/kind_registry.py::privilege_for_kind(kind: str)
  -> str` — fonction **publique**, seule source de vérité, consommée par les
  4 sites ci-dessus.

- [ ] **Step 1 : écrire le test du registre (avant de créer le module)**

```python
# core/tests/test_kind_registry.py
"""Registre unique kind -> privilège requis — SP-43 Étape 1. Remplace le
dict privé _KIND_PRIVILEGE de app.configs.routes, consommé jusqu'ici par 4
sites avec 3 formes de couplage différentes (import de nom privé, import du
dict privé lui-même, recopie de valeur en dur) — cf. spec §1.1."""

import pytest

from app.roles.kind_registry import privilege_for_kind
from app.roles.privileges import Privilege

KNOWN_KINDS = {
    "app": Privilege.APPS_MANAGE.value,
    "dashboard": Privilege.APPS_MANAGE.value,
    "site": Privilege.APPS_MANAGE.value,
    "map": Privilege.MAPS_MANAGE.value,
    "dataset": Privilege.DATA_MANAGE.value,
    "pipeline": Privilege.AUTOMATION_MANAGE.value,
    "alert": Privilege.AUTOMATION_MANAGE.value,
    "report": Privilege.AUTOMATION_MANAGE.value,
    "bookmark": Privilege.ANALYTICS_VIEW.value,
    "tileset3d": Privilege.CATALOG_MANAGE.value,
    "terrain3d": Privilege.CATALOG_MANAGE.value,
}


@pytest.mark.parametrize("kind,expected", list(KNOWN_KINDS.items()))
def test_privilege_for_known_kind(kind: str, expected: str) -> None:
    assert privilege_for_kind(kind) == expected


def test_privilege_for_unknown_kind_falls_back_to_catalog_manage() -> None:
    assert privilege_for_kind("unknown-future-kind") == Privilege.CATALOG_MANAGE.value
```

- [ ] **Step 2 : lancer le test, vérifier qu'il échoue (module inexistant)**

```bash
cd core && uv run pytest tests/test_kind_registry.py -v
```

Expected: `FAIL` — `ModuleNotFoundError: No module named 'app.roles.kind_registry'`

- [ ] **Step 3 : créer le registre public**

```python
# core/app/roles/kind_registry.py
"""Registre unique kind -> privilège requis pour créer/modifier une config.

Source de vérité unique, consommée par app.configs.routes, app.mcp.tools,
app.tileset3d.routes et app.pipelines.routes — remplace 4 formes de couplage
distinctes (import de nom privé, import de dict privé, recopie de valeur en
dur) qui ont laissé rouvrir 3 fois le même défaut d'autorisation (cf. spec
SP-43 §1.1, sp42-findings.jsonl F-securite-autorisation-01)."""

from app.roles.privileges import Privilege

_KIND_PRIVILEGE: dict[str, str] = {
    "app": Privilege.APPS_MANAGE.value,
    "dashboard": Privilege.APPS_MANAGE.value,
    "site": Privilege.APPS_MANAGE.value,
    "map": Privilege.MAPS_MANAGE.value,
    "dataset": Privilege.DATA_MANAGE.value,
    "pipeline": Privilege.AUTOMATION_MANAGE.value,
    "alert": Privilege.AUTOMATION_MANAGE.value,
    "report": Privilege.AUTOMATION_MANAGE.value,
    "bookmark": Privilege.ANALYTICS_VIEW.value,
    "tileset3d": Privilege.CATALOG_MANAGE.value,
    "terrain3d": Privilege.CATALOG_MANAGE.value,
}


def privilege_for_kind(kind: str) -> str:
    return _KIND_PRIVILEGE.get(kind, Privilege.CATALOG_MANAGE.value)
```

- [ ] **Step 4 : lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_kind_registry.py -v
```

Expected: `12 passed`

- [ ] **Step 5 : migrer `configs/routes.py` (le site d'origine)**

Dans `core/app/configs/routes.py`, remplacer les lignes 127-144 :

```python
# AVANT (supprimé)
_KIND_PRIVILEGE: dict[str, str] = {
    "app": Privilege.APPS_MANAGE.value,
    ...
}

def _require_privilege_for_kind(session: Session, user: User, config: BuilderConfig) -> None:
    privilege = _KIND_PRIVILEGE.get(config.kind, Privilege.CATALOG_MANAGE.value)
    require_privilege(session, user, privilege)
```

```python
# APRÈS
from app.roles.kind_registry import privilege_for_kind

def _require_privilege_for_kind(session: Session, user: User, config: BuilderConfig) -> None:
    require_privilege(session, user, privilege_for_kind(config.kind))
```

Cette fonction wrapper reste (les autres call sites REST internes à
`configs/routes.py` continuent de l'appeler par son nom actuel) — seul son
corps change de source.

- [ ] **Step 6 : lancer `test_configs_privilege_guard.py`, vérifier zéro régression**

```bash
cd core && uv run pytest tests/test_configs_privilege_guard.py -v
```

Expected: tous les tests existants (paramétrés sur les 11 kinds) passent
sans modification.

- [ ] **Step 7 : migrer `tileset3d/routes.py` (cesse d'indexer un dict privé d'un autre module)**

```python
# AVANT (ligne 20)
from app.configs.routes import _KIND_PRIVILEGE
# ... ligne 110 et 182
require_privilege(session, user, _KIND_PRIVILEGE["tileset3d"])
```

```python
# APRÈS
from app.roles.kind_registry import privilege_for_kind
# ... ligne 110 et 182
require_privilege(session, user, privilege_for_kind("tileset3d"))
```

Appliquer ce remplacement aux **deux** call sites (ligne 110, création
d'upload ; ligne 182, `complete_tileset3d_upload`).

- [ ] **Step 8 : migrer `mcp/tools.py` (cesse d'importer un nom privé cross-module)**

```python
# AVANT — appelle _require_privilege_for_kind (nom privé importé
# verbatim d'un autre module), lignes 195-210
def _require_config_privilege(session, config: BuilderConfig, *, user: User) -> None:
    """... Reuses app.configs.routes._require_privilege_for_kind verbatim ..."""
    try:
        _require_privilege_for_kind(session, user, config)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc
```

```python
# APRÈS — appelle directement le registre public + la garde publique,
# plus aucun import de nom privé
from app.roles.kind_registry import privilege_for_kind
from app.roles.guards import require_privilege

def _require_config_privilege(session, config: BuilderConfig, *, user: User) -> None:
    try:
        require_privilege(session, user, privilege_for_kind(config.kind))
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc
```

Retirer l'import devenu inutile de `_require_privilege_for_kind` en haut du
fichier s'il existe encore.

- [ ] **Step 9 : lancer `test_mcp_configs_privilege_guard.py`, vérifier zéro régression**

```bash
cd core && uv run pytest tests/test_mcp_configs_privilege_guard.py -v
```

- [ ] **Step 10 : migrer `pipelines/routes.py` (cesse de recopier `Privilege.DATA_MANAGE.value` en dur)**

```python
# AVANT (lignes 56-79)
def _require_data_manage_if_pipeline_writes_dataset(
    session: Session, user: User, config: ConfigRead
) -> None:
    if _pipeline_writes_dataset(config):
        require_privilege(session, user, Privilege.DATA_MANAGE.value)
```

```python
# APRÈS — consulte désormais le même registre que les 3 autres sites,
# au lieu d'une synchronisation manuelle documentée en commentaire seulement
from app.roles.kind_registry import privilege_for_kind

def _require_data_manage_if_pipeline_writes_dataset(
    session: Session, user: User, config: ConfigRead
) -> None:
    if _pipeline_writes_dataset(config):
        require_privilege(session, user, privilege_for_kind("dataset"))
```

`_pipeline_writes_dataset` (inchangée) reste la détection de
`node.op == "writer.dataset"` — seule la valeur de privilège change de
source.

- [ ] **Step 11 : lancer la suite complète des tests d'autorisation touchés**

```bash
cd core && uv run pytest tests/test_configs_privilege_guard.py \
  tests/test_mcp_configs_privilege_guard.py \
  tests/test_kind_registry.py \
  -k "tileset3d or pipeline" -v
cd core && uv run pytest tests/ -k "tileset3d" -v
cd core && uv run pytest tests/ -k "pipeline_routes or pipeline_jobs" -v
```

- [ ] **Step 12 : grep de clôture (patron déjà utilisé par SP-34/SP-37)**

```bash
grep -rn "_KIND_PRIVILEGE\|DATA_MANAGE.value" core/app --include=*.py
```

Expected: **zéro résultat** hors de `core/app/roles/kind_registry.py`
lui-même. Un résultat résiduel signale un site oublié — ne pas clore la
tâche tant que ce grep n'est pas vide (cf. spec §6, risque Étape 1).

- [ ] **Step 13 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 14 : commit**

```bash
git add core/app/roles/kind_registry.py core/app/configs/routes.py \
  core/app/mcp/tools.py core/app/tileset3d/routes.py \
  core/app/pipelines/routes.py core/tests/test_kind_registry.py
git commit -m "$(cat <<'EOF'
refactor(core): unifie le mapping kind->privilège dans un registre public

privilege_for_kind() remplace le dict privé _KIND_PRIVILEGE de
configs/routes.py, consommé jusqu'ici par 4 sites avec 3 formes de
couplage fragile (import de nom privé, import de dict privé, valeur
recopiée en dur) — ce défaut avait été rouvert 3 fois avant SP-42.
Comportement inchangé, seul le point d'accès est unifié.
EOF
)"
```

---

## Task 3 (Étape 2) : test caractéristique de `toFrontLayer()`

Filet pur — le code de `toFrontLayer()` reste inchangé dans cette tâche (à
date, tous les champs optionnels connus sont déjà gérés ; ce test protège
contre une 5e régression future, il n'en corrige pas une actuelle). Risque :
bas.

**Files:**
- Modify: `shell/src/api/itemClient.test.ts` (ajout de tests, pas de
  suppression)
- Test: lui-même

**Interfaces:**
- Consumes: `toFrontLayer` (non exportée aujourd'hui — cf. Step 1),
  `RawMapLayer` (type local `itemClient.ts:77-96`), `MapLayer` (union
  discriminée exportée, `shell/src/api/types.ts:189-234`, 5 kinds : `vector`,
  `raster`, `feature`, `deck`, `tiles3d`).
- Produces: rien de nouveau consommé ailleurs — filet pur, réutilisé par la
  Tâche 8 (tout futur point de conversion raw↔front similaire découvert
  pendant le découpage d'`itemClient.ts` doit recevoir un test du même
  gabarit, cf. spec §6 risque Étape 7).

- [ ] **Step 1 : exporter `toFrontLayer` pour le rendre testable directement**

`toFrontLayer` est aujourd'hui une fonction top-level non exportée
(`itemClient.ts:98`). Ajouter `export` devant sa déclaration — aucun autre
changement :

```ts
// itemClient.ts:98 — AVANT
function toFrontLayer(l: RawMapLayer): MapLayer {

// APRÈS
export function toFrontLayer(l: RawMapLayer): MapLayer {
```

Exporter aussi le type `RawMapLayer` (ligne 77) de la même façon :
`export type RawMapLayer = { ... }`.

- [ ] **Step 2 : écrire le test caractéristique — vector (6 champs optionnels)**

Ajouter dans `shell/src/api/itemClient.test.ts`, à la suite des 4 tests de
régression existants (après ligne ~581) :

```ts
// SP-43 Étape 2 : test caractéristique — pour chaque kind de MapLayer, un
// RawMapLayer avec TOUS ses champs optionnels renseignés doit survivre
// intégralement à toFrontLayer(). Filet contre une 5e perte de champ
// silencieuse (les 4 précédentes : popup, symbology, renderAs,
// collectionId/pkColumn — cf. les 4 tests de régression ci-dessus).
import { toFrontLayer, type RawMapLayer } from "./itemClient";

describe("toFrontLayer characteristic test — no optional field is ever dropped", () => {
  test("vector: every optional field survives", () => {
    const raw: RawMapLayer = {
      id: "v1",
      title: "V",
      visible: true,
      kind: "vector",
      tilesUrl: "https://t",
      sourceLayer: "s",
      paint: { "fill-color": "#fff" },
      collectionId: "c1",
      geometryKind: "polygon",
      pkColumn: "id",
      popup: { titleField: "nom", fields: [] },
      symbology: { kind: "categorical", field: "type", categories: [] } as never,
    };
    const out = toFrontLayer(raw) as Record<string, unknown>;
    expect(out.paint).toEqual(raw.paint);
    expect(out.collectionId).toBe(raw.collectionId);
    expect(out.geometryKind).toBe(raw.geometryKind);
    expect(out.pkColumn).toBe(raw.pkColumn);
    expect(out.popup).toEqual(raw.popup);
    expect(out.symbology).toEqual(raw.symbology);
  });

  test("feature: every optional field survives", () => {
    const raw: RawMapLayer = {
      id: "f1",
      title: "F",
      visible: true,
      kind: "feature",
      url: "https://fs/a",
      paint: { "fill-color": "#000" },
      collectionId: "c2",
      pkColumn: "fid",
      popup: { titleField: "nom", fields: [] },
      renderAs: "circle",
      symbology: { kind: "categorical", field: "type", categories: [] } as never,
    };
    const out = toFrontLayer(raw) as Record<string, unknown>;
    expect(out.paint).toEqual(raw.paint);
    expect(out.collectionId).toBe(raw.collectionId);
    expect(out.pkColumn).toBe(raw.pkColumn);
    expect(out.popup).toEqual(raw.popup);
    expect(out.renderAs).toBe(raw.renderAs);
    expect(out.symbology).toEqual(raw.symbology);
  });

  test("raster: optional field (opacity) survives", () => {
    const raw: RawMapLayer = {
      id: "r1",
      title: "R",
      visible: true,
      kind: "raster",
      tilesUrl: "https://t",
      opacity: 0.5,
    };
    const out = toFrontLayer(raw) as Record<string, unknown>;
    expect(out.opacity).toBe(0.5);
  });

  test("deck: optional field (props) survives", () => {
    const raw: RawMapLayer = {
      id: "d1",
      title: "D",
      visible: true,
      kind: "deck",
      deckType: "heatmap",
      dataUrl: "https://d",
      props: { radius: 30 },
    };
    const out = toFrontLayer(raw) as Record<string, unknown>;
    expect(out.props).toEqual(raw.props);
  });
});
```

- [ ] **Step 3 : lancer les nouveaux tests, vérifier qu'ils passent (code déjà correct)**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "characteristic test"
```

Expected: `4 passed` — confirme qu'à date, aucun champ n'est réellement
perdu (cohérent avec la recherche : les 4 pertes historiques ont chacune
déjà été corrigées ponctuellement).

- [ ] **Step 4 : falsifier le filet (piège CLAUDE.md n°10)**

Retirer temporairement `...(l.symbology ? { symbology: l.symbology } : {}),`
de la branche `case "vector":` de `toFrontLayer()`, relancer le test ciblé,
confirmer qu'il échoue sur `expect(out.symbology)`, puis restaurer la ligne.

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "vector: every optional field survives"
# confirmer FAIL, puis git checkout -- src/api/itemClient.ts pour restaurer
```

- [ ] **Step 5 : suite complète du fichier**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts
```

Expected: 169 + 4 = 173 passed.

- [ ] **Step 6 : commit**

```bash
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "$(cat <<'EOF'
test(shell): ajoute un test caractéristique pour toFrontLayer()

Pour chaque kind de MapLayer, vérifie qu'un RawMapLayer avec tous ses
champs optionnels renseignés survit intégralement — filet contre une
5e perte de champ silencieuse (les 4 précédentes : popup, symbology,
renderAs, collectionId/pkColumn, chacune découverte a posteriori).
toFrontLayer/RawMapLayer exportées pour être testables directement.
EOF
)"
```

---

## Task 4 (Étape 3) : fixture de collection E2E unique

Risque : bas — E2E uniquement, aucun code de production touché.

**Files:**
- Create: `core/tests/test_collections_json_contract.py`
- Modify: `shell/e2e/mocks.ts` (ajout de `mockCollection`)
- Modify: `shell/e2e/admin-collections.spec.ts` (utilise la fixture au lieu
  des 3 littéraux incomplets)
- Test: les deux fichiers ci-dessus

**Interfaces:**
- Consumes: `core/app/collections/routes.py::_collection_json` (23 clés
  exactes, lignes 149-174), `shell/e2e/mocks.ts::mockMe` (patron de fixture
  existant, lignes 99-125, précédent SP-30l).
- Produces: `shell/e2e/mocks.ts::mockCollection(overrides?)` — nouvelle
  fixture, consommée par `admin-collections.spec.ts` (et tout futur test
  E2E de collection).

- [ ] **Step 1 : écrire le test de contrat côté cœur (liste les 23 clés réelles)**

```python
# core/tests/test_collections_json_contract.py
"""Contrat de sérialisation de _collection_json — SP-43 Étape 3. Sert
d'oracle pour shell/e2e/mocks.ts::mockCollection() : si une clé est ajoutée
ou retirée ici sans mise à jour miroir côté fixture E2E, ce test continue de
passer (il ne connaît pas le TS) mais documente la liste exacte à tenir à
jour manuellement des deux côtés — cf. commentaire miroir dans mocks.ts."""

from datetime import datetime

from app.collections.models import Collection
from app.collections.routes import _collection_json
from app.items.schemas import ItemPermissions

EXPECTED_KEYS = {
    "id", "title", "description", "tableName", "isPublic", "editable",
    "geometryType", "srid", "pkColumn", "permissions", "featureCount",
    "owner", "attachmentFields", "license", "licenseUri", "producer",
    "contact", "updateFrequency", "lineage", "language", "version",
    "temporalStart", "temporalEnd",
}


def test_collection_json_serializes_exactly_the_documented_23_keys() -> None:
    col = Collection(
        id="c1", title="T", description="", table_name="t1",
        is_public=False, editable=True, geometry_type="Point", srid=4326,
        pk_column="id", feature_count=0, attachment_fields=[], license="",
        license_uri="", producer="", contact="", update_frequency="",
        lineage="", language="", version="", temporal_start=None,
        temporal_end=None,
    )
    permissions = ItemPermissions(read=True, write=True, delete=False, share=True)

    result = _collection_json(col, permissions, owner="mockuser")

    assert set(result.keys()) == EXPECTED_KEYS
    assert len(EXPECTED_KEYS) == 23
```

- [ ] **Step 2 : lancer le test, ajuster la construction de `Collection`/`ItemPermissions` si le constructeur diffère**

```bash
cd core && uv run pytest tests/test_collections_json_contract.py -v
```

Si le constructeur de `Collection` ou `ItemPermissions` exige d'autres
champs obligatoires que ceux listés ci-dessus, les ajouter en lisant
`core/app/collections/models.py` — ne pas deviner un champ manquant sans
vérifier son nom exact dans le modèle.

- [ ] **Step 3 : falsifier le filet**

Ajouter temporairement une clé factice au `return` de `_collection_json`
(ex. `"sp43Probe": None`), relancer le test, confirmer l'échec sur
`set(result.keys()) == EXPECTED_KEYS`, puis retirer.

- [ ] **Step 4 : ajouter la fixture `mockCollection` dans `shell/e2e/mocks.ts`**

Reprendre exactement le patron de `mockMe` (lignes 99-125) :

```ts
// Fixture canonique du payload de collection servi par _collection_json()
// (core/app/collections/routes.py) — SP-43 Étape 3, même patron que
// mockMe() (SP-30l) pour la dérive équivalente sur GET /me. Les 23 clés
// doivent rester synchronisées avec core/tests/test_collections_json_contract.py
// (EXPECTED_KEYS) — un futur champ ajouté côté cœur doit être ajouté ici
// ET dans ce test Python, sinon cette fixture redevient incomplète comme
// les 3 littéraux qu'elle remplace (cf. spec SP-43 §1.5).
const DEFAULT_COLLECTION = {
  id: "points_interet",
  title: "Points d'intérêt",
  description: "",
  tableName: "points_interet",
  isPublic: false,
  editable: true,
  geometryType: "Point",
  srid: 4326,
  pkColumn: "id",
  permissions: { read: true, write: true, delete: false, share: true },
  featureCount: 0,
  owner: "mockuser",
  attachmentFields: [] as { key: string; label: string }[],
  license: "",
  licenseUri: "",
  producer: "",
  contact: "",
  updateFrequency: "",
  lineage: "",
  language: "",
  version: "",
  temporalStart: null as string | null,
  temporalEnd: null as string | null,
};

export function mockCollection(overrides: Partial<typeof DEFAULT_COLLECTION> = {}) {
  return { ...DEFAULT_COLLECTION, ...overrides };
}
```

- [ ] **Step 5 : remplacer les 3 littéraux incomplets dans `admin-collections.spec.ts`**

```ts
// AVANT (lignes 38-54, POST 201 — arrêté à owner)
await route.fulfill({
  status: 201,
  json: {
    id: "points_interet", title: "Points d'intérêt", description: "",
    tableName: "points_interet", isPublic: false, editable: true,
    geometryType: "Point", srid: 4326, pkColumn: "id",
    permissions: { read: true, write: true, delete: false, share: true },
    featureCount: 0, owner: "mockuser",
  },
});

// APRÈS
import { mockCollection } from "./mocks";
// ...
await route.fulfill({ status: 201, json: mockCollection() });
```

Appliquer le même remplacement aux 2 autres réponses mockées (GET liste
ligne ~57-80, PATCH ligne ~83-104), en passant les `overrides` nécessaires à
chaque scénario de test (ex. `mockCollection({ title: "Renommée" })` pour le
test de renommage, s'il y en a un — lire le test existant pour préserver le
champ qu'il fait varier).

- [ ] **Step 6 : lancer la suite E2E de la page**

```bash
cd shell && npx playwright test admin-collections.spec.ts
```

- [ ] **Step 7 : suite E2E complète (VITE_AUTH_MODE=mock)**

```bash
cd shell && npm run e2e
```

- [ ] **Step 8 : commit**

```bash
git add core/tests/test_collections_json_contract.py shell/e2e/mocks.ts \
  shell/e2e/admin-collections.spec.ts
git commit -m "$(cat <<'EOF'
test(shell,core): fixture de collection E2E unique + contrat de sérialisation

mockCollection() (shell/e2e/mocks.ts) remplace 3 littéraux E2E tous
arrêtés au champ owner (12 des 23 champs réels de _collection_json()
absents) — coût déjà payé deux fois (EditCollectionPanel plantait sur
attachmentFields, SP-40 ; l'onglet Métadonnées ouvertes revalidait
l'écart, SP-41). test_collections_json_contract.py sert d'oracle des
23 clés côté cœur.
EOF
)"
```

---

## Task 5 (Étape 4) : application des `server_default=` manquants

Protégée par la Tâche 1 (le comparateur doit déjà exister et être rouge).
Risque : moyen — additif, chaque changement doit déjà correspondre à la
valeur migrée.

**Files:**
- Modify (une colonne ou plus par fichier, 12 fichiers) :
  `core/app/collections/models.py`, `core/app/items/models.py`,
  `core/app/pipelines/models.py`, `core/app/users/models.py`,
  `core/app/alerts/models.py`, `core/app/appexport/models.py`,
  `core/app/ingestion/models.py`, `core/app/export/models.py`,
  `core/app/extensions/models.py`, `core/app/harvest/models.py`,
  `core/app/notifications/models.py`, `core/app/roles/models.py`,
  `core/app/tileset3d/models.py`, `core/app/terrain3d/models.py`
- Test: `core/tests/test_model_alembic_parity.py` (Tâche 1, oracle unique de
  cette tâche)

**Interfaces:**
- Consumes: `core/tests/test_model_alembic_parity.py` (doit passer de rouge
  à vert au fil de cette tâche, colonne par colonne).
- Produces: rien de nouveau — tâche purement corrective sur les modèles.

Chaque sous-étape suit le même patron mécanique : ajouter `server_default=`
au `mapped_column(...)` existant, avec la valeur exacte déjà posée par la
migration correspondante (jamais une valeur devinée), relancer le
comparateur limité à ce module, commit. **24 colonnes réparties sur 14
fichiers** — table exhaustive ci-dessous, issue de la lecture directe des
modèles et migrations (pas du finding original, qui sous-estime la liste
car 8 colonnes citées par lui sont déjà corrigées depuis SP-41).

| # | Fichier modèle | Colonne | `default=` actuel | Migration source | `server_default=` à ajouter |
|---|---|---|---|---|---|
| 1 | `collections/models.py:26` | `description` | `""` | `0008:30` | `""` |
| 2 | `collections/models.py:33` | `is_public` | `False` | `0008:35` | `sa.false()` |
| 3 | `collections/models.py:34` | `editable` | `True` | `0008:36` | `sa.true()` |
| 4 | `collections/models.py:38` | `attachment_fields` | `list` | `0032:42` | `"[]"` |
| 5 | `items/models.py:31` | `is_published` | `False` | `0005:29` | `sa.false()` |
| 6 | `items/models.py:32` | `is_public` | `False` | `0006:19` | `sa.false()` |
| 7 | `pipelines/models.py:21` | `status` | `"queued"` | `0018:25` | `"queued"` |
| 8 | `pipelines/models.py:24` | `node_stats` | `dict` | `0018:29` | `"{}"` |
| 9 | `users/models.py:23` | `first_name` | `""` | `0003:26` | `""` |
| 10 | `users/models.py:24` | `last_name` | `""` | `0003:27` | `""` |
| 11 | `users/models.py:32` | `is_admin` | `False` | `0008:21` | `sa.false()` |
| 12 | `alerts/models.py:20` | `transitioned` | `False` | `0020:27` | `sa.false()` |
| 13 | `appexport/models.py:27` | `status` | `"pending"` | `0027:27` | `"pending"` |
| 14 | `ingestion/models.py:20` | `status` | `"pending"` | `0009:24` | `"pending"` |
| 15 | `export/models.py` | `status` | `"pending"` | `0021:27` | `"pending"` |
| 16 | `extensions/models.py` | `enabled` | `True` | `0013:32` | `sa.true()` |
| 17 | `harvest/models.py` | `mode` | `"reference"` | `0016:27` | `"reference"` |
| 18 | `harvest/models.py` | `enabled` | `True` | `0016:28` | `sa.true()` |
| 19 | `harvest/models.py` | `is_stale` | `False` | `0016:51` | `sa.false()` |
| 20 | `notifications/models.py` | `value` | `"all"` | `0031:57` | `"all"` |
| 21 | `roles/models.py` | `is_built_in` | `False` | `0030:125` | `sa.false()` |
| 22 | `tileset3d/models.py` | `status` | `"pending"` | `0025:25` | `"pending"` |
| 23 | `terrain3d/models.py` | `status` | `"uploaded"` | `0026:25` | `"uploaded"` |

(23 lignes listées — la 24e du décompte du fork de recherche correspond à
une variation de comptage entre `description` compté ou non dans le total
"~27" de la spec ; les 23 ci-dessus sont celles vérifiées directement dans
le code à la date de ce plan. Si le comparateur de la Tâche 1 révèle une
24e colonne non listée ici lors du Step 1 ci-dessous, l'ajouter à la table
avant de continuer — ne pas la découvrir en cours de route sans la
documenter.)

- [ ] **Step 1 : capturer le diff complet actuel comme point de départ**

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -v 2>&1 | tee /tmp/sp43-step4-baseline.txt
```

Comparer la liste de colonnes du diff affiché à la table ci-dessus — si une
colonne apparaît dans le diff mais pas dans la table, l'ajouter à la table
avec sa valeur exacte lue dans le modèle et la migration correspondante
avant de continuer.

- [ ] **Step 2 : corriger `collections/models.py` (4 colonnes, #1-4)**

```python
# core/app/collections/models.py
description: Mapped[str] = mapped_column(String, default="", server_default="")
is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=sa.false())
editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default=sa.true())
attachment_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False, server_default="[]")
```

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -v
```

Vérifier que les 4 colonnes de `collections` ont disparu du diff.

```bash
git add core/app/collections/models.py
git commit -m "refactor(core): ajoute server_default= manquant sur 4 colonnes collections"
```

- [ ] **Step 3 : corriger `items/models.py` (2 colonnes, #5-6)**

```python
# core/app/items/models.py
is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false())
is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false())
```

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -v
git add core/app/items/models.py
git commit -m "refactor(core): ajoute server_default= manquant sur 2 colonnes items"
```

- [ ] **Step 4 : corriger `pipelines/models.py` (2 colonnes, #7-8)**

```python
# core/app/pipelines/models.py — PipelineRun
status: Mapped[str] = mapped_column(String, default="queued", server_default="queued")
node_stats: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
```

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -v
git add core/app/pipelines/models.py
git commit -m "refactor(core): ajoute server_default= manquant sur 2 colonnes pipelines"
```

- [ ] **Step 5 : corriger `users/models.py` (3 colonnes, #9-11)**

```python
# core/app/users/models.py
first_name: Mapped[str] = mapped_column(String, default="", server_default="")
last_name: Mapped[str] = mapped_column(String, default="", server_default="")
is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=sa.false())
```

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -v
git add core/app/users/models.py
git commit -m "refactor(core): ajoute server_default= manquant sur 3 colonnes users"
```

- [ ] **Step 6 : corriger les 10 fichiers restants (une colonne chacun, #12-23)**

Appliquer le même patron mécanique à chaque fichier, un commit par fichier,
en relançant `uv run pytest tests/test_model_alembic_parity.py -v` après
chaque modification :

```python
# alerts/models.py
transitioned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false())

# appexport/models.py
status: Mapped[str] = mapped_column(String, default="pending", server_default="pending")

# ingestion/models.py
status: Mapped[str] = mapped_column(String, default="pending", server_default="pending")

# export/models.py
status: Mapped[str] = mapped_column(String, default="pending", server_default="pending")

# extensions/models.py
enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa.true())

# harvest/models.py (3 colonnes dans le même fichier)
mode: Mapped[str] = mapped_column(String, default="reference", server_default="reference")
enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa.true())
is_stale: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false())

# notifications/models.py
value: Mapped[str] = mapped_column(String, default="all", server_default="all")

# roles/models.py
is_built_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.false())

# tileset3d/models.py
status: Mapped[str] = mapped_column(String, default="pending", server_default="pending")

# terrain3d/models.py
status: Mapped[str] = mapped_column(String, default="uploaded", server_default="uploaded")
```

Un commit distinct par fichier (`refactor(core): ajoute server_default=
manquant sur <module>.<colonne>`), sauf `harvest/models.py` qui porte 3
colonnes en un seul commit (même fichier).

- [ ] **Step 7 : vérifier le comparateur entièrement vert**

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -v
```

Expected: `1 passed` (le diff réel est vide).

- [ ] **Step 8 : rejouer les migrations existantes sur base non vide, dans les deux sens (piège CLAUDE.md n°8)**

```bash
cd core && uv run pytest tests/test_attachments_migration_alembic.py \
  tests/test_metadata_migration_alembic.py -v
```

Ces deux tests exercent déjà upgrade→insert→downgrade→upgrade sur les
migrations 0032/0033 — vérifier qu'aucun des `server_default=` ajoutés
ci-dessus n'a modifié leur comportement (ils ne devraient pas, ce sont des
tables différentes, mais confirmer qu'aucune régression croisée n'existe).

- [ ] **Step 9 : ⚠️ mettre à jour le conteneur `postgis-test` s'il est utilisé par une session de dev locale**

Rappel CLAUDE.md : ce conteneur n'est pas tracké par Alembic — si la suite
complète est rejouée contre lui plutôt que contre une base jetable neuve,
un `ALTER TABLE ... SET DEFAULT ...` manuel peut être nécessaire pour
chaque colonne ci-dessus avant de voir la suite pytest repasser au vert
(sinon échecs `UndefinedColumn`/valeurs `NULL` sans rapport apparent avec
cette tâche).

- [ ] **Step 10 : suite complète**

```bash
cd core && uv run pytest
```

Expected : aucune régression — ces changements sont additifs
(`server_default=` n'affecte que les futurs `INSERT` sans valeur explicite
émis par un outil externe à l'ORM, jamais un `INSERT` émis par SQLAlchemy
lui-même qui fournit toujours la valeur Python `default=`).

- [ ] **Step 11 : régénération OpenAPI (diff vide attendu)**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
git diff core/openapi.json
```

Expected: diff vide (aucune route ni forme de réponse ne change).

---

## Task 6 (Étape 5) : module de support de job partagé

Risque : moyen — 5 (potentiellement 6) fichiers touchés simultanément,
chacun garde son test dédié comme oracle. **Correction de nommage de la
spec** : les fichiers de test réels sont au **singulier**
(`test_report_jobs.py`, pas `test_reports_jobs.py`), vérifié par recherche
préalable — ne pas supposer les noms de la spec.

**Files:**
- Create: `core/app/jobs/common.py`, `core/app/jobs/__init__.py`
- Modify: `core/app/reports/jobs.py`, `core/app/alerts/jobs.py`,
  `core/app/pipelines/jobs.py`, `core/app/ingestion/tasks.py`,
  `core/app/appexport/jobs.py`
- Test: `core/tests/test_report_jobs.py`, `test_alert_jobs.py`,
  `test_pipeline_jobs.py`, `test_ingestion_tasks.py`,
  `test_appexport_jobs.py` (existants, vérifiés), + nouveau
  `core/tests/test_jobs_common.py`

**Interfaces:**
- Consumes: signatures actuelles de `_session_factory()`,
  `_owner_user()`/`_acting_user()`, `_notify()` dans les 5 fichiers (toutes
  divergentes — cf. Step 1).
- Produces: `core/app/jobs/common.py::session_factory() -> SessionFactory`,
  `resolve_owner_user(session, *, tenant_id: str, item_id: str) -> User`,
  `notify_best_effort(session_factory, *, tenant_id: str, recipient_user_id:
  str, kind: str, status: str, error: str | None = None) -> None`.

**⚠️ Note de conception, à trancher explicitement avant le Step 3** (ne pas
supposer) : la recherche préalable a trouvé **4 formes de résolution du
destinataire** de la notification selon le fichier (owner résolu par
tenant_id+item_id / owner explicite avec nom de fonction différent /
created_by explicite / user_id déjà résolu par l'appelant), et **une 5e
fonction `_notify` de forme totalement différente** dans `alerts/jobs.py`
(prend `session` et non `session_factory`, n'écrit **aucune** notification
in-app — seulement webhook/email par canal — et n'est donc **pas** un
candidat à l'extraction dans `notify_best_effort`). Un **6e fichier frère**,
`core/app/export/jobs.py`, porte aussi `_notify`/`_session_factory` et n'est
pas dans l'énumération de la spec — décision à prendre au Step 1.

- [ ] **Step 1 : lire les 5 (potentiellement 6) fichiers, confirmer le périmètre exact avant de coder**

```bash
sed -n '1,130p' core/app/reports/jobs.py
sed -n '1,260p' core/app/alerts/jobs.py
sed -n '1,110p' core/app/pipelines/jobs.py
sed -n '1,90p' core/app/ingestion/tasks.py
sed -n '1,70p' core/app/appexport/jobs.py
sed -n '1,70p' core/app/export/jobs.py
```

Confirmer : (a) `core/app/export/jobs.py` porte bien le même patron
`_session_factory`/`_notify` — si oui, l'inclure dans cette tâche comme 6e
fichier migré (ce plan suppose que oui, à vérifier avant de continuer) ; (b)
`alerts/jobs.py::_notify` garde sa forme propre (webhook/email par canal,
**hors périmètre de `notify_best_effort`**) — seuls `_session_factory()` et
`_owner_user()` d'`alerts/jobs.py` migrent vers le module commun, pas son
`_notify`.

- [ ] **Step 2 : écrire le test du module commun (avant de le créer)**

```python
# core/tests/test_jobs_common.py
"""Module de support de job partagé — SP-43 Étape 5. Remplace
_session_factory()/_owner_user()/_notify() dupliqués sur 5-6 fichiers de
job procrastinate. notify_best_effort() préserve l'invariant déjà correct
sur les 5 sites actuels (le try/except de notification est strictement
séparé du commit de statut du job, cf. sp39 UnboundLocalError x2) : un
échec dans notify_best_effort ne doit JAMAIS remonter à l'appelant."""

from unittest.mock import patch

import pytest

from app.jobs.common import notify_best_effort, resolve_owner_user, session_factory


def test_session_factory_returns_a_callable_session_factory() -> None:
    factory = session_factory()
    session = factory()
    try:
        assert session is not None
    finally:
        session.close()


def test_resolve_owner_user_raises_when_item_not_found(db_session, tenant) -> None:
    with pytest.raises(LookupError):
        resolve_owner_user(db_session, tenant_id=tenant.id, item_id="does-not-exist")


def test_notify_best_effort_failure_never_raises(db_session, tenant, user) -> None:
    """Falsification de l'isolation try/except — reproduit le mécanisme exact
    des 2 UnboundLocalError trouvés par SP-39 (ingestion/tasks.py,
    pipelines/jobs.py) : une exception dans le chemin de notification ne
    doit jamais empêcher l'appelant de continuer."""
    with patch(
        "app.notifications.repo.create_notification",
        side_effect=RuntimeError("simulated notification backend failure"),
    ):
        # ne doit lever aucune exception
        notify_best_effort(
            lambda: db_session,
            tenant_id=tenant.id,
            recipient_user_id=user.id,
            kind="report",
            status="done",
        )
```

- [ ] **Step 3 : lancer le test, vérifier qu'il échoue (module inexistant)**

```bash
cd core && uv run pytest tests/test_jobs_common.py -v
```

- [ ] **Step 4 : créer `core/app/jobs/common.py`**

En s'appuyant sur la forme la plus répandue (`reports/jobs.py` et
`pipelines/jobs.py`, identiques) :

```python
# core/app/jobs/common.py
"""Support de job partagé — session, résolution du propriétaire, notification
best-effort. Remplace 5 copies quasi identiques (reports/alerts/pipelines/
ingestion/appexport/export jobs.py) qui ont produit 2 UnboundLocalError réels
(SP-39) : une variable référencée par l'appel de notification de la branche
d'échec n'était pas garantie liée si l'échec survenait avant son affectation
normale. L'isolation try/except (notification best-effort strictement
séparée du commit du statut du job) est un invariant à préserver dans tout
appelant — ne jamais fusionner les deux blocs."""

import os
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.db import make_engine, make_session_factory
from app.items.models import Item
from app.notifications import repo as notifications_repo
from app.users.models import User

SessionFactory = Callable[[], Session]


def session_factory() -> SessionFactory:
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def resolve_owner_user(session: Session, *, tenant_id: str, item_id: str) -> User:
    from sqlalchemy import select

    owner_id = session.execute(
        select(Item.owner_id).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if owner_id is None:
        raise LookupError(f"item '{item_id}' not found")
    user = session.get(User, owner_id)
    assert user is not None
    return user


def notify_best_effort(
    session_factory_fn: SessionFactory,
    *,
    tenant_id: str,
    recipient_user_id: str,
    kind: str,
    status: str,
    error: str | None = None,
) -> None:
    """Best-effort : toute exception ici est avalée, jamais propagée. Le
    destinataire doit déjà être résolu par l'appelant (owner / created_by /
    user_id explicite selon le domaine) — cette fonction ne fait aucune
    résolution elle-même, cf. note de conception de la Tâche 6."""
    try:
        session = session_factory_fn()
        try:
            notifications_repo.create_notification(
                session,
                tenant_id=tenant_id,
                user_id=recipient_user_id,
                kind=kind,
                status=status,
                error=error,
            )
            session.commit()
        finally:
            session.close()
    except Exception:  # noqa: BLE001 — best-effort explicite, jamais remonté
        pass
```

- [ ] **Step 5 : lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_jobs_common.py -v
```

Ajuster les fixtures `db_session`/`tenant`/`user` selon les fixtures
réellement disponibles dans `core/tests/conftest.py` (vérifier leur nom
exact avant d'exécuter).

- [ ] **Step 6 : migrer `reports/jobs.py` (la forme la plus proche du module commun)**

```python
# AVANT (lignes 45-58, 74-124)
def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)

def _owner_user(session, *, tenant_id, item_id):
    ...

def _notify(session_factory, *, tenant_id, item_id, status, error=None):
    ...  # ~50 lignes dupliquées
```

```python
# APRÈS
from app.jobs.common import notify_best_effort, resolve_owner_user, session_factory

# à l'intérieur de la fonction de job, au point d'appel existant :
owner = resolve_owner_user(session, tenant_id=tenant_id, item_id=item_id)
...
notify_best_effort(
    session_factory,
    tenant_id=tenant_id,
    recipient_user_id=owner.id,
    kind="report",
    status=status,
    error=error,
)
```

Conserver exactement la même structure try/except autour de l'appel côté
appelant (le bloc protégé qui entoure `_notify(...)` aujourd'hui doit
entourer `notify_best_effort(...)` demain, sans fusion avec le commit du
statut du job).

- [ ] **Step 7 : lancer `test_report_jobs.py` (18 tests), vérifier zéro régression**

```bash
cd core && uv run pytest tests/test_report_jobs.py -v
```

```bash
git add core/app/jobs/common.py core/app/jobs/__init__.py core/app/reports/jobs.py \
  core/tests/test_jobs_common.py
git commit -m "refactor(core): extrait le support de job partagé, migre reports/jobs.py"
```

- [ ] **Step 8 : migrer `pipelines/jobs.py` (même forme que reports, fonction nommée `_acting_user`)**

Même patron qu'au Step 6 — noter que `pipelines/jobs.py` nomme sa fonction
`_acting_user` (pas `_owner_user`) mais son corps est identique : elle migre
vers `resolve_owner_user` sans changement de comportement, seul son nom
d'appel change côté `pipelines/jobs.py`.

```bash
cd core && uv run pytest tests/test_pipeline_jobs.py -v
```

Vérifier en particulier `test_notification_write_failure_does_not_affect_run_status`
(ligne 252, test de falsification déjà écrit par SP-39 pour ce fichier) —
doit rester vert à l'identique après migration.

```bash
git add core/app/pipelines/jobs.py
git commit -m "refactor(core): migre pipelines/jobs.py vers le support de job partagé"
```

- [ ] **Step 9 : migrer `ingestion/tasks.py` (signature différente : `created_by` explicite, pas de `_session_factory` séparée)**

`ingestion/tasks.py` ne porte pas de `_session_factory()` distincte
(construite inline dans `run_ingestion_task`) et sa fonction `_notify` prend
`created_by` au lieu de résoudre un owner — utiliser `notify_best_effort`
directement avec `recipient_user_id=created_by`, sans appeler
`resolve_owner_user` (pas d'owner à résoudre ici, le créateur est déjà
connu de l'appelant).

```bash
cd core && uv run pytest tests/test_ingestion_tasks.py -v
```

Vérifier en particulier `test_notification_write_failure_does_not_affect_job_status`
(ligne 201, 2e test de falsification SP-39) reste vert.

```bash
git add core/app/ingestion/tasks.py
git commit -m "refactor(core): migre ingestion/tasks.py vers le support de job partagé"
```

- [ ] **Step 10 : migrer `appexport/jobs.py` (signature différente : `user_id` explicite, résolu par le caller depuis `job.user_id`)**

Même remarque qu'au Step 9 : pas de résolution owner interne, utiliser
`notify_best_effort(..., recipient_user_id=job.user_id, ...)` directement.

```bash
cd core && uv run pytest tests/test_appexport_jobs.py -v
git add core/app/appexport/jobs.py
git commit -m "refactor(core): migre appexport/jobs.py vers le support de job partagé"
```

- [ ] **Step 11 : migrer `export/jobs.py` (6e fichier confirmé au Step 1, si applicable)**

Appliquer le patron le plus proche identifié au Step 1 (probablement
identique à `appexport/jobs.py` — vérifier sa signature `_notify` exacte
avant de choisir entre le patron `owner résolu`/`created_by`/`user_id`).

```bash
cd core && uv run pytest tests/test_export_jobs.py -v  # nom exact à vérifier au Step 1
git add core/app/export/jobs.py
git commit -m "refactor(core): migre export/jobs.py vers le support de job partagé"
```

- [ ] **Step 12 : `alerts/jobs.py` — migrer uniquement `_session_factory`/`_owner_user`, PAS `_notify`**

Rappel de la note de conception : `alerts/jobs.py::_notify` (lignes
197-248) a une forme et un rôle différents (webhook/email par canal, aucune
notification in-app) — ne pas la faire entrer dans `notify_best_effort`.
Migrer seulement :

```python
# AVANT
def _session_factory(): ...
def _owner_user(session, *, tenant_id, item_id): ...  # lève AlertEvaluationError

# APRÈS
from app.jobs.common import resolve_owner_user, session_factory
# _owner_user local devient un thin wrapper si le type d'exception métier
# (AlertEvaluationError) doit être préservé pour les appelants existants :
def _owner_user(session, *, tenant_id, item_id):
    try:
        return resolve_owner_user(session, tenant_id=tenant_id, item_id=item_id)
    except LookupError as exc:
        raise AlertEvaluationError(str(exc)) from exc
```

```bash
cd core && uv run pytest tests/test_alert_jobs.py -v
git add core/app/alerts/jobs.py
git commit -m "refactor(core): migre alerts/jobs.py (session/owner uniquement, _notify propre conservée)"
```

- [ ] **Step 13 : falsifier l'isolation try/except sur les 5-6 call sites après migration**

Pour chacun des fichiers migrés, forcer une exception dans le chemin de
`notify_best_effort` (monkeypatch `app.notifications.repo.create_notification`
pour lever), relancer le test dédié du fichier, confirmer que le statut du
job est bien committé malgré l'échec de notification (déjà couvert
explicitement par les 2 tests de falsification SP-39 cités aux Steps 8-9 ;
ajouter le même test pour `reports`/`appexport`/`export`/`alerts` s'il
n'existe pas encore).

- [ ] **Step 14 : suite complète**

```bash
cd core && uv run pytest
```

---

## Task 7 (Étape 6) : primitive `aria-expanded`/`aria-controls`

Risque : moyen — 7-9 sites, changement additif (attributs ARIA) sans
changement de comportement fonctionnel testable par ailleurs.

**Files:**
- Create: `shell/src/ui/kit/usePanelTrigger.ts` (premier hook du dossier
  `ui/kit/` — décision explicite : hook plutôt que composant wrapper, cf.
  Step 1)
- Modify: `shell/src/pages/CollectionsAdminPage.tsx` (2 sites),
  `shell/src/pages/HarvestSourcesAdminPage.tsx` (2 sites),
  `shell/src/pages/RolesAdminPage.tsx` (1 site),
  `shell/src/builder/print/ExportPanel.tsx` (1 site),
  `shell/src/builder/pipeline/PipelineCanvas.tsx` (1 site),
  `shell/src/shell/NewItemButton.tsx` (1 site, patron Drawer),
  `shell/src/shell/ImportFileButton.tsx` (1 site, patron Drawer)
- Test: `shell/src/ui/kit/usePanelTrigger.test.ts` (nouveau),
  `CollectionsAdminPage.test.tsx`, `HarvestSourcesAdminPage.test.tsx`,
  `RolesAdminPage.test.tsx` (existants, augmentés)

**Interfaces:**
- Consumes: patron Radix de référence
  `shell/src/ui/kit/Combobox.tsx:24,56-59` (`useId()` +
  `aria-expanded`/`aria-controls` sur le déclencheur, `id` sur la cible).
- Produces: `usePanelTrigger(open: boolean) -> { panelId: string,
  triggerProps: { "aria-expanded": boolean, "aria-controls": string },
  panelProps: { id: string, role: "region" } }` — premier hook de
  `ui/kit/`, et `expectAriaWired(trigger: HTMLElement, panelId: string)`
  (helper de test réutilisable).

- [ ] **Step 1 : écrire le test du hook (avant de le créer)**

```ts
// shell/src/ui/kit/usePanelTrigger.test.ts
import { renderHook } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { usePanelTrigger } from "./usePanelTrigger";

describe("usePanelTrigger", () => {
  test("wires aria-expanded=false and a shared id when closed", () => {
    const { result } = renderHook(() => usePanelTrigger(false));
    expect(result.current.triggerProps["aria-expanded"]).toBe(false);
    expect(result.current.triggerProps["aria-controls"]).toBe(result.current.panelId);
    expect(result.current.panelProps.id).toBe(result.current.panelId);
    expect(result.current.panelProps.role).toBe("region");
  });

  test("wires aria-expanded=true when open", () => {
    const { result } = renderHook(() => usePanelTrigger(true));
    expect(result.current.triggerProps["aria-expanded"]).toBe(true);
  });

  test("panelId is stable across re-renders", () => {
    const { result, rerender } = renderHook(({ open }) => usePanelTrigger(open), {
      initialProps: { open: false },
    });
    const firstId = result.current.panelId;
    rerender({ open: true });
    expect(result.current.panelId).toBe(firstId);
  });
});
```

- [ ] **Step 2 : lancer le test, vérifier qu'il échoue (module inexistant)**

```bash
cd shell && npx vitest run src/ui/kit/usePanelTrigger.test.ts
```

- [ ] **Step 3 : écrire le hook**

```ts
// shell/src/ui/kit/usePanelTrigger.ts
import { useId } from "react";

/**
 * Câble aria-expanded/aria-controls sur un déclencheur et id/role="region"
 * sur le panneau qu'il bascule — fait de la convention CLAUDE.md du
 * 2026-09-01 une propriété du composant plutôt qu'une prose à respecter de
 * mémoire (SP-43 §3.6). Patron de référence : ui/kit/Combobox.tsx, seul
 * site du dépôt à câbler ces attributs aujourd'hui, via Radix.
 */
export function usePanelTrigger(open: boolean) {
  const panelId = useId();
  return {
    panelId,
    triggerProps: {
      "aria-expanded": open,
      "aria-controls": panelId,
    } as const,
    panelProps: {
      id: panelId,
      role: "region" as const,
    },
  };
}
```

- [ ] **Step 4 : lancer le test, vérifier qu'il passe**

```bash
cd shell && npx vitest run src/ui/kit/usePanelTrigger.test.ts
```

- [ ] **Step 5 : exporter le hook depuis l'index du kit**

```ts
// shell/src/ui/kit/index.ts — ajouter
export { usePanelTrigger } from "./usePanelTrigger";
```

- [ ] **Step 6 : écrire le helper de test générique**

```ts
// shell/src/test/expectAriaWired.ts (nouveau fichier partagé)
import { expect } from "vitest";

export function expectAriaWired(trigger: HTMLElement, panelId: string) {
  expect(trigger).toHaveAttribute("aria-controls", panelId);
  const panel = document.getElementById(panelId);
  expect(panel).not.toBeNull();
  expect(trigger.getAttribute("aria-expanded")).toBe(
    trigger.getAttribute("aria-expanded"), // valeur observée, comparée explicitement par l'appelant
  );
}
```

Note : la forme exacte de `expectAriaWired` doit permettre à l'appelant de
vérifier la valeur `true`/`false` attendue explicitement — préférer cette
forme plus stricte :

```ts
export function expectAriaWired(
  trigger: HTMLElement,
  panelId: string,
  expectedExpanded: boolean,
) {
  expect(trigger).toHaveAttribute("aria-controls", panelId);
  expect(trigger).toHaveAttribute("aria-expanded", String(expectedExpanded));
  if (expectedExpanded) {
    expect(document.getElementById(panelId)).not.toBeNull();
  }
}
```

- [ ] **Step 7 : appliquer le hook à `CollectionsAdminPage.tsx` (2 sites) — premier site, avec test**

```tsx
// AVANT (lignes 107-118, bouton Éditer)
<Button onClick={() => { setRegistering(false); setSharing(null); setEditing(col); }}>
  Éditer
</Button>
{editing && <EditCollectionPanel collection={editing} ... />}
```

```tsx
// APRÈS
const editPanel = usePanelTrigger(editing !== null);
// ...
<Button
  {...editPanel.triggerProps}
  onClick={() => { setRegistering(false); setSharing(null); setEditing(col); }}
>
  Éditer
</Button>
{editing && <div {...editPanel.panelProps}><EditCollectionPanel collection={editing} ... /></div>}
```

Répéter pour le 2e site (bouton Partager, lignes 119-130) avec un
`usePanelTrigger` distinct (`sharingPanel`).

Ajouter dans `CollectionsAdminPage.test.tsx` :

```tsx
import { expectAriaWired } from "../test/expectAriaWired";
// ... dans un test existant qui clique sur "Éditer" :
const trigger = screen.getByRole("button", { name: "Éditer" });
expectAriaWired(trigger, trigger.getAttribute("aria-controls")!, false);
fireEvent.click(trigger);
expectAriaWired(trigger, trigger.getAttribute("aria-controls")!, true);
```

```bash
cd shell && npx vitest run src/pages/CollectionsAdminPage.test.tsx
```

```bash
git add shell/src/ui/kit/usePanelTrigger.ts shell/src/ui/kit/usePanelTrigger.test.ts \
  shell/src/ui/kit/index.ts shell/src/test/expectAriaWired.ts \
  shell/src/pages/CollectionsAdminPage.tsx shell/src/pages/CollectionsAdminPage.test.tsx
git commit -m "refactor(shell): câble aria-expanded/aria-controls sur CollectionsAdminPage"
```

- [ ] **Step 8 : appliquer le même patron à `HarvestSourcesAdminPage.tsx` (2 sites)**

Même transformation qu'au Step 7 sur les boutons « Ajouter une source »
(lignes 65-75) et « Éditer » (lignes 120-129), en réutilisant
`expectAriaWired` dans `HarvestSourcesAdminPage.test.tsx`.

```bash
cd shell && npx vitest run src/pages/HarvestSourcesAdminPage.test.tsx
git add shell/src/pages/HarvestSourcesAdminPage.tsx shell/src/pages/HarvestSourcesAdminPage.test.tsx
git commit -m "refactor(shell): câble aria-expanded/aria-controls sur HarvestSourcesAdminPage"
```

- [ ] **Step 9 : appliquer le même patron à `RolesAdminPage.tsx` (1 site)**

Bouton « Éditer » (lignes 98-108).

```bash
cd shell && npx vitest run src/pages/RolesAdminPage.test.tsx
git add shell/src/pages/RolesAdminPage.tsx shell/src/pages/RolesAdminPage.test.tsx
git commit -m "refactor(shell): câble aria-expanded/aria-controls sur RolesAdminPage"
```

- [ ] **Step 10 : appliquer à `ExportPanel.tsx` (bouton « Exporter », lignes 83-88)**

```tsx
// AVANT
<Button onClick={() => setPickerOpen((open) => !open)}>Exporter</Button>
{pickerOpen && <Panel>...</Panel>}

// APRÈS
const exportPanel = usePanelTrigger(pickerOpen);
<Button {...exportPanel.triggerProps} onClick={() => setPickerOpen((o) => !o)}>Exporter</Button>
{pickerOpen && <Panel {...exportPanel.panelProps}>...</Panel>}
```

```bash
cd shell && npx vitest run src/builder/print/ExportPanel.test.tsx
git add shell/src/builder/print/ExportPanel.tsx
git commit -m "refactor(shell): câble aria-expanded/aria-controls sur ExportPanel"
```

- [ ] **Step 11 : appliquer à `PipelineCanvas.tsx` (bouton natif `<button>`, lignes 129-136)**

```tsx
// AVANT
<button aria-label="Insérer une étape sur cette arête" onClick={() => setOpen((o) => !o)}>+</button>
{open && <div role="menu">...</div>}

// APRÈS — conserver aria-label existant, ajouter aria-expanded/aria-controls
const insertMenu = usePanelTrigger(open);
<button
  aria-label="Insérer une étape sur cette arête"
  aria-expanded={insertMenu.triggerProps["aria-expanded"]}
  aria-controls={insertMenu.triggerProps["aria-controls"]}
  onClick={() => setOpen((o) => !o)}
>
  +
</button>
{open && <div role="menu" id={insertMenu.panelId}>...</div>}
```

Note : ce site garde `role="menu"` (pas `role="region"` du hook) sur la
cible — ne pas écraser un rôle ARIA déjà correct et plus spécifique, câbler
uniquement l'`id` et les attributs du déclencheur.

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx
git add shell/src/builder/pipeline/PipelineCanvas.tsx
git commit -m "refactor(shell): câble aria-expanded/aria-controls sur PipelineCanvas"
```

- [ ] **Step 12 : `NewItemButton.tsx`/`ImportFileButton.tsx` — cause mécanique différente (Drawer sans Trigger Radix)**

Ces deux sites ouvrent un `Drawer` (`shell/src/ui/kit/Drawer.tsx`, qui
n'utilise pas `DialogPrimitive.Trigger` — le bouton externe n'a aucun lien
mécanique avec le composant). Appliquer le même hook :

```tsx
// AVANT (NewItemButton.tsx:162-165)
<Button size="sm" onClick={() => setOpen(true)}>...</Button>
<Drawer open={open} onOpenChange={...} title="Nouvel élément">

// APRÈS
const drawerPanel = usePanelTrigger(open);
<Button size="sm" {...drawerPanel.triggerProps} onClick={() => setOpen(true)}>...</Button>
<Drawer open={open} onOpenChange={...} title="Nouvel élément" id={drawerPanel.panelId}>
```

Vérifier que `Drawer` accepte déjà une prop `id` transmise à
`DialogPrimitive.Content` — sinon l'ajouter à `Drawer.tsx` (changement
minimal, un seul prop transmis).

```bash
cd shell && npx vitest run src/shell/NewItemButton.test.tsx src/shell/ImportFileButton.test.tsx
git add shell/src/shell/NewItemButton.tsx shell/src/shell/ImportFileButton.tsx shell/src/ui/kit/Drawer.tsx
git commit -m "refactor(shell): câble aria-expanded/aria-controls sur NewItemButton/ImportFileButton"
```

- [ ] **Step 13 : suite complète shell + E2E**

```bash
cd shell && npm run test && npm run e2e
```

---

## Task 8 (Étape 7) : découpage d'`itemClient.ts`/`hooks.ts` par domaine

Risque élevé — fichier central de l'architecture (règle n°1 CLAUDE.md,
« `ItemClient` est le sas »). **La même interface `ItemClient` exportée et
la même fonction-usine `createItemClient()` sont préservées** — seule
l'implémentation interne est répartie en modules par domaine. Un commit par
domaine, suite complète (**173** tests — 169 existants + 4 de la Tâche 3)
rejouée après chacun.

**Files:**
- Create: `shell/src/api/base.ts` (dépendances transverses),
  `shell/src/api/domains/identity.ts`, `domains/notifications.ts`,
  `domains/items.ts`, `domains/collectionsAdmin.ts`,
  `domains/extensionsAdminTools.ts`, `domains/layers.ts`,
  `domains/datasets.ts`, `domains/pipelines.ts`, `domains/alerts.ts`,
  `domains/reports.ts`, `domains/apps.ts`, `domains/attachments.ts`,
  `domains/features.ts`, `domains/exportsIngestion.ts`, `domains/tiles3d.ts`
- Modify: `shell/src/api/itemClient.ts` (devient une simple composition des
  15 domaines + du module de base), `shell/src/api/hooks.ts` (regroupé dans
  les mêmes 15 domaines, en fichiers `domains/<domaine>.hooks.ts`)
- Test: `shell/src/api/itemClient.test.ts` (inchangé dans sa forme, doit
  rester vert à l'identique après chaque domaine extrait)

**Interfaces:**
- Consumes: `ItemClient` (interface complète, `shell/src/api/types.ts:331-558`,
  ~111 méthodes), `toFrontLayer`/`RawMapLayer` (Tâche 3, déjà exportées).
- Produces: chaque `domains/<domaine>.ts` exporte une fonction
  `create<Domaine>Methods(base: ItemClientBase) -> Pick<ItemClient, ...>` ;
  `itemClient.ts::createItemClient()` les compose par spread. Consommé par
  la Tâche 3 (répliquer le test caractéristique si un nouveau point de
  conversion raw↔front apparaît pendant ce découpage — cf. spec §6 risque
  Étape 7).

**⚠️ Risque d'import circulaire (spec §6)** : extraire d'abord les
dépendances transverses (`request()`, `datasetCache`/`resolveDataset()`,
`_fetchGeoJsonFeatures()`, les 4 `fetch*Sources()`) dans `base.ts`, **avant**
tout découpage par domaine — ne jamais les laisser dans un module de
domaine dont un autre domaine dépendrait.

- [ ] **Step 1 : baseline — confirmer 173 tests passent avant tout changement**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts
```

Expected: `173 passed` (169 + les 4 de la Tâche 3).

- [ ] **Step 2 : extraire le module de base (`base.ts`) — dépendances transverses**

```ts
// shell/src/api/base.ts
import type { CrossFilterLink, DataRecord, DatasetColumnMeta, LayerSource } from "./types";

export type ItemClientBase = {
  request<T>(method: string, path: string, body?: unknown): Promise<T>;
  resolveDataset(pk: string): Promise<ResolvedDataset>;
  fetchGeoJsonFeatures(url: string): Promise<DataRecord[]>;
  fetchCoreCollections(q?: string): Promise<LayerSource[]>;
  fetchExternalRasterSources(q?: string): Promise<LayerSource[]>;
  fetchHostedTileset3dSources(q?: string): Promise<LayerSource[]>;
  fetchHostedTerrain3dSources(q?: string): Promise<{ id: string; title: string }[]>;
};

export type ResolvedDataset = {
  source: "collection" | "arcgis";
  collectionId: string | null;
  arcgisItemId: string | null;
  columns: Record<string, DatasetColumnMeta>;
  timeField: string | null;
  reactsToExtent: boolean;
  crossFilterLinks: CrossFilterLink[];
  sourcePipelineId: string | null;
};

export const GEOMETRY_KINDS: Record<string, "point" | "line" | "polygon"> = {
  Point: "point", MultiPoint: "point", LineString: "line",
  MultiLineString: "line", Polygon: "polygon", MultiPolygon: "polygon",
};

export function createBase(opts: { coreUrl: string; getToken: () => string | undefined }): ItemClientBase {
  const { coreUrl, getToken } = opts;

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(`${coreUrl}${path}`, {
      method, headers, body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} ${method} ${path}`);
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  const datasetCache = new Map<string, ResolvedDataset>();

  async function resolveDataset(pk: string): Promise<ResolvedDataset> {
    const cached = datasetCache.get(pk);
    if (cached) return cached;
    const data = await request<{ config?: { dataset?: Record<string, unknown> | null } }>(
      "GET", `/configs/by-item/${pk}`,
    );
    const dataset = data.config?.dataset as Record<string, unknown> | undefined;
    if (!dataset) throw new Error("resolveDataset: config has no dataset payload");
    const resolved: ResolvedDataset = {
      source: dataset.source as "collection" | "arcgis",
      collectionId: (dataset.collectionId as string) ?? null,
      arcgisItemId: (dataset.arcgisItemId as string) ?? null,
      columns: (dataset.columns as Record<string, DatasetColumnMeta>) ?? {},
      timeField: (dataset.timeField as string) ?? null,
      reactsToExtent: (dataset.reactsToExtent as boolean) ?? false,
      crossFilterLinks: (dataset.crossFilterLinks as CrossFilterLink[]) ?? [],
      sourcePipelineId: (dataset.sourcePipelineId as string) ?? null,
    };
    datasetCache.set(pk, resolved);
    return resolved;
  }

  async function fetchGeoJsonFeatures(url: string): Promise<DataRecord[]> {
    const token = getToken();
    const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) throw new Error(`Request failed: ${res.status} features`);
    const data = (await res.json()) as {
      features?: { id?: string | number; properties?: Record<string, unknown>; geometry?: unknown }[];
    };
    return (data.features ?? []).map((f, i) => ({
      id: f.id ?? i, properties: f.properties ?? {}, geometry: f.geometry,
    }));
  }

  // fetchCoreCollections / fetchExternalRasterSources / fetchHostedTileset3dSources /
  // fetchHostedTerrain3dSources : déplacer le corps existant tel quel depuis
  // itemClient.ts, en remplaçant les appels internes à request() par le
  // request() de cette closure (identique).

  return {
    request, resolveDataset, fetchGeoJsonFeatures,
    fetchCoreCollections, fetchExternalRasterSources,
    fetchHostedTileset3dSources, fetchHostedTerrain3dSources,
  };
}
```

Ne pas encore modifier `itemClient.ts` à ce stade — `base.ts` existe mais
n'est pas encore consommé. Lancer `npx tsc --noEmit` pour confirmer que le
nouveau fichier compile isolément.

```bash
git add shell/src/api/base.ts
git commit -m "refactor(shell): extrait les dépendances transverses d'itemClient dans base.ts"
```

- [ ] **Step 3 : extraire le domaine le plus petit en premier — `notifications.ts` (6 méthodes), pour valider le patron**

```ts
// shell/src/api/domains/notifications.ts
import type { ItemClient } from "../types";
import type { ItemClientBase } from "../base";

type NotificationsMethods = Pick<
  ItemClient,
  | "listNotifications" | "getUnreadNotificationCount" | "markNotificationRead"
  | "markAllNotificationsRead" | "getNotificationPreference" | "updateNotificationPreference"
>;

export function createNotificationsMethods(base: ItemClientBase): NotificationsMethods {
  const { request } = base;
  return {
    async listNotifications(params) {
      return request("GET", `/notifications?page=${params.page}&pageSize=${params.pageSize}`);
    },
    async getUnreadNotificationCount() {
      return request("GET", "/notifications/unread-count");
    },
    async markNotificationRead(id) {
      return request("POST", `/notifications/${id}/read`);
    },
    async markAllNotificationsRead() {
      return request("POST", "/notifications/read-all");
    },
    async getNotificationPreference() {
      return request("GET", "/notifications/preference");
    },
    async updateNotificationPreference(value) {
      return request("PUT", "/notifications/preference", { value });
    },
  };
}
```

Reprendre le corps exact de chaque méthode depuis `itemClient.ts` (lignes
619-656 selon la recherche préalable) — ne pas réinventer les chemins/verbes
HTTP, les copier tels quels.

- [ ] **Step 4 : brancher le domaine dans `createItemClient()`**

```ts
// itemClient.ts — AVANT : les 6 méthodes notifications inline dans le
// littéral retourné par createItemClient()

// APRÈS
import { createBase } from "./base";
import { createNotificationsMethods } from "./domains/notifications";

export function createItemClient(opts: { coreUrl: string; getToken: () => string | undefined }): ItemClient {
  const base = createBase(opts);
  return {
    ...createNotificationsMethods(base),
    // ... reste des méthodes encore inline, migrées domaine par domaine
    // dans les steps suivants
  };
}
```

- [ ] **Step 5 : suite complète, confirmer 173 passed**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts
```

```bash
git add shell/src/api/domains/notifications.ts shell/src/api/itemClient.ts
git commit -m "refactor(shell): extrait le domaine notifications d'itemClient.ts"
```

- [ ] **Step 6 : répéter le patron du Step 3-5 pour les 14 domaines restants, un commit par domaine**

Appliquer exactement le même patron (créer `domains/<domaine>.ts`, copier
le corps exact des méthodes depuis `itemClient.ts` aux lignes indiquées,
brancher dans `createItemClient()`, lancer la suite, commit) pour chacun
des domaines suivants, dans cet ordre (du plus petit au plus gros, pour
détecter tôt un problème de composition) :

| Domaine | Fichier | Méthodes (nom, ligne actuelle dans itemClient.ts) |
|---|---|---|
| identity | `domains/identity.ts` | getMe(528), getPrivilegeCatalog(582), listRoles(586), createRole(590), updateRole(594), deleteRole(598), listUsers(602), updateUserRole(615) |
| attachments | `domains/attachments.ts` | presignAttachmentUpload(1553), confirmAttachmentUpload(1565), listAttachments(1577), deleteAttachment(1590), attachmentFileUrl(1597), downloadAttachment(1601) |
| alerts | `domains/alerts.ts` | createAlertRuleItem(1166), getAlertRuleConfig(1195), saveAlertRuleConfig(1204), listAlertRulesForDataset(1212), getAlertEvaluations(1216) |
| reports | `domains/reports.ts` | createReportScheduleItem(1220), getReportScheduleConfig(1249), saveReportScheduleConfig(1259), getReportRuns(1267) |
| tiles3d | `domains/tiles3d.ts` | createTileset3DUpload(1694), presignTileset3DUploadPart(1698), completeTileset3DUpload(1705), getTileset3DUploadJob(1709), listHostedTerrain3DSources(1717), presignTerrain3DUpload(1720), createTerrain3DUpload(1727), getTerrain3DUploadJob(1731) |
| extensionsAdminTools | `domains/extensionsAdminTools.ts` | listActiveExtensions(781), listAllExtensions(813), setExtensionEnabled(847), launchAdminTool(851), listHarvestSources(890), createHarvestSource(895), updateHarvestSource(899), deleteHarvestSource(903), runHarvestSource(907) |
| collectionsAdmin | `domains/collectionsAdmin.ts` | listCollections(855), listCandidateTables(860), createCollection(868), createEmptyCollection(872), updateCollection(882), deleteCollection(886), getCollectionSharing(911), setCollectionSharing(915) |
| exportsIngestion | `domains/exportsIngestion.ts` | createExport(1390), getExportJob(1394), createAppExport(1398), getAppExportJob(1403), presignUpload(1659), uploadToPresignedUrl(1666), inspectUpload(1671), createIngestionJob(1677), getIngestionJob(1681), runAnalyticsSql(1690) |
| pipelines | `domains/pipelines.ts` | createPipelineItem(1100), getPipelineConfig(1129), savePipelineConfig(1139), getPipelineOps(1147), runPipeline(1151), getPipelineRuns(1155), previewPipeline(1159) |
| apps | `domains/apps.ts` | getAppConfig(1313), getPublicAppConfig(1345), saveAppConfig(1374), copilotTurn(1407) |
| features | `domains/features.ts` | getCollection(1614), getCollectionPermission(1618), createFeature(1626), updateFeature(1638), deleteFeature(1651) |
| datasets | `domains/datasets.ts` | createDatasetItem(1019), getDatasetConfig(1271), saveDatasetConfig(1295), queryDataSource(1425, **consomme `base.resolveDataset`**), featuresUrl(1411), exportDataSource(1525), getCollectionSchema(1549) |
| layers | `domains/layers.ts` | createMapItem(919), getMapConfig(949, **consomme `toFrontLayer` de la Tâche 3**), saveMapConfig(996), listLayerSources(755, **consomme `base.fetchCoreCollections`/`fetchExternalRasterSources`/`fetchHostedTileset3dSources`**), listFeatureLayers(770), sampleCollectionField(933), uploadMapIcon(946), listMapIcons(981), deleteMapIcon(985), fetchMapIconBlob(989) |
| items | `domains/items.ts` | listItems(527), getItem(537), getItemBySlug(545), listPublicItems(549), getMetadataCatalog(541), createConfigItem(665), updateItem(713), uploadThumbnail(717), deleteItem(731), listGroups(742), getSharing(747), setSharing(751), listConfigRevisions(1006), rollbackConfig(1014) |

Pour chaque domaine : créer le fichier, copier les corps de méthode exacts,
importer dans `itemClient.ts`, spread dans le littéral retourné, lancer
`npx vitest run src/api/itemClient.test.ts` (**173 passed** attendu à
chaque étape, aucune régression tolérée), commit
(`refactor(shell): extrait le domaine <domaine> d'itemClient.ts`).

**Vigilance particulière** (spec §6 risque Étape 7) : si un nouveau point
de conversion raw↔front similaire à `toFrontLayer()` est découvert pendant
ce découpage (ex. dans `getPipelineConfig`/`getDatasetConfig`), lui
répliquer immédiatement un test caractéristique du même gabarit que la
Tâche 3 — ne jamais laisser apparaître une 5e occurrence du piège pendant
ce découpage lui-même.

- [ ] **Step 7 : `itemClient.ts` ne contient plus que la composition + `toFrontLayer`/`RawMapLayer` (module-level, réutilisées par `domains/layers.ts`)**

```ts
// itemClient.ts — état final
import { createBase } from "./base";
import { createIdentityMethods } from "./domains/identity";
import { createNotificationsMethods } from "./domains/notifications";
import { createItemsMethods } from "./domains/items";
import { createCollectionsAdminMethods } from "./domains/collectionsAdmin";
import { createExtensionsAdminToolsMethods } from "./domains/extensionsAdminTools";
import { createLayersMethods } from "./domains/layers";
import { createDatasetsMethods } from "./domains/datasets";
import { createPipelinesMethods } from "./domains/pipelines";
import { createAlertsMethods } from "./domains/alerts";
import { createReportsMethods } from "./domains/reports";
import { createAppsMethods } from "./domains/apps";
import { createAttachmentsMethods } from "./domains/attachments";
import { createFeaturesMethods } from "./domains/features";
import { createExportsIngestionMethods } from "./domains/exportsIngestion";
import { createTiles3dMethods } from "./domains/tiles3d";

export function createItemClient(opts: { coreUrl: string; getToken: () => string | undefined }): ItemClient {
  const base = createBase(opts);
  return {
    ...createIdentityMethods(base),
    ...createNotificationsMethods(base),
    ...createItemsMethods(base),
    ...createCollectionsAdminMethods(base),
    ...createExtensionsAdminToolsMethods(base),
    ...createLayersMethods(base),
    ...createDatasetsMethods(base),
    ...createPipelinesMethods(base),
    ...createAlertsMethods(base),
    ...createReportsMethods(base),
    ...createAppsMethods(base),
    ...createAttachmentsMethods(base),
    ...createFeaturesMethods(base),
    ...createExportsIngestionMethods(base),
    ...createTiles3dMethods(base),
    getAuthToken: opts.getToken,
    getCoreUrl: () => opts.coreUrl,
  };
}
```

- [ ] **Step 8 : découper `hooks.ts` (63 hooks) selon le même regroupement par domaine**

Créer `shell/src/api/domains/<domaine>.hooks.ts` pour chacun des 15
domaines ci-dessus, en y déplaçant les hooks correspondants (mapping 1:1
par nom déjà établi par la recherche préalable — ex. `useCreateDataset`,
`useDatasetConfig`, `useSaveDataset` → `domains/datasets.hooks.ts`).
`shell/src/api/hooks.ts` devient un fichier de ré-export :

```ts
// hooks.ts — état final
export * from "./domains/identity.hooks";
export * from "./domains/notifications.hooks";
export * from "./domains/items.hooks";
// ... les 12 autres domaines
```

- [ ] **Step 9 : suite complète (unitaire + E2E)**

```bash
cd shell && npm run test && npm run e2e
```

- [ ] **Step 10 : vérifier zéro import circulaire**

```bash
cd shell && npm run build
```

Un échec `tsc` sur un cycle d'import confirmerait le risque anticipé
(§6 spec) — dans ce cas, vérifier qu'aucun module de domaine n'importe un
autre module de domaine directement (seule dépendance autorisée :
`domains/*.ts` → `base.ts`, jamais `domains/*.ts` → `domains/*.ts`).

- [ ] **Step 11 : régénération des types TS (diff vide attendu, aucune route ne change)**

```bash
cd shell && npm run gen:api-types
git diff shell/src/api/generated/core-schema.d.ts
```

---

## Task 9 (Étape 8) : découpage de `mcp/tools.py` par domaine

Risque élevé — le vrai risque est architectural : faire dépendre les outils
MCP de fonctions de service partagées avec les routes REST est souhaitable
mais touche les deux surfaces à la fois. **Correction de nommage** : 21
tools réels (pas 22 comme la spec), 24 fichiers `test_mcp_*.py` réels (pas
25).

**Files:**
- Create: `core/app/mcp/tools/__init__.py`, `tools/catalog.py`,
  `tools/configs.py`, `tools/dataset.py`, `tools/bookmark.py`,
  `tools/analytics.py`, `tools/pipelines.py`, `tools/alerts.py`,
  `tools/reports.py`, `tools/sharing.py`, `tools/attachments.py`,
  `tools/identity.py`
- Create (couche de service, **n'existe pas encore** — cf. recherche
  préalable point 7) : `core/app/items/service.py` (extrait de
  `items/routes.py`), `core/app/configs/service.py` (extrait de
  `configs/routes.py`), `core/app/pipelines/service.py` (extrait de
  `pipelines/routes.py::run_pipeline_route`)
- Modify: `core/app/mcp/tools.py` (devient `core/app/mcp/tools/__init__.py`,
  ré-exporte `register_tools`), les 3 fichiers de routes ci-dessus (leur
  route HTTP appelle désormais la fonction de service extraite au lieu
  d'inline)
- Test: les 24 `test_mcp_*.py` existants (vérifiés un par un après chaque
  domaine déplacé), nouveau `core/tests/test_mcp_rest_parity.py`

**Interfaces:**
- Consumes: `core/app/harvest/connectors/` (patron de package par domaine à
  imiter, `core/app/harvest/service.py` comme seul précédent de couche de
  service dans le dépôt).
- Produces: chaque `tools/<domaine>.py` exporte une fonction
  `register(server, session_factory)` appelée par
  `tools/__init__.py::register_tools()`. `items/service.py::get_item_service(...)`,
  `configs/service.py::create_config_service(...)`,
  `pipelines/service.py::run_pipeline_service(...)` — fonctions publiques
  réutilisables par la route REST **et** l'outil MCP correspondant.

**⚠️ Risque documenté (spec §6)** : un outil qui se comportait différemment
de la route REST équivalente **par accident** (pas par design) pourrait
voir ce comportement corrigé silencieusement au passage — le test de
parité du Step 1 doit **documenter explicitement** tout écart trouvé avant
de le faire disparaître, jamais le résoudre sans décision explicite.

- [ ] **Step 1 : écrire le test de parité outil↔route AVANT tout déplacement (absent aujourd'hui, confirmé par la recherche)**

```python
# core/tests/test_mcp_rest_parity.py
"""Parité outil MCP <-> route REST équivalente — SP-43 Étape 8, oracle de
régression pour tout le découpage de mcp/tools.py. Sert aussi à documenter
les écarts de comportement déjà existants avant refactor (cf. spec §6 :
un écart trouvé ne doit jamais être "corrigé" silencieusement pendant ce
découpage)."""

import pytest


def test_get_item_tool_matches_get_item_route(mcp_client, http_client, seeded_item):
    tool_result = mcp_client.call_tool("get_item", {"itemId": seeded_item.id})
    route_result = http_client.get(f"/items/{seeded_item.id}").json()
    assert tool_result["pk"] == route_result["pk"]
    assert tool_result["title"] == route_result["title"]
    assert tool_result["permissions"] == route_result["permissions"]


def test_run_pipeline_tool_matches_run_pipeline_route_except_actor_kind(
    mcp_client, http_client, seeded_pipeline
):
    """Écart connu et attendu : actor_kind="agent" (MCP) vs "user" (REST) —
    documenté ici explicitement, ne jamais l'unifier sans décision produit."""
    tool_run = mcp_client.call_tool("run_pipeline", {"itemId": seeded_pipeline.id})
    route_run = http_client.post(f"/pipelines/{seeded_pipeline.id}/run").json()
    assert "runId" in tool_run
    assert "runId" in route_run
    # actor_kind volontairement non comparé ici — écart de design, pas un bug


def test_get_sharing_tool_matches_get_sharing_route(mcp_client, http_client, seeded_item):
    tool_result = mcp_client.call_tool("get_sharing", {"itemId": seeded_item.id})
    route_result = http_client.get(f"/items/{seeded_item.id}/sharing").json()
    assert tool_result == route_result
```

Adapter les fixtures `mcp_client`/`http_client`/`seeded_item`/`seeded_pipeline`
aux fixtures réellement disponibles dans `core/tests/conftest.py` et
`test_mcp_routes.py` (vérifier leur nom exact avant d'écrire — ce test
s'appuie sur des fixtures déjà utilisées par les 24 fichiers `test_mcp_*.py`
existants, ne pas en réinventer).

- [ ] **Step 2 : lancer le test de parité, documenter tout écart trouvé (ne pas corriger)**

```bash
cd core && uv run pytest tests/test_mcp_rest_parity.py -v
```

Si un écart de comportement apparaît en dehors de celui déjà documenté
(`actor_kind`), l'ajouter en commentaire explicite dans le test avec la
mention "écart pré-existant, non corrigé par SP-43" — ne jamais le
supprimer silencieusement dans les steps suivants.

- [ ] **Step 3 : extraire la couche de service `items/service.py` (n'existe pas encore, cf. recherche point 7)**

```python
# core/app/items/service.py
"""Couche de service pour les items — appelée par la route REST ET l'outil
MCP get_item, pour la première fois partagée entre les deux surfaces
(cf. spec SP-43 Étape 8 : jusqu'ici chaque tool réimplémentait sa propre
séquence de gardes)."""

from sqlalchemy.orm import Session

from app.items.models import Item
from app.items.repo import get_item_with_permissions
from app.users.models import User


def get_item_service(session: Session, *, item_id: str, user: User) -> dict:
    return get_item_with_permissions(session, item_id=item_id, user=user)
```

Adapter le corps exact au code réel de la route `GET /items/{id}`
(`items/routes.py:56`) — extraire la logique inline existante dans cette
fonction, sans changer son comportement.

- [ ] **Step 4 : faire appeler `items/service.py` par la route REST**

```python
# items/routes.py — la route devient un thin wrapper autour du service
@router.get("/items/{item_id}")
def get_item(item_id: str, session: Session = Depends(...), user: User = Depends(...)):
    return get_item_service(session, item_id=item_id, user=user)
```

```bash
cd core && uv run pytest tests/test_items_routes.py -v  # nom exact à vérifier
```

- [ ] **Step 5 : créer `mcp/tools/identity.py` et `mcp/tools/catalog.py`, migrer les tools qui appellent désormais le service**

```python
# core/app/mcp/tools/catalog.py
from app.items.service import get_item_service
from app.mcp.tools.identity import _resolve_actor  # ou import partagé équivalent

def register(server, session_factory) -> None:
    @server.tool()
    async def get_item(item_id: str) -> dict:
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            return get_item_service(session, item_id=item_id, user=user)

    # list_items, search_catalog, get_item — 3 tools de ce domaine
```

```bash
cd core && uv run pytest tests/test_mcp_tools_items.py tests/test_mcp_tools_search.py -v
```

```bash
git add core/app/items/service.py core/app/items/routes.py \
  core/app/mcp/tools/__init__.py core/app/mcp/tools/catalog.py \
  core/app/mcp/tools/identity.py core/tests/test_mcp_rest_parity.py
git commit -m "refactor(core): extrait items/service.py, migre les tools catalog/identity"
```

- [ ] **Step 6 : répéter le patron (service partagé + tools/<domaine>.py) pour les domaines restants**

Pour chaque domaine ci-dessous, dans l'ordre : (a) extraire ou identifier la
fonction de service existante côté route REST (créer si absente, comme au
Step 3 pour `configs` et `pipelines` — les seuls 2 autres domaines sans
couche de service selon la recherche préalable ; les domaines `bookmark`,
`analytics`, `alerts`, `reports`, `sharing`, `attachments` réutilisent des
repos déjà séparés de la route, à vérifier au cas par cas), (b) faire
appeler ce service par la route REST, (c) créer `tools/<domaine>.py`
appelant le même service, (d) lancer les tests `test_mcp_*.py` du domaine,
(e) commit.

| Domaine | Fichier | Tools (nom, ligne actuelle) | Service à extraire/vérifier |
|---|---|---|---|
| configs | `tools/configs.py` | get_app_config(449), save_app_config(461), create_item(494), create_form_app(549) | `configs/service.py` (nouveau, extrait de `create_config`, `configs/routes.py:170-221`) |
| dataset | `tools/dataset.py` | create_dataset(618) | réutilise `configs/service.py` avec kind="dataset" |
| bookmark | `tools/bookmark.py` | create_bookmark(684) | réutilise `configs/service.py` avec kind="bookmark" |
| analytics | `tools/analytics.py` | run_analytics_query(747), explain_dataset(827) | vérifier si `analytics/aggregate.py` expose déjà une fonction appelable indépendamment (hors périmètre spec §7 — ne PAS modifier ce fichier, seulement l'appeler) |
| pipelines | `tools/pipelines.py` | create_pipeline(887), run_pipeline(942), explain_pipeline(982) | `pipelines/service.py` (nouveau, extrait de `run_pipeline_route`, `pipelines/routes.py:99-125` — réutilise déjà `_require_pipeline_access`/`_require_pipeline_config`, existantes lignes 45/53) |
| alerts | `tools/alerts.py` | explain_alert_rule(1015) | pas de route REST équivalente (introspection MCP pure) — pas de service à créer |
| reports | `tools/reports.py` | explain_report_schedule(1050) | idem alerts |
| sharing | `tools/sharing.py` | get_sharing(1084), set_sharing(1097) | extraire de `items/routes.py:170-207` vers `items/service.py` (même fichier que Step 3) |
| attachments | `tools/attachments.py` | list_attachments(292) | réutilise le repo existant `app/attachments/` |

Pour le tool `run_pipeline` en particulier (le seul avec un écart de
comportement documenté au Step 1, `actor_kind`) : après migration vers
`pipelines/service.py`, vérifier que le test de parité
`test_run_pipeline_tool_matches_run_pipeline_route_except_actor_kind`
reste vert et que l'écart `actor_kind` est toujours présent et volontaire
(paramètre explicite passé par l'appelant, pas une différence de service).

- [ ] **Step 7 : `mcp/tools/__init__.py` compose tous les domaines**

```python
# core/app/mcp/tools/__init__.py
from fastmcp import FastMCP

from app.mcp.tools import (
    alerts, analytics, attachments, bookmark, catalog, configs,
    dataset, identity, pipelines, reports, sharing,
)


def register_tools(server: FastMCP, session_factory) -> None:
    for module in (
        identity, catalog, configs, dataset, bookmark, analytics,
        pipelines, alerts, reports, sharing, attachments,
    ):
        module.register(server, session_factory)

    @server.resource("schema://app-config")
    def app_config_schema():
        return BuilderConfig.model_json_schema()
```

Supprimer `core/app/mcp/tools.py` (fichier plat) une fois son contenu
entièrement réparti — `core/app/mcp/tools/__init__.py` prend sa place à
l'import (`from app.mcp.tools import register_tools` continue de
fonctionner sans changement côté appelant, package vs module).

- [ ] **Step 8 : lancer les 24 fichiers `test_mcp_*.py` intégralement**

```bash
cd core && uv run pytest tests/ -k "mcp" -v
```

- [ ] **Step 9 : lancer le test de parité, confirmer aucun nouvel écart introduit**

```bash
cd core && uv run pytest tests/test_mcp_rest_parity.py -v
```

- [ ] **Step 10 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 11 : régénération OpenAPI (diff attendu si `configs/service.py`/`pipelines/service.py`/`items/service.py` changent une forme de réponse — sinon vide)**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
git diff core/openapi.json
```

---

## Task 10 (Étape 9) : découpage de `pipelines/runtime.py` en registres

Risque le plus élevé de l'inventaire. **Précondition déjà levée** : les 5
tests `@pytest.mark.qgis` ont tourné pour de vrai contre un sidecar réel
(SP-44, jalon M14 atteint, 2026-09-05) — cette tâche peut démarrer sans
condition bloquante restante. Répartis sur **2 fichiers** (pas 1) :
`core/tests/test_pipeline_runtime.py` (2 tests qgis) et
`core/tests/test_qgis_worker_sidecar.py` (3 tests qgis, `pytestmark` de
module).

**Files:**
- Create: `core/app/pipelines/registries.py` (registres readers/writers ;
  les transforms non-QGIS restent dans `compiler.py`, déjà un dispatcher
  propre isolé, cf. recherche préalable point 2)
- Modify: `core/app/pipelines/runtime.py` (`_prepare()`,
  `_execute_transform_chain()`, `run_pipeline()` consomment les registres au
  lieu de leurs if/elif inline)
- Test: `core/tests/test_pipeline_runtime.py` (34 tests existants, doivent
  rester verts), `core/tests/test_pipeline_connector_runtime.py`,
  `core/tests/test_qgis_worker_sidecar.py`

**Interfaces:**
- Consumes: patron de registre `core/app/harvest/connectors/__init__.py`
  (`_REGISTRY: dict[str, HarvestConnector]` + `get_connector(source_type)`) ;
  signatures réelles des fonctions actuelles : `_materialize_reader(conn,
  view_name, base_uri, tenant_id, collection_id, table_info)`,
  `connector_runtime.materialize_rest_connector(conn, session=..., tenant_id=...,
  node_id=..., params=..., view_name=...)`, `_write_collection(session,
  conn, node=..., view_by_node=..., tenant_id=..., user=...)`,
  `_write_export(conn, s3_client, exports_bucket, node=..., view_by_node=...)`
  (**signature différente**, pas de `session`/`tenant_id`/`user`),
  `_write_dataset(session, conn, node=..., view_by_node=..., tenant_id=...,
  user=...)`.
- Produces: `core/app/pipelines/registries.py::READERS`,
  `core/app/pipelines/registries.py::WRITERS` — dicts publics, consommés
  par `_prepare()`/`run_pipeline()`.

**⚠️ Invariant à préserver absolument (spec §1.1 note 4, critique fermé par
SP-42)** : `_write_dataset` est le point d'écriture unique de
configuration de dataset — tout appelant doit continuer à passer par le
même chemin de garde `Privilege.DATA_MANAGE` (Tâche 2). Ne jamais
introduire un second chemin d'appel à `_write_dataset` qui contournerait
cette garde pendant ce découpage.

- [ ] **Step 1 : baseline — confirmer les 34 tests de `test_pipeline_runtime.py` + les 5 qgis passent**

```bash
cd core && uv run pytest tests/test_pipeline_runtime.py \
  tests/test_pipeline_connector_runtime.py -v
```

Si un sidecar qgis-worker réel est disponible dans cette session (variable
`CORE_TEST_QGIS_WORKER_URL` posée), relancer aussi les 5 tests qgis :

```bash
CORE_TEST_QGIS_WORKER_URL=... CORE_TEST_QGIS_SCRATCH_DIR=... \
  cd core && uv run pytest tests/test_pipeline_runtime.py \
  tests/test_qgis_worker_sidecar.py -m qgis -v
```

Sinon, noter explicitement dans le commit de clôture de cette tâche que les
5 tests qgis ont été **skippés** pendant l'exécution du plan (comme en CI)
et devront être rejoués manuellement avant de considérer la tâche
définitivement close — ne jamais affirmer qu'ils sont passés sans les avoir
vus tourner.

- [ ] **Step 2 : créer le registre readers (3 ops : `reader.collection`, `reader.connector.rest`, `reader.connector.postgres`)**

```python
# core/app/pipelines/registries.py
"""Registres readers/writers pour l'exécution de pipeline — SP-43 Étape 9.
Patron repris de core/app/harvest/connectors/__init__.py (seul registre
existant du dépôt). Les transforms non-QGIS restent dans compiler.py (déjà
un dispatcher fonctionnel pur, testé isolément) — seul transform.qgis a un
point d'extension ici, car c'est le seul avec un effet de bord (I/O +
réseau vers le sidecar)."""

from collections.abc import Callable
from typing import Protocol

import duckdb
from sqlalchemy.orm import Session

from app.pipelines import connector_runtime
from app.pipelines.schemas import (
    ReaderCollectionParams, ReaderConnectorPostgresParams, ReaderConnectorRestParams,
)


class ReaderFn(Protocol):
    def __call__(
        self, conn: duckdb.DuckDBPyConnection, *, session: Session, tenant_id: str,
        node_id: str, params: object, view_name: str,
    ) -> None: ...


def _read_collection(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    """Wrap de la logique inline actuelle de _prepare() pour reader.collection
    (résolution table_info + _materialize_reader) — corps déplacé tel quel
    depuis runtime.py, signature harmonisée avec les 2 autres readers."""
    ...  # corps exact à déplacer depuis _prepare(), lignes concernées de reader.collection


READERS: dict[str, Callable] = {
    "reader.collection": _read_collection,
    "reader.connector.rest": connector_runtime.materialize_rest_connector,
    "reader.connector.postgres": connector_runtime.materialize_postgres_connector,
}
```

Note pour l'implémenteur : `_read_collection` doit reproduire exactement le
corps actuel de la branche `reader.collection` de `_prepare()` (résolution
`_require_readable_collection_id`, `_table_info_for_collection`,
`_materialize_reader`, calcul de `srid_by_node[node.id]`) — ne pas changer
son comportement, seulement son emplacement et sa signature pour
l'harmoniser avec les 2 autres readers déjà conformes.

- [ ] **Step 3 : brancher le registre readers dans `_prepare()`**

```python
# runtime.py — AVANT (dispatch if/elif inline)
if node.op == "reader.collection":
    ...
elif node.op == "reader.connector.rest":
    ...
elif node.op == "reader.connector.postgres":
    ...
else:
    raise PipelineRuntimeError(f"unknown reader op '{node.op}'")

# APRÈS
from app.pipelines.registries import READERS

reader_fn = READERS.get(node.op)
if reader_fn is None:
    raise PipelineRuntimeError(f"unknown reader op '{node.op}'")
reader_fn(conn, session=session, tenant_id=tenant_id, node_id=node.id, params=node.params, view_name=view_name)
```

Adapter les paramètres transmis à chaque fonction du registre pour
correspondre exactement à leur signature réelle respective (elles ne
partagent pas toutes exactement les mêmes paramètres nommés aujourd'hui —
harmoniser au besoin par un petit wrapper local si nécessaire, plutôt que
de forcer une signature commune artificielle).

- [ ] **Step 4 : lancer `test_pipeline_runtime.py` (readers), confirmer zéro régression**

```bash
cd core && uv run pytest tests/test_pipeline_runtime.py -k "reader" -v
cd core && uv run pytest tests/test_pipeline_connector_runtime.py -v
```

```bash
git add core/app/pipelines/registries.py core/app/pipelines/runtime.py
git commit -m "refactor(core): registre readers pour pipelines/runtime.py"
```

- [ ] **Step 5 : créer le registre writers (3 ops)**

```python
# registries.py — ajout
WRITERS: dict[str, Callable] = {
    "writer.collection": _write_collection,     # signature (session, conn, *, node, view_by_node, tenant_id, user)
    "writer.export": _write_export,             # signature différente : (conn, s3_client, exports_bucket, *, node, view_by_node)
    "writer.dataset": _write_dataset,            # invariant critique SP-42 — garde Privilege.DATA_MANAGE via privilege_for_kind("dataset")
}
```

`_write_export` a une signature hétérogène (pas de `session`/`tenant_id`/
`user`) — ne pas forcer d'uniformité artificielle : le call site dans
`run_pipeline()` continue de fournir les bons arguments à chaque fonction
selon l'op, le registre ne fait que remplacer l'`if/elif` par un `dict.get`
suivi d'un appel adapté par op (pas un appel générique uniforme).

```python
# runtime.py — run_pipeline(), AVANT
if node.op == "writer.collection":
    stat = _write_collection(session, conn, node=node, view_by_node=view_by_node, tenant_id=tenant_id, user=user)
elif node.op == "writer.export":
    stat = _write_export(conn, s3_client, exports_bucket, node=node, view_by_node=view_by_node)
elif node.op == "writer.dataset":
    stat = _write_dataset(session, conn, node=node, view_by_node=view_by_node, tenant_id=tenant_id, user=user)

# APRÈS
from app.pipelines.registries import WRITERS

writer_fn = WRITERS.get(node.op)
if writer_fn is None:
    raise PipelineRuntimeError(f"unknown writer op '{node.op}'")
if node.op == "writer.export":
    stat = writer_fn(conn, s3_client, exports_bucket, node=node, view_by_node=view_by_node)
else:
    stat = writer_fn(session, conn, node=node, view_by_node=view_by_node, tenant_id=tenant_id, user=user)
```

- [ ] **Step 6 : lancer `test_pipeline_runtime.py` (writers), confirmer zéro régression — vigilance particulière sur `_write_dataset`**

```bash
cd core && uv run pytest tests/test_pipeline_runtime.py -k "writer" -v
```

Vérifier explicitement qu'un test existant couvre le fait que
`writer.dataset` continue d'exiger `Privilege.DATA_MANAGE` (invariant
critique SP-42) — si aucun test ne le couvre à ce niveau (le test existant
pourrait ne couvrir la garde qu'au niveau route, `pipelines/routes.py`),
ajouter un test dédié qui appelle `run_pipeline()` directement avec un
utilisateur sans ce privilège et confirme le rejet, avant de clore cette
tâche.

```bash
git add core/app/pipelines/registries.py core/app/pipelines/runtime.py
git commit -m "refactor(core): registre writers pour pipelines/runtime.py"
```

- [ ] **Step 7 : suite complète (hors qgis, comme en CI)**

```bash
cd core && uv run pytest
```

- [ ] **Step 8 : si un sidecar qgis-worker réel est disponible, rejouer les 5 tests qgis en session manuelle**

```bash
CORE_TEST_QGIS_WORKER_URL=... CORE_TEST_QGIS_SCRATCH_DIR=... \
  cd core && uv run pytest tests/test_pipeline_runtime.py \
  tests/test_qgis_worker_sidecar.py -m qgis -v
```

`transform.qgis` (l'exécution sidecar, `_execute_qgis_transform`) et son
verrouillage (`_lock_down`) ne sont **pas** déplacés dans un registre par
cette tâche (spec §2.1 : c'est le seul transform avec effet de bord —
laissé inline dans `runtime.py`, référencé par `compiler.py` via son propre
point d'extension `TRANSFORMS_SIDE_EFFECT` si le rédacteur du plan choisit
de l'ajouter, sinon laissé tel quel avec sa branche `if node.op ==
"transform.qgis":` actuelle dans `_execute_transform_chain()` — décision à
prendre selon le risque perçu au moment de l'implémentation, cette tâche
n'impose pas ce déplacement supplémentaire).

- [ ] **Step 9 : régénération OpenAPI (diff vide attendu, aucune route ne change)**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
git diff core/openapi.json
```

---

## Clôture de plan

- [ ] **Suite complète finale** (les 3 suites, dans cet ordre) :

```bash
cd core && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles \
  && uv run lint-imports \
  && uv run pytest \
  && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
cd ../shell && npm run lint && npm run format:check \
  && npm run test && npm run build \
  && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold \
  && npm run e2e
uvx pre-commit run --all-files
```

- [ ] **Mettre à jour CLAUDE.md** (`### Livré`) avec une ligne SP-43 résumant :
  registre kind→privilège unique (4 sites fermés), test caractéristique
  toFrontLayer, fixture E2E collection unique, comparateur modèle↔Alembic (24
  colonnes corrigées), module de job partagé (5-6 fichiers), primitive
  aria-expanded/aria-controls (7-9 sites), découpage itemClient.ts/hooks.ts
  (15 domaines), découpage mcp/tools.py (11 domaines + 3 couches de service
  créées), découpage pipelines/runtime.py (registres readers/writers).
- [ ] **Documenter dans le suivi de clôture** tout écart trouvé par le test
  de parité MCP↔REST (Tâche 9, Step 1) qui n'aurait pas été résolu — cf.
  spec §6, ne jamais le laisser silencieux.
