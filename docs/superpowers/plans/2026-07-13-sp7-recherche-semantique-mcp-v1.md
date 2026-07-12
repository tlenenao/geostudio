# SP-7 — Recherche sémantique + MCP v1 : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Le catalogue GeoStudio se cherche en langage naturel (pgvector + recherche hybride texte/vecteur) et un agent MCP peut chercher, lire des données géospatiales, et composer une application formulaire fonctionnelle sur une collection existante.

**Architecture:** Colonne `embedding vector(1536)` directe sur `items`/`collections`, calculée en job procrastinate asynchrone via un fournisseur enfichable. `list_items`/`list_collections` combinent trigram (`pg_trgm`) et vecteur (`pgvector`) par Reciprocal Rank Fusion, uniquement sur l'ensemble déjà filtré par les permissions — sur SQLite (tests rapides), le comportement `ILIKE` actuel reste inchangé, la voie hybride est Postgres-only (comme `get_extent_provider`/`get_feature_counter` déjà dans le code). Trois nouveaux outils MCP (`search_catalog`, `query_features`, `create_form_app`) suivent le patron des 7 outils v0 : mince adaptateur au-dessus des mêmes fonctions de repository, mêmes permissions, `actor_kind=agent` dans `audit_log`.

**Tech Stack:** Python/FastAPI/SQLAlchemy 2.0 (cœur), `pgvector` (extension Postgres + package Python `pgvector`), `pg_trgm`, `procrastinate` (jobs), React/TypeScript/Vitest/Playwright (shell), Alembic (migrations).

## Global Constraints

- `tenant_id` et `audit_log` sur toute écriture (CLAUDE.md) — chaque item/collection créé par un outil MCP passe par `write_audit` avec `actor_kind="agent"`.
- TDD systématique ; les 19 specs E2E existantes restent vertes.
- Commits conventional (`feat(core): …`, `feat(shell): …`), petits, un sujet.
- `ItemClient` (`shell/src/api/itemClient.ts`) reste le seul point de contact du shell avec le cœur.
- Frontières de modules du cœur outillées par `import-linter` (`core/pyproject.toml [tool.importlinter]`) : `app.items` ne peut jamais importer `app.collections`/`app.configs`/`app.ingestion`/`app.features`/`app.mcp` (couches au-dessus) ; les modules non listés dans `layers` (`app.db`, et les nouveaux `app.jobs`/`app.search`) sont hors contrat, importables depuis n'importe quelle couche — même patron que `app.db` aujourd'hui.
- Docs et messages utilisateur en français ; code/identifiants en anglais.
- Spec de référence : `docs/superpowers/specs/2026-07-13-sp7-recherche-semantique-mcp-v1-design.md`.

---

## Task 1: App procrastinate partagée (préalable aux jobs d'embedding)

Un seul `procrastinate.App` doit exister pour que le worker (un seul process, une seule commande `procrastinate --app ... worker`) connaisse à la fois les tâches d'ingestion (SP-6a) et les futures tâches d'embedding (Task 5, Task 7) — une tâche déférée via un `App` mais exécutée par le worker d'un *autre* `App` échoue (le nom de tâche n'est pas dans son registre). `app.ingestion.tasks` définit aujourd'hui son propre `procrastinate.App` ; ce n'est pas réutilisable tel quel par `app.items`/`app.collections` (couches inférieures à `app.ingestion` dans le contrat `import-linter` — `app.items` ne peut pas importer `app.ingestion`). On extrait donc l'instance partagée dans un module neuf, hors du contrat de couches (comme `app.db`).

**Files:**
- Create: `core/app/jobs.py`
- Modify: `core/app/ingestion/tasks.py:1-30` (retire `_conninfo`/`app =`, importe depuis `app.jobs`)
- Modify: `docker-compose.yml:130-132` (commande worker)
- Test: `core/tests/test_ingestion_tasks.py` (déjà existant — doit rester vert sans modification, preuve que le refactor est transparent)
- Test: `core/tests/test_jobs.py` (nouveau, un test minimal)

**Interfaces:**
- Produces: `app.jobs.app` — l'unique instance `procrastinate.App`, à importer par tout module `*.jobs` définissant une tâche (`from app.jobs import app`).

- [ ] **Step 1: Écrire le test qui prouve qu'une seule instance App existe et est partagée**

```python
# core/tests/test_jobs.py
"""Une seule instance procrastinate.App pour tout le process (Task 1, SP-7) —
sinon une tâche déférée par un module et exécutée par le worker d'un autre
App échoue (nom de tâche absent de son registre)."""
import procrastinate

from app import jobs
from app.ingestion import tasks as ingestion_tasks


def test_jobs_app_is_a_procrastinate_app():
    assert isinstance(jobs.app, procrastinate.App)


def test_ingestion_tasks_reuses_the_shared_app():
    assert ingestion_tasks.app is jobs.app
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.jobs'`

- [ ] **Step 3: Create `app/jobs.py` (App extrait tel quel depuis `app.ingestion.tasks`)**

```python
# core/app/jobs.py
"""Instance procrastinate.App partagée par tout le cœur — un seul worker
process (docker-compose.yml, service `worker`) exécute toutes les tâches de
tous les modules `*.jobs`/`*.tasks`, quel que soit le domaine qui les a
déférées. Module volontairement hors du contrat de couches import-linter
(comme app.db) : app.items et app.collections doivent pouvoir l'importer
sans que ce soit une violation de couche."""
import os

import procrastinate


def _conninfo() -> str:
    # .get() avec repli, jamais os.environ[...] : ce module est importé
    # transitivement par app.main dans toute la suite de tests, y compris
    # les tests SQLite qui ne définissent jamais DATABASE_URL — un KeyError
    # ici casserait la collecte pytest entière. Le repli n'est jamais
    # utilisé pour de vrai (le worker/cœur déployés reçoivent toujours
    # DATABASE_URL via docker-compose).
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost/geostudio_dev")
    return database_url.replace("postgresql+psycopg://", "postgresql://")


app = procrastinate.App(connector=procrastinate.SyncPsycopgConnector(conninfo=_conninfo()))
```

- [ ] **Step 4: Migrer `app/ingestion/tasks.py` pour réutiliser `app.jobs.app`**

Remplacer les lignes 1-30 de `core/app/ingestion/tasks.py` (imports + `_conninfo` + `app = procrastinate.App(...)`) par :

```python
"""Tâche procrastinate (SP-6a) : orchestre téléchargement S3 → pipeline
d'import (app.ingestion.importer.run_import) → mise à jour du statut du job.
Toute erreur (parsing ou inattendue) marque le job "error", jamais de job
bloqué en pending/running ("zombie", critère d'acceptation SP-6a).
L'instance procrastinate.App vit dans app.jobs (SP-7 Task 1) — partagée avec
les tâches d'embedding d'app.items/app.collections."""
import logging
import os

from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion import repository as ingestion_repo
from app.ingestion.importer import run_import
from app.ingestion.parsers import IngestionParseError
from app.ingestion.storage import download_object, make_s3_client
from app.jobs import app

logger = logging.getLogger(__name__)
```

