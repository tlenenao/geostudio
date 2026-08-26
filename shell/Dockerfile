FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Build-time public config; override at build with --build-arg as needed.
ARG VITE_CORE_URL=http://localhost:8200
ARG VITE_OIDC_AUTHORITY=http://localhost:8180/realms/geostudio
ARG VITE_OIDC_CLIENT_ID=geostudio-shell
ARG VITE_OIDC_REDIRECT_URI=http://localhost:8300/
ENV VITE_CORE_URL=$VITE_CORE_URL \
    VITE_OIDC_AUTHORITY=$VITE_OIDC_AUTHORITY \
    VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID \
    VITE_OIDC_REDIRECT_URI=$VITE_OIDC_REDIRECT_URI
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY env-config.template.js /usr/share/nginx/html/env-config.template.js
COPY docker-entrypoint.d/40-render-runtime-config.sh /docker-entrypoint.d/40-render-runtime-config.sh
# nginx:alpine crée déjà un utilisateur système `nginx` (uid/gid 101) pour
# ses workers — réutilisé directement plutôt qu'un nouvel utilisateur.
# /usr/share/nginx/html doit rester inscriptible par cet utilisateur :
# 40-render-runtime-config.sh y écrit env-config.js à CHAQUE démarrage de
# conteneur (docker-entrypoint.d tourne avant que nginx ne serve), et ce
# script s'exécute désormais lui aussi sous USER nginx (plus root). /run
# (alias /var/run) ajouté au chown — trouvé empiriquement (SP-26/3.6) : le
# master nginx écrit son pidfile dans /run/nginx.pid (directive `pid` de
# /etc/nginx/nginx.conf) et échouait en `open() "/run/nginx.pid" failed
# (13: Permission denied)` sous USER nginx sans ce chown, alors que
# l'image nginx:alpine ne le prévoit que pour un master root qui, lui,
# droppe seulement ses workers en `nginx` (directive `user nginx;`).
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /run
USER nginx
EXPOSE 8300
