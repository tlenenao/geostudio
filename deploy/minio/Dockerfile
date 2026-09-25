# deploy/minio/Dockerfile
# quay.io/minio/minio ET minio/minio (Docker Hub) sont verrouillés en pull
# anonyme sur TOUS les tags (401 Unauthorized / pull access denied,
# vérifié le 2026-09-25). Les recettes Docker officielles de l'amont sont
# elles-mêmes cassées : son Dockerfile top-level fait `FROM
# minio/minio:latest` (circulaire — dépend du dépôt verrouillé). Seule sa
# cible Makefile `build` (un simple `go build` d'un module Go pur, sans
# dépendance à un registre) reste reproductible — c'est elle que ce
# Dockerfile reproduit, PAS `make docker`.
ARG MINIO_RELEASE=RELEASE.2025-10-15T17-29-55Z

FROM --platform=$BUILDPLATFORM golang:1.24-bookworm AS build
ARG MINIO_RELEASE
ARG TARGETARCH
WORKDIR /src
# MINIO_RELEASE=RELEASE (variable d'environnement lue par
# buildscripts/gen-ldflags.go, distincte de l'ARG Docker de même nom
# ci-dessus) fait porter au binaire un préfixe de version
# "RELEASE.<tag>" au lieu de "DEVELOPMENT.<tag>" par défaut — vérifié :
# sans cette variable, `minio --version` affiche
# DEVELOPMENT.2025-10-15T17-29-55Z. Cosmétique (le binaire est identique)
# mais trompeur en diagnostic d'incident ; l'amont ne publie pas la
# recette CI exacte qui positionne cette variable pour ses propres builds
# de release — reconstituée ici par lecture de
# buildscripts/gen-ldflags.go.
RUN git clone --depth 1 --branch "${MINIO_RELEASE}" https://github.com/minio/minio . \
    && MINIO_RELEASE=RELEASE CGO_ENABLED=0 GOARCH="${TARGETARCH}" \
       go build -tags kqueue -trimpath \
       --ldflags "$(MINIO_RELEASE=RELEASE go run buildscripts/gen-ldflags.go)" \
       -o /out/minio

FROM debian:bookworm-slim
# ca-certificates : TLS sortant (un déploiement peut pointer ce MinIO en
# mode passerelle/réplication vers un vrai S3). curl : le healthcheck
# compose existant (curl -f .../minio/health/live) reste inchangé.
# Binaire standalone (CGO_ENABLED=0) : aucune autre dépendance runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/minio /usr/bin/minio
COPY --from=build /src/dockerscripts/docker-entrypoint.sh /usr/bin/docker-entrypoint.sh
RUN chmod +x /usr/bin/minio /usr/bin/docker-entrypoint.sh

# Cette image DISTRIBUE ET EXPOSE COMME SERVICE RÉSEAU un binaire AGPL —
# contrairement à deploy/backup/Dockerfile (mc, invoqué en sous-processus,
# jamais servi sur le réseau), voir LICENSE-MINIO.md pour l'analyse
# complète de la clause réseau AGPL §13, qui s'applique directement ici.
COPY --from=build /src/LICENSE /licenses/LICENSE
COPY --from=build /src/CREDITS /licenses/CREDITS
COPY LICENSE-MINIO.md /LICENSE-MINIO.md
LABEL org.opencontainers.image.licenses="AGPL-3.0-or-later AND Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/tlenenao/geostudio"
LABEL org.opencontainers.image.description="Serveur MinIO (stockage objet S3) recompile depuis les sources AGPL officielles (github.com/minio/minio) car quay.io/minio/minio et minio/minio sont verrouilles en pull anonyme. Voir /LICENSE-MINIO.md."

EXPOSE 9000 9001
ENTRYPOINT ["/usr/bin/docker-entrypoint.sh"]
CMD ["minio"]
