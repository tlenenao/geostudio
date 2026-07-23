# SP-6b — Ingestion v1 : GeoPackage et Shapefile zippé (pyogrio) : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un utilisateur authentifié importe un GeoPackage (`.gpkg`) ou un Shapefile zippé (`.zip`) depuis le shell — y compris en CRS projeté (reprojeté automatiquement en WGS84) et avec plusieurs couches (sélection forcée avant l'import) — et obtient une carte prête à consulter, exactement comme pour GeoJSON/CSV en SP-6a. Le critère M4 de la feuille de route (« GPKG 50 000 entités → carte en <5 min ») est validé par un test dédié.

**Architecture:** Ajout net sur l'infrastructure SP-6a (mêmes tables `ingestion_jobs`, même API `/uploads/*`, même pipeline `run_import`, même worker `procrastinate`) — pas de refactor. Deux nouveaux parseurs (`parse_gpkg`, `parse_shapefile_zip`) basés sur `pyogrio` (GDAL/GEOS/PROJ embarqués dans les wheels, aucun paquet système). Un GeoPackage/Shapefile peut avoir plusieurs couches : un nouvel endpoint `POST /uploads/inspect`, appelé par le shell juste après l'upload S3 et avant la création du job, liste les couches ; le shell affiche un sélecteur seulement si nécessaire (>1 couche). Le CRS source (souvent ≠ WGS84 pour ces formats) est reprojeté via `pyproj` ; un CRS non résolu échoue net (fail-fast, même doctrine que SP-6a).

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic/`pyogrio`/`pyproj`/`numpy` (Tasks 1-5), React 19 + TypeScript + Vitest/MSW (Task 6), Playwright (Task 7, `VITE_AUTH_MODE=mock`).

## Global Constraints

- **Ajout net sur SP-6a** (cf. `docs/superpowers/specs/2026-07-12-sp6b-ingestion-gpkg-shapefile-design.md`) : mêmes tables, même API `/uploads/*`, même pipeline `run_import`, même worker. Aucun refactor du code SP-6a existant au-delà des points listés ici.
- **Décisions produit verrouillées** (réponses de Tanguy, 2026-07-12, ne pas re-débattre) :
  - GeoPackage/Shapefile multi-couches → le shell **liste les couches et force une sélection** (pas d'auto-sélection de la 1ʳᵉ couche, pas d'import multi-collections en un job).
  - CRS non-WGS84 → **reprojection automatique via `pyproj` pour tout CRS résolu** ; **fail-fast** si le CRS est absent ou non reconnu (pas de liste blanche de CRS courants à maintenir).
  - Le critère **M4** de la feuille de route (GPKG 50k entités → carte en <5 min) est **validé dans ce plan** (Task 5), pas différé à SP-6c.
- **Dépendances nouvelles** : `pyogrio>=0.9`, `pyproj>=3.6`. Vérifié manuellement (2026-07-12, `pyogrio==0.13.0`/`pyproj==3.7.2`) : wheels manylinux, GDAL/GEOS/PROJ embarqués, **aucun paquet système à ajouter** au `Dockerfile` (`uv pip install pyogrio pyproj` suffit, testé en dehors du conteneur). `numpy` est déjà tiré transitivement par `shapely`/`pyogrio` (présent depuis SP-6a) — pas d'entrée `pyproject.toml` dédiée.
- **`layer_name` ignoré par GeoJSON/CSV** — même précédent que `lat_field`/`lon_field`, déjà ignorés par la branche `geojson` de `run_import` en SP-6a.
- **Tous les paramètres nouveaux ont un défaut `None`** (`repository.create_job(..., layer_name=None)`, `importer.run_import(..., layer_name=None)`, `parsers.parse_gpkg(content, layer_name=None)`, `parsers.parse_shapefile_zip(content, layer_name=None)`) : aucun appelant existant (`routes.py`, `tasks.py`, tests SP-6a) ne casse tant que sa propre tâche ne l'a pas mis à jour explicitement. Ceci est une déviation volontaire du style strict de `lat_field`/`lon_field` (kwargs obligatoires en SP-6a) — justifiée ici pour ne pas casser le build entre tâches sur un module déjà en production (SP-6a est mergé sur `dev`), contrairement à SP-6a où Task 1 précédait la création de son unique appelant (Task 4) dans le même plan.
- **Fail-fast** (doctrine SP-6a inchangée) : toute géométrie, couche ou CRS invalide fait échouer **tout** le job — jamais d'import partiel silencieux ; le message devient `ingestion_jobs.error_message` tel quel.
- **`force_2d=True`** à la lecture pyogrio : toute coordonnée Z est tronquée silencieusement (documenté §10 du design, hors périmètre — cohérent avec la table PostGIS 2D créée par `run_import`, inchangée depuis SP-6a).
- **Aucune fixture binaire committée** : les GPKG/Shapefile de test sont synthétisés en mémoire par les tests eux-mêmes via `pyogrio.raw.write()` (`tmp_path` pytest), jamais de `.gpkg`/`.zip` versionné dans le dépôt.
- **Pas de découpage en lots pour l'insertion PostGIS** : benchmark manuel (psycopg3 `executemany`, 50 000 lignes point+2 colonnes contre un PostGIS réel jetable) — 0,8 s en un seul appel, 0,67-0,68 s en lots de 2000/5000. L'insertion actuelle de `run_import` (un seul appel `session.execute(text(...), params)`, inchangée depuis SP-6a) n'est pas le goulot pour le volume visé par M4 — ne pas ajouter de complexité de batching sans bénéfice mesuré (YAGNI).
- Aucune régression : `cd core && uv run pytest` (302+ tests SP-6a de base) et `cd shell && npm run test` (398+ tests) + `npm run build` verts après chaque tâche ; `cd shell && npm run e2e` vert après la Task 7 (19 specs : 18 existantes + la nouvelle).
- Docs et messages utilisateur en français ; code/identifiants en anglais (champs Python en camelCase côté schémas Pydantic exposés en API, comme le reste du cœur). TDD systématique ; commits conventional en français.
- `pyogrio` et `pyproj` sont de nouvelles dépendances : le `Dockerfile` du cœur maintient sa propre liste `uv pip install` **à la main**, en plus de `pyproject.toml` — toute tâche qui ajoute une dépendance à `pyproject.toml` DOIT aussi l'ajouter au Dockerfile, sous peine de crash-loop du conteneur (note déjà présente en tête du Dockerfile, respectée depuis SP-1a).
- `pyogrio`/`pyproj` sont des libs récentes pour ce projet : si un nom de paramètre exact ne correspond pas à la version réellement installée par `uv sync`, consulter `.venv/lib/*/site-packages/pyogrio/`/`pyproj/` directement plutôt que de deviner plus avant. Les signatures et comportements cités dans ce plan ont été vérifiés manuellement le 2026-07-12 contre `pyogrio==0.13.0`/`pyproj==3.7.2`/`shapely==2.1.2` (mêmes planchers `>=` que ceux fixés au `pyproject.toml`).

---

## Task 1: `ingestion_jobs.layer_name` — migration, modèle, repository

**Files:**
- Create: `core/alembic/versions/0010_ingestion_jobs_layer_name.py`
- Modify: `core/app/ingestion/models.py`
- Modify: `core/app/ingestion/repository.py`
- Modify: `core/tests/test_ingestion_repository.py`

**Interfaces:**
- Produces: `IngestionJob.layer_name: str | None` ; `repository.create_job(session, *, tenant_id, created_by, source_key, filename, collection_title, lat_field, lon_field, layer_name=None) -> IngestionJob` (nouveau kwarg optionnel, défaut `None`, appelants existants inchangés).
- Consumes: rien de nouveau — extension de l'existant SP-6a.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `core/tests/test_ingestion_repository.py` (fichier existant, laisser les 3 tests actuels inchangés) :

