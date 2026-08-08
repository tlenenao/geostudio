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

COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL spatial'); c.execute('INSTALL h3 FROM community')"
RUN python -m playwright install --with-deps chromium

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

CMD ["python", "-m", "procrastinate", "--app", "app.jobs.app", "worker", "-q", "export"]
