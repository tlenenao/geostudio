# qgis/qgis:release-3_34 = QGIS 3.34.5 "Prizren" (LTR) — PAS :latest, qui
# pointe vers un build 4.3.0-Master instable (vérifié en design, §2).
FROM qgis/qgis:release-3_34

# Doit précéder le RUN qgis_process ci-dessous : sans display X et sans ce
# réglage, qgis_process avorte (Qt "could not connect to display") même
# pour une commande headless comme `plugins enable` — vérifié à l'exécution
# de cette tâche (le Dockerfile du design le plaçait après le RUN).
ENV QT_QPA_PLATFORM=offscreen

# grassprovider fournit les ids grass7:* (dont grass7:r.watershed, le cas
# hydrologie de l'étude de faisabilité) mais est désactivé par défaut —
# vérifié en design (qgis_process plugins list). L'activer ici l'écrit dans
# le profil QGIS gravé dans cette image ; l'activer au runtime ne
# survivrait pas à un `docker run --rm` frais (design §2 point 6).
#
# HOME fixé avant l'activation du plugin GRASS (SP-26/3.6) : qgis_process
# écrit l'état "grassprovider activé" dans un profil sous $HOME/.local/
# share/QGIS/QGIS3/profiles/default — un HOME différent à l'exécution
# (non-root) le verrait désactivé, cassant silencieusement tous les
# grass7:* de l'allowlist figée (core/app/pipelines/ops/
# qgis_algorithms.json). Même mécanisme que core/Dockerfile pour DuckDB.
#
# uid/gid FIXES à 1001 — MÊME nombre que l'utilisateur `app` de
# core/Dockerfile (revue finale SP-26, C1). Ce sidecar et le service
# `worker` (même image que `core`) se partagent le volume nommé
# `etl-scratch:/scratch` : core/app/pipelines/runtime.py écrit `in.gpkg`
# comme `app`, ce serveur écrit `out.gpkg` dans le même répertoire comme
# `qgis` — sans uid identique, l'un des deux échoue en PermissionError
# selon lequel des deux conteneurs a démarré (et donc peuplé le volume nommé)
# en premier. `useradd --system` sans uid explicite laisse chaque image de
# base allouer indépendamment le premier uid système libre ; rien ne
# garantit qu'Ubuntu (cette image) et Debian (python:3.12-slim, core/
# Dockerfile) convergent. 1001 vérifié libre dans les deux images de base au
# moment de ce correctif (`getent passwd 1001` échoue dans les deux) ; à
# revérifier si l'une des deux images de base change de distribution/version.
RUN groupadd --system --gid 1001 qgis \
  && useradd --system --uid 1001 --gid qgis --home-dir /opt/qgis-home --create-home qgis
ENV HOME=/opt/qgis-home

RUN qgis_process plugins enable grassprovider

COPY server.py /app/server.py
COPY allowlist.txt /app/allowlist.txt

# Cette image est désormais PUBLIÉE sur ghcr.io (SP-21) — c'est un acte de
# distribution de QGIS et GRASS, tous deux sous GPL. La notice voyage donc
# avec l'image, pas seulement dans le dépôt.
COPY LICENSE-QGIS.md /LICENSE-QGIS.md
LABEL org.opencontainers.image.licenses="GPL-2.0-or-later AND Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/tlenenao/geostudio"
LABEL org.opencontainers.image.description="Sidecar QGIS Processing pour GeoStudio — contient QGIS et GRASS (GPL). Voir /LICENSE-QGIS.md."

RUN mkdir -p /scratch && chown -R qgis:qgis /opt/qgis-home /app /scratch
USER qgis

CMD ["python3", "/app/server.py"]
