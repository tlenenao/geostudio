# SP-12c — Moteur de moissonnage + connecteur STAC externe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un admin déclare une source de moissonnage pointant un catalogue STAC externe ; le cœur la moissonne en job procrastinate et référence chaque Collection distante comme un item « externe » cherchable (mode `reference`, défaut) ou la copie en collection PostGIS locale via le pipeline d'ingestion SP-6 (mode `copy`) — un re-moissonnage met à jour sans jamais dupliquer.

**Architecture:** Nouveau module `core/app/harvest/` : `models.py` (ORM `HarvestSource`/`HarvestRecord`), `connectors/` (abstraction `HarvestConnector` + seule implémentation `StacConnector`, zéro I/O DB — HTTP uniquement), `repository.py` (CRUD + upsert idempotent via contrainte unique `(tenant_id, source_id, external_id)`), `service.py` (le moteur : fetch → upsert → marquage périmé), `routes.py` (CRUD admin-only `/harvest/sources*` + déclenchement), `jobs.py` (procrastinate : run manuel + balayage périodique). Réutilise `app.ingestion.importer.run_import` (mode copy), `app.items.repository` (mode reference), le patron admin CRUD audité de `app.extensions`. Surface shell minimale : page d'admin miroir de `CollectionsAdminPage`, badge « Externe » sur les items moissonnés.

**Tech Stack:** FastAPI, SQLAlchemy, `httpx` (déjà dépendance, déjà auto-instrumenté OTel), procrastinate (queue `harvest`), React/TanStack Query côté shell.

## Global Constraints

- **Un seul connecteur livré : `StacConnector` (`type="stac"`)**. L'abstraction `HarvestConnector` (Protocole : `type: str`, `supports_copy: bool`, `fetch(url) -> Iterable[HarvestedRecord]`) est dimensionnée pour les connecteurs futurs (ArcGIS FS, GetCapabilities, CSW, CKAN — SP-12d…g) mais aucun autre n'est écrit ici.
- **Zéro I/O DB dans un connecteur** — il ne parle qu'HTTP au distant et produit des `HarvestedRecord` (dataclass pure) ; l'écriture DB (upsert item/collection) est faite exclusivement par `service.py`.
- **Granularité Collection** : une STAC Collection distante = un item externe local (jamais l'Item STAC/feature). Descendre à la feature ferait exploser le catalogue pour un simple référencement.
- **Idempotence stricte** : contrainte d'unicité `(tenant_id, source_id, external_id)` sur `harvest_records`, vérifiée contre Postgres réel (non couvrable SQLite, même discipline que `uq_items_tenant_slug` SP-13a). Re-moissonner une source inchangée ne crée jamais de doublon ; une entité disparue est marquée `is_stale=true`, jamais supprimée.
- **Mode `reference` (défaut)** : crée/met à jour un `Item` de `resource_type="external"` (pas de migration de colonne, `resource_type` est un `String` libre — même pattern que `"site"` de SP-13a). `is_published`/`is_public` faux par défaut.
- **Mode `copy`** : route les items GeoJSON de la collection distante (`{items_url}`) vers `app.ingestion.importer.run_import` — copie l'**index interrogeable** (footprints + propriétés), jamais les octets d'assets raster. Un connecteur `supports_copy=False` refuse `mode="copy"` à la **création** de la source (400), jamais un échec silencieux au runtime. **Simplification assumée et documentée dans le code** (§Task 4) : un contenu déjà copié n'est jamais ré-importé lors des moissonnages suivants (seule la fraîcheur du mapping avance) — le pipeline SP-6 ne sait que créer une nouvelle collection, jamais mettre à jour le contenu d'une collection existante ; re-synchroniser le contenu est hors périmètre SP-12c.
- **Un item moissonné (mode reference) n'est jamais re-exporté** par STAC/DCAT (SP-12a/SP-12b, qui n'exportent que nos `collections`) — pas de blanchiment de catalogue tiers. En mode `copy`, la collection PostGIS produite est une vraie collection locale, légitimement exportable comme les autres.
- **Parsing STAC tolérant et borné** (`_MAX_CATALOG_DEPTH=5`, `_MAX_COLLECTIONS=500`, timeout HTTP 10s par requête) : un champ manquant se replie (titre ← id, bbox ← monde, keywords ← `[]`) plutôt que de faire tomber tout le moissonnage ; un catalogue distant cyclique/hostile ne bloque pas le worker (garde anti-cycle sur les URLs déjà visitées).
- **Toutes les routes `/harvest/*` sont admin-only** (`_require_admin`, 403 sinon), écritures **auditées** (`harvest_source.create`/`update`/`delete`/`run`, patron exact `app.extensions`).
- **Mode read-only/démo (SP-9)** : le middleware ASGI existant couvre gratuitement les routes de gestion (POST/PUT/PATCH/DELETE). Le **balayage périodique** et `run_harvest_task` doivent en plus court-circuiter explicitement via `is_read_only_mode()` (mutation hors requête HTTP, invisible au middleware) — une démo publique ne moissonne pas.
- **SSRF documenté, non mitigé au-delà de l'admin-only v0** : le worker fetch une URL fournie par l'admin. Mitigation v0 = admin-only (déjà de confiance) + bornes/timeouts. Allowlist d'egress différée à SP-12d, signalée en suivi dans ce plan, pas implémentée ici.
- **`app.harvest` inséré entre `app.public` et `app.ingestion`** dans le contrat `layered architecture` d'import-linter (peut importer `app.ingestion`, `app.items`, `app.collections`, `app.tenants`, `app.auth`, `app.audit`, `app.db` ; jamais l'inverse). `app.jobs` reste hors contrat (comme pour tout autre domaine).
- **`import_paths` de `app/jobs.py`** doit inclure `"app.harvest.jobs"` — sans quoi le worker réel ne connaît pas les tâches de moissonnage (leçon SP-7).
- **Pas de MCP** pour cette sous-phase (gestion admin humaine uniquement, pas d'outil agent) — cohérent avec le silence de la spec sur ce point.
- **Dérive OpenAPI** : `core/openapi.json` + `shell/src/api/generated/core-schema.d.ts` régénérés (le shell consomme réellement ces endpoints, contrairement à SP-12a/b).
- Chaque fichier source créé porte l'en-tête `# SPDX-License-Identifier: Apache-2.0` en première ligne.
- Commandes : `cd core && uv run pytest ...` ; lint de frontières : `cd core && uv run lint-imports` ; shell : `cd shell && npm run test -- <fichier>` / `npm run e2e` / `npm run build`.

---

## Fichiers créés / modifiés

**Cœur :**
- **Create** `core/app/harvest/__init__.py` — package vide.
- **Create** `core/app/harvest/models.py` — ORM `HarvestSource`, `HarvestRecord`.
- **Create** `core/app/harvest/connectors/__init__.py` — `get_connector(type) -> HarvestConnector`.
- **Create** `core/app/harvest/connectors/base.py` — `HarvestConnector` (Protocol), `HarvestedRecord` (dataclass).
- **Create** `core/app/harvest/connectors/stac.py` — `StacConnector`.
- **Create** `core/app/harvest/repository.py` — CRUD sources/records, `list_due_sources`, `mark_missing_as_stale`.
- **Create** `core/app/harvest/service.py` — `harvest_source(session, source)`, le moteur.
- **Create** `core/app/harvest/schemas.py` — `HarvestSourceCreate`/`Patch`.
- **Create** `core/app/harvest/routes.py` — routeur `/harvest/sources*`.
- **Create** `core/app/harvest/jobs.py` — `run_harvest_task`, `run_harvest_sweep_task` (périodique).
- **Create** `core/alembic/versions/0016_harvest.py` — migration `harvest_sources`/`harvest_records`.
- **Modify** `core/app/db.py` — enregistrer `app.harvest.models` dans `core_table_names()`.
- **Modify** `core/app/jobs.py` — `import_paths` += `"app.harvest.jobs"`.
- **Modify** `core/app/main.py` — monter `harvest_routes.router`.
- **Modify** `core/pyproject.toml` — `app.harvest` dans le contrat `layered architecture` + `ignore_imports`.
- **Create** `core/tests/test_harvest_models.py`, `test_harvest_stac_connector.py`, `test_harvest_repository.py`, `test_harvest_service.py`, `test_harvest_jobs.py`, `test_harvest_routes.py`.

**Shell :**
- **Modify** `shell/src/api/types.ts` — `ResourceType` += `"external"` ; `HarvestSource`, `HarvestSourceCreateInput`, `HarvestSourcePatchInput` ; `ItemClient` += 6 méthodes.
- **Modify** `shell/src/api/itemClient.ts` — implémentation des 6 méthodes.
- **Modify** `shell/src/api/hooks.ts` — `useHarvestSources`, `useCreateHarvestSource`, `useUpdateHarvestSource`, `useDeleteHarvestSource`, `useRunHarvestSource`.
- **Create** `shell/src/pages/HarvestSourcesAdminPage.tsx` + `.test.tsx`.
- **Create** `shell/src/shell/CreateHarvestSourceDialog.tsx`, `EditHarvestSourceDialog.tsx`.
- **Modify** `shell/src/shell/routes.tsx` — route `/admin/harvest`.
- **Modify** `shell/src/shell/AppLayout.tsx` — lien de nav « Moissonnage ».
- **Modify** `shell/src/ui/ItemCard.tsx` — badge « Externe ».
- **Create** `shell/e2e/harvest-stac.spec.ts`.

---

### Task 1: Modèle de données — `HarvestSource`/`HarvestRecord`

**Files:**
- Create: `core/app/harvest/__init__.py`
- Create: `core/app/harvest/models.py`
- Create: `core/alembic/versions/0016_harvest.py`
- Modify: `core/app/db.py:41-57` (`core_table_names`)
- Modify: `core/pyproject.toml:66-100` (import-linter)
- Test: `core/tests/test_harvest_models.py`

**Interfaces:**
- Produces: `app.harvest.models.HarvestSource` (`id, tenant_id, owner_id, type, url, mode, enabled, interval_minutes, last_run_at, last_status, last_error, created_at, updated_at`), `app.harvest.models.HarvestRecord` (`id, tenant_id, source_id, external_id, item_id, collection_id, content_hash, harvested_at, is_stale`), contrainte unique `uq_harvest_records_tenant_source_external` sur `(tenant_id, source_id, external_id)`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# core/tests/test_harvest_models.py
# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import inspect

from app.db import init_db, make_engine, make_session_factory
from app.harvest.models import HarvestRecord, HarvestSource
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_harvest_tables_are_created_by_init_db():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    table_names = set(inspect(engine).get_table_names())
    assert {"harvest_sources", "harvest_records"} <= table_names
    engine.dispose()


def test_harvest_source_and_record_round_trip():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        source = HarvestSource(
            id="src-1", tenant_id=tenant.id, owner_id=user.id, type="stac",
            url="https://example.com/stac", mode="reference", enabled=True,
            interval_minutes=60,
        )
        s.add(source)
        s.flush()
        record = HarvestRecord(
            id="rec-1", tenant_id=tenant.id, source_id=source.id,
            external_id="ext-1", item_id=None, collection_id=None,
        )
        s.add(record)
        s.commit()

        fetched = s.get(HarvestSource, "src-1")
        assert fetched.url == "https://example.com/stac"
        assert fetched.last_status is None
        fetched_record = s.get(HarvestRecord, "rec-1")
        assert fetched_record.source_id == "src-1"
        assert fetched_record.is_stale is False
    engine.dispose()
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_harvest_models.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'app.harvest'`

- [ ] **Step 3: Créer le package et les modèles**

```python
# core/app/harvest/__init__.py
# SPDX-License-Identifier: Apache-2.0
```

```python
# core/app/harvest/models.py
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class HarvestSource(Base):
    __tablename__ = "harvest_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False, default="reference")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class HarvestRecord(Base):
    __tablename__ = "harvest_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", "external_id",
            name="uq_harvest_records_tenant_source_external",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("harvest_sources.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    collection_id: Mapped[str | None] = mapped_column(ForeignKey("collections.id"), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    harvested_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

```python
# core/alembic/versions/0016_harvest.py
"""app.harvest — harvest_sources + harvest_records (SP-12c)

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "harvest_sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False, server_default="reference"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interval_minutes", sa.Integer(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_status", sa.String(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "harvest_records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "source_id", sa.String(),
            sa.ForeignKey("harvest_sources.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), sa.ForeignKey("items.id"), nullable=True),
        sa.Column("collection_id", sa.String(), sa.ForeignKey("collections.id"), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("harvested_at", sa.DateTime(), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "uq_harvest_records_tenant_source_external",
        "harvest_records",
        ["tenant_id", "source_id", "external_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_harvest_records_tenant_source_external", table_name="harvest_records")
    op.drop_table("harvest_records")
    op.drop_table("harvest_sources")
```

Modify `core/app/db.py` (`core_table_names`, ligne 47-55) :

```python
    from app.audit import models as audit_models  # noqa: F401
    from app.collections import models as collections_models  # noqa: F401
    from app.configs import models  # noqa: F401
    from app.extensions import models as extensions_models  # noqa: F401
    from app.harvest import models as harvest_models  # noqa: F401
    from app.ingestion import models as ingestion_models  # noqa: F401
    from app.items import models as items_models  # noqa: F401
    from app.sharing import models as sharing_models  # noqa: F401
    from app.tenants import models as tenants_models  # noqa: F401
    from app.users import models as users_models  # noqa: F401
```

Modify `core/pyproject.toml` — insérer `"app.harvest"` entre `"app.public"` et `"app.ingestion"` dans `layers`, et ajouter à `ignore_imports` :

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.harvest",
    "app.ingestion",
    "app.dcat",
    "app.stac",
    "app.features",
    "app.collections",
    "app.configs",
    "app.extensions",
    "app.items",
    "app.sharing",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
ignore_imports = [
    "app.db -> app.configs.models",
    "app.db -> app.collections.models",
    "app.db -> app.items.models",
    "app.db -> app.audit.models",
    "app.db -> app.tenants.models",
    "app.db -> app.users.models",
    "app.db -> app.sharing.models",
    "app.db -> app.ingestion.models",
    "app.db -> app.extensions.models",
    "app.db -> app.harvest.models",
]
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_harvest_models.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lancer le lint de frontières**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 6: Commit**

```bash
git add core/app/harvest/__init__.py core/app/harvest/models.py core/alembic/versions/0016_harvest.py core/app/db.py core/pyproject.toml core/tests/test_harvest_models.py
git commit -m "feat(core): harvest_sources/harvest_records ORM + migration (SP-12c)"
```

---

### Task 2: Connecteur STAC — `HarvestConnector`/`HarvestedRecord` + `StacConnector`

**Files:**
- Create: `core/app/harvest/connectors/__init__.py`
- Create: `core/app/harvest/connectors/base.py`
- Create: `core/app/harvest/connectors/stac.py`
- Test: `core/tests/test_harvest_stac_connector.py`

**Interfaces:**
- Consumes: rien (module autonome, HTTP only).
- Produces: `app.harvest.connectors.base.HarvestedRecord(external_id: str, title: str, abstract: str, keywords: list[str], bbox: list[float], external_url: str, items_url: str | None)`, `app.harvest.connectors.base.HarvestConnector` (Protocol : `type: str`, `supports_copy: bool`, `fetch(url: str) -> Iterable[HarvestedRecord]`), `app.harvest.connectors.stac.StacConnector` (`type="stac"`, `supports_copy=True`, constructeur `StacConnector(client: httpx.Client | None = None)`), `app.harvest.connectors.get_connector(source_type: str) -> HarvestConnector` (lève `ValueError` si type inconnu).

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# core/tests/test_harvest_stac_connector.py
# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest

from app.harvest.connectors import get_connector
from app.harvest.connectors.stac import StacConnector

API_COLLECTIONS = {
    "collections": [
        {
            "id": "buildings",
            "title": "Bâtiments",
            "description": "Empreintes de bâtiments",
            "keywords": ["bati", "urbain"],
            "extent": {"spatial": {"bbox": [[1.0, 45.0, 2.0, 46.0]]}},
            "links": [
                {"rel": "self", "href": "https://stac.example.com/collections/buildings"},
                {"rel": "items", "href": "https://stac.example.com/collections/buildings/items"},
            ],
        },
        {
            "id": "roads",
            # title/description/keywords/extent absents : tolérance §2.7.
            "links": [],
        },
    ],
}

CATALOG_ROOT = {
    "type": "Catalog",
    "id": "root",
    "links": [
        {"rel": "child", "href": "https://stac.example.com/child-collection.json"},
        {"rel": "child", "href": "https://stac.example.com/child-catalog.json"},
    ],
}

CHILD_COLLECTION = {
    "type": "Collection",
    "id": "parcels",
    "title": "Parcelles",
    "description": "Parcelles cadastrales",
    "keywords": ["cadastre"],
    "extent": {"spatial": {"bbox": [[3.0, 47.0, 4.0, 48.0]]}},
    "links": [
        {"rel": "self", "href": "https://stac.example.com/child-collection.json"},
        {"rel": "items", "href": "https://stac.example.com/child-collection/items"},
    ],
}

CHILD_CATALOG = {
    "type": "Catalog",
    "id": "sub",
    "links": [
        {"rel": "child", "href": "https://stac.example.com/grandchild-collection.json"},
    ],
}

GRANDCHILD_COLLECTION = {
    "type": "Collection",
    "id": "trails",
    "title": "Sentiers",
    "description": "Sentiers de randonnée",
    "links": [
        {"rel": "self", "href": "https://stac.example.com/grandchild-collection.json"},
        {"rel": "items", "href": "https://stac.example.com/grandchild-collection/items"},
    ],
}

CYCLIC_CATALOG = {
    "type": "Catalog",
    "id": "cyclic",
    "links": [{"rel": "child", "href": "https://stac.example.com/cyclic.json"}],
}


def _connector(handler) -> StacConnector:
    transport = httpx.MockTransport(handler)
    return StacConnector(client=httpx.Client(transport=transport))


def test_fetch_api_collections_endpoint_maps_all_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://stac.example.com/collections"
        return httpx.Response(200, json=API_COLLECTIONS)

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    assert len(records) == 2
    buildings = next(r for r in records if r.external_id == "buildings")
    assert buildings.title == "Bâtiments"
    assert buildings.abstract == "Empreintes de bâtiments"
    assert buildings.keywords == ["bati", "urbain"]
    assert buildings.bbox == [1.0, 45.0, 2.0, 46.0]
    assert buildings.external_url == "https://stac.example.com/collections/buildings"
    assert buildings.items_url == "https://stac.example.com/collections/buildings/items"


def test_fetch_tolerates_missing_optional_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=API_COLLECTIONS)

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    roads = next(r for r in records if r.external_id == "roads")
    assert roads.title == "roads"
    assert roads.abstract == ""
    assert roads.keywords == []
    assert roads.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert roads.items_url is None


def test_fetch_follows_static_catalog_child_links_recursively():
    docs = {
        "https://stac.example.com/catalog.json": CATALOG_ROOT,
        "https://stac.example.com/child-collection.json": CHILD_COLLECTION,
        "https://stac.example.com/child-catalog.json": CHILD_CATALOG,
        "https://stac.example.com/grandchild-collection.json": GRANDCHILD_COLLECTION,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=docs[str(request.url)])

    records = list(_connector(handler).fetch("https://stac.example.com/catalog.json"))
    assert {r.external_id for r in records} == {"parcels", "trails"}


def test_fetch_terminates_on_cyclic_catalog_links():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=CYCLIC_CATALOG)

    records = list(_connector(handler).fetch("https://stac.example.com/cyclic.json"))
    assert records == []


