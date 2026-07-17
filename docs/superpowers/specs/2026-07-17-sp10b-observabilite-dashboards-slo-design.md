# SP-10b — Observabilité packagée : profil compose, dashboards, SLO/alertes

Date : 2026-07-17
Statut : validé (brainstorm), en attente de plan

## Contexte

SP-10 (« Observabilité & SLO », cf.
`docs/vision/2026-07-04-feuille-de-route-geostudio.md` §SP-10, arbitrage A26)
équipe la plateforme pour s'exploiter au moment où la démo publique (SP-9,
clos) reçoit du trafic réel. **SP-10a** (spec+plan écrits le 2026-07-16, pas
encore exécutés) couvre l'instrumentation elle-même — SDK OTel dans
`core`/`worker`, spans auto+manuels, logs corrélés `trace_id`/`span_id`, 3
compteurs métier (`geostudio.items.created`, `geostudio.configs.published`,
`geostudio.apps.runtime_executions`) — sans exportateur attaché par défaut
(`OTEL_EXPORTER_OTLP_ENDPOINT` absent = zéro appel réseau, zéro changement de
comportement, y compris dans toute la suite de tests).

**SP-10b** couvre l'autre moitié, explicitement différée par SP-10a : rendre
ces signaux *exploitables*. Le profil compose `--profile observability`
(conteneur unique `grafana/otel-lgtm`, arbitrage A26), les dashboards
packagés, les 4 SLO/alertes de la feuille de route, et le critère
d'acceptation « une alerte de test se déclenche ». SP-10b **dépend de SP-10a**
(il a besoin de spans/métriques réels à visualiser) — son exécution doit donc
suivre celle de SP-10a, même si les deux specs sont écrites indépendamment.

Aujourd'hui, `docker-compose.yml` ne définit aucun service d'observabilité,
`martin` n'est scrapé par personne malgré son endpoint Prometheus natif, et
Postgres n'a aucun exporter de métriques.

## Objectif de SP-10b

Un opérateur qui lance `docker compose --profile observability up` (un seul
flag, aucune édition manuelle de `.env` requise) voit dans Grafana (`:3000`) 4
dashboards alimentés en données réelles, les 4 SLO de la feuille de route
visibles dans l'Alerting Grafana, et peut observer une alerte se déclencher de
façon reproductible — sans que cela ne change quoi que ce soit au comportement
d'un `docker compose up` classique (sans le profil), hormis un compromis
assumé et vérifié (cf. §Risques et §Compose).

Hors périmètre (cf. feuille de route + SP-10a) : télémétrie OTel navigateur,
SLO de fraîcheur CDC (SP-11), notification externe des alertes (Slack/email/
webhook) — la preuve d'acceptation se limite à l'état « firing » visible dans
Grafana.

## Architecture

### Compose : nouveaux services, profil `observability`

Nouveau bloc dans `docker-compose.yml`, chaque service portant
`profiles: ["observability"]` (absent du profil par défaut — `docker compose
up` sans flag ne les démarre jamais) :