(Le reste du fichier — `_make_s3_client_from_env`, `_uploads_bucket`, `@app.task(queue="ingestion") def run_ingestion_task(...)` — ne change pas : `app` référence maintenant `app.jobs.app` au lieu d'une instance locale.)

- [ ] **Step 5: Mettre à jour la commande worker dans `docker-compose.yml`**

```yaml
  worker:
    build: ./core
    command: >
      sh -c "procrastinate --app app.jobs.app schema --apply &&
             procrastinate --app app.jobs.app worker -q ingestion,search"
```

(Ajout de la queue `search`, utilisée par les tâches d'embedding des Task 5 et 7.)

- [ ] **Step 6: Run all tests to verify nothing broke**

Run: `cd core && uv run pytest tests/test_jobs.py tests/test_ingestion_tasks.py tests/test_ingestion_routes.py -v`
Expected: PASS (les tests `test_ingestion_tasks.py` sont marqués `postgis` — skippés sans `CORE_TEST_DATABASE_URL`, c'est normal ; ils ne doivent PAS échouer)

Run: `cd core && uv run pytest -q`
Expected: même nombre de passed/skipped qu'avant ce commit (aucune régression)

- [ ] **Step 7: Commit**

```bash
git add core/app/jobs.py core/app/ingestion/tasks.py docker-compose.yml core/tests/test_jobs.py
git commit -m "refactor(core): extraire l'App procrastinate partagée dans app.jobs (SP-7)"
```

---

## Task 2: Infra pgvector — image Postgres, migration, colonnes embedding

L'image Postgres actuelle (`postgis/postgis:16-3.4`, `docker-compose.yml:15`) ne fournit pas l'extension `vector` (pgvector). Il faut une image qui bundle PostGIS **et** pgvector — un `Dockerfile` maison au-dessus de l'image officielle (le paquet Debian `postgresql-16-pgvector` est disponible via le dépôt PGDG déjà configuré dans l'image `postgis/postgis`). Tous les tests `postgis` construisent leur schéma via `Base.metadata.create_all()` (pas `alembic upgrade head`, cf. `tests/test_ingestion_tasks.py`) — donc `tests/conftest.py` doit aussi créer les extensions, pas seulement la migration.

**Files:**
- Create: `deploy/postgis/Dockerfile`
- Modify: `docker-compose.yml:14-15` (`postgis` service : `image` → `build`)
- Modify: `core/tests/conftest.py:9-24` (créer les extensions dans `pg_engine`)
- Modify: `core/pyproject.toml:8-19` (dépendance `pgvector`)
- Modify: `core/Dockerfile:11-15` (dépendance `pgvector`)
- Create: `core/alembic/versions/0012_pgvector_embeddings.py`
- Modify: `core/app/items/models.py:1-28` (colonne `embedding`)
- Modify: `core/app/collections/models.py:1-33` (colonne `embedding`)
- Test: `core/tests/test_pgvector_infra.py` (nouveau, marqué `postgis`)

**Interfaces:**
- Produces: `Item.embedding: list[float] | None`, `Collection.embedding: list[float] | None` (colonnes ORM, type `pgvector.sqlalchemy.Vector(1536)`) — consommées par Task 5/6/7.

- [ ] **Step 1: Construire l'image Postgres+pgvector**

```dockerfile
# deploy/postgis/Dockerfile
# postgis/postgis:16-3.4 ne fournit pas pgvector — le dépôt PGDG (déjà
# configuré dans l'image officielle pour installer les paquets postgis) sert
# aussi le paquet Debian postgresql-16-pgvector (SP-7, recherche sémantique).
FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: Brancher l'image dans docker-compose et vérifier manuellement**

Dans `docker-compose.yml`, remplacer :

```yaml
  postgis:
    image: postgis/postgis:16-3.4
```

par :

```yaml
  postgis:
    build: ./deploy/postgis
```

Run: `docker compose build postgis && docker compose up -d postgis`
Attendre ~5s puis :
Run: `docker compose exec postgis psql -U gis -d gis -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm; SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm');"`
Expected: la requête retourne les deux lignes `vector` et `pg_trgm` sans erreur.

- [ ] **Step 3: Ajouter `pgvector` aux dépendances Python (pyproject + Dockerfile du cœur)**

Dans `core/pyproject.toml`, dans `[project] dependencies`, ajouter après `"pyproj>=3.6",` :

```toml
    "pgvector>=0.3",
```

Dans `core/Dockerfile`, dans la ligne `uv pip install --system --no-cache`, ajouter `"pgvector>=0.3"` à la liste.

Run: `cd core && uv sync`
Expected: `pgvector` apparaît dans `uv.lock`, aucune erreur.

- [ ] **Step 4: Étendre `tests/conftest.py` pour créer les extensions avant tout test `postgis`**

```python
# core/tests/conftest.py — remplacer le corps de pg_engine
@pytest.fixture(scope="session")
def pg_engine():
    url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("CORE_TEST_DATABASE_URL non défini — test postgis skippé")
    engine = create_engine(url)
    # Le rôle RLS et les extensions vector/pg_trgm existent dans la base de
    # test (idempotent) : les tests DDL (SP-3) et d'embedding (SP-7)
    # construisent leur schéma via Base.metadata.create_all(), jamais
    # `alembic upgrade head` — la migration seule ne suffit donc pas ici.
    with engine.begin() as conn:
        conn.execute(text(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gis_rls') "
            "THEN CREATE ROLE gis_rls NOLOGIN; END IF; END $$;"
        ))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    yield engine
    engine.dispose()
```

- [ ] **Step 5: Écrire le test qui prouve que les colonnes embedding existent et font un aller-retour**

```python
# core/tests/test_pgvector_infra.py
"""Colonnes embedding (SP-7 Task 2) : la colonne existe, un vecteur écrit se
relit identique, NULL par défaut (dégradation gracieuse tant que le job
d'embedding n'est pas passé — voir Task 5/7)."""
import pytest
from sqlalchemy import select

from app.collections.models import Collection
from app.db import Base, make_session_factory
from app.items.models import Item
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("TRUNCATE items, collections, users, tenants CASCADE"))


def test_item_embedding_defaults_to_null(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    item = Item(
        id="i1", tenant_id=tenant.id, owner_id=user.id,
        resource_type="app", title="X",
    )
    session.add(item)
    session.flush()
    assert session.scalar(select(Item.embedding).where(Item.id == "i1")) is None


def test_item_embedding_roundtrips(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    item = Item(
        id="i2", tenant_id=tenant.id, owner_id=user.id,
        resource_type="app", title="X",
    )
    session.add(item)
    session.flush()
    vector = [0.1] * 1536
    item.embedding = vector
    session.flush()
    session.expire(item)
    reloaded = session.get(Item, "i2")
    assert reloaded.embedding == pytest.approx(vector)


def test_collection_embedding_roundtrips(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    col = Collection(
        id="c1", tenant_id=tenant.id, owner_id=user.id, table_name="c1",
        title="Collection", pk_column="id",
    )
    session.add(col)
    session.flush()
    vector = [0.2] * 1536
    col.embedding = vector
    session.flush()
    session.expire(col)
    reloaded = session.get(Collection, "c1")
    assert reloaded.embedding == pytest.approx(vector)
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_pgvector_infra.py -v -m postgis`
Expected: FAIL — `AttributeError: 'Item' object has no attribute 'embedding'`

- [ ] **Step 7: Ajouter la colonne `embedding` aux modèles**

Dans `core/app/items/models.py`, ajouter l'import et la colonne :

```python
from pgvector.sqlalchemy import Vector
```

```python
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
```
(ajoutée après `keywords`)

Dans `core/app/collections/models.py`, même import, colonne ajoutée après `feature_count`:

```python
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_pgvector_infra.py -v -m postgis`
Expected: PASS (3 tests)

Run: `cd core && uv run pytest -q`
Expected: aucune régression sur le reste de la suite (SQLite continue de créer la colonne sans erreur — `Vector.get_col_spec()` n'a pas de dépendance au dialecte)

- [ ] **Step 9: Écrire la migration Alembic 0012**

```python
# core/alembic/versions/0012_pgvector_embeddings.py
"""pgvector (SP-7) — extensions vector/pg_trgm, colonne embedding sur
items/collections, index de recherche (GIN trigram, ivfflat cosine).

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-13
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column("items", sa.Column("embedding", Vector(1536), nullable=True))
    op.add_column("collections", sa.Column("embedding", Vector(1536), nullable=True))

    op.execute(
        "CREATE INDEX ix_items_trgm ON items "
        "USING gin ((title || ' ' || abstract) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_collections_trgm ON collections "
        "USING gin ((title || ' ' || description) gin_trgm_ops)"
    )
    # ivfflat sur une table possiblement vide au moment de la migration :
    # accepté (index sous-optimal jusqu'au premier ANALYZE avec des lignes),
    # pas de VACUUM/reindex piloté en v1 (spec §Hors périmètre).
    op.execute(
        "CREATE INDEX ix_items_embedding ON items "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX ix_collections_embedding ON collections "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_items_embedding")
    op.execute("DROP INDEX IF EXISTS ix_collections_embedding")
    op.execute("DROP INDEX IF EXISTS ix_items_trgm")
    op.execute("DROP INDEX IF EXISTS ix_collections_trgm")
    op.drop_column("collections", "embedding")
    op.drop_column("items", "embedding")
```

- [ ] **Step 10: Vérifier la migration contre un Postgres jetable réel**

Récupérer le tag construit au Step 2 :
Run: `docker images --filter "reference=*postgis*" --format "{{.Repository}}:{{.Tag}}"`
Note le tag (ex. `geostudio-postgis` ou `geostudio_postgis` selon le nom du
projet compose) et l'utiliser ci-dessous à la place de `<POSTGIS_IMAGE>` :

```bash
docker run --rm -d --name sp7-pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_USER=gis -e POSTGRES_DB=gis -p 5433:5432 <POSTGIS_IMAGE>
sleep 3
cd core && DATABASE_URL=postgresql+psycopg://gis:test@localhost:5433/gis uv run alembic upgrade head
docker exec sp7-pg-test psql -U gis -d gis -c "\d items" | grep embedding
docker exec sp7-pg-test psql -U gis -d gis -c "\d collections" | grep embedding
docker stop sp7-pg-test
```
Expected: `alembic upgrade head` réussit sans erreur, `embedding` apparaît de type `vector(1536)` dans les deux `\d`.

- [ ] **Step 11: Commit**

```bash
git add deploy/postgis/Dockerfile docker-compose.yml core/tests/conftest.py \
  core/pyproject.toml core/uv.lock core/Dockerfile \
  core/alembic/versions/0012_pgvector_embeddings.py \
  core/app/items/models.py core/app/collections/models.py \
  core/tests/test_pgvector_infra.py
git commit -m "feat(core): pgvector — image Postgres, migration, colonnes embedding (SP-7)"
```

---

## Task 3: Fournisseur d'embeddings enfichable

**Files:**
- Create: `core/app/search/__init__.py`
- Create: `core/app/search/providers.py`
- Test: `core/tests/test_search_providers.py`
- Modify: `.env.example` (documentation des nouvelles variables)

**Interfaces:**
- Produces: `app.search.providers.EmbeddingProvider` (Protocol, méthode `embed(text: str) -> list[float]`), `FakeProvider(vectors: dict[str, list[float]] | None = None)`, `OpenAICompatibleProvider(*, api_url, api_key, model)`, `get_embedding_provider() -> EmbeddingProvider` — consommées par Task 5, 6, 7.

- [ ] **Step 1: Écrire les tests**

```python
# core/tests/test_search_providers.py
import pytest

from app.search.providers import EMBEDDING_DIM, FakeProvider, get_embedding_provider


def test_fake_provider_is_deterministic():
    provider = FakeProvider()
    v1 = provider.embed("incidents voirie")
    v2 = provider.embed("incidents voirie")
    assert v1 == v2
    assert len(v1) == EMBEDDING_DIM


def test_fake_provider_differs_for_different_text():
    provider = FakeProvider()
    assert provider.embed("a") != provider.embed("b")


def test_fake_provider_uses_explicit_vector_when_given():
    controlled = [1.0] * EMBEDDING_DIM
    provider = FakeProvider(vectors={"known text": controlled})
    assert provider.embed("known text") == controlled
    assert provider.embed("other text") != controlled  # repli sur le hash


def test_get_embedding_provider_defaults_to_fake(monkeypatch):
    monkeypatch.delenv("CORE_EMBEDDING_PROVIDER", raising=False)
    provider = get_embedding_provider()
    assert provider.__class__.__name__ == "FakeProvider"


def test_get_embedding_provider_openai_requires_config(monkeypatch):
    monkeypatch.setenv("CORE_EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("CORE_EMBEDDING_API_URL", raising=False)
    with pytest.raises(KeyError):
        get_embedding_provider()


def test_get_embedding_provider_rejects_unknown_kind(monkeypatch):
    monkeypatch.setenv("CORE_EMBEDDING_PROVIDER", "nonsense")
    with pytest.raises(ValueError, match="nonsense"):
        get_embedding_provider()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_search_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.search'`

- [ ] **Step 3: Implémenter**

```python
# core/app/search/__init__.py
```//(vide)

```python
# core/app/search/providers.py
"""Fournisseur d'embeddings enfichable (SP-7). Deux implémentations : un
provider HTTP compatible OpenAI/Voyage pour la production, et un provider
déterministe sans réseau pour dev/test/mock (CORE_EMBEDDING_PROVIDER=fake,
même convention que CORE_AUTH_MODE=mock). Le hash du FakeProvider n'a aucun
sens sémantique — il garantit seulement "même texte -> même vecteur", ce qui
suffit à exercer le mécanisme de recherche hybride en test. Les tests qui
veulent contrôler quels textes se ressemblent injectent une table
text -> vecteur explicite plutôt que de dépendre du hash."""
import hashlib
import os
import random
from typing import Protocol

import httpx

EMBEDDING_DIM = 1536


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


class FakeProvider:
    def __init__(self, vectors: dict[str, list[float]] | None = None):
        self._vectors = vectors or {}

    def embed(self, text: str) -> list[float]:
        if text in self._vectors:
            return self._vectors[text]
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(EMBEDDING_DIM)]


class OpenAICompatibleProvider:
    def __init__(self, *, api_url: str, api_key: str, model: str):
        self._api_url = api_url
        self._api_key = api_key
        self._model = model

    def embed(self, text: str) -> list[float]:
        response = httpx.post(
            self._api_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"input": text, "model": self._model},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]


def get_embedding_provider() -> EmbeddingProvider:
    kind = os.environ.get("CORE_EMBEDDING_PROVIDER", "fake")
    if kind == "fake":
        return FakeProvider()
    if kind == "openai":
        return OpenAICompatibleProvider(
            api_url=os.environ["CORE_EMBEDDING_API_URL"],
            api_key=os.environ["CORE_EMBEDDING_API_KEY"],
            model=os.environ.get("CORE_EMBEDDING_MODEL", "text-embedding-3-small"),
        )
    raise ValueError(f"unknown CORE_EMBEDDING_PROVIDER: {kind}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_search_providers.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Documenter les variables d'environnement**

Ajouter dans `.env.example`, après le bloc `S3_UPLOADS_BUCKET` :

```bash
# ─── Cœur : fournisseur d'embeddings (recherche sémantique, SP-7) ────
# "fake" pour dev/test/mock (aucun accès réseau) ; "openai" en usage réel.
CORE_EMBEDDING_PROVIDER=fake
# Requis seulement si CORE_EMBEDDING_PROVIDER=openai — endpoint HTTP
# compatible OpenAI (POST {input, model} -> {data:[{embedding}]}), ex.
# https://api.openai.com/v1/embeddings ou un endpoint Voyage compatible.
CORE_EMBEDDING_API_URL=
CORE_EMBEDDING_API_KEY=
CORE_EMBEDDING_MODEL=text-embedding-3-small
```

- [ ] **Step 6: Commit**

```bash
git add core/app/search/__init__.py core/app/search/providers.py \
  core/tests/test_search_providers.py .env.example
git commit -m "feat(core): fournisseur d'embeddings enfichable — fake + OpenAI-compatible (SP-7)"
```

---

## Task 4: Reciprocal Rank Fusion + requête hybride générique

**Files:**
- Create: `core/app/search/ranking.py`
- Test: `core/tests/test_search_ranking.py`

**Interfaces:**
- Consumes: rien (module pur, aucune dépendance domaine)
- Produces: `reciprocal_rank_fusion(ranked_lists: list[list[str]], *, k: int = 60) -> list[tuple[str, float]]`, `hybrid_search_ids(session, *, base_stmt, id_column, text_columns, embedding_column, query_text, query_vector, limit=200) -> list[str]` — consommées par Task 6 (`app.items.repository`) et Task 7 (`app.collections.repository`).

- [ ] **Step 1: Écrire les tests pour `reciprocal_rank_fusion`**

```python
# core/tests/test_search_ranking.py
from app.search.ranking import reciprocal_rank_fusion


def test_rrf_favors_items_present_in_both_lists():
    ranked = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]])
    ids = [i for i, _score in ranked]
    # "a" et "b" apparaissent dans les deux listes (rangs proches) ; "c" et
    # "d" n'apparaissent que dans une seule — a/b doivent sortir devant.
    assert ids.index("a") < ids.index("c")
    assert ids.index("b") < ids.index("d")


