# SP-6a — Infra jobs (procrastinate) + ingestion GeoJSON/CSV : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un utilisateur authentifié importe un GeoJSON ou un CSV+lat/lon depuis le shell ; le cœur enfile un job (`procrastinate`), un worker conteneurisé parse le fichier, crée une table PostGIS + l'enregistre comme collection (réutilise le chemin `register_collection`), et construit un item carte prêt à consulter — sans intervention manuelle après le clic d'upload.

**Architecture:** Upload direct navigateur→MinIO via URL présignée (le cœur ne voit jamais les octets, arbitrage A6) ; `POST /uploads` crée une ligne `ingestion_jobs` (tenant_id + audit) et enfile une tâche `procrastinate` ; le worker (même image Docker que le cœur, process séparé) télécharge le fichier, le parse en pur Python (`shapely`, zéro GDAL — réservé à SP-6b), crée la table PostGIS, appelle directement les fonctions internes de `app.collections`/`app.configs`/`app.items` (pas de saut HTTP) pour enregistrer la collection et créer l'item carte, puis met à jour le statut du job. Le shell poll `GET /uploads/{id}` jusqu'à `done`/`error`.

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic/`procrastinate`/`shapely`/`boto3` (Tasks 1-4), React 19 + TypeScript + Vitest/MSW (Task 5), Playwright (Task 6, `VITE_AUTH_MODE=mock`).

## Global Constraints

- `evaluateExpression`/aucun rapport avec CEL ici — SP-6a est un chantier cœur+infra, aucune expression no-code en jeu.
- Zéro dépendance GDAL : `shapely` + `json`/`csv` standard uniquement pour GeoJSON/CSV. GeoPackage/Shapefile (`pyogrio`) sont hors périmètre (SP-6b).
- Toute ligne/feature invalide fait échouer **tout** le job (fail-fast) — jamais d'import partiel silencieux ; le message d'erreur devient `ingestion_jobs.error_message` tel quel.
- CRS supposée WGS84 (4326) pour GeoJSON (RFC 7946) et CSV — pas de détection/reprojection de CRS en 6a.
- Chaque upload crée **toujours** une nouvelle collection (jamais d'ajout à une collection existante).
- `ingestion_jobs` porte `tenant_id` + trace d'audit dès sa migration (règle non négociable du projet).
- Le pipeline d'import réutilise directement les fonctions internes de `app.collections` (introspection, DDL, `create_collection`), `app.configs` (`create_config`) et `app.items` (`create_item`) — pas de saut HTTP interne, même chemin qu'un admin enregistrant une collection à la main.
- Tout utilisateur authentifié peut uploader (pas de restriction admin, contrairement à l'enregistrement manuel de collection en SP-3a).
- Aucune régression : `cd core && uv run pytest` (302+ tests : 272 exécutés + 30 postgis) et `cd shell && npm run test` (394+ tests) + `npm run build` verts après chaque tâche ; `cd shell && npm run e2e` vert après la Task 6 (18 specs : 17 existantes + la nouvelle).
- Docs et messages utilisateur en français ; code/identifiants en anglais (champs Python en camelCase côté schémas Pydantic exposés en API, comme le reste du cœur — ex. `ItemRead.resourceType`). TDD systématique ; commits conventional en français.
- `procrastinate` et `shapely` sont de nouvelles dépendances : le `Dockerfile` du cœur maintient sa propre liste `uv pip install` **à la main**, en plus de `pyproject.toml` (commentaire existant en tête du Dockerfile) — toute tâche qui ajoute une dépendance à `pyproject.toml` DOIT aussi l'ajouter au Dockerfile, sous peine de crash-loop du conteneur.
- `procrastinate` est une lib récente pour ce projet : si un nom de paramètre exact (ex. `conninfo=` sur `SyncPsycopgConnector`) ne correspond pas à la version réellement installée par `uv sync`, consulter `.venv/lib/*/site-packages/procrastinate/` directement plutôt que de deviner plus avant.

---

## Task 1: `ingestion_jobs` — table, migration, repository

**Files:**
- Create: `core/app/ingestion/__init__.py`
- Create: `core/app/ingestion/models.py`
- Create: `core/app/ingestion/repository.py`
- Create: `core/alembic/versions/0009_ingestion_jobs.py`
- Modify: `core/app/db.py:40-54` (`core_table_names`)
- Modify: `core/pyproject.toml:38-66` (import-linter : layers + ignore_imports)
- Test: `core/tests/test_ingestion_repository.py`

**Interfaces:**
- Produces: `IngestionJob` (modèle SQLAlchemy) ; `repository.create_job(session, *, tenant_id, created_by, source_key, filename, collection_title, lat_field, lon_field) -> IngestionJob` ; `repository.get_job(session, *, tenant_id, job_id) -> IngestionJob | None` ; `repository.mark_running(session, *, job_id) -> None` ; `repository.mark_done(session, *, job_id, collection_id, item_id) -> None` ; `repository.mark_error(session, *, job_id, error_message) -> None`.
- Consumes: `app.db.Base`, `app.tenants.repository.get_or_create_default_tenant`, `app.users.repository.get_or_create_user` (tests seulement).

- [ ] **Step 1: Créer le module et écrire les tests qui échouent**

Créer `core/app/ingestion/__init__.py` (vide).

Créer `core/tests/test_ingestion_repository.py` :

```python
from app.db import init_db, make_engine, make_session_factory
from app.ingestion import repository as repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    return Session, tenant, user


def test_create_and_get_job():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="f.geojson", collection_title="Villes",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id
        assert job.status == "pending"
    with Session() as s:
        fetched = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched is not None
        assert fetched.filename == "f.geojson"
        assert fetched.collection_title == "Villes"


def test_get_job_scoped_to_tenant():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="f.geojson", collection_title="Villes",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        assert repo.get_job(s, tenant_id="other-tenant", job_id=job_id) is None


def test_mark_running_then_done():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="f.geojson", collection_title="Villes",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        repo.mark_running(s, job_id=job_id)
        s.commit()
    with Session() as s:
        repo.mark_done(s, job_id=job_id, collection_id="c1", item_id="i1")
        s.commit()
    with Session() as s:
        fetched = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.status == "done"
        assert fetched.collection_id == "c1"
        assert fetched.item_id == "i1"


def test_mark_error():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="f.geojson", collection_title="Villes",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        repo.mark_error(s, job_id=job_id, error_message="JSON invalide")
        s.commit()
    with Session() as s:
        fetched = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.status == "error"
        assert fetched.error_message == "JSON invalide"


def test_create_job_stores_optional_lat_lon_fields():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="f.csv", collection_title="Villes",
            lat_field="y", lon_field="x",
        )
        s.commit()
        assert job.lat_field == "y"
        assert job.lon_field == "x"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_ingestion_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion.models'` (ni `repository`, le module n'existe pas encore).

- [ ] **Step 3: Créer le modèle**

Créer `core/app/ingestion/models.py` :

```python
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # "pending" | "running" | "done" | "error"
    source_key: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    collection_title: Mapped[str] = mapped_column(String, nullable=False)
    lat_field: Mapped[str | None] = mapped_column(String, nullable=True)
    lon_field: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    collection_id: Mapped[str | None] = mapped_column(String, nullable=True)
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
```

- [ ] **Step 4: Créer le repository**

Créer `core/app/ingestion/repository.py` :

```python
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.models import IngestionJob


def create_job(
    session: Session, *, tenant_id: str, created_by: str, source_key: str,
    filename: str, collection_title: str,
    lat_field: str | None, lon_field: str | None,
) -> IngestionJob:
    job = IngestionJob(
        id=uuid.uuid4().hex, tenant_id=tenant_id, created_by=created_by,
        status="pending", source_key=source_key, filename=filename,
        collection_title=collection_title, lat_field=lat_field, lon_field=lon_field,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> IngestionJob | None:
    return session.scalar(
        select(IngestionJob).where(
            IngestionJob.id == job_id, IngestionJob.tenant_id == tenant_id
        )
    )


# mark_running/mark_done/mark_error sont appelées uniquement par le worker
# (app.ingestion.tasks), qui a déjà validé le job via get_job(tenant_id=...)
# au tout début de la tâche — pas de re-filtrage par tenant ici, job_id est
# un identifiant interne non devinable (uuid4) à ce stade, jamais fourni
# directement par une requête HTTP utilisateur.
def mark_running(session: Session, *, job_id: str) -> None:
    job = session.get(IngestionJob, job_id)
    if job is None:
        return
    job.status = "running"
    session.flush()


def mark_done(session: Session, *, job_id: str, collection_id: str, item_id: str) -> None:
    job = session.get(IngestionJob, job_id)
    if job is None:
        return
    job.status = "done"
    job.collection_id = collection_id
    job.item_id = item_id
    session.flush()


def mark_error(session: Session, *, job_id: str, error_message: str) -> None:
    job = session.get(IngestionJob, job_id)
    if job is None:
        return
    job.status = "error"
    job.error_message = error_message
    session.flush()
```

- [ ] **Step 5: Enregistrer le modèle auprès de `core_table_names` et de l'import-linter**

Dans `core/app/db.py`, remplacer la fonction `core_table_names` (actuellement lignes 40-54) :

```python
def core_table_names() -> frozenset[str]:
    """Noms des tables du cœur, calculés APRÈS import de tous les modules
    models. Les imports paresseux sont indispensables : un appelant peut être
    importé avant app.items/app.configs (ordre alphabétique dans main.py), et
    ``Base.metadata`` ne connaît que les modèles déjà importés. Source de
    vérité de la denylist du registre de collections."""
    from app.audit import models as audit_models  # noqa: F401
    from app.collections import models as collections_models  # noqa: F401
    from app.configs import models  # noqa: F401
    from app.ingestion import models as ingestion_models  # noqa: F401
    from app.items import models as items_models  # noqa: F401
    from app.sharing import models as sharing_models  # noqa: F401
    from app.tenants import models as tenants_models  # noqa: F401
    from app.users import models as users_models  # noqa: F401

    return frozenset(Base.metadata.tables)
```

Dans `core/pyproject.toml`, le module `app.ingestion` sera importé par `app.collections`/`app.configs`/`app.items`/`app.audit`/`app.auth` (Tasks 3-4 : le pipeline d'import et les routes appellent directement leurs fonctions internes) et par `app.features` (le worker écrit sous `rls_scope`, définie dans `app.features.rls`) — il doit donc se situer **au-dessus** de tous ces modules dans les couches. Remplacer le bloc `[[tool.importlinter.contracts]]` (actuellement lignes 41-66) :

```toml
[[tool.importlinter.contracts]]
name = "layered architecture"
type = "layers"
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.ingestion",
    "app.features",
    "app.collections",
    "app.configs",
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
]
```

- [ ] **Step 6: Créer la migration Alembic**

Créer `core/alembic/versions/0009_ingestion_jobs.py` :

```python
"""ingestion_jobs table (SP-6a)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("collection_title", sa.String(), nullable=False),
        sa.Column("lat_field", sa.String(), nullable=True),
        sa.Column("lon_field", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("collection_id", sa.String(), nullable=True),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ingestion_jobs")
```

- [ ] **Step 7: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_ingestion_repository.py -v`
Expected: PASS (5/5)

Run: `cd core && uv run pytest`
Expected: PASS (277+ passed, 30 skipped postgis) — aucune régression.

Run: `cd core && uv run lint-imports`
Expected: PASS — la nouvelle couche `app.ingestion` ne casse aucune contrainte existante (elle n'importe encore rien).

Run: `cd core && uv run alembic upgrade head && uv run alembic downgrade base`
Expected: les deux commandes réussissent sans erreur (nécessite `DATABASE_URL` pointant vers un Postgres réel — utiliser `CORE_TEST_DATABASE_URL` si disponible localement, sinon vérifier au minimum que `alembic upgrade head` ne lève pas d'erreur de syntaxe en local via `alembic check`/`uv run python -c "import app.alembic_env"` selon ce qui est disponible ; le job CI `migrations` validera formellement les deux commandes contre un Postgres réel).

- [ ] **Step 8: Commit**

```bash
cd core
git add app/ingestion/__init__.py app/ingestion/models.py app/ingestion/repository.py \
  alembic/versions/0009_ingestion_jobs.py app/db.py pyproject.toml \
  tests/test_ingestion_repository.py
git commit -m "feat(core): ingestion_jobs — table, migration, repository (SP-6a)"
```

---

## Task 2: Parseurs GeoJSON et CSV+lat/lon

**Files:**
- Create: `core/app/ingestion/parsers.py`
- Modify: `core/pyproject.toml` (dépendance `shapely`)
- Modify: `core/Dockerfile` (liste `uv pip install` synchronisée à la main)
- Test: `core/tests/test_ingestion_parsers.py`

**Interfaces:**
- Produces: `IngestionParseError(Exception)` ; `detect_lat_lon_fields(fieldnames: list[str]) -> tuple[str, str] | None` ; `parse_geojson(content: bytes) -> Iterator[tuple[shapely.geometry.base.BaseGeometry, dict]]` ; `parse_csv_latlon(content: bytes, lat_field: str | None, lon_field: str | None) -> Iterator[tuple[BaseGeometry, dict]]`. Ni l'une ni l'autre ne lève en dehors d'`IngestionParseError` sur une entrée malformée (fail-fast, message précis).
- Consumes: `shapely` (nouvelle dépendance).

- [ ] **Step 1: Ajouter la dépendance**

Dans `core/pyproject.toml`, dans `dependencies` (actuellement lignes 6-18), ajouter après `"boto3>=1.34",` :

```toml
    "shapely>=2.0",
```

Dans `core/Dockerfile`, ajouter `"shapely>=2.0"` à la liste `uv pip install --system --no-cache` (actuellement après `"mcp>=1.12"`) :

```dockerfile
RUN uv pip install --system --no-cache \
    "fastapi>=0.111" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" \
    "pydantic>=2.7" "httpx>=0.27" "psycopg[binary]>=3.1" \
    "alembic>=1.13" "pyjwt[crypto]>=2.8" "boto3>=1.34" "python-multipart>=0.0.9" \
    "mcp>=1.12" "shapely>=2.0"
```

Run: `cd core && uv sync`
Expected: `shapely` installé, aucune erreur de résolution.

- [ ] **Step 2: Écrire les tests qui échouent**

Créer `core/tests/test_ingestion_parsers.py` :

```python
import pytest

from app.ingestion.parsers import (
    IngestionParseError, detect_lat_lon_fields, parse_csv_latlon, parse_geojson,
)


def test_parse_geojson_yields_geometry_and_properties():
    content = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":{"nom":"A"},"geometry":{"type":"Point","coordinates":[1.0,2.0]}}]}'
    )
    rows = list(parse_geojson(content))
    assert len(rows) == 1
    geom, props = rows[0]
    assert geom.geom_type == "Point"
    assert (geom.x, geom.y) == (1.0, 2.0)
    assert props == {"nom": "A"}


def test_parse_geojson_defaults_missing_properties_to_empty_dict():
    content = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"geometry":{"type":"Point","coordinates":[1.0,2.0]}}]}'
    )
    rows = list(parse_geojson(content))
    assert rows[0][1] == {}