def test_fetch_caps_number_of_collections():
    many = {"collections": [
        {"id": f"c{i}", "title": f"C{i}", "links": []} for i in range(600)
    ]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=many)

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    assert len(records) == 500


def test_fetch_returns_empty_on_http_error_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    assert records == []


def test_get_connector_returns_stac_connector():
    connector = get_connector("stac")
    assert connector.type == "stac"
    assert connector.supports_copy is True


def test_get_connector_unknown_type_raises():
    with pytest.raises(ValueError):
        get_connector("arcgis-fs")
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_harvest_stac_connector.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'app.harvest.connectors'`

- [ ] **Step 3: Implémenter `base.py`, `stac.py`, `connectors/__init__.py`**

```python
# core/app/harvest/connectors/__init__.py
# SPDX-License-Identifier: Apache-2.0
```

```python
# core/app/harvest/connectors/base.py
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class HarvestedRecord:
    external_id: str
    title: str
    abstract: str
    keywords: list[str]
    bbox: list[float]
    external_url: str
    items_url: str | None


class HarvestConnector(Protocol):
    type: str
    supports_copy: bool

    def fetch(self, url: str) -> Iterable[HarvestedRecord]: ...
```

```python
# core/app/harvest/connectors/stac.py
# SPDX-License-Identifier: Apache-2.0
"""Connecteur STAC externe (SP-12c) — HTTP uniquement, zéro I/O DB. Parsing
tolérant et borné (§2.7 spec) : un catalogue distant malformé/cyclique/hostile
ne doit jamais faire tomber tout un moissonnage ni bloquer le worker."""
import logging
from collections.abc import Iterable
from urllib.parse import urljoin

import httpx

from app.harvest.connectors.base import HarvestedRecord

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_CATALOG_DEPTH = 5
_MAX_COLLECTIONS = 500
_WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]


