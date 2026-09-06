# GAP-19 — SDK d'embedding : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Donner à un tiers le moyen d'intégrer une App/Dashboard GeoStudio
entière, en lecture seule, dans un `<iframe>` sur son propre site, via un
jeton invité qui réutilise le mécanisme `share_link` existant (SP-54) et
autorise, en plus de l'item lui-même, la lecture des collections que sa
config référence.

**Architecture:** Un nouveau module `app/configs/guest_access.py` résout la
portée d'un jeton de lien de partage (item racine + collections référencées
par ses `dataSources`, y compris via `datasetId`) en une dépendance FastAPI
additive (`get_share_link_actor`), consommée par le chokepoint déjà unique
`get_readable_collection` et par `GET /configs/by-item/{item_id}`. Le jeton
voyage sur un en-tête HTTP dédié (`X-Share-Link-Token`), jamais sur
`Authorization` — chemin réellement parallèle à `get_current_user`. Côté
shell, une page publique `/embed/:token` construit son propre `ItemClient`
(jeton invité au lieu d'un jeton OIDC) et réutilise `AppRenderer(config,
mode="runtime")` tel quel.

**Tech Stack:** FastAPI/SQLAlchemy/Pydantic (cœur), React/TanStack
Query/React Router (shell), pytest (cœur), Vitest+Testing Library+MSW
(shell unitaire), Playwright (shell E2E).

## Global Constraints

- Aucune modification de `can()`/`decide()`/`get_current_user` — chemin
  d'autorisation invité strictement additif (spec §3 décision 4).
- Le jeton invité ne voyage jamais sur `Authorization` (spec §2.5).
- Portée résolue par requête HTTP, jamais mise en cache au-delà (spec §3
  décision 3).
- `cd core && PYTHONPATH=. uv run lint-imports` doit rester vert sans
  nouvelle entrée `ignore_imports` (spec §2.4).
- Chaque tâche cœur qui touche une route ou un schéma se termine par la
  régénération OpenAPI/TS (Tâche 9) — mais UNE SEULE fois, à la fin de
  toutes les tâches cœur, pas par tâche (éviter de régénérer 6 fois).
- `core/tests/test_deployability.py`/`lint-imports`/`ruff` ne sont pas
  modifiés par ce plan (aucune nouvelle variable d'environnement, aucun
  nouveau service).
- Docs/commentaires en français, identifiants/code en anglais (convention
  du dépôt).

---

## File Structure

**Cœur (nouveau/modifié) :**
- Create: `core/app/configs/guest_access.py` — `GuestActor`,
  `resolve_guest_scope`, `authorize_guest_item_read`,
  `authorize_guest_collection_read`, `get_share_link_actor`.
- Test: `core/tests/test_configs_guest_access.py`
- Modify: `core/app/collections/routes.py` (`get_readable_collection` +
  `get_collection`/`get_collection_schema`)
- Modify: `core/app/configs/routes.py` (`get_config_by_item`)
- Modify: `core/app/features/routes.py` (`list_features`,
  `get_single_feature`, `aggregate_features`)
- Modify: `core/app/features/tiles.py` (`get_collection_tile`)
- Modify: `core/app/attachments/routes.py` (`list_attachments_route`,
  `read_attachment_file`)
- Modify: `core/app/sharing/schemas.py` (`ShareLinkCreated.token`)
- Modify: `core/app/items/routes.py` (`create_share_link_route`)
- Test: `core/tests/test_collections_guest_access_routes.py`
- Test: `core/tests/test_configs_guest_access_routes.py`
- Test: `core/tests/test_features_guest_access_routes.py`
- Test: `core/tests/test_features_tiles_guest_access_postgis.py`
- Test: `core/tests/test_attachments_guest_access_routes.py`
- Modify: `core/tests/test_share_links_routes.py` (nouveau test `token`)
- Modify: `core/openapi.json` (régénéré, Tâche 9)

**Shell (nouveau/modifié) :**
- Modify: `shell/src/api/base.ts` (`ItemClientBase.getShareLinkToken`,
  `request()`, `fetchGeoJsonFeatures()`)
- Modify: `shell/src/api/itemClient.ts` (`createItemClient` accepte/expose
  `getShareLinkToken`)
- Modify: `shell/src/api/types.ts` (`ItemClient.getShareLinkToken?`,
  `createShareLink` return type gagne `token`)
- Modify: `shell/src/api/domains/items.ts` (`createShareLink` relaie
  `token`)
- Modify: `shell/src/map/MapView.tsx` (prop `getShareLinkToken?`,
  `transformRequest`, fetch manuel d'attachment)
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (thread
  `getShareLinkToken`)
- Create: `shell/src/pages/embed/resolveShareLink.ts`
- Create: `shell/src/pages/EmbedPage.tsx`
- Modify: `shell/src/shell/routes.tsx` (`/embed/:token`)
- Modify: `shell/src/shell/ShareForm.tsx` (section « Intégrer »)
- Create: `shell/src/api/base.test.ts` additions (ou fichier existant si
  présent — vérifié à l'exécution, cf. Tâche 10)
- Modify: `shell/src/api/itemClient.test.ts` (nouveaux tests
  `getShareLinkToken`/`createShareLink` retourne `token`)
- Modify: `shell/src/map/MapView.test.tsx` (nouveaux tests
  `transformRequest`/attachment avec `getShareLinkToken`)
- Create: `shell/src/pages/embed/resolveShareLink.test.ts`
- Create: `shell/src/pages/EmbedPage.test.tsx`
- Modify: `shell/src/shell/ShareForm.test.tsx` (nouveaux tests section «
  Intégrer »)
- Create: `shell/e2e/embed.spec.ts`
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré, Tâche 9)

---

## Task 1: `app/configs/guest_access.py` — résolution de la portée invité

**Files:**
- Create: `core/app/configs/guest_access.py`
- Test: `core/tests/test_configs_guest_access.py`

**Interfaces:**
- Consumes: `app.sharing.share_links.ShareLinkTokenClaims` (déjà existant :
  `share_link_id: str`, `tenant_id: str`, `item_id: str`) ;
  `app.sharing.share_links.decode_share_link_token(token: str) ->
  ShareLinkTokenClaims` ; `app.sharing.share_links.ShareLinkTokenError` ;
  `app.sharing.repository.get_active_share_link(session, *, tenant_id,
  link_id) -> ShareLink | None` ; `app.items.repository.get_access_facts
  (session, *, tenant_id, item_id) -> ItemAccessFacts | None` ;
  `app.configs.repository.get_config_by_item(session, item_id) ->
  ConfigRead | None` (avec `ConfigRead.kind: str`, `ConfigRead.config:
  BuilderConfig`) ; `app.configs.schemas.BuilderConfig.dataSources:
  list[DataSource]` (`DataSource.type: str`, `.layer: str`,
  `.datasetId: str | None` — **absent en pratique côté schéma cœur
  aujourd'hui**, cf. Step 1 ci-dessous) ; `app.configs.schemas.
  DatasetPayload.source: Literal["collection","arcgis"]`,
  `.collectionId: str | None`.
- Produces (consommé par les Tâches 2-7) : `GuestActor` (dataclass gelée,
  champs `tenant_id: str`, `item_id: str`, `share_link_id: str`,
  `allowed_item_ids: frozenset[str]`, `allowed_collection_ids:
  frozenset[str]`) ; `resolve_guest_scope(session: Session, claims:
  ShareLinkTokenClaims) -> GuestActor | None` ;
  `authorize_guest_item_read(guest: GuestActor | None, item_id: str) ->
  bool` ; `authorize_guest_collection_read(guest: GuestActor | None,
  collection_id: str) -> bool` ; `get_share_link_actor(x_share_link_token:
  str | None = Header(default=None, alias="X-Share-Link-Token"), session:
  Session = Depends(get_session)) -> GuestActor | None` (dépendance
  FastAPI, ne lève jamais).

**Note préalable importante** : `core/app/configs/schemas.py::DataSource`
(la forme CŒUR) ne porte aujourd'hui **pas** de champ `datasetId` — seul le
type TypeScript `shell/src/api/types.ts:737-744` l'a. Avant d'écrire Step 3
ci-dessous, ouvrir `core/app/configs/schemas.py` et vérifier l'état réel de
`class DataSource` : si `datasetId` est toujours absent côté cœur, l'ajouter
comme `datasetId: str | None = None` (champ additif, rétrocompatible —
aucune migration, `BuilderConfig` est stocké en JSON dans
`ConfigRevision.data`, pas de colonne SQL par champ). Falsifier avant
d'avancer : un `BuilderConfig.model_validate({..., "dataSources": [{"id":
"x", "type": "features", "service": "core", "layer": "", "datasetId":
"item-2", "query": {}}]})` doit réussir et exposer `.dataSources[0].
datasetId == "item-2"`.

- [ ] **Step 1: Écrire le test qui prouve que `DataSource.datasetId` existe côté cœur**

```python
# core/tests/test_configs_guest_access.py (nouveau fichier)
# SPDX-License-Identifier: Apache-2.0
from app.configs.schemas import BuilderConfig


def test_data_source_accepts_a_dataset_id():
    config = BuilderConfig.model_validate(
        {
            "kind": "app",
            "dataSources": [
                {
                    "id": "ds1",
                    "type": "features",
                    "service": "core",
                    "layer": "",
                    "datasetId": "item-dataset-1",
                    "query": {},
                }
            ],
            "layout": {"type": "grid", "items": []},
        }
    )
    assert config.dataSources[0].datasetId == "item-dataset-1"
```

- [ ] **Step 2: Lancer le test, constater l'échec (ou le succès) réel**

Run: `cd core && uv run pytest tests/test_configs_guest_access.py::test_data_source_accepts_a_dataset_id -v`

Si le test échoue avec une erreur Pydantic (`Extra inputs are not
permitted` ou équivalent), `DataSource.datasetId` n'existe pas encore côté
cœur — ouvrir `core/app/configs/schemas.py`, trouver `class DataSource
(BaseModel)` (près de la ligne 14) et ajouter le champ :

```python
class DataSource(BaseModel):
    id: str
    type: str
    service: str
    layer: str
    datasetId: str | None = None
    query: dict = Field(default_factory=dict)
```

Si le test passe déjà (le champ existe), ne rien changer et documenter ce
fait dans le message du commit de cette étape (`nothing to change — already
present`) plutôt que de faire un commit vide.

- [ ] **Step 3: Relancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_configs_guest_access.py::test_data_source_accepts_a_dataset_id -v`
Expected: PASS

- [ ] **Step 4: Écrire le module `guest_access.py` — squelette + `authorize_*`**

```python
# core/app/configs/guest_access.py
# SPDX-License-Identifier: Apache-2.0
"""Autorisation invité (GAP-19) : un jeton de lien de partage (SP-54,
app.sharing.share_links) autorise, en plus de la lecture de l'item racine,
la lecture des collections que sa config référence comme sources de
données. Chemin PARALLÈLE à app.sharing.authorization.can() — jamais une
modification de can()/decide()/get_current_user. Vit dans app.configs (pas
app.sharing) car la résolution de portée a besoin de lire BuilderConfig/
DataSource (app.configs.schemas) et get_config_by_item
(app.configs.repository) — app.sharing est EN DESSOUS d'app.configs dans le
contrat de couches (core/pyproject.toml) et ne peut donc pas les importer.
Même patron qu'app.configs.bbox (SP-55/GAP-06), même raison structurelle."""

from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.db import get_session
from app.items import repository as items_repo
from app.sharing import repository as sharing_repo
from app.sharing.share_links import ShareLinkTokenClaims, ShareLinkTokenError, decode_share_link_token


@dataclass(frozen=True)
class GuestActor:
    tenant_id: str
    item_id: str
    share_link_id: str
    allowed_item_ids: frozenset[str]
    allowed_collection_ids: frozenset[str]


def authorize_guest_item_read(guest: GuestActor | None, item_id: str) -> bool:
    return guest is not None and item_id in guest.allowed_item_ids


def authorize_guest_collection_read(guest: GuestActor | None, collection_id: str) -> bool:
    return guest is not None and collection_id in guest.allowed_collection_ids
```

- [ ] **Step 5: Test que `authorize_guest_item_read`/`authorize_guest_collection_read` sont de simples vérifications d'appartenance**

```python
# core/tests/test_configs_guest_access.py (suite)
from app.configs.guest_access import (
    GuestActor,
    authorize_guest_collection_read,
    authorize_guest_item_read,
)


def _guest(**overrides) -> GuestActor:
    defaults = dict(
        tenant_id="t1",
        item_id="app-1",
        share_link_id="link-1",
        allowed_item_ids=frozenset({"app-1"}),
        allowed_collection_ids=frozenset({"col-a"}),
    )
    defaults.update(overrides)
    return GuestActor(**defaults)


def test_authorize_guest_item_read_true_for_allowed_id():
    assert authorize_guest_item_read(_guest(), "app-1") is True


def test_authorize_guest_item_read_false_for_other_id():
    assert authorize_guest_item_read(_guest(), "app-2") is False


def test_authorize_guest_item_read_false_when_guest_is_none():
    assert authorize_guest_item_read(None, "app-1") is False


def test_authorize_guest_collection_read_true_for_allowed_id():
    assert authorize_guest_collection_read(_guest(), "col-a") is True


def test_authorize_guest_collection_read_false_for_other_id():
    assert authorize_guest_collection_read(_guest(), "col-b") is False


def test_authorize_guest_collection_read_false_when_guest_is_none():
    assert authorize_guest_collection_read(None, "col-a") is False
```