def test_parse_geojson_rejects_malformed_json():
    with pytest.raises(IngestionParseError, match="JSON invalide"):
        list(parse_geojson(b"{not json"))


def test_parse_geojson_rejects_non_feature_collection():
    with pytest.raises(IngestionParseError, match="FeatureCollection"):
        list(parse_geojson(b'{"type":"Feature","properties":{},"geometry":null}'))


def test_parse_geojson_rejects_missing_geometry():
    content = b'{"type":"FeatureCollection","features":[{"type":"Feature","properties":{}}]}'
    with pytest.raises(IngestionParseError, match="feature 0"):
        list(parse_geojson(content))


def test_detect_lat_lon_fields_case_insensitive():
    assert detect_lat_lon_fields(["Lat", "Lon"]) == ("Lat", "Lon")
    assert detect_lat_lon_fields(["latitude", "longitude"]) == ("latitude", "longitude")
    assert detect_lat_lon_fields(["nom", "valeur"]) is None


def test_parse_csv_latlon_auto_detects_columns():
    content = b"nom,lat,lon\nParis,48.85,2.35\n"
    rows = list(parse_csv_latlon(content, None, None))
    assert len(rows) == 1
    geom, props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)
    assert props == {"nom": "Paris"}


def test_parse_csv_latlon_uses_explicit_field_names():
    content = b"nom,y_coord,x_coord\nParis,48.85,2.35\n"
    rows = list(parse_csv_latlon(content, "y_coord", "x_coord"))
    geom, props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)


def test_parse_csv_latlon_fails_fast_on_invalid_row():
    content = b"nom,lat,lon\nParis,48.85,2.35\nCasse,abc,2.35\n"
    with pytest.raises(IngestionParseError, match="ligne 2"):
        list(parse_csv_latlon(content, None, None))


def test_parse_csv_latlon_raises_when_columns_cannot_be_detected():
    content = b"nom,valeur\nA,1\n"
    with pytest.raises(IngestionParseError, match="introuvables"):
        list(parse_csv_latlon(content, None, None))
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_ingestion_parsers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion.parsers'`.

- [ ] **Step 4: Implémenter**

Créer `core/app/ingestion/parsers.py` :