class StacConnector:
    type = "stac"
    supports_copy = True

    def __init__(self, *, client: httpx.Client | None = None):
        self._client = client

    def fetch(self, url: str) -> Iterable[HarvestedRecord]:
        client = self._client or httpx.Client(timeout=_DEFAULT_TIMEOUT_SECONDS)
        owns_client = self._client is None
        records: list[HarvestedRecord] = []
        seen_docs: set[str] = set()
        try:
            self._walk(client, url, depth=0, records=records, seen_docs=seen_docs)
        finally:
            if owns_client:
                client.close()
        return records

    def _walk(self, client, url, *, depth, records, seen_docs) -> None:
        if len(records) >= _MAX_COLLECTIONS or url in seen_docs:
            return
        seen_docs.add(url)
        try:
            response = client.get(url, timeout=_DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            doc = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("stac harvest: échec de récupération de %s : %s", url, exc)
            return

        if isinstance(doc.get("collections"), list):
            for coll in doc["collections"]:
                if len(records) >= _MAX_COLLECTIONS:
                    return
                record = self._collection_to_record(coll, base_url=url)
                if record is not None:
                    records.append(record)
            return

        doc_type = doc.get("type")
        if doc_type == "Collection":
            record = self._collection_to_record(doc, base_url=url)
            if record is not None:
                records.append(record)
            return

        if doc_type == "Catalog":
            if depth >= _MAX_CATALOG_DEPTH:
                logger.warning("stac harvest: profondeur maximale atteinte à %s", url)
                return
            for link in doc.get("links", []) or []:
                if link.get("rel") != "child" or not link.get("href"):
                    continue
                child_url = urljoin(url, link["href"])
                self._walk(client, child_url, depth=depth + 1, records=records, seen_docs=seen_docs)
                if len(records) >= _MAX_COLLECTIONS:
                    return
            return
        # Type inconnu/absent : document ignoré silencieusement (tolérance §2.7).

    @staticmethod
    def _collection_to_record(coll: dict, *, base_url: str) -> HarvestedRecord | None:
        external_id = coll.get("id")
        if not external_id:
            return None
        title = coll.get("title") or str(external_id)
        abstract = coll.get("description") or ""
        keywords = list(coll.get("keywords") or [])

        bbox = _WORLD_BBOX
        extent = coll.get("extent")
        spatial = extent.get("spatial") if isinstance(extent, dict) else None
        bboxes = spatial.get("bbox") if isinstance(spatial, dict) else None
        if isinstance(bboxes, list) and bboxes and isinstance(bboxes[0], list) and len(bboxes[0]) >= 4:
            bbox = [float(v) for v in bboxes[0][:4]]

        self_href, items_href = None, None
        for link in coll.get("links", []) or []:
            rel, href = link.get("rel"), link.get("href")
            if not href:
                continue
            if rel == "self" and self_href is None:
                self_href = urljoin(base_url, href)
            if rel == "items" and items_href is None:
                items_href = urljoin(base_url, href)

        return HarvestedRecord(
            external_id=str(external_id), title=title, abstract=abstract,
            keywords=keywords, bbox=bbox, external_url=self_href or base_url,
            items_url=items_href,
        )
```

```python
# core/app/harvest/connectors/__init__.py (complété)
# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors.base import HarvestConnector
from app.harvest.connectors.stac import StacConnector

_REGISTRY: dict[str, HarvestConnector] = {"stac": StacConnector()}


def get_connector(source_type: str) -> HarvestConnector:
    connector = _REGISTRY.get(source_type)
    if connector is None:
        raise ValueError(f"unknown harvest connector type: {source_type!r}")
    return connector
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_harvest_stac_connector.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/connectors/ core/tests/test_harvest_stac_connector.py
git commit -m "feat(core): connecteur STAC externe tolérant/borné (SP-12c)"
```

---

### Task 3: Repository `harvest_sources`/`harvest_records`

**Files:**
- Create: `core/app/harvest/repository.py`
- Test: `core/tests/test_harvest_repository.py`

**Interfaces:**
- Consumes: `app.harvest.models.HarvestSource`, `HarvestRecord` (Task 1).
- Produces: `create_source(session, *, tenant_id, owner_id, type, url, mode, enabled, interval_minutes) -> HarvestSource`, `get_source(session, *, tenant_id, source_id) -> HarvestSource | None`, `list_sources(session, *, tenant_id) -> list[HarvestSource]`, `update_source(session, source, **fields) -> HarvestSource`, `delete_source(session, source) -> None`, `mark_running(session, *, tenant_id, source_id) -> None`, `get_record(session, *, tenant_id, source_id, external_id) -> HarvestRecord | None`, `create_record(session, *, tenant_id, source_id, external_id, item_id, collection_id, content_hash) -> HarvestRecord`, `update_record(session, record, **fields) -> HarvestRecord`, `mark_missing_as_stale(session, *, tenant_id, source_id, seen_external_ids: set[str]) -> None`, `list_due_sources(session) -> list[HarvestSource]`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# core/tests/test_harvest_repository.py
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import Base, init_db, make_engine, make_session_factory
from app.harvest import repository as repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant_and_user(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    return tenant, user


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE harvest_records, harvest_sources, items, users, tenants CASCADE"
        ))


@pytest.fixture()
def pg_tenant_and_user(pg_session):
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    return tenant, user


def test_create_get_list_source(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://stac.example.com/collections", mode="reference",
        enabled=True, interval_minutes=60,
    )
    fetched = repo.get_source(session, tenant_id=tenant.id, source_id=source.id)
    assert fetched.url == "https://stac.example.com/collections"
    assert [s.id for s in repo.list_sources(session, tenant_id=tenant.id)] == [source.id]


def test_get_source_cross_tenant_returns_none(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    assert repo.get_source(session, tenant_id="other-tenant", source_id=source.id) is None


def test_update_source_patches_fields(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    repo.update_source(session, source, url="https://b", enabled=False)
    assert source.url == "https://b"
    assert source.enabled is False


def test_delete_source_cascades_to_records(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="ext-1",
        item_id=None, collection_id=None, content_hash="h",
    )
    session.flush()
    repo.delete_source(session, source)
    session.flush()
    assert repo.get_source(session, tenant_id=tenant.id, source_id=source.id) is None
    from app.harvest.models import HarvestRecord
    assert session.query(HarvestRecord).count() == 0


def test_mark_running_sets_status(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    repo.mark_running(session, tenant_id=tenant.id, source_id=source.id)
    assert source.last_status == "running"


def test_mark_missing_as_stale_flags_unseen_records_only(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    seen = repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="keep",
        item_id=None, collection_id=None, content_hash="h1",
    )
    gone = repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="gone",
        item_id=None, collection_id=None, content_hash="h2",
    )
    session.flush()
    repo.mark_missing_as_stale(
        session, tenant_id=tenant.id, source_id=source.id, seen_external_ids={"keep"},
    )
    assert seen.is_stale is False
    assert gone.is_stale is True


def test_list_due_sources_includes_never_run_and_overdue_enabled_sources(session, tenant_and_user):
    tenant, user = tenant_and_user

    def make(url, *, enabled=True, interval_minutes=30, last_run_at=None):
        s = repo.create_source(
            session, tenant_id=tenant.id, owner_id=user.id, type="stac", url=url,
            mode="reference", enabled=enabled, interval_minutes=interval_minutes,
        )
        s.last_run_at = last_run_at
        return s

    never_run = make("https://a")
    overdue = make("https://b", last_run_at=datetime.now(timezone.utc) - timedelta(hours=1))
    fresh = make("https://c", last_run_at=datetime.now(timezone.utc))
    make("https://d", enabled=False, last_run_at=None)
    make("https://e", interval_minutes=None, last_run_at=None)
    session.flush()

    due_ids = {s.id for s in repo.list_due_sources(session)}
    assert due_ids == {never_run.id, overdue.id}
    assert fresh.id not in due_ids


@pytest.mark.postgis
def test_unique_constraint_rejects_duplicate_external_id_for_same_source(pg_session, pg_tenant_and_user):
    tenant, user = pg_tenant_and_user
    source = repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    pg_session.commit()
    repo.create_record(
        pg_session, tenant_id=tenant.id, source_id=source.id, external_id="dup",
        item_id=None, collection_id=None, content_hash="h",
    )
    pg_session.commit()
    with pytest.raises(IntegrityError):
        repo.create_record(
            pg_session, tenant_id=tenant.id, source_id=source.id, external_id="dup",
            item_id=None, collection_id=None, content_hash="h2",
        )
        pg_session.commit()
    pg_session.rollback()
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_harvest_repository.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'app.harvest.repository'`

- [ ] **Step 3: Implémenter `repository.py`**

```python
# core/app/harvest/repository.py
# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.harvest.models import HarvestRecord, HarvestSource


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_source(
    session: Session, *, tenant_id: str, owner_id: str, type: str, url: str,
    mode: str, enabled: bool, interval_minutes: int | None,
) -> HarvestSource:
    source = HarvestSource(
        id=uuid.uuid4().hex, tenant_id=tenant_id, owner_id=owner_id, type=type,
        url=url, mode=mode, enabled=enabled, interval_minutes=interval_minutes,
    )
    session.add(source)
    session.flush()
    return source


def get_source(session: Session, *, tenant_id: str, source_id: str) -> HarvestSource | None:
    return session.scalar(
        select(HarvestSource).where(
            HarvestSource.id == source_id, HarvestSource.tenant_id == tenant_id,
        )
    )


def list_sources(session: Session, *, tenant_id: str) -> list[HarvestSource]:
    return list(session.scalars(
        select(HarvestSource)
        .where(HarvestSource.tenant_id == tenant_id)
        .order_by(HarvestSource.created_at)
    ).all())


def update_source(session: Session, source: HarvestSource, **fields) -> HarvestSource:
    for key, value in fields.items():
        setattr(source, key, value)
    session.flush()
    return source


def delete_source(session: Session, source: HarvestSource) -> None:
    session.delete(source)
    session.flush()


def mark_running(session: Session, *, tenant_id: str, source_id: str) -> None:
    source = get_source(session, tenant_id=tenant_id, source_id=source_id)
    if source is None:
        return
    source.last_status = "running"
    session.flush()


def get_record(
    session: Session, *, tenant_id: str, source_id: str, external_id: str,
) -> HarvestRecord | None:
    return session.scalar(
        select(HarvestRecord).where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.source_id == source_id,
            HarvestRecord.external_id == external_id,
        )
    )


def create_record(
    session: Session, *, tenant_id: str, source_id: str, external_id: str,
    item_id: str | None, collection_id: str | None, content_hash: str | None,
) -> HarvestRecord:
    record = HarvestRecord(
        id=uuid.uuid4().hex, tenant_id=tenant_id, source_id=source_id,
        external_id=external_id, item_id=item_id, collection_id=collection_id,
        content_hash=content_hash,
    )
    session.add(record)
    session.flush()
    return record


def update_record(session: Session, record: HarvestRecord, **fields) -> HarvestRecord:
    for key, value in fields.items():
        setattr(record, key, value)
    session.flush()
    return record


def mark_missing_as_stale(
    session: Session, *, tenant_id: str, source_id: str, seen_external_ids: set[str],
) -> None:
    records = session.scalars(
        select(HarvestRecord).where(
            HarvestRecord.tenant_id == tenant_id, HarvestRecord.source_id == source_id,
        )
    ).all()
    for record in records:
        if record.external_id not in seen_external_ids and not record.is_stale:
            record.is_stale = True
    session.flush()


def list_due_sources(session: Session) -> list[HarvestSource]:
    now = _now()
    candidates = session.scalars(
        select(HarvestSource).where(
            HarvestSource.enabled.is_(True),
            HarvestSource.interval_minutes.is_not(None),
        )
    ).all()
    due = []
    for source in candidates:
        if source.last_run_at is None:
            due.append(source)
            continue
        threshold = source.last_run_at + timedelta(minutes=source.interval_minutes)
        if threshold <= now:
            due.append(source)
    return due
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_harvest_repository.py -v`
Expected: PASS (7 tests toujours-run + 1 `postgis` skippé sans `CORE_TEST_DATABASE_URL`)

- [ ] **Step 5 (si `CORE_TEST_DATABASE_URL` est disponible) : valider le test postgis réellement**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://... uv run pytest tests/test_harvest_repository.py -v`
Expected: PASS (8 tests, dont la contrainte unique vérifiée contre Postgres réel)

- [ ] **Step 6: Commit**

```bash
git add core/app/harvest/repository.py core/tests/test_harvest_repository.py
git commit -m "feat(core): CRUD harvest_sources/harvest_records + due-sources (SP-12c)"
```

---

### Task 4: Moteur (`service.py`) — upsert idempotent, modes reference/copy

**Files:**
- Create: `core/app/harvest/service.py`
- Test: `core/tests/test_harvest_service.py`

**Interfaces:**
- Consumes: `app.harvest.connectors.get_connector`, `app.harvest.connectors.base.HarvestedRecord`, `app.harvest.repository` (Task 3), `app.items.repository.create_item`/`update_item`, `app.ingestion.importer.run_import`.
- Produces: `harvest_source(session: Session, source: HarvestSource, *, items_fetcher: Callable[[str], bytes] = _default_items_fetcher) -> None` — ne lève jamais (toute erreur de fetch/import est capturée et se traduit par `source.last_status="error"`).

- [ ] **Step 1: Écrire les tests qui échouent (mode reference, SQLite)**

```python
# core/tests/test_harvest_service.py
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import Mock

import pytest
from sqlalchemy import text

from app.db import Base, init_db, make_engine, make_session_factory
from app.harvest import repository as harvest_repo
from app.harvest import service
from app.harvest.connectors.base import HarvestedRecord
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

RECORD_A = HarvestedRecord(
    external_id="buildings", title="Bâtiments", abstract="Empreintes",
    keywords=["bati"], bbox=[1.0, 45.0, 2.0, 46.0],
    external_url="https://stac.example.com/collections/buildings",
    items_url="https://stac.example.com/collections/buildings/items",
)
RECORD_B = HarvestedRecord(
    external_id="roads", title="Routes", abstract="", keywords=[],
    bbox=[-180.0, -90.0, 180.0, 90.0],
    external_url="https://stac.example.com/collections/roads", items_url=None,
)


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant_and_user(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    return tenant, user


def _fake_connector(records):
    connector = Mock()
    connector.fetch = Mock(return_value=records)
    return connector


def test_reference_mode_first_harvest_creates_external_items(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    monkeypatch.setattr(
        service, "get_connector", lambda t: _fake_connector([RECORD_A, RECORD_B]),
    )
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://stac.example.com/collections", mode="reference",
        enabled=True, interval_minutes=None,
    )
    service.harvest_source(session, source)

    assert source.last_status == "ok"
    assert source.last_run_at is not None
    rec_a = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="buildings")
    assert rec_a is not None
    item = items_repo.get_item(session, tenant_id=tenant.id, item_id=rec_a.item_id)
    assert item.resourceType == "external"
    assert item.title == "Bâtiments"
    assert item.keywords == ["bati"]
    assert item.isPublished is False


def test_reference_mode_reharvest_updates_without_duplicating(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A]))
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    service.harvest_source(session, source)
    first_item_id = harvest_repo.get_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="buildings"
    ).item_id

    updated = HarvestedRecord(
        external_id="buildings", title="Bâtiments (v2)", abstract="Empreintes",
        keywords=["bati"], bbox=RECORD_A.bbox, external_url=RECORD_A.external_url,
        items_url=RECORD_A.items_url,
    )
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([updated]))
    service.harvest_source(session, source)

    all_records = session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert all_records == 1
    rec = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="buildings")
    assert rec.item_id == first_item_id
    item = items_repo.get_item(session, tenant_id=tenant.id, item_id=first_item_id)
    assert item.title == "Bâtiments (v2)"


def test_missing_entity_is_marked_stale_not_deleted(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A, RECORD_B]))
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    service.harvest_source(session, source)

    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A]))
    service.harvest_source(session, source)

    stale = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="roads")
    assert stale.is_stale is True
    kept = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="buildings")
    assert kept.is_stale is False


def test_connector_fetch_failure_sets_error_status_without_raising(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user

    def _raise(t):
        connector = Mock()
        connector.fetch = Mock(side_effect=RuntimeError("boom"))
        return connector

    monkeypatch.setattr(service, "get_connector", _raise)
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    service.harvest_source(session, source)  # ne doit pas lever
    assert source.last_status == "error"
    assert "boom" in source.last_error
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_harvest_service.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'app.harvest.service'`

- [ ] **Step 3: Implémenter `service.py`**

```python
# core/app/harvest/service.py
# SPDX-License-Identifier: Apache-2.0
"""Le moteur de moissonnage (SP-12c) : fetch via le connecteur du type de la
source, puis upsert idempotent des HarvestedRecord contre harvest_records
(§2.3 spec — contrainte unique (tenant_id, source_id, external_id) garantit
l'absence de doublon même sur exécutions concurrentes). Ne lève jamais : toute
erreur de fetch termine la source en last_status="error", jamais un job
zombie (même philosophie que app.ingestion.tasks)."""
import hashlib
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.harvest import repository as harvest_repo
from app.harvest.connectors import get_connector
from app.harvest.connectors.base import HarvestedRecord
from app.harvest.models import HarvestSource
from app.ingestion.importer import run_import
from app.items import repository as items_repo

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _content_hash(rec: HarvestedRecord) -> str:
    raw = "|".join([
        rec.title, rec.abstract, ",".join(sorted(rec.keywords)),
        ",".join(f"{v:.6f}" for v in rec.bbox),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _default_items_fetcher(url: str) -> bytes:
    response = httpx.get(url, timeout=10.0)
    response.raise_for_status()
    return response.content


def harvest_source(
    session: Session, source: HarvestSource, *, items_fetcher=_default_items_fetcher,
) -> None:
    try:
        connector = get_connector(source.type)
        records = list(connector.fetch(source.url))
    except Exception as exc:
        logger.exception("harvest source %s: échec de récupération", source.id)
        source.last_status = "error"
        source.last_error = str(exc)[:500]
        session.flush()
        return

    seen_external_ids: set[str] = set()
    for rec in records:
        seen_external_ids.add(rec.external_id)
        digest = _content_hash(rec)
        existing = harvest_repo.get_record(
            session, tenant_id=source.tenant_id, source_id=source.id, external_id=rec.external_id,
        )
        if source.mode == "copy":
            _upsert_copy(session, source, rec, existing, digest, items_fetcher)
        else:
            _upsert_reference(session, source, rec, existing, digest)

    harvest_repo.mark_missing_as_stale(
        session, tenant_id=source.tenant_id, source_id=source.id, seen_external_ids=seen_external_ids,
    )
    source.last_run_at = _now()
    source.last_status = "ok"
    source.last_error = None
    session.flush()


def _upsert_reference(session, source, rec: HarvestedRecord, existing, digest: str) -> None:
    if existing is None:
        item = items_repo.create_item(
            session, tenant_id=source.tenant_id, owner_id=source.owner_id,
            resource_type="external", title=rec.title,
        )
        items_repo.update_item(
            session, tenant_id=source.tenant_id, item_id=item.id,
            title=None, abstract=rec.abstract, keywords=rec.keywords, is_published=None,
        )
        write_audit(
            session, tenant_id=source.tenant_id, actor_id=source.owner_id, actor_kind="user",
            action="harvest_record.create", object_type="item", object_id=item.id,
            payload={"sourceId": source.id, "externalId": rec.external_id},
        )
        harvest_repo.create_record(
            session, tenant_id=source.tenant_id, source_id=source.id, external_id=rec.external_id,
            item_id=item.id, collection_id=None, content_hash=digest,
        )
        return

    if existing.content_hash != digest:
        items_repo.update_item(
            session, tenant_id=source.tenant_id, item_id=existing.item_id,
            title=rec.title, abstract=rec.abstract, keywords=rec.keywords, is_published=None,
        )
    harvest_repo.update_record(session, existing, content_hash=digest, harvested_at=_now(), is_stale=False)


def _upsert_copy(session, source, rec: HarvestedRecord, existing, digest: str, items_fetcher) -> None:
    if existing is not None:
        # v0 : un contenu déjà copié n'est jamais ré-importé — le pipeline
        # SP-6 (run_import) ne sait que CRÉER une nouvelle collection, jamais
        # mettre à jour le contenu d'une collection existante. Seule la
        # fraîcheur du mapping avance, pour respecter "jamais de doublon"
        # sans reconstruire une synchronisation de contenu hors périmètre
        # SP-12c (cf. plan §Global Constraints).
        harvest_repo.update_record(session, existing, content_hash=digest, harvested_at=_now(), is_stale=False)
        return

    if rec.items_url is None:
        logger.warning(
            "harvest source %s: collection distante %s sans lien items, copie ignorée",
            source.id, rec.external_id,
        )
        return

    content = items_fetcher(rec.items_url)
    result = run_import(
        session, tenant_id=source.tenant_id, created_by=source.owner_id,
        filename="harvest.geojson", content=content, collection_title=rec.title,
        lat_field=None, lon_field=None,
    )
    write_audit(
        session, tenant_id=source.tenant_id, actor_id=source.owner_id, actor_kind="user",
        action="harvest_record.create", object_type="collection", object_id=result.collection_id,
        payload={"sourceId": source.id, "externalId": rec.external_id},
    )
    harvest_repo.create_record(
        session, tenant_id=source.tenant_id, source_id=source.id, external_id=rec.external_id,
        item_id=result.item_id, collection_id=result.collection_id, content_hash=digest,
    )
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_harvest_service.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Ajouter le test du mode `copy` (postgis) au même fichier**

Ajouter en fin de `core/tests/test_harvest_service.py` :

```python
GEOJSON_ITEMS = (
    b'{"type":"FeatureCollection","features":['
    b'{"type":"Feature","properties":{"nom":"A"},'
    b'"geometry":{"type":"Point","coordinates":[1.0,45.0]}}]}'
)


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE harvest_records, harvest_sources, items, configs, "
            "config_revisions, collections, audit_log, users, tenants CASCADE"
        ))


