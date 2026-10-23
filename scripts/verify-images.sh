#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# AUD-113 : vérifie côté consommateur la signature cosign keyless de chaque image
# ghcr.io/tlenenao/geostudio-* du compose de production, au tag GEOSTUDIO_VERSION
# (ou en argument). Voir docs/supply-chain.md. Exige `cosign` et `docker compose`.
set -euo pipefail

tag="${1:-${GEOSTUDIO_VERSION:-}}"
[ -n "$tag" ] || { echo "usage : verify-images.sh <tag>  (ou GEOSTUDIO_VERSION)" >&2; exit 2; }
command -v cosign >/dev/null || { echo "cosign introuvable (https://docs.sigstore.dev/cosign/)" >&2; exit 2; }

identity='^https://github.com/tlenenao/geostudio/\.github/workflows/'
issuer='https://token.actions.githubusercontent.com'

# Les images sont lues dans le fichier de production, pas dupliquées ici.
images="$(grep -oE 'ghcr\.io/tlenenao/geostudio-[a-z0-9-]+' docker-compose.prod.yml | sort -u)"
fail=0
for img in $images; do
  if cosign verify --certificate-identity-regexp "$identity" \
      --certificate-oidc-issuer "$issuer" "$img:$tag" >/dev/null 2>&1; then
    echo "OK   $img:$tag"
  else
    echo "FAIL $img:$tag" >&2
    fail=1
  fi
done
exit "$fail"
