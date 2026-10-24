# deploy/export-worker/Dockerfile
# Miroir de core/Dockerfile (même dépendances, mêmes extensions DuckDB
# préinstallées) + Chromium Playwright. Volontairement un Dockerfile séparé
# plutôt qu'ajouter Playwright à core/Dockerfile : le binaire Chromium avec
# ses dépendances système pèse plusieurs centaines de Mo, que ni `core` ni
# le `worker` partagé (ingestion/search/cdc/etl) n'ont besoin de porter
# (SP-17a, design §Infrastructure — même rationale que deploy/qgis-worker,
# à ceci près que la raison ici est le poids de l'image, pas une licence).
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

WORKDIR /app

RUN pip install --no-cache-dir uv==0.11.21

RUN groupadd --system app && useradd --system --gid app --home-dir /opt/geostudio-home --create-home app
ENV HOME=/opt/geostudio-home

# AUD-111 : versions figées par uv.lock (même fichier que core/Dockerfile, donc couvertes
# par le `pip-audit` de la CI) — plus de résolution flottante à chaque rebuild.
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/requirements.txt \
  && uv pip install --system --no-cache -r /tmp/requirements.txt
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL spatial'); c.execute('INSTALL h3 FROM community')"
RUN python -m playwright install --with-deps chromium

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
# AUD-187 : liste blanche (cf. core/Dockerfile) ; pas de spike_*/measure_*/audit_*.
COPY scripts/__init__.py scripts/healthcheck_worker_stalled.py scripts/ensure_procrastinate_schema.py ./scripts/

# Playwright/Chromium écrit son cache sous $HOME/.cache par défaut au
# premier lancement si absent — installé ci-dessus alors que HOME est déjà
# fixé, donc déjà sous /opt/geostudio-home. chown après tous les COPY/RUN
# précédents pour couvrir le cache Chromium en plus des extensions DuckDB.
RUN chown -R app:app /opt/geostudio-home /app
USER app

CMD ["python", "-m", "procrastinate", "--app", "app.jobs.app", "worker", "-q", "export"]
