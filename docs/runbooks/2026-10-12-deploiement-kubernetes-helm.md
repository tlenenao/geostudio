# Runbook — déploiement Kubernetes (chart Helm, ARC-29)

Chart : `deploy/helm/geostudio/`. Images : `ghcr.io/tlenenao/geostudio-{core,shell,export-worker}` en
amd64 **et** arm64 (release multi-arch). Garde-fou : `core/tests/test_helm_chart.py` (équivalent de
`test_deployability.py`) + workflow `.github/workflows/helm-chart.yml` (lint, rendu, fumée kind).

## Ce que le chart déploie / ne déploie pas

| Déployé | Externe (à fournir, via `config.*` et le Secret) |
|---|---|
| `core` (+ migrations `alembic upgrade head` au démarrage), `worker`, `cdc-worker`, `shell` | Postgres (PostGIS + pgvector, `wal_level=logical`), pgbouncer optionnel |
| `export-worker` (`exportWorker.enabled`) | S3 compatible (MinIO) et ses buckets, Keycloak/OIDC, titiler |
| `otel-lgtm` (`observability.enabled`) | Martin, passerelle `/admin/*` (Traefik compose), `appexport-runtime-builder` |
| Ingress (`ingress.enabled`, deux hôtes : shell et API) | Dashboards Grafana provisionnés (le chart lance `otel-lgtm` nu) |

## Installation

```bash
kubectl create secret generic gs-secrets \
  --from-literal=DATABASE_URL='postgresql+psycopg://gis:...@pgbouncer:6432/gis' \
  --from-literal=CDC_DATABASE_URL='postgresql://gis:...@postgis:5432/gis' \
  --from-literal=CORE_SECRETS_MASTER_KEY="$(head -c 32 /dev/urandom | base64)" \
  --from-literal=S3_ACCESS_KEY=... --from-literal=S3_SECRET_KEY=...
helm install gs deploy/helm/geostudio --set secrets.existingSecret=gs-secrets \
  -f mes-valeurs.yaml   # config.CORE_OIDC_*, config.S3_ENDPOINT_URL, config.CORE_BASE_URL, ingress.*, shell.env.VITE_CORE_URL
```

Les valeurs sont documentées commentaire par commentaire dans `deploy/helm/geostudio/values.yaml`.
`config.*` = mêmes noms et mêmes défauts que le compose (le test échoue sur toute dérive). Écarts
volontaires : `CORE_AUTH_MODE=oidc` (le cœur refuse `mock` hors `CORE_ENV=development`),
`CORE_ADMIN_TOOLS_GATEWAY_URL` vide, `SHELL_BASE_URL` calculé.

## Secrets

Jamais dans `values` : `helm template` échoue sans `secrets.existingSecret`. Clés du Secret = noms des
variables d'environnement ; chaque workload ne reçoit que les siennes (`secretKeyRef`, pas `envFrom`).
Obligatoires : `DATABASE_URL`, `CORE_SECRETS_MASTER_KEY`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` ; `CDC_DATABASE_URL`
(connexion **directe** au primaire) si `cdcWorker.enabled` ; `CORE_EXPORT_TOKEN_SECRET` si l'export est activé.

## Invariants (ADR 0019 inchangé : ceci n'est pas la HA réelle, ARC-32)

- `cdc-worker` : un seul réplica, stratégie `Recreate`, non configurable (slot de réplication logique).
- `core.replicas > 1` : le limiteur de débit reste en mémoire par process (budget effectif `N x budget`) ;
  démarrer les réplicas l'un après l'autre sur une migration lourde (pas de verrou de migration).
- Sondes = healthchecks du compose : `core` startup 180 s puis `/health` ; `worker`, `cdc-worker`,
  `export-worker` en `exec` (mêmes commandes) ; `shell` `GET /`.
- Sécurité : `runAsNonRoot`, uid numériques (core/worker/cdc 1001, shell 101 nginx, export-worker 999),
  `allowPrivilegeEscalation: false`, `drop: [ALL]`, seccomp `RuntimeDefault`. Pas de
  `readOnlyRootFilesystem` (DuckDB/home écrivent dans le conteneur) : durcissement à faire.
  L'uid de `export-worker` (utilisateur système non fixé dans son Dockerfile) est à revérifier à chaque
  changement d'image de base.
- Volumes : `/scratch` du worker = `emptyDir`. Le volume `csp-dynamic-conf` (CSP dynamique lue par
  Traefik, SP-48) et `appexport-runtime` n'existent pas dans le chart : la CSP dynamique et l'export d'app
  autoporté restent propres au compose.

## Ce qui est vérifié, et par quoi

- Local / CI rapide : `helm lint`, `helm template` (défauts et toutes options), `test_helm_chart.py`
  (valeurs rendues vs compose, secrets, non-root, sondes, commandes, images/version, `cdc` mono-writer).
- CI lourd : `helm install --wait` sur kind jetable + `curl /health` (core) et `/` (shell), avec PostGIS et
  MinIO jetables (`deploy/helm/ci/smoke-deps.yaml`), `cdc-worker` désactivé (nécessite publication + slot).
