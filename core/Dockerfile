FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

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
# à égress restreint/air-gapped. Aucun USER switch dans cette image : le
# process de build et le process runtime tournent sous le même utilisateur,
# donc le même répertoire d'extensions (~/.duckdb/extensions) est réutilisé.
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL spatial')"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

EXPOSE 8200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