```python
"""Parseurs GeoJSON et CSV+lat/lon (SP-6a) — pur Python, aucune dépendance
GDAL (réservée à SP-6b pour GeoPackage/Shapefile). Chaque parseur produit un
flux (géométrie shapely, propriétés) ; toute ligne/feature invalide lève
IngestionParseError immédiatement (fail-fast, §5 de la spec SP-6a) — pas
d'import partiel silencieux."""
import csv
import io
import json
from collections.abc import Iterator

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry


class IngestionParseError(Exception):
    """Message affiché tel quel comme ingestion_jobs.error_message."""


_LAT_NAMES = {"lat", "latitude", "y"}
_LON_NAMES = {"lon", "lng", "longitude", "x"}


def detect_lat_lon_fields(fieldnames: list[str]) -> tuple[str, str] | None:
    by_lower = {name.lower(): name for name in fieldnames}
    lat = next((by_lower[n] for n in _LAT_NAMES if n in by_lower), None)
    lon = next((by_lower[n] for n in _LON_NAMES if n in by_lower), None)
    if lat is None or lon is None:
        return None
    return lat, lon


def parse_geojson(content: bytes) -> Iterator[tuple[BaseGeometry, dict]]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise IngestionParseError(f"JSON invalide : {exc}") from exc
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise IngestionParseError("le GeoJSON doit être une FeatureCollection")
    features = data.get("features", [])
    for i, feature in enumerate(features):
        geometry = feature.get("geometry")
        if geometry is None:
            raise IngestionParseError(f"feature {i} : géométrie manquante")
        try:
            geom = shape(geometry)
        except (ValueError, AttributeError, KeyError, TypeError) as exc:
            raise IngestionParseError(f"feature {i} : géométrie invalide ({exc})") from exc
        if not geom.is_valid:
            raise IngestionParseError(f"feature {i} : géométrie invalide")
        yield geom, dict(feature.get("properties") or {})


def parse_csv_latlon(
    content: bytes, lat_field: str | None, lon_field: str | None,
) -> Iterator[tuple[BaseGeometry, dict]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    fieldnames = reader.fieldnames or []
    if lat_field is None or lon_field is None:
        detected = detect_lat_lon_fields(fieldnames)
        if detected is None:
            raise IngestionParseError(
                "colonnes lat/lon introuvables automatiquement — précisez-les"
            )
        lat_field, lon_field = detected
    if lat_field not in fieldnames or lon_field not in fieldnames:
        raise IngestionParseError(f"colonnes '{lat_field}'/'{lon_field}' absentes du CSV")
    for i, row in enumerate(reader, start=1):
        try:
            lat = float(row[lat_field])
            lon = float(row[lon_field])
        except (TypeError, ValueError):
            raise IngestionParseError(
                f"ligne {i} : lat/lon invalide "
                f"('{row.get(lat_field)}', '{row.get(lon_field)}')"
            )
        properties = {k: v for k, v in row.items() if k not in (lat_field, lon_field)}
        yield Point(lon, lat), properties
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_ingestion_parsers.py -v`
Expected: PASS (10/10)

Run: `cd core && uv run pytest`
Expected: PASS (287+ passed, 30 skipped postgis) — aucune régression.

- [ ] **Step 6: Commit**

```bash
cd core
git add app/ingestion/parsers.py pyproject.toml Dockerfile tests/test_ingestion_parsers.py
git commit -m "feat(core): parseurs GeoJSON/CSV+lat-lon — fail-fast, pur Python (SP-6a)"
```

---

## Task 3: Worker `procrastinate` + pipeline d'import (table PostGIS + collection + item carte)

**Files:**
- Create: `core/app/ingestion/storage.py`
- Create: `core/app/ingestion/importer.py`
- Create: `core/app/ingestion/tasks.py`
- Modify: `core/pyproject.toml` (dépendance `procrastinate`)
- Modify: `core/Dockerfile` (liste `uv pip install` synchronisée)
- Modify: `docker-compose.yml` (service `worker`, `S3_UPLOADS_BUCKET` sur `core`)
- Modify: `.env.example` (`S3_UPLOADS_BUCKET`)
- Test: `core/tests/test_ingestion_storage.py`
- Test: `core/tests/test_ingestion_importer.py` (postgis)
- Test: `core/tests/test_ingestion_tasks.py` (postgis)

