FROM python:3.12-slim

WORKDIR /app

# libexpat1 : python:3.12-slim (Debian trixie) ne l'embarque plus par défaut,
# alors que le module stdlib `pyexpat` (utilisé par `defusedxml`, dépendance
# directe du cœur — app/mapicons/svg.py, app/harvest/connectors/ows.py) le
# charge dynamiquement au runtime. Sans lui : ImportError "libexpat.so.1:
# cannot open shared object file" dès qu'un des trois services construits
# depuis cette image (core/worker/cdc-worker) importe `app.jobs`, qui
# enregistre toutes les tâches y compris celles import ant ces modules.
RUN apt-get update \
  && apt-get install -y --no-install-recommends libexpat1 \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# Utilisateur non-root (SP-26/3.6) — créé avant l'installation des
# extensions DuckDB : HOME doit être fixé ET rester identique entre le
# build (encore root ici) et l'exécution (USER app plus bas), sinon DuckDB
# ne retrouve plus ~/.duckdb/extensions à l'exécution et retente un
# INSTALL réseau — cf. commentaire historique juste en dessous.
#
# uid/gid FIXES à 1001 (pas --system sans le préciser) — revue finale SP-26
# (C1) : ce conteneur (via docker-compose.yml's `worker`, `build: ./core`,
# même image que `core`) et deploy/qgis-worker/Dockerfile (utilisateur
# `qgis`) se partagent le volume nommé `etl-scratch:/scratch` —
# core/app/pipelines/runtime.py y écrit `in.gpkg` comme `app`, puis le
# sidecar qgis-worker y écrit `out.gpkg` comme `qgis`. `useradd --system`
# sans uid explicite laisse chaque image allouer le premier uid système
# libre indépendamment — qgis/qgis:release-3_34 (Ubuntu) et
# python:3.12-slim (Debian) n'ont aucune garantie de converger sur le même
# nombre. 1001 vérifié libre dans les deux images de base au moment de ce
# correctif (`getent passwd 1001` échoue dans les deux) ; à revérifier si
# l'une des deux images de base change de distribution/version.
RUN groupadd --system --gid 1001 app \
  && useradd --system --uid 1001 --gid app --home-dir /opt/geostudio-home --create-home app
ENV HOME=/opt/geostudio-home

COPY pyproject.toml ./
# Installe directement depuis [project.dependencies] de pyproject.toml (pas
# de [build-system] dans ce fichier, donc `uv pip install -r pyproject.toml`
# ne fait qu'installer les dépendances listées, sans tenter de construire/
# installer le paquet geostudio-core lui-même). Remplace une liste dupliquée
# à la main qui avait dérivé à plusieurs reprises (alembic/pyjwt/boto3/
# python-multipart/mcp puis defusedxml, chacun crash-loopant le conteneur au
# premier import manquant) — une seule source de vérité désormais.
RUN uv pip install --system --no-cache -r pyproject.toml

# Pré-installe les extensions DuckDB httpfs/spatial (SP-11b, module
# app/analytics/duckdb_conn.py) sur le disque de l'image, au build — sans
# quoi le premier POST /collections/{id}/aggregate en runtime déclencherait
# un INSTALL réseau vers extensions.duckdb.org, qui échoue en déploiement
# à égress restreint/air-gapped. Toujours root ici (HOME fixé ci-dessus,
# écrit dans /opt/geostudio-home) ; USER app plus bas réutilise le même
# HOME, donc le même répertoire d'extensions (~/.duckdb/extensions).
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL spatial'); c.execute('INSTALL h3 FROM community')"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

# /scratch (revue finale SP-26, C1) : cette même image sert aussi le service
# `worker` de docker-compose.yml, qui monte le volume nommé `etl-scratch` sur
# /scratch — core/app/pipelines/runtime.py et core/app/terrain3d/jobs.py y
# écrivent au runtime (os.makedirs("/scratch", ...) puis des fichiers dedans).
# Sans ce mkdir+chown ici, Docker crée le point de montage en root:root au
# premier démarrage (le répertoire n'existe pas dans l'image), et l'utilisateur
# non-root `app` échoue en PermissionError — même mécanisme, et même correctif,
# que deploy/backup/Dockerfile pour /backup/archives et
# deploy/qgis-worker/Dockerfile pour /scratch lui-même côté sidecar QGIS.
# Le service `core` (pas seulement `worker`) construit aussi cette image mais
# ne monte pas /scratch — inoffensif, ce mkdir ne coûte rien pour lui.
RUN mkdir -p /scratch && chown -R app:app /opt/geostudio-home /app /scratch
USER app

EXPOSE 8200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
