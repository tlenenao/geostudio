# SP-6a — Ingestion v1 : infra jobs + GeoJSON/CSV

## 1. Contexte et périmètre

SP-6 (feuille de route §SP-6) vise le 2ᵉ cas d'usage de la vision : « publier
une donnée → carte partageable en minutes ». C'est un chantier de la taille
de SP-3/SP-4, découpé en trois sous-phases :

- **SP-6a (ce document)** : infrastructure de jobs (`procrastinate`, arbitrage
  A5) + worker conteneurisé + import **GeoJSON et CSV+lat/lon** (formats pur
  Python, aucune dépendance GDAL) → collection + item carte auto-créés. UI
  minimale (formulaire d'upload + poll court), pas de suivi temps réel.
- **SP-6b** (hors périmètre de ce document) : GeoPackage et Shapefile zippé
  via `pyogrio`/GDAL — ajout net une fois 6a en place, pas un refactor.
- **SP-6c** (hors périmètre) : suivi de job dans l'UI (états en direct), génération
  PMTiles optionnelle pour les grosses couches (tippecanoe).

Le critère d'acceptation global de SP-6 (« GPKG 50k entités → carte en <5
min ») ne s'applique pleinement qu'après 6b/6c ; 6a est jugé sur son propre
périmètre (GeoJSON/CSV, jobs synchrones testables, pas d'optimisation grande
échelle).

## 2. Architecture

```
Shell                          Cœur (FastAPI)                    Worker (procrastinate)
  │                                  │                                    │
  │─ POST /uploads/presign ────────▶│ génère URL présignée MinIO          │
  │◀── {uploadUrl, key} ─────────────│                                    │
  │                                  │                                    │
  │─ PUT <uploadUrl> (fichier) ─────▶│ MinIO (direct, cœur hors chemin)   │
  │                                  │                                    │
  │─ POST /uploads {key, filename,  │                                    │
  │   collectionTitle, latField?,   │                                    │
  │   lonField?} ────────────────────▶│ crée ingestion_jobs (pending)      │
  │                                  │  + enfile tâche procrastinate ────▶│
  │◀── {jobId} ───────────────────────│                                    │
  │                                  │                                    │ lit le fichier (S3)
  │                                  │                                    │ parse (shapely)
  │                                  │                                    │ crée table PostGIS
  │─ GET /uploads/{jobId} ──────────▶│                                    │ charge les lignes
  │◀── {status, errorMessage?,      │                                    │ register_collection()
  │     collectionId?, itemId?} ─────│◀── met à jour ingestion_jobs ──────│ crée MapConfig + Item
```

Nouveau module `core/app/ingestion/` (même convention que `items`/
`collections` : `models.py`, `schemas.py`, `repository.py`, `routes.py`,
plus `parsers.py` et `tasks.py`). Nouveau service `worker` dans
`docker-compose.yml` (même image que `core`, commande
`procrastinate --app app.ingestion.tasks.app worker`).

## 3. Modèle de données

Table `ingestion_jobs` (Alembic, `tenant_id` + traçabilité dès la migration,
conforme à la règle non négociable du projet) :

```python
class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # "pending" | "running" | "done" | "error"
    source_key: Mapped[str] = mapped_column(String, nullable=False)   # clé S3
    filename: Mapped[str] = mapped_column(String, nullable=False)
    collection_title: Mapped[str] = mapped_column(String, nullable=False)
    lat_field: Mapped[str | None] = mapped_column(String, nullable=True)  # CSV seulement
    lon_field: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    collection_id: Mapped[str | None] = mapped_column(String, nullable=True)
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
```

Chaque transition d'état écrit aussi une ligne `audit_log`
(`action="ingestion.job_completed"` / `"ingestion.job_failed"`,
`actor_kind="system"` pour les écritures faites par le worker — le job a été
*lancé* par un utilisateur, tracé à la création, mais son exécution est
asynchrone et non attribuable à une requête utilisateur en cours).

## 4. API