@pytest.fixture()
def pg_tenant_and_user(pg_session):
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    return tenant, user


@pytest.mark.postgis
def test_copy_mode_first_harvest_creates_local_collection(pg_session, pg_tenant_and_user, monkeypatch):
    tenant, user = pg_tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A]))
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    service.harvest_source(pg_session, source, items_fetcher=lambda url: GEOJSON_ITEMS)

    assert source.last_status == "ok"
    rec = harvest_repo.get_record(pg_session, tenant_id=tenant.id, source_id=source.id, external_id="buildings")
    assert rec.collection_id is not None
    assert rec.item_id is not None


@pytest.mark.postgis
def test_copy_mode_reharvest_does_not_reimport(pg_session, pg_tenant_and_user, monkeypatch):
    tenant, user = pg_tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A]))
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    fetch_calls = []

    def counting_fetcher(url):
        fetch_calls.append(url)
        return GEOJSON_ITEMS

    service.harvest_source(pg_session, source, items_fetcher=counting_fetcher)
    service.harvest_source(pg_session, source, items_fetcher=counting_fetcher)

    assert len(fetch_calls) == 1
    count = pg_session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 1
```

- [ ] **Step 6: Lancer les tests postgis (si `CORE_TEST_DATABASE_URL` disponible), vérifier qu'ils passent**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://... uv run pytest tests/test_harvest_service.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Commit**

```bash
git add core/app/harvest/service.py core/tests/test_harvest_service.py
git commit -m "feat(core): moteur de moissonnage — upsert idempotent, modes reference/copy (SP-12c)"
```

---

### Task 5: Jobs procrastinate — `run_harvest_task` + balayage périodique

**Files:**
- Create: `core/app/harvest/jobs.py`
- Modify: `core/app/jobs.py:59` (`import_paths`)
- Test: `core/tests/test_harvest_jobs.py`

**Interfaces:**
- Consumes: `app.harvest.repository` (Task 3), `app.harvest.service.harvest_source` (Task 4), `app.auth.dependency.is_read_only_mode`.
- Produces: `app.harvest.jobs.run_harvest_task` (tâche procrastinate `queue="harvest"`, params `source_id: str, tenant_id: str`), `app.harvest.jobs.run_harvest_sweep_task` (tâche périodique `cron="*/15 * * * *"`, param `timestamp: int`).

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# core/tests/test_harvest_jobs.py
# SPDX-License-Identifier: Apache-2.0
"""Bout en bout : run_harvest_task/run_harvest_sweep_task, connecteur
procrastinate remplacé par InMemoryConnector (même pattern que
test_ingestion_tasks.py) ; PostGIS réel pour les tables harvest_*/items."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from procrastinate import testing
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.harvest import jobs as harvest_jobs
from app.harvest import repository as harvest_repo
from app.harvest import service
from app.harvest.connectors.base import HarvestedRecord
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

RECORD = HarvestedRecord(
    external_id="buildings", title="Bâtiments", abstract="", keywords=[],
    bbox=[-180.0, -90.0, 180.0, 90.0], external_url="https://a", items_url=None,
)


@pytest.fixture()
def env(pg_engine, monkeypatch):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "false")
    in_memory = testing.InMemoryConnector()
    with harvest_jobs.app.replace_connector(in_memory) as app:
        yield app, Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE harvest_records, harvest_sources, items, configs, "
            "config_revisions, collections, audit_log, users, tenants CASCADE"
        ))


def test_run_harvest_task_harvests_a_reference_source(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(service, "get_connector", lambda t: Mock(fetch=Mock(return_value=[RECORD])))
    with Session() as s:
        source = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=user.id, type="stac", url="https://a",
            mode="reference", enabled=True, interval_minutes=None,
        )
        s.commit()
        source_id = source.id

    harvest_jobs.run_harvest_task.defer(source_id=source_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["harvest"])

    with Session() as s:
        fetched = harvest_repo.get_source(s, tenant_id=tenant.id, source_id=source_id)
        assert fetched.last_status == "ok"
        rec = harvest_repo.get_record(s, tenant_id=tenant.id, source_id=source_id, external_id="buildings")
        assert rec is not None


def test_run_harvest_task_missing_source_is_a_noop(env):
    app, Session, tenant, user = env
    harvest_jobs.run_harvest_task.defer(source_id="does-not-exist", tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["harvest"])  # ne doit pas lever


def test_run_harvest_task_short_circuits_in_read_only_mode(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(service, "get_connector", lambda t: Mock(fetch=Mock(return_value=[RECORD])))
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with Session() as s:
        source = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=user.id, type="stac", url="https://a",
            mode="reference", enabled=True, interval_minutes=None,
        )
        s.commit()
        source_id = source.id

    harvest_jobs.run_harvest_task.defer(source_id=source_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["harvest"])

    with Session() as s:
        fetched = harvest_repo.get_source(s, tenant_id=tenant.id, source_id=source_id)
        assert fetched.last_status is None  # jamais moissonné


def test_sweep_defers_due_sources_only(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(service, "get_connector", lambda t: Mock(fetch=Mock(return_value=[RECORD])))
    with Session() as s:
        due = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=user.id, type="stac", url="https://due",
            mode="reference", enabled=True, interval_minutes=30,
        )
        not_due = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=user.id, type="stac", url="https://not-due",
            mode="reference", enabled=True, interval_minutes=30,
        )
        not_due.last_run_at = datetime.now(timezone.utc)
        s.commit()
        due_id, not_due_id = due.id, not_due.id

    harvest_jobs.run_harvest_sweep_task.defer(timestamp=0)
    app.run_worker(wait=False, queues=["harvest"])

    with Session() as s:
        assert harvest_repo.get_source(s, tenant_id=tenant.id, source_id=due_id).last_status == "ok"
        assert harvest_repo.get_source(s, tenant_id=tenant.id, source_id=not_due_id).last_status is None


def test_sweep_short_circuits_in_read_only_mode(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(service, "get_connector", lambda t: Mock(fetch=Mock(return_value=[RECORD])))
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with Session() as s:
        due = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=user.id, type="stac", url="https://due",
            mode="reference", enabled=True, interval_minutes=30,
        )
        s.commit()
        due_id = due.id

    harvest_jobs.run_harvest_sweep_task.defer(timestamp=0)
    app.run_worker(wait=False, queues=["harvest"])

    with Session() as s:
        assert harvest_repo.get_source(s, tenant_id=tenant.id, source_id=due_id).last_status is None
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://... uv run pytest tests/test_harvest_jobs.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'app.harvest.jobs'`

