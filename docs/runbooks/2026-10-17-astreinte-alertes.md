# Runbook — astreinte : que faire quand une alerte sonne (AUD-039)

Chaque règle de `deploy/observability/grafana/provisioning/alerting/rules.yaml`
porte une annotation `runbook_url` qui pointe vers la section de même nom
ci-dessous (`core/tests/test_deployability.py` vérifie que les deux restent
alignés). Commandes écrites pour le compose ; en Helm, remplacer
`docker compose exec <service>` par `kubectl exec deploy/<release>-geostudio-<service>`.

## Recevoir les alertes

Sans `GRAFANA_ALERT_WEBHOOK_URL` dans `.env`, Grafana évalue les règles mais
les livre à `http://127.0.0.1:1/...` : **personne n'est prévenu**. Régler
une URL de webhook (Slack, Mattermost, Teams, ntfy, un relais e-mail…) puis
`docker compose --profile observability up -d otel-lgtm`. Vérifier une fois
la chaîne de bout en bout : passer `isPaused: false` sur
`test-alert-always-firing`, constater la notification, remettre `true`.

Toutes les règles ci-dessous sont en `noDataState: Alerting` sauf les deux
règles de latence : une métrique qui disparaît (service arrêté, export OTLP
coupé) sonne comme une panne, ce qu'elle est.

## slo-api-features-latency-p95

**Sens** : P95 des routes `/v1/collections/{cid}/items*` > 200 ms sur 5 min.

1. Tableau de bord « GeoStudio — Cœur » : la latence monte-t-elle sur une
   seule collection (requête lourde, bbox géante) ou partout ?
2. Partout : `docker compose exec postgis psql -U gis -c "SELECT pid, now()-query_start AS d, state, left(query,120) FROM pg_stat_activity WHERE state <> 'idle' ORDER BY d DESC LIMIT 10"`
   — une requête longue ou un verrou ? `pg_cancel_backend(pid)` si besoin.
3. Vérifier la saturation de pgbouncer (`docker compose logs --tail 100 pgbouncer`)
   et le CPU de `core` (`docker stats`).

## slo-martin-tiles-latency-p95

**Sens** : P95 des tuiles Martin > 50 ms sur 5 min.

1. Tableau de bord « GeoStudio — Martin (tuiles) » : pic de requêtes/s
   (trafic) ou latence seule (base) ? `docker compose logs --tail 200 martin`
   pour repérer la source lente.
2. Index spatial manquant sur la table d'une collection importée :
   `\d+ <table>` dans psql, `CREATE INDEX ... USING gist (geom)` si absent.
3. Postgres saturé : mêmes vérifications que la section précédente.

## slo-jobs-backlog

**Sens** : plus de jobs `todo`+`doing` que le seuil, depuis 5 min. Aucune
donnée = alerte (cœur arrêté ou export OTLP coupé).

1. `docker compose ps worker export-worker` : workers vivants et `healthy` ?
2. `docker compose logs --tail 200 worker` : erreurs de connexion, OOM
   (`docker inspect $(docker compose ps -q worker) --format '{{.State.OOMKilled}}'`) ?
3. Vue d'état d'instance (Administration → Infrastructure) : quelle file
   grossit ? Une file `export` qui grossit avec le profil `export` éteint
   est attendue : allumer le profil ou ne pas proposer l'export.
4. Charge légitime : `docker compose up -d --scale worker=2`.

## slo-api-5xx-rate

**Sens** : plus de 1 % de réponses 5xx sur 5 min. Aucune donnée = alerte.

1. `docker compose logs --since 10m core | grep '"level": "ERROR"'` — chaque
   500 porte un `request_id` (aussi renvoyé au client dans l'en-tête
   `X-Request-ID` et le corps `requestId`) : le rechercher dans Loki
   (`{service_name="geostudio-core"} |= "<id>"`) puis ouvrir la trace.
2. 503 `identity provider unreachable` en série : Keycloak est tombé
   (`docker compose ps keycloak`).
3. Erreurs base (`OperationalError`) : Postgres/pgbouncer, voir ci-dessus.

## ops-cdc-slot-inactive

**Sens** : aucun process ne tient le slot de réplication `geostudio_cdc_slot`
depuis 10 min. Le lac n'est plus alimenté et Postgres conserve tout le WAL
depuis la dernière confirmation.

1. `docker compose ps cdc-worker` puis `docker compose logs --tail 200 cdc-worker`.
2. Redémarrer : `docker compose up -d cdc-worker`. Le worker reprend au
   dernier LSN confirmé, sans perte.
3. En échec répété (message malformé, bucket S3 manquant), corriger la
   cause avant que `ops-cdc-slot-wal` ne sonne à son tour.

## ops-cdc-slot-wal

**Sens** : le slot retient plus de 5 Gio de WAL. Le disque de Postgres se
remplit ; à saturation, **toute la plateforme s'arrête**.

1. Traiter d'abord `ops-cdc-slot-inactive` si elle sonne aussi.
2. Slot actif mais en retard : le worker n'écrit pas assez vite (S3 lent ?
   `docker compose logs cdc-worker`).
3. **Dernier recours**, si le disque va saturer avant la reprise :
   `docker compose stop cdc-worker` puis
   `docker compose exec postgis psql -U gis -c "SELECT pg_drop_replication_slot('geostudio_cdc_slot')"`.
   Le WAL est libéré immédiatement. Le worker recrée le slot au démarrage,
   mais **les changements intervenus entre-temps manquent au lac** : le
   noter et prévoir de recharger les collections concernées.

## ops-jobs-failed

**Sens** : au moins un job a échoué dans les dernières 24 h (jauge
`geostudio_jobs_failed`, par file).

1. Repérer les jobs : `docker compose exec postgis psql -U gis -c "SELECT j.id, j.queue_name, j.task_name, e.at FROM procrastinate_jobs j JOIN procrastinate_events e ON e.job_id = j.id AND e.type = 'failed' WHERE e.at > now() - interval '24 hours' ORDER BY e.at DESC LIMIT 20"`.
2. Logs du worker à l'heure de l'échec (`docker compose logs --since 24h worker`).
3. La plupart des échecs sont aussi visibles par l'utilisateur concerné
   (import, export, pipeline en « échec » dans l'interface) : relancer
   depuis l'interface une fois la cause corrigée. L'alerte se résout seule
   24 h après le dernier échec.

## ops-jobs-oldest-age

**Sens** : un job exigible attend un worker depuis plus de 30 min.

1. La file concernée (label `queue`) a-t-elle un consommateur ? `worker`
   écoute toutes les files sauf `export`, réservée à `export-worker`
   (profil `export`).
2. Worker vivant mais bloqué sur un job long : la sonde
   `scripts.healthcheck_worker_stalled` le signale (`docker compose ps`
   → `unhealthy`) ; `docker compose restart worker`.