- **`POST /uploads/presign`** `{filename, contentType}` → `{uploadUrl, key}`.
  Authentifié (tout utilisateur), clé préfixée `tenant_id/uuid-filename`
  (évite les collisions inter-tenants, cohérent avec le pattern déjà en
  place pour les vignettes S3).
- **`POST /uploads`** `{key, filename, collectionTitle, latField?,
  lonField?}` → `201 {jobId}`. Crée la ligne `ingestion_jobs` (`status=
  pending`), enfile la tâche procrastinate, audite la création
  (`actor_kind="user"`, l'utilisateur courant).
- **`GET /uploads/{jobId}`** → `{status, errorMessage?, collectionId?,
  itemId?}`. 404 si le job n'appartient pas au tenant courant (RLS
  applicative identique aux autres ressources).

## 5. Parsing (`core/app/ingestion/parsers.py`)

Interface commune, un module par format :

```python
def parse_geojson(content: bytes) -> Iterator[tuple[BaseGeometry, dict]]: ...
def parse_csv_latlon(content: bytes, lat_field: str | None, lon_field: str | None) -> Iterator[tuple[BaseGeometry, dict]]: ...
```

- **GeoJSON** : `json.loads` + `shapely.geometry.shape(feature["geometry"])`
  par feature de la `FeatureCollection`. CRS supposée WGS84 (RFC 7946
  l'impose — pas de détection de CRS en 6a, ce sera un sujet GDAL de 6b).
- **CSV+lat/lon** : `csv.DictReader`. Détection auto des colonnes par nom
  (`lat`/`latitude`/`y` et `lon`/`lng`/`longitude`/`x`, insensible à la
  casse) ; si l'auto-détection échoue, `latField`/`lonField` doivent être
  fournis explicitement par l'utilisateur (l'UI les demande seulement si
  la détection échoue côté client, sur un aperçu des en-têtes). Géométrie :
  `shapely.geometry.Point(lon, lat)`.
- **Aucune dépendance GDAL** — seule dépendance nouvelle : `shapely`
  (`core/pyproject.toml`).
- **Fail-fast** : toute ligne/feature invalide (géométrie manquante ou
  invalide, `lat`/`lon` non numériques, JSON malformé) lève une exception
  précise (`"ligne 42 : lat invalide 'abc'"`, `"feature 3 : géométrie
  manquante"`) qui devient `ingestion_jobs.error_message` tel quel. Pas
  d'import partiel silencieux — un rejet net est plus facile à corriger
  pour l'utilisateur qu'un import à moitié fait sans le savoir.

## 6. Import PostGIS + collection + item carte (`core/app/ingestion/tasks.py`)

1. Télécharge `source_key` depuis S3 (réutilise le client `boto3` déjà
   configuré pour les vignettes).