- [ ] **Step 3: Implémenter `jobs.py`**

```python
# core/app/harvest/jobs.py
# SPDX-License-Identifier: Apache-2.0
"""Jobs procrastinate du moteur de moissonnage (SP-12c) — run manuel
(POST /harvest/sources/{id}/run) et balayage périodique des sources dues.
Tourne dans le worker partagé (docker-compose.yml, cf. app.jobs pour la
raison de import_paths). Court-circuite en mode lecture seule/démo (SP-9) :
mutation hors requête HTTP, invisible au middleware ASGI read_only_guard."""
import logging
import os

from app.auth.dependency import is_read_only_mode
from app.db import make_engine, make_session_factory, request_scoped_session
from app.harvest import repository as harvest_repo
from app.harvest import service
from app.jobs import app

logger = logging.getLogger(__name__)


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


@app.task(queue="harvest")
def run_harvest_task(source_id: str, tenant_id: str) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : moissonnage de la source %s ignoré", source_id)
        return
    session_factory = _session_factory()
    with request_scoped_session(session_factory) as session:
        harvest_repo.mark_running(session, tenant_id=tenant_id, source_id=source_id)
    with request_scoped_session(session_factory) as session:
        source = harvest_repo.get_source(session, tenant_id=tenant_id, source_id=source_id)
        if source is None:
            logger.error("harvest source %s introuvable (tenant %s)", source_id, tenant_id)
            return
        service.harvest_source(session, source)


@app.periodic(cron="*/15 * * * *")
@app.task(queue="harvest")
def run_harvest_sweep_task(timestamp: int) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : balayage de moissonnage ignoré")
        return
    session_factory = _session_factory()
    with request_scoped_session(session_factory) as session:
        due = harvest_repo.list_due_sources(session)
        for source in due:
            run_harvest_task.defer(source_id=source.id, tenant_id=source.tenant_id)
```

Modify `core/app/jobs.py` (ligne 59) :