def test_rrf_handles_an_id_present_in_only_one_list():
    ranked = reciprocal_rank_fusion([["a"], []])
    assert ranked == [("a", 1 / 61)]


def test_rrf_handles_empty_lists():
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_k_constant_is_configurable():
    ranked_default = reciprocal_rank_fusion([["a"]])
    ranked_k1 = reciprocal_rank_fusion([["a"]], k=1)
    assert ranked_default[0][1] == 1 / 61
    assert ranked_k1[0][1] == 1 / 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_search_ranking.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.search.ranking'`

- [ ] **Step 3: Implémenter `reciprocal_rank_fusion`**

```python
# core/app/search/ranking.py
"""Recherche hybride générique (SP-7) : combine des listes classées
(trigram, vecteur) par Reciprocal Rank Fusion, et une requête SQLAlchemy
paramétrique qui construit ces deux listes candidates au-dessus d'un
`base_stmt` déjà filtré par permissions. Module pur / sans dépendance
domaine (comme app.db) — app.items.repository et app.collections.repository
l'utilisent tous deux (Task 6, Task 7)."""
from sqlalchemy import Select, func
from sqlalchemy.orm import Session


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], *, k: int = 60
) -> list[tuple[str, float]]:
    """score(id) = somme de 1/(k+rang) sur chaque liste où id apparaît (rang
    1-indexé). k=60 = constante standard de l'article RRF original (Cormack
    et al. 2009), utilisée telle quelle. Pas de pénalité pour un id absent
    d'une des listes — juste absent de cette somme."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, obj_id in enumerate(ranked, start=1):
            scores[obj_id] = scores.get(obj_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_search_ranking.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Écrire le test `postgis` pour `hybrid_search_ids`**

```python
# core/tests/test_search_ranking.py — ajouter à la suite du fichier
import pytest

from app.db import Base, make_session_factory
from app.items.models import Item
from app.search.providers import FakeProvider
from app.search.ranking import hybrid_search_ids
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from sqlalchemy import select


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("TRUNCATE items, users, tenants CASCADE"))


@pytest.mark.postgis
def test_hybrid_search_ids_ranks_a_vector_match_ahead_of_a_weak_text_match(pg_session):
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    close_vector = [1.0] * 1536
    query_vector = [0.99] * 1536  # très proche de close_vector (cosine)
    far_vector = [-1.0] * 1536

    semantically_close = Item(
        id="i-close", tenant_id=tenant.id, owner_id=user.id,
        resource_type="app", title="Sujet totalement différent",
        embedding=close_vector,
    )
    weak_text_match = Item(
        id="i-weak", tenant_id=tenant.id, owner_id=user.id,
        resource_type="app", title="incidents", embedding=far_vector,
    )
    pg_session.add_all([semantically_close, weak_text_match])
    pg_session.flush()

    base_stmt = select(Item).where(Item.tenant_id == tenant.id)
    provider = FakeProvider(vectors={"incidents voirie": query_vector})
    ids = hybrid_search_ids(
        pg_session, base_stmt=base_stmt, id_column=Item.id,
        text_columns=[Item.title, Item.abstract], embedding_column=Item.embedding,
        query_text="incidents voirie", query_vector=provider.embed("incidents voirie"),
    )
    assert ids.index("i-close") < ids.index("i-weak")
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_search_ranking.py -v -m postgis`
Expected: FAIL — `ImportError: cannot import name 'hybrid_search_ids'`

- [ ] **Step 7: Implémenter `hybrid_search_ids`**

Ajouter à `core/app/search/ranking.py` :

```python
def hybrid_search_ids(
    session: Session,
    *,
    base_stmt: Select,
    id_column,
    text_columns: list,
    embedding_column,
    query_text: str,
    query_vector: list[float],
    limit: int = 200,
) -> list[str]:
    """Construit deux requêtes candidates (trigram, vecteur) au-dessus de
    `base_stmt` — déjà filtré tenant/scope/permissions par l'appelant, avant
    tout scoring (spec §Recherche hybride + permissions) — et les combine
    par RRF. `base_stmt` est un objet Select immuable : chaque `.where(...)`
    ci-dessous produit une requête indépendante qui garde le FROM/WHERE
    d'origine, sans interférer avec l'autre branche."""
    concatenated = text_columns[0]
    for col in text_columns[1:]:
        concatenated = func.concat(concatenated, " ", col)
    similarity_expr = func.similarity(concatenated, query_text)
    trigram_stmt = (
        base_stmt.where(similarity_expr > 0.05)
        .order_by(similarity_expr.desc())
        .limit(limit)
        .with_only_columns(id_column)
    )
    trigram_ids = [row[0] for row in session.execute(trigram_stmt).all()]

    vector_stmt = (
        base_stmt.where(embedding_column.isnot(None))
        .order_by(embedding_column.cosine_distance(query_vector))
        .limit(limit)
        .with_only_columns(id_column)
    )
    vector_ids = [row[0] for row in session.execute(vector_stmt).all()]

    ranked = reciprocal_rank_fusion([trigram_ids, vector_ids])
    return [obj_id for obj_id, _score in ranked]
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_search_ranking.py -v -m postgis`
Expected: PASS

Run: `cd core && uv run pytest -q`
Expected: aucune régression

- [ ] **Step 9: Commit**

```bash
git add core/app/search/ranking.py core/tests/test_search_ranking.py
git commit -m "feat(core): Reciprocal Rank Fusion + requête hybride générique (SP-7)"
```

---

## Task 5: Job d'embedding des items + câblage à l'écriture

**Files:**
- Create: `core/app/items/jobs.py`
- Modify: `core/app/items/routes.py` (enqueue après create/update)
- Test: `core/tests/test_items_jobs.py`

**Interfaces:**
- Consumes: `app.jobs.app` (Task 1), `app.search.providers.get_embedding_provider` (Task 3)
- Produces: `app.items.jobs.embed_item_task` (tâche procrastinate, queue `"search"`, params `item_id: str, tenant_id: str`) — appelée par `app.items.routes` après `create_item`/`update_item`.

- [ ] **Step 1: Écrire le test (pattern `InMemoryConnector`, identique à `test_ingestion_tasks.py`)**

```python
# core/tests/test_items_jobs.py
"""Job d'embedding d'un item (SP-7 Task 5) — même pattern que
test_ingestion_tasks.py : connecteur procrastinate remplacé par
InMemoryConnector, écritures contre PostGIS réel."""
import pytest
from procrastinate import testing
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.items import jobs as item_jobs
from app.items import repository as items_repo
from app.jobs import app as jobs_app
from app.search.providers import FakeProvider
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


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
    in_memory = testing.InMemoryConnector()
    with jobs_app.replace_connector(in_memory) as app:
        yield app, Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE items, users, tenants CASCADE"))


def test_embed_item_task_sets_the_embedding_column(env, monkeypatch):
    app, Session, tenant, user = env
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id,
            resource_type="app", title="Incidents voirie",
        )
        s.commit()
        item_id = item.id

    fake = FakeProvider(vectors={"Incidents voirie\n\n": [0.5] * 1536})
    monkeypatch.setattr(item_jobs, "get_embedding_provider", lambda: fake)

    item_jobs.embed_item_task.defer(item_id=item_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["search"])

    with Session() as s:
        from app.items.models import Item
        reloaded = s.get(Item, item_id)
        assert reloaded.embedding == pytest.approx([0.5] * 1536)


def test_embed_item_task_missing_item_is_a_noop_not_a_crash(env):
    app, Session, tenant, _user = env
    item_jobs.embed_item_task.defer(item_id="does-not-exist", tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["search"])  # ne doit pas lever
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_items_jobs.py -v -m postgis`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.items.jobs'`

- [ ] **Step 3: Implémenter `app/items/jobs.py`**

```python
# core/app/items/jobs.py
"""Job d'embedding d'un item (SP-7) — recalcule embedding après chaque
create/update (app.items.routes), asynchrone (jamais de blocage de
l'écriture sur un fournisseur d'embeddings lent/indisponible). Échec
= log, embedding reste NULL, l'item reste cherchable par trigram seul
(dégradation gracieuse, spec §Pipeline d'embedding)."""
import logging
import os

from sqlalchemy import select

from app.db import make_engine, make_session_factory, request_scoped_session
from app.items.models import Item
from app.jobs import app
from app.search.providers import get_embedding_provider

logger = logging.getLogger(__name__)


def _embed_text(item: Item) -> str:
    return f"{item.title}\n{item.abstract}\n{', '.join(item.keywords or [])}"


@app.task(queue="search")
def embed_item_task(item_id: str, tenant_id: str) -> None:
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    session_factory = make_session_factory(engine)
    try:
        with request_scoped_session(session_factory) as session:
            item = session.scalar(
                select(Item).where(Item.id == item_id, Item.tenant_id == tenant_id)
            )
            if item is None:
                logger.warning("embed_item_task: item %s introuvable (tenant %s)", item_id, tenant_id)
                return
            provider = get_embedding_provider()
            item.embedding = provider.embed(_embed_text(item))
    except Exception:
        logger.exception("embed_item_task: échec du calcul d'embedding pour l'item %s", item_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_items_jobs.py -v -m postgis`
Expected: PASS (2 tests)

- [ ] **Step 5: Câbler l'enqueue depuis `app/items/repository.py`**

`app/items/routes.py` n'a pas de route `POST /items` propre — la création
passe par `app.configs.routes`/`app.mcp.tools`, qui appellent toutes deux
`items_repo.create_item` directement. L'enqueue doit donc vivre au niveau du
**repository**, pas des routes, pour couvrir tous les appelants (REST via
configs, MCP `create_item`, et le futur `create_form_app` de Task 10) sans
dupliquer l'appel à chaque appelant. Dans `core/app/items/repository.py`,
ajouter en fin de `create_item` et `update_item` :

