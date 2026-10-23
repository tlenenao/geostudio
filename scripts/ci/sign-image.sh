#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# AUD-177 : signature cosign keyless IDEMPOTENTE d'une image par digest. Un build bit-à-bit
# identique (cache buildx) redonne le même digest ; re-signer ce digest échoue en 409
# « an equivalent entry already exists in the transparency log » (run Publish edge du
# 2026-10-18). Si le digest porte déjà une signature de nos workflows, on ne re-signe pas.
# usage : sign-image.sh <ghcr.io/org/image@sha256:…>
set -euo pipefail
ref="${1:?usage : sign-image.sh <image@digest>}"
identity='^https://github.com/tlenenao/geostudio/\.github/workflows/'
issuer='https://token.actions.githubusercontent.com'

if cosign verify --certificate-identity-regexp "$identity" \
    --certificate-oidc-issuer "$issuer" "$ref" >/dev/null 2>&1; then
  echo "déjà signé, rien à faire : $ref"
  exit 0
fi
cosign sign --yes "$ref"