```python
    import_paths=[
        "app.ingestion.tasks", "app.items.jobs", "app.collections.jobs",
        "app.cdc.jobs", "app.harvest.jobs",
    ],
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://... uv run pytest tests/test_harvest_jobs.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Lancer le test de régression `import_paths`**

Run: `cd core && uv run pytest tests/test_jobs.py -v`
Expected: PASS (le test `test_import_paths_registers_all_domain_tasks` couvre désormais aussi `app.harvest.jobs`)

- [ ] **Step 6: Commit**

```bash
git add core/app/harvest/jobs.py core/app/jobs.py core/tests/test_harvest_jobs.py
git commit -m "feat(core): jobs de moissonnage — run manuel + balayage périodique, fail-safe read-only (SP-12c)"
```

---

### Task 6: Routes REST `/harvest/sources*` + schemas

**Files:**
- Create: `core/app/harvest/schemas.py`
- Create: `core/app/harvest/routes.py`
- Test: `core/tests/test_harvest_routes.py`

**Interfaces:**
- Consumes: `app.harvest.repository` (Task 3), `app.harvest.connectors.get_connector` (Task 2), `app.harvest.jobs.run_harvest_task` (Task 5), `app.audit.writer.write_audit`, `app.auth.dependency.get_current_user`.
- Produces: `router` (`APIRouter`) exposant `POST /harvest/sources`, `GET /harvest/sources`, `GET /harvest/sources/{id}`, `PATCH /harvest/sources/{id}`, `DELETE /harvest/sources/{id}`, `POST /harvest/sources/{id}/run` ; réponse JSON `{id, type, url, mode, enabled, intervalMinutes, lastRunAt, lastStatus, lastError}`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# core/tests/test_harvest_routes.py
# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.models import Tenant
from app.users.repository import get_or_create_user

SOURCE_BODY = {
    "type": "stac", "url": "https://stac.example.com/collections",
    "mode": "reference", "enabled": True, "intervalMinutes": 60,
}


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.delenv("CORE_READ_ONLY_MODE", raising=False)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        from app.tenants.repository import get_or_create_default_tenant
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="r", username="regular",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, admin, regular


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_create_requires_admin(env):
    app, client, _, _admin, regular = env
    _as(app, regular)
    assert client.post("/harvest/sources", json=SOURCE_BODY).status_code == 403


def test_create_and_list(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post("/harvest/sources", json=SOURCE_BODY)
    assert r.status_code == 201
    assert r.json()["type"] == "stac"
    listed = client.get("/harvest/sources").json()["sources"]
    assert [s["url"] for s in listed] == ["https://stac.example.com/collections"]


def test_create_copy_mode_on_supporting_connector_succeeds(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    body = {**SOURCE_BODY, "mode": "copy"}
    assert client.post("/harvest/sources", json=body).status_code == 201


def test_create_copy_mode_on_unknown_type_is_422(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    body = {**SOURCE_BODY, "type": "arcgis-fs"}
    assert client.post("/harvest/sources", json=body).status_code == 422


def test_patch_requires_admin_and_toggles_enabled(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    created = client.post("/harvest/sources", json=SOURCE_BODY).json()
    _as(app, regular)
    assert client.patch(f"/harvest/sources/{created['id']}", json={"enabled": False}).status_code == 403
    _as(app, admin)
    r = client.patch(f"/harvest/sources/{created['id']}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_get_and_patch_cross_tenant_returns_404(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/harvest/sources", json=SOURCE_BODY).json()

    with Session() as s:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other", name="Other")
        s.add(other_tenant)
        s.flush()
        other_admin = get_or_create_user(
            s, tenant_id=other_tenant.id, oidc_sub="oa", username="other-admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()

    _as(app, other_admin)
    assert client.get(f"/harvest/sources/{created['id']}").status_code == 404
    assert client.patch(f"/harvest/sources/{created['id']}", json={"enabled": False}).status_code == 404


def test_delete_source(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    created = client.post("/harvest/sources", json=SOURCE_BODY).json()
    assert client.delete(f"/harvest/sources/{created['id']}").status_code == 204
    assert client.get("/harvest/sources").json()["sources"] == []


def test_run_defers_a_task_and_is_audited(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/harvest/sources", json=SOURCE_BODY).json()
    deferred = []
    from app.harvest import routes as harvest_routes

    def fake_deferrer():
        def deferrer(source_id, tenant_id):
            deferred.append((source_id, tenant_id))
        return deferrer

    app.dependency_overrides[harvest_routes.get_task_deferrer] = fake_deferrer
    r = client.post(f"/harvest/sources/{created['id']}/run")
    assert r.status_code == 202
    assert deferred == [(created["id"], admin.tenant_id)]

    from app.audit.models import AuditLog
    from sqlalchemy import select
    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    assert "harvest_source.create" in actions
    assert "harvest_source.run" in actions


def test_run_missing_source_is_404(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    assert client.post("/harvest/sources/does-not-exist/run").status_code == 404


def test_mutations_blocked_in_read_only_mode(env, monkeypatch):
    app, client, _, admin, _regular = env
    _as(app, admin)
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    assert client.post("/harvest/sources", json=SOURCE_BODY).status_code == 403
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_harvest_routes.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'app.harvest.routes'`

- [ ] **Step 3: Implémenter `schemas.py` et `routes.py`**

```python
# core/app/harvest/schemas.py
# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import BaseModel, Field


class HarvestSourceCreate(BaseModel):
    type: Literal["stac"]
    url: str = Field(min_length=1)
    mode: Literal["reference", "copy"] = "reference"
    enabled: bool = True
    intervalMinutes: int | None = Field(default=None, ge=1)


class HarvestSourcePatch(BaseModel):
    url: str | None = Field(default=None, min_length=1)
    mode: Literal["reference", "copy"] | None = None
    enabled: bool | None = None
    intervalMinutes: int | None = None
```

```python
# core/app/harvest/routes.py
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.harvest import repository as repo
from app.harvest.connectors import get_connector
from app.harvest.jobs import run_harvest_task
from app.harvest.schemas import HarvestSourceCreate, HarvestSourcePatch
from app.users.models import User

router = APIRouter()


def _require_admin(user) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


def _source_json(source) -> dict:
    return {
        "id": source.id, "type": source.type, "url": source.url, "mode": source.mode,
        "enabled": source.enabled, "intervalMinutes": source.interval_minutes,
        "lastRunAt": source.last_run_at.isoformat() if source.last_run_at else None,
        "lastStatus": source.last_status, "lastError": source.last_error,
    }


def _check_copy_support(type_: str, mode: str) -> None:
    if mode != "copy":
        return
    connector = get_connector(type_)
    if not connector.supports_copy:
        raise HTTPException(status_code=400, detail=f"connector {type_!r} does not support copy mode")


def get_task_deferrer():  # overridé en test
    def deferrer(source_id: str, tenant_id: str) -> None:
        run_harvest_task.defer(source_id=source_id, tenant_id=tenant_id)
    return deferrer


@router.post("/harvest/sources", status_code=201)
def create_source(
    body: HarvestSourceCreate,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    _check_copy_support(body.type, body.mode)
    source = repo.create_source(
        session, tenant_id=user.tenant_id, owner_id=user.id, type=body.type,
        url=body.url, mode=body.mode, enabled=body.enabled, interval_minutes=body.intervalMinutes,
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.create", object_type="harvest_source", object_id=source.id,
        payload={"type": source.type, "url": source.url},
    )
    return _source_json(source)


@router.get("/harvest/sources")
def list_sources(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    _require_admin(user)
    sources = repo.list_sources(session, tenant_id=user.tenant_id)
    return {"sources": [_source_json(s) for s in sources]}


@router.get("/harvest/sources/{source_id}")
def get_source(
    source_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    return _source_json(source)


@router.patch("/harvest/sources/{source_id}")
def patch_source(
    source_id: str, body: HarvestSourcePatch,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    fields = body.model_dump(exclude_unset=True)
    if "intervalMinutes" in fields:
        fields["interval_minutes"] = fields.pop("intervalMinutes")
    if fields.get("mode") == "copy":
        _check_copy_support(source.type, "copy")
    repo.update_source(session, source, **fields)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.update", object_type="harvest_source", object_id=source.id,
        payload={"fields": list(fields)},
    )
    return _source_json(source)


@router.delete("/harvest/sources/{source_id}", status_code=204)
def delete_source(
    source_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.delete", object_type="harvest_source", object_id=source.id, payload={},
    )
    repo.delete_source(session, source)


@router.post("/harvest/sources/{source_id}/run", status_code=202)
def run_source(
    source_id: str,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    defer_task=Depends(get_task_deferrer),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.run", object_type="harvest_source", object_id=source.id, payload={},
    )
    session.commit()
    defer_task(source.id, user.tenant_id)
    return {"status": "queued"}
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_harvest_routes.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/schemas.py core/app/harvest/routes.py core/tests/test_harvest_routes.py
git commit -m "feat(core): routes admin CRUD /harvest/sources* + déclenchement audité (SP-12c)"
```

---

### Task 7: Montage dans `main.py` + validation cœur complète + OpenAPI/types shell

**Files:**
- Modify: `core/app/main.py:14-90`
- Modify: `core/openapi.json` (régénéré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré)

**Interfaces:**
- Consumes: `app.harvest.routes.router` (Task 6).

- [ ] **Step 1: Monter le routeur**

Modify `core/app/main.py` — ajouter l'import (ordre alphabétique, ligne ~18) :

```python
from app.harvest import routes as harvest_routes
```

Et l'`include_router` (après `extensions_routes`, avant `features_routes`) :

```python
    app.include_router(configs_routes.router)
    app.include_router(extensions_routes.router)
    app.include_router(harvest_routes.router)
    app.include_router(instance_routes.router)
```

- [ ] **Step 2: Lancer la suite cœur complète**

Run: `cd core && uv run pytest`
Expected: tous les tests passent (SQLite ; les tests `postgis` skippent sans `CORE_TEST_DATABASE_URL`)

- [ ] **Step 3: Lancer le lint de frontières**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 4: Régénérer `openapi.json`**

Run: `cd core && uv run python scripts/export_openapi.py openapi.json`
Expected: fichier réécrit, contient les chemins `/harvest/sources` et `/harvest/sources/{source_id}`.

- [ ] **Step 5: Vérifier la présence des nouveaux chemins**

Run: `cd core && grep -c '"/harvest' openapi.json`
Expected: > 0

- [ ] **Step 6: Régénérer les types TypeScript du shell**

Run: `cd shell && npm run gen:api-types`
Expected: `src/api/generated/core-schema.d.ts` réécrit sans erreur `openapi-typescript`.

- [ ] **Step 7: Vérifier que le build shell reste vert**

Run: `cd shell && npm run build`
Expected: `tsc --noEmit` + `vite build` passent sans erreur

- [ ] **Step 8: Commit**

```bash
git add core/app/main.py core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): monter le routeur /harvest + régénérer OpenAPI/types (SP-12c)"
```

---

### Task 8: Shell — `ItemClient`/hooks/types pour les sources de moissonnage

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Test: `shell/src/api/hooks.test.tsx`

**Interfaces:**
- Produces: `HarvestSource`, `HarvestSourceCreateInput`, `HarvestSourcePatchInput` (types.ts) ; `ItemClient.listHarvestSources()`, `.createHarvestSource(input)`, `.getHarvestSource(id)`, `.updateHarvestSource(id, patch)`, `.deleteHarvestSource(id)`, `.runHarvestSource(id)` ; hooks `useHarvestSources`, `useCreateHarvestSource`, `useUpdateHarvestSource`, `useDeleteHarvestSource`, `useRunHarvestSource`.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `shell/src/api/hooks.test.tsx` (imports en tête, ligne 10, ajouter `useCreateHarvestSource, useHarvestSources, useRunHarvestSource` à la liste existante) :

