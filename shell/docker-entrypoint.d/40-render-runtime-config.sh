#!/bin/sh
set -eu
envsubst '${VITE_CORE_URL} ${VITE_MARTIN_URL} ${VITE_OIDC_AUTHORITY} ${VITE_OIDC_CLIENT_ID} ${VITE_OIDC_REDIRECT_URI} ${VITE_AUTH_MODE}' \
  < /usr/share/nginx/html/env-config.template.js \
  > /usr/share/nginx/html/env-config.js
