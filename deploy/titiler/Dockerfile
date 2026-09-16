# deploy/titiler/Dockerfile
# Reproduit à l'identique dockerfiles/Dockerfile.gunicorn du dépôt
# developmentseed/titiler (tag 0.18.4, la version actuellement consommée —
# ce chantier ne monte PAS de version titiler, il rapatrie exactement ce qui
# est déployé aujourd'hui). L'image tierce ghcr.io/developmentseed/titiler
# est mono-arch amd64, mais sa PROPRE base,
# ghcr.io/vincentsarago/uvicorn-gunicorn (recette officielle titiler), est
# multi-arch — le blocage est une lacune de publication côté devseed, pas
# une limite technique GDAL/rasterio (rasterio 1.4.4 publie des wheels
# manylinux_2_28_aarch64 sur PyPI : pas de compilation requise ici).
#
# Épinglage par version PyPI plutôt que COPY src/titiler/ + build depuis les
# sources (comme le fait l'amont) : plus simple à maintenir dans ce dépôt,
# comportement runtime identique — titiler.application.main:app est le même
# point d'entrée. Coût de possession assumé : une future montée de version
# de titiler en amont nécessitera de rebasculer à la main ces 4 numéros de
# version — même modèle que deploy/postgis/Dockerfile (pgvector/wal2json).
ARG PYTHON_VERSION=3.11
FROM ghcr.io/vincentsarago/uvicorn-gunicorn:${PYTHON_VERSION}
RUN python -m pip install -U pip
RUN python -m pip install --no-cache-dir \
      "titiler.core==0.18.4" \
      "titiler.extensions[cogeo,stac]==0.18.4" \
      "titiler.mosaic==0.18.4" \
      "titiler.application==0.18.4"
ENV MODULE_NAME=titiler.application.main
ENV VARIABLE_NAME=app
