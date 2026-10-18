# Vérification de l'addendum AUD-151 à AUD-192 dans le code (2026-10-18)

Relecture du code de `dev` (64a6e73a) par trois agents, en lecture seule. Aucun test lancé : les verdicts viennent de la lecture du code, pas d'un rejeu. Piège n°12 : à recouper avant de clore un point.

**Décompte (42 constats)** : 12 fermés, 1 fermé avec réserve, 5 partiels, 24 ouverts.

## AUD-151 et AUD-183 à 192

| AUD | Statut | Preuve / reste | Effort |
|---|---|---|---|
| 151 | FERMÉ | regex `tenant/[0-9a-f]{32}/name`, refus de `..`, `key_in_use` 409. Jumelles `ingestion/routes.py:104` et `:211` non revérifiées | – |
| 183 | OUVERT (incertain) | `sql/init.sql` monté en `docker-compose.yml:32` ; confirmer par `docker compose config` que la surcharge prod l'écarte | S |
| 184 | PARTIEL | `mem_limit` sur 7 services ; pas de `cpus`/`pids_limit` ; cdc-worker `${CDC_WORKER_MEM_LIMIT:-0}` | S |
| 185 | FERMÉ | `GET /users/{id}/export`, privilège `compliance.manage` (`bdcde35d`) ; pas de `/users/me/export` | – |
| 186 | OUVERT | `If-Match` toujours optionnel, pas de 428 | S |
| 187 | OUVERT | `COPY scripts` dans `core/Dockerfile:70` et `deploy/export-worker/Dockerfile:29` | S |
| 188 | OUVERT | transaction unique dans `alembic/env.py`, pas de `lock_timeout` | S |
| 189 | OUVERT | FK sans `NOT VALID` (0043, 0070) | S |
| 190 | OUVERT | reconstruction HNSW non concurrente (0071) | S |
| 191 | OUVERT | 0005 échoue sur `configs` non vide ; 0007 idem | S |
| 192 | OUVERT | `_refuse_if_data` seulement dans 0039/0042 | S |

## AUD-152 à 167

| AUD | Statut | Preuve / reste | Effort |
|---|---|---|---|
| 152 | FERMÉ | `cloudfiles.py:867` `sanitize_cell` (`e37d2034`) | – |
| 153 | FERMÉ | middleware `body_limit` 413/411 sur `/v1/public/submit/` (`main.py:475-500`) | – |
| 154 | PARTIEL | IPv6 /64, groupe `public-submit`, limiteur par jeton fermés ; `HourlyLimiter` par process, `CORE_QUOTAS_ENABLED` faux par défaut, ADR 0017 non ajusté | S |
| 155 | PARTIEL | groupe `ogc-read`, sémaphore WMS, timeouts fermés ; pas de cache public court, `count_mode="exact"` pour `hits` | S |
| 156 | PARTIEL | regex `/jobs`, plafond de jobs actifs, purge fermés ; pacer par process, pas de privilège exigé | S |
| 157 | FERMÉ | zonal : fenêtre 16 M px, sémaphore, budget, 503, groupe `zonal` (lecture par fenêtres laissée en `ponytail`) | – |
| 158 | OUVERT | contrôle `Host`/jeton sous `if token is not None` (`sidecar/app.py:67`) ; non exploitable dans le produit Tauri livré | S |
| 159 | OUVERT | `reader.file` sans refus de `/vsi*`/`://` (`runtime.py:613`) ; `allowed_directories` élargi à tout `writer.file` du payload | S-M |
| 160 | OUVERT | `_SIDECAR_SAFE_OPS` ne filtre que `get_ops` | S |
| 161 | OUVERT | aperçu desktop sur `demotiles.maplibre.org`, pas de CSP Tauri | S |
| 162 | FERMÉ | `_PreviewBody` accepté (`c031d3ed`) | – |
| 163 | OUVERT | `numberMatched` fuit le total hors RLS (`relations/service.py:~212`) | S |
| 164 | OUVERT | `sensitiveFields` non contrôlé au PATCH, `FilterError` non traduit | S |
| 165 | OUVERT | `check_write` absent de la soumission publique, de l'import et du `writer.collection` | M |
| 166 | OUVERT | pas de `before_update` sur `parent_key` | M |
| 167 | OUVERT | suppression de collection sans contrôle ni audit des relations | S |

## AUD-168 à 182

| AUD | Statut | Preuve / reste | Effort |
|---|---|---|---|
| 168 | FERMÉ | `try/except` + rollback par événement (`a8350992`) | – |
| 169 | FERMÉ | `allow_redirects=False`, 3xx = erreur | – |
| 170 | FERMÉ | `MAX_EVENT_AGE`, 4xx propres à l'événement, purge des `pending` | – |
| 171 | OUVERT | curseur `/changes` sur `created_at` posé à l'écriture, sans fenêtre de recouvrement | M |
| 172 | FERMÉ avec réserve | `public_error` partout sauf `tileset3d/jobs.py:156`, `reports/jobs.py:282`/`:433` ; ingestion non relue | S |
| 173 | FERMÉ | manifeste d'exemple en `widgets.example.com`, test de validation | – |
| 174 | OUVERT (cause changée) | job `desktop-etl WebDriver E2E` rouge : sélecteur `reader.file` introuvable (`golden-path.spec.js:168`) | S/M |
| 175 | FERMÉ | `--collect-data morecantile` (`0a6a747c`), freeze vert sur main | – |
| 176 | PARTIEL | CI : 51 échecs sur 100 runs ; push + PR doublent les runs | S |
| 177 | OUVERT | cosign : le run Publish edge du 18/10 échoue à la signature, jamais réussie en réel (cause non lue) | M |
| 178 | OUVERT | aucune base de Dockerfile épinglée par digest | M |
| 179 | OUVERT | minio/titiler/postgis sans `USER` | M |
| 180 | FERMÉ | `uv==0.11.21` + `uv export --frozen` ; `core/Dockerfile:16` non relu | – |
| 181 | OUVERT | `pip install` sans version dans `appexport-standalone`, pas de HEALTHCHECK | S |
| 182 | OUVERT | MinIO cloné par tag sans `MINIO_COMMIT` vérifié | S |

## Mineurs non votés

Ouverts : audit de routage avant limiteur ; `parse_bbox_floats` miny>maxy ; `mark_all_read` charge toutes les lignes, sans rétention ; `GET /v1/instance` public ; `jobs.stalled` fondé sur les événements ; suppression d'icône réservée au créateur ; `martin-config.yaml` et `no_log` Ansible ; migration 0070 avec trou 0069. Fermé : erreur du job qualité. Incertain : `writer.file` CSV (derrière flag éteint). Non revérifiés : budget lineage/xlsform, focus `widget.js`, chaînes françaises `AppErrorBoundary`/`LazyWcHost`, `.expect()` du sidecar, horodatage de signature des webhooks.

## Jumelles à lister avant toute clôture (piège n°14)

`ingestion/routes.py:104/:211` ; `readers2.py:112-133` et `wfs.py` (chemins `/vsi*`) ; chaînes d'erreur brutes des jobs ingestion/rapports/tileset ; `.defer()` nus dans `raster/routes.py:78` et `dataexport/routes.py:30`.