- **`otel-lgtm`** — image `grafana/otel-lgtm` (tag épinglé, pas `:latest` —
  cf. Risques), ports `3000` (UI Grafana), `4317`/`4318` (OTLP grpc/http,
  déjà la cible de `core`/`worker` posée par SP-10a). Trois montages :
  - `deploy/observability/otelcol-config.yaml` →
    `/otel-lgtm/otelcol-config.yaml` (étend la config par défaut du
    collector embarqué, cf. section suivante — ce montage **remplace**
    entièrement la config par défaut de l'image, il ne la fusionne pas).
  - `deploy/observability/grafana/provisioning/dashboards/` →
    `/otel-lgtm/grafana/conf/provisioning/dashboards/custom/` (les 4
    dashboards packagés + un provider YAML `type: file`).
  - `deploy/observability/grafana/provisioning/alerting/` →
    `/otel-lgtm/grafana/conf/provisioning/alerting/` (les règles SLO, cf.
    §Alerting).
- **`postgres-exporter`** — image `prometheuscommunity/postgres-exporter`,
  `DATA_SOURCE_NAME` pointant sur `postgresql://gis:${PG_PASSWORD}@pgbouncer:
  6432/gis` (réutilise le secret existant, aucun nouveau credential).
  Expose `:9187/metrics`.

`core`/`worker` gagnent, **sans condition de profil** (décision assumée, cf.
§Risques) :
```
OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-lgtm:4318
OTEL_SERVICE_NAME: geostudio-core   # geostudio-worker pour le service worker
```
Compose ne permet pas de conditionner une variable d'environnement d'un
service non-profilé à l'activation d'un profil sur un autre service — le
choix retenu est de pointer l'endpoint en dur, et de vérifier empiriquement
(première tâche du plan) que l'échec de connexion du `BatchSpanProcessor`/
`PeriodicExportingMetricReader` quand `otel-lgtm` n'est pas démarré reste
silencieux/non bloquant (retry en arrière-plan, pas de crash, pas d'erreur
utilisateur visible) avant de considérer ce choix comme définitivement
acquis. C'est ce qui permet à `docker compose --profile observability up` de
tenir sa promesse « sans configuration » : un seul flag suffit, l'export
OTLP est déjà câblé des deux côtés.

### Collecteur OTel : scraping Prometheus de Martin et Postgres

Le fichier monté `otelcol-config.yaml` **remplace** la config par défaut du
collecteur embarqué dans `grafana/otel-lgtm` (confirmé : pas de mécanisme de
fusion partielle documenté par l'image). `deploy/observability/otelcol-
config.yaml` part donc de la config par défaut de l'image (à extraire et
committer telle quelle au début du plan, pas reconstruite de mémoire) et lui
ajoute un receiver Prometheus :

```yaml
receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: martin
          scrape_interval: 15s
          metrics_path: /_/metrics
          static_configs: [{targets: ["martin:3000"]}]
        - job_name: postgres
          scrape_interval: 15s
          static_configs: [{targets: ["postgres-exporter:9187"]}]
```
câblé dans le pipeline `metrics` existant, à côté du receiver `otlp` déjà
présent par défaut (pas à sa place).

### Métrique de backlog de jobs

Aucune métrique de backlog n'existe aujourd'hui (SP-10a n'a posé que des
spans par job exécuté, pas un compteur de jobs en attente). Nouvel
`ObservableGauge` OTel dans `core/app/observability.py`,
`geostudio.jobs.backlog` (attribut `queue`), dont le callback exécute :
```sql
SELECT queue, COUNT(*) FROM procrastinate_jobs
WHERE status IN ('todo', 'doing') GROUP BY queue
```
contre le même engine SQLAlchemy que `create_app()` construit déjà. Les
callbacks de gauge observable OTel sont appelés paresseusement à chaque tick
d'export (le `PeriodicExportingMetricReader` déjà posé par SP-10a) — aucune
nouvelle boucle de polling, aucun nouveau thread ; coût d'une requête indexée
bon marché par tick.

### Dashboards packagés (4)

Fichiers JSON statiques dans `deploy/observability/grafana/provisioning/
dashboards/`, interrogeant Mimir (compatible Prometheus) en PromQL :

1. **Cœur** — latence P95 (`http_server_duration_milliseconds`, histogram
   émis par `FastAPIInstrumentor`, `histogram_quantile`), taux de 5xx,
   requêtes/s, par `http_route`.
2. **Martin** — latence P95 des tuiles, requêtes/s, taux de cache hit — noms
   de métriques exacts à relever contre un vrai scrape de `/_/metrics` en
   tâche de plan (pas devinés ici).
3. **Jobs** — `geostudio.jobs.backlog` par file, durée des jobs (dérivée des
   spans `procrastinate.job.*` de SP-10a — mécanisme exact, span-metrics
   Tempo ou équivalent, à confirmer en tâche de plan), nombre d'échecs
   (spans en statut `ERROR`).
4. **Postgres** — connexions, taux de cache hit, taille de base — métriques
   standard de `postgres-exporter`, aucune requête custom.

Les datasources (Mimir/Loki/Tempo) sont déjà auto-provisionnées par l'image
`grafana/otel-lgtm` — rien à ajouter à ce niveau, seuls les dashboards et les
règles d'alerte sont packagés par ce chantier.

### SLO et alertes (5 règles)

Provisioning Grafana Alerting (`deploy/observability/grafana/provisioning/
alerting/rules.yaml`), un dossier `SLO`, 5 règles :

1. Latence API Features P95 < 200 ms — requête filtrée sur les `http_route`
   correspondant aux chemins OGC API Features (`/collections/*/items*`),
   pas l'ensemble des routes du cœur.
2. Latence tuiles Martin P95 < 50 ms.
3. Backlog de jobs sous seuil (`geostudio.jobs.backlog`, seuil provisoire —
   pas de trafic réel pour le calibrer, ajustable plus tard).
4. Taux de 5xx < 1 %.
5. **Règle de test** (dossier séparé, ex. `SLO/test-alert-do-not-keep-in-
   prod`) — seuil délibérément trivial (ex. latence > 1 ms, ou `up{job=
   "martin"} < 2`) qui se déclenche en quelques secondes après le démarrage
   de la stack. Preuve reproductible que le pipeline d'alerting fonctionne
   bout en bout, sans attendre ni simuler une vraie dégradation. Documentée
   comme étape de vérification manuelle, pas un fixture permanent —
   `enabled: false` par défaut ou équivalent, activée pour la démo puis
   désactivée (décision précise laissée au plan).

Aucun contact point/canal de notification (Slack, email, webhook) —
l'acceptation se limite à l'état « firing » visible dans l'UI/API Grafana
Alerting. Cohérent avec le cadrage de la feuille de route (« une référence
d'exploitation packagée », pas une chaîne d'astreinte complète) ; une
intégration de notification réelle est un prolongement naturel mais hors
périmètre de SP-10b.

## Tests

- Empirique (pas un test automatisé) : `docker compose up` sans le profil —
  confirmer que `core`/`worker` démarrent et servent normalement malgré
  `OTEL_EXPORTER_OTLP_ENDPOINT` pointant vers un `otel-lgtm` non démarré
  (pas de crash, logs d'avertissement bornés/périodiques tolérés).
- Empirique : `docker compose --profile observability up` — les 4
  dashboards affichent des données réelles après un peu de trafic généré
  (script ou navigation manuelle), en moins d'une minute.
- Empirique : une requête lente (à provoquer manuellement, ex. une requête
  Features sur un gros jeu de données) est traçable shell → cœur → SQL dans
  Tempo (Explore Grafana).
- Empirique : les 4 règles SLO sont visibles dans Grafana Alerting ; la
  règle de test se déclenche (état « firing ») peu après le démarrage.
- Automatisé (core) : le callback du gauge `geostudio.jobs.backlog` retourne
  les bons comptages par file contre une base de test avec des jobs dans
  différents statuts (`todo`/`doing`/`succeeded`/`failed`), sans dépendre
  d'un vrai collecteur OTLP (lecture directe du gauge via un
  `InMemoryMetricReader`, même patron que les tests OTel de SP-10a).

## Risques

- La config par défaut du collecteur embarqué dans `grafana/otel-lgtm` n'est
  pas un contrat versionné documenté — le tag d'image est épinglé (pas
  `:latest`) pour éviter toute dérive silencieuse ; une future montée de
  version manuelle de ce tag doit re-differ la config par défaut avant de
  fusionner à nouveau notre receiver Prometheus dedans.
- Les noms exacts des métriques exposées par `/_/metrics` de Martin ne sont
  confirmés que sur le chemin (pas le contenu) — le dashboard Martin est
  finalisé contre un scrape réel en tâche de plan, pas écrit à l'aveugle ici.
- Le seuil de backlog de jobs est provisoire, sans trafic réel pour le
  calibrer — documenté comme valeur par défaut raisonnable, ajustable.
- La règle d'alerte de test reste un fichier permanent du dépôt sauf
  décision explicite de la désactiver par défaut — signalé pour que le plan
  tranche (`enabled: false`, ou toggle documenté pour la démo).
- `OTEL_EXPORTER_OTLP_ENDPOINT` pointé en dur sur `core`/`worker` introduit un
  bruit de log de fond (connexions refusées périodiques) sur tout
  déploiement qui n'active jamais le profil `observability` — compromis
  assumé plutôt qu'une activation en deux étapes (flag + édition `.env`),
  cf. §Compose.

## Critères d'acceptation

1. `docker compose --profile observability up` (un seul flag) → les 4
   dashboards Grafana sont alimentés en données réelles sans configuration
   manuelle supplémentaire.
2. Une requête lente est traçable de bout en bout shell → cœur → SQL dans
   Tempo.
3. Les 4 SLO de la feuille de route sont visibles dans Grafana Alerting.
4. Une alerte de test se déclenche de façon observable et reproductible peu
   après le démarrage de la stack.
5. Sans le profil `observability` : `docker compose up` reste pleinement
   fonctionnel — aucun crash, aucune régression de comportement, seul un
   bruit de log de fond toléré et documenté (cf. Risques).