2. Parse la totalité du fichier en mémoire (features + géométries) — les
   gros volumes (>quelques dizaines de milliers d'entités) sont un sujet de
   SP-6b/6c (GDAL en streaming, PMTiles), pas de 6a.
3. Crée une table PostGIS (`ingest_<uuid court>`), colonnes inférées du type
   Python de chaque propriété sur le premier lot de features (réutilise les
   conventions de types de `app.collections.introspection`), colonne
   géométrie typée selon la géométrie dominante rencontrée.
4. Charge les lignes par lot (`INSERT ... VALUES`, géométrie via
   `ST_GeomFromText`).
5. Appelle directement la fonction interne de `app.collections.repository`
   qu'utilise `POST /collections` (pas de saut HTTP interne) : RLS générée
   (rôle `gis_rls`, policy `tenant_isolation`), introspection, emprise
   (`app.collections.extent.table_extent`) — le chemin qu'un admin suit
   aujourd'hui à la main pour enregistrer une collection.
6. Construit un `MapConfig` : une couche `{ kind: "feature", url:
   "/collections/{id}/items", paint: <défaut selon la géométrie dominante>
   }`, vue centrée sur l'emprise retournée à l'étape 5.
7. Crée un `Item(resource_type="map")` possédé par `created_by`, privé par
   défaut (mêmes règles que tout item neuf), et son `MapConfig` associé.
8. Met à jour `ingestion_jobs` : `status="done"`, `collection_id`,
   `item_id`. Toute exception aux étapes 1-7 met `status="error"` +
   `error_message`, jamais de job qui reste en `running` indéfiniment
   (retries procrastinate bornés — un job qui épuise ses retries passe en
   `error`, pas en zombie silencieux).

## 7. UI shell (minimale)

Nouvelle action **« Importer un fichier »** dans le catalogue (à côté de
« Nouveau ») :

1. Sélection du fichier + titre de la collection cible.
2. `POST /uploads/presign` → `PUT` direct MinIO (barre de progression basée
   sur l'événement `progress` de la requête).
3. Pour un CSV : aperçu des en-têtes ; si l'auto-détection lat/lon échoue,
   deux `<select>` apparaissent pour les choisir manuellement avant de
   continuer.
4. `POST /uploads` → poll court (`GET /uploads/{jobId}` toutes les 1-2 s,
   quelques dizaines de secondes max en pratique vu la taille visée par
   6a) → redirection vers l'item carte créé une fois `status="done"`.
5. `status="error"` : affiche `errorMessage` tel quel, permet de recommencer.

Pas de suivi multi-jobs ni de notification en tâche de fond — c'est le
périmètre de SP-6c.

## 8. Permissions

Tout utilisateur authentifié peut uploader (pas de restriction admin,
contrairement à l'enregistrement manuel d'une collection existante en
SP-3a) — la collection et l'item créés lui appartiennent, partage privé par
défaut, modifiable ensuite via les mécanismes de partage existants.

## 9. Tests

- **Cœur** :
  - Unitaires des parseurs (GeoJSON/CSV valides et invalides), en pur
    Python, sans base de données.
  - Intégration de la tâche procrastinate (exécution synchrone en mode
    test — `procrastinate` fournit un mode de test dédié), sur une vraie
    table PostGIS (infra de test existante marquée `postgis`) : vérifie la
    création de la collection, l'emprise, l'item carte, et la mise à jour
    du job.
  - API (`presign`, `create`, `get`) : permissions (un job d'un autre
    tenant renvoie 404), validation des entrées.
- **Shell** :
  - Test unitaire du formulaire d'import (mock `presign`/`PUT`/`create`/
    poll), y compris le chemin de détection lat/lon manuelle.
  - **Une spec E2E** (18ᵉ, `shell/e2e/ingestion.spec.ts`) : upload d'un
    petit GeoJSON via l'UI → item carte visible avec les entités
    importées.

## 10. Hors périmètre (rappel)

- GeoPackage, Shapefile zippé, détection/reprojection de CRS non-WGS84 →
  SP-6b.
- Suivi de job en direct dans l'UI, notifications, PMTiles/tippecanoe pour
  les grosses couches → SP-6c.
- Ajout à une collection existante (upsert) : toujours une nouvelle
  collection en 6a ; réévalué si un besoin utilisateur réel apparaît.
- Détection de CRS pour le CSV (WGS84 supposée, comme le GeoJSON).

## 11. Critères d'acceptation (SP-6a)

- Un GeoJSON valide (points/lignes/polygones) uploadé via l'UI produit une
  collection interrogeable (`GET /collections/{id}/items`) et un item carte
  visible avec les entités, sans intervention manuelle après le clic
  d'upload.
- Un CSV avec colonnes `lat`/`lon` standard produit le même résultat sans
  saisie manuelle ; un CSV aux colonnes ambiguës demande la sélection
  manuelle avant de continuer.
- Un fichier corrompu (JSON malformé, CSV avec des `lat` non numériques)
  produit `status="error"` avec un message lisible pointant la ligne/
  feature fautive, jamais un job bloqué en `pending`/`running`.
- Toutes les specs E2E existantes (17) restent vertes + la nouvelle (18).
