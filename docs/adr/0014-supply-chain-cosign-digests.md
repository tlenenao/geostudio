# 0014 — Chaîne d'approvisionnement : cosign keyless, attestation SBOM, digests

Statut: acceptée — points 1, 2 et 4 implémentés (2026-10-11), **jamais exécutés sur un vrai run GitHub** ; point 3 (bases épinglées par digest) reste à faire
Source : spec `docs/superpowers/specs/2026-10-04-cloture-backlog-38-rev-design.md` (arbitrage 281 b, QCM 2026-10-04) ; REV-281 (b) ; SP-22 (SBOM/Trivy/Dependabot), `core/scripts/check_published_images.py`.

## Contexte

Neuf images `ghcr.io/tlenenao/geostudio-*` sont publiées par `release.yml`/`publish-edge.yml` (via `_build-and-push.yml`). État réel relevé dans le dépôt le 2026-10-07 : un SBOM SPDX est généré par `anchore/sbom-action` mais **publié seulement comme artefact de run** (pas attaché à l'image) ; **aucune signature** cosign ni attestation ; aucun `@sha256:` dans les compose ni les `FROM` des Dockerfile ; Dependabot (`docker`, 9 répertoires) surveille les tags flottants des images de base. Un consommateur du compose de production s'appuie donc sur des tags mutables : rien ne prouve qu'une image tirée sort du workflow du dépôt.

## Décision

1. Chaque image publiée est **signée par cosign en mode keyless** (identité OIDC du workflow GitHub Actions, journal Rekor) et porte une **attestation SBOM** attachée au digest.
2. Le compose de production référence les images **par digest**, écrit par le workflow de release et non à la main ; le tag reste en commentaire.
3. Les images de base des `Dockerfile` sont **épinglées par digest** (`FROM image:tag@sha256:…`), mises à jour par Dependabot `docker`.
4. `check_published_images.py` vérifie en plus la signature de chaque image pour l'identité de workflow attendue.

## Conséquences

- **Implémenté, non vérifié en réel** (REV-281 (b)) : `_build-and-push.yml` signe chaque image par digest (`cosign sign --yes <image>@<digest>`, `sigstore/cosign-installer` épinglé par SHA) et attache l'attestation SBOM via `actions/attest` (et non `actions/attest-sbom`, déprécié) ; chaque leg exporte `digests/<image>.digest` ; le job `pin-digests` de `release.yml` génère `docker-compose.digests.yml` (override `image: …@sha256:…` de `docker-compose.prod.yml`, `core/scripts/pin_compose_digests.py`) ; `check_published_images.py --verify-signatures` (appelé par `verify-published` des deux workflows) lance `cosign verify` par digest. La première exécution réelle est celle du prochain tag `v*.*.*` : un échec de signature ou de vérification y est attendu et acceptable à corriger. Le tag `edge` est signé lui aussi (les permissions du workflow appelé doivent de toute façon être accordées par l'appelant) mais reste un confort, jamais utilisé en production.
- Reste à faire : point 3 (`FROM … @sha256:` dans les `Dockerfile`).
- Le workflow de release devra déclarer `id-token: write` (+ `attestations: write`) **sur le job appelé et sur l'appelant du workflow réutilisable** : spécifier une permission met les autres à `none` (incident Proxmox, historique d'exécution).
- Un opérateur pourra vérifier : `cosign verify --certificate-identity-regexp '^https://github.com/tlenenao/geostudio/.github/workflows/' --certificate-oidc-issuer https://token.actions.githubusercontent.com <image>@<digest>`.
- L'épinglage par digest fige les correctifs de sécurité des bases : Dependabot `docker` devient la seule voie de mise à jour. Le tag `edge` reste un confort non signé, jamais utilisé en production.
- Hors périmètre : signature des exports d'app (SP-18), contrôle d'admission côté cluster.