**Interfaces:**
- Produces: `storage.make_s3_client(*, endpoint_url, access_key, secret_key)` ; `storage.ensure_uploads_bucket(client, bucket)` ; `storage.generate_presigned_put_url(client, *, bucket, key, content_type, expires_in=900) -> str` ; `storage.download_object(client, *, bucket, key) -> bytes` ; `importer.ImportResult(collection_id: str, item_id: str)` ; `importer.run_import(session, *, tenant_id, created_by, filename, content, collection_title, lat_field, lon_field) -> ImportResult` (lève `IngestionParseError` sur fichier invalide, ne crée rien en cas d'échec) ; `tasks.app` (App procrastinate, module-level) ; `tasks.run_ingestion_task(job_id: str, tenant_id: str) -> None` (tâche `@app.task(queue="ingestion")`, ne lève jamais — toute erreur finit `ingestion_jobs.status="error"`).
- Consumes: `app.ingestion.repository` (Task 1), `app.ingestion.parsers` (Task 2), `app.collections.repository.create_collection`, `app.collections.ddl.{apply_collection_ddl,quote_ident}`, `app.collections.introspection_pg.introspect_table`, `app.collections.extent.table_extent`, `app.configs.repository.create_config`, `app.configs.schemas.{BuilderConfig,MapConfig,MapView,BaseMap,MapLayer}`, `app.items.repository.create_item`, `app.db.{make_engine,make_session_factory,request_scoped_session}`.

- [ ] **Step 1: Ajouter la dépendance `procrastinate`**

Dans `core/pyproject.toml`, ajouter après `"shapely>=2.0",` :

```toml
    "procrastinate>=2.0",
```

Dans `core/Dockerfile`, ajouter `"procrastinate>=2.0"` à la liste `uv pip install` :

```dockerfile
RUN uv pip install --system --no-cache \
    "fastapi>=0.111" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" \
    "pydantic>=2.7" "httpx>=0.27" "psycopg[binary]>=3.1" \
    "alembic>=1.13" "pyjwt[crypto]>=2.8" "boto3>=1.34" "python-multipart>=0.0.9" \
    "mcp>=1.12" "shapely>=2.0" "procrastinate>=2.0"
```

Run: `cd core && uv sync`
Expected: `procrastinate` installé.

- [ ] **Step 2: Écrire les tests qui échouent pour `storage.py`**

Créer `core/tests/test_ingestion_storage.py` :

```python
"""Wrapper S3 fin — testé avec un client boto3 factice (pas de MinIO réel
nécessaire), même patron que fake_introspector dans test_collections_routes.py."""
from app.ingestion.storage import (
    download_object, ensure_uploads_bucket, generate_presigned_put_url,
)


class _FakeS3Client:
    def __init__(self):
        self.created_buckets: list[str] = []
        self.cors_calls: list[tuple[str, dict]] = []
        self.presign_calls: list[tuple[str, dict, int]] = []
        self._objects: dict[str, bytes] = {}

    def create_bucket(self, Bucket):  # noqa: N803 - signature boto3
        self.created_buckets.append(Bucket)

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        self.cors_calls.append((Bucket, CORSConfiguration))

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        self.presign_calls.append((operation, Params, ExpiresIn))
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}?presigned=1"

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self._objects[Key] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        class _Body:
            def __init__(self, data: bytes):
                self._data = data

            def read(self) -> bytes:
                return self._data

        return {"Body": _Body(self._objects[Key])}


def test_ensure_uploads_bucket_creates_and_sets_cors():
    client = _FakeS3Client()
    ensure_uploads_bucket(client, "geostudio-uploads")
    assert client.created_buckets == ["geostudio-uploads"]
    assert len(client.cors_calls) == 1
    assert client.cors_calls[0][0] == "geostudio-uploads"


def test_generate_presigned_put_url_targets_put_object():
    client = _FakeS3Client()
    url = generate_presigned_put_url(
        client, bucket="geostudio-uploads", key="t/abc-file.geojson",
        content_type="application/geo+json",
    )
    assert url == "https://minio.test/geostudio-uploads/t/abc-file.geojson?presigned=1"
    operation, params, expires = client.presign_calls[0]
    assert operation == "put_object"
    assert params["Bucket"] == "geostudio-uploads"
    assert params["Key"] == "t/abc-file.geojson"
    assert params["ContentType"] == "application/geo+json"
    assert expires == 900


def test_download_object_reads_body():
    client = _FakeS3Client()
    client.put_object(Bucket="b", Key="k", Body=b"hello")
    assert download_object(client, bucket="b", key="k") == b"hello"
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_ingestion_storage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion.storage'`.

- [ ] **Step 4: Implémenter `storage.py`**

Créer `core/app/ingestion/storage.py` :

```python
"""Stockage S3/MinIO pour l'ingestion (SP-6a) : URL présignée pour l'upload
direct navigateur→bucket (arbitrage A6 — le cœur ne doit pas être sur le
chemin des octets pour les uploads de données) et lecture par le worker."""
from botocore.exceptions import ClientError

_CORS_CONFIGURATION = {
    "CORSRules": [{
        "AllowedMethods": ["PUT"],
        "AllowedOrigins": ["*"],
        "AllowedHeaders": ["*"],
        "MaxAgeSeconds": 3000,
    }]
}
# CORS large (dev) : l'upload présigné se fait depuis le navigateur, une
# origine différente du cœur (A6). À resserrer aux origines réelles avant
# une mise en production multi-origine.


def make_s3_client(*, endpoint_url: str, access_key: str, secret_key: str):
    import boto3

    return boto3.client(
        "s3", endpoint_url=endpoint_url,
        aws_access_key_id=access_key, aws_secret_access_key=secret_key,
    )


def ensure_uploads_bucket(client, bucket: str) -> None:
    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise
    client.put_bucket_cors(Bucket=bucket, CORSConfiguration=_CORS_CONFIGURATION)


def generate_presigned_put_url(
    client, *, bucket: str, key: str, content_type: str, expires_in: int = 900,
) -> str:
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )


def download_object(client, *, bucket: str, key: str) -> bytes:
    obj = client.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_ingestion_storage.py -v`
Expected: PASS (3/3)

- [ ] **Step 6: Écrire les tests qui échouent pour `importer.py` (postgis)**

Créer `core/tests/test_ingestion_importer.py` :

```python
"""Bout en bout sur PostGIS réel : run_import seul (table + collection + item
carte), sans procrastinate ni S3 — même infra que test_features_integration.py."""
import pytest
from sqlalchemy import text

from app.collections import repository as collections_repo
from app.configs import repository as configs_repo
from app.db import Base, make_session_factory
from app.ingestion.importer import run_import
from app.ingestion.parsers import IngestionParseError
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

GEOJSON = (
    b'{"type":"FeatureCollection","features":['
    b'{"type":"Feature","properties":{"nom":"A","population":100},'
    b'"geometry":{"type":"Point","coordinates":[1.0,45.0]}},'
    b'{"type":"Feature","properties":{"nom":"B","population":200},'
    b'"geometry":{"type":"Point","coordinates":[2.0,46.0]}}]}'
)


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    yield Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE items, configs, config_revisions, collections, "
            "audit_log, users, tenants CASCADE"
        ))


def test_geojson_import_creates_queryable_collection_and_map_item(env):
    Session, tenant, user = env
    with Session() as s:
        result = run_import(
            s, tenant_id=tenant.id, created_by=user.id, filename="villes.geojson",
            content=GEOJSON, collection_title="Villes", lat_field=None, lon_field=None,
        )
        s.commit()
        config = configs_repo.get_config_by_item(s, item_id=result.item_id)
        assert config is not None
        assert config.config.kind == "map"
        assert len(config.config.map.layers) == 1
        assert result.collection_id in config.config.map.layers[0].url

    with Session() as s:
        rows = s.execute(
            text(f"SELECT nom, population FROM public.{result.collection_id} ORDER BY nom")
        ).all()
        assert [tuple(r) for r in rows] == [("A", 100), ("B", 200)]


def test_csv_import_with_auto_detected_lat_lon(env):
    Session, tenant, user = env
    csv_content = b"nom,lat,lon\nParis,48.85,2.35\nLyon,45.76,4.83\n"
    with Session() as s:
        result = run_import(
            s, tenant_id=tenant.id, created_by=user.id, filename="villes.csv",
            content=csv_content, collection_title="Villes CSV",
            lat_field=None, lon_field=None,
        )
        s.commit()
        assert result.collection_id is not None
        assert result.item_id is not None


def test_corrupted_geojson_raises_without_creating_anything(env):
    Session, tenant, user = env
    with Session() as s:
        with pytest.raises(IngestionParseError):
            run_import(
                s, tenant_id=tenant.id, created_by=user.id, filename="broken.geojson",
                content=b"not json", collection_title="Casse",
                lat_field=None, lon_field=None,
            )
        s.rollback()
    with Session() as s:
        cols = collections_repo.list_visible_collections(
            s, tenant_id=tenant.id, user_id=user.id, is_admin=True
        )
        assert cols == []
```

- [ ] **Step 7: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_ingestion_importer.py -v -m postgis`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion.importer'` (ou skip si `CORE_TEST_DATABASE_URL` n'est pas défini localement — dans ce cas, vérifier au moins l'échec d'import via `uv run python -c "import app.ingestion.importer"`).

- [ ] **Step 8: Implémenter `importer.py`**

Créer `core/app/ingestion/importer.py` :

```python
"""Pipeline d'import (SP-6a) : table PostGIS + collection + item carte, à
partir d'un flux de (géométrie, propriétés) déjà parsé (app.ingestion.parsers).
Séparé de tasks.py pour rester testable sans procrastinate ni S3 (postgis
seulement) — mêmes fonctions internes qu'un admin enregistrant une collection
à la main (app.collections.routes.register_collection)."""
import math
import os
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.collections.ddl import apply_collection_ddl, quote_ident
from app.collections.extent import table_extent
from app.collections.introspection_pg import introspect_table
from app.configs import repository as configs_repo
from app.configs.schemas import BaseMap, BuilderConfig, MapConfig, MapLayer, MapView
from app.ingestion.parsers import IngestionParseError, parse_csv_latlon, parse_geojson
from app.items import repository as items_repo

# Doit rester synchronisé avec shell/src/map/basemaps.ts DEFAULT_BASEMAP.style.
_DEFAULT_BASEMAP_STYLE = "https://demotiles.maplibre.org/style.json"

_GEOM_TYPE_MAP = {
    "Point": "Point", "MultiPoint": "MultiPoint",
    "LineString": "LineString", "MultiLineString": "MultiLineString",
    "Polygon": "Polygon", "MultiPolygon": "MultiPolygon",
}


@dataclass
class ImportResult:
    collection_id: str
    item_id: str


def _pick_format(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith((".geojson", ".json")):
        return "geojson"
    if lower.endswith(".csv"):
        return "csv"
    raise IngestionParseError(f"format non supporté : {filename}")


def _sql_type_for(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "bigint"
    if isinstance(value, float):
        return "double precision"
    return "text"


def _zoom_for_extent(bbox: list[float]) -> float:
    span = max(bbox[2] - bbox[0], bbox[3] - bbox[1], 0.0001)
    # Approximation grossière (span=360° → zoom 0, chaque doublement du zoom
    # réduit le span de moitié) : suffisant pour un centrage initial
    # raisonnable, l'utilisateur ajuste ensuite dans l'éditeur de carte.
    return max(0.0, min(18.0, math.log2(360.0 / span)))


def run_import(
    session: Session, *, tenant_id: str, created_by: str, filename: str,
    content: bytes, collection_title: str,
    lat_field: str | None, lon_field: str | None,
) -> ImportResult:
    fmt = _pick_format(filename)
    if fmt == "geojson":
        rows = list(parse_geojson(content))
    else:
        rows = list(parse_csv_latlon(content, lat_field, lon_field))
    if not rows:
        raise IngestionParseError("le fichier ne contient aucune entité")

    # Colonnes : union des clés de propriétés rencontrées, type déduit de la
    # première valeur non nulle vue pour chaque clé (repli "text" si toujours
    # nulle). Propriétés nommées "id" ou "geom" entreraient en collision avec
    # les colonnes fixes ci-dessous — cas non géré en v1 (hors périmètre SP-6a).
    columns: dict[str, str] = {}
    for _geom, props in rows:
        for key, value in props.items():
            if key in columns or value is None:
                continue
            columns[key] = _sql_type_for(value)
    for _geom, props in rows:
        for key in props:
            columns.setdefault(key, "text")

    geom_types = {geom.geom_type for geom, _props in rows}
    single_type = next(iter(geom_types)) if len(geom_types) == 1 else None
    pg_geom_type = _GEOM_TYPE_MAP.get(single_type, "Geometry") if single_type else "Geometry"

    table_name = f"ingest_{uuid.uuid4().hex[:12]}"
    t = quote_ident(session, table_name)
    col_defs = ", ".join(
        f"{quote_ident(session, name)} {sql_type}" for name, sql_type in columns.items()
    )
    create_sql = f"CREATE TABLE public.{t} (id serial PRIMARY KEY"
    if col_defs:
        create_sql += f", {col_defs}"
    create_sql += f", geom geometry({pg_geom_type}, 4326))"
    session.execute(text(create_sql))

    col_names = list(columns.keys())
    insert_cols = ", ".join(quote_ident(session, name) for name in col_names)
    insert_cols_full = (insert_cols + ", " if insert_cols else "") + "geom"
    placeholders = ", ".join(f":{name}" for name in col_names)
    values_clause = (placeholders + ", " if placeholders else "") + "ST_GeomFromText(:geom_wkt, 4326)"
    insert_sql = f"INSERT INTO public.{t} ({insert_cols_full}) VALUES ({values_clause})"
    params = []
    for geom, props in rows:
        row_params = {name: props.get(name) for name in col_names}
        row_params["geom_wkt"] = geom.wkt
        params.append(row_params)
    session.execute(text(insert_sql), params)

    info = introspect_table(session, table_name)
    apply_collection_ddl(session, table_name)
    col = collections_repo.create_collection(
        session, tenant_id=tenant_id, owner_id=created_by, table_name=table_name,
        title=collection_title, description="", is_public=False,
        pk_column=info.pk_column, geometry_column=info.geometry_column,
        geometry_type=info.geometry_type, srid=info.srid,
    )

    bbox = table_extent(session, info)
    if bbox:
        center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        zoom = _zoom_for_extent(bbox)
    else:
        center, zoom = (2.4, 46.6), 5.0

    core_base_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=created_by,
        resource_type="map", title=collection_title,
    )
    config = BuilderConfig(
        kind="map",
        map=MapConfig(
            basemap=BaseMap(style=_DEFAULT_BASEMAP_STYLE),
            view=MapView(center=center, zoom=zoom),
            layers=[MapLayer(
                id=str(uuid.uuid4()), title=collection_title, visible=True,
                kind="feature", url=f"{core_base_url}/collections/{col.id}/items",
            )],
        ),
    )
    configs_repo.create_config(session, config, item_id=item.id)

    return ImportResult(collection_id=col.id, item_id=item.id)
```

- [ ] **Step 9: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_ingestion_importer.py -v -m postgis`
Expected: PASS (3/3) si `CORE_TEST_DATABASE_URL` est défini, sinon SKIP explicite (jamais d'échec silencieux).

- [ ] **Step 10: Écrire les tests qui échouent pour `tasks.py` (postgis)**

Créer `core/tests/test_ingestion_tasks.py` :

```python
"""Bout en bout : run_ingestion_task, connecteur procrastinate remplacé par
InMemoryConnector (pattern documenté procrastinate.testing) pour ne dépendre
d'aucun vrai worker en CI ; PostGIS réel pour les écritures du pipeline."""
import pytest
from procrastinate import testing
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.ingestion import repository as ingestion_repo
from app.ingestion import tasks as ingestion_tasks
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


class _FakeS3Client:
    def __init__(self, objects: dict[str, bytes]):
        self._objects = objects

    def get_object(self, Bucket, Key):  # noqa: N803 - signature boto3
        class _Body:
            def __init__(self, data: bytes):
                self._data = data

            def read(self) -> bytes:
                return self._data

        return {"Body": _Body(self._objects[Key])}


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
    monkeypatch.setenv("DATABASE_URL", str(pg_engine.url))
    in_memory = testing.InMemoryConnector()
    with ingestion_tasks.app.replace_connector(in_memory) as app:
        yield app, Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE ingestion_jobs, items, configs, config_revisions, "
            "collections, audit_log, users, tenants CASCADE"
        ))