```python
def test_create_job_stores_layer_name():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="villes.gpkg", collection_title="Villes",
            lat_field=None, lon_field=None, layer_name="villes",
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        fetched = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.layer_name == "villes"


def test_create_job_defaults_layer_name_to_none():
    Session, tenant, user = _env()
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k",
            filename="villes.geojson", collection_title="Villes",
            lat_field=None, lon_field=None,
        )
        s.commit()
        assert job.layer_name is None
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_ingestion_repository.py -v`
Expected: FAIL — `TypeError: create_job() got an unexpected keyword argument 'layer_name'` sur le premier nouveau test ; le second échoue aussi (`layer_name` inconnu de `IngestionJob`).

- [ ] **Step 3: Migration + modèle**

Créer `core/alembic/versions/0010_ingestion_jobs_layer_name.py` :

```python
"""ingestion_jobs.layer_name (SP-6b — GeoPackage/Shapefile multi-couches)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs", sa.Column("layer_name", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("ingestion_jobs", "layer_name")
```

Dans `core/app/ingestion/models.py`, ajouter la colonne juste après `lon_field` :

```python
    lat_field: Mapped[str | None] = mapped_column(String, nullable=True)
    lon_field: Mapped[str | None] = mapped_column(String, nullable=True)
    layer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Step 4: Repository**

Dans `core/app/ingestion/repository.py`, modifier `create_job` :

```python
def create_job(
    session: Session, *, tenant_id: str, created_by: str, source_key: str,
    filename: str, collection_title: str,
    lat_field: str | None, lon_field: str | None, layer_name: str | None = None,
) -> IngestionJob:
    job = IngestionJob(
        id=uuid.uuid4().hex, tenant_id=tenant_id, created_by=created_by,
        status="pending", source_key=source_key, filename=filename,
        collection_title=collection_title, lat_field=lat_field, lon_field=lon_field,
        layer_name=layer_name,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job
```

Le reste du fichier (`get_job`, `mark_running`, `mark_done`, `mark_error`) est inchangé.

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_ingestion_repository.py -v`
Expected: 5 passed (3 existants + 2 nouveaux).

- [ ] **Step 6: Suite complète + commit**

Run: `cd core && uv run pytest`
Expected: tous les tests SP-6a passent toujours (aucune régression — `layer_name` optionnel n'affecte aucun appelant existant).

```bash
git add core/alembic/versions/0010_ingestion_jobs_layer_name.py \
        core/app/ingestion/models.py core/app/ingestion/repository.py \
        core/tests/test_ingestion_repository.py
git commit -m "feat(core): ingestion_jobs.layer_name (SP-6b)"
```

---

## Task 2: Dépendances `pyogrio`/`pyproj` + parseurs GeoPackage/Shapefile zippé

**Files:**
- Modify: `core/pyproject.toml`
- Modify: `core/Dockerfile`
- Modify: `core/app/ingestion/parsers.py`
- Modify: `core/tests/test_ingestion_parsers.py`

**Interfaces:**
- Produces: `parsers.LayerInfo` (dataclass : `name: str`, `feature_count: int`, `geometry_type: str`) ; `parsers.list_layers(content: bytes, filename: str) -> list[LayerInfo]` (lève `ValueError` si le format n'est ni `.gpkg` ni `.zip`, `IngestionParseError` si le fichier est illisible) ; `parsers.parse_gpkg(content: bytes, layer_name: str | None = None) -> Iterator[tuple[BaseGeometry, dict]]` ; `parsers.parse_shapefile_zip(content: bytes, layer_name: str | None = None) -> Iterator[tuple[BaseGeometry, dict]]`.
- Consumes: `parsers.IngestionParseError` (existant, SP-6a).

- [ ] **Step 1: Dépendances**

Dans `core/pyproject.toml`, ajouter à `dependencies` (après `"shapely>=2.0"`) :

```toml
    "shapely>=2.0",
    "procrastinate>=2.0",
    "pyogrio>=0.9",
    "pyproj>=3.6",
```

Dans `core/Dockerfile`, ajouter les deux paquets à la ligne `uv pip install --system --no-cache` :

```dockerfile
RUN uv pip install --system --no-cache \
    "fastapi>=0.111" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" \
    "pydantic>=2.7" "httpx>=0.27" "psycopg[binary]>=3.1" \
    "alembic>=1.13" "pyjwt[crypto]>=2.8" "boto3>=1.34" "python-multipart>=0.0.9" \
    "mcp>=1.12" "shapely>=2.0" "procrastinate>=2.0" "pyogrio>=0.9" "pyproj>=3.6"
```

Run: `cd core && uv sync`
Expected: résolution réussie, `pyogrio`/`pyproj` installés (wheels manylinux — pas de compilation, quelques secondes).

Run: `cd core && uv run python -c "import pyogrio, pyproj; print(pyogrio.__version__, pyproj.__version__)"`
Expected: affiche les versions installées, aucune erreur d'import (confirme qu'aucune lib système GDAL n'est requise).

- [ ] **Step 2: Écrire les tests qui échouent**

Ajouter en tête de `core/tests/test_ingestion_parsers.py` (fichier existant — remplacer le bloc d'imports, laisser tous les tests GeoJSON/CSV existants inchangés en dessous) :

```python
import warnings
import zipfile

import numpy as np
import pytest
import shapely
from pyogrio.raw import write as pyogrio_write
from shapely.geometry import Point

from app.ingestion.parsers import (
    IngestionParseError, LayerInfo, detect_lat_lon_fields, list_layers,
    parse_csv_latlon, parse_geojson, parse_gpkg, parse_shapefile_zip,
)
```

Puis ajouter à la fin du fichier :

```python
def _gpkg_bytes(tmp_path, *, layer="entites", crs="EPSG:4326", points=None, fields=None):
    points = points or [(1.0, 2.0), (3.0, 4.0)]
    fields = fields or {"nom": np.array(["A", "B"][: len(points)], dtype=object)}
    path = tmp_path / f"{layer}.gpkg"
    geometry = shapely.to_wkb(np.array([Point(x, y) for x, y in points], dtype=object))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pyogrio avertit si crs=None (cas volontaire d'un test)
        pyogrio_write(
            str(path), geometry=geometry, field_data=list(fields.values()),
            fields=list(fields.keys()), layer=layer, geometry_type="Point", crs=crs,
        )
    return path.read_bytes()


def _shapefile_zip_bytes(tmp_path) -> bytes:
    shp_path = tmp_path / "villes.shp"
    geometry = shapely.to_wkb(np.array([Point(1.0, 45.0), Point(2.0, 46.0)], dtype=object))
    pyogrio_write(
        str(shp_path), geometry=geometry, field_data=[np.array(["A", "B"], dtype=object)],
        fields=["nom"], geometry_type="Point", crs="EPSG:4326",
    )
    zip_path = tmp_path / "villes.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for ext in ("shp", "shx", "dbf", "prj", "cpg"):
            p = tmp_path / f"villes.{ext}"
            if p.exists():
                z.write(p, arcname=p.name)
    return zip_path.read_bytes()


def test_list_layers_single_layer_gpkg(tmp_path):
    content = _gpkg_bytes(tmp_path)
    layers = list_layers(content, "villes.gpkg")
    assert layers == [LayerInfo(name="entites", feature_count=2, geometry_type="Point")]


def test_list_layers_multi_layer_gpkg(tmp_path):
    path = tmp_path / "multi.gpkg"
    geom = shapely.to_wkb(np.array([Point(1.0, 1.0)], dtype=object))
    pyogrio_write(str(path), geometry=geom, field_data=[np.array(["A"], dtype=object)],
                  fields=["nom"], layer="a", geometry_type="Point", crs="EPSG:4326")
    pyogrio_write(str(path), geometry=geom, field_data=[np.array(["B"], dtype=object)],
                  fields=["nom"], layer="b", geometry_type="Point", crs="EPSG:4326")
    layers = list_layers(path.read_bytes(), "multi.gpkg")
    assert {l.name for l in layers} == {"a", "b"}
    assert all(l.feature_count == 1 for l in layers)


def test_list_layers_shapefile_zip_names_layer_from_shp(tmp_path):
    content = _shapefile_zip_bytes(tmp_path)
    layers = list_layers(content, "villes.zip")
    assert layers == [LayerInfo(name="villes", feature_count=2, geometry_type="Point")]


def test_list_layers_rejects_unsupported_extension():
    with pytest.raises(ValueError, match="non concerné"):
        list_layers(b"nom,lat,lon\n", "villes.csv")


def test_list_layers_corrupted_file_raises_parse_error():
    with pytest.raises(IngestionParseError, match="illisible"):
        list_layers(b"not a real gpkg", "villes.gpkg")


def test_parse_gpkg_yields_geometry_and_properties(tmp_path):
    content = _gpkg_bytes(tmp_path)
    rows = list(parse_gpkg(content, "entites"))
    assert len(rows) == 2
    geom0, props0 = rows[0]
    assert geom0.geom_type == "Point"
    assert (geom0.x, geom0.y) == (1.0, 2.0)
    assert props0 == {"nom": "A"}


def test_parse_gpkg_auto_selects_layer_when_only_one(tmp_path):
    content = _gpkg_bytes(tmp_path)
    rows = list(parse_gpkg(content, layer_name=None))
    assert len(rows) == 2


def test_parse_gpkg_requires_explicit_layer_when_multiple(tmp_path):
    path = tmp_path / "multi.gpkg"
    geom = shapely.to_wkb(np.array([Point(1.0, 1.0)], dtype=object))
    pyogrio_write(str(path), geometry=geom, field_data=[np.array(["A"], dtype=object)],
                  fields=["nom"], layer="a", geometry_type="Point", crs="EPSG:4326")
    pyogrio_write(str(path), geometry=geom, field_data=[np.array(["B"], dtype=object)],
                  fields=["nom"], layer="b", geometry_type="Point", crs="EPSG:4326")
    with pytest.raises(IngestionParseError, match="plusieurs couches"):
        list(parse_gpkg(path.read_bytes(), layer_name=None))


def test_parse_gpkg_rejects_unknown_layer_name(tmp_path):
    content = _gpkg_bytes(tmp_path)
    with pytest.raises(IngestionParseError, match="introuvable"):
        list(parse_gpkg(content, "n-existe-pas"))


def test_parse_gpkg_normalizes_numpy_scalars_and_nan(tmp_path):
    content = _gpkg_bytes(tmp_path, fields={
        "nom": np.array(["A", "B"], dtype=object),
        "population": np.array([10, 20], dtype="int64"),
        "score": np.array([1.5, np.nan], dtype="float64"),
    })
    rows = list(parse_gpkg(content, "entites"))
    _, props0 = rows[0]
    assert props0 == {"nom": "A", "population": 10, "score": 1.5}
    assert isinstance(props0["population"], int)
    _, props1 = rows[1]
    assert props1["score"] is None


def test_parse_gpkg_reprojects_non_wgs84_crs(tmp_path):
    import pyproj
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)
    x, y = transformer.transform(2.35, 48.85)
    content = _gpkg_bytes(
        tmp_path, crs="EPSG:2154", points=[(x, y)],
        fields={"nom": np.array(["Paris"], dtype=object)},
    )
    rows = list(parse_gpkg(content, "entites"))
    geom, _props = rows[0]
    assert geom.x == pytest.approx(2.35, abs=1e-6)
    assert geom.y == pytest.approx(48.85, abs=1e-6)


def test_parse_gpkg_skips_transform_when_already_wgs84(tmp_path):
    content = _gpkg_bytes(tmp_path, crs="EPSG:4326", points=[(2.35, 48.85)],
                           fields={"nom": np.array(["Paris"], dtype=object)})
    rows = list(parse_gpkg(content, "entites"))
    geom, _props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)


def test_parse_gpkg_missing_crs_fails_fast(tmp_path):
    content = _gpkg_bytes(tmp_path, crs=None)
    with pytest.raises(IngestionParseError, match="CRS"):
        list(parse_gpkg(content, "entites"))


def test_parse_shapefile_zip_yields_geometry_and_properties(tmp_path):
    content = _shapefile_zip_bytes(tmp_path)
    rows = list(parse_shapefile_zip(content, "villes"))
    assert len(rows) == 2
    geom0, props0 = rows[0]
    assert geom0.geom_type == "Point"
    assert props0 == {"nom": "A"}


def test_parse_shapefile_zip_auto_selects_single_layer(tmp_path):
    content = _shapefile_zip_bytes(tmp_path)
    rows = list(parse_shapefile_zip(content, layer_name=None))
    assert len(rows) == 2
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_ingestion_parsers.py -v`
Expected: FAIL — `ImportError: cannot import name 'LayerInfo' from 'app.ingestion.parsers'` (ni `list_layers`, `parse_gpkg`, `parse_shapefile_zip`).

- [ ] **Step 4: Implémenter les nouveaux parseurs**

Dans `core/app/ingestion/parsers.py`, remplacer l'en-tête du fichier (docstring + imports) par :

```python
"""Parseurs GeoJSON, CSV+lat/lon (SP-6a) et GeoPackage/Shapefile zippé
(SP-6b, via pyogrio — wheels manylinux, GDAL/GEOS/PROJ embarqués, aucun
paquet système requis). Chaque parseur produit un flux (géométrie shapely,
propriétés) ; toute ligne/feature/entité invalide lève IngestionParseError
immédiatement (fail-fast) — pas d'import partiel silencieux."""
import csv
import io
import json
import math
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np
import pyogrio
import pyproj
import shapely
from pyogrio.errors import DataLayerError, DataSourceError
from pyproj.exceptions import CRSError
from shapely.errors import ShapelyError
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform


class IngestionParseError(Exception):
    """Message affiché tel quel comme ingestion_jobs.error_message."""


_LAT_NAMES = {"lat", "latitude", "y"}
_LON_NAMES = {"lon", "lng", "longitude", "x"}
_WGS84 = pyproj.CRS.from_epsg(4326)
_OGR_ERRORS = (DataSourceError, DataLayerError)
```

Laisser `detect_lat_lon_fields`, `parse_geojson` et `parse_csv_latlon` **inchangés** (déjà présents en dessous). Ajouter ensuite, **à la fin du fichier** :

```python
@dataclass
class LayerInfo:
    name: str
    feature_count: int
    geometry_type: str


@contextmanager
def _temp_file(content: bytes, suffix: str) -> Iterator[str]:
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(content)
        tmp.flush()
        yield tmp.name


def _crs_transform(crs: str | None):
    try:
        src = pyproj.CRS.from_user_input(crs)
    except CRSError as exc:
        raise IngestionParseError(f"CRS manquant ou non reconnu : {crs!r}") from exc
    if src == _WGS84:
        return None
    transformer = pyproj.Transformer.from_crs(src, _WGS84, always_xy=True)
    return transformer.transform


def _native_value(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _read_features(path: str, layer_name: str | None) -> Iterator[tuple[BaseGeometry, dict]]:
    try:
        raw_layers = pyogrio.list_layers(path)
    except _OGR_ERRORS as exc:
        raise IngestionParseError(f"fichier illisible : {exc}") from exc
    available = [str(name) for name, _geom_type in raw_layers]
    if layer_name is None:
        if len(available) != 1:
            raise IngestionParseError(
                f"plusieurs couches disponibles ({', '.join(available)}) — précisez layerName"
            )
        layer_name = available[0]
    elif layer_name not in available:
        raise IngestionParseError(
            f"couche '{layer_name}' introuvable — couches disponibles : {', '.join(available)}"
        )
    try:
        meta, _index, geometry, field_data = pyogrio.raw.read(
            path, layer=layer_name, force_2d=True
        )
    except _OGR_ERRORS as exc:
        raise IngestionParseError(f"couche '{layer_name}' illisible : {exc}") from exc

    transform = _crs_transform(meta["crs"])
    fields = list(meta["fields"])

    for i, wkb in enumerate(geometry):
        if wkb is None:
            raise IngestionParseError(f"entité {i} : géométrie manquante")
        try:
            geom = shapely.from_wkb(wkb)
        except ShapelyError as exc:
            raise IngestionParseError(f"entité {i} : géométrie invalide ({exc})") from exc
        if transform is not None:
            geom = shapely_transform(transform, geom)
        if not geom.is_valid:
            raise IngestionParseError(f"entité {i} : géométrie invalide")
        properties = {
            field: _native_value(field_data[j][i]) for j, field in enumerate(fields)
        }
        yield geom, properties


def parse_gpkg(
    content: bytes, layer_name: str | None = None,
) -> Iterator[tuple[BaseGeometry, dict]]:
    with _temp_file(content, ".gpkg") as path:
        yield from _read_features(path, layer_name)


def parse_shapefile_zip(
    content: bytes, layer_name: str | None = None,
) -> Iterator[tuple[BaseGeometry, dict]]:
    with _temp_file(content, ".zip") as path:
        yield from _read_features(f"/vsizip/{path}", layer_name)


def list_layers(content: bytes, filename: str) -> list[LayerInfo]:
    lower = filename.lower()
    if lower.endswith(".gpkg"):
        suffix, wrap = ".gpkg", (lambda p: p)
    elif lower.endswith(".zip"):
        suffix, wrap = ".zip", (lambda p: f"/vsizip/{p}")
    else:
        raise ValueError(f"format non concerné par l'inspection : {filename}")
    with _temp_file(content, suffix) as tmp_path:
        path = wrap(tmp_path)
        try:
            raw_layers = pyogrio.list_layers(path)
        except _OGR_ERRORS as exc:
            raise IngestionParseError(f"fichier illisible : {exc}") from exc
        layers = []
        for name, _geom_type in raw_layers:
            try:
                info = pyogrio.read_info(path, layer=name)
            except _OGR_ERRORS as exc:
                raise IngestionParseError(f"couche '{name}' illisible : {exc}") from exc
            layers.append(LayerInfo(
                name=str(name), feature_count=int(info["features"]),
                geometry_type=str(info["geometry_type"] or "Unknown"),
            ))
        if not layers:
            raise IngestionParseError("aucune couche trouvée dans le fichier")
        return layers
```

Note : `pyogrio.raw` est accessible directement après `import pyogrio` (sous-module déjà importé dans l'espace de noms du paquet, vérifié) — pas besoin d'un `import pyogrio.raw` séparé.

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_ingestion_parsers.py -v`
Expected: tous les tests passent (existants GeoJSON/CSV + nouveaux GPKG/Shapefile, ~30 tests).

- [ ] **Step 6: Suite complète + lint imports + commit**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: tout vert.

```bash
git add core/pyproject.toml core/Dockerfile core/app/ingestion/parsers.py \
        core/tests/test_ingestion_parsers.py
git commit -m "feat(core): parseurs GeoPackage/Shapefile zippé — couches, CRS (SP-6b)"
```

---

## Task 3: Pipeline d'import — `run_import` étendu (PostGIS réel)

**Files:**
- Modify: `core/app/ingestion/importer.py`
- Modify: `core/tests/test_ingestion_importer.py`

**Interfaces:**
- Produces: `importer.run_import(session, *, tenant_id, created_by, filename, content, collection_title, lat_field, lon_field, layer_name=None) -> ImportResult` (nouveau kwarg optionnel, défaut `None`).
- Consumes: `parsers.parse_gpkg`, `parsers.parse_shapefile_zip`, `parsers.IngestionParseError` (Task 2).

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter en tête de `core/tests/test_ingestion_importer.py` (fichier existant, imports actuels conservés, en ajouter) :

```python
import numpy as np
import shapely
from pyogrio.raw import write as pyogrio_write
from shapely.geometry import Point
```

Ajouter à la fin du fichier :

```python
def _gpkg_bytes(tmp_path, *, layer="entites", crs="EPSG:4326", points=None):
    points = points or [(1.0, 45.0), (2.0, 46.0)]
    path = tmp_path / f"{layer}.gpkg"
    geometry = shapely.to_wkb(np.array([Point(x, y) for x, y in points], dtype=object))
    pyogrio_write(
        str(path), geometry=geometry,
        field_data=[np.array(["A", "B"][: len(points)], dtype=object)],
        fields=["nom"], layer=layer, geometry_type="Point", crs=crs,
    )
    return path.read_bytes()


def test_gpkg_import_creates_queryable_collection_and_map_item(env, tmp_path):
    Session, tenant, user = env
    content = _gpkg_bytes(tmp_path)
    with Session() as s:
        result = run_import(
            s, tenant_id=tenant.id, created_by=user.id, filename="villes.gpkg",
            content=content, collection_title="Villes GPKG", lat_field=None,
            lon_field=None, layer_name="entites",
        )
        s.commit()
    with Session() as s:
        rows = s.execute(
            text(f"SELECT nom FROM public.{result.collection_id} ORDER BY nom")
        ).scalars().all()
        assert rows == ["A", "B"]


def test_gpkg_import_reprojects_non_wgs84_crs(env, tmp_path):
    import pyproj
    Session, tenant, user = env
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)
    x, y = transformer.transform(2.35, 48.85)
    content = _gpkg_bytes(tmp_path, crs="EPSG:2154", points=[(x, y)])
    with Session() as s:
        result = run_import(
            s, tenant_id=tenant.id, created_by=user.id, filename="l93.gpkg",
            content=content, collection_title="Villes L93", lat_field=None,
            lon_field=None, layer_name="entites",
        )
        s.commit()
    with Session() as s:
        lon, lat = s.execute(
            text(f"SELECT ST_X(geom), ST_Y(geom) FROM public.{result.collection_id}")
        ).one()
        assert lon == pytest.approx(2.35, abs=1e-6)
        assert lat == pytest.approx(48.85, abs=1e-6)


def test_gpkg_import_requires_layer_name_when_multiple_layers(env, tmp_path):
    Session, tenant, user = env
    path = tmp_path / "multi.gpkg"
    geometry = shapely.to_wkb(np.array([Point(1.0, 1.0)], dtype=object))
    pyogrio_write(str(path), geometry=geometry, field_data=[np.array(["A"], dtype=object)],
                  fields=["nom"], layer="a", geometry_type="Point", crs="EPSG:4326")
    pyogrio_write(str(path), geometry=geometry, field_data=[np.array(["B"], dtype=object)],
                  fields=["nom"], layer="b", geometry_type="Point", crs="EPSG:4326")
    content = path.read_bytes()
    with Session() as s:
        with pytest.raises(IngestionParseError):
            run_import(
                s, tenant_id=tenant.id, created_by=user.id, filename="multi.gpkg",
                content=content, collection_title="Multi", lat_field=None,
                lon_field=None, layer_name=None,
            )
        s.rollback()
    with Session() as s:
        cols = collections_repo.list_visible_collections(
            s, tenant_id=tenant.id, user_id=user.id, is_admin=True
        )
        assert cols == []


def test_shapefile_zip_import_creates_queryable_collection(env, tmp_path):
    import zipfile
    Session, tenant, user = env
    shp_path = tmp_path / "villes.shp"
    geometry = shapely.to_wkb(np.array([Point(1.0, 45.0), Point(2.0, 46.0)], dtype=object))
    pyogrio_write(
        str(shp_path), geometry=geometry, field_data=[np.array(["A", "B"], dtype=object)],
        fields=["nom"], geometry_type="Point", crs="EPSG:4326",
    )
    zip_path = tmp_path / "villes.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for ext in ("shp", "shx", "dbf", "prj", "cpg"):
            p = tmp_path / f"villes.{ext}"
            if p.exists():
                z.write(p, arcname=p.name)
    with Session() as s:
        result = run_import(
            s, tenant_id=tenant.id, created_by=user.id, filename="villes.zip",
            content=zip_path.read_bytes(), collection_title="Villes Shapefile",
            lat_field=None, lon_field=None, layer_name="villes",
        )
        s.commit()
    with Session() as s:
        rows = s.execute(
            text(f"SELECT nom FROM public.{result.collection_id} ORDER BY nom")
        ).scalars().all()
        assert rows == ["A", "B"]
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_ingestion_importer.py -v -m postgis`
(ou sans `CORE_TEST_DATABASE_URL` : les nouveaux tests sont **skippés**, pas d'échec visible — vérifier plutôt l'erreur d'import Python : `TypeError: run_import() got an unexpected keyword argument 'layer_name'` en les lançant localement contre un PostGIS jetable, cf. Global Constraints du plan SP-6a sur la même limitation.)
Expected: FAIL sur les 4 nouveaux tests avec `TypeError: run_import() got an unexpected keyword argument 'layer_name'`.

- [ ] **Step 3: Étendre `_pick_format` et `run_import`**

Dans `core/app/ingestion/importer.py`, modifier l'import de `app.ingestion.parsers` :

```python
from app.ingestion.parsers import (
    IngestionParseError, parse_csv_latlon, parse_geojson, parse_gpkg, parse_shapefile_zip,
)
```

Modifier `_pick_format` :

```python
def _pick_format(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith((".geojson", ".json")):
        return "geojson"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".gpkg"):
        return "gpkg"
    if lower.endswith(".zip"):
        return "shapefile"
    raise IngestionParseError(f"format non supporté : {filename}")
```

Modifier la signature de `run_import` et le dispatch des parseurs :

```python
def run_import(
    session: Session, *, tenant_id: str, created_by: str, filename: str,
    content: bytes, collection_title: str,
    lat_field: str | None, lon_field: str | None, layer_name: str | None = None,
) -> ImportResult:
    fmt = _pick_format(filename)
    if fmt == "geojson":
        rows = list(parse_geojson(content))
    elif fmt == "csv":
        rows = list(parse_csv_latlon(content, lat_field, lon_field))
    elif fmt == "gpkg":
        rows = list(parse_gpkg(content, layer_name))
    else:
        rows = list(parse_shapefile_zip(content, layer_name))
    if not rows:
        raise IngestionParseError("le fichier ne contient aucune entité")
```

Le reste de la fonction (colonnes inférées, création de table, `register_collection`, item carte, audit) est **inchangé** — déjà générique sur `list[tuple[BaseGeometry, dict]]`.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_ingestion_importer.py -v`
Expected: tous les tests passent (existants GeoJSON/CSV + les 4 nouveaux GPKG/Shapefile).

- [ ] **Step 5: Suite complète + commit**

Run: `cd core && uv run pytest` (sans `CORE_TEST_DATABASE_URL` : les tests `postgis` sont skippés, le reste doit passer) puis, si un PostGIS jetable est disponible localement, relancer avec `CORE_TEST_DATABASE_URL` défini pour valider réellement les 4 nouveaux tests (comme fait en revue finale SP-6a).

```bash
git add core/app/ingestion/importer.py core/tests/test_ingestion_importer.py
git commit -m "feat(core): run_import — GeoPackage/Shapefile zippé, reprojection CRS (SP-6b)"
```

---

## Task 4: API `POST /uploads/inspect`, `layerName` sur `/uploads`, worker

**Files:**
- Modify: `core/app/ingestion/schemas.py`
- Modify: `core/app/ingestion/routes.py`
- Modify: `core/app/ingestion/tasks.py`
- Modify: `core/tests/test_ingestion_routes.py`
- Modify: `core/tests/test_ingestion_tasks.py`

**Interfaces:**
- Produces: `POST /uploads/inspect` `{key, filename}` → `200 {layers: [{name, featureCount, geometryType}]}` (400 clé hors tenant ou format non concerné, 404 objet introuvable, 422 fichier illisible) ; `IngestionJobCreate.layerName: str | None`.
- Consumes: `parsers.list_layers`, `parsers.IngestionParseError` (Task 2), `storage.download_object` (existant SP-6a).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `core/tests/test_ingestion_routes.py`, remplacer la classe `_FakeS3Client` et la fixture `env` par :

```python
from botocore.exceptions import ClientError


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}"

    def get_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject"
            )

        class _Body:
            def __init__(self, data: bytes):
                self._data = data

            def read(self) -> bytes:
                return self._data

        return {"Body": _Body(self.objects[Key])}


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

    fake_s3 = _FakeS3Client()
    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: fake_s3
    deferred: list[tuple[str, str]] = []
    app.dependency_overrides[ingestion_routes.get_task_deferrer] = (
        lambda: (lambda job_id, tenant_id: deferred.append((job_id, tenant_id)))
    )
    client = TestClient(app)
    return client, Session, tenant, alice, deferred, fake_s3
```

Mettre à jour les deux tests existants qui déstructurent `env` explicitement (les autres, `client, *_ = env`, n'ont pas besoin de changer) :

```python
def test_create_upload_job_defers_task_and_returns_job_id(env):
    client, Session, tenant, alice, deferred, _fake_s3 = env
    ...  # corps inchangé


def test_create_upload_job_is_audited(env):
    client, Session, tenant, alice, _deferred, _fake_s3 = env
    ...  # corps inchangé
```

Ajouter à la fin du fichier (utilise `pyogrio` pour synthétiser un GPKG minimal — même patron que Tasks 2/3) :

```python
def _tiny_gpkg_bytes(tmp_path) -> bytes:
    import numpy as np
    import shapely
    from pyogrio.raw import write as pyogrio_write
    path = tmp_path / "villes.gpkg"
    geometry = shapely.to_wkb(np.array([shapely.geometry.Point(1.0, 2.0)], dtype=object))
    pyogrio_write(
        str(path), geometry=geometry, field_data=[np.array(["A"], dtype=object)],
        fields=["nom"], layer="villes", geometry_type="Point", crs="EPSG:4326",
    )
    return path.read_bytes()


def test_inspect_upload_returns_layers(env, tmp_path):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    fake_s3.objects[f"{tenant.id}/k.gpkg"] = _tiny_gpkg_bytes(tmp_path)
    r = client.post(
        "/uploads/inspect", json={"key": f"{tenant.id}/k.gpkg", "filename": "villes.gpkg"}
    )
    assert r.status_code == 200
    assert r.json() == {"layers": [{"name": "villes", "featureCount": 1, "geometryType": "Point"}]}


def test_inspect_upload_rejects_foreign_tenant_key(env):
    client, *_ = env
    r = client.post(
        "/uploads/inspect", json={"key": "other-tenant/k.gpkg", "filename": "villes.gpkg"}
    )
    assert r.status_code == 400


def test_inspect_upload_rejects_unsupported_format(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    fake_s3.objects[f"{tenant.id}/k.csv"] = b"nom,lat,lon\n"
    r = client.post(
        "/uploads/inspect", json={"key": f"{tenant.id}/k.csv", "filename": "villes.csv"}
    )
    assert r.status_code == 400


def test_inspect_upload_404_when_object_missing(env):
    client, Session, tenant, *_ = env
    r = client.post(
        "/uploads/inspect", json={"key": f"{tenant.id}/absent.gpkg", "filename": "villes.gpkg"}
    )
    assert r.status_code == 404


def test_inspect_upload_422_on_corrupt_file(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    fake_s3.objects[f"{tenant.id}/k.gpkg"] = b"not a real gpkg"
    r = client.post(
        "/uploads/inspect", json={"key": f"{tenant.id}/k.gpkg", "filename": "villes.gpkg"}
    )
    assert r.status_code == 422


def test_create_upload_job_accepts_layer_name(env):
    client, Session, tenant, *_ = env
    r = client.post("/uploads", json={
        "key": f"{tenant.id}/abc-villes.gpkg", "filename": "villes.gpkg",
        "collectionTitle": "Villes", "layerName": "villes",
    })
    assert r.status_code == 201
    job_id = r.json()["jobId"]
    with Session() as s:
        from app.ingestion import repository as ingestion_repo
        job = ingestion_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.layer_name == "villes"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_ingestion_routes.py -v`
Expected: FAIL — les tests `inspect_upload` échouent en 404 (route inexistante) ; `test_create_upload_job_accepts_layer_name` échoue (`layerName` ignoré par le schéma, `job.layer_name` reste `None`).

- [ ] **Step 3: Schémas**

Dans `core/app/ingestion/schemas.py`, ajouter `layerName` à `IngestionJobCreate` et les nouveaux modèles :

```python
class IngestionJobCreate(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    collectionTitle: str = Field(min_length=1)
    latField: str | None = None
    lonField: str | None = None
    layerName: str | None = None


class InspectRequest(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)


class LayerInfoOut(BaseModel):
    name: str
    featureCount: int
    geometryType: str


class InspectResponse(BaseModel):
    layers: list[LayerInfoOut]
```

(`PresignRequest`, `PresignResponse`, `IngestionJobCreated`, `IngestionJobStatus` inchangés.)

- [ ] **Step 4: Route `POST /uploads/inspect` + `layerName` sur `POST /uploads`**

Dans `core/app/ingestion/routes.py`, étendre les imports :

```python
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.ingestion import repository as repo
from app.ingestion.parsers import IngestionParseError, list_layers
from app.ingestion.schemas import (
    IngestionJobCreate, IngestionJobCreated, IngestionJobStatus,
    InspectRequest, InspectResponse, LayerInfoOut, PresignRequest, PresignResponse,
)
from app.ingestion.storage import (
    download_object, ensure_uploads_bucket, generate_presigned_put_url,
)
from app.ingestion.tasks import run_ingestion_task
from app.users.models import User
```

Ajouter la route (par exemple juste après `presign_upload`) :

```python
@router.post("/uploads/inspect", response_model=InspectResponse)
def inspect_upload(
    body: InspectRequest,
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_uploads_bucket),
) -> InspectResponse:
    if not body.key.startswith(f"{user.tenant_id}/"):
        raise HTTPException(status_code=400, detail="invalid upload key")
    try:
        content = download_object(s3, bucket=bucket, key=body.key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="objet introuvable") from exc
    try:
        layers = list_layers(content, body.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IngestionParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return InspectResponse(layers=[
        LayerInfoOut(name=layer.name, featureCount=layer.feature_count, geometryType=layer.geometry_type)
        for layer in layers
    ])
```

Dans `create_upload_job`, ajouter `layer_name=body.layerName` à l'appel `repo.create_job` :

```python
    job = repo.create_job(
        session, tenant_id=user.tenant_id, created_by=user.id, source_key=body.key,
        filename=body.filename, collection_title=body.collectionTitle,
        lat_field=body.latField, lon_field=body.lonField, layer_name=body.layerName,
    )
```

- [ ] **Step 5: Fil `layer_name` dans le worker**

Dans `core/app/ingestion/tasks.py`, modifier `run_ingestion_task` :

```python
            ingestion_repo.mark_running(session, job_id=job_id)
            filename, source_key, collection_title, lat_field, lon_field, layer_name, created_by = (
                job.filename, job.source_key, job.collection_title,
                job.lat_field, job.lon_field, job.layer_name, job.created_by,
            )

        s3 = _make_s3_client_from_env()
        content = download_object(s3, bucket=_uploads_bucket(), key=source_key)
        with request_scoped_session(session_factory) as session:
            result = run_import(
                session, tenant_id=tenant_id, created_by=created_by, filename=filename,
                content=content, collection_title=collection_title,
                lat_field=lat_field, lon_field=lon_field, layer_name=layer_name,
            )
```

- [ ] **Step 6: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_ingestion_routes.py -v`
Expected: tous passent.

Dans `core/tests/test_ingestion_tasks.py`, les deux appels existants à `ingestion_repo.create_job(...)` n'ont pas besoin de changer (`layer_name` a un défaut `None`, Task 1) — vérifier qu'ils passent toujours tels quels :

Run: `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_ingestion_tasks.py -v`
Expected: 3 passed, sans modification du fichier.

- [ ] **Step 7: Régénérer l'OpenAPI + suite complète + commit**

Run:
```bash
cd core && uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Expected: `core/openapi.json` et `shell/src/api/generated/core-schema.d.ts` reflètent `POST /uploads/inspect` et `IngestionJobCreate.layerName` — diff visible sur ces deux fichiers seulement.

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: tout vert.

```bash
git add core/app/ingestion/schemas.py core/app/ingestion/routes.py \
        core/app/ingestion/tasks.py core/tests/test_ingestion_routes.py \
        core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): POST /uploads/inspect, layerName sur /uploads (SP-6b)"
```

---

## Task 5: Validation perf M4 — GPKG 50 000 entités

**Files:**
- Create: `core/tests/test_ingestion_importer_perf.py`

**Interfaces:**
- Consumes: `importer.run_import` (Task 3).
- Produces: rien de nouveau — test de non-régression perf, isolé dans son propre fichier pour rester facilement skippable/identifiable.

- [ ] **Step 1: Écrire le test**

Créer `core/tests/test_ingestion_importer_perf.py` :

```python
"""Validation du critère M4 (feuille de route, §SP-6) : un GeoPackage de
50 000 entités s'importe en un temps trivial devant le budget UI de 5 min
(le budget UI couvre aussi le transfert réseau du fichier, hors périmètre
d'un test backend — cf. design SP-6b §11)."""
import time

import numpy as np
import pytest
import shapely
from pyogrio.raw import write as pyogrio_write
from shapely.geometry import Point
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.ingestion.importer import run_import
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

N_FEATURES = 50_000
# Seuil très en-dessous du budget M4 de 5 min (300s) : couvre une marge CI
# généreuse tout en restant un signal de régression utile. Mesuré en local
# (2026-07-12, hors CI) : lecture+reprojection pyogrio/pyproj de 50k points
# <0,1s, insertion PostGIS (executemany) <1s — le pipeline complet est de
# l'ordre de quelques secondes, très loin du seuil.
PERF_BUDGET_SECONDS = 180


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


def _synthetic_gpkg_bytes(tmp_path) -> bytes:
    rng = np.random.default_rng(42)
    lons = rng.uniform(-5.0, 9.0, N_FEATURES)
    lats = rng.uniform(41.0, 51.0, N_FEATURES)
    geometry = shapely.to_wkb(
        np.array([Point(x, y) for x, y in zip(lons, lats)], dtype=object)
    )
    path = tmp_path / "big.gpkg"
    pyogrio_write(
        str(path), geometry=geometry,
        field_data=[
            np.array([f"entite-{i}" for i in range(N_FEATURES)], dtype=object),
            np.arange(N_FEATURES, dtype="int64"),
        ],
        fields=["nom", "rang"], layer="entites", geometry_type="Point", crs="EPSG:4326",
    )
    return path.read_bytes()


def test_gpkg_50k_features_imports_within_m4_budget(env, tmp_path):
    Session, tenant, user = env
    content = _synthetic_gpkg_bytes(tmp_path)

    with Session() as s:
        t0 = time.monotonic()
        result = run_import(
            s, tenant_id=tenant.id, created_by=user.id, filename="big.gpkg",
            content=content, collection_title="Gros import", lat_field=None,
            lon_field=None, layer_name="entites",
        )
        s.commit()
        elapsed = time.monotonic() - t0

    assert elapsed < PERF_BUDGET_SECONDS, (
        f"import de {N_FEATURES} entités trop lent : {elapsed:.1f}s "
        f"(budget {PERF_BUDGET_SECONDS}s)"
    )

    with Session() as s:
        count = s.execute(
            text(f"SELECT count(*) FROM public.{result.collection_id}")
        ).scalar_one()
        assert count == N_FEATURES
```

- [ ] **Step 2: Lancer le test contre un PostGIS réel**

Run: `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_ingestion_importer_perf.py -v -s`
Expected: PASS. Noter le temps réel mesuré (affiché via `-s` si un `print(elapsed)` est ajouté temporairement, ou en lisant la durée totale rapportée par pytest) dans le rapport de tâche — c'est la preuve empirique du critère M4, à consigner explicitement (ne pas se contenter du seuil `PERF_BUDGET_SECONDS` qui est volontairement large pour la marge CI).

Sans `CORE_TEST_DATABASE_URL` : `pytest tests/test_ingestion_importer_perf.py -v` doit afficher `1 skipped`.

- [ ] **Step 3: Suite complète + commit**

Run: `cd core && uv run pytest`
Expected: aucune régression (le nouveau test est skippé en l'absence de `CORE_TEST_DATABASE_URL`, comme tous les tests `postgis`).

```bash
git add core/tests/test_ingestion_importer_perf.py
git commit -m "test(core): valide le critère M4 — GPKG 50k entités <5min (SP-6b)"
```

---

## Task 6: Shell — sélecteur de couche (`ItemClient`, `ImportFileButton`)

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/shell/ImportFileButton.tsx`
- Modify: `shell/src/shell/ImportFileButton.test.tsx`

**Interfaces:**
- Produces: `ItemClient.inspectUpload(input: {key: string; filename: string}): Promise<{layers: {name: string; featureCount: number; geometryType: string}[]}>` ; `ItemClient.createIngestionJob` accepte désormais `layerName?: string`.
- Consumes: `POST /uploads/inspect`, `IngestionJobCreate.layerName` (Task 4).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/shell/ImportFileButton.test.tsx`, ajouter après les tests existants :

```tsx
function gpkgFile(name = "villes.gpkg") {
  return new File(["fake-gpkg-bytes"], name, { type: "application/geopackage+sqlite3" });
}

test("auto-selects the only layer of a GeoPackage without showing a picker", async () => {
  server.use(
    http.post("https://core.test/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-3", key: "t/ghi-villes.gpkg" })),
    http.put("https://minio.test/upload-3", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/uploads/inspect", () =>
      HttpResponse.json({ layers: [{ name: "villes", featureCount: 2, geometryType: "Point" }] })),
    http.post("https://core.test/uploads", async ({ request }) => {
      const body = (await request.json()) as { layerName?: string };
      expect(body.layerName).toBe("villes");
      return HttpResponse.json({ jobId: "job-3" });
    }),
    http.get("https://core.test/uploads/job-3", () =>
      HttpResponse.json({ status: "done", errorMessage: null, collectionId: "ingest_x", itemId: "99" })),
  );

  render(<Harness><ImportFileButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), gpkgFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByText("map-99")).toBeInTheDocument());
});

test("shows a layer picker for a multi-layer GeoPackage and imports the chosen layer", async () => {
  server.use(
    http.post("https://core.test/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-4", key: "t/jkl-multi.gpkg" })),
    http.put("https://minio.test/upload-4", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/uploads/inspect", () =>
      HttpResponse.json({
        layers: [
          { name: "villes", featureCount: 2, geometryType: "Point" },
          { name: "routes", featureCount: 5, geometryType: "LineString" },
        ],
      })),
    http.post("https://core.test/uploads", async ({ request }) => {
      const body = (await request.json()) as { layerName?: string };
      expect(body.layerName).toBe("routes");
      return HttpResponse.json({ jobId: "job-4" });
    }),
    http.get("https://core.test/uploads/job-4", () =>
      HttpResponse.json({ status: "done", errorMessage: null, collectionId: "ingest_y", itemId: "100" })),
  );

  render(<Harness><ImportFileButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), gpkgFile("multi.gpkg"));
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Multi");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByLabelText("Couche à importer")).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Couche à importer"), "routes");
  await userEvent.click(screen.getByRole("button", { name: "Continuer" }));

  await waitFor(() => expect(screen.getByText("map-100")).toBeInTheDocument());
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npm run test -- ImportFileButton`
Expected: FAIL — `client.inspectUpload is not a function`, et le sélecteur "Couche à importer" n'existe pas encore.

- [ ] **Step 3: Étendre `ItemClient`**

Dans `shell/src/api/types.ts`, remplacer le bloc d'ingestion (lignes 119-130 actuelles) par :

```ts
  presignUpload(filename: string, contentType: string): Promise<{ uploadUrl: string; key: string }>;
  uploadToPresignedUrl(url: string, file: File): Promise<void>;
  inspectUpload(input: { key: string; filename: string }): Promise<{
    layers: { name: string; featureCount: number; geometryType: string }[];
  }>;
  createIngestionJob(input: {
    key: string; filename: string; collectionTitle: string;
    latField?: string; lonField?: string; layerName?: string;
  }): Promise<{ jobId: string }>;
  getIngestionJob(jobId: string): Promise<{
    status: "pending" | "running" | "done" | "error";
    errorMessage: string | null;
    collectionId: string | null;
    itemId: string | null;
  }>;
```

Dans `shell/src/api/itemClient.ts`, ajouter `inspectUpload` juste après `uploadToPresignedUrl` (et avant `createIngestionJob`) :

```ts
    async inspectUpload(input: { key: string; filename: string }) {
      return request<{
        layers: { name: string; featureCount: number; geometryType: string }[];
      }>("POST", "/uploads/inspect", input);
    },

    async createIngestionJob(input) {
      return request<{ jobId: string }>("POST", "/uploads", input);
    },
```

- [ ] **Step 4: Sélecteur de couche dans `ImportFileButton`**

Remplacer entièrement `shell/src/shell/ImportFileButton.tsx` par :

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useItemClient } from "../api/hooks";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Dialog } from "../ui/dialog";

type Phase = "form" | "uploading" | "selecting-layer" | "polling" | "error";
type LayerInfo = { name: string; featureCount: number; geometryType: string };

const LAT_NAMES = ["lat", "latitude", "y"];
const LON_NAMES = ["lon", "lng", "longitude", "x"];

function detectLatLon(headers: string[]): boolean {
  const byLower = new Set(headers.map((h) => h.trim().toLowerCase()));
  const hasLat = LAT_NAMES.some((n) => byLower.has(n));
  const hasLon = LON_NAMES.some((n) => byLower.has(n));
  return hasLat && hasLon;
}

function isLayeredFormat(filename: string): boolean {
  const lower = filename.toLowerCase();
  return lower.endsWith(".gpkg") || lower.endsWith(".zip");
}

export function ImportFileButton() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [csvHeaders, setCsvHeaders] = useState<string[] | null>(null);
  const [latField, setLatField] = useState("");
  const [lonField, setLonField] = useState("");
  const [uploadedKey, setUploadedKey] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerInfo[]>([]);
  const [layerName, setLayerName] = useState("");
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
    setUploadedKey(null);
    setLayers([]);
    setLayerName("");
    setPhase("form");
    setError("");
  }

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setCsvHeaders(null);
    if (f && f.name.toLowerCase().endsWith(".csv")) {
      const blob = f.slice(0, 4096);
      const text = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => resolve("");
        reader.readAsText(blob);
      });
      const firstLine = text.split(/\r?\n/)[0] ?? "";
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

  async function startJob(key: string, chosenLayerName: string | undefined) {
    const { jobId } = await client.createIngestionJob({
      key, filename: file!.name, collectionTitle: title.trim(),
      latField: needsManualLatLon ? latField : undefined,
      lonField: needsManualLatLon ? lonField : undefined,
      layerName: chosenLayerName,
    });
    setPhase("polling");
    await poll(jobId);
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
      if (isLayeredFormat(file.name)) {
        const { layers: found } = await client.inspectUpload({ key, filename: file.name });
        if (found.length > 1) {
          setUploadedKey(key);
          setLayers(found);
          setPhase("selecting-layer");
          return;
        }
        await startJob(key, found[0]?.name);
        return;
      }
      await startJob(key, undefined);
    } catch {
      setPhase("error");
      setError("Échec de l'import.");
    }
  }

  async function confirmLayer(e: React.FormEvent) {
    e.preventDefault();
    if (!uploadedKey || !layerName) return;
    setPhase("uploading");
    setError("");
    try {
      await startJob(uploadedKey, layerName);
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
        {phase === "selecting-layer" ? (
          <form onSubmit={confirmLayer} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Couche à importer
              <select
                aria-label="Couche à importer"
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                value={layerName}
                onChange={(e) => setLayerName(e.target.value)}
              >
                <option value="">—</option>
                {layers.map((l) => (
                  <option key={l.name} value={l.name}>
                    {l.name} ({l.featureCount} entités)
                  </option>
                ))}
              </select>
            </label>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={close}>
                Annuler
              </Button>
              <Button type="submit" size="sm" disabled={!layerName}>
                Continuer
              </Button>
            </div>
          </form>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Fichier à importer
              <input
                aria-label="Fichier à importer"
                type="file"
                accept=".geojson,.json,.csv,.gpkg,.zip"
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
        )}
      </Dialog>
    </>
  );
}
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd shell && npm run test -- ImportFileButton`
Expected: tous les tests passent (existants GeoJSON/CSV inchangés + les 2 nouveaux GPKG).

- [ ] **Step 6: Suite complète + build + commit**

Run: `cd shell && npm run test && npm run build`
Expected: 400+ tests verts, build OK (le `core-schema.d.ts` régénéré en Task 4 doit déjà refléter `layerName`/`inspectUpload` sans erreur TypeScript).

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts \
        shell/src/shell/ImportFileButton.tsx shell/src/shell/ImportFileButton.test.tsx
git commit -m "feat(shell): sélecteur de couche GeoPackage/Shapefile à l'import (SP-6b)"
```

---

## Task 7: E2E — import GeoPackage multi-couches

**Files:**
- Create: `shell/e2e/ingestion-gpkg.spec.ts`

**Interfaces:**
- Consumes: `ImportFileButton` (Task 6), mocks réseau Playwright (même patron que `shell/e2e/ingestion.spec.ts`, SP-6a).

- [ ] **Step 1: Écrire la spec**

Créer `shell/e2e/ingestion-gpkg.spec.ts` :

```ts
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

async function mockGpkgIngestionFlow(page: Page) {
  let jobPolls = 0;
  await page.route("**/uploads/presign", async (route) => {
    await route.fulfill({
      json: { uploadUrl: "https://minio.test/upload-gpkg", key: "t/abc-multi.gpkg" },
    });
  });
  await page.route("https://minio.test/upload-gpkg", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/uploads/inspect", async (route) => {
    await route.fulfill({
      json: {
        layers: [
          { name: "villes", featureCount: 2, geometryType: "Point" },
          { name: "routes", featureCount: 5, geometryType: "LineString" },
        ],
      },
    });
  });
  await page.route("**/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "job-gpkg" } });
  });
  await page.route("**/uploads/job-gpkg", async (route) => {
    jobPolls += 1;
    if (jobPolls < 2) {
      await route.fulfill({
        json: { status: "pending", errorMessage: null, collectionId: null, itemId: null },
      });
    } else {
      await route.fulfill({
        json: { status: "done", errorMessage: null, collectionId: "ingest_multi", itemId: "88" },
      });
    }
  });
  await page.route("https://core.test/items/88", async (route) => {
    await route.fulfill({
      json: {
        pk: "88", resourceType: "map", title: "Réseau", abstract: "", owner: "mockuser",
        thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: false,
      },
    });
  });
  await page.route("**/configs/by-item/**", async (route) => {
    if (!route.request().url().endsWith("/88") || route.request().method() !== "GET") {
      return route.fallback();
    }
    await route.fulfill({
      json: {
        id: "cfg-88", itemId: "88", kind: "map",
        config: {
          kind: "map", theme: {}, dataSources: [],
          map: {
            basemap: { style: "https://demotiles.maplibre.org/style.json" },
            view: { center: [1.5, 45.5], zoom: 10 },
            layers: [{
              id: "l1", title: "Réseau", visible: true, kind: "feature",
              url: "https://core.test/collections/ingest_multi/items",
            }],
          },
        },
      },
    });
  });
}

test("importer un GeoPackage à plusieurs couches force la sélection d'une couche", async ({ page }) => {
  await mockCore(page);
  await mockGpkgIngestionFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Importer un fichier" }).click();
  await page.getByLabel("Fichier à importer").setInputFiles({
    name: "multi.gpkg",
    mimeType: "application/geopackage+sqlite3",
    buffer: Buffer.from("fake-gpkg-bytes"),
  });
  await page.getByLabel("Titre de la collection").fill("Réseau");
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await expect(page.getByLabel("Couche à importer")).toBeVisible();
  await page.getByLabel("Couche à importer").selectOption("routes");
  await page.getByRole("button", { name: "Continuer" }).click();

  await expect(page).toHaveURL(/\/maps\/88$/, { timeout: 10_000 });
});
```

- [ ] **Step 2: Lancer la spec seule, vérifier le succès**

Run: `cd shell && npx playwright test ingestion-gpkg --project=chromium`
Expected: 1 passed.

- [ ] **Step 3: Suite E2E complète + commit**

Run: `cd shell && npm run e2e`
Expected: 19 specs vertes (18 existantes + `ingestion-gpkg.spec.ts`).

```bash
git add shell/e2e/ingestion-gpkg.spec.ts
git commit -m "test(shell): e2e — importer un GeoPackage à plusieurs couches (SP-6b)"
```

---

## Revue finale de branche

Après la Task 7, lancer une revue finale de branche (modèle opus, même patron que SP-6a) avant merge vers `main` : porter une attention particulière à
(a) la cohérence tenant/audit sur le chemin `/uploads/inspect` (lecture seule, mais vérifier qu'aucune fuite cross-tenant n'est possible via une clé S3 devinée — même garde que `POST /uploads`, déjà testée Task 4),
(b) la fermeture effective des fichiers temporaires (`tempfile.NamedTemporaryFile`) sur tous les chemins d'erreur des nouveaux parseurs,
(c) la validité de la mesure perf Task 5 rejouée réellement contre un PostGIS jetable (pas seulement skippée localement), comme fait en revue finale SP-6a pour `test_ingestion_tasks.py`.
