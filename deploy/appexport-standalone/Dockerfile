# deploy/appexport-standalone/Dockerfile
# Image générique de l'export d'app "Autoporté" (SP-18c) : bâtie UNE FOIS
# (CI/release, jamais par export — même philosophie que
# deploy/appexport-runtime-builder), publiée sur ghcr.io. Contexte = racine
# du dépôt (comme appexport-runtime-builder) : la première étape a besoin de
# shell/, la seconde de core/app/. Les données propres à un export (config
# de l'app, instantané GeoParquet) ne sont JAMAIS dans l'image — montées au
# runtime via le volume /data (cf. docker-compose.yml généré par
# build_standalone_bundle_zip, core/app/appexport/bundler.py).
FROM node:22-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS shell-runtime
WORKDIR /build
COPY shell/package.json shell/package-lock.json ./
RUN npm ci
COPY shell/ .
RUN npm run build:export-runtime
# StaticFiles(html=True) (core/app/appexport/miniserver/main.py) sert
# index.html pour "/" — le build Vite produit index.export.html
# (vite.export.config.ts's rollupOptions.input), jamais index.html.
RUN mv dist-export/index.export.html dist-export/index.html

FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home-dir /opt/geostudio-home --create-home app
ENV HOME=/opt/geostudio-home
# Dépendances volontairement minimales — PAS `uv sync`/pyproject.toml
# complet (psycopg/psycopg2-binary/Keycloak/dlt/Playwright...) : le
# mini-serveur ne parle jamais à Postgres/Keycloak/MinIO, seulement à
# DuckDB + des fichiers locaux montés en lecture seule. sqlalchemy reste
# nécessaire : app.collections.introspection (TableInfo/ColumnInfo,
# réutilisés tels quels par app.appexport.manifest) importe
# sqlalchemy.orm.Session pour un alias de type non utilisé ici — coûte
# l'installation du paquet, jamais une connexion réelle (aucun driver
# psycopg présent dans cette image).
# AUD-181 : versions figées sur celles de core/uv.lock (à tenir synchrones à la montée du verrou).
# ponytail: dépendances transitives non verrouillées ici ; `uv export --frozen` si une dérive est mesurée.
RUN pip install --no-cache-dir fastapi==0.138.1 'uvicorn[standard]==0.49.0' pydantic==2.13.4 duckdb==1.5.5 sqlalchemy==2.0.51
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL spatial')"
# Copie l'arbre app/ complet (même convention que core/Dockerfile et
# deploy/export-worker/Dockerfile) plutôt qu'un COPY sélectif fragile :
# Python n'a besoin de paquets installés que pour les modules réellement
# importés par app.appexport.miniserver.main — le reste, présent sur disque
# mais jamais importé, est inoffensif.
COPY core/app ./app
COPY --from=shell-runtime /build/dist-export /runtime
ENV APPEXPORT_STANDALONE_DATA_DIR=/data
ENV APPEXPORT_STANDALONE_RUNTIME_DIR=/runtime
RUN mkdir -p /data && chown -R app:app /opt/geostudio-home /app /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/', timeout=3)"
CMD ["uvicorn", "app.appexport.miniserver.main:app", "--host", "0.0.0.0", "--port", "8000"]