def test_valid_geojson_marks_job_done_with_collection_and_item(env, monkeypatch):
    app, Session, tenant, user = env
    geojson = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":{"nom":"A"},"geometry":{"type":"Point","coordinates":[1.0,45.0]}}]}'
    )
    monkeypatch.setattr(
        ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({"k1": geojson})
    )
    with Session() as s:
        job = ingestion_repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k1",
            filename="villes.geojson", collection_title="Villes import",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id

    ingestion_tasks.run_ingestion_task.defer(job_id=job_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["ingestion"])

    with Session() as s:
        fetched = ingestion_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.status == "done"
        assert fetched.collection_id is not None
        assert fetched.item_id is not None


def test_corrupted_file_marks_job_error_not_zombie(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(
        ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({"k2": b"not json"})
    )
    with Session() as s:
        job = ingestion_repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k2",
            filename="broken.geojson", collection_title="Casse",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id

    ingestion_tasks.run_ingestion_task.defer(job_id=job_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["ingestion"])

    with Session() as s:
        fetched = ingestion_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.status == "error"
        assert fetched.error_message is not None


def test_missing_job_is_a_noop_not_a_crash(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({}))
    ingestion_tasks.run_ingestion_task.defer(job_id="does-not-exist", tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["ingestion"])  # ne doit pas lever
```

- [ ] **Step 11: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_ingestion_tasks.py -v -m postgis`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion.tasks'`.

- [ ] **Step 12: Implémenter `tasks.py`**

Créer `core/app/ingestion/tasks.py` :

```python
"""Tâche procrastinate (SP-6a) : orchestre téléchargement S3 → pipeline
d'import (app.ingestion.importer.run_import) → mise à jour du statut du job.
Toute erreur (parsing ou inattendue) marque le job "error", jamais de job
bloqué en pending/running ("zombie", critère d'acceptation SP-6a)."""
import logging
import os

import procrastinate

from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion import repository as ingestion_repo
from app.ingestion.importer import run_import
from app.ingestion.parsers import IngestionParseError
from app.ingestion.storage import download_object, make_s3_client

logger = logging.getLogger(__name__)


def _conninfo() -> str:
    # .get() avec repli, jamais os.environ[...] : ce module est importé
    # transitivement par app.main (via app.ingestion.routes, Task 4) dans
    # TOUTE la suite de tests, y compris les tests SQLite qui ne définissent
    # jamais DATABASE_URL — un KeyError ici casserait la collecte pytest
    # entière. Le repli n'est jamais utilisé pour de vrai (le worker/cœur
    # déployés reçoivent toujours DATABASE_URL via docker-compose).
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost/geostudio_dev")
    return database_url.replace("postgresql+psycopg://", "postgresql://")


app = procrastinate.App(connector=procrastinate.SyncPsycopgConnector(conninfo=_conninfo()))


def _make_s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _uploads_bucket() -> str:
    return os.environ.get("S3_UPLOADS_BUCKET", "geostudio-uploads")


@app.task(queue="ingestion")
def run_ingestion_task(job_id: str, tenant_id: str) -> None:
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    session_factory = make_session_factory(engine)

    with request_scoped_session(session_factory) as session:
        job = ingestion_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("ingestion job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        ingestion_repo.mark_running(session, job_id=job_id)
        filename, source_key, collection_title, lat_field, lon_field, created_by = (
            job.filename, job.source_key, job.collection_title,
            job.lat_field, job.lon_field, job.created_by,
        )

    try:
        s3 = _make_s3_client_from_env()
        content = download_object(s3, bucket=_uploads_bucket(), key=source_key)
        with request_scoped_session(session_factory) as session:
            result = run_import(
                session, tenant_id=tenant_id, created_by=created_by, filename=filename,
                content=content, collection_title=collection_title,
                lat_field=lat_field, lon_field=lon_field,
            )
        with request_scoped_session(session_factory) as session:
            ingestion_repo.mark_done(
                session, job_id=job_id,
                collection_id=result.collection_id, item_id=result.item_id,
            )
    except IngestionParseError as exc:
        with request_scoped_session(session_factory) as session:
            ingestion_repo.mark_error(session, job_id=job_id, error_message=str(exc))
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("ingestion job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            ingestion_repo.mark_error(
                session, job_id=job_id, error_message=f"erreur interne : {exc}"
            )
```

- [ ] **Step 13: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_ingestion_tasks.py -v -m postgis`
Expected: PASS (3/3) si `CORE_TEST_DATABASE_URL` est défini, sinon SKIP.

Run: `cd core && uv run pytest`
Expected: PASS (290 passed, 36 skipped postgis sans `CORE_TEST_DATABASE_URL` — 30 préexistants + 6 nouveaux, `test_ingestion_importer.py`/`test_ingestion_tasks.py` ; 326 passed, 0 skipped avec) — aucune régression.

Run: `cd core && uv run lint-imports`
Expected: PASS — `app.ingestion` importe `app.collections`/`app.configs`/`app.items`/`app.features` (transitivement, via un futur usage de `rls_scope` si besoin) sans violer les couches (il est positionné au-dessus d'eux).

- [ ] **Step 14: Service `worker` et bucket d'upload dans le compose**

Dans `docker-compose.yml`, ajouter `S3_UPLOADS_BUCKET: geostudio-uploads` à l'environnement du service `core` (après `S3_THUMBNAILS_BUCKET: geostudio-thumbnails`) :

```yaml
      S3_THUMBNAILS_BUCKET: geostudio-thumbnails
      S3_UPLOADS_BUCKET: geostudio-uploads
```

Ajouter un nouveau service `worker` juste après le service `core` :

```yaml
  # Worker d'ingestion (SP-6a) — même image que le cœur, process séparé
  # (procrastinate worker, file Postgres, pas de broker — arbitrage A5).
  worker:
    build: ./core
    command: >
      sh -c "procrastinate --app app.ingestion.tasks.app schema --apply &&
             procrastinate --app app.ingestion.tasks.app worker -q ingestion"
    environment:
      DATABASE_URL: postgresql+psycopg://gis:${PG_PASSWORD}@pgbouncer:6432/gis
      S3_ENDPOINT_URL: http://minio:9000
      S3_ACCESS_KEY: ${MINIO_USER}
      S3_SECRET_KEY: ${MINIO_PASSWORD}
      S3_UPLOADS_BUCKET: geostudio-uploads
      CORE_BASE_URL: ${CORE_BASE_URL:-http://localhost:8200}
    networks: [gis-net]
    depends_on: [pgbouncer, minio]
    restart: unless-stopped
```

Dans `.env.example`, ajouter après `S3_THUMBNAILS_BUCKET=geostudio-thumbnails` :

```
S3_UPLOADS_BUCKET=geostudio-uploads
```

- [ ] **Step 15: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/ingestion/storage.py core/app/ingestion/importer.py core/app/ingestion/tasks.py \
  core/pyproject.toml core/Dockerfile core/tests/test_ingestion_storage.py \
  core/tests/test_ingestion_importer.py core/tests/test_ingestion_tasks.py \
  docker-compose.yml .env.example
git commit -m "feat(core): pipeline d'import + worker procrastinate — table PostGIS, collection, item carte (SP-6a)"
```

---

## Task 4: API `/uploads/presign`, `/uploads`, `/uploads/{id}`

**Files:**
- Create: `core/app/ingestion/schemas.py`
- Create: `core/app/ingestion/routes.py`
- Modify: `core/app/main.py`
- Test: `core/tests/test_ingestion_routes.py`

**Interfaces:**
- Produces: `POST /uploads/presign` `{filename, contentType}` → `201 {uploadUrl, key}` ; `POST /uploads` `{key, filename, collectionTitle, latField?, lonField?}` → `201 {jobId}` ; `GET /uploads/{jobId}` → `{status, errorMessage, collectionId, itemId}` (404 hors tenant).
- Consumes: `app.ingestion.repository` (Task 1), `app.ingestion.tasks.run_ingestion_task` (Task 3), `app.ingestion.storage.{make_s3_client,ensure_uploads_bucket,generate_presigned_put_url}` (Task 3), `app.auth.dependency.get_current_user`, `app.audit.writer.write_audit`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `core/tests/test_ingestion_routes.py` :

```python
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}"


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: _FakeS3Client()
    deferred: list[tuple[str, str]] = []
    app.dependency_overrides[ingestion_routes.get_task_deferrer] = (
        lambda: (lambda job_id, tenant_id: deferred.append((job_id, tenant_id)))
    )
    client = TestClient(app)
    return client, Session, tenant, alice, deferred


def test_presign_returns_upload_url_and_key(env):
    client, *_ = env
    r = client.post("/uploads/presign", json={"filename": "villes.geojson", "contentType": "application/geo+json"})
    assert r.status_code == 200
    body = r.json()
    assert body["key"].endswith("-villes.geojson")
    assert body["uploadUrl"].startswith("https://minio.test/")


def test_create_upload_job_defers_task_and_returns_job_id(env):
    client, Session, tenant, alice, deferred = env
    r = client.post("/uploads", json={
        "key": "t/abc-villes.geojson", "filename": "villes.geojson",
        "collectionTitle": "Villes",
    })
    assert r.status_code == 201
    job_id = r.json()["jobId"]
    assert deferred == [(job_id, tenant.id)]

    r2 = client.get(f"/uploads/{job_id}")
    assert r2.status_code == 200
    assert r2.json() == {
        "status": "pending", "errorMessage": None, "collectionId": None, "itemId": None,
    }


def test_get_upload_job_404_for_unknown_job(env):
    client, *_ = env
    assert client.get("/uploads/does-not-exist").status_code == 404


def test_create_upload_job_is_audited(env):
    client, Session, tenant, alice, _ = env
    client.post("/uploads", json={
        "key": "t/abc.csv", "filename": "villes.csv", "collectionTitle": "Villes CSV",
        "latField": "y", "lonField": "x",
    })
    with Session() as s:
        from sqlalchemy import select
        from app.audit.models import AuditLog
        rows = s.scalars(select(AuditLog).where(AuditLog.action == "ingestion.job_create")).all()
        assert len(rows) == 1
        assert rows[0].payload["collectionTitle"] == "Villes CSV"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_ingestion_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion.schemas'` (ni `routes`).

- [ ] **Step 3: Implémenter `schemas.py`**

Créer `core/app/ingestion/schemas.py` :

```python
from pydantic import BaseModel, Field


class PresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    contentType: str = Field(min_length=1, max_length=100)


class PresignResponse(BaseModel):
    uploadUrl: str
    key: str


class IngestionJobCreate(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    collectionTitle: str = Field(min_length=1)
    latField: str | None = None
    lonField: str | None = None


class IngestionJobCreated(BaseModel):
    jobId: str


class IngestionJobStatus(BaseModel):
    status: str
    errorMessage: str | None
    collectionId: str | None
    itemId: str | None
```

- [ ] **Step 4: Implémenter `routes.py`**

Créer `core/app/ingestion/routes.py` :

```python
import os
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.ingestion import repository as repo
from app.ingestion.schemas import (
    IngestionJobCreate, IngestionJobCreated, IngestionJobStatus,
    PresignRequest, PresignResponse,
)
from app.ingestion.storage import (
    ensure_uploads_bucket, generate_presigned_put_url,
)
from app.ingestion.tasks import run_ingestion_task
from app.users.models import User

router = APIRouter()


def get_s3_client():  # overridé dans main.py quand S3_* est configuré
    raise RuntimeError("S3 client dependency not configured")


def get_uploads_bucket() -> str:
    return os.environ.get("S3_UPLOADS_BUCKET", "geostudio-uploads")


def get_task_deferrer() -> Callable[[str, str], None]:
    def deferrer(job_id: str, tenant_id: str) -> None:
        run_ingestion_task.defer(job_id=job_id, tenant_id=tenant_id)
    return deferrer


@router.post("/uploads/presign", response_model=PresignResponse)
def presign_upload(
    body: PresignRequest,
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_uploads_bucket),
) -> PresignResponse:
    ensure_uploads_bucket(s3, bucket)
    key = f"{user.tenant_id}/{uuid.uuid4().hex}-{body.filename}"
    url = generate_presigned_put_url(
        s3, bucket=bucket, key=key, content_type=body.contentType
    )
    return PresignResponse(uploadUrl=url, key=key)


@router.post("/uploads", response_model=IngestionJobCreated, status_code=201)
def create_upload_job(
    body: IngestionJobCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> IngestionJobCreated:
    job = repo.create_job(
        session, tenant_id=user.tenant_id, created_by=user.id, source_key=body.key,
        filename=body.filename, collection_title=body.collectionTitle,
        lat_field=body.latField, lon_field=body.lonField,
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="ingestion.job_create", object_type="ingestion_job", object_id=job.id,
        payload={"filename": body.filename, "collectionTitle": body.collectionTitle},
    )
    # Commit avant de déférer : procrastinate insère la tâche via sa propre
    # connexion, hors de cette transaction SQLAlchemy — un worker pourrait la
    # ramasser avant le commit implicite de fin de requête et ne pas trouver
    # la ligne ingestion_jobs (job "zombie", l'inverse du critère
    # d'acceptation SP-6a). Commit explicite ici pour que la ligne soit
    # visible avant que la tâche n'existe.
    session.commit()
    defer_task(job.id, user.tenant_id)
    return IngestionJobCreated(jobId=job.id)


@router.get("/uploads/{job_id}", response_model=IngestionJobStatus)
def get_upload_job(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> IngestionJobStatus:
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return IngestionJobStatus(
        status=job.status, errorMessage=job.error_message,
        collectionId=job.collection_id, itemId=job.item_id,
    )
```

- [ ] **Step 5: Câbler dans `main.py`**

Dans `core/app/main.py`, ajouter l'import (ordre alphabétique, après `from app.features import routes as features_routes`) :

```python
from app.ingestion import routes as ingestion_routes
```

Ajouter `app.include_router(ingestion_routes.router)` après `app.include_router(features_routes.router)` (actuellement ligne 55).

Après le bloc S3 des vignettes (actuellement lignes 57-67), ajouter :

```python
    s3_uploads_bucket = os.environ.get("S3_UPLOADS_BUCKET", "geostudio-uploads")
    if s3_endpoint and s3_access_key and s3_secret_key:
        from app.ingestion.storage import make_s3_client

        app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: make_s3_client(
            endpoint_url=s3_endpoint, access_key=s3_access_key, secret_key=s3_secret_key,
        )
        app.dependency_overrides[ingestion_routes.get_uploads_bucket] = lambda: s3_uploads_bucket
```

(Ce bloc partage les variables `s3_endpoint`/`s3_access_key`/`s3_secret_key` déjà lues juste au-dessus pour les vignettes — ne pas les relire.)

- [ ] **Step 6: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_ingestion_routes.py -v`
Expected: PASS (4/4)

Run: `cd core && uv run pytest`
Expected: PASS (294 passed, 36 skipped postgis sans `CORE_TEST_DATABASE_URL` ; 330 passed, 0 skipped avec) — aucune régression.

Run: `cd core && uv run lint-imports`
Expected: PASS.

- [ ] **Step 7: Régénérer `core-schema.d.ts` (évite le drift CI `api-types-drift`)**

Ces nouvelles routes/schémas Pydantic changent l'OpenAPI exposé par le
cœur — le job CI `api-types-drift` (`.github/workflows/ci.yml`) régénère
`core/openapi.json` puis `shell/src/api/generated/core-schema.d.ts` et échoue
sur tout diff non commité. Régénérer maintenant, comme documenté dans
`shell/package.json` (`gen:api-types`) :

```bash
cd core && PYTHONPATH=. uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Run: `cd shell && npm run build`
Expected: PASS — `core-schema.d.ts` régénéré compile toujours (les nouveaux
schémas `Ingestion*`/`Presign*` s'ajoutent sans toucher les types existants
consommés par le shell).

- [ ] **Step 8: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/ingestion/schemas.py core/app/ingestion/routes.py core/app/main.py \
  core/tests/test_ingestion_routes.py core/openapi.json \
  shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): API /uploads/presign, /uploads, /uploads/{id} (SP-6a)"
```

---

## Task 5: Shell — bouton « Importer un fichier »

**Files:**
- Modify: `shell/src/api/types.ts` (interface `ItemClient`)
- Modify: `shell/src/api/itemClient.ts`
- Create: `shell/src/shell/ImportFileButton.tsx`
- Modify: `shell/src/shell/AppLayout.tsx`
- Test: `shell/src/shell/ImportFileButton.test.tsx`

**Interfaces:**
- Produces: `ItemClient.presignUpload(filename, contentType) -> Promise<{uploadUrl, key}>` ; `ItemClient.uploadToPresignedUrl(url, file) -> Promise<void>` ; `ItemClient.createIngestionJob(input) -> Promise<{jobId}>` ; `ItemClient.getIngestionJob(jobId) -> Promise<{status, errorMessage, collectionId, itemId}>` ; composant `<ImportFileButton />`.
- Consumes: `useItemClient` (`shell/src/api/hooks.ts`, existant), `Dialog`/`Button`/`Input` (`shell/src/ui/`, existants), API cœur Task 4.

- [ ] **Step 1: Étendre l'interface `ItemClient`**

Dans `shell/src/api/types.ts`, dans `interface ItemClient` (actuellement lignes 95-118), ajouter avant la ligne finale `}` :

```ts
  presignUpload(filename: string, contentType: string): Promise<{ uploadUrl: string; key: string }>;
  uploadToPresignedUrl(url: string, file: File): Promise<void>;
  createIngestionJob(input: {
    key: string; filename: string; collectionTitle: string;
    latField?: string; lonField?: string;
  }): Promise<{ jobId: string }>;
  getIngestionJob(jobId: string): Promise<{
    status: "pending" | "running" | "done" | "error";
    errorMessage: string | null;
    collectionId: string | null;
    itemId: string | null;
  }>;