```python
def create_item(
    session: Session, *, tenant_id: str, owner_id: str, resource_type: str, title: str
) -> Item:
    item = Item(
        id=uuid.uuid4().hex, tenant_id=tenant_id, owner_id=owner_id,
        resource_type=resource_type, title=title,
    )
    session.add(item)
    session.flush()
    session.refresh(item)
    from app.items.jobs import embed_item_task
    embed_item_task.defer(item_id=item.id, tenant_id=tenant_id)
    return item
```

(import local, pas en tête de fichier : évite un cycle d'import — `app.items.jobs` importe `app.items.models`, qui est importé transitivement très tôt par `app.db.core_table_names()`)

Et en fin de `update_item`, juste avant le `return` :

```python
    from app.items.jobs import embed_item_task
    embed_item_task.defer(item_id=item.id, tenant_id=tenant_id)
    return _to_read(item, owner_username)
```

- [ ] **Step 6: Étendre le test pour prouver l'enqueue à la création/modification**

Ajouter à `core/tests/test_items_repository.py` :

```python
def test_create_item_enqueues_an_embedding_job(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    deferred = []
    from app.items import jobs as item_jobs
    monkeypatch.setattr(
        item_jobs.embed_item_task, "defer",
        lambda **kwargs: deferred.append(kwargs),
    )
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X")
    assert deferred == [{"item_id": item.id, "tenant_id": tenant.id}]


def test_update_item_enqueues_an_embedding_job(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    item = repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="X")
    deferred = []
    from app.items import jobs as item_jobs
    monkeypatch.setattr(
        item_jobs.embed_item_task, "defer",
        lambda **kwargs: deferred.append(kwargs),
    )
    repo.update_item(
        session, tenant_id=tenant.id, item_id=item.id,
        title="Y", abstract=None, keywords=None, is_published=None,
    )
    assert deferred == [{"item_id": item.id, "tenant_id": tenant.id}]
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_items_repository.py -v`
Expected: PASS, y compris les deux nouveaux tests (tests SQLite — `embed_item_task.defer` est monkeypatché, aucun accès réseau/DB procrastinate réel nécessaire ici)

Run: `cd core && uv run pytest -q`
Expected: aucune régression

- [ ] **Step 8: Commit**

```bash
git add core/app/items/jobs.py core/app/items/repository.py \
  core/tests/test_items_jobs.py core/tests/test_items_repository.py
git commit -m "feat(core): job d'embedding des items, câblé à create/update (SP-7)"
```

---

## Task 6: Recherche hybride dans `list_items`

**Files:**
- Modify: `core/app/items/repository.py`
- Test: `core/tests/test_items_repository.py`

**Interfaces:**
- Consumes: `app.search.providers.get_embedding_provider` (Task 3), `app.search.ranking.hybrid_search_ids` (Task 4)
- Produces: `list_items(...)` inchangé en signature — le comportement change uniquement pour `q` non vide sur dialecte `postgresql` ; sur SQLite (tests rapides existants) le comportement `ILIKE` actuel est préservé à l'identique.

- [ ] **Step 1: Écrire le test `postgis` qui prouve le ranking hybride + les permissions**

Ajouter à `core/tests/test_items_repository.py` (ce fichier a déjà `tenant_and_user`, réutilisé) :

```python
import pytest
from app.search.providers import FakeProvider


@pytest.mark.postgis
def test_list_items_hybrid_search_ranks_semantic_match_ahead_of_weak_text_match(
    session, tenant_and_user, monkeypatch,
):
    from app.db import Base
    Base.metadata.create_all(session.get_bind())
    tenant, user = tenant_and_user

    close_vector = [1.0] * 1536
    query_vector = [0.99] * 1536
    far_vector = [-1.0] * 1536

    semantically_close = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id,
        resource_type="app", title="Sujet totalement différent",
    )
    semantically_close.embedding = close_vector
    weak_text_match = repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id,
        resource_type="app", title="incidents",
    )
    weak_text_match.embedding = far_vector
    session.flush()

    from app.items import repository as items_repo_module
    fake = FakeProvider(vectors={"incidents voirie": query_vector})
    monkeypatch.setattr(items_repo_module, "get_embedding_provider", lambda: fake)

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q="incidents voirie", resource_type=None, scope="all", page=1, page_size=12,
    )
    titles = [i.title for i in page.items]
    assert titles.index("Sujet totalement différent") < titles.index("incidents")


@pytest.mark.postgis
def test_list_items_hybrid_search_never_leaks_an_invisible_item(session, tenant_and_user, monkeypatch):
    from app.db import Base
    Base.metadata.create_all(session.get_bind())
    tenant, user = tenant_and_user
    other = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-other",
        username="other", email=None, first_name="", last_name="",
    )
    invisible = repo.create_item(
        session, tenant_id=tenant.id, owner_id=other.id,
        resource_type="app", title="incidents secrets",
    )
    invisible.embedding = [1.0] * 1536
    session.flush()

    from app.items import repository as items_repo_module
    fake = FakeProvider(vectors={"incidents": [1.0] * 1536})
    monkeypatch.setattr(items_repo_module, "get_embedding_provider", lambda: fake)

    page = repo.list_items(
        session, tenant_id=tenant.id, current_user_id=user.id,
        q="incidents", resource_type=None, scope="mine", page=1, page_size=12,
    )
    assert page.items == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_items_repository.py -v -m postgis -k hybrid`
Expected: FAIL (le ranking actuel est un simple ILIKE, "incidents" sort devant "Sujet totalement différent")

- [ ] **Step 3: Implémenter la branche hybride dans `list_items`**

Dans `core/app/items/repository.py`, ajouter aux imports existants en tête de
fichier (après `from app.users.models import User`) :

```python
from app.search.providers import get_embedding_provider
from app.search.ranking import hybrid_search_ids

_RRF_CANDIDATE_LIMIT = 200
```

Puis remplacer le corps de `list_items` :

```python
def list_items(
    session: Session,
    *,
    tenant_id: str,
    current_user_id: str,
    q: str | None,
    resource_type: str | None,
    scope: str,
    page: int,
    page_size: int,
) -> ItemPage:
    query = select(Item, User.username).join(User, User.id == Item.owner_id).where(Item.tenant_id == tenant_id)
    if resource_type:
        query = query.where(Item.resource_type == resource_type)

    shared_exists = (
        select(ItemShare.item_id)
        .join(GroupMember, GroupMember.group_id == ItemShare.group_id)
        .where(
            ItemShare.item_id == Item.id,
            ItemShare.tenant_id == tenant_id,
            GroupMember.user_id == current_user_id,
            GroupMember.tenant_id == tenant_id,
        )
        .exists()
    )
    if scope == "mine":
        query = query.where(Item.owner_id == current_user_id)
    elif scope == "public":
        query = query.where(Item.is_published.is_(True))
    elif scope == "shared":
        query = query.where(Item.owner_id != current_user_id, shared_exists)
    elif scope == "all":
        query = query.where(
            or_(
                Item.owner_id == current_user_id,
                Item.is_public.is_(True),
                Item.is_published.is_(True),
                shared_exists,
            )
        )
    # À ce stade, `query` ne contient que des lignes visibles par
    # current_user_id — c'est la base sur laquelle la recherche (hybride ou
    # ILIKE) s'exécute ensuite (spec §Recherche hybride + permissions : le
    # filtre can()/scope passe TOUJOURS avant le scoring).

    if q and session.get_bind().dialect.name == "postgresql":
        provider = get_embedding_provider()
        candidate_ids = hybrid_search_ids(
            session, base_stmt=query, id_column=Item.id,
            text_columns=[Item.title, Item.abstract], embedding_column=Item.embedding,
            query_text=q, query_vector=provider.embed(q), limit=_RRF_CANDIDATE_LIMIT,
        )
        total = len(candidate_ids)
        page_ids = candidate_ids[(page - 1) * page_size: (page - 1) * page_size + page_size]
        rows = session.execute(
            select(Item, User.username).join(User, User.id == Item.owner_id)
            .where(Item.id.in_(page_ids))
        ).all()
        by_id = {item.id: (item, owner_username) for item, owner_username in rows}
        items = [_to_read(*by_id[i]) for i in page_ids if i in by_id]
        return ItemPage(items=items, total=total, page=page, pageSize=page_size)

    if q:
        like = f"%{q}%"
        query = query.where(or_(Item.title.ilike(like), Item.abstract.ilike(like)))

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.order_by(Item.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [_to_read(item, owner_username) for item, owner_username in rows]
    return ItemPage(items=items, total=total, page=page, pageSize=page_size)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_items_repository.py -v -m postgis`
Expected: PASS

- [ ] **Step 5: Vérifier la non-régression SQLite (comportement ILIKE inchangé) et l'ensemble de la suite**

Run: `cd core && uv run pytest tests/test_items_repository.py -v`
Expected: PASS, y compris `test_list_items_search_and_type_filter` (préexistant, ILIKE sur SQLite — inchangé)

Run: `cd core && uv run pytest -q`
Expected: aucune régression

- [ ] **Step 6: Commit**

```bash
git add core/app/items/repository.py core/tests/test_items_repository.py
git commit -m "feat(core): recherche hybride (RRF) dans list_items, permissions avant scoring (SP-7)"
```

---

## Task 7: Embedding des collections + recherche hybride + `GET /collections?q=`

Même patron que Task 5+6, appliqué à `app.collections`.

**Files:**
- Create: `core/app/collections/jobs.py`
- Modify: `core/app/collections/repository.py` (`create_collection`, nouveau `list_visible_collections(..., q=None)`, enqueue)
- Modify: `core/app/collections/routes.py` (`list_collections` gagne `q`, `patch_collection` enqueue après modification)
- Test: `core/tests/test_collections_jobs.py`
- Test: `core/tests/test_collections_models.py` ou `test_collections_authorization.py` (selon où vivent déjà les tests de `list_visible_collections` — vérifier avant d'écrire)
- Test: `core/tests/test_collections_routes.py`

**Interfaces:**
- Produces: `app.collections.jobs.embed_collection_task` (tâche procrastinate, queue `"search"`) ; `list_visible_collections(session, *, tenant_id, user_id, is_admin, q=None)` ; route `GET /collections?q=...`.

- [ ] **Step 1: Localiser les tests existants de `list_visible_collections`**

Run: `cd core && grep -rn "list_visible_collections" tests/`
Note le(s) fichier(s) exact(s) (probablement `tests/test_ingestion_importer.py` seulement, per recherche précédente — pas de fichier `test_collections_repository.py` dédié). Créer `core/tests/test_collections_repository.py` s'il n'existe pas encore pour y placer les nouveaux tests de recherche hybride, à côté d'un test de non-régression minimal sur le comportement existant.

- [ ] **Step 2: Écrire le test du job d'embedding**

```python
# core/tests/test_collections_jobs.py
"""Job d'embedding d'une collection (SP-7 Task 7) — même pattern que
test_items_jobs.py."""
import pytest
from procrastinate import testing
from sqlalchemy import text

from app.collections import jobs as collection_jobs
from app.collections import repository as collections_repo
from app.db import Base, make_session_factory
from app.jobs import app as jobs_app
from app.search.providers import FakeProvider
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


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
    in_memory = testing.InMemoryConnector()
    with jobs_app.replace_connector(in_memory) as app:
        yield app, Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE collections, users, tenants CASCADE"))


def test_embed_collection_task_sets_the_embedding_column(env, monkeypatch):
    app, Session, tenant, user = env
    with Session() as s:
        col = collections_repo.create_collection(
            s, tenant_id=tenant.id, owner_id=user.id, table_name="incidents",
            title="Incidents", description="Voirie", is_public=False,
            pk_column="id", geometry_column=None, geometry_type=None, srid=None,
        )
        s.commit()
        col_id = col.id

    fake = FakeProvider(vectors={"Incidents\nVoirie": [0.5] * 1536})
    monkeypatch.setattr(collection_jobs, "get_embedding_provider", lambda: fake)

    collection_jobs.embed_collection_task.defer(collection_id=col_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["search"])

    with Session() as s:
        from app.collections.models import Collection
        reloaded = s.get(Collection, col_id)
        assert reloaded.embedding == pytest.approx([0.5] * 1536)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_collections_jobs.py -v -m postgis`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.collections.jobs'`

- [ ] **Step 4: Implémenter `app/collections/jobs.py`**

```python
# core/app/collections/jobs.py
"""Job d'embedding d'une collection (SP-7) — même patron que
app.items.jobs.embed_item_task."""
import logging
import os

from sqlalchemy import select

from app.collections.models import Collection
from app.db import make_engine, make_session_factory, request_scoped_session
from app.jobs import app
from app.search.providers import get_embedding_provider

logger = logging.getLogger(__name__)


def _embed_text(col: Collection) -> str:
    return f"{col.title}\n{col.description}"


@app.task(queue="search")
def embed_collection_task(collection_id: str, tenant_id: str) -> None:
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    session_factory = make_session_factory(engine)
    try:
        with request_scoped_session(session_factory) as session:
            col = session.scalar(
                select(Collection).where(
                    Collection.id == collection_id, Collection.tenant_id == tenant_id
                )
            )
            if col is None:
                logger.warning(
                    "embed_collection_task: collection %s introuvable (tenant %s)",
                    collection_id, tenant_id,
                )
                return
            provider = get_embedding_provider()
            col.embedding = provider.embed(_embed_text(col))
    except Exception:
        logger.exception(
            "embed_collection_task: échec du calcul d'embedding pour %s", collection_id
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_collections_jobs.py -v -m postgis`
Expected: PASS

- [ ] **Step 6: Câbler l'enqueue dans `create_collection` et le PATCH**

Dans `core/app/collections/repository.py`, fin de `create_collection` :

```python
    session.add(col)
    session.flush()
    from app.collections.jobs import embed_collection_task
    embed_collection_task.defer(collection_id=col.id, tenant_id=tenant_id)
    return col
```

Dans `core/app/collections/routes.py`, fonction `patch_collection`, après la boucle `setattr` et avant `session.flush()` — ajouter l'enqueue seulement si titre ou description ont changé (évite un recalcul inutile sur un simple toggle `isPublic`/`editable`) :

```python
@router.patch("/collections/{collection_id}")
def patch_collection(
    collection_id: str, body: CollectionPatch,
    user=Depends(get_current_user), session: Session = Depends(get_session),
):
    col = get_readable_collection(session, user, collection_id)
    if not can(session, user_id=user.id, action="write", item=repo.get_access_facts(col),
               kind="collection", actor_is_admin=user.is_admin):
        raise HTTPException(status_code=403, detail="write access required")
    text_changed = (
        (body.title is not None and body.title != col.title)
        or (body.description is not None and body.description != col.description)
    )
    for attr, value in (("title", body.title), ("description", body.description),
                        ("is_public", body.isPublic), ("editable", body.editable)):
        if value is not None:
            setattr(col, attr, value)
    session.flush()
    if text_changed:
        from app.collections.jobs import embed_collection_task
        embed_collection_task.defer(collection_id=col.id, tenant_id=user.tenant_id)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="collection.update", object_type="collection", object_id=col.id,
                payload=body.model_dump(exclude_none=True))
    return _collection_json(col, _can_write_collection(session, user, col))
```

- [ ] **Step 7: Écrire les tests de recherche hybride + permissions pour `list_visible_collections`**

```python
# core/tests/test_collections_repository.py (nouveau fichier)
import pytest

from app.collections import repository as repo
from app.db import Base, make_engine, init_db, make_session_factory
from app.search.providers import FakeProvider
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


def test_list_visible_collections_q_none_is_unchanged(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_collection(
        session, tenant_id=tenant.id, owner_id=user.id, table_name="c1",
        title="Communes", description="", is_public=True,
        pk_column="id", geometry_column=None, geometry_type=None, srid=None,
    )
    cols = repo.list_visible_collections(session, tenant_id=tenant.id, user_id=user.id, is_admin=False)
    assert [c.title for c in cols] == ["Communes"]


# Le test de ranking/permissions hybride a besoin de Postgres réel (pg_trgm +
# pgvector) — fixture dédiée `pg_session`, même patron que Task 6.
@pytest.fixture()
def pg_session(pg_engine):
    from sqlalchemy import text
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE collections, users, tenants CASCADE"))


@pytest.mark.postgis
def test_list_visible_collections_hybrid_search_never_leaks_an_invisible_collection(
    pg_session, monkeypatch,
):
    tenant = get_or_create_default_tenant(pg_session)
    owner = get_or_create_user(
        pg_session, tenant_id=tenant.id, oidc_sub="owner", username="owner",
        email=None, first_name="", last_name="",
    )
    other = get_or_create_user(
        pg_session, tenant_id=tenant.id, oidc_sub="other", username="other",
        email=None, first_name="", last_name="",
    )
    private = repo.create_collection(
        pg_session, tenant_id=tenant.id, owner_id=owner.id, table_name="secret",
        title="Secret incidents", description="", is_public=False,
        pk_column="id", geometry_column=None, geometry_type=None, srid=None,
    )
    private.embedding = [1.0] * 1536
    pg_session.flush()

    from app.collections import repository as collections_repo_module
    fake = FakeProvider(vectors={"incidents": [1.0] * 1536})
    monkeypatch.setattr(collections_repo_module, "get_embedding_provider", lambda: fake)

    cols = repo.list_visible_collections(
        pg_session, tenant_id=tenant.id, user_id=other.id, is_admin=False, q="incidents",
    )
    assert cols == []
```

- [ ] **Step 8: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_collections_repository.py -v -k q_none`
Expected: PASS (ce test ne touche pas la nouvelle branche)

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_collections_repository.py -v -m postgis`
Expected: FAIL — `list_visible_collections() got an unexpected keyword argument 'q'`

- [ ] **Step 9: Implémenter la branche hybride dans `list_visible_collections`**

Dans `core/app/collections/repository.py`, ajouter aux imports existants en
tête de fichier (après `from app.sharing.models import ...`) :

```python
from app.search.providers import get_embedding_provider
from app.search.ranking import hybrid_search_ids

_RRF_CANDIDATE_LIMIT = 200
```

Puis remplacer le corps de `list_visible_collections` :

```python
def list_visible_collections(
    session: Session, *, tenant_id: str, user_id: str | None, is_admin: bool,
    q: str | None = None,
) -> list[Collection]:
    stmt = select(Collection).where(Collection.tenant_id == tenant_id)
    if not is_admin:
        if user_id is None:
            stmt = stmt.where(Collection.is_public.is_(True))
        else:
            shared_ids = (
                select(CollectionShare.collection_id)
                .join(GroupMember, GroupMember.group_id == CollectionShare.group_id)
                .where(GroupMember.user_id == user_id,
                       CollectionShare.tenant_id == tenant_id)
            )
            stmt = stmt.where(
                Collection.is_public.is_(True)
                | (Collection.owner_id == user_id)
                | Collection.id.in_(shared_ids)
            )
    # Filtre de visibilité posé AVANT toute recherche (spec §Recherche
    # hybride + permissions), comme pour list_items.

    if q and session.get_bind().dialect.name == "postgresql":
        provider = get_embedding_provider()
        candidate_ids = hybrid_search_ids(
            session, base_stmt=stmt, id_column=Collection.id,
            text_columns=[Collection.title, Collection.description],
            embedding_column=Collection.embedding,
            query_text=q, query_vector=provider.embed(q), limit=_RRF_CANDIDATE_LIMIT,
        )
        rows = session.execute(
            select(Collection).where(Collection.id.in_(candidate_ids))
        ).all()
        by_id = {c.id: c for (c,) in rows}
        return [by_id[i] for i in candidate_ids if i in by_id]

    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Collection.title.ilike(like), Collection.description.ilike(like)))

    return list(session.scalars(stmt.order_by(Collection.title)).all())
```

La ligne d'import existante `from sqlalchemy import delete, func, select` ne
porte pas `or_` — la changer en `from sqlalchemy import delete, func, or_, select`.

- [ ] **Step 10: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_collections_repository.py -v -m postgis`
Expected: PASS

Run: `cd core && uv run pytest tests/test_ingestion_importer.py -v -k list_visible_collections`
Expected: PASS (les 2 appels existants passent bien `q` implicitement omis — signature rétrocompatible)

- [ ] **Step 11: Brancher `q` sur la route `GET /collections`**

Dans `core/app/collections/routes.py` :

```python
@router.get("/collections")
def list_collections(
    q: str | None = None,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
):
    from app.tenants.repository import get_or_create_default_tenant
    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    cols = repo.list_visible_collections(
        session, tenant_id=tenant_id, user_id=user.id if user else None,
        is_admin=bool(user and user.is_admin), q=q,
    )
    return {"collections": [_collection_json(c, _can_write_collection(session, user, c)) for c in cols]}
```

- [ ] **Step 12: Écrire le test de route**

Ajouter à `core/tests/test_collections_routes.py` :

```python
def test_list_collections_accepts_q_param_without_error(env):
    app, client, Session, admin, regular, _ddl = env
    _as(app, regular)
    with Session() as s:
        repo.create_collection(
            s, tenant_id=admin.tenant_id, owner_id=admin.id, table_name="c1",
            title="Communes", description="", is_public=True,
            pk_column="id", geometry_column=None, geometry_type=None, srid=None,
        )
        s.commit()
    resp = client.get("/collections?q=commun")
    assert resp.status_code == 200
    # SQLite (route de test) : repli ILIKE, "commun" est une sous-chaîne de "Communes".
    assert [c["title"] for c in resp.json()["collections"]] == ["Communes"]
```

(vérifier l'import `from app.collections import repository as repo` déjà présent dans ce fichier de test ; sinon l'ajouter)

- [ ] **Step 13: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v`
Expected: PASS

Run: `cd core && uv run pytest -q`
Expected: aucune régression sur l'ensemble de la suite

- [ ] **Step 14: Commit**

```bash
git add core/app/collections/jobs.py core/app/collections/repository.py \
  core/app/collections/routes.py core/tests/test_collections_jobs.py \
  core/tests/test_collections_repository.py core/tests/test_collections_routes.py
git commit -m "feat(core): embedding + recherche hybride sur les collections, GET /collections?q= (SP-7)"
```

---

## Task 8: Outil MCP `search_catalog`

**Files:**
- Modify: `core/app/mcp/tools.py`
- Test: `core/tests/test_mcp_tools_search.py`

**Interfaces:**
- Consumes: `items_repo.list_items` (déjà hybride depuis Task 6)
- Produces: outil MCP `search_catalog(q, type=None, scope="all", page=1, pageSize=12) -> ItemPage`

- [ ] **Step 1: Écrire le test**

```python
# core/tests/test_mcp_tools_search.py
"""search_catalog (SP-7 Task 8) — mince adaptateur au-dessus de
items_repo.list_items, même patron de test que test_mcp_tools_create.py."""
from tests.test_mcp_tools_create import app_client, call_tool  # noqa: F401 (fixtures/helpers réutilisés)


def test_search_catalog_returns_items_matching_q(app_client):
    with app_client:
        call_tool(
            app_client, "create_item",
            {"kind": "app", "title": "Incidents voirie",
             "config": {"kind": "app", "layout": {"type": "grid", "items": []}}},
        )
        call_tool(
            app_client, "create_item",
            {"kind": "dashboard", "title": "Ventes",
             "config": {"kind": "dashboard", "layout": {"type": "grid", "items": []}}},
        )
        result = call_tool(app_client, "search_catalog", {"q": "incidents"})

    assert [i["title"] for i in result["items"]] == ["Incidents voirie"]


def test_search_catalog_respects_scope(app_client):
    with app_client:
        result = call_tool(app_client, "search_catalog", {"scope": "mine"})
    assert result["items"] == []  # aucun item créé par le caller dans ce test
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_mcp_tools_search.py -v`
Expected: FAIL — l'outil `search_catalog` n'existe pas (erreur MCP "Unknown tool")

- [ ] **Step 3: Implémenter dans `app/mcp/tools.py`**

Chaque outil de ce fichier ouvre sa propre session (`request_scoped_session`) —
factoriser un helper partagé entre `list_items` et `search_catalog` forcerait
soit une session artificiellement partagée entre les deux, soit un helper qui
prend `session`/`user` déjà résolus en paramètres pour un gain de 3 lignes :
pas rentable. `search_catalog` duplique donc le corps de `list_items` sous un
nom distinct — c'est exactement le même choix que `_can_write_collection`
(collections/routes.py) et `_get_writable` (features/routes.py), déjà
dupliqués dans ce dépôt pour des raisons similaires. Ajouter, après l'outil
`list_items` existant (dans `register_tools`) :

```python
    @server.tool()
    async def search_catalog(
        ctx: Context,
        q: str | None = None,
        type: str | None = None,
        scope: str = "all",
        page: int = 1,
        pageSize: int = 12,
    ) -> ItemPage:
        """Search the catalog (hybrid trigram + vector ranking on q) — items
        only, not collections. Same permissions/parameters as list_items;
        registered as its own tool for agent discoverability of the search
        capability (SP-7 MCP v1)."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            return items_repo.list_items(
                session, tenant_id=user.tenant_id, current_user_id=user.id,
                q=q, resource_type=type, scope=scope, page=page, page_size=pageSize,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_mcp_tools_search.py -v`
Expected: PASS

Run: `cd core && uv run pytest -q`
Expected: aucune régression

- [ ] **Step 5: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_search.py
git commit -m "feat(core): outil MCP search_catalog (SP-7)"
```

---

## Task 9: Outil MCP `query_features`

**Files:**
- Modify: `core/app/mcp/tools.py`
- Test: `core/tests/test_mcp_tools_query_features.py`

**Interfaces:**
- Consumes: `app.features.repository.select_features`/`FilterError`, `app.features.rls.rls_scope`, `app.collections.introspection_pg.introspect_table`, `app.collections.introspection.{TableNotFound,UnsupportedTable}`
- Produces: outil MCP `query_features(collectionId, bbox=None, filters=None, limit=100, offset=0) -> dict` (GeoJSON FeatureCollection)

- [ ] **Step 1: Écrire le test**

Ce test a besoin d'une vraie collection PostGIS (comme `test_features_routes_write.py` existant probablement) — vérifier le fixture PostGIS utilisé par les tests de features REST et le réutiliser :

Run: `cd core && grep -n "pytestmark\|fixture" tests/test_features_routes*.py | head -20`

Puis écrire, en reprenant ce même patron de fixture (collection réelle enregistrée, table backing créée) :

```python
# core/tests/test_mcp_tools_query_features.py
"""query_features (SP-7 Task 9) — mince adaptateur MCP au-dessus de
select_features, même permissions que GET /collections/{id}/items."""
import pytest

from tests.test_mcp_tools_create import app_client, call_tool, call_tool_expecting_error  # noqa: F401

pytestmark = pytest.mark.postgis


def _register_incidents_collection(app_client):
    with app_client.session_factory() as session:
        from app.collections.ddl import apply_collection_ddl
        from app.collections import repository as collections_repo
        from sqlalchemy import text
        session.execute(text(
            "CREATE TABLE incidents (id serial PRIMARY KEY, tenant_id text NOT NULL, "
            "titre text, geom geometry(Point, 4326))"
        ))
        session.commit()
        apply_collection_ddl(session, "incidents")
        col = collections_repo.create_collection(
            session, tenant_id=app_client.tenant.id, owner_id=app_client.mock_user.id,
            table_name="incidents", title="Incidents", description="", is_public=True,
            pk_column="id", geometry_column="geom", geometry_type="Point", srid=4326,
        )
        session.execute(text(
            "INSERT INTO incidents (tenant_id, titre, geom) VALUES "
            "(:tid, 'Nid de poule', ST_SetSRID(ST_MakePoint(2.3, 48.8), 4326))"
        ), {"tid": app_client.tenant.id})
        session.commit()
        return col.id


def test_query_features_returns_geojson_for_a_readable_collection(app_client):
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        result = call_tool(app_client, "query_features", {"collectionId": collection_id})

    assert result["type"] == "FeatureCollection"
    assert result["numberReturned"] == 1
    assert result["features"][0]["properties"]["titre"] == "Nid de poule"


def test_query_features_unknown_collection_errors(app_client):
    with app_client:
        error_text = call_tool_expecting_error(app_client, "query_features", {"collectionId": "nope"})
    assert "not found" in error_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_mcp_tools_query_features.py -v -m postgis`
Expected: FAIL — l'outil `query_features` n'existe pas

- [ ] **Step 3: Implémenter dans `app/mcp/tools.py`**

Ajouter les imports en tête de fichier — `can` est déjà importé (utilisé par
`_require_access`), les autres sont nouveaux :

```python
from app.collections import repository as collections_repo
from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.features.repository import FilterError, select_features
from app.features.rls import rls_scope
```

Ajouter une fonction utilitaire ValueError-raising pour la lecture d'une collection (miroir de `get_readable_collection`, comme `_require_access` mirrore la logique items) :

```python
def _require_collection_read(session, *, user: User, collection_id: str):
    """Mirrors app/collections/routes.py's get_readable_collection — ValueError
    instead of HTTPException, same rationale as _require_access above."""
    col = collections_repo.get_collection(session, tenant_id=user.tenant_id, collection_id=collection_id)
    if col is None:
        raise ValueError("collection not found")
    readable = can(
        session, user_id=user.id, action="read",
        item=collections_repo.get_access_facts(col), kind="collection",
        actor_is_admin=user.is_admin,
    )
    if not readable:
        raise ValueError("collection not found")
    return col


def _parse_bbox_tuple(raw: str) -> tuple[float, float, float, float]:
    parts = raw.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must be minx,miny,maxx,maxy")
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        raise ValueError("bbox must be minx,miny,maxx,maxy") from None
```

Ajouter l'outil dans `register_tools` :

```python
    @server.tool()
    async def query_features(
        ctx: Context,
        collectionId: str,
        bbox: str | None = None,
        filters: dict[str, str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Read features from a collection — mirrors GET
        /collections/{id}/items (bbox, attribute filters, pagination), same
        permissions/RLS. No natural-language-to-filter translation: filters
        are structured field=value pairs, like any OGC client (SP-7 MCP v1)."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            col = _require_collection_read(session, user=user, collection_id=collectionId)
            try:
                info = introspect_table(session, col.table_name)
            except TableNotFound:
                raise ValueError("collection backing table not found")
            except UnsupportedTable as exc:
                raise ValueError(exc.reason)
            parsed_bbox = _parse_bbox_tuple(bbox) if bbox else None
            try:
                with rls_scope(session, col.tenant_id):
                    page = select_features(
                        session, info, limit=min(limit, 1000), offset=offset,
                        bbox=parsed_bbox, filters=filters or None,
                    )
            except FilterError as exc:
                raise ValueError(f"unknown filter field: {exc.field}")
            return {
                "type": "FeatureCollection", "features": page.features,
                "numberMatched": page.number_matched, "numberReturned": page.number_returned,
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_mcp_tools_query_features.py -v -m postgis`
Expected: PASS

Run: `cd core && uv run pytest -q`
Expected: aucune régression

- [ ] **Step 5: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_query_features.py
git commit -m "feat(core): outil MCP query_features (SP-7)"
```

---

## Task 10: Outil MCP `create_form_app`

**Files:**
- Create: `core/app/mcp/form_app.py`
- Modify: `core/app/mcp/tools.py`
- Test: `core/tests/test_mcp_form_app.py` (génération pure, sans DB)
- Test: `core/tests/test_mcp_tools_create_form_app.py` (bout-en-bout, `postgis`)

**Interfaces:**
- Produces: `app.mcp.form_app.build_config(*, collection_id, schema, include_form) -> BuilderConfig`, `form_fields_from_schema(schema: dict) -> list[dict]`, `can_write_collection(session, *, user, col) -> bool` ; outil MCP `create_form_app(collectionId, title=None) -> ItemRead`.

- [ ] **Step 1: Écrire le test unitaire de génération (pas de DB)**

```python
# core/tests/test_mcp_form_app.py
"""Génération d'AppConfig pour create_form_app (SP-7 Task 10) — pure, sans
DB. Sert aussi de test de non-régression structurel pour le mapping
schéma->champs, dupliqué côté TS dans
shell/src/builder/widgets/form.tsx::fieldsFromSchema (même risque de dérive
que CEL, arbitrage A8 — voir spec §Architecture MCP v1)."""
from app.mcp.form_app import build_config, form_fields_from_schema

SCHEMA = {
    "collection": "incidents", "pk": "id",
    "geometry": {"column": "geom", "type": "Point", "srid": 4326},
    "fields": [
        {"name": "titre", "type": "string", "required": True, "maxLength": 200},
        {"name": "gravite", "type": "enum", "required": False, "values": ["faible", "haute"]},
    ],
}


def test_form_fields_from_schema_maps_every_field_visible_and_unordered_by_default():
    fields = form_fields_from_schema(SCHEMA)
    assert fields == [
        {"name": "titre", "type": "string", "label": "titre", "order": 0,
         "hidden": False, "required": True, "maxLength": 200},
        {"name": "gravite", "type": "enum", "label": "gravite", "order": 1,
         "hidden": False, "required": False, "values": ["faible", "haute"]},
    ]


def test_build_config_with_form_includes_form_map_table_and_message():
    config = build_config(collection_id="incidents", schema=SCHEMA, include_form=True)
    widget_types = [item.widget for item in config.layout.items]
    assert widget_types == ["form", "map", "table"]
    assert len(config.messages) == 1
    assert config.messages[0].event == "itemSelected"
    assert config.messages[0].action == "loadRecord"
    table_item = next(i for i in config.layout.items if i.widget == "table")
    assert table_item.props["columns"] == ["titre", "gravite"]


def test_build_config_without_form_has_only_map_and_table():
    config = build_config(collection_id="incidents", schema=SCHEMA, include_form=False)
    widget_types = [item.widget for item in config.layout.items]
    assert widget_types == ["map", "table"]
    assert config.messages == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_mcp_form_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.mcp.form_app'`

- [ ] **Step 3: Implémenter `app/mcp/form_app.py`**

```python
# core/app/mcp/form_app.py
"""Génération d'AppConfig pour l'outil MCP create_form_app (SP-7) — mêmes
briques que le gabarit builder « Application de saisie » (SP-4c,
shell/src/builder/templates.ts), assemblées côté serveur à partir du schéma
introspecté d'une collection plutôt que choisies à la main dans le builder."""
from app.collections import repository as collections_repo
from app.collections.models import Collection
from app.configs.schemas import BuilderConfig, DataSource, Layout, LayoutItem, Message
from app.sharing.authorization import can
from app.users.models import User


def can_write_collection(session, *, user: User, col: Collection) -> bool:
    """Mirror of app/collections/routes.py's _can_write_collection (private
    to that module, no user=None branch needed here — an MCP tool always has
    a resolved user via _resolve_actor)."""
    return col.editable and can(
        session, user_id=user.id, action="write",
        item=collections_repo.get_access_facts(col), kind="collection",
        actor_is_admin=user.is_admin,
    )


def form_fields_from_schema(schema: dict) -> list[dict]:
    """Python mirror of shell/src/builder/widgets/form.tsx's
    fieldsFromSchema: 1:1 mapping over schema["fields"], order=index,
    hidden=False always, required carried over, maxLength/values passed
    through when present. Kept in sync by the structural tests in
    tests/test_mcp_form_app.py rather than shared code across the TS/Python
    boundary (same trade-off as CEL's cel-js/cel-python, arbitrage A8)."""
    fields = []
    for i, f in enumerate(schema["fields"]):
        entry: dict = {
            "name": f["name"], "type": f["type"], "label": f["name"],
            "order": i, "hidden": False, "required": f["required"],
        }
        if "maxLength" in f:
            entry["maxLength"] = f["maxLength"]
        if "values" in f:
            entry["values"] = f["values"]
        fields.append(entry)
    return fields


def build_config(*, collection_id: str, schema: dict, include_form: bool) -> BuilderConfig:
    data_source_id = f"{collection_id}-ds"
    data_sources = [DataSource(id=data_source_id, type="features", service="core", layer=collection_id, query={})]
    columns = [f["name"] for f in schema["fields"]]

    items: list[LayoutItem] = []
    messages: list[Message] = []
    if include_form:
        items.append(LayoutItem(
            id="form", widget="form", x=0, y=0, w=4, h=6,
            props={
                "dataSourceId": data_source_id,
                "fields": form_fields_from_schema(schema),
                "submitLabel": "Enregistrer",
                "geometryType": schema["geometry"]["type"] if schema["geometry"] else None,
            },
        ))
        items.append(LayoutItem(
            id="map", widget="map", x=4, y=0, w=8, h=4, props={"dataSourceId": data_source_id},
        ))
        items.append(LayoutItem(
            id="table", widget="table", x=4, y=4, w=8, h=2,
            props={"dataSourceId": data_source_id, "columns": columns, "pageSize": 10},
        ))
        messages.append(Message(**{"from": "table", "event": "itemSelected", "to": "form", "action": "loadRecord"}))
    else:
        items.append(LayoutItem(
            id="map", widget="map", x=0, y=0, w=8, h=4, props={"dataSourceId": data_source_id},
        ))
        items.append(LayoutItem(
            id="table", widget="table", x=0, y=4, w=8, h=2,
            props={"dataSourceId": data_source_id, "columns": columns, "pageSize": 10},
        ))

    return BuilderConfig(
        kind="app", dataSources=data_sources,
        layout=Layout(type="grid", breakpoints={}, items=items), messages=messages,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_mcp_form_app.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Écrire le test bout-en-bout MCP**

```python
# core/tests/test_mcp_tools_create_form_app.py
import pytest

from tests.test_mcp_tools_create import app_client, call_tool, call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import _register_incidents_collection  # noqa: F401

pytestmark = pytest.mark.postgis


def test_create_form_app_owner_gets_form_map_table(app_client):
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        result = call_tool(app_client, "create_form_app", {"collectionId": collection_id})

    assert result["resourceType"] == "app"
    with app_client.session_factory() as session:
        from app.configs import repository as configs_repo
        config = configs_repo.get_config_by_item(session, result["pk"])
        widget_types = [item["widget"] for item in config.config["layout"]["items"]]
        assert widget_types == ["form", "map", "table"]


def test_create_form_app_writes_audit_log_with_agent_actor(app_client):
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        call_tool(app_client, "create_form_app", {"collectionId": collection_id})

    with app_client.session_factory() as session:
        from sqlalchemy import select
        from app.audit.models import AuditLog
        rows = list(session.scalars(select(AuditLog)))
        actions = {r.action for r in rows}
        assert "item.create" in actions
        assert "config.create" in actions
        assert all(r.actor_kind == "agent" for r in rows if r.object_type in ("item", "config"))


def test_create_form_app_unknown_collection_errors(app_client):
    with app_client:
        error_text = call_tool_expecting_error(app_client, "create_form_app", {"collectionId": "nope"})
    assert "not found" in error_text
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_mcp_tools_create_form_app.py -v -m postgis`
Expected: FAIL — l'outil `create_form_app` n'existe pas

- [ ] **Step 7: Implémenter l'outil dans `app/mcp/tools.py`**

Ajouter l'import :

```python
from app.mcp import form_app
```

Ajouter l'outil dans `register_tools` :

```python
    @server.tool()
    async def create_form_app(
        ctx: Context, collectionId: str, title: str | None = None,
    ) -> ItemRead:
        """Compose a Carte+Table(+Formulaire if the caller can write) app on
        an existing collection, from its introspected schema — same shape as
        the builder's "Application de saisie" gallery template (SP-4c),
        generated instead of hand-picked. Formulaire is included only if the
        caller has write access to the collection (mirrors the canWrite
        predicate SP-4c exposes on collections). SP-7 MCP v1."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            col = _require_collection_read(session, user=user, collection_id=collectionId)
            try:
                info = introspect_table(session, col.table_name)
            except TableNotFound:
                raise ValueError("collection backing table not found")
            except UnsupportedTable as exc:
                raise ValueError(exc.reason)
            schema = table_info_to_schema(info)
            include_form = form_app.can_write_collection(session, user=user, col=col)
            config = form_app.build_config(
                collection_id=collectionId, schema=schema, include_form=include_form,
            )
            item = items_repo.create_item(
                session, tenant_id=user.tenant_id, owner_id=user.id,
                resource_type="app", title=title or f"Application {col.title}",
            )
            config_result = configs_repo.create_config(session, config, item_id=item.id)
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": item.title, "collectionId": collectionId},
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="config.create", object_type="config", object_id=config_result.id,
                payload={"collectionId": collectionId, "includeForm": include_form},
            )
            result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item.id)
            assert result is not None
            return result
```

Ajouter l'import `from app.collections.schema_json import table_info_to_schema` en tête de fichier (nouveau à ce stade — Task 9 n'en avait pas besoin, `query_features` retourne des features brutes, pas un schéma).

Note : `items_repo.create_item` a été modifié en Task 5 pour enqueue automatiquement `embed_item_task` — `create_form_app` en bénéficie gratuitement, aucun câblage supplémentaire nécessaire ici.

- [ ] **Step 8: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest tests/test_mcp_tools_create_form_app.py -v -m postgis`
Expected: PASS

Run: `cd core && uv run pytest -q`
Expected: aucune régression, suite complète verte

- [ ] **Step 9: Commit**

```bash
git add core/app/mcp/form_app.py core/app/mcp/tools.py \
  core/tests/test_mcp_form_app.py core/tests/test_mcp_tools_create_form_app.py
git commit -m "feat(core): outil MCP create_form_app, piloté par le schéma (SP-7)"
```

---

## Task 11: Shell — recherche de collections dans `LayerPicker`

**Files:**
- Modify: `shell/src/api/types.ts` (`listLayerSources` accepte des params)
- Modify: `shell/src/api/itemClient.ts` (`fetchCoreCollections(q?)`, filtre client Martin)
- Modify: `shell/src/api/hooks.ts` (`useLayerSources` passe `q`)
- Modify: `shell/src/map/LayerPicker.tsx` (champ de recherche)
- Test: `shell/src/map/LayerPicker.test.tsx`
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces: `ItemClient.listLayerSources(params?: { q?: string }): Promise<LayerSource[]>` — signature étendue, rétrocompatible (`params` optionnel).

- [ ] **Step 1: Écrire le test `itemClient.test.ts` pour le passthrough de `q`**

Lire d'abord `shell/src/api/itemClient.test.ts` pour repérer le patron exact des tests `fetch` existants (mock global `fetch`), puis ajouter :

```typescript
test("listLayerSources passes q to /collections and lets Martin sources through unfiltered when q is empty", async () => {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.includes("/catalog")) {
      return { ok: true, json: async () => ({ tiles: {} }) } as Response;
    }
    if (url.includes("/collections")) {
      expect(url).toContain("q=commun");
      return { ok: true, json: async () => ({ collections: [{ id: "c1", title: "Communes" }] }) } as Response;
    }
    throw new Error(`unexpected url ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = makeClient("t"); // adapter au helper de fabrique déjà utilisé dans ce fichier
  const sources = await client.listLayerSources({ q: "commun" });
  expect(sources).toHaveLength(1);
});
```

(Adapter aux helpers exacts déjà présents dans `itemClient.test.ts`, notamment `makeClient`/le mock de `martinUrl`/`coreUrl` — lire le fichier avant d'écrire ce test pour respecter le patron existant plutôt que d'inventer une nouvelle fixture.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- itemClient.test.ts`
Expected: FAIL — `listLayerSources` ignore aujourd'hui tout argument (signature `(): Promise<...>`, `q` jamais transmis à l'URL)

- [ ] **Step 3: Étendre le type `ItemClient` et la signature**

Dans `shell/src/api/types.ts:107` :

```typescript
  listLayerSources(params?: { q?: string }): Promise<LayerSource[]>;
```

- [ ] **Step 4: Implémenter dans `itemClient.ts`**

Modifier `fetchCoreCollections` (ligne ~210) pour accepter `q` :

```typescript
  async function fetchCoreCollections(q?: string): Promise<LayerSource[]> {
    const token = getToken();
    const query = q ? `?q=${encodeURIComponent(q)}` : "";
    const res = await fetch(`${coreUrl}/collections${query}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} /collections`);
    const data = (await res.json()) as {
      collections?: { id: string; title?: string; featureCount?: number | null }[];
    };
    return (data.collections ?? []).map((c) => ({
      id: c.id,
      title: c.title ?? c.id,
      service: "core" as const,
      kind: "feature" as const,
      url: `${coreUrl}/collections/${c.id}/items`,
      featureCount: c.featureCount,
    }));
  }
```

Modifier `fetchMartinSources` pour accepter `q` et filtrer côté client par sous-chaîne du titre (Martin n'a pas de recherche serveur — YAGNI d'en ajouter une pour un service de tuiles statique) :

```typescript
  async function fetchMartinSources(q?: string): Promise<LayerSource[]> {
    if (!martinUrl) return [];
    const res = await fetch(`${martinUrl}/catalog`);
    if (!res.ok) throw new Error(`Request failed: ${res.status} /catalog`);
    const data = (await res.json()) as {
      tiles?: Record<string, { description?: string }>;
    };
    const sources = Object.entries(data.tiles ?? {}).map(([id, meta]) => ({
      id,
      title: meta.description ?? id,
      service: "martin" as const,
      kind: "vector" as const,
      tilesUrl: `${martinUrl}/${id}/{z}/{x}/{y}`,
      sourceLayer: id,
    }));
    if (!q) return sources;
    const needle = q.toLowerCase();
    return sources.filter((s) => s.title.toLowerCase().includes(needle));
  }
```

Modifier `listLayerSources` :

```typescript
    async listLayerSources(params?: { q?: string }): Promise<LayerSource[]> {
      const results = await Promise.allSettled([
        fetchMartinSources(params?.q),
        fetchCoreCollections(params?.q),
      ]);
      const fulfilled = results.filter(
        (r): r is PromiseFulfilledResult<LayerSource[]> => r.status === "fulfilled",
      );
      if (fulfilled.length === 0) {
        throw new Error("listLayerSources: all layer services failed");
      }
      return fulfilled.flatMap((r) => r.value);
    },
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd shell && npm run test -- itemClient.test.ts`
Expected: PASS

- [ ] **Step 6: Étendre `useLayerSources`**

Dans `shell/src/api/hooks.ts:144` :

```typescript
export function useLayerSources(options?: { enabled?: boolean; q?: string }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["layer-sources", options?.q ?? ""],
    queryFn: () => client.listLayerSources({ q: options?.q }),
    enabled: options?.enabled ?? true,
  });
}
```

- [ ] **Step 7: Écrire le test `LayerPicker.test.tsx` pour le champ de recherche**

Ajouter à `shell/src/map/LayerPicker.test.tsx` :

```typescript
test("has a search field that calls listLayerSources with q", async () => {
  const onAdd = vi.fn();
  const client = { listLayerSources: vi.fn().mockResolvedValue(sources) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayerPicker onAdd={onAdd} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await screen.findByRole("button", { name: /Communes/ });
  const search = screen.getByRole("searchbox", { name: /rechercher/i });
  await userEvent.type(search, "commun");
  await waitFor(() => {
    expect(client.listLayerSources).toHaveBeenLastCalledWith({ q: "commun" });
  });
});
```

(ajouter `waitFor` à l'import `@testing-library/react` en tête du fichier de test — patron déjà utilisé dans `shell/src/builder/widgets/form.test.tsx`, pas `vi.waitFor`)

- [ ] **Step 8: Run test to verify it fails**

Run: `cd shell && npm run test -- LayerPicker.test.tsx`
Expected: FAIL — pas de `role="searchbox"` dans `LayerPicker` aujourd'hui

- [ ] **Step 9: Implémenter le champ de recherche dans `LayerPicker.tsx`**

```typescript
// shell/src/map/LayerPicker.tsx
import { useState } from "react";
import { useLayerSources } from "../api/hooks";
import type { LayerSource, MapLayer } from "../api/types";

function toMapLayer(source: LayerSource): MapLayer {
  const id = crypto.randomUUID();
  if (source.kind === "vector") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "vector",
      tilesUrl: source.tilesUrl ?? "",
      sourceLayer: source.sourceLayer ?? "",
    };
  }
  return { id, title: source.title, visible: true, kind: "feature", url: source.url ?? "" };
}

export function LayerPicker({ onAdd }: { onAdd: (layer: MapLayer) => void }) {
  const [q, setQ] = useState("");
  const { data, isLoading, isError, refetch } = useLayerSources({ q: q || undefined });

  return (
    <div className="flex flex-col gap-2">
      <input
        type="search"
        role="searchbox"
        aria-label="Rechercher une source de couche"
        placeholder="Rechercher…"
        className="h-8 rounded-md border border-slate-300 px-2 text-sm"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {isLoading && <p className="text-sm text-slate-500">Chargement des sources…</p>}
      {isError && (
        <div className="text-sm text-red-600">
          <p role="alert">Impossible de charger les sources de couches.</p>
          <button type="button" className="underline" onClick={() => refetch()}>
            Réessayer
          </button>
        </div>
      )}
      {!isLoading && !isError && (!data || data.length === 0) && (
        <p className="text-sm text-slate-500">Aucune source disponible.</p>
      )}
      {!isLoading && !isError && data && data.length > 0 && (
        <ul className="flex flex-col gap-1">
          {data.map((source) => (
            <li key={`${source.service}:${source.id}`}>
              <button
                type="button"
                className="w-full rounded-md px-2 py-1 text-left text-sm hover:bg-slate-100"
                onClick={() => onAdd(toMapLayer(source))}
              >
                {source.title}
                <span className="ml-2 text-xs text-slate-400">{source.kind}</span>
                {typeof source.featureCount === "number" && (
                  <span className="ml-2 text-xs text-slate-400">
                    {source.featureCount} entités
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

(pas de debounce ajouté : `useQuery` de TanStack Query dédoublonne déjà par `queryKey`, et le volume de sources/collections reste petit en v1 — un debounce serait une optimisation prématurée sans utilisateur réel qui en pâtit, YAGNI)

- [ ] **Step 10: Run test to verify it passes**

Run: `cd shell && npm run test -- LayerPicker.test.tsx`
Expected: PASS, y compris les tests préexistants (`isLoading`/`isError`/liste vide) — vérifier qu'aucun n'est cassé par le changement de structure JSX (les tests existants cherchent des `role="button"`/`role="alert"`, inchangés)

- [ ] **Step 11: Run full shell suite**

Run: `cd shell && npm run test`
Expected: tous les tests passent (401+ fichiers), aucune régression

Run: `cd shell && npm run build`
Expected: `tsc --noEmit` + `vite build` réussissent sans erreur de type

- [ ] **Step 12: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/hooks.ts \
  shell/src/map/LayerPicker.tsx shell/src/map/LayerPicker.test.tsx shell/src/api/itemClient.test.ts
git commit -m "feat(shell): recherche de collections dans LayerPicker (SP-7)"
```

---

## Task 12: E2E — recherche catalogue (régression) + recherche LayerPicker + permissions

**Files:**
- Modify: `shell/e2e/mocks.ts` (route `**/collections` paramétrable par `q`)
- Create: `shell/e2e/layer-picker-search.spec.ts`
- Modify: `shell/e2e/catalog.spec.ts` (test de non-régression : recherche par sous-chaîne toujours fonctionnelle)

**Interfaces:**
- Aucune nouvelle interface — vérifie le comportement bout-en-bout des Tasks 10-11 à travers le mock réseau Playwright existant.

- [ ] **Step 1: Étendre `mocks.ts` pour que `**/collections` réponde selon `q`**

Dans `shell/e2e/mocks.ts`, remplacer la route `**/collections` (ligne ~156, celle qui retourne `{ collections: [] }` par défaut) :

```typescript
  const ALL_COLLECTIONS = [
    { id: "communes", title: "Communes", featureCount: 12 },
    { id: "incidents", title: "Incidents voirie", featureCount: 3 },
  ];

  await page.route("**/collections", async (route) => {
    const url = new URL(route.request().url());
    const q = url.searchParams.get("q");
    const collections = q
      ? ALL_COLLECTIONS.filter((c) => c.title.toLowerCase().includes(q.toLowerCase()))
      : [];
    await route.fulfill({ json: { collections } });
  });
```

(le défaut `q=null` → `[]` préserve exactement le comportement actuel des specs existantes qui ne passent jamais par `LayerPicker` avec une recherche — seule la nouvelle spec `layer-picker-search.spec.ts` fournit `q`)

- [ ] **Step 2: Écrire la spec E2E `layer-picker-search.spec.ts`**

`LayerPicker` est toujours visible directement dans `LayersPanel` (pas de bouton
« ouvrir » — cf. `shell/src/map/LayersPanel.tsx:42-44`) ; la création d'une
carte suit exactement le patron de `e2e/map-editor.spec.ts` (catalogue →
« Nouveau » → dialogue → `/maps/77`) :

```typescript
// shell/e2e/layer-picker-search.spec.ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("searching in the layer picker filters collections by title", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Ma carte");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);

  const search = page.getByRole("searchbox", { name: /rechercher une source de couche/i });
  await search.fill("incid");

  await expect(page.getByRole("button", { name: /Incidents voirie/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Communes/ })).not.toBeVisible();
});
```

- [ ] **Step 3: Run E2E spec to verify it fails**

Run: `cd shell && npx playwright test layer-picker-search.spec.ts`
Expected: FAIL avant Task 11 fusionnée localement — si Task 11 est déjà committée (exécution séquentielle du plan), ce test doit déjà passer ; sinon, l'échec attendu est l'absence du `searchbox`. Dans les deux cas, exécuter pour confirmer l'état attendu avant de continuer.

- [ ] **Step 4: Ajouter le test de non-régression de la recherche catalogue**

La barre de recherche catalogue (`shell/src/pages/CatalogPage.tsx:38-46`) est
un `<Input aria-label="Rechercher">` **sans** `type="search"` — son rôle
accessible est `textbox`, pas `searchbox` (celui-ci est nouveau, propre au
`LayerPicker` de Task 11). La route mock `**/items*` de `mocks.ts` ne filtre
pas elle-même par `q` (elle ne l'a jamais fait — aucune spec existante n'en a
besoin) : rien côté Task 6-9 ne touche ce chemin shell, donc la régression à
prouver est que **la requête envoyée par le shell porte toujours `q`**, pas
un filtrage de rendu que le mock ne fait pas. Ajouter à
`shell/e2e/catalog.spec.ts` :

```typescript
test("catalog search still sends q to the core (regression)", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();

  const request = page.waitForRequest((req) => req.url().includes("/items?") && req.url().includes("q=Alp"));
  await page.getByRole("textbox", { name: "Rechercher" }).fill("Alp");
  await request;
});
```

- [ ] **Step 5: Run full E2E suite**

Run: `cd shell && npm run e2e`
Expected: les 20 specs (19 existantes + `layer-picker-search.spec.ts`) passent — `VITE_AUTH_MODE=mock`, aucune régression sur les 19 specs préexistantes.

- [ ] **Step 6: Commit**

```bash
git add shell/e2e/mocks.ts shell/e2e/layer-picker-search.spec.ts shell/e2e/catalog.spec.ts
git commit -m "test(e2e): recherche LayerPicker + non-régression recherche catalogue (SP-7)"
```

---

## Vérification finale (avant intégration)

Une fois les 12 tâches terminées :

```bash
cd core && uv run pytest -q                         # sans DB
cd core && CORE_TEST_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@localhost:5432/gis uv run pytest -q -m postgis  # avec DB réelle
cd core && uv run import-linter                     # frontières de modules
cd shell && npm run test
cd shell && npm run build
cd shell && npm run e2e
```

Critères d'acceptation à revérifier manuellement contre la spec
(`docs/superpowers/specs/2026-07-13-sp7-recherche-semantique-mcp-v1-design.md`
§Critères d'acceptation) : recherche sémantique catalogue (test Task 6),
`create_form_app` fonctionnel avec/sans droits d'écriture (test Task 10),
non-régression substring (test Task 12), zéro fuite de metadata (tests Task
6/7), recherche `LayerPicker` (test Task 11/12).
