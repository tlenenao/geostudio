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

CMD ["python3", "/app/server.py"]