```

- [ ] **Step 2: Écrire les tests qui échouent**

Créer `shell/src/shell/ImportFileButton.test.tsx` :

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ImportFileButton } from "./ImportFileButton";

function MapProbe() {
  const { pk } = useParams();
  return <div>map-{pk}</div>;
}

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          {children}
          <Routes>
            <Route path="/maps/:pk" element={<MapProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

function geojsonFile() {
  return new File(
    ['{"type":"FeatureCollection","features":[]}'],
    "villes.geojson",
    { type: "application/geo+json" },
  );
}

test("uploads a file and navigates to the created map once the job is done", async () => {
  server.use(
    http.post("https://core.test/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-1", key: "t/abc-villes.geojson" })),
    http.put("https://minio.test/upload-1", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/uploads", () => HttpResponse.json({ jobId: "job-1" })),
    http.get("https://core.test/uploads/job-1", () =>
      HttpResponse.json({ status: "done", errorMessage: null, collectionId: "ingest_abc", itemId: "42" })),
  );

  render(<Harness><ImportFileButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), geojsonFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByText("map-42")).toBeInTheDocument());
});

test("shows the job's error message and lets the user retry", async () => {
  server.use(
    http.post("https://core.test/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-2", key: "t/def-broken.geojson" })),
    http.put("https://minio.test/upload-2", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/uploads", () => HttpResponse.json({ jobId: "job-2" })),
    http.get("https://core.test/uploads/job-2", () =>
      HttpResponse.json({ status: "error", errorMessage: "JSON invalide", collectionId: null, itemId: null })),
  );

  render(<Harness><ImportFileButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), geojsonFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Casse");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("JSON invalide"));
  expect(screen.getByRole("button", { name: "Importer" })).toBeEnabled();
});

test("shows manual lat/lon selectors when a CSV's columns cannot be auto-detected", async () => {
  render(<Harness><ImportFileButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  const csv = new File(["nom,valeur\nA,1\n"], "data.csv", { type: "text/csv" });
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), csv);

  await waitFor(() => expect(screen.getByLabelText("Colonne latitude")).toBeInTheDocument());
  expect(screen.getByLabelText("Colonne longitude")).toBeInTheDocument();
});

test("does not show manual lat/lon selectors when a CSV's columns are auto-detectable", async () => {
  render(<Harness><ImportFileButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  const csv = new File(["nom,lat,lon\nParis,48.85,2.35\n"], "villes.csv", { type: "text/csv" });
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), csv);

  await waitFor(() => expect(screen.getByLabelText("Titre de la collection")).toBeInTheDocument());
  expect(screen.queryByLabelText("Colonne latitude")).not.toBeInTheDocument();
});
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/ImportFileButton.test.tsx`
Expected: FAIL — `Cannot find module './ImportFileButton'`.

