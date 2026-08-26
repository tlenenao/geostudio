# deploy/export-worker/Dockerfile
# Miroir de core/Dockerfile (même dépendances, mêmes extensions DuckDB
# préinstallées) + Chromium Playwright. Volontairement un Dockerfile séparé
# plutôt qu'ajouter Playwright à core/Dockerfile : le binaire Chromium avec
# ses dépendances système pèse plusieurs centaines de Mo, que ni `core` ni
# le `worker` partagé (ingestion/search/cdc/etl) n'ont besoin de porter
# (SP-17a, design §Infrastructure — même rationale que deploy/qgis-worker,
# à ceci près que la raison ici est le poids de l'image, pas une licence).
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

RUN groupadd --system app && useradd --system --gid app --home-dir /opt/geostudio-home --create-home app
ENV HOME=/opt/geostudio-home

COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL spatial'); c.execute('INSTALL h3 FROM community')"
RUN python -m playwright install --with-deps chromium

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

# Playwright/Chromium écrit son cache sous $HOME/.cache par défaut au
# premier lancement si absent — installé ci-dessus alors que HOME est déjà
# fixé, donc déjà sous /opt/geostudio-home. chown après tous les COPY/RUN
# précédents pour couvrir le cache Chromium en plus des extensions DuckDB.
RUN chown -R app:app /opt/geostudio-home /app
USER app

CMD ["python", "-m", "procrastinate", "--app", "app.jobs.app", "worker", "-q", "export"]
