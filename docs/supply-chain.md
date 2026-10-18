# Chaîne d'approvisionnement : ce qui est garanti, comment le vérifier

## À la publication (CI)

- Actions GitHub **épinglées par SHA**.
- Images `ghcr.io/tlenenao/geostudio-*` construites par `_build-and-push.yml`, **signées
  par cosign en mode keyless** (identité = les workflows de ce dépôt) ; releases :
  SBOM SPDX + attestation, scan Trivy (informatif, déposé dans l'onglet *Security*).
- `docker-compose.digests.yml` (artefact de release) épingle chaque image par digest.
- Dépendances Python figées par `core/uv.lock` — **toutes** les images Python, export-worker
  compris — et auditées par `pip-audit --strict` ; npm par `npm audit` (seuil *high*).
- **Licences** : `core/scripts/check_licenses.py` et `shell/scripts/check-licenses.mjs`
  refusent GPL/AGPL ; une LGPL doit être déclarée avec sa raison dans
  `core/license-exceptions.json` (lien dynamique uniquement).
- Dependabot : Python, npm, Actions, Dockerfiles, **cargo** (sidecar desktop), **npm
  desktop**, **images des compose** et **chart Helm**.
- Binaire `mc` (image de sauvegarde, AGPL) vérifié par **sha256** au build.
- Compose de production : pas de repli `latest` — `GEOSTUDIO_VERSION` est requis.

## Côté consommateur : vérifier avant de déployer

```bash
./scripts/verify-images.sh vX.Y.Z      # exige cosign ; chaque image du compose de production
# ou, à l'installation :
INSTALL_VERIFY_SIGNATURES=1 ./scripts/install.sh
```

Équivalent manuel pour une image :

```bash
cosign verify \
  --certificate-identity-regexp '^https://github.com/tlenenao/geostudio/\.github/workflows/' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/tlenenao/geostudio-core:vX.Y.Z
```

Pour épingler par digest : `docker compose -f docker-compose.yml -f docker-compose.prod.yml
-f docker-compose.digests.yml up -d` avec le fichier joint à la release. Le SBOM d'une
image se vérifie avec `gh attestation verify oci://ghcr.io/tlenenao/geostudio-core:vX.Y.Z
--repo tlenenao/geostudio`.

## Limites connues (décisions assumées)

- **Jamais rejoué sur une release réelle** (AUD-177) : la signature, l'attestation et
  `verify-images.sh` sont testés avec des doublures ; la première release signée est
  leur première exécution réelle — la rejouer et corriger ici au besoin.
- **Images de base sans digest** (`python:3.12-slim`, `node:22-slim`, `nginx`, `debian`…) : tags
  flottants au sein d'une branche mineure ; l'épinglage par digest sera fait avec Dependabot
  Docker une fois la cadence de mises à jour acceptée. Les images GeoStudio **publiées** sont,
  elles, reproductibles par digest.
- **Trivy ne bloque pas** la publication (une CVE d'image de base ne doit pas empêcher un
  correctif) ; le rapport est examiné à chaque release.
- **Canal `edge`** : image signée mais sans SBOM ni scan (coût) ; ne pas l'utiliser en production.
- **Extensions DuckDB** (`httpfs`, `spatial`, `h3` communautaire) téléchargées au build, absentes
  du SBOM.
- Keycloak 24.0.5, pgbouncer et martin sont suivis par Dependabot (compose) mais leur montée
  de version reste une décision manuelle.