- [ ] **Step 4: Implémenter les méthodes `itemClient.ts`**

Dans `shell/src/api/itemClient.ts`, à l'intérieur de `createItemClient` (après la définition de `request<T>`, avant le `return` final de l'objet implémentant `ItemClient` — chercher le dernier champ retourné, ex. `deleteFeature`, et ajouter juste avant l'accolade fermante du `return {`) :

```ts
    async presignUpload(filename: string, contentType: string) {
      return request<{ uploadUrl: string; key: string }>(
        "POST", "/uploads/presign", { filename, contentType },
      );
    },
    async uploadToPresignedUrl(url: string, file: File) {
      const res = await fetch(url, { method: "PUT", body: file });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    },
    async createIngestionJob(input) {
      return request<{ jobId: string }>("POST", "/uploads", input);
    },
    async getIngestionJob(jobId: string) {
      return request<{
        status: "pending" | "running" | "done" | "error";
        errorMessage: string | null;
        collectionId: string | null;
        itemId: string | null;
      }>("GET", `/uploads/${jobId}`);
    },
```

(`request<T>` existe déjà dans ce fichier — voir son usage pour `createConfigItem`/`updateItem` etc. juste au-dessus dans le même objet retourné.)

- [ ] **Step 5: Implémenter `ImportFileButton.tsx`**

Créer `shell/src/shell/ImportFileButton.tsx` :

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useItemClient } from "../api/hooks";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Dialog } from "../ui/dialog";

type Phase = "form" | "uploading" | "polling" | "error";

const LAT_NAMES = ["lat", "latitude", "y"];
const LON_NAMES = ["lon", "lng", "longitude", "x"];

function detectLatLon(headers: string[]): boolean {
  const byLower = new Set(headers.map((h) => h.trim().toLowerCase()));
  const hasLat = LAT_NAMES.some((n) => byLower.has(n));
  const hasLon = LON_NAMES.some((n) => byLower.has(n));
  return hasLat && hasLon;
}

