# deploy/appexport-runtime-builder/Dockerfile
# Bâtit une fois le runtime d'export statique générique (shell/dist-export)
# et le copie dans un volume Docker partagé avec `worker` — jamais rebâti
# par export (SP-18a, plan §Architecture). Contexte = racine du dépôt (pas
# ./shell) : c'est le seul service de la stack dont c'est le cas, pour
# pouvoir COPY shell/ sans changer le contexte des autres services Node.
FROM node:20-slim
WORKDIR /build
# uid/gid FIXE à 1001 (revue finale SP-26 round 2, N2) — même convention que
# core/Dockerfile (`app`), deploy/qgis-worker/Dockerfile (`qgis`, C1) et
# deploy/backup/Dockerfile (`backup`, N1) : donne au runbook de migration
# non-root (docs/runbooks/2026-08-27-migration-conteneurs-non-root.md) un
# nombre stable à documenter pour le volume nommé `appexport-runtime`,
# plutôt qu'un uid laissé au hasard de l'allocation `--system` de Debian.
# Pas de contrainte de convergence avec `app`/`qgis`/`backup` ici (aucun
# volume partagé avec eux, `appexport-runtime` n'a que ce service en
# écriture — `worker` le monte en lecture seule) — 1001 choisi seulement
# pour la cohérence documentaire. Vérifié libre dans node:20-slim au moment
# de ce correctif (`getent passwd 1001`/`getent group 1001` échouent tous
# les deux ; `node` y occupe déjà 1000).
RUN groupadd --system --gid 1001 builder \
  && useradd --system --uid 1001 --gid builder --create-home builder
COPY shell/package.json shell/package-lock.json ./
RUN npm ci
COPY shell/ .
RUN npm run build:export-runtime
RUN mkdir -p /export-runtime && chown -R builder:builder /build /export-runtime
USER builder
CMD ["sh", "-c", "mkdir -p /export-runtime && cp -r dist-export/* /export-runtime/ && echo 'export runtime built'"]