```typescript
test("useHarvestSources returns the mapped sources", async () => {
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: [
          {
            id: "src-1", type: "stac", url: "https://stac.example.com/collections",
            mode: "reference", enabled: true, intervalMinutes: 60,
            lastRunAt: null, lastStatus: null, lastError: null,
          },
        ],
      }),
    ),
  );
  const { result } = renderHook(() => useHarvestSources(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.[0]?.url).toBe("https://stac.example.com/collections");
});

test("useCreateHarvestSource posts the input and invalidates the list", async () => {
  let posted: unknown;
  server.use(
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json({
        id: "src-2", type: "stac", url: "https://a", mode: "reference",
        enabled: true, intervalMinutes: null, lastRunAt: null, lastStatus: null, lastError: null,
      }, { status: 201 });
    }),
  );
  const { result } = renderHook(() => useCreateHarvestSource(), { wrapper });
  await result.current.mutateAsync({ type: "stac", url: "https://a", mode: "reference", enabled: true });
  expect(posted).toEqual({ type: "stac", url: "https://a", mode: "reference", enabled: true });
});

test("useRunHarvestSource posts to the run endpoint", async () => {
  let called = false;
  server.use(
    http.post("https://core.test/harvest/sources/src-1/run", () => {
      called = true;
      return HttpResponse.json({ status: "queued" }, { status: 202 });
    }),
  );
  const { result } = renderHook(() => useRunHarvestSource(), { wrapper });
  await result.current.mutateAsync("src-1");
  expect(called).toBe(true);
});
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd shell && npm run test -- hooks.test.tsx`
Expected: FAIL (`useHarvestSources`/`useCreateHarvestSource`/`useRunHarvestSource` n'existent pas)

- [ ] **Step 3: Ajouter les types**

Modify `shell/src/api/types.ts` (ligne 2) :

```typescript
export type ResourceType = "app" | "dashboard" | "map" | "site" | "external";
```

Ajouter après `CollectionPatchInput` (ligne ~257) :

```typescript
export type HarvestSourceType = "stac";
export type HarvestSourceMode = "reference" | "copy";
export type HarvestSourceStatus = "running" | "ok" | "error" | null;

export type HarvestSource = {
  id: string;
  type: HarvestSourceType;
  url: string;
  mode: HarvestSourceMode;
  enabled: boolean;
  intervalMinutes: number | null;
  lastRunAt: string | null;
  lastStatus: HarvestSourceStatus;
  lastError: string | null;
};

export type HarvestSourceCreateInput = {
  type: HarvestSourceType;
  url: string;
  mode: HarvestSourceMode;
  enabled: boolean;
  intervalMinutes?: number;
};

export type HarvestSourcePatchInput = {
  url?: string;
  mode?: HarvestSourceMode;
  enabled?: boolean;
  intervalMinutes?: number;
};
```

Ajouter à l'interface `ItemClient` (après `deleteCollection`, ligne ~125) :

```typescript
  listHarvestSources(): Promise<HarvestSource[]>;
  createHarvestSource(input: HarvestSourceCreateInput): Promise<HarvestSource>;
  updateHarvestSource(id: string, patch: HarvestSourcePatchInput): Promise<HarvestSource>;
  deleteHarvestSource(id: string): Promise<void>;
  runHarvestSource(id: string): Promise<void>;
```

- [ ] **Step 4: Implémenter dans `itemClient.ts`**

Modify `shell/src/api/itemClient.ts` (import ligne 2, ajouter `HarvestSource, HarvestSourceCreateInput, HarvestSourcePatchInput` à la liste) ; ajouter après `deleteCollection` (ligne ~383) :

```typescript
    async listHarvestSources(): Promise<HarvestSource[]> {
      const data = await request<{ sources: HarvestSource[] }>("GET", `/harvest/sources`);
      return data.sources ?? [];
    },

    async createHarvestSource(input: HarvestSourceCreateInput): Promise<HarvestSource> {
      return request<HarvestSource>("POST", `/harvest/sources`, input);
    },

    async updateHarvestSource(id: string, patch: HarvestSourcePatchInput): Promise<HarvestSource> {
      return request<HarvestSource>("PATCH", `/harvest/sources/${id}`, patch);
    },

    async deleteHarvestSource(id: string): Promise<void> {
      await request<void>("DELETE", `/harvest/sources/${id}`);
    },

    async runHarvestSource(id: string): Promise<void> {
      await request<void>("POST", `/harvest/sources/${id}/run`);
    },
```

- [ ] **Step 5: Ajouter les hooks**

Modify `shell/src/api/hooks.ts` — ajouter après `useDeleteCollection` (fin de fichier ou après le bloc collections) :

```typescript
export function useHarvestSources(options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["harvest-sources"],
    queryFn: () => client.listHarvestSources(),
    enabled: options?.enabled ?? true,
  });
}

export function useCreateHarvestSource() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: HarvestSourceCreateInput) => client.createHarvestSource(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
    },
  });
}

export function useUpdateHarvestSource(id: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: HarvestSourcePatchInput) => client.updateHarvestSource(id, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
    },
  });
}

export function useDeleteHarvestSource() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.deleteHarvestSource(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
    },
  });
}

export function useRunHarvestSource() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.runHarvestSource(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["harvest-sources"] });
    },
  });
}
```

Ajouter `HarvestSource, HarvestSourceCreateInput, HarvestSourcePatchInput` à l'import de types en tête de `hooks.ts` (ligne 4).

- [ ] **Step 6: Lancer le test, vérifier qu'il passe**

Run: `cd shell && npm run test -- hooks.test.tsx`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/hooks.ts shell/src/api/hooks.test.tsx
git commit -m "feat(shell): ItemClient/hooks pour les sources de moissonnage (SP-12c)"
```

---

### Task 9: Shell — page d'admin `/admin/harvest` + dialogues + navigation

**Files:**
- Create: `shell/src/shell/CreateHarvestSourceDialog.tsx`
- Create: `shell/src/shell/EditHarvestSourceDialog.tsx`
- Create: `shell/src/pages/HarvestSourcesAdminPage.tsx`
- Create: `shell/src/pages/HarvestSourcesAdminPage.test.tsx`
- Modify: `shell/src/shell/routes.tsx`
- Modify: `shell/src/shell/AppLayout.tsx`

**Interfaces:**
- Consumes: hooks de Task 8, `ConfirmDialog`, `Dialog`, `Button`, `Input` (composants `ui/` existants), `useMe`, `useInstanceInfo`.

- [ ] **Step 1: Écrire le test qui échoue**

```tsx
// shell/src/pages/HarvestSourcesAdminPage.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { HarvestSourcesAdminPage } from "./HarvestSourcesAdminPage";

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <HarvestSourcesAdminPage />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

function mockAdmin() {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
  );
}

test("shows an access-denied message and never calls /harvest/sources when not admin", async () => {
  let called = false;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false }),
    ),
    http.get("https://core.test/harvest/sources", () => {
      called = true;
      return HttpResponse.json({ sources: [] });
    }),
  );
  render(<Harness />);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux administrateurs."),
  );
  expect(called).toBe(false);
});

test("admin creates a STAC source and triggers a manual run", async () => {
  mockAdmin();
  let created: unknown = null;
  let ran = false;
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: created ? [{
          id: "src-1", type: "stac", url: "https://stac.example.com/collections",
          mode: "reference", enabled: true, intervalMinutes: null,
          lastRunAt: null, lastStatus: ran ? "ok" : null, lastError: null,
        }] : [],
      }),
    ),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      created = await request.json();
      return HttpResponse.json({
        id: "src-1", ...created, lastRunAt: null, lastStatus: null, lastError: null,
      }, { status: 201 });
    }),
    http.post("https://core.test/harvest/sources/src-1/run", () => {
      ran = true;
      return HttpResponse.json({ status: "queued" }, { status: 202 });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  const dialog = screen.getByRole("dialog", { name: "Ajouter une source" });
  await userEvent.type(dialog.querySelector("input[aria-label='URL']")!, "https://stac.example.com/collections");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer", exact: true }));
  await waitFor(() => expect(created).not.toBeNull());
  expect(await screen.findByText("https://stac.example.com/collections")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Moissonner maintenant" }));
  await waitFor(() => expect(ran).toBe(true));
});

test("delete removes the source from the list", async () => {
  mockAdmin();
  let deleted = false;
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: deleted ? [] : [{
          id: "src-1", type: "stac", url: "https://a", mode: "reference",
          enabled: true, intervalMinutes: null, lastRunAt: null, lastStatus: null, lastError: null,
        }],
      }),
    ),
    http.delete("https://core.test/harvest/sources/src-1", () => {
      deleted = true;
      return HttpResponse.text("", { status: 204 });
    }),
  );
  render(<Harness />);
  await screen.findByText("https://a");
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  // Le bouton de la ligne et celui du ConfirmDialog partagent le même nom
  // accessible une fois le dialogue ouvert — on scope au dialogue (même
  // patron que admin-collections.spec.ts).
  await userEvent.click(screen.getByRole("dialog").getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(deleted).toBe(true));
  await waitFor(() => expect(screen.queryByText("https://a")).not.toBeInTheDocument());
});
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd shell && npm run test -- HarvestSourcesAdminPage.test.tsx`
Expected: FAIL (module introuvable)

- [ ] **Step 3: Implémenter les dialogues**

```tsx
// shell/src/shell/CreateHarvestSourceDialog.tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCreateHarvestSource, useInstanceInfo } from "../api/hooks";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { Input } from "../ui/input";