export function ImportFileButton() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [csvHeaders, setCsvHeaders] = useState<string[] | null>(null);
  const [latField, setLatField] = useState("");
  const [lonField, setLonField] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [error, setError] = useState("");
  const client = useItemClient();
  const navigate = useNavigate();

  function close() {
    setOpen(false);
    setFile(null);
    setTitle("");
    setCsvHeaders(null);
    setLatField("");
    setLonField("");
    setPhase("form");
    setError("");
  }

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setCsvHeaders(null);
    if (f && f.name.toLowerCase().endsWith(".csv")) {
      const firstLine = (await f.slice(0, 4096).text()).split(/\r?\n/)[0] ?? "";
      const headers = firstLine.split(",").map((h) => h.trim());
      if (!detectLatLon(headers)) setCsvHeaders(headers);
    }
  }

  const needsManualLatLon = csvHeaders !== null;

  async function poll(jobId: string) {
    for (;;) {
      const job = await client.getIngestionJob(jobId);
      if (job.status === "done" && job.itemId) {
        close();
        navigate(`/maps/${job.itemId}`);
        return;
      }
      if (job.status === "error") {
        setPhase("error");
        setError(job.errorMessage ?? "Échec de l'import.");
        return;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    if (needsManualLatLon && (!latField || !lonField)) return;
    setPhase("uploading");
    setError("");
    try {
      const { uploadUrl, key } = await client.presignUpload(
        file.name, file.type || "application/octet-stream",
      );
      await client.uploadToPresignedUrl(uploadUrl, file);
      const { jobId } = await client.createIngestionJob({
        key, filename: file.name, collectionTitle: title.trim(),
        latField: needsManualLatLon ? latField : undefined,
        lonField: needsManualLatLon ? lonField : undefined,
      });
      setPhase("polling");
      await poll(jobId);
    } catch {
      setPhase("error");
      setError("Échec de l'import.");
    }
  }

  const busy = phase === "uploading" || phase === "polling";

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Importer un fichier
      </Button>
      <Dialog open={open} onClose={close} title="Importer un fichier">
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Fichier à importer
            <input
              aria-label="Fichier à importer"
              type="file"
              accept=".geojson,.json,.csv"
              onChange={onFileChange}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Titre de la collection
            <Input
              aria-label="Titre de la collection"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          {needsManualLatLon && (
            <>
              <label className="flex flex-col gap-1 text-sm">
                Colonne latitude
                <select
                  aria-label="Colonne latitude"
                  className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                  value={latField}
                  onChange={(e) => setLatField(e.target.value)}
                >
                  <option value="">—</option>
                  {csvHeaders!.map((h) => <option key={h} value={h}>{h}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                Colonne longitude
                <select
                  aria-label="Colonne longitude"
                  className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                  value={lonField}
                  onChange={(e) => setLonField(e.target.value)}
                >
                  <option value="">—</option>
                  {csvHeaders!.map((h) => <option key={h} value={h}>{h}</option>)}
                </select>
              </label>
            </>
          )}
          {phase === "error" && (
            <p role="alert" className="text-sm text-red-600">{error}</p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Annuler
            </Button>
            <Button type="submit" size="sm" disabled={busy}>
              {phase === "uploading" ? "Envoi…" : phase === "polling" ? "Import en cours…" : "Importer"}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
```

- [ ] **Step 6: Câbler dans `AppLayout.tsx`**

Dans `shell/src/shell/AppLayout.tsx`, ajouter l'import après `import { NewItemButton } from "./NewItemButton";` :

```tsx
import { ImportFileButton } from "./ImportFileButton";
```

Ajouter `<ImportFileButton />` juste après `<NewItemButton />` (actuellement ligne 13) :

```tsx
          <NewItemButton />
          <ImportFileButton />
```

- [ ] **Step 7: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/shell/ImportFileButton.test.tsx`
Expected: PASS (4/4)

Run: `cd shell && npm run test && npm run build`
Expected: PASS (398+ tests).

- [ ] **Step 8: Commit**

```bash
cd shell
git add src/api/types.ts src/api/itemClient.ts src/shell/ImportFileButton.tsx \
  src/shell/ImportFileButton.test.tsx src/shell/AppLayout.tsx
git commit -m "feat(shell): bouton Importer un fichier — upload présigné, poll du job, redirection carte (SP-6a)"
```

---

## Task 6: E2E — spec « importer un GeoJSON »

**Files:**
- Create: `shell/e2e/ingestion.spec.ts`

**Interfaces:**
- Consumes: tout SP-6a (Tasks 1-5). Étend `mockCore` (`shell/e2e/mocks.ts`) via des routes locales à la spec, même patron que `seedExprBoundButton` dans `expr-bindings.spec.ts` (SP-5c) — pas de modification de `mocks.ts` partagé.

- [ ] **Step 1: Écrire la spec**

Créer `shell/e2e/ingestion.spec.ts` :

```ts
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

async function mockIngestionFlow(page: Page) {
  let jobPolls = 0;
  await page.route("**/uploads/presign", async (route) => {
    await route.fulfill({
      json: { uploadUrl: "https://minio.test/upload-1", key: "t/abc-villes.geojson" },
    });
  });
  await page.route("https://minio.test/upload-1", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "job-1" } });
  });
  await page.route("**/uploads/job-1", async (route) => {
    jobPolls += 1;
    if (jobPolls < 2) {
      await route.fulfill({
        json: { status: "pending", errorMessage: null, collectionId: null, itemId: null },
      });
    } else {
      await route.fulfill({
        json: { status: "done", errorMessage: null, collectionId: "ingest_abc", itemId: "78" },
      });
    }
  });
  await page.route("https://core.test/items/78", async (route) => {
    await route.fulfill({
      json: {
        pk: "78", resourceType: "map", title: "Villes importées", abstract: "", owner: "mockuser",
        thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: false,
      },
    });
  });
  await page.route("**/configs/by-item/**", async (route) => {
    if (!route.request().url().endsWith("/78") || route.request().method() !== "GET") {
      return route.fallback();
    }
    await route.fulfill({
      json: {
        id: "cfg-78", itemId: "78", kind: "map",
        config: {
          kind: "map", theme: {}, dataSources: [],
          map: {
            basemap: { style: "https://demotiles.maplibre.org/style.json" },
            view: { center: [1.5, 45.5], zoom: 10 },
            layers: [{
              id: "l1", title: "Villes importées", visible: true, kind: "feature",
              url: "https://core.test/collections/ingest_abc/items",
            }],
          },
        },
      },
    });
  });
}

test("importer un GeoJSON crée une carte accessible sans intervention manuelle", async ({ page }) => {
  await mockCore(page);
  await mockIngestionFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Importer un fichier" }).click();
  await page.getByLabel("Fichier à importer").setInputFiles({
    name: "villes.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from('{"type":"FeatureCollection","features":[]}'),
  });
  await page.getByLabel("Titre de la collection").fill("Villes importées");
  await page.getByRole("button", { name: "Importer" }).click();

  await expect(page).toHaveURL(/\/maps\/78$/, { timeout: 10_000 });
});

test("un job en erreur affiche le message et permet de recommencer", async ({ page }) => {
  await mockCore(page);
  await page.route("**/uploads/presign", async (route) => {
    await route.fulfill({
      json: { uploadUrl: "https://minio.test/upload-2", key: "t/def-broken.geojson" },
    });
  });
  await page.route("https://minio.test/upload-2", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "job-2" } });
  });
  await page.route("**/uploads/job-2", async (route) => {
    await route.fulfill({
      json: { status: "error", errorMessage: "JSON invalide", collectionId: null, itemId: null },
    });
  });
  await page.goto("/");

  await page.getByRole("button", { name: "Importer un fichier" }).click();
  await page.getByLabel("Fichier à importer").setInputFiles({
    name: "broken.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from("not json"),
  });
  await page.getByLabel("Titre de la collection").fill("Casse");
  await page.getByRole("button", { name: "Importer" }).click();

  await expect(page.getByRole("alert")).toHaveText("JSON invalide");
  await expect(page.getByRole("button", { name: "Importer" })).toBeEnabled();
});
```

- [ ] **Step 2: Lancer la spec**

Run: `cd shell && npx playwright test ingestion.spec.ts`
Expected: PASS. Si le premier test échoue sur le timing du poll (2 requêtes GET `/uploads/job-1` avant `done`), vérifier que `jobPolls` s'incrémente bien à chaque appel intercepté et ajuster le nombre de tours si le composant poll à un rythme différent de celui supposé — ne pas modifier `ImportFileButton.tsx` sans avoir d'abord confirmé via `page.on("request", ...)` combien de polls ont réellement lieu.

- [ ] **Step 3: Lancer la suite E2E complète**

Run: `cd shell && npm run e2e`
Expected: PASS — 18 specs vertes (17 existantes + `ingestion.spec.ts`).

- [ ] **Step 4: Commit**

```bash
cd shell
git add e2e/ingestion.spec.ts
git commit -m "test(shell): e2e — importer un GeoJSON crée une carte accessible sans intervention manuelle (SP-6a)"
```

---

## Couverture spec → tâches (auto-vérification)

- §2 architecture (schéma, module `core/app/ingestion/`, service `worker`) → Tasks 1, 3, 4.
- §3 modèle de données `ingestion_jobs` → Task 1.
- §4 API (`presign`, `create`, `get`) → Task 4.
- §5 parsing GeoJSON/CSV, fail-fast, détection lat/lon → Task 2.
- §6 pipeline PostGIS + collection + item carte → Task 3.
- §7 UI shell minimale (formulaire, poll, sélecteurs lat/lon manuels) → Task 5.
- §8 permissions (tout utilisateur authentifié) → Task 4 (pas de `_require_admin`, contrairement à `register_collection`).
- §9 tests (unitaires parseurs, intégration postgis, API, shell, E2E) → Tasks 1-6, chacune sa propre stratégie de test conforme à §9.
- §10 hors périmètre (GeoPackage/Shapefile, CRS non-WGS84, suivi temps réel, PMTiles, ajout à une collection existante) → non traité, confirmé absent de toute tâche.
- §11 critères d'acceptation → Task 6 (E2E golden path + erreur), Task 3 (fail-fast sans zombie, test dédié `test_missing_job_is_a_noop_not_a_crash` et `test_corrupted_file_marks_job_error_not_zombie`).