- [ ] **Step 6: Lancer, constater le succès (fonctions déjà écrites au Step 4)**

Run: `cd core && uv run pytest tests/test_configs_guest_access.py -v`
Expected: 7 passed (le test du Step 1 + les 6 ci-dessus)

- [ ] **Step 7: Commit**

```bash
cd core && git add app/configs/schemas.py app/configs/guest_access.py tests/test_configs_guest_access.py
git commit -m "feat(core): pose GuestActor et les vérifications d'appartenance (GAP-19)"
```

- [ ] **Step 8: Écrire le test de `resolve_guest_scope` — cas simple, un `DataSource.layer` direct**

Fixture SQLite partagée par tout ce fichier (même patron que
`core/tests/test_configs_extension_permissions.py`) :

```python
# core/tests/test_configs_guest_access.py (en tête de fichier, après les imports)
import pytest

from app.configs import repository as configs_repo
from app.configs.guest_access import resolve_guest_scope
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.sharing.share_links import ShareLinkTokenClaims
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    yield make_session_factory(engine)
    engine.dispose()


def _create_app_item(session, *, tenant_id, owner_id, data_sources):
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="app", title="App"
    )
    config = BuilderConfig.model_validate(
        {
            "kind": "app",
            "dataSources": data_sources,
            "layout": {"type": "grid", "items": []},
        }
    )
    configs_repo.create_config(session, item_id=item.id, tenant_id=tenant_id, config=config)
    session.commit()
    return item.id


def test_resolve_guest_scope_collects_direct_layer_references(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        app_item_id = _create_app_item(
            session, tenant_id=tenant.id, owner_id=owner.id,
            data_sources=[
                {"id": "ds1", "type": "features", "service": "core", "layer": "incidents", "query": {}},
                {"id": "ds2", "type": "static", "service": "core", "layer": "", "query": {"records": []}},
            ],
        )
        claims = ShareLinkTokenClaims(share_link_id="link-1", tenant_id=tenant.id, item_id=app_item_id)

        guest = resolve_guest_scope(session, claims)

        assert guest is not None
        assert guest.allowed_item_ids == frozenset({app_item_id})
        assert guest.allowed_collection_ids == frozenset({"incidents"})
```

Note : `configs_repo.create_config` — vérifier sa signature exacte dans
`core/app/configs/repository.py` avant d'écrire ce test (elle peut différer
de l'appel ci-dessus, ex. accepter directement un dict au lieu d'un
`BuilderConfig`, ou nécessiter un titre) ; l'ajuster à la signature réelle
plutôt que de la deviner — piège CLAUDE.md n°3.

- [ ] **Step 9: Lancer, constater l'échec (`resolve_guest_scope` n'existe pas encore)**

Run: `cd core && uv run pytest tests/test_configs_guest_access.py::test_resolve_guest_scope_collects_direct_layer_references -v`
Expected: FAIL avec `ImportError: cannot import name 'resolve_guest_scope'`