export function CreateHarvestSourceDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const createSource = useCreateHarvestSource();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<"reference" | "copy">("reference");

  function close() {
    setUrl("");
    setMode("reference");
    createSource.reset();
    onClose();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!url) return;
    try {
      await createSource.mutateAsync({ type: "stac", url, mode, enabled: true });
      close();
    } catch {
      // surfaced via createSource.isError
    }
  }

  return (
    <Dialog open={open} onClose={close} title="Ajouter une source">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          URL
          <Input aria-label="URL" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Mode
          <select
            aria-label="Mode"
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
            value={mode}
            onChange={(e) => setMode(e.target.value as "reference" | "copy")}
          >
            <option value="reference">Référence</option>
            <option value="copy">Copie</option>
          </select>
        </label>
        {createSource.isError && (
          <p role="alert" className="text-sm text-red-600">
            Échec de la création.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={close}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={!url || createSource.isPending || readOnly}>
            Enregistrer
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
```

```tsx
// shell/src/shell/EditHarvestSourceDialog.tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useInstanceInfo, useUpdateHarvestSource } from "../api/hooks";
import type { HarvestSource } from "../api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { Input } from "../ui/input";

export function EditHarvestSourceDialog({
  source, open, onClose,
}: { source: HarvestSource; open: boolean; onClose: () => void }) {
  const updateSource = useUpdateHarvestSource(source.id);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [url, setUrl] = useState(source.url);
  const [enabled, setEnabled] = useState(source.enabled);

  useEffect(() => {
    if (!open) return;
    setUrl(source.url);
    setEnabled(source.enabled);
    updateSource.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, source]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateSource.mutateAsync({ url, enabled });
      onClose();
    } catch {
      // surfaced via updateSource.isError
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={`Éditer ${source.url}`}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          URL
          <Input aria-label="URL" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            aria-label="Actif"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Actif
        </label>
        {updateSource.isError && (
          <p role="alert" className="text-sm text-red-600">
            Échec de la mise à jour.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={updateSource.isPending || readOnly}>
            Enregistrer
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
```

- [ ] **Step 4: Implémenter la page**

```tsx
// shell/src/pages/HarvestSourcesAdminPage.tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useDeleteHarvestSource, useHarvestSources, useMe, useRunHarvestSource } from "../api/hooks";
import type { HarvestSource } from "../api/types";
import { Button } from "../ui/button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { CreateHarvestSourceDialog } from "../shell/CreateHarvestSourceDialog";
import { EditHarvestSourceDialog } from "../shell/EditHarvestSourceDialog";

export function HarvestSourcesAdminPage() {
  const meQuery = useMe();
  const sourcesQuery = useHarvestSources({ enabled: meQuery.data?.isAdmin === true });
  const deleteSource = useDeleteHarvestSource();
  const runSource = useRunHarvestSource();
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<HarvestSource | null>(null);
  const [deleting, setDeleting] = useState<HarvestSource | null>(null);

  if (meQuery.isLoading) {
    return <p role="status">Chargement…</p>;
  }
  if (meQuery.data?.isAdmin !== true) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Accès réservé aux administrateurs.
      </p>
    );
  }

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await deleteSource.mutateAsync(deleting.id);
      setDeleting(null);
    } catch {
      // surfaced via deleteSource.isError
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">Moissonnage</h1>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          Ajouter une source
        </Button>
      </div>
      {sourcesQuery.isLoading && <p role="status">Chargement…</p>}
      {sourcesQuery.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec du chargement des sources.
        </p>
      )}
      {deleteSource.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec de la suppression.
        </p>
      )}
      {sourcesQuery.data && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="py-2">Type</th>
              <th className="py-2">URL</th>
              <th className="py-2">Mode</th>
              <th className="py-2">Actif</th>
              <th className="py-2">Dernier statut</th>
              <th className="py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sourcesQuery.data.map((source) => (
              <tr key={source.id} className="border-b border-slate-100">
                <td className="py-2">{source.type}</td>
                <td className="py-2 text-xs text-slate-500">{source.url}</td>
                <td className="py-2">{source.mode}</td>
                <td className="py-2">{source.enabled ? "Oui" : "Non"}</td>
                <td className="py-2">{source.lastStatus ?? "—"}</td>
                <td className="py-2 flex gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={() => runSource.mutate(source.id)}>
                    Moissonner maintenant
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setEditing(source)}>
                    Éditer
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setDeleting(source)}>
                    Supprimer
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <CreateHarvestSourceDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      {editing && (
        <EditHarvestSourceDialog source={editing} open={true} onClose={() => setEditing(null)} />
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Supprimer la source"
        message={deleting ? `Supprimer la source « ${deleting.url} » ? Les items/collections déjà produits survivent.` : ""}
        confirmLabel="Supprimer"
        pending={deleteSource.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={confirmDelete}
      />
    </div>
  );
}
```

- [ ] **Step 5: Câbler la route et le lien de navigation**

Modify `shell/src/shell/routes.tsx` — import (ligne 12) :

```typescript
import { HarvestSourcesAdminPage } from "../pages/HarvestSourcesAdminPage";
```

Route (après `/admin/collections`, ligne 88) :

```tsx
        <Route path="/admin/harvest" element={<HarvestSourcesAdminPage />} />
```

Modify `shell/src/shell/AppLayout.tsx` (après le lien « Collections », ligne 44) :

```tsx
              <Link to="/admin/harvest" className="mt-1 block text-sm font-medium hover:underline">
                Moissonnage
              </Link>
```

- [ ] **Step 6: Lancer le test, vérifier qu'il passe**

Run: `cd shell && npm run test -- HarvestSourcesAdminPage.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 7: Lancer la suite shell complète + build**

Run: `cd shell && npm run test && npm run build`
Expected: tous les tests passent, build clean

- [ ] **Step 8: Commit**

```bash
git add shell/src/shell/CreateHarvestSourceDialog.tsx shell/src/shell/EditHarvestSourceDialog.tsx shell/src/pages/HarvestSourcesAdminPage.tsx shell/src/pages/HarvestSourcesAdminPage.test.tsx shell/src/shell/routes.tsx shell/src/shell/AppLayout.tsx
git commit -m "feat(shell): page admin /admin/harvest — CRUD sources + déclenchement manuel (SP-12c)"
```

---

### Task 10: Badge « Externe » dans le catalogue

**Files:**
- Modify: `shell/src/ui/ItemCard.tsx`
- Test: `shell/src/ui/ItemCard.test.tsx` (créer si absent, sinon compléter le fichier existant — vérifier avec `find shell/src/ui -iname "ItemCard.test.tsx"` avant d'écrire)

**Interfaces:**
- Consumes: `item.resourceType === "external"` (Task 8's `ResourceType` union).

- [ ] **Step 1: Écrire le test qui échoue**

```tsx
// shell/src/ui/ItemCard.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { ItemCard } from "./ItemCard";

const BASE_ITEM = {
  pk: "1", title: "Bâtiments", abstract: "", owner: "alice", thumbnailUrl: null,
  date: "2026-01-01", configId: null, isPublished: false,
} as const;

test("renders a French 'Externe' badge for resourceType external", () => {
  render(<ItemCard item={{ ...BASE_ITEM, resourceType: "external" }} onOpen={() => {}} />);
  expect(screen.getByText("Externe")).toBeInTheDocument();
});

test("renders the raw resourceType for other types", () => {
  render(<ItemCard item={{ ...BASE_ITEM, resourceType: "map" }} onOpen={() => {}} />);
  expect(screen.getByText("map")).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd shell && npm run test -- ItemCard.test.tsx`
Expected: FAIL (badge affiche `external` littéral au lieu de `Externe`)

- [ ] **Step 3: Ajouter le mapping de libellé**

Modify `shell/src/ui/ItemCard.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import type { Item, ResourceType } from "../api/types";
import { Button } from "./button";
import { Card } from "./card";

const RESOURCE_TYPE_LABELS: Partial<Record<ResourceType, string>> = {
  external: "Externe",
};

export function ItemCard({
  item,
  onOpen,
  actions,
}: {
  item: Item;
  onOpen: (pk: string, type: ResourceType) => void;
  actions?: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col gap-2 p-4">
      <div className="flex items-start justify-between">
        <span className="w-fit rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
          {RESOURCE_TYPE_LABELS[item.resourceType] ?? item.resourceType}
        </span>
        {actions}
      </div>
      {item.thumbnailUrl && (
        <img
          src={item.thumbnailUrl}
          alt={item.title}
          className="h-24 w-full rounded object-cover"
        />
      )}
      <h3 className="text-base font-semibold">{item.title}</h3>
      <p className="line-clamp-2 text-sm text-slate-500">{item.abstract}</p>
      <Button size="sm" className="mt-2 w-fit" onClick={() => onOpen(item.pk, item.resourceType)}>
        Ouvrir
      </Button>
    </Card>
  );
}
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd shell && npm run test -- ItemCard.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/ui/ItemCard.tsx shell/src/ui/ItemCard.test.tsx
git commit -m "feat(shell): badge « Externe » sur les items moissonnés du catalogue (SP-12c)"
```

---

### Task 11: E2E `harvest-stac.spec.ts` + vérification finale de branche

**Files:**
- Create: `shell/e2e/harvest-stac.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`shell/e2e/mocks.ts`), routes shell `/admin/harvest`.

- [ ] **Step 1: Écrire la spec E2E**

```typescript
// shell/e2e/harvest-stac.spec.ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un admin déclare une source STAC, la moissonne, et un re-moissonnage ne duplique pas", async ({ page }) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: true,
      },
    });
  });

  let created: unknown = null;
  let runCount = 0;
  let harvestedItem: Record<string, unknown> | null = null;

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1", type: "stac", url: "https://stac.example.com/collections",
          mode: "reference", enabled: true, intervalMinutes: null,
          lastRunAt: null, lastStatus: null, lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [{
              id: "src-1", type: "stac", url: "https://stac.example.com/collections",
              mode: "reference", enabled: true, intervalMinutes: null,
              lastRunAt: runCount > 0 ? "2026-07-19T10:00:00Z" : null,
              lastStatus: runCount > 0 ? "ok" : null, lastError: null,
            }]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedItem = {
      pk: "ext-1", resourceType: "external", title: "Bâtiments (STAC distant)",
      abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01",
      configId: null, isPublished: false,
    };
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  // Host-scoped: le shell a lui-même une route client "/items" (catalogue) —
  // un glob non scopé casserait la navigation (même rationale que
  // "/items/1"/"/items/9" ailleurs dans cette suite).
  await page.route("https://core.test/items*", async (route) => {
    const items = harvestedItem ? [harvestedItem] : [];
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.goto("/admin/harvest");
  await expect(page.getByRole("link", { name: "Moissonnage" })).toBeVisible();

  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill("https://stac.example.com/collections");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect.poll(() => created).toEqual({
    type: "stac", url: "https://stac.example.com/collections", mode: "reference", enabled: true,
  });
  await expect(page.getByText("https://stac.example.com/collections")).toBeVisible();

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Bâtiments (STAC distant)")).toBeVisible();
  await expect(page.getByText("Externe")).toBeVisible();

  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(2);
  await page.goto("/");
  await expect(page.getByText("Bâtiments (STAC distant)")).toHaveCount(1);
});
```

- [ ] **Step 2: Lancer la spec E2E seule**

Run: `cd shell && npx playwright test harvest-stac.spec.ts`
Expected: PASS (1 test)

- [ ] **Step 3: Lancer la suite E2E complète (non-régression)**

Run: `cd shell && npm run e2e`
Expected: 44/44 specs vertes (43 existantes + `harvest-stac.spec.ts`)

- [ ] **Step 4: Lancer la suite cœur complète**

Run: `cd core && uv run pytest`
Expected: tous les tests passent (SQLite) ; noter le compte final passed/skipped

- [ ] **Step 5 (si un PostGIS jetable est disponible) : validation empirique complète**

Run un conteneur PostGIS+pgvector jetable (`deploy/postgis/Dockerfile`, cf. notes SP-12 précédentes), puis :

```bash
cd core
CORE_TEST_DATABASE_URL=postgresql+psycopg://... uv run alembic upgrade head
CORE_TEST_DATABASE_URL=postgresql+psycopg://... uv run pytest -m postgis -v
```

Expected: migration 0016 s'applique proprement sur une base déjà à `0015` ; tous les tests `postgis` (dont la contrainte unique `harvest_records` et les jobs procrastinate) passent contre Postgres réel.

- [ ] **Step 6: Lancer le lint de frontières une dernière fois**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 7: Commit**

```bash
git add shell/e2e/harvest-stac.spec.ts
git commit -m "test(e2e): parcours admin → moissonnage STAC → item externe, re-moissonnage sans doublon (SP-12c)"
```

---

## Suivi hors périmètre (signalé, non implémenté ici)

- **SSRF/egress** : allowlist des plages loopback/link-local/privées, différée à SP-12d (§Global Constraints).
- **Miroir des octets d'assets** (COG rasters) en mode `copy` : hors périmètre, différé (bande passante/stockage/licences).
- **Re-synchronisation de contenu en mode `copy`** : un contenu déjà copié n'est jamais ré-importé aux moissonnages suivants (§Task 4) — limitation assumée du pipeline SP-6, à lever si un besoin réel apparaît.
- **Connecteurs ArcGIS FS/GetCapabilities/CSW/CKAN** : SP-12d…g, abstraction déjà dimensionnée.
- **Clic « Ouvrir » sur un item externe** dans le catalogue : navigue vers `/apps/{pk}/edit` par défaut (comportement générique d'`ItemCard`, pas de page dédiée) — la spec ne demande aucune surface d'édition pour un item externe ; à revisiter si ce parcours doit devenir utilisable.
