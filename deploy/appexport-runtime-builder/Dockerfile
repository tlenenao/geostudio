# deploy/appexport-runtime-builder/Dockerfile
# Bâtit une fois le runtime d'export statique générique (shell/dist-export)
# et le copie dans un volume Docker partagé avec `worker` — jamais rebâti
# par export (SP-18a, plan §Architecture). Contexte = racine du dépôt (pas
# ./shell) : c'est le seul service de la stack dont c'est le cas, pour
# pouvoir COPY shell/ sans changer le contexte des autres services Node.
FROM node:20-slim
WORKDIR /build
COPY shell/package.json shell/package-lock.json ./
RUN npm ci
COPY shell/ .
RUN npm run build:export-runtime
CMD ["sh", "-c", "mkdir -p /export-runtime && cp -r dist-export/* /export-runtime/ && echo 'export runtime built'"]