- [ ] **Step 10: Implémenter `resolve_guest_scope` (cas simple d'abord, sans `datasetId`)**

```python
# core/app/configs/guest_access.py (ajouter après authorize_guest_collection_read)


def resolve_guest_scope(session: Session, claims: ShareLinkTokenClaims) -> "GuestActor | None":
    facts = items_repo.get_access_facts(session, tenant_id=claims.tenant_id, item_id=claims.item_id)
    if facts is None:
        return None
    root = configs_repo.get_config_by_item(session, claims.item_id)
    if root is None or root.kind not in ("app", "dashboard"):
        return None

    allowed_item_ids = {claims.item_id}
    allowed_collection_ids: set[str] = set()
    for ds in root.config.dataSources:
        if ds.type == "static":
            continue
        if ds.layer:
            allowed_collection_ids.add(ds.layer)

    return GuestActor(
        tenant_id=claims.tenant_id,
        item_id=claims.item_id,
        share_link_id=claims.share_link_id,
        allowed_item_ids=frozenset(allowed_item_ids),
        allowed_collection_ids=frozenset(allowed_collection_ids),
    )
```

- [ ] **Step 11: Relancer, vérifier le succès**

Run: `cd core && uv run pytest tests/test_configs_guest_access.py::test_resolve_guest_scope_collects_direct_layer_references -v`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
cd core && git add app/configs/guest_access.py tests/test_configs_guest_access.py
git commit -m "feat(core): resolve_guest_scope collecte les collections référencées directement"
```

- [ ] **Step 13: Écrire les tests des cas limites (kind non-app/dashboard, item absent, datasetId, cross-tenant)**

```python
# core/tests/test_configs_guest_access.py (suite)


def test_resolve_guest_scope_returns_none_for_unknown_item(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        claims = ShareLinkTokenClaims(share_link_id="l", tenant_id=tenant.id, item_id="does-not-exist")
        assert resolve_guest_scope(session, claims) is None


def test_resolve_guest_scope_returns_none_for_non_app_dashboard_kind(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            session, tenant_id=tenant.id, owner_id=owner.id, resource_type="dataset", title="D"
        )
        config = BuilderConfig.model_validate(
            {"kind": "dataset", "dataset": {"source": "collection", "collectionId": "incidents", "columns": {}}}
        )
        configs_repo.create_config(session, item_id=item.id, tenant_id=tenant.id, config=config)
        session.commit()
        claims = ShareLinkTokenClaims(share_link_id="l", tenant_id=tenant.id, item_id=item.id)
        assert resolve_guest_scope(session, claims) is None


def test_resolve_guest_scope_follows_dataset_id_to_its_collection(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        dataset_item = items_repo.create_item(
            session, tenant_id=tenant.id, owner_id=owner.id, resource_type="dataset", title="D"
        )
        dataset_config = BuilderConfig.model_validate(
            {"kind": "dataset", "dataset": {"source": "collection", "collectionId": "communes", "columns": {}}}
        )
        configs_repo.create_config(session, item_id=dataset_item.id, tenant_id=tenant.id, config=dataset_config)
        app_item_id = _create_app_item(
            session, tenant_id=tenant.id, owner_id=owner.id,
            data_sources=[
                {
                    "id": "ds1", "type": "features", "service": "core", "layer": "",
                    "datasetId": dataset_item.id, "query": {},
                },
            ],
        )
        claims = ShareLinkTokenClaims(share_link_id="l", tenant_id=tenant.id, item_id=app_item_id)

        guest = resolve_guest_scope(session, claims)

        assert guest is not None
        assert guest.allowed_item_ids == frozenset({app_item_id, dataset_item.id})
        assert guest.allowed_collection_ids == frozenset({"communes"})


def test_resolve_guest_scope_ignores_an_arcgis_dataset(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        dataset_item = items_repo.create_item(
            session, tenant_id=tenant.id, owner_id=owner.id, resource_type="dataset", title="D"
        )
        dataset_config = BuilderConfig.model_validate(
            {"kind": "dataset", "dataset": {"source": "arcgis", "arcgisItemId": "arcgis-1", "columns": {}}}
        )
        configs_repo.create_config(session, item_id=dataset_item.id, tenant_id=tenant.id, config=dataset_config)
        app_item_id = _create_app_item(
            session, tenant_id=tenant.id, owner_id=owner.id,
            data_sources=[
                {
                    "id": "ds1", "type": "features", "service": "core", "layer": "",
                    "datasetId": dataset_item.id, "query": {},
                },
            ],
        )
        claims = ShareLinkTokenClaims(share_link_id="l", tenant_id=tenant.id, item_id=app_item_id)

        guest = resolve_guest_scope(session, claims)

        assert guest is not None
        # Le dataset ArcGIS est bien listé comme item lisible (résolution de
        # son itemClient.getDatasetConfig continuera de fonctionner), mais
        # n'ajoute AUCUNE collection : source arcgis, hors modèle collection.
        assert guest.allowed_item_ids == frozenset({app_item_id, dataset_item.id})
        assert guest.allowed_collection_ids == frozenset()


def test_resolve_guest_scope_rejects_a_dataset_id_from_another_tenant(session_factory):
    with session_factory() as session:
        tenant_a = get_or_create_default_tenant(session)
        owner_a = get_or_create_user(
            session, tenant_id=tenant_a.id, oidc_sub="oa", username="ownera",
            email=None, first_name="", last_name="",
        )
        from app.tenants.repository import create_tenant

        tenant_b = create_tenant(session, name="tenant-b", slug="tenant-b")
        owner_b = get_or_create_user(
            session, tenant_id=tenant_b.id, oidc_sub="ob", username="ownerb",
            email=None, first_name="", last_name="",
        )
        # Un dataset appartenant au tenant B, référençant une collection
        # privée du tenant B ("secret-b").
        foreign_dataset = items_repo.create_item(
            session, tenant_id=tenant_b.id, owner_id=owner_b.id, resource_type="dataset", title="D-B"
        )
        foreign_config = BuilderConfig.model_validate(
            {"kind": "dataset", "dataset": {"source": "collection", "collectionId": "secret-b", "columns": {}}}
        )
        configs_repo.create_config(session, item_id=foreign_dataset.id, tenant_id=tenant_b.id, config=foreign_config)
        # Une App du tenant A qui référence (par construction de test, comme
        # si un import/copier-coller malencontreux avait recopié un id) ce
        # dataset du tenant B via datasetId.
        app_item_id = _create_app_item(
            session, tenant_id=tenant_a.id, owner_id=owner_a.id,
            data_sources=[
                {
                    "id": "ds1", "type": "features", "service": "core", "layer": "",
                    "datasetId": foreign_dataset.id, "query": {},
                },
            ],
        )
        claims = ShareLinkTokenClaims(share_link_id="l", tenant_id=tenant_a.id, item_id=app_item_id)

        guest = resolve_guest_scope(session, claims)

        assert guest is not None
        assert foreign_dataset.id not in guest.allowed_item_ids
        assert "secret-b" not in guest.allowed_collection_ids
```

Vérifier avant d'écrire ce dernier test que `app.tenants.repository`
expose bien une fonction de création de tenant nommée `create_tenant` avec
cette signature (`name`, `slug`) — ajuster si le nom réel diffère (piège
CLAUDE.md n°3, ne pas deviner).

- [ ] **Step 14: Lancer, constater l'échec sur les cas `datasetId`/cross-tenant (pas encore implémentés)**

Run: `cd core && uv run pytest tests/test_configs_guest_access.py -v`
Expected: `test_resolve_guest_scope_returns_none_for_unknown_item` et
`test_resolve_guest_scope_returns_none_for_non_app_dashboard_kind` PASS déjà
(couverts par le Step 10) ; les trois tests `datasetId`/cross-tenant FAIL
(assertions sur `allowed_item_ids`/`allowed_collection_ids` fausses, le
code du Step 10 ignore encore `ds.datasetId`).

- [ ] **Step 15: Étendre `resolve_guest_scope` pour suivre `datasetId`**

```python
# core/app/configs/guest_access.py — remplacer le corps de la boucle for
# ds in root.config.dataSources (posé au Step 10) par :

    allowed_item_ids = {claims.item_id}
    allowed_collection_ids: set[str] = set()
    for ds in root.config.dataSources:
        if ds.type == "static":
            continue
        if ds.datasetId:
            ds_facts = items_repo.get_access_facts(
                session, tenant_id=claims.tenant_id, item_id=ds.datasetId
            )
            if ds_facts is None:
                continue
            allowed_item_ids.add(ds.datasetId)
            ds_config = configs_repo.get_config_by_item(session, ds.datasetId)
            if (
                ds_config is not None
                and ds_config.kind == "dataset"
                and ds_config.config.dataset is not None
                and ds_config.config.dataset.source == "collection"
                and ds_config.config.dataset.collectionId
            ):
                allowed_collection_ids.add(ds_config.config.dataset.collectionId)
        elif ds.layer:
            allowed_collection_ids.add(ds.layer)
```

- [ ] **Step 16: Relancer toute la suite du fichier, vérifier le succès complet**

Run: `cd core && uv run pytest tests/test_configs_guest_access.py -v`
Expected: tous les tests PASS (12 au total : 1 datasource + 6
authorize_* + 5 resolve_guest_scope).

- [ ] **Step 17: Commit**

```bash
cd core && git add app/configs/guest_access.py tests/test_configs_guest_access.py
git commit -m "feat(core): resolve_guest_scope suit datasetId, ignore arcgis, refuse le cross-tenant"
```

- [ ] **Step 18: Écrire le test de `get_share_link_actor` (la dépendance FastAPI elle-même)**

```python
# core/tests/test_configs_guest_access.py (suite)
import pytest

from app.configs.guest_access import get_share_link_actor
from app.sharing import repository as sharing_repo
from app.sharing.share_links import mint_share_link_token


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    # >=32 bytes, même contrainte que test_share_links_routes.py.
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", "test-guest-access-secret-padding0")


def test_get_share_link_actor_returns_none_without_a_header(session_factory):
    with session_factory() as session:
        assert get_share_link_actor(x_share_link_token=None, session=session) is None


def test_get_share_link_actor_returns_none_for_a_garbage_token(session_factory):
    with session_factory() as session:
        assert get_share_link_actor(x_share_link_token="not-a-jwt", session=session) is None


def test_get_share_link_actor_resolves_a_valid_token(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        app_item_id = _create_app_item(
            session, tenant_id=tenant.id, owner_id=owner.id,
            data_sources=[
                {"id": "ds1", "type": "features", "service": "core", "layer": "incidents", "query": {}},
            ],
        )
        link = sharing_repo.create_share_link(
            session, tenant_id=tenant.id, item_id=app_item_id, created_by=owner.id, ttl_seconds=3600
        )
        session.commit()
        token = mint_share_link_token(
            share_link_id=link.id, tenant_id=tenant.id, item_id=app_item_id, ttl_seconds=3600
        )

        guest = get_share_link_actor(x_share_link_token=token, session=session)

        assert guest is not None
        assert guest.allowed_collection_ids == frozenset({"incidents"})


def test_get_share_link_actor_returns_none_for_a_revoked_link(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        app_item_id = _create_app_item(
            session, tenant_id=tenant.id, owner_id=owner.id,
            data_sources=[
                {"id": "ds1", "type": "features", "service": "core", "layer": "incidents", "query": {}},
            ],
        )
        link = sharing_repo.create_share_link(
            session, tenant_id=tenant.id, item_id=app_item_id, created_by=owner.id, ttl_seconds=3600
        )
        session.commit()
        token = mint_share_link_token(
            share_link_id=link.id, tenant_id=tenant.id, item_id=app_item_id, ttl_seconds=3600
        )
        sharing_repo.revoke_share_link(session, tenant_id=tenant.id, link_id=link.id)
        session.commit()

        assert get_share_link_actor(x_share_link_token=token, session=session) is None
```

- [ ] **Step 19: Lancer, constater l'échec (`get_share_link_actor` n'existe pas encore)**

Run: `cd core && uv run pytest tests/test_configs_guest_access.py -v -k get_share_link_actor`
Expected: FAIL avec `ImportError`

- [ ] **Step 20: Implémenter `get_share_link_actor`**

```python
# core/app/configs/guest_access.py — ajouter en fin de fichier


def get_share_link_actor(
    x_share_link_token: str | None = Header(default=None, alias="X-Share-Link-Token"),
    session: Session = Depends(get_session),
) -> "GuestActor | None":
    if not x_share_link_token:
        return None
    try:
        claims = decode_share_link_token(x_share_link_token)
    except ShareLinkTokenError:
        return None
    link = sharing_repo.get_active_share_link(
        session, tenant_id=claims.tenant_id, link_id=claims.share_link_id
    )
    if link is None:
        return None
    return resolve_guest_scope(session, claims)
```

- [ ] **Step 21: Relancer toute la suite, vérifier le succès complet**

Run: `cd core && uv run pytest tests/test_configs_guest_access.py -v`
Expected: tous PASS (16 tests au total)

- [ ] **Step 22: `ruff format`/`ruff check`/`mypy --strict` sur ce module**

Run: `cd core && uv run ruff format app/configs/guest_access.py tests/test_configs_guest_access.py && uv run ruff check app/configs/guest_access.py tests/test_configs_guest_access.py`
Expected: propre. `app.configs` ne fait PAS partie des 6 modules
`mypy --strict` de `CLAUDE.md` — ne pas le lancer inutilement (pas dans le
périmètre déclaré).

- [ ] **Step 23: `lint-imports`, vérifier zéro nouvelle exemption**

Run: `cd core && uv run lint-imports`
Expected: PASS, sans modification de `pyproject.toml`.

- [ ] **Step 24: Commit**

```bash
cd core && git add app/configs/guest_access.py tests/test_configs_guest_access.py
git commit -m "feat(core): get_share_link_actor — dépendance FastAPI additive du jeton invité"
```

---

## Task 2: `get_readable_collection` accepte un `GuestActor`

**Files:**
- Modify: `core/app/collections/routes.py:181-213`
- Test: `core/tests/test_collections_guest_access_routes.py`

**Interfaces:**
- Consumes: `GuestActor`, `authorize_guest_collection_read` (Task 1).
- Produces: `get_readable_collection(session, user, collection_id, *,
  can_manage_collections: bool = False, guest: GuestActor | None = None)`
  — signature étendue, consommée par les Tâches 4-7.

- [ ] **Step 1: Écrire le test qui prouve le nouveau comportement, en appelant la fonction directement (pas de route encore câblée)**

```python
# core/tests/test_collections_guest_access_routes.py (nouveau fichier)
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from app.collections import repository as collections_repo
from app.collections.models import Collection
from app.collections.routes import get_readable_collection
from app.configs.guest_access import GuestActor
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    yield make_session_factory(engine)
    engine.dispose()


def _create_private_collection(session, *, tenant_id, owner_id, collection_id):
    col = Collection(
        id=collection_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        table_name=collection_id,
        title=collection_id,
        description="",
        pk_column="id",
        editable=True,
        is_public=False,
    )
    session.add(col)
    session.flush()
    return col


def _guest(tenant_id, *, allowed=("incidents",)) -> GuestActor:
    return GuestActor(
        tenant_id=tenant_id,
        item_id="app-1",
        share_link_id="link-1",
        allowed_item_ids=frozenset({"app-1"}),
        allowed_collection_ids=frozenset(allowed),
    )


def test_guest_with_allowed_collection_bypasses_can(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        _create_private_collection(session, tenant_id=tenant.id, owner_id=owner.id, collection_id="incidents")
        session.commit()

        col = get_readable_collection(
            session, None, "incidents", guest=_guest(tenant.id)
        )

        assert col.id == "incidents"


def test_guest_without_the_collection_in_scope_still_gets_404(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        _create_private_collection(session, tenant_id=tenant.id, owner_id=owner.id, collection_id="secret")
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            get_readable_collection(session, None, "secret", guest=_guest(tenant.id, allowed=("incidents",)))
        assert exc_info.value.status_code == 404


def test_guest_uses_its_own_tenant_not_the_default_tenant(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        _create_private_collection(session, tenant_id=tenant.id, owner_id=owner.id, collection_id="incidents")
        session.commit()

        # guest.tenant_id volontairement erroné : la collection n'existe pas
        # dans ce tenant-là, même si "incidents" existe ailleurs.
        with pytest.raises(HTTPException) as exc_info:
            get_readable_collection(
                session, None, "incidents",
                guest=GuestActor(
                    tenant_id="wrong-tenant", item_id="app-1", share_link_id="link-1",
                    allowed_item_ids=frozenset({"app-1"}), allowed_collection_ids=frozenset({"incidents"}),
                ),
            )
        assert exc_info.value.status_code == 404
```

Vérifier la signature réelle du constructeur `Collection` (`core/app/
collections/models.py`) avant ce Step — certains champs par défaut
(`feature_count`, `attachment_fields`, etc.) peuvent être requis ; ajuster
`_create_private_collection` à la signature réelle plutôt que de la
deviner (piège CLAUDE.md n°3).

- [ ] **Step 2: Lancer, constater l'échec (`get_readable_collection` ne connaît pas encore `guest`)**

Run: `cd core && uv run pytest tests/test_collections_guest_access_routes.py -v`
Expected: FAIL avec `TypeError: get_readable_collection() got an unexpected keyword argument 'guest'`

- [ ] **Step 3: Étendre `get_readable_collection`**

```python
# core/app/collections/routes.py — remplacer les lignes 181-213 par :

def get_readable_collection(
    session,
    user,
    collection_id,
    *,
    can_manage_collections: bool = False,
    guest=None,  # GuestActor | None (app.configs.guest_access) — import
    # local dans la fonction pour ne pas créer d'import de niveau module
    # (app.collections est déjà AU-DESSUS d'app.configs dans le contrat de
    # couches, donc l'import direct serait légal, mais rester cohérent avec
    # le style déjà utilisé plus haut dans cette même fonction pour
    # get_or_create_default_tenant, importé localement lui aussi).
):
    """404 avant 403 : une collection illisible est indistinguable d'une absente.

    `can_manage_collections` (privilège `admin.collections.manage`, SP-35) élargit
    la visibilité exactement comme `can_see_all` le fait déjà pour
    `list_visible_collections` : un rôle sur mesure porteur de ce privilège doit
    voir individuellement (GET/PATCH/DELETE) toute collection qu'il voit déjà en
    liste, pas seulement les siennes/partagées/publiques — sinon un même
    utilisateur verrait une collection dans `GET /collections` puis un 404 en
    cliquant dessus ou en la supprimant (piège n°5, chemin de lecture oublié,
    appliqué ici à la visibilité individuelle plutôt qu'au verdict `delete`).

    `guest` (GAP-19) : un GuestActor dont `allowed_collection_ids` contient
    `collection_id` contourne can() — c'est le but (portée invité explicite,
    même sur une collection privée). Résolu avec `guest.tenant_id`, jamais
    le tenant par défaut du chemin anonyme ci-dessous."""
    from app.configs.guest_access import authorize_guest_collection_read

    col = None
    if user is not None:
        col = repo.get_collection(session, tenant_id=user.tenant_id, collection_id=collection_id)
    elif guest is not None:
        col = repo.get_collection(session, tenant_id=guest.tenant_id, collection_id=collection_id)
    else:
        from app.tenants.repository import get_or_create_default_tenant

        tenant = get_or_create_default_tenant(session)
        col = repo.get_collection(session, tenant_id=tenant.id, collection_id=collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="collection not found")

    if guest is not None and authorize_guest_collection_read(guest, collection_id):
        return col

    readable = can_manage_collections or can(
        session,
        user_id=user.id if user else "",
        action="read",
        item=repo.get_access_facts(col),
        kind="collection",
        actor_is_admin=bool(user and user.is_admin),
    )
    if not readable:
        raise HTTPException(status_code=404, detail="collection not found")
    return col
```

- [ ] **Step 4: Relancer, vérifier le succès**

Run: `cd core && uv run pytest tests/test_collections_guest_access_routes.py -v`
Expected: 3 passed

- [ ] **Step 5: Rejouer la suite complète de `app/collections` pour vérifier l'absence de régression**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v`
Expected: tous les tests déjà existants passent inchangés (le paramètre
`guest` est optionnel, défaut `None`, jamais consommé par ces tests).

- [ ] **Step 6: Commit**

```bash
cd core && git add app/collections/routes.py tests/test_collections_guest_access_routes.py
git commit -m "feat(core): get_readable_collection accepte un GuestActor (GAP-19)"
```

---

## Task 3: `GET /configs/by-item/{item_id}` accepte le jeton invité

**Files:**
- Modify: `core/app/configs/routes.py:352-365`
- Test: `core/tests/test_configs_guest_access_routes.py`

**Interfaces:**
- Consumes: `GuestActor`, `get_share_link_actor`, `authorize_guest_item_read`
  (Task 1) ; `app.auth.dependency.get_current_user_optional` (déjà
  existant).
- Produces: rien de nouveau consommé par une tâche ultérieure — la route
  elle-même est le produit final de cette tâche, consommée directement par
  le shell (Task 12).

- [ ] **Step 1: Écrire le test bout-en-bout (TestClient), en réutilisant le patron `.pop()` de `test_features_routes_read.py::test_anonymous_reads_public_only`**

```python
# core/tests/test_configs_guest_access_routes.py (nouveau fichier)
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

_SECRET = "test-configs-guest-access-secret-pad0"


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET)


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app)
    client.session_factory = Session  # type: ignore[attr-defined]
    client.tenant_id = tenant.id  # type: ignore[attr-defined]
    return app, client


def _create_app_config(client, *, data_sources):
    body = {
        "kind": "app",
        "dataSources": data_sources,
        "layout": {"type": "grid", "items": []},
    }
    created = client.post("/v1/configs", json={"title": "App", "config": body}).json()
    return created["itemId"]


def _create_link_token(client, item_id: str) -> str:
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    return created["url"].rsplit("/", 1)[-1]


def test_guest_token_grants_access_to_the_root_app_config(env):
    app, client = env
    item_id = _create_app_config(
        client,
        data_sources=[
            {"id": "ds1", "type": "features", "service": "core", "layer": "incidents", "query": {}},
        ],
    )
    token = _create_link_token(client, item_id)

    # Retire les overrides posés pour la préparation : la requête suivante
    # doit être traitée par le VRAI get_current_user_optional (aucune
    # Authorization envoyée, seul le header invité compte).
    app.dependency_overrides.pop(get_current_user)
    response = client.get(
        f"/v1/configs/by-item/{item_id}", headers={"X-Share-Link-Token": token}
    )

    assert response.status_code == 200
    assert response.json()["itemId"] == item_id


def test_guest_token_for_a_non_app_dashboard_item_gets_404(env):
    app, client = env
    body = {"kind": "dataset", "dataset": {"source": "collection", "collectionId": "incidents", "columns": {}}}
    created = client.post("/v1/configs", json={"title": "D", "config": body}).json()
    item_id = created["itemId"]
    token = _create_link_token(client, item_id)

    app.dependency_overrides.pop(get_current_user)
    response = client.get(
        f"/v1/configs/by-item/{item_id}", headers={"X-Share-Link-Token": token}
    )

    assert response.status_code == 404
    # La résolution publique de métadonnées, elle, continue de fonctionner :
    # inchangée par ce chantier.
    resolved = client.get(f"/v1/share-links/{token}")
    assert resolved.status_code == 200
    assert resolved.json()["itemId"] == item_id


def test_revoked_token_behaves_exactly_like_no_token(env):
    app, client = env
    item_id = _create_app_config(client, data_sources=[])
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    token = created["url"].rsplit("/", 1)[-1]
    link_id = client.get(f"/v1/items/{item_id}/share-links").json()[0]["id"]
    client.delete(f"/v1/items/{item_id}/share-links/{link_id}")

    app.dependency_overrides.pop(get_current_user)
    with_token = client.get(f"/v1/configs/by-item/{item_id}", headers={"X-Share-Link-Token": token})
    without_token = client.get(f"/v1/configs/by-item/{item_id}")

    assert with_token.status_code == without_token.status_code == 404


def test_authenticated_user_unaffected_by_guest_wiring(env):
    app, client = env
    item_id = _create_app_config(client, data_sources=[])
    # Utilisateur réel, AUCUN jeton invité : le comportement doit être
    # strictement celui d'avant ce chantier.
    app.dependency_overrides[get_current_user_optional] = lambda: client.app.dependency_overrides[
        get_current_user
    ]()
    response = client.get(f"/v1/configs/by-item/{item_id}")
    assert response.status_code == 200
    assert response.json()["itemId"] == item_id
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd core && uv run pytest tests/test_configs_guest_access_routes.py -v`
Expected: FAIL sur les 3 premiers tests (la route exige encore
`get_current_user`, un appel sans Authorization renvoie 401, pas 200/404
selon le cas) ; le 4ᵉ (`test_authenticated_user_unaffected_by_guest_wiring`)
peut déjà passer ou échouer selon l'implémentation actuelle — noter le
résultat réel sans le supposer.

- [ ] **Step 3: Câbler le jeton invité sur la route**

```python
# core/app/configs/routes.py — en tête de fichier, ajouter aux imports existants :
from app.auth.dependency import get_current_user, get_current_user_optional
from app.configs.guest_access import GuestActor, authorize_guest_item_read, get_share_link_actor

# Remplacer les lignes 352-365 (get_config_by_item) par :


@router.get("/configs/by-item/{item_id}", response_model=ConfigRead)
def get_config_by_item(
    item_id: str,
    mode: str | None = None,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
) -> ConfigRead:
    if user is not None:
        _require_access(session, user=user, item_id=item_id, action="read")
    elif not authorize_guest_item_read(guest, item_id):
        raise HTTPException(status_code=404, detail="config not found")
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    if mode == "runtime":
        _apps_runtime_executions_counter.add(1)
    return result
```

- [ ] **Step 4: Relancer, vérifier le succès complet**

Run: `cd core && uv run pytest tests/test_configs_guest_access_routes.py -v`
Expected: 4 passed

- [ ] **Step 5: Rejouer toute la suite `core/tests` touchant `app/configs` pour vérifier l'absence de régression**

Run: `cd core && uv run pytest tests/ -k configs -v`
Expected: tous PASS (aucune route/comportement existant modifié pour un
utilisateur réel).

- [ ] **Step 6: Commit**

```bash
cd core && git add app/configs/routes.py tests/test_configs_guest_access_routes.py
git commit -m "feat(core): GET /configs/by-item/{id} accepte un jeton invité (GAP-19)"
```

---

## Task 4: `app/features/routes.py` — features/aggregate acceptent le jeton invité

**Files:**
- Modify: `core/app/features/routes.py:188-230,251-280,498-514`
- Test: `core/tests/test_features_guest_access_routes.py`

**Interfaces:**
- Consumes: `GuestActor`, `get_share_link_actor` (Task 1) ;
  `get_readable_collection(..., guest=...)` (Task 2).
- Produces: rien de nouveau — consommé directement par le shell (widgets
  carte/table/graphique en mode embed).

- [ ] **Step 1: Écrire le test bout-en-bout (fake introspector/repo, patron `test_features_routes_read.py`)**

```python
# core/tests/test_features_guest_access_routes.py (nouveau fichier)
# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.features.repository import FeaturePage
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

_SECRET = "test-features-guest-access-secret-pad"

INFO = TableInfo(
    table_name="incidents", pk_column="id", geometry_column="geom",
    geometry_type="Point", srid=4326,
    columns=[ColumnInfo(name="titre", type="string", required=True)],
)
FEAT = {"type": "Feature", "id": 1, "geometry": None, "properties": {"titre": "a"}}


def fake_introspector(session, table_name):
    if table_name not in ("incidents", "other"):
        raise TableNotFound(table_name)
    return INFO


def fake_repo():
    def select_features(session, info, *, limit, offset, bbox=None, geom_intersects=None, filters=None):
        return FeaturePage(features=[FEAT], number_matched=1, number_returned=1)

    def get_feature(session, info, *, fid):
        return FEAT if fid == "1" else None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature)


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET)


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[features_routes.get_features_repo] = lambda: fake_repo()
    app.dependency_overrides[features_routes.get_rls_scope] = lambda: features_routes.null_rls_scope
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_user_optional] = lambda: owner
    client = TestClient(app)
    client.session_factory = Session  # type: ignore[attr-defined]
    return app, client, owner


def _register(client, table_name: str):
    client.post("/v1/collections", json={"tableName": table_name, "isPublic": False})


def _create_app_config(client, *, layer: str) -> str:
    body = {
        "kind": "app",
        "dataSources": [{"id": "ds1", "type": "features", "service": "core", "layer": layer, "query": {}}],
        "layout": {"type": "grid", "items": []},
    }
    return client.post("/v1/configs", json={"title": "App", "config": body}).json()["itemId"]


def _mint_token(client, item_id: str) -> str:
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    return created["url"].rsplit("/", 1)[-1]


def test_guest_token_reads_features_of_a_referenced_private_collection(env):
    app, client, _owner = env
    _register(client, "incidents")
    _register(client, "other")
    item_id = _create_app_config(client, layer="incidents")
    token = _mint_token(client, item_id)

    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get("/v1/collections/incidents/items", headers={"X-Share-Link-Token": token})
    assert r.status_code == 200
    assert r.json()["numberReturned"] == 1

    r2 = client.get("/v1/collections/incidents/items/1", headers={"X-Share-Link-Token": token})
    assert r2.status_code == 200

    r3 = client.post(
        "/v1/collections/incidents/aggregate", json={"agg": "count"},
        headers={"X-Share-Link-Token": token},
    )
    assert r3.status_code == 200


def test_guest_token_does_not_grant_access_to_an_unreferenced_private_collection(env):
    app, client, _owner = env
    _register(client, "incidents")
    _register(client, "other")
    item_id = _create_app_config(client, layer="incidents")
    token = _mint_token(client, item_id)

    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get("/v1/collections/other/items", headers={"X-Share-Link-Token": token})
    assert r.status_code == 404

    r2 = client.get("/v1/collections/other/items/1", headers={"X-Share-Link-Token": token})
    assert r2.status_code == 404

    r3 = client.post(
        "/v1/collections/other/aggregate", json={"agg": "count"},
        headers={"X-Share-Link-Token": token},
    )
    assert r3.status_code == 404


def test_export_routes_still_require_a_real_user_even_with_a_guest_token(env):
    app, client, _owner = env
    _register(client, "incidents")
    item_id = _create_app_config(client, layer="incidents")
    token = _mint_token(client, item_id)

    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get(
        "/v1/collections/incidents/export/items?format=csv",
        headers={"X-Share-Link-Token": token},
    )
    assert r.status_code == 401
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd core && uv run pytest tests/test_features_guest_access_routes.py -v`
Expected: FAIL sur `test_guest_token_reads_features_...` (404, le
`guest`/header n'est pas encore câblé) ; `test_guest_token_does_not_grant_
access_...` peut déjà passer par accident (les deux donnent 404) — vérifier
au Step 4 qu'il passe pour la BONNE raison (portée invité, pas absence de
câblage) ; `test_export_routes_still_require_a_real_user...` doit déjà
passer (route inchangée par ce plan).

- [ ] **Step 3: Câbler `guest` sur `list_features`/`get_single_feature`/`aggregate_features`**

```python
# core/app/features/routes.py — en tête de fichier, ajouter :
from app.configs.guest_access import GuestActor, get_share_link_actor

# list_features (lignes 188-201) : ajouter le paramètre et le relayer
@router.get("/collections/{collection_id}/items")
def list_features(
    collection_id: str,
    request: Request,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
    bbox: str | None = None,
    geom_intersects: str | None = None,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id, guest=guest)
    # ... reste du corps INCHANGÉ ...

# aggregate_features (lignes 251-260) : même ajout
@router.post("/collections/{collection_id}/aggregate")
def aggregate_features(
    collection_id: str,
    body: AggregateRequestBody,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    conn_factory=Depends(get_duckdb_connection_factory),
    base_uri: str = Depends(get_analytics_base_uri),
):
    col = get_readable_collection(session, user, collection_id, guest=guest)
    # ... reste du corps INCHANGÉ ...

# get_single_feature (lignes 498-508) : même ajout
@router.get("/collections/{collection_id}/items/{fid}")
def get_single_feature(
    collection_id: str,
    fid: str,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id, guest=guest)
    # ... reste du corps INCHANGÉ ...
```

- [ ] **Step 4: Relancer, vérifier le succès complet**

Run: `cd core && uv run pytest tests/test_features_guest_access_routes.py -v`
Expected: 3 passed

- [ ] **Step 5: Rejouer toute la suite features pour vérifier l'absence de régression**

Run: `cd core && uv run pytest tests/test_features_routes_read.py tests/test_features_routes_write.py -v`
Expected: tous PASS inchangés.

- [ ] **Step 6: Commit**

```bash
cd core && git add app/features/routes.py tests/test_features_guest_access_routes.py
git commit -m "feat(core): list_features/get_single_feature/aggregate_features acceptent le jeton invité"
```

---

## Task 5: `GET /collections/{id}/tiles/{z}/{x}/{y}.mvt` accepte le jeton invité

**Files:**
- Modify: `core/app/features/tiles.py:113-165`
- Test: `core/tests/test_features_tiles_guest_access_postgis.py` (marqué
  `@pytest.mark.postgis` — les tuiles MVT ne se testent qu'avec de vraies
  fonctions PostGIS, patron `test_features_tiles_postgis.py`)

**Interfaces:**
- Consumes: `GuestActor`, `get_share_link_actor` (Task 1),
  `get_readable_collection(..., guest=...)` (Task 2).

- [ ] **Step 1: Écrire le test PostGIS bout-en-bout**

```python
# core/tests/test_features_tiles_guest_access_postgis.py (nouveau fichier)
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

_SECRET = "test-tiles-guest-access-secret-padding"


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET)


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        for table in ("demo_incidents_guest", "demo_other_guest"):
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
            conn.execute(
                text(
                    f"CREATE TABLE {table} (id serial PRIMARY KEY, "
                    "titre text NOT NULL, geom geometry(Point, 4326))"
                )
            )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_user_optional] = lambda: owner
    client = TestClient(app)
    client.post("/v1/collections", json={"tableName": "demo_incidents_guest", "isPublic": False})
    client.post("/v1/collections", json={"tableName": "demo_other_guest", "isPublic": False})
    client.post(
        "/v1/collections/demo_incidents_guest/items",
        json={
            "type": "Feature", "properties": {"titre": "Fuite"},
            "geometry": {"type": "Point", "coordinates": [2.35, 48.85]},
        },
    )
    body = {
        "kind": "app",
        "dataSources": [
            {"id": "ds1", "type": "features", "service": "core", "layer": "demo_incidents_guest", "query": {}}
        ],
        "layout": {"type": "grid", "items": []},
    }
    item_id = client.post("/v1/configs", json={"title": "App", "config": body}).json()["itemId"]
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    token = created["url"].rsplit("/", 1)[-1]
    yield client, app, token
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents_guest"))
        conn.execute(text("DROP TABLE IF EXISTS demo_other_guest"))
        conn.execute(
            text(
                "TRUNCATE collection_shares, collections, config_revisions, configs, "
                "share_link, items, audit_log, users, tenants CASCADE"
            )
        )


def test_guest_token_reads_a_tile_of_a_referenced_private_collection(pg_app):
    client, app, token = pg_app
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get(
        "/v1/collections/demo_incidents_guest/tiles/0/0/0.mvt",
        headers={"X-Share-Link-Token": token},
    )
    assert r.status_code == 200
    assert r.content


def test_guest_token_gets_404_on_an_unreferenced_private_collection(pg_app):
    client, app, token = pg_app
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get(
        "/v1/collections/demo_other_guest/tiles/0/0/0.mvt",
        headers={"X-Share-Link-Token": token},
    )
    assert r.status_code == 404
```

Vérifier avant d'exécuter que les noms de table exacts à `TRUNCATE` dans
`pg_engine.begin()` (fin de fixture) correspondent réellement aux tables
créées par `Base.metadata.create_all` sur ce conteneur — copier le bloc
`TRUNCATE` de `test_features_tiles_postgis.py` tel quel puis y ajouter
`configs, config_revisions, share_link` (tables touchées par ce test, pas
par l'original) plutôt que de deviner la liste complète.
- [ ] **Step 2: Lancer contre un conteneur PostGIS de test réel**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://... uv run pytest tests/test_features_tiles_guest_access_postgis.py -v`
(remplacer par la vraie chaîne de connexion du conteneur `postgis-test` de
la session — cf. `CLAUDE.md` §Commandes). Sans `CORE_TEST_DATABASE_URL`,
ce test skip silencieusement (`pg_engine` fixture) — ne jamais conclure
« ça passe » sans l'avoir vu tourner pour de vrai (piège CLAUDE.md n°2/6).
Expected: FAIL (le paramètre `guest` n'existe pas encore sur
`get_collection_tile`).

- [ ] **Step 3: Câbler `guest` sur `get_collection_tile`**

```python
# core/app/features/tiles.py — en tête de fichier, ajouter :
from app.configs.guest_access import GuestActor, get_share_link_actor

# Remplacer la signature de get_collection_tile (lignes 113-123) par :
@router.get("/collections/{collection_id}/tiles/{z}/{x}/{y}.mvt")
def get_collection_tile(
    collection_id: str,
    z: int,
    x: int,
    y: int,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    rls=Depends(get_rls_scope),
) -> Response:
    # Même porte que GET /items : 404 avant 403, anonyme accepté sur une
    # collection publique — plus désormais un jeton invité scopé (GAP-19).
    col = get_readable_collection(session, user, collection_id, guest=guest)
    # ... reste du corps INCHANGÉ ...
```

- [ ] **Step 4: Relancer, vérifier le succès complet**

Run: `cd core && CORE_TEST_DATABASE_URL=... uv run pytest tests/test_features_tiles_guest_access_postgis.py -v`
Expected: 2 passed

- [ ] **Step 5: Rejouer `test_features_tiles_postgis.py` pour l'absence de régression**

Run: `cd core && CORE_TEST_DATABASE_URL=... uv run pytest tests/test_features_tiles_postgis.py -v`
Expected: tous PASS inchangés.

- [ ] **Step 6: Commit**

```bash
cd core && git add app/features/tiles.py tests/test_features_tiles_guest_access_postgis.py
git commit -m "feat(core): GET /collections/{id}/tiles/{z}/{x}/{y}.mvt accepte le jeton invité"
```

---

## Task 6: `GET /collections/{id}` et `/schema` acceptent le jeton invité

**Files:**
- Modify: `core/app/collections/routes.py:415-482`
- Test: `core/tests/test_collections_guest_access_routes.py` (fichier créé
  Task 2, complété ici)

**Interfaces:**
- Consumes: `GuestActor`, `get_share_link_actor` (Task 1),
  `get_readable_collection(..., guest=...)` (Task 2).

- [ ] **Step 1: Ajouter les tests bout-en-bout au fichier de la Task 2**

```python
# core/tests/test_collections_guest_access_routes.py (ajouter en fin de fichier)
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db as _init_db_route, make_engine as _make_engine_route, \
    make_session_factory as _make_session_factory_route, request_scoped_session
from app.main import create_app

_SECRET = "test-collections-guest-access-secret0"


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET)


@pytest.fixture()
def route_env():
    engine = _make_engine_route("sqlite+pysqlite:///:memory:")
    _init_db_route(engine)
    Session = _make_session_factory_route(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_user_optional] = lambda: owner
    client = TestClient(app)
    client.post("/v1/collections", json={"tableName": "incidents", "isPublic": False})
    client.post("/v1/collections", json={"tableName": "other", "isPublic": False})
    body = {
        "kind": "app",
        "dataSources": [{"id": "ds1", "type": "features", "service": "core", "layer": "incidents", "query": {}}],
        "layout": {"type": "grid", "items": []},
    }
    item_id = client.post("/v1/configs", json={"title": "App", "config": body}).json()["itemId"]
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    token = created["url"].rsplit("/", 1)[-1]
    return app, client, token


def test_guest_token_reads_collection_metadata_and_schema(route_env):
    app, client, token = route_env
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get("/v1/collections/incidents", headers={"X-Share-Link-Token": token})
    assert r.status_code == 200

    r2 = client.get("/v1/collections/incidents/schema", headers={"X-Share-Link-Token": token})
    assert r2.status_code == 200


def test_guest_token_does_not_read_an_unreferenced_collection(route_env):
    app, client, token = route_env
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get("/v1/collections/other", headers={"X-Share-Link-Token": token})
    assert r.status_code == 404

    r2 = client.get("/v1/collections/other/schema", headers={"X-Share-Link-Token": token})
    assert r2.status_code == 404
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd core && uv run pytest tests/test_collections_guest_access_routes.py -v -k route_env`
Expected: FAIL sur `test_guest_token_reads_collection_metadata_and_schema`
(404, `guest` pas encore câblé sur ces deux routes).

- [ ] **Step 3: Câbler `guest` sur `get_collection`/`get_collection_schema`**

```python
# core/app/collections/routes.py — en tête de fichier, ajouter :
from app.configs.guest_access import GuestActor, get_share_link_actor

# get_collection (lignes 415-429)
@router.get("/collections/{collection_id}")
def get_collection(
    collection_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
    extent_provider=Depends(get_extent_provider),
):
    can_manage_collections = bool(
        user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    )
    col = get_readable_collection(
        session, user, collection_id, can_manage_collections=can_manage_collections, guest=guest
    )
    # ... reste du corps INCHANGÉ ...

# get_collection_schema (lignes 463-475)
@router.get("/collections/{collection_id}/schema")
def get_collection_schema(
    collection_id: str,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
):
    can_manage_collections = bool(
        user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    )
    col = get_readable_collection(
        session, user, collection_id, can_manage_collections=can_manage_collections, guest=guest
    )
    # ... reste du corps INCHANGÉ ...
```

- [ ] **Step 4: Relancer, vérifier le succès complet**

Run: `cd core && uv run pytest tests/test_collections_guest_access_routes.py -v`
Expected: tous PASS (5 tests au total avec ceux de la Task 2)

- [ ] **Step 5: Rejouer `test_collections_routes.py` pour l'absence de régression**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v`
Expected: tous PASS inchangés.

- [ ] **Step 6: Commit**

```bash
cd core && git add app/collections/routes.py tests/test_collections_guest_access_routes.py
git commit -m "feat(core): GET /collections/{id} et /schema acceptent le jeton invité"
```

---

## Task 7: pièces jointes (`attachments`) acceptent le jeton invité

**Files:**
- Modify: `core/app/attachments/routes.py:286-297,300-335`
- Test: `core/tests/test_attachments_guest_access_routes.py`

**Interfaces:**
- Consumes: `GuestActor`, `get_share_link_actor` (Task 1),
  `get_readable_collection(..., guest=...)` (Task 2).

- [ ] **Step 1: Écrire le test bout-en-bout (patron `_FakeS3Client` de `test_attachments_read_routes.py`)**

```python
# core/tests/test_attachments_guest_access_routes.py (nouveau fichier)
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.attachments import repository as attachments_repo
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

_SECRET = "test-attachments-guest-access-secret0"


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {"key-1": b"contenu"}

    def get_object(self, *, Bucket, Key):
        class _Body:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

        return {"Body": _Body(self.objects[Key])}


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET)


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="o", username="owner",
            email=None, first_name="", last_name="",
        )
        col = Collection(
            id="incidents", tenant_id=tenant.id, owner_id=owner.id, table_name="incidents",
            title="incidents", description="", pk_column="id", editable=True, is_public=False,
            attachment_fields=[{"key": "photos", "label": "Photos"}],
        )
        s.add(col)
        attachment = attachments_repo.create_attachment(
            s, tenant_id=tenant.id, collection_id="incidents", fid="1", field_key="photos",
            filename="photo.jpg", content_type="image/jpeg", byte_size=7, s3_key="key-1",
            created_by=owner.id,
        )
        s.commit()
        attachment_id = attachment.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _FakeS3Client()
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_user_optional] = lambda: owner
    client = TestClient(app)
    body = {
        "kind": "app",
        "dataSources": [{"id": "ds1", "type": "features", "service": "core", "layer": "incidents", "query": {}}],
        "layout": {"type": "grid", "items": []},
    }
    item_id = client.post("/v1/configs", json={"title": "App", "config": body}).json()["itemId"]
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    token = created["url"].rsplit("/", 1)[-1]
    return app, client, token, attachment_id


def test_guest_token_lists_and_downloads_an_attachment(env):
    app, client, token, attachment_id = env
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get(
        "/v1/collections/incidents/items/1/attachments", headers={"X-Share-Link-Token": token}
    )
    assert r.status_code == 200
    assert len(r.json()["attachments"]) == 1

    r2 = client.get(
        f"/v1/collections/incidents/items/1/attachments/{attachment_id}/file",
        headers={"X-Share-Link-Token": token},
    )
    assert r2.status_code == 200
    assert r2.content == b"contenu"
```

Vérifier la signature exacte de `attachments_repo.create_attachment`
(`core/app/attachments/repository.py`) avant d'exécuter — l'ajuster si elle
diffère de l'appel ci-dessus (piège CLAUDE.md n°3).

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd core && uv run pytest tests/test_attachments_guest_access_routes.py -v`
Expected: FAIL (404 sur les deux appels, `guest` pas encore câblé).

- [ ] **Step 3: Câbler `guest` sur `list_attachments_route`/`read_attachment_file`**

```python
# core/app/attachments/routes.py — en tête de fichier, ajouter :
from app.configs.guest_access import GuestActor, get_share_link_actor

# list_attachments_route (lignes 286-297)
@router.get("/collections/{collection_id}/items/{fid}/attachments", response_model=AttachmentList)
def list_attachments_route(
    collection_id: str,
    fid: str,
    fieldKey: str | None = None,
    user: User | None = Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session),
):
    col = get_readable_collection(session, user, collection_id, guest=guest)
    # ... reste du corps INCHANGÉ ...

# read_attachment_file (lignes 300-318)
@router.get("/collections/{collection_id}/items/{fid}/attachments/{attachment_id}/file")
def read_attachment_file(
    collection_id: str,
    fid: str,
    attachment_id: str,
    user: User | None = Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session),
    s3=Depends(get_s3_client),
) -> Response:
    col = get_readable_collection(session, user, collection_id, guest=guest)
    # ... reste du corps INCHANGÉ ...
```

- [ ] **Step 4: Relancer, vérifier le succès complet**

Run: `cd core && uv run pytest tests/test_attachments_guest_access_routes.py -v`
Expected: 1 passed

- [ ] **Step 5: Rejouer `test_attachments_read_routes.py` pour l'absence de régression**

Run: `cd core && uv run pytest tests/test_attachments_read_routes.py -v`
Expected: tous PASS inchangés.

- [ ] **Step 6: `lint-imports` final côté cœur**

Run: `cd core && uv run lint-imports`
Expected: PASS, zéro nouvelle exemption.

- [ ] **Step 7: Commit**

```bash
cd core && git add app/attachments/routes.py tests/test_attachments_guest_access_routes.py
git commit -m "feat(core): pièces jointes acceptent le jeton invité (GAP-19)"
```

---

## Task 8: `ShareLinkCreated` gagne `token`

**Files:**
- Modify: `core/app/sharing/schemas.py:22-24`
- Modify: `core/app/items/routes.py:263-297`
- Modify: `core/tests/test_share_links_routes.py`

**Interfaces:**
- Produces: `ShareLinkCreated{url: str, expiresAt: str, token: str}` —
  consommé par le shell (Task 10, `createShareLink`).

- [ ] **Step 1: Écrire le test**

```python
# core/tests/test_share_links_routes.py (ajouter en fin de fichier)
def test_create_share_link_response_includes_the_raw_token(client):
    response = client.post(f"/v1/items/{client.item_id}/share-links", json={"ttlDays": 7})
    body = response.json()
    assert body["token"]
    assert body["url"].endswith(f"/share-links/{body['token']}")
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd core && uv run pytest tests/test_share_links_routes.py::test_create_share_link_response_includes_the_raw_token -v`
Expected: FAIL avec `KeyError: 'token'`

- [ ] **Step 3: Ajouter le champ au schéma et le renseigner dans la route**

```python
# core/app/sharing/schemas.py — remplacer
class ShareLinkCreated(BaseModel):
    url: str
    expiresAt: str

# par
class ShareLinkCreated(BaseModel):
    url: str
    expiresAt: str
    token: str
```

```python
# core/app/items/routes.py — dans create_share_link_route, remplacer
    return ShareLinkCreated(
        url=f"{base_url}/v1/share-links/{token}", expiresAt=link.expires_at.isoformat()
    )

# par
    return ShareLinkCreated(
        url=f"{base_url}/v1/share-links/{token}",
        expiresAt=link.expires_at.isoformat(),
        token=token,
    )
```

- [ ] **Step 4: Relancer, vérifier le succès**

Run: `cd core && uv run pytest tests/test_share_links_routes.py -v`
Expected: tous PASS (le nouveau test + les existants inchangés)

- [ ] **Step 5: Commit**

```bash
cd core && git add app/sharing/schemas.py app/items/routes.py tests/test_share_links_routes.py
git commit -m "feat(core): ShareLinkCreated expose le jeton brut (GAP-19)"
```

---

## Task 9: régénération OpenAPI + types TS + gardes de qualité cœur

**Files:**
- Modify: `core/openapi.json`
- Modify: `shell/src/api/generated/core-schema.d.ts`

- [ ] **Step 1: Régénérer la spec OpenAPI**

Run:
```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
```
Expected: le fichier est réécrit.

- [ ] **Step 2: Vérifier le diff — au minimum `ShareLinkCreated.token` doit apparaître**

Run: `git diff --stat core/openapi.json && grep -c '"token"' core/openapi.json`
Expected: diff non vide. Vérifier EMPIRIQUEMENT (ne pas supposer, spec §5
critère 12) si les paramètres `X-Share-Link-Token`/`shareToken` des routes
des Tâches 3-7 apparaissent dans le document — `grep -c "X-Share-Link-Token" core/openapi.json`
et noter le résultat réel dans le message du commit de cette étape,
quel qu'il soit (présent ou absent selon comment FastAPI sérialise un
paramètre `Header` optionnel non documenté explicitement par un
`Query`/`Path`).

- [ ] **Step 3: Régénérer les types TS shell**

Run: `cd shell && npm run gen:api-types`
Expected: `src/api/generated/core-schema.d.ts` réécrit, diff non vide
(nouveau champ `token`).

- [ ] **Step 4: `ruff`/`lint-imports`/couverture cœur, portes de qualité complètes**

Run:
```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run lint-imports
uv run pytest
```
Expected: tout vert. Consigner le compte réel de tests passés/skippés/
échoués dans le message de commit (piège CLAUDE.md n°12 — ne jamais
recopier un compte d'une session précédente).

- [ ] **Step 5: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "chore(core,shell): régénère OpenAPI + types TS après GAP-19 (guest access)"
```

---

## Task 10: shell — transport du jeton invité (`base.ts`/`itemClient.ts`/`types.ts`)

**Files:**
- Modify: `shell/src/api/base.ts:117-130,171-183,185-200,258-274,355-368`
- Modify: `shell/src/api/itemClient.ts:29-56`
- Modify: `shell/src/api/types.ts` (`ItemClient.getShareLinkToken?`,
  `createShareLink` return type)
- Modify: `shell/src/api/domains/items.ts:221-227`
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces: `ItemClientBase.getShareLinkToken?: () => string | undefined`
  (nouveau champ optionnel) ; `createItemClient(opts: { coreUrl: string;
  getToken: () => string | undefined; getShareLinkToken?: () => string |
  undefined }): ItemClient` (signature étendue) ; `ItemClient.
  getShareLinkToken?(): string | undefined` ; `ItemClient.createShareLink
  (itemId, ttlDays): Promise<{ url: string; expiresAt: string; token:
  string }>` (type de retour étendu) — consommés par les Tâches 11-13.

- [ ] **Step 1: Écrire le test qui prouve que `request()` pose `X-Share-Link-Token` quand `getShareLinkToken` est fourni**

```ts
// shell/src/api/itemClient.test.ts (ajouter, après makeClient())
function makeClientWithShareToken(shareToken: string | undefined) {
  return createItemClient({
    coreUrl: "https://core.test",
    getToken: () => undefined,
    getShareLinkToken: () => shareToken,
  });
}

test("request() attaches X-Share-Link-Token but no Authorization when only a share token is set", async () => {
  let auth: string | null = null;
  let shareHeader: string | null = null;
  server.use(
    http.get("https://core.test/v1/items/it1", ({ request }) => {
      auth = request.headers.get("authorization");
      shareHeader = request.headers.get("x-share-link-token");
      return HttpResponse.json({
        pk: "it1", resourceType: "app", title: "T", abstract: "", owner: "o",
        thumbnailUrl: null, date: "", configId: "c1", isPublished: false,
        license: "", language: "fr", permissions: {},
      });
    }),
  );
  await makeClientWithShareToken("share-tok-1").getItem("it1");
  expect(auth).toBeNull();
  expect(shareHeader).toBe("share-tok-1");
});

test("request() attaches no X-Share-Link-Token when getShareLinkToken is absent", async () => {
  let shareHeader: string | null = "not-checked";
  server.use(
    http.get("https://core.test/v1/items", ({ request }) => {
      shareHeader = request.headers.get("x-share-link-token");
      return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 });
    }),
  );
  await makeClient("abc").listItems({});
  expect(shareHeader).toBeNull();
});

test("createShareLink returns the raw token alongside url/expiresAt", async () => {
  server.use(
    http.post("https://core.test/v1/items/it1/share-links", () =>
      HttpResponse.json({ url: "https://core.test/v1/share-links/tok-123", expiresAt: "2026-10-01", token: "tok-123" }),
    ),
  );
  const link = await makeClient("abc").createShareLink("it1", 7);
  expect(link.token).toBe("tok-123");
});
```

Vérifier avant d'écrire ce test la forme exacte attendue par `getItem`
(response JSON) contre `shell/src/api/domains/items.ts::getItem` — ajuster
les champs du mock si la forme diverge (piège CLAUDE.md n°3).

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "X-Share-Link-Token"`
Expected: FAIL — `createItemClient` ne connaît pas encore `getShareLinkToken`
(erreur TypeScript à la compilation vitest, ou header jamais posé).

- [ ] **Step 3: Étendre `ItemClientBase`/`createBase`/`request`/`fetchGeoJsonFeatures`**

```ts
// shell/src/api/base.ts — remplacer la définition de ItemClientBase (lignes 117-130) par :
export type ItemClientBase = {
  coreUrl: string;
  getToken: () => string | undefined;
  getShareLinkToken?: () => string | undefined;
  request<T>(method: string, path: string, body?: unknown): Promise<T>;
  resolveDataset(pk: string): Promise<ResolvedDataset>;
  datasetCache: Map<string, ResolvedDataset>;
  invalidateDatasetCache(pk?: string): void;
  fetchGeoJsonFeatures(url: string): Promise<DataRecord[]>;
  fetchCoreCollections(q?: string): Promise<LayerSource[]>;
  fetchExternalRasterSources(q?: string): Promise<LayerSource[]>;
  fetchHostedTileset3dSources(q?: string): Promise<LayerSource[]>;
  fetchHostedTerrain3dSources(q?: string): Promise<{ id: string; title: string }[]>;
};

// remplacer la signature de createBase (lignes 171-174) par :
export function createBase(opts: {
  coreUrl: string;
  getToken: () => string | undefined;
  getShareLinkToken?: () => string | undefined;
}): ItemClientBase {
  const coreUrl = `${opts.coreUrl}/v1`;
  const { getToken, getShareLinkToken } = opts;

  // remplacer le corps de request() (lignes 185-200) par :
  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const token = getToken();
    const shareToken = getShareLinkToken?.();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (shareToken) headers["X-Share-Link-Token"] = shareToken;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(`${coreUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status} ${method} ${path}`);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  // remplacer le corps de fetchGeoJsonFeatures() (lignes 258-274) par :
  async function fetchGeoJsonFeatures(url: string): Promise<DataRecord[]> {
    const token = getToken();
    const shareToken = getShareLinkToken?.();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (shareToken) headers["X-Share-Link-Token"] = shareToken;
    const res = await fetch(url, { headers });
    if (!res.ok) throw new Error(`Request failed: ${res.status} features`);
    const data = (await res.json()) as {
      features?: {
        id?: string | number;
        properties?: Record<string, unknown>;
        geometry?: unknown;
      }[];
    };
    return (data.features ?? []).map((f, i) => ({
      id: f.id ?? i,
      properties: f.properties ?? {},
      geometry: f.geometry,
    }));
  }

  // remplacer le return final (lignes 355-368) par :
  return {
    coreUrl,
    getToken,
    getShareLinkToken,
    request,
    resolveDataset,
    datasetCache,
    invalidateDatasetCache,
    fetchGeoJsonFeatures,
    fetchCoreCollections,
    fetchExternalRasterSources,
    fetchHostedTileset3dSources,
    fetchHostedTerrain3dSources,
  };
}
```

- [ ] **Step 4: Étendre `createItemClient` (`itemClient.ts`) pour relayer/exposer `getShareLinkToken`**

```ts
// shell/src/api/itemClient.ts — remplacer la signature (lignes 29-32) par :
export function createItemClient(opts: {
  coreUrl: string;
  getToken: () => string | undefined;
  getShareLinkToken?: () => string | undefined;
}): ItemClient {
  const base = createBase(opts);

  return {
    // ... spread inchangés ...
    getAuthToken: base.getToken,
    getCoreUrl: () => base.coreUrl,
    getShareLinkToken: base.getShareLinkToken,
  };
}
```

- [ ] **Step 5: Ajouter `getShareLinkToken?` à `ItemClient` (`types.ts`) et étendre `createShareLink`**

```ts
// shell/src/api/types.ts — juste après getCoreUrl?(): string; (ligne ~649), ajouter :
  // Optionnel : présent uniquement sur l'ItemClient construit par la page
  // d'embed (/embed/:token, GAP-19) — le jeton de lien de partage voyage sur
  // un en-tête dédié, jamais sur Authorization (cf. getAuthToken ci-dessus,
  // qui reste undefined dans ce cas). Absent sur tout ItemClient normal.
  getShareLinkToken?(): string | undefined;

// remplacer (ligne 472) :
  createShareLink(itemId: string, ttlDays: number): Promise<{ url: string; expiresAt: string }>;
// par :
  createShareLink(
    itemId: string,
    ttlDays: number,
  ): Promise<{ url: string; expiresAt: string; token: string }>;
```

```ts
// shell/src/api/domains/items.ts — remplacer (lignes 221-227) :
    async createShareLink(
      itemId: string,
      ttlDays: number,
    ): Promise<{ url: string; expiresAt: string }> {
      return request<{ url: string; expiresAt: string }>("POST", `/items/${itemId}/share-links`, {
        ttlDays,
      });
    },
// par :
    async createShareLink(
      itemId: string,
      ttlDays: number,
    ): Promise<{ url: string; expiresAt: string; token: string }> {
      return request<{ url: string; expiresAt: string; token: string }>(
        "POST",
        `/items/${itemId}/share-links`,
        { ttlDays },
      );
    },
```

- [ ] **Step 6: Relancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: tous PASS

- [ ] **Step 7: `tsc --noEmit` (le nouveau champ `token` doit être consommé partout où `createShareLink`/`ShareLinkCreated` sont utilisés, sinon erreur de type)**

Run: `cd shell && npx tsc --noEmit`
Expected: propre — si une erreur apparaît sur `ShareLinksPanel.tsx`
(`link.token` non lu, `Property 'token' is missing` improbable puisque
c'est un ajout, pas un retrait — mais vérifier tout de même), corriger au
Step suivant (Task 13) plutôt qu'ici : cette tâche ne touche pas encore
`ShareForm.tsx`.

- [ ] **Step 8: Commit**

```bash
cd shell && git add src/api/base.ts src/api/itemClient.ts src/api/types.ts src/api/domains/items.ts src/api/itemClient.test.ts
git commit -m "feat(shell): ItemClient transporte le jeton invité sur X-Share-Link-Token (GAP-19)"
```

---

## Task 11: shell — `MapView`/`mapWidget` transportent le jeton invité

**Files:**
- Modify: `shell/src/map/MapView.tsx:892-897,1003-1023,1099-1103,1356-1390`
- Modify: `shell/src/builder/widgets/mapWidget.tsx:358-359`
- Test: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `ItemClient.getShareLinkToken?` (Task 10).
- Produces: `MapView` accepte un prop optionnel `getShareLinkToken?: () =>
  string | undefined`.

- [ ] **Step 1: Écrire le test `transformRequest` avec `getShareLinkToken`**

```tsx
// shell/src/map/MapView.test.tsx (ajouter après le test "core collection tile requests carry the session bearer token", ligne ~1167)
test("core collection tile requests carry the share-link header when no auth token is set", () => {
  render(
    <MapView
      config={tiled({ geometryKind: "polygon" })}
      getAuthToken={() => undefined}
      getShareLinkToken={() => "share-tok"}
      getCoreUrl={() => "http://core.test"}
    />,
  );
  const t = mapInstances[0].opts.transformRequest!;
  expect(t("http://core.test/collections/communes/tiles/1/2/3.mvt")).toEqual({
    url: "http://core.test/collections/communes/tiles/1/2/3.mvt",
    headers: { "X-Share-Link-Token": "share-tok" },
  });
});

test("core collection tile requests never carry both Authorization and X-Share-Link-Token from a normal authenticated client", () => {
  render(
    <MapView
      config={tiled({ geometryKind: "polygon" })}
      getAuthToken={() => "tok"}
      getCoreUrl={() => "http://core.test"}
      // getShareLinkToken absent — client normal
    />,
  );
  const t = mapInstances[0].opts.transformRequest!;
  expect(t("http://core.test/collections/communes/tiles/1/2/3.mvt")).toEqual({
    url: "http://core.test/collections/communes/tiles/1/2/3.mvt",
    headers: { Authorization: "Bearer tok" },
  });
});
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t "share-link"`
Expected: FAIL — le prop `getShareLinkToken` n'existe pas encore sur
`MapView`, TypeScript refuse la compilation du test (ou le header n'est
jamais posé).

- [ ] **Step 3: Ajouter le prop et le fil jusqu'à `transformRequest` + le fetch manuel d'attachment**

```tsx
// shell/src/map/MapView.tsx — dans le type de props (près des lignes 892-897), ajouter :
    getAuthToken?: () => string | undefined;
    getCoreUrl?: () => string;
    getShareLinkToken?: () => string | undefined;

// dans la déstructuration des props (ligne ~920), ajouter :
    getAuthToken,
    getCoreUrl,
    getShareLinkToken,

// près des refs existantes (lignes 1003-1023), ajouter :
  const getShareLinkTokenRef = useRef(getShareLinkToken);
  useEffect(() => {
    getShareLinkTokenRef.current = getShareLinkToken;
  }, [getShareLinkToken]);

// dans transformRequest (lignes 1099-1103), remplacer :
      transformRequest: (url: string) => {
        const coreUrl = getCoreUrlRef.current?.();
        if (isHostedTilesetUrl(url, coreUrl) || isHostedCollectionUrl(url, coreUrl)) {
          const token = getAuthTokenRef.current?.();
          if (token) return { url, headers: { Authorization: `Bearer ${token}` } };
        }
        return { url };
      },
// par :
      transformRequest: (url: string) => {
        const coreUrl = getCoreUrlRef.current?.();
        if (isHostedTilesetUrl(url, coreUrl) || isHostedCollectionUrl(url, coreUrl)) {
          const token = getAuthTokenRef.current?.();
          if (token) return { url, headers: { Authorization: `Bearer ${token}` } };
          const shareToken = getShareLinkTokenRef.current?.();
          if (shareToken) return { url, headers: { "X-Share-Link-Token": shareToken } };
        }
        return { url };
      },
```

**Note d'implémentation** : le corps réel de `transformRequest` autour de
la ligne 1099 est probablement légèrement différent de cet extrait
minimal (cf. la lecture complète du fichier avant d'écrire cette étape) —
vérifier le code réel avant d'appliquer ce remplacement, et appliquer le
même principe (`Authorization` d'abord, sinon `X-Share-Link-Token`, jamais
les deux à la fois) plutôt que de copier-coller aveuglément ce snippet
(piège CLAUDE.md n°3).

```tsx
// shell/src/map/MapView.tsx — dans le fetch manuel d'attachment (lignes ~1356-1390), remplacer chaque occurrence de :
    const token = getAuthTokenRef.current?.();
    ...
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
// par :
    const token = getAuthTokenRef.current?.();
    const shareToken = getShareLinkTokenRef.current?.();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    else if (shareToken) headers["X-Share-Link-Token"] = shareToken;
    fetch(url, { headers })
```

- [ ] **Step 4: Câbler `mapWidget.tsx`**

```tsx
// shell/src/builder/widgets/mapWidget.tsx — remplacer (lignes 358-359) :
              getAuthToken={client.getAuthToken}
              getCoreUrl={client.getCoreUrl}
// par :
              getAuthToken={client.getAuthToken}
              getCoreUrl={client.getCoreUrl}
              getShareLinkToken={client.getShareLinkToken}
```

- [ ] **Step 5: Relancer, vérifier le succès**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: tous PASS (les deux nouveaux + les existants inchangés)

- [ ] **Step 6: `tsc --noEmit`**

Run: `cd shell && npx tsc --noEmit`
Expected: propre.

- [ ] **Step 7: Commit**

```bash
cd shell && git add src/map/MapView.tsx src/map/MapView.test.tsx src/builder/widgets/mapWidget.tsx
git commit -m "feat(shell): MapView transporte X-Share-Link-Token sur tuiles et attachments (GAP-19)"
```

---

## Task 12: shell — `EmbedPage.tsx` + route `/embed/:token`

**Files:**
- Create: `shell/src/pages/embed/resolveShareLink.ts`
- Create: `shell/src/pages/embed/resolveShareLink.test.ts`
- Create: `shell/src/pages/EmbedPage.tsx`
- Create: `shell/src/pages/EmbedPage.test.tsx`
- Modify: `shell/src/shell/routes.tsx:428-431`

**Interfaces:**
- Consumes: `createItemClient` (Task 10), `ItemClientProvider` (existant),
  `AppRenderer` (existant, `shell/src/builder/AppRenderer.tsx`),
  `registerBuiltinWidgets`/`registerCounterExampleWidget`/
  `registerCounterWcExampleWidget` (existant, `shell/src/builder/widgets`
  et `shell/src/builder/examples/*`), `useAppConfig` (existant,
  `shell/src/api/domains/apps.hooks.ts`), `loadConfig` (existant,
  `shell/src/config.ts`).
- Produces: route publique `/embed/:token`, composant `EmbedPage`.

- [ ] **Step 1: Écrire le test de `resolveShareLink` (petit helper de fetch public, sans `ItemClient`)**

```ts
// shell/src/pages/embed/resolveShareLink.test.ts
// SPDX-License-Identifier: Apache-2.0
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { resolveShareLink } from "./resolveShareLink";

test("resolveShareLink returns the resolved metadata on success", async () => {
  server.use(
    http.get("https://core.test/v1/share-links/tok-1", () =>
      HttpResponse.json({
        itemId: "app-1", title: "Mon App", resourceType: "app", expiresAt: "2026-10-01",
      }),
    ),
  );
  const resolved = await resolveShareLink("https://core.test", "tok-1");
  expect(resolved).toEqual({
    itemId: "app-1", title: "Mon App", resourceType: "app", expiresAt: "2026-10-01",
  });
});

test("resolveShareLink throws on a 401 (invalid or expired token)", async () => {
  server.use(
    http.get("https://core.test/v1/share-links/bad", () =>
      HttpResponse.json({ detail: "invalid or expired share link" }, { status: 401 }),
    ),
  );
  await expect(resolveShareLink("https://core.test", "bad")).rejects.toThrow();
});
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd shell && npx vitest run src/pages/embed/resolveShareLink.test.ts`
Expected: FAIL — le fichier `resolveShareLink.ts` n'existe pas encore.

- [ ] **Step 3: Implémenter `resolveShareLink`**

```ts
// shell/src/pages/embed/resolveShareLink.ts
// SPDX-License-Identifier: Apache-2.0
export type ResolvedShareLink = {
  itemId: string;
  title: string;
  resourceType: string;
  expiresAt: string;
};

// GET /share-links/{token} est une route PUBLIQUE (core/app/items/
// routes.py::resolve_share_link_route, SP-54, inchangée par GAP-19) : pas
// d'ItemClient/Authorization ici, un simple fetch nu suffit — c'est
// exactement ce que la page d'embed doit rester capable de faire sans
// dépendre d'aucun état d'authentification de l'onglet hôte.
export async function resolveShareLink(coreUrl: string, token: string): Promise<ResolvedShareLink> {
  const res = await fetch(`${coreUrl}/v1/share-links/${encodeURIComponent(token)}`);
  if (!res.ok) {
    throw new Error(`share link resolution failed: ${res.status}`);
  }
  return (await res.json()) as ResolvedShareLink;
}
```

- [ ] **Step 4: Relancer, vérifier le succès**

Run: `cd shell && npx vitest run src/pages/embed/resolveShareLink.test.ts`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/pages/embed/resolveShareLink.ts src/pages/embed/resolveShareLink.test.ts
git commit -m "feat(shell): resolveShareLink — résolution publique du lien pour l'embed (GAP-19)"
```

- [ ] **Step 6: Écrire le test de `EmbedPage`**

```tsx
// shell/src/pages/EmbedPage.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { EmbedPage } from "./EmbedPage";

function renderWithClient(token: string) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <EmbedPage token={token} />
    </QueryClientProvider>,
  );
}

test("shows an explicit message for a non app/dashboard resource type", async () => {
  server.use(
    http.get("https://core.test/v1/share-links/tok-map", () =>
      HttpResponse.json({ itemId: "map-1", title: "Carte", resourceType: "map", expiresAt: "2026-10-01" }),
    ),
  );
  renderWithClient("tok-map");
  expect(await screen.findByText(/ne peut pas être intégré/i)).toBeInTheDocument();
});

test("shows an explicit message for an invalid or expired token", async () => {
  server.use(
    http.get("https://core.test/v1/share-links/bad", () =>
      HttpResponse.json({ detail: "invalid or expired share link" }, { status: 401 }),
    ),
  );
  renderWithClient("bad");
  expect(await screen.findByText(/expiré ou révoqué/i)).toBeInTheDocument();
});

test("renders the App via AppRenderer for a valid app token, sending only the share-link header", async () => {
  let sawAuthorization = false;
  let sawShareHeader = false;
  server.use(
    http.get("https://core.test/v1/share-links/tok-app", () =>
      HttpResponse.json({ itemId: "app-1", title: "Mon App", resourceType: "app", expiresAt: "2026-10-01" }),
    ),
    http.get("https://core.test/v1/configs/by-item/app-1", ({ request }) => {
      sawAuthorization = request.headers.get("authorization") !== null;
      sawShareHeader = request.headers.get("x-share-link-token") === "tok-app";
      return HttpResponse.json({
        config: {
          kind: "app", theme: {}, dataSources: [], messages: [],
          layout: { type: "grid", items: [] },
        },
      });
    }),
  );
  renderWithClient("tok-app");
  await screen.findByText("Mon App", { exact: false }).catch(() => undefined);
  // AppRenderer lui-même n'affiche pas nécessairement le titre — l'assertion
  // qui compte est sur les en-têtes de la requête de config, vérifiés
  // ci-dessous après un court délai de résolution des requêtes.
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(sawAuthorization).toBe(false);
  expect(sawShareHeader).toBe(true);
});
```

Ce dernier test est délicat (attente asynchrone de deux requêtes en
cascade) — l'ajuster si nécessaire avec `waitFor` de Testing Library
plutôt qu'un `setTimeout` arbitraire, en vérifiant contre le patron déjà
utilisé par `shell/src/pages/AppRuntimePage.test.tsx` (s'il existe) avant
d'écrire la version finale — piège CLAUDE.md n°10 (un correctif de filet
de test se vérifie par falsification, jamais supposé correct).

- [ ] **Step 7: Lancer, constater l'échec**

Run: `cd shell && npx vitest run src/pages/EmbedPage.test.tsx`
Expected: FAIL — `EmbedPage` n'existe pas encore.

- [ ] **Step 8: Implémenter `EmbedPage`**

```tsx
// shell/src/pages/EmbedPage.tsx
// SPDX-License-Identifier: Apache-2.0
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { loadConfig } from "../config";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { useAppConfig } from "../api/domains/apps.hooks";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { registerCounterExampleWidget } from "../builder/examples/counterWidget";
import { registerCounterWcExampleWidget } from "../builder/examples/counterWidgetWc";
import { resolveShareLink } from "./embed/resolveShareLink";
import { t } from "../i18n";

registerBuiltinWidgets();
registerCounterExampleWidget();
registerCounterWcExampleWidget();

const runtimeEnv = (window as unknown as { __GEOSTUDIO_ENV__?: Record<string, string | undefined> })
  .__GEOSTUDIO_ENV__;
const embedConfig = loadConfig(
  import.meta.env as unknown as Record<string, string | undefined>,
  runtimeEnv,
);

const EMBEDDABLE_RESOURCE_TYPES = new Set(["app", "dashboard"]);

function EmbedApp({ itemId, token }: { itemId: string; token: string }) {
  const client = useMemo(
    () =>
      createItemClient({
        coreUrl: embedConfig.coreUrl,
        getToken: () => undefined,
        getShareLinkToken: () => token,
      }),
    [token],
  );
  return (
    <ItemClientProvider client={client}>
      <EmbedAppRenderer itemId={itemId} />
    </ItemClientProvider>
  );
}

function EmbedAppRenderer({ itemId }: { itemId: string }) {
  const query = useAppConfig(itemId, { mode: "runtime" });
  if (query.isLoading) {
    return <p role="status">{t("common.loading")}</p>;
  }
  if (query.isError || !query.data) {
    return (
      <p role="alert" className="text-sm text-red-600">
        {t("appRuntime.notFound")}
      </p>
    );
  }
  return (
    <div className="h-screen w-screen">
      <AppRenderer config={query.data} mode="runtime" />
    </div>
  );
}

export function EmbedPage({ token }: { token: string }) {
  const linkQuery = useQuery({
    queryKey: ["embed-share-link", token],
    queryFn: () => resolveShareLink(embedConfig.coreUrl, token),
    retry: false,
  });

  if (linkQuery.isLoading) {
    return <p role="status">{t("common.loading")}</p>;
  }
  if (linkQuery.isError || !linkQuery.data) {
    return (
      <p role="alert" className="p-4 text-sm text-red-600">
        {t("embed.linkExpiredOrRevoked")}
      </p>
    );
  }
  if (!EMBEDDABLE_RESOURCE_TYPES.has(linkQuery.data.resourceType)) {
    return (
      <p role="alert" className="p-4 text-sm text-red-600">
        {t("embed.notEmbeddable")}
      </p>
    );
  }
  return <EmbedApp itemId={linkQuery.data.itemId} token={token} />;
}
```

Ajouter les deux nouvelles clés i18n (`embed.linkExpiredOrRevoked` — texte
contenant « expiré ou révoqué », `embed.notEmbeddable` — texte contenant «
ne peut pas être intégré ») dans `shell/src/i18n/catalog.fr.ts`, à côté des
clés `appRuntime.*` existantes — suivre le format déjà utilisé pour ces
clés voisines (vérifier le fichier réel avant d'écrire les deux entrées,
ne pas deviner sa structure exacte).

- [ ] **Step 9: Relancer, vérifier le succès**

Run: `cd shell && npx vitest run src/pages/EmbedPage.test.tsx src/pages/embed/resolveShareLink.test.ts`
Expected: tous PASS. Si le 3ᵉ test de `EmbedPage.test.tsx` (assertions sur
les en-têtes) reste instable, le retravailler avec `waitFor` avant de
continuer — ne jamais le laisser flaky (piège CLAUDE.md n°10).

- [ ] **Step 10: Ajouter la route `/embed/:token` (publique, hors `<ProtectedLayout>`)**

```tsx
// shell/src/shell/routes.tsx — ajouter la fonction, à côté de SitePublicRoute/PublicItemRoute/DatasetRoute :
function EmbedRoute() {
  const { token } = useParams();
  return <EmbedPage token={token!} />;
}

// et la route elle-même, dans AppRoutes(), au même niveau que /sites/:slug
// (après </Route> de ProtectedLayout, ligne ~428) :
        <Route path="/apps/:pk/:pageId?" element={<AppRuntimeRoute />} />
        <Route path="/embed/:token" element={<EmbedRoute />} />
        <Route path="/sites/:slug" element={<SitePublicRoute />} />
```

Ajouter l'import `import { EmbedPage } from "../pages/EmbedPage";` en tête
de fichier, à côté des autres imports de pages (vérifier si `EmbedPage`
doit être en `lazy()` comme les autres routes de ce fichier depuis SP-60 —
lire l'en-tête du fichier avant cette étape : si toutes les pages sont déjà
en `React.lazy()`, suivre exactement le même patron plutôt que d'importer
`EmbedPage` de façon synchrone, ce qui romprait la convention établie par
SP-60 et gonflerait le chunk d'entrée — piège CLAUDE.md n°3).

- [ ] **Step 11: Vérifier manuellement que la route compile et se monte (test de fumée)**

Run: `cd shell && npx tsc --noEmit`
Expected: propre.

- [ ] **Step 12: Commit**

```bash
cd shell && git add src/pages/EmbedPage.tsx src/pages/EmbedPage.test.tsx src/shell/routes.tsx src/i18n/catalog.fr.ts
git commit -m "feat(shell): route publique /embed/:token (GAP-19)"
```

---

## Task 13: shell — section « Intégrer » dans `ShareForm.tsx`

**Files:**
- Modify: `shell/src/shell/ShareForm.tsx:24-121`
- Modify: `shell/src/shell/ShareForm.test.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`

**Interfaces:**
- Consumes: `useCreateShareLink` (existant, retourne désormais `{ url,
  expiresAt, token }` depuis Task 10).

- [ ] **Step 1: Écrire le test — le bloc « Intégrer » apparaît après création, avec le bon `src` d'iframe**

Vérifier d'abord la structure réelle de `shell/src/shell/ShareForm.test.tsx`
(fixtures, mocks `useCreateShareLink`) avant d'écrire ce test — l'ajuster à
la forme réelle plutôt que de la deviner. Squelette attendu :

```tsx
// shell/src/shell/ShareForm.test.tsx (ajouter un test, patron à aligner sur les tests existants du fichier)
test("shows an embed snippet with the shell origin after creating a share link", async () => {
  // ... rendu de ShareForm avec les mocks habituels du fichier, créer un
  // lien de partage (bouton "Créer un lien"), attendre lastCreatedUrl ...
  // Le mock de useCreateShareLink doit résoudre { url: "...", expiresAt: "...", token: "tok-42" }.
  expect(await screen.findByText(/tok-42/)).toBeInTheDocument();
  // ou, selon l'implémentation retenue au Step 3, vérifier la présence
  // littérale de "/embed/tok-42" dans le texte affiché.
});
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd shell && npx vitest run src/shell/ShareForm.test.tsx -t "embed snippet"`
Expected: FAIL — la section n'existe pas encore.

- [ ] **Step 3: Ajouter la section « Intégrer » à `ShareLinksPanel`**

```tsx
// shell/src/shell/ShareForm.tsx — dans ShareLinksPanel, après la ligne
// setLastCreatedUrl(link.url), garder aussi le token :
  const [lastCreatedUrl, setLastCreatedUrl] = useState<string | null>(null);
  const [lastCreatedToken, setLastCreatedToken] = useState<string | null>(null);

  async function handleCreate() {
    createLink.reset();
    setLastCreatedUrl(null);
    setLastCreatedToken(null);
    try {
      const link = await createLink.mutateAsync(ttlDays);
      setLastCreatedUrl(link.url);
      setLastCreatedToken(link.token);
    } catch {
      /* surfaced via createLink.isError */
    }
  }

  // ... et dans le JSX, après le bloc {lastCreatedUrl && (...)} existant, ajouter :
      {lastCreatedToken && (
        <div className="flex flex-col gap-1 border-t border-rule pt-2">
          <p className="text-xs font-medium text-ink-2">{t("shareForm.embedTitle")}</p>
          <textarea
            readOnly
            aria-label={t("shareForm.embedSnippetAria")}
            className="h-20 w-full rounded-md border border-rule bg-surface p-2 font-mono text-xs text-ink"
            value={`<iframe src="${window.location.origin}/embed/${lastCreatedToken}" width="100%" height="600" style="border:0" loading="lazy"></iframe>`}
          />
        </div>
      )}
```

Ajouter les deux clés i18n (`shareForm.embedTitle`, `shareForm.
embedSnippetAria`) à `shell/src/i18n/catalog.fr.ts`, à côté des clés
`shareForm.*` existantes (mêmes conventions que les entrées voisines,
vérifier le fichier réel avant d'écrire).

- [ ] **Step 4: Relancer, vérifier le succès**

Run: `cd shell && npx vitest run src/shell/ShareForm.test.tsx`
Expected: tous PASS

- [ ] **Step 5: `tsc --noEmit` + suite complète shell**

Run: `cd shell && npx tsc --noEmit && npm run test`
Expected: propre, aucune régression (compte de tests rejoué, jamais
recopié d'une session antérieure — piège CLAUDE.md n°12).

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/shell/ShareForm.tsx src/shell/ShareForm.test.tsx src/i18n/catalog.fr.ts
git commit -m "feat(shell): section Intégrer dans ShareForm (GAP-19)"
```

---

## Task 14: E2E Playwright — parcours d'embed complet + non-régression sécurité

**Files:**
- Create: `shell/e2e/embed.spec.ts`

**Interfaces:**
- Consumes: tout ce qui précède (Tâches 1-13), via une stack shell+cœur
  réelle (`VITE_AUTH_MODE=mock` ou équivalent E2E, patron des autres specs
  de `shell/e2e/`).

- [ ] **Step 1: Lire un spec E2E existant proche pour en reprendre la structure de mocks**

Avant d'écrire quoi que ce soit, ouvrir un spec E2E qui mocke déjà
`GET /configs/by-item/:id` et une route de collection (ex. celui qui
couvre `AppRuntimePage`) ainsi que `shell/e2e/mocks.ts` — piège CLAUDE.md
n°3/n°57b (SP-57b a montré que `mocks.ts` porte des routes en regex
littéral non couvertes par un remplacement naïf) : vérifier que toute URL
mockée dans ce nouveau spec respecte le préfixe `/v1/` réellement utilisé
par le shell (`createBase` ajoute déjà `/v1`, cf. Task 10) et le patron
`page.route(...)` déjà en usage dans ce dossier plutôt que d'inventer sa
propre convention.

- [ ] **Step 2: Écrire le spec E2E**

```ts
// shell/e2e/embed.spec.ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";

const TOKEN = "e2e-embed-token";

test("un jeton invité valide rend l'App sans jamais envoyer Authorization", async ({ page }) => {
  const requestsSeen: { url: string; hasAuth: boolean; hasShareHeader: boolean }[] = [];

  await page.route("**/v1/share-links/*", (route) =>
    route.fulfill({
      json: { itemId: "app-1", title: "App de démo", resourceType: "app", expiresAt: "2099-01-01" },
    }),
  );
  await page.route("**/v1/configs/by-item/app-1*", async (route) => {
    const headers = route.request().headers();
    requestsSeen.push({
      url: route.request().url(),
      hasAuth: "authorization" in headers,
      hasShareHeader: headers["x-share-link-token"] === TOKEN,
    });
    await route.fulfill({
      json: {
        config: {
          kind: "app",
          theme: {},
          dataSources: [
            { id: "ds1", type: "features", service: "core", layer: "incidents", query: {} },
          ],
          messages: [],
          layout: {
            type: "grid",
            items: [{ id: "w1", widget: "table", x: 0, y: 0, w: 4, h: 4, props: { dataSourceId: "ds1" } }],
          },
        },
      },
    });
  });
  await page.route("**/v1/collections/incidents/items*", async (route) => {
    const headers = route.request().headers();
    requestsSeen.push({
      url: route.request().url(),
      hasAuth: "authorization" in headers,
      hasShareHeader: headers["x-share-link-token"] === TOKEN,
    });
    await route.fulfill({
      json: { type: "FeatureCollection", features: [], numberMatched: 0, numberReturned: 0 },
    });
  });

  await page.goto(`/embed/${TOKEN}`);
  await expect(page.locator("body")).not.toContainText("Chargement");

  expect(requestsSeen.length).toBeGreaterThan(0);
  for (const seen of requestsSeen) {
    expect(seen.hasAuth).toBe(false);
    expect(seen.hasShareHeader).toBe(true);
  }
});

test("un lien vers un type non intégrable affiche un message explicite", async ({ page }) => {
  await page.route("**/v1/share-links/*", (route) =>
    route.fulfill({
      json: { itemId: "map-1", title: "Une carte", resourceType: "map", expiresAt: "2099-01-01" },
    }),
  );

  await page.goto(`/embed/${TOKEN}`);

  await expect(page.getByText(/ne peut pas être intégré/i)).toBeVisible();
});

test("un jeton invalide affiche un message explicite, jamais une page blanche", async ({ page }) => {
  await page.route("**/v1/share-links/*", (route) =>
    route.fulfill({ status: 401, json: { detail: "invalid or expired share link" } }),
  );

  await page.goto(`/embed/${TOKEN}`);

  await expect(page.getByText(/expiré ou révoqué/i)).toBeVisible();
});
```

- [ ] **Step 3: Lancer ce spec seul**

Run: `cd shell && npx playwright test e2e/embed.spec.ts`
Expected: 3 passed. Ajuster les sélecteurs/mocks au comportement réel
observé (le texte exact affiché par `t("common.loading")`, la forme exacte
de la réponse `configs/by-item` attendue par `getAppConfig` côté shell) —
ne jamais supposer qu'un mock « ressemble » à la vraie forme sans l'avoir
vérifié contre le code de `shell/src/api/domains/apps.ts::getAppConfig`
(déjà lu en préparant ce plan — la forme `{ config: { kind, theme,
dataSources, messages, pages, variables, layout, navigationMode,
interactions, printLayout } }` est la bonne, mais un widget "table" n'a
pas été vérifié ici : si son rendu échoue faute d'un mock de schéma de
collection, ajouter la route `GET /collections/incidents/schema` mockée de
la même façon).

- [ ] **Step 4: Lancer la suite E2E complète pour vérifier l'absence de régression**

Run: `cd shell && npm run e2e`
Expected: le compte affiché par CLAUDE.md avant ce plan, plus 3 (les
nouveaux tests de ce fichier) ; consigner le compte réel observé, jamais
supposé.

- [ ] **Step 5: Commit**

```bash
cd shell && git add e2e/embed.spec.ts
git commit -m "test(shell): E2E embed — jeton invité, non-embeddable, jeton invalide (GAP-19)"
```

---

## Final Verification (à faire après la Task 14, avant de clore le plan)

- [ ] `cd core && uv run pytest` — suite complète, compte réel consigné.
- [ ] `cd core && uv run ruff check . && uv run ruff format --check . && uv run lint-imports` — tous verts.
- [ ] `cd shell && npm run test` — suite complète, compte réel consigné.
- [ ] `cd shell && npm run lint && npm run format:check` — tous verts.
- [ ] `cd shell && npm run build` — propre, vérifier le seuil de taille de
      bundle (`.bundle-size-threshold`) toujours respecté (nouvelle route
      `/embed/:token` en `lazy()`, ne devrait pas grossir le chunk
      d'entrée si le Step 10 de la Task 12 a été suivi).
- [ ] `cd shell && npm run e2e` — suite complète, compte réel consigné.
- [ ] Diff `core/openapi.json`/`shell/src/api/generated/core-schema.d.ts`
      non vide et cohérent (Task 9), vérifié plutôt que supposé.
- [ ] Relire la spec (`docs/superpowers/specs/2026-09-06-gap19-embed-sdk-design.md`)
      §5 (critères d'acceptation) un par un et pointer, pour chacun, le
      test qui le prouve — noter tout écart trouvé pendant l'exécution
      (piège CLAUDE.md n°3), jamais corrigé silencieusement sans le
      documenter dans le message du commit correspondant ou dans une note
      de revue finale de branche.
