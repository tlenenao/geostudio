# Runbook — déploiement Kubernetes (chart Helm, ARC-29)

Chart : `deploy/helm/geostudio/`. Images : `ghcr.io/tlenenao/geostudio-{core,shell,export-worker}` en
amd64 **et** arm64 (release multi-arch). Garde-fou : `core/tests/test_helm_chart.py` (équivalent de
`test_deployability.py`) + workflow `.github/workflows/helm-chart.yml` (lint, rendu, fumée kind).

## Ce que le chart déploie / ne déploie pas

| Déployé | Externe (à fournir, via `config.*` et le Secret) |
|---|---|
| `core` (migrations : Job hook `pre-install,pre-upgrade` `<release>-migrations`, AUD-033), `worker`, `cdc-worker`, `shell` | Postgres (PostGIS + pgvector, `wal_level=logical`, `max_slot_wal_keep_size` borné — 10GB recommandé, AUD-012), pgbouncer optionnel |
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
  les migrations tournent une fois par release dans le Job hook, avant les nouveaux pods (`helm upgrade
  --no-hooks` les saute : à proscrire). Le Job ne lit que le Secret (`DATABASE_URL`,
  `CORE_MIGRATION_DATABASE_URL`) : il passe avant la création du ConfigMap.
- Sondes = healthchecks du compose : `core` startup 180 s puis `/health` ; `worker`, `cdc-worker`,
  `export-worker` en `exec` (mêmes commandes) ; `shell` `GET /`.
- Sécurité : `runAsNonRoot`, uid numériques (core/worker/cdc 1001, shell 101 nginx, export-worker 999),
  `allowPrivilegeEscalation: false`, `drop: [ALL]`, seccomp `RuntimeDefault`. Pas de
  `readOnlyRootFilesystem` (DuckDB/home écrivent dans le conteneur) : durcissement à faire.
  L'uid de `export-worker` (utilisateur système non fixé dans son Dockerfile) est à revérifier à chaque
  changement d'image de base.
- Volumes : `/scratch` du worker = `emptyDir`. Le volume `csp-dynamic-conf` (CSP dynamique lue par
  Traefik, SP-48) et `appexport-runtime` n'existent pas dans le chart : la CSP dynamique et l'export d'app
  autoporté restent propres au compose (la tâche de CSP dynamique ne fait rien sans ce volume).
- En-têtes de sécurité (AUD-030) : nginx du shell pose HSTS, `X-Frame-Options: DENY` (sauf `/embed/`) et une
  CSP **statique** `shell.csp`, en `Report-Only` tant que `config.CORE_CSP_MODE` n'est pas `enforce`.
  `connect-src` reçoit automatiquement les origines de `ingress.apiHost`, de `shell.env.VITE_CORE_URL` et
  de l'autorité OIDC (`shell.env.VITE_OIDC_AUTHORITY`, sinon `config.CORE_OIDC_ISSUER`) ; avant
  d'enforcer, ajouter les hôtes de fonds de carte (`img-src`). Pas de rate-limit au niveau Ingress
  (dépend du contrôleur) : le limiteur applicatif du cœur reste le seul.
- Schéma des origines : sans `ingress.tlsSecretName`, le chart suppose que l'Ingress sert en **http**
  (CORS `http://<host>`, `connect-src http://<apiHost>`). Si le TLS est terminé ailleurs (load balancer,
  cert-manager hors chart), les origines dérivées sont fausses : fixer `config.CORE_CORS_ALLOWED_ORIGINS`
  à `https://<host>` (et compléter `shell.csp` en conséquence).
- Job de migration (`helm.sh/hook-delete-policy: before-hook-creation`) : le Job réussi reste dans le
  namespace jusqu'à la montée de version suivante, qui le remplace ; `kubectl delete job
  <release>-geostudio-migrations` est sans risque après succès. `helm uninstall` ne le supprime pas.
- **Retour arrière** : `helm rollback` ne rejoue aucun hook et n'exécute **aucun** `alembic downgrade` ; le
  schéma reste celui de la version la plus récente. Revenir à une image antérieure n'est sûr que si le
  CHANGELOG ne signale pas de migration incompatible ; sinon restaurer la sauvegarde prise avant la
  montée (même consigne que le runbook compose `2026-10-17-montee-de-version.md`).
- `otel-lgtm` : `observability.existingClaim` pour garder métriques, logs et traces au redémarrage.

## Ce qui est vérifié, et par quoi

- Local / CI rapide : `helm lint`, `helm template` (défauts et toutes options), `test_helm_chart.py`
  (valeurs rendues vs compose, secrets, non-root, sondes, commandes, images/version, `cdc` mono-writer).
- CI lourd : `helm install --wait` sur kind jetable + `curl /health` (core) et `/` (shell), avec PostGIS et
  MinIO jetables (`deploy/helm/ci/smoke-deps.yaml`), `cdc-worker` désactivé (nécessite publication + slot).
