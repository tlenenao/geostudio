# 0014 — Chaîne d'approvisionnement : cosign keyless, attestation SBOM, digests

Statut: acceptée (cible actée, non implémentée à la date de l'ADR)
Source : spec `docs/superpowers/specs/2026-10-04-cloture-backlog-38-rev-design.md` (arbitrage 281 b, QCM 2026-10-04) ; REV-281 (b) ; SP-22 (SBOM/Trivy/Dependabot), `core/scripts/check_published_images.py`.

## Contexte

Neuf images `ghcr.io/tlenenao/geostudio-*` sont publiées par `release.yml`/`publish-edge.yml` (via `_build-and-push.yml`). État réel relevé dans le dépôt le 2026-10-07 : un SBOM SPDX est généré par `anchore/sbom-action` mais **publié seulement comme artefact de run** (pas attaché à l'image) ; **aucune signature** cosign ni attestation ; aucun `@sha256:` dans les compose ni les `FROM` des Dockerfile ; Dependabot (`docker`, 9 répertoires) surveille les tags flottants des images de base. Un consommateur du compose de production s'appuie donc sur des tags mutables : rien ne prouve qu'une image tirée sort du workflow du dépôt.

## Décision

1. Chaque image publiée est **signée par cosign en mode keyless** (identité OIDC du workflow GitHub Actions, journal Rekor) et porte une **attestation SBOM** attachée au digest.
2. Le compose de production référence les images **par digest**, écrit par le workflow de release et non à la main ; le tag reste en commentaire.
3. Les images de base des `Dockerfile` sont **épinglées par digest** (`FROM image:tag@sha256:…`), mises à jour par Dependabot `docker`.
4. `check_published_images.py` vérifie en plus la signature de chaque image pour l'identité de workflow attendue.

## Conséquences

- **Rien de ceci n'est câblé** : l'implémentation est un chantier à part (REV-281 (b) reste partiellement fermée, la décision étant seule actée ici).
- Le workflow de release devra déclarer `id-token: write` (+ `attestations: write`) **sur le job appelé et sur l'appelant du workflow réutilisable** : spécifier une permission met les autres à `none` (incident Proxmox, historique d'exécution).
- Un opérateur pourra vérifier : `cosign verify --certificate-identity-regexp '^https://github.com/tlenenao/geostudio/.github/workflows/' --certificate-oidc-issuer https://token.actions.githubusercontent.com <image>@<digest>`.
- L'épinglage par digest fige les correctifs de sécurité des bases : Dependabot `docker` devient la seule voie de mise à jour. Le tag `edge` reste un confort non signé, jamais utilisé en production.
- Hors périmètre : signature des exports d'app (SP-18), contrôle d'admission côté cluster.
