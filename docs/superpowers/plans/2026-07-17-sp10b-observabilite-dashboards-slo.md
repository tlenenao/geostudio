# SP-10b — Observabilité packagée : profil compose, dashboards, SLO/alertes — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un opérateur qui lance `docker compose --profile observability up` voit dans Grafana 4 dashboards alimentés en données réelles (cœur, Martin, jobs, Postgres), les 4 SLO de la feuille de route visibles dans l'Alerting Grafana, et peut déclencher une alerte de test de façon reproductible — sans rien changer au comportement d'un `docker compose up` classique.

**Architecture:** Un service `otel-lgtm` (image `grafana/otel-lgtm`, Prometheus+Loki+Tempo+Grafana packagés) et un service `postgres-exporter`, tous deux sous `profiles: ["observability"]`. Le collecteur OTel embarqué scrape en plus Martin (`/_/metrics`) et `postgres-exporter` via un receiver Prometheus ajouté à sa config par défaut. `core`/`worker` pointent leur export OTLP vers `otel-lgtm:4318` sans condition de profil (déjà instrumentés par SP-10a) — un `docker compose up` sans le profil laisse cet export échouer silencieusement en arrière-plan. 4 dashboards et 5 règles d'alerte Grafana sont provisionnés par fichiers montés. Un nouvel `ObservableGauge` (`geostudio.jobs.backlog`) complète l'instrumentation SP-10a côté cœur.

**Tech Stack:** `grafana/otel-lgtm` (Prometheus/Loki/Tempo/Grafana), `prometheuscommunity/postgres-exporter`, OpenTelemetry Python SDK (déjà en place depuis SP-10a), Grafana provisioning YAML/JSON.

## Global Constraints

- Aucun service `profiles: ["observability"]` ne doit démarrer avec un `docker compose up` sans flag — vérifié à la fin (Task 6).
- `docker compose --profile observability up` doit rester un seul flag, sans édition manuelle de `.env` (arbitrage A26 / objectif SP-10b).
- Pas de notification externe (Slack/email/webhook) — l'acceptation se limite à l'état « firing » visible dans Grafana Alerting.
- Toute image nouvellement introduite est épinglée par tag exact, jamais `:latest`.
- Docs et commentaires de code en français (code/identifiants en anglais), conventions déjà en place dans `core/app/observability.py`.
- Commits conventionnels (`feat(deploy): …`, `feat(core): …`), un sujet par commit.

## Corrections apportées à la spec pendant l'écriture du plan

Ces points ont été vérifiés empiriquement (conteneurs jetables, pas de supposition) et **divergent du texte de la spec** `docs/superpowers/specs/2026-07-17-sp10b-observabilite-dashboards-slo-design.md` — à connaître avant d'exécuter, car un implémenteur qui suivrait la spec au pied de la lettre sur ces points précis obtiendrait un dashboard vide ou un service qui ne démarre pas :

1. **Martin `v0.13.0` (version actuellement épinglée dans `docker-compose.yml`) n'expose aucun endpoint `/_/metrics`** — testé directement, 404. Les métriques Prometheus de Martin n'existent que depuis `v0.18.0` (confirmé via les release notes GitHub officielles). Task 1 bascule l'image sur `ghcr.io/maplibre/martin:v0.18.0` — testé : `martin-config.yaml` (format actuel) reste compatible tel quel avec cette version.
2. **Martin n'expose que 2 métriques**, pas de taux de cache hit : `martin_http_requests_total{endpoint,method,status}` et `martin_http_requests_duration_seconds_{bucket,sum,count}{endpoint,method,status,le}` (confirmé par scrape réel). Le panneau « taux de cache hit » du dashboard Martin de la spec est irréalisable — remplacé par un panneau « requêtes/s par statut ».
3. **Le datasource Prometheus embarqué dans `grafana/otel-lgtm` s'appelle `Prometheus` (uid `prometheus`), pas Mimir** — la spec parle de « Mimir (compatible Prometheus) » par erreur ; l'image utilise un vrai Prometheus (confirmé via son fichier de provisioning de datasources). Les dashboards packagés référencent `uid: prometheus`.
4. **Le montage de répertoire pour les dashboards ne peut PAS être un unique montage sur `.../dashboards/custom/`** comme le suggère la spec : Grafana ne charge les fichiers de config de provider (`type: file`) que s'ils sont directement sous `.../provisioning/dashboards/`, pas dans un sous-répertoire — vérifié par un test A/B direct (un provider monté dans un sous-dossier n'apparaît jamais dans `/api/search`, le même provider monté au niveau attendu fonctionne immédiatement). Task 4 utilise donc **deux montages distincts** : un fichier provider au niveau racine de `provisioning/dashboards/`, et un répertoire séparé (`custom/`) pour le contenu JSON, référencé par le `path:` du provider.
5. **Port `3000` déjà pris par `martin`** (`docker-compose.yml` actuel publie déjà `"3000:3000"` en dehors de tout profil) — comme les services par défaut tournent toujours, même avec `--profile observability`, publier aussi Grafana sur le port hôte 3000 provoquerait un conflit de bind au démarrage. Grafana est republié sur le port hôte **3001** (le port interne du conteneur reste 3000, changement uniquement côté hôte).
6. **Un `ObservableGauge` avec `unit="1"` se traduit en Prometheus avec un suffixe `_ratio`** (`geostudio_jobs_backlog_ratio` au lieu de `geostudio_jobs_backlog`) — comportement de la convention de nommage OTel→Prometheus (unité UCUM `"1"` interprétée comme un ratio sur les instruments de type gauge), vérifié en faisant réellement transiter la métrique par un collecteur réel. `register_jobs_backlog_gauge` (Task 3) utilise `unit=""` pour obtenir le nom `geostudio_jobs_backlog` tel qu'annoncé par la spec.
7. **La colonne `procrastinate_jobs` pour la file est `queue_name`**, pas `queue` comme l'écrit la requête SQL donnée en exemple par la spec (vérifié contre le schéma réel de la bibliothèque `procrastinate` installée).
8. **`SchemaManager.apply_schema()` de `procrastinate` n'est pas idempotent** (`CREATE TYPE` échoue au second appel sur la même base) — vérifié en le rejouant deux fois. La fixture de test (Task 3) le garde par une vérification `has_table(...)`.

---

### Task 1: Compose — services `otel-lgtm`/`postgres-exporter`, bascule Martin, câblage OTLP inconditionnel

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: services `otel-lgtm` (ports hôte `3001` Grafana, `4317`/`4318` OTLP ; réseau interne `gis-net`, résolu par les autres services via le nom `otel-lgtm`) et `postgres-exporter` (port `9187`, réseau interne), tous deux `profiles: ["observability"]`. `core`/`worker` gagnent `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_SERVICE_NAME`, consommés sans changement de code par `core/app/observability.py` (déjà lu via `os.environ`, SP-10a).

- [ ] **Step 1: Vérifier empiriquement l'innocuité d'un endpoint OTLP inaccessible**

Depuis `core/`, lancer le serveur avec un endpoint OTLP qui ne répond jamais et vérifier que `/health` reste rapide (pas de blocage, pas de crash) :

```bash
cd core
timeout 15 env OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:1 OTEL_SERVICE_NAME=geostudio-core-probe \
  .venv/bin/uvicorn app.main:app --port 18211 --host 127.0.0.1 &
sleep 3
curl -s -o /dev/null -w "health: %{http_code} in %{time_total}s\n" http://127.0.0.1:18211/health
kill %1 2>/dev/null; wait 2>/dev/null
```

Expected: `health: 200 in` un temps de l'ordre de quelques dizaines de millisecondes (pas de blocage sur le port injoignable), aucune exception dans les logs uvicorn. Cette vérification confirme que pointer `OTEL_EXPORTER_OTLP_ENDPOINT` en dur sur `core`/`worker` (Step 3 ci-dessous) est sans risque quand `otel-lgtm` n'est pas démarré.

- [ ] **Step 2: Basculer Martin sur une version qui expose `/_/metrics`**

Dans `docker-compose.yml`, service `martin` :

```yaml
  martin:
    image: ghcr.io/maplibre/martin:v0.18.0
```

(seule la ligne `image:` change — `v0.13.0` → `v0.18.0` ; le reste du service, y compris `martin-config.yaml`, est inchangé et reste compatible tel quel avec cette version, vérifié).

- [ ] **Step 3: Câbler l'export OTLP inconditionnel sur `core` et `worker`**

Dans le service `core`, ajouter à `environment:` (après `CORE_READ_ONLY_MODE`) :

```yaml
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-lgtm:4318
      OTEL_SERVICE_NAME: geostudio-core
```

Dans le service `worker`, ajouter à `environment:` (après `CORE_BASE_URL`) :

```yaml
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-lgtm:4318
      OTEL_SERVICE_NAME: geostudio-worker
```

- [ ] **Step 4: Ajouter les services `otel-lgtm` et `postgres-exporter`**

Nouveau bloc dans `docker-compose.yml`, entre le service `worker` et la section `# ─── Auth ──────`:

```yaml
  # ─── Observabilité (SP-10b, profil optionnel) ──────────

  # Grafana (:3001 côté hôte — :3000 est déjà pris par martin ci-dessus,
  # le port interne du conteneur reste 3000) + Prometheus/Loki/Tempo
  # embarqués. `otelcol-config.yaml` remplace entièrement la config par
  # défaut du collecteur embarqué (pas de fusion partielle) et lui ajoute
  # le scraping Prometheus de martin/postgres-exporter (cf. Task 2).
  otel-lgtm:
    image: grafana/otel-lgtm:0.11.4
    profiles: ["observability"]
    ports:
      - "3001:3000"
      - "4317:4317"
      - "4318:4318"
    volumes:
      - ./deploy/observability/otelcol-config.yaml:/otel-lgtm/otelcol-config.yaml
      - ./deploy/observability/grafana/provisioning/dashboards/geostudio-dashboards.yaml:/otel-lgtm/grafana/conf/provisioning/dashboards/geostudio-dashboards.yaml
      - ./deploy/observability/grafana/provisioning/dashboards/custom:/otel-lgtm/grafana/conf/provisioning/dashboards/custom
      - ./deploy/observability/grafana/provisioning/alerting:/otel-lgtm/grafana/conf/provisioning/alerting
    networks: [gis-net]

  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:v0.20.1
    profiles: ["observability"]
    environment:
      DATA_SOURCE_NAME: postgresql://gis:${PG_PASSWORD}@pgbouncer:6432/gis?sslmode=disable
    networks: [gis-net]
    depends_on:
      pgbouncer:
        condition: service_started
```

- [ ] **Step 5: Valider la syntaxe compose sans démarrer les services profilés**

Les fichiers montés par `otel-lgtm` (`deploy/observability/...`) n'existent pas encore (Tasks 2/4/5) — ne pas essayer de démarrer le profil maintenant, seulement valider que le YAML est bien formé :

```bash
docker compose config --quiet && echo "compose config OK"
```

Expected: `compose config OK`, aucune erreur de parsing.

- [ ] **Step 6: Vérifier qu'un `docker compose up` par défaut reste inchangé**

```bash
docker compose config --services
```

Expected: la liste ne contient PAS `otel-lgtm` ni `postgres-exporter` (services profilés absents de la résolution par défaut, sans `--profile`).

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(deploy): SP-10b — services otel-lgtm/postgres-exporter (profil observability), Martin v0.18.0"
```

---

### Task 2: Config du collecteur OTel — scraping Prometheus de Martin et Postgres

**Files:**
- Create: `deploy/observability/otelcol-config.yaml`

**Interfaces:**
- Consumes: aucune dépendance de code — fichier de config pur, monté par le service `otel-lgtm` défini en Task 1.
- Produces: pipeline `metrics` du collecteur exposant, via l'exporteur `otlphttp/metrics` déjà présent par défaut, les métriques `martin_http_requests_total`/`martin_http_requests_duration_seconds_*` et `pg_*` (postgres-exporter) au Prometheus embarqué — consommées par les dashboards (Task 4) et les règles d'alerte (Task 5).

- [ ] **Step 1: Écrire la config étendue**

Cette config part de la config par défaut réelle de l'image `grafana/otel-lgtm:0.11.4` (extraite et vérifiée, pas reconstruite de mémoire — confirmée bootable telle quelle avec les deux receivers Prometheus ajoutés, cf. §Corrections point 1 plus haut) :

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
        cors:
          allowed_origins:
            - http://*
  prometheus/collector:
    config:
      scrape_configs:
        - job_name: "opentelemetry-collector"
          scrape_interval: 1s
          static_configs:
            - targets: ["127.0.0.1:8888"]
  # Ajouté par SP-10b : scrape de Martin (/_/metrics, disponible depuis
  # v0.18.0 — cf. Task 1 Step 2) et de postgres-exporter. Nommé
  # `prometheus/geostudio` (pas un `prometheus:` nu) pour rester cohérent
  # avec la convention type/instance déjà utilisée par `prometheus/collector`
  # ci-dessus — les deux sont des instances distinctes du même receiver type.
  prometheus/geostudio:
    config:
      scrape_configs:
        - job_name: martin
          scrape_interval: 15s
          metrics_path: /_/metrics
          static_configs:
            - targets: ["martin:3000"]
        - job_name: postgres
          scrape_interval: 15s
          static_configs:
            - targets: ["postgres-exporter:9187"]

extensions:
  health_check:
    endpoint: 0.0.0.0:13133
    path: "/ready"

processors:
  batch:

exporters:
  otlphttp/metrics:
    endpoint: http://127.0.0.1:9090/api/v1/otlp
    tls:
      insecure: true
  otlphttp/traces:
    endpoint: http://127.0.0.1:4418
    tls:
      insecure: true
  otlphttp/logs:
    endpoint: http://127.0.0.1:3100/otlp
    tls:
      insecure: true
  otlp/profiles:
    endpoint: http://127.0.0.1:4040
    tls:
      insecure: true
  debug/metrics:
    verbosity: detailed
  debug/traces:
    verbosity: detailed
  debug/logs:
    verbosity: detailed

service:
  extensions: [health_check]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/traces]
    metrics:
      # prometheus/geostudio ajouté par SP-10b, à côté de otlp et
      # prometheus/collector déjà présents par défaut.
      receivers: [otlp, prometheus/collector, prometheus/geostudio]
      processors: [batch]
      exporters: [otlphttp/metrics]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/logs]
    profiles:
      receivers: [otlp]
      exporters: [otlp/profiles]
```

- [ ] **Step 2: Vérifier que le collecteur démarre avec cette config**

```bash
docker run -d --rm --name sp10b-otelcol-check -p 13030:3000 \
  -v "$(pwd)/deploy/observability/otelcol-config.yaml:/otel-lgtm/otelcol-config.yaml" \
  grafana/otel-lgtm:0.11.4
sleep 15
docker logs sp10b-otelcol-check 2>&1 | grep -i "otelcol is up and running"
docker rm -f sp10b-otelcol-check
```

Expected: la ligne `Otelcol is up and running. Startup time: N seconds` apparaît, aucune erreur de config (`error`/`panic`) dans les logs.

- [ ] **Step 3: Commit**

```bash
git add deploy/observability/otelcol-config.yaml
git commit -m "feat(deploy): SP-10b — config collecteur OTel, scrape Prometheus de Martin et postgres-exporter"
```

---

### Task 3: Métrique de backlog de jobs (`geostudio.jobs.backlog`)

**Files:**
- Modify: `core/app/observability.py`
- Modify: `core/app/main.py`
- Modify: `core/tests/conftest.py`
- Create: `core/tests/test_observability_jobs_backlog.py`

**Interfaces:**
- Consumes: `metrics.get_meter` (déjà importé dans `observability.py`, SP-10a) ; `pg_engine` (fixture existante, `core/tests/conftest.py`).
- Produces: `observability.register_jobs_backlog_gauge(engine, *, meter=None) -> None`, appelée depuis `create_app()` (`core/app/main.py`) juste après `observability.instrument_engine(engine)`. Fixture `pg_engine_with_procrastinate_schema` (session-scoped, dépend de `pg_engine`), réutilisable par tout futur test nécessitant une vraie table `procrastinate_jobs`.

- [ ] **Step 1: Écrire le test (échoue — `register_jobs_backlog_gauge` n'existe pas encore)**

D'abord, ajouter la fixture partagée dans `core/tests/conftest.py` (après `pg_session_factory`) :

```python
@pytest.fixture(scope="session")
def pg_engine_with_procrastinate_schema(pg_engine):
    """pg_engine, avec le schéma procrastinate (table procrastinate_jobs et
    dépendances) appliqué s'il est absent. apply_schema() n'est PAS
    idempotent — un second appel sur une base où le schéma existe déjà lève
    (CREATE TYPE échoue), vérifié empiriquement — d'où la garde has_table()
    pour rester rejouable d'une session pytest à l'autre sur une base de
    test persistante."""
    import procrastinate
    from sqlalchemy import inspect as sa_inspect

    if not sa_inspect(pg_engine).has_table("procrastinate_jobs"):
        conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace(
            "postgresql+psycopg://", "postgresql://"
        )
        app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=conninfo))
        with app.open():
            app.schema_manager.apply_schema()
    return pg_engine
```

Puis créer `core/tests/test_observability_jobs_backlog.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from sqlalchemy import text

from app import observability

pytestmark = pytest.mark.postgis


def _read_backlog(reader: InMemoryMetricReader) -> dict[str, float]:
    data = reader.get_metrics_data()
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == "geostudio.jobs.backlog":
                    return {dp.attributes["queue"]: dp.value for dp in metric.data.data_points}
    return {}


def test_jobs_backlog_gauge_counts_todo_and_doing_per_queue(pg_engine_with_procrastinate_schema):
    engine = pg_engine_with_procrastinate_schema
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM procrastinate_jobs"))
        conn.execute(text(
            "INSERT INTO procrastinate_jobs (queue_name, task_name, status) VALUES "
            "('ingestion', 't1', 'todo'), ('ingestion', 't2', 'doing'), "
            "('search', 't3', 'todo'), ('ingestion', 't4', 'succeeded'), "
            "('search', 't5', 'failed')"
        ))

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test")

    observability.register_jobs_backlog_gauge(engine, meter=meter)

    assert _read_backlog(reader) == {"ingestion": 2, "search": 1}
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

```bash
cd core
CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:<password>@localhost:<port>/gis \
  uv run pytest tests/test_observability_jobs_backlog.py -v
```

(remplacer `<password>`/`<port>` par une base PostGIS de test réelle — cf. `CONTRIBUTING.md` pour la construire via `deploy/postgis/Dockerfile` si besoin.)

Expected: FAIL avec `AttributeError: module 'app.observability' has no attribute 'register_jobs_backlog_gauge'`.

- [ ] **Step 3: Implémenter `register_jobs_backlog_gauge`**

Dans `core/app/observability.py`, ajouter à la fin du fichier :

```python
def register_jobs_backlog_gauge(engine, *, meter=None) -> None:
    """ObservableGauge geostudio.jobs.backlog, un point de données par file
    (attribut `queue`) — compte les lignes procrastinate_jobs en statut
    todo/doing. Callback appelé paresseusement à chaque tick d'export du
    PeriodicExportingMetricReader (déjà posé par setup(), SP-10a) — aucune
    nouvelle boucle de polling, aucun nouveau thread.

    unit="" et pas "1" : un ObservableGauge avec unit="1" se traduit côté
    Prometheus par un nom suffixé _ratio (convention de nommage OTel→
    Prometheus : l'unité UCUM "1" est interprétée comme un ratio sur les
    gauges) — vérifié empiriquement en faisant transiter la métrique par un
    vrai collecteur. geostudio.jobs.backlog est un compte, pas un ratio ;
    unit="" produit le nom géostudio_jobs_backlog attendu par les dashboards
    et règles d'alerte (Tasks 4/5)."""
    from opentelemetry.metrics import Observation
    from sqlalchemy import text

    meter = meter or metrics.get_meter(__name__)

    def _callback(options):
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT queue_name, COUNT(*) AS n FROM procrastinate_jobs "
                "WHERE status IN ('todo', 'doing') GROUP BY queue_name"
            ))
            return [Observation(count, {"queue": queue_name}) for queue_name, count in rows]

    meter.create_observable_gauge(
        "geostudio.jobs.backlog",
        callbacks=[_callback],
        unit="",
        description="Jobs procrastinate en attente ou en cours, par file",
    )
```

- [ ] **Step 4: Câbler l'appel dans `create_app()`**

Dans `core/app/main.py`, juste après la ligne `observability.instrument_engine(engine)` :

```python
    engine = make_engine(database_url)
    observability.instrument_engine(engine)
    observability.register_jobs_backlog_gauge(engine)
    init_db(engine)
```

- [ ] **Step 5: Lancer le test et vérifier qu'il passe**

```bash
cd core
CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:<password>@localhost:<port>/gis \
  uv run pytest tests/test_observability_jobs_backlog.py -v
```

Expected: PASS.

- [ ] **Step 6: Lancer toute la suite (sans DB Postgres, régression rapide)**

```bash
cd core
uv run pytest
```

Expected: aucune régression (le nouveau test est skippé, `CORE_TEST_DATABASE_URL` absent en local par défaut — comportement identique aux autres tests `postgis` existants).

- [ ] **Step 7: Commit**

```bash
git add core/app/observability.py core/app/main.py core/tests/conftest.py core/tests/test_observability_jobs_backlog.py
git commit -m "feat(core): SP-10b — ObservableGauge geostudio.jobs.backlog"
```

---

### Task 4: Dashboards Grafana packagés (4)

**Files:**
- Create: `deploy/observability/grafana/provisioning/dashboards/geostudio-dashboards.yaml`
- Create: `deploy/observability/grafana/provisioning/dashboards/custom/core.json`
- Create: `deploy/observability/grafana/provisioning/dashboards/custom/martin.json`
- Create: `deploy/observability/grafana/provisioning/dashboards/custom/jobs.json`
- Create: `deploy/observability/grafana/provisioning/dashboards/custom/postgres.json`

**Interfaces:**
- Consumes: métriques `http_server_duration_milliseconds{http_route,http_status_code}` (FastAPIInstrumentor, SP-10a), `martin_http_requests_total`/`martin_http_requests_duration_seconds_*` (Task 2), `geostudio_jobs_backlog{queue}` (Task 3), `pg_stat_database_*`/`pg_database_size_bytes` (postgres-exporter, Task 1), datasource Prometheus `uid: prometheus` et Tempo `uid: tempo` (auto-provisionnés par l'image `grafana/otel-lgtm`, confirmé — rien à ajouter à ce niveau).

- [ ] **Step 1: Provider de dashboards**

`deploy/observability/grafana/provisioning/dashboards/geostudio-dashboards.yaml` — **ce fichier doit rester au niveau racine de `provisioning/dashboards/` dans le conteneur** (monté directement, pas via le sous-répertoire `custom/`), sans quoi Grafana ne le charge jamais (cf. §Corrections point 4) :

```yaml
apiVersion: 1
providers:
  - name: "GeoStudio"
    type: file
    updateIntervalSeconds: 30
    options:
      path: /otel-lgtm/grafana/conf/provisioning/dashboards/custom
      foldersFromFilesStructure: false
```

- [ ] **Step 2: Dashboard Cœur**

`deploy/observability/grafana/provisioning/dashboards/custom/core.json` :

```json
{
  "title": "GeoStudio — Cœur",
  "uid": "geostudio-core",
  "schemaVersion": 39,
  "version": 1,
  "editable": true,
  "tags": ["geostudio", "sp10b"],
  "time": {"from": "now-1h", "to": "now"},
  "panels": [
    {
      "id": 1,
      "title": "Latence P95 par route (ms)",
      "type": "timeseries",
      "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "prometheus", "uid": "prometheus"},
          "expr": "histogram_quantile(0.95, sum(rate(http_server_duration_milliseconds_bucket[5m])) by (le, http_route))",
          "legendFormat": "{{http_route}}"
        }
      ]
    },
    {
      "id": 2,
      "title": "Taux de 5xx",
      "type": "timeseries",
      "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "prometheus", "uid": "prometheus"},
          "expr": "sum(rate(http_server_duration_milliseconds_count{http_status_code=~\"5..\"}[5m])) / sum(rate(http_server_duration_milliseconds_count[5m]))",
          "legendFormat": "taux 5xx"
        }
      ]
    },
    {
      "id": 3,
      "title": "Requêtes/s par route",
      "type": "timeseries",
      "gridPos": {"x": 0, "y": 8, "w": 24, "h": 8},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "prometheus", "uid": "prometheus"},
          "expr": "sum(rate(http_server_duration_milliseconds_count[5m])) by (http_route)",
          "legendFormat": "{{http_route}}"
        }
      ]
    }
  ]
}
```

- [ ] **Step 3: Dashboard Martin**

`deploy/observability/grafana/provisioning/dashboards/custom/martin.json` — **3 panneaux, pas 4** : pas de panneau « cache hit », cette métrique n'existe pas côté Martin (cf. §Corrections point 2) :

```json
{
  "title": "GeoStudio — Martin (tuiles)",
  "uid": "geostudio-martin",
  "schemaVersion": 39,
  "version": 1,
  "editable": true,
  "tags": ["geostudio", "sp10b"],
  "time": {"from": "now-1h", "to": "now"},
  "panels": [
    {
      "id": 1,
      "title": "Latence P95 tuiles (s)",
      "type": "timeseries",
      "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "prometheus", "uid": "prometheus"},
          "expr": "histogram_quantile(0.95, sum(rate(martin_http_requests_duration_seconds_bucket{endpoint=\"/{source_ids}/{z}/{x}/{y}\"}[5m])) by (le))",
          "legendFormat": "P95"
        }
      ]
    },
    {
      "id": 2,
      "title": "Requêtes/s par statut",
      "type": "timeseries",
      "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "prometheus", "uid": "prometheus"},
          "expr": "sum(rate(martin_http_requests_total[5m])) by (status)",
          "legendFormat": "{{status}}"
        }
      ]
    },
    {
      "id": 3,
      "title": "Erreurs 5xx/s",
      "type": "timeseries",
      "gridPos": {"x": 0, "y": 8, "w": 24, "h": 8},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "prometheus", "uid": "prometheus"},
          "expr": "sum(rate(martin_http_requests_total{status=~\"5..\"}[5m]))",
          "legendFormat": "5xx/s"
        }
      ]
    }
  ]
}
```

- [ ] **Step 4: Dashboard Jobs**

`deploy/observability/grafana/provisioning/dashboards/custom/jobs.json` — le panneau de backlog interroge Prometheus (fiable, testé) ; les deux panneaux de durée/échecs de jobs interrogent Tempo par TraceQL sur les spans `procrastinate.job.*` de SP-10a (mécanisme confirmé fonctionnel côté traçage — cf. Task 6 Step 3 — mais la syntaxe exacte du panneau `type: "traces"` n'a pas été éprouvée en dashboard provisionné dans ce plan ; si son rendu est incorrect une fois la stack levée, l'ajuster depuis l'éditeur Grafana en Explore→Tempo puis « Export panel » plutôt que deviner à nouveau) :

```json
{
  "title": "GeoStudio — Jobs",
  "uid": "geostudio-jobs",
  "schemaVersion": 39,
  "version": 1,
  "editable": true,
  "tags": ["geostudio", "sp10b"],
  "time": {"from": "now-1h", "to": "now"},
  "panels": [
    {
      "id": 1,
      "title": "Backlog par file",
      "type": "timeseries",
      "gridPos": {"x": 0, "y": 0, "w": 24, "h": 8},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "prometheus", "uid": "prometheus"},
          "expr": "geostudio_jobs_backlog",
          "legendFormat": "{{queue}}"
        }
      ]
    },
    {
      "id": 2,
      "title": "Durée des jobs (traces)",
      "type": "traces",
      "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8},
      "datasource": {"type": "tempo", "uid": "tempo"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "tempo", "uid": "tempo"},
          "queryType": "traceqlSearch",
          "query": "{name=~\"procrastinate\\\\.job\\\\..*\"}"
        }
      ]
    },
    {
      "id": 3,
      "title": "Échecs de jobs (spans ERROR)",
      "type": "traces",
      "gridPos": {"x": 12, "y": 8, "w": 12, "h": 8},
      "datasource": {"type": "tempo", "uid": "tempo"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "tempo", "uid": "tempo"},
          "queryType": "traceqlSearch",
          "query": "{name=~\"procrastinate\\\\.job\\\\..*\" && status=error}"
        }
      ]
    }
  ]
}
```

- [ ] **Step 5: Dashboard Postgres**

`deploy/observability/grafana/provisioning/dashboards/custom/postgres.json` :

```json
{
  "title": "GeoStudio — Postgres",
  "uid": "geostudio-postgres",
  "schemaVersion": 39,
  "version": 1,
  "editable": true,
  "tags": ["geostudio", "sp10b"],
  "time": {"from": "now-1h", "to": "now"},
  "panels": [
    {
      "id": 1,
      "title": "Connexions actives (gis)",
      "type": "timeseries",
      "gridPos": {"x": 0, "y": 0, "w": 8, "h": 8},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "prometheus", "uid": "prometheus"},
          "expr": "pg_stat_database_numbackends{datname=\"gis\"}",
          "legendFormat": "connexions"
        }
      ]
    },
    {
      "id": 2,
      "title": "Taux de cache hit",
      "type": "timeseries",
      "gridPos": {"x": 8, "y": 0, "w": 8, "h": 8},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "prometheus", "uid": "prometheus"},
          "expr": "sum(rate(pg_stat_database_blks_hit{datname=\"gis\"}[5m])) / (sum(rate(pg_stat_database_blks_hit{datname=\"gis\"}[5m])) + sum(rate(pg_stat_database_blks_read{datname=\"gis\"}[5m])))",
          "legendFormat": "cache hit"
        }
      ]
    },
    {
      "id": 3,
      "title": "Taille de la base (gis, bytes)",
      "type": "timeseries",
      "gridPos": {"x": 16, "y": 0, "w": 8, "h": 8},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {
          "refId": "A",
          "datasource": {"type": "prometheus", "uid": "prometheus"},
          "expr": "pg_database_size_bytes{datname=\"gis\"}",
          "legendFormat": "taille"
        }
      ]
    }
  ]
}
```

- [ ] **Step 6: Vérifier empiriquement que les 4 dashboards sont chargés**

```bash
docker run -d --rm --name sp10b-dash-check -p 13040:3000 \
  -v "$(pwd)/deploy/observability/grafana/provisioning/dashboards/geostudio-dashboards.yaml:/otel-lgtm/grafana/conf/provisioning/dashboards/geostudio-dashboards.yaml" \
  -v "$(pwd)/deploy/observability/grafana/provisioning/dashboards/custom:/otel-lgtm/grafana/conf/provisioning/dashboards/custom" \
  grafana/otel-lgtm:0.11.4
sleep 20
curl -s -u admin:admin "http://localhost:13040/api/search?type=dash-db" | python3 -c "
import json,sys
titles = sorted(d['title'] for d in json.load(sys.stdin))
print('\n'.join(titles))
"
docker rm -f sp10b-dash-check
```

Expected: la liste inclut au moins `GeoStudio — Cœur`, `GeoStudio — Martin (tuiles)`, `GeoStudio — Jobs`, `GeoStudio — Postgres` (en plus des 3 dashboards par défaut de l'image, `JVM Overview (OpenTelemetry)`/`RED Metrics …`, laissés intacts — confirmés non affectés par ce montage).

- [ ] **Step 7: Commit**

```bash
git add deploy/observability/grafana/provisioning/dashboards
git commit -m "feat(deploy): SP-10b — 4 dashboards Grafana packagés (cœur, Martin, jobs, Postgres)"
```

---

### Task 5: SLO et alertes Grafana (5 règles)

**Files:**
- Create: `deploy/observability/grafana/provisioning/alerting/rules.yaml`

**Interfaces:**
- Consumes: mêmes métriques que Task 4 (`http_server_duration_milliseconds_*`, `martin_http_requests_duration_seconds_*`, `geostudio_jobs_backlog`).
- Produces: 5 règles Grafana Alerting dans le dossier `SLO` (4 réelles) + un dossier séparé pour la règle de test — visibles via `GET /api/prometheus/grafana/api/v1/rules` (vérifié, cf. Step 2).

- [ ] **Step 1: Écrire les 5 règles**

`deploy/observability/grafana/provisioning/alerting/rules.yaml` :

```yaml
apiVersion: 1
groups:
  - orgId: 1
    name: SLO
    folder: SLO
    interval: 1m
    rules:
      - uid: slo-api-features-latency-p95
        title: "SLO: latence API Features P95 < 200ms"
        condition: B
        data:
          - refId: A
            datasourceUid: prometheus
            relativeTimeRange: {from: 300, to: 0}
            model:
              editorMode: code
              expr: histogram_quantile(0.95, sum(rate(http_server_duration_milliseconds_bucket{http_route=~"/collections/.*/items.*"}[5m])) by (le))
              instant: true
              refId: A
          - refId: B
            datasourceUid: "__expr__"
            model:
              type: threshold
              expression: A
              conditions:
                - evaluator: {type: gt, params: [200]}
              refId: B
        for: 5m
        noDataState: OK
        execErrState: Error
        labels: {severity: warning, slo: api-features-latency}
        annotations: {summary: "Latence P95 des routes OGC API Features au-dessus de 200ms depuis 5 minutes"}
        isPaused: false

      - uid: slo-martin-tiles-latency-p95
        title: "SLO: latence tuiles Martin P95 < 50ms"
        condition: B
        data:
          - refId: A
            datasourceUid: prometheus
            relativeTimeRange: {from: 300, to: 0}
            model:
              editorMode: code
              expr: histogram_quantile(0.95, sum(rate(martin_http_requests_duration_seconds_bucket{endpoint="/{source_ids}/{z}/{x}/{y}"}[5m])) by (le))
              instant: true
              refId: A
          - refId: B
            datasourceUid: "__expr__"
            model:
              type: threshold
              expression: A
              conditions:
                - evaluator: {type: gt, params: [0.05]}
              refId: B
        for: 5m
        noDataState: OK
        execErrState: Error
        labels: {severity: warning, slo: martin-tiles-latency}
        annotations: {summary: "Latence P95 des tuiles Martin au-dessus de 50ms depuis 5 minutes"}
        isPaused: false

      - uid: slo-jobs-backlog
        title: "SLO: backlog de jobs sous seuil"
        condition: B
        data:
          - refId: A
            datasourceUid: prometheus
            relativeTimeRange: {from: 300, to: 0}
            model:
              editorMode: code
              expr: sum(geostudio_jobs_backlog)
              instant: true
              refId: A
          - refId: B
            datasourceUid: "__expr__"
            model:
              type: threshold
              expression: A
              conditions:
                # Seuil provisoire (aucun trafic réel pour le calibrer) —
                # ajustable sans changer la structure de la règle.
                - evaluator: {type: gt, params: [50]}
              refId: B
        for: 5m
        noDataState: OK
        execErrState: Error
        labels: {severity: warning, slo: jobs-backlog}
        annotations: {summary: "Backlog de jobs procrastinate au-dessus du seuil depuis 5 minutes"}
        isPaused: false

      - uid: slo-api-5xx-rate
        title: "SLO: taux de 5xx < 1%"
        condition: B
        data:
          - refId: A
            datasourceUid: prometheus
            relativeTimeRange: {from: 300, to: 0}
            model:
              editorMode: code
              expr: sum(rate(http_server_duration_milliseconds_count{http_status_code=~"5.."}[5m])) / sum(rate(http_server_duration_milliseconds_count[5m]))
              instant: true
              refId: A
          - refId: B
            datasourceUid: "__expr__"
            model:
              type: threshold
              expression: A
              conditions:
                - evaluator: {type: gt, params: [0.01]}
              refId: B
        for: 5m
        noDataState: OK
        execErrState: Error
        labels: {severity: critical, slo: api-5xx-rate}
        annotations: {summary: "Taux de réponses 5xx au-dessus de 1% depuis 5 minutes"}
        isPaused: false

  # Dossier séparé, volontairement distinct de SLO : preuve reproductible
  # que le pipeline d'alerting fonctionne bout en bout (condition
  # mathématique triviale, ne dépend d'aucune métrique/trafic réel),
  # PAS un SLO. isPaused: true par défaut — mettre à `false` juste avant
  # une démo pour observer l'état "firing" en quelques secondes, remettre
  # à `true` ensuite (ne pas laisser cette règle active en continu : elle
  # sonne toujours vraie par construction, cf. Task 6 Step 5).
  - orgId: 1
    name: test-alert-do-not-keep-in-prod
    folder: SLO-test-alert-do-not-keep-in-prod
    interval: 10s
    rules:
      - uid: test-alert-always-firing
        title: "TEST — preuve que le pipeline d'alerting fonctionne (pas un SLO)"
        condition: A
        data:
          - refId: A
            datasourceUid: "__expr__"
            model:
              type: math
              expression: "1 == 1"
              refId: A
        for: 0s
        noDataState: OK
        execErrState: Alerting
        labels: {severity: test}
        annotations: {summary: "Alerte de test toujours déclenchée — preuve du pipeline d'alerting, à laisser en pause hors démo"}
        isPaused: true
```

- [ ] **Step 2: Vérifier empiriquement que les règles se chargent et que la règle de test se déclenche**

```bash
mkdir -p /tmp/sp10b-alert-check
cp deploy/observability/grafana/provisioning/alerting/rules.yaml /tmp/sp10b-alert-check/
# Copie temporaire avec la règle de test dépausée, pour la seule durée de
# cette vérification manuelle (le fichier commité en Step 1 reste isPaused: true).
sed 's/isPaused: true/isPaused: false/' /tmp/sp10b-alert-check/rules.yaml > /tmp/sp10b-alert-check/rules-unpaused.yaml
mv /tmp/sp10b-alert-check/rules-unpaused.yaml /tmp/sp10b-alert-check/rules.yaml

docker run -d --rm --name sp10b-alert-check -p 13050:3000 \
  -v /tmp/sp10b-alert-check:/otel-lgtm/grafana/conf/provisioning/alerting \
  grafana/otel-lgtm:0.11.4
sleep 20
curl -s -u admin:admin "http://localhost:13050/api/prometheus/grafana/api/v1/rules" | python3 -c "
import json,sys
d = json.load(sys.stdin)
for g in d['data']['groups']:
    for r in g['rules']:
        print(g['name'], '/', r['name'], '->', r['state'])
"
docker rm -f sp10b-alert-check
rm -rf /tmp/sp10b-alert-check
```

Expected: 5 lignes affichées (4 règles `SLO` à l'état `pending` ou `inactive` selon le trafic — normal, aucun trafic généré ici — et `test-alert-do-not-keep-in-prod / TEST — … -> firing`, apparaissant en quelques secondes).

- [ ] **Step 3: Commit**

```bash
git add deploy/observability/grafana/provisioning/alerting
git commit -m "feat(deploy): SP-10b — 5 règles d'alerte Grafana (4 SLO + 1 règle de test)"
```

---

### Task 6: Validation de bout en bout contre les 5 critères d'acceptation

**Files:** aucun fichier créé — validation empirique pure contre la stack complète.

**Interfaces:**
- Consumes: l'ensemble des livrables Tasks 1-5.

- [ ] **Step 1: Préparer l'environnement**

```bash
[ -f .env ] || ./scripts/bootstrap-env.sh
```

(cf. `README.md`/`CONTRIBUTING.md`, SP-9 install-secrets — génère un `.env` avec des secrets forts si absent, n'écrase jamais un `.env` existant.)

- [ ] **Step 2: Critère #5 — `docker compose up` par défaut reste inchangé**

```bash
docker compose up -d postgis pgbouncer minio core worker
sleep 15
curl -s -o /dev/null -w "core /health: %{http_code}\n" http://localhost:8200/health
docker compose logs core --tail 50 | grep -iE "error|traceback" || echo "aucune erreur dans les logs core"
docker compose logs worker --tail 50 | grep -iE "error|traceback" || echo "aucune erreur dans les logs worker"
```

Expected: `core /health: 200`, aucune ligne d'erreur (un bruit de log périodique de connexion OTLP refusée est toléré et documenté — cf. §Risques de la spec — mais ne doit apparaître ni comme `ERROR` bloquant ni comme `Traceback`).

- [ ] **Step 3: Critères #1-#4 — démarrer le profil observability et générer du trafic**

```bash
docker compose --profile observability up -d
sleep 30

# Trafic cœur (déclenche http_server_duration_milliseconds)
for i in $(seq 1 20); do curl -s -o /dev/null http://localhost:8200/health; done

# Trafic Martin (déclenche martin_http_requests_total) — adapter la source
# à une couche réellement enregistrée dans martin-config.yaml / la base démo
curl -s -o /dev/null http://localhost:3000/catalog

sleep 20  # laisser au moins un cycle de scrape (15s) + un export OTLP passer
```

- [ ] **Step 4: Critère #1 — les 4 dashboards affichent des données réelles**

```bash
curl -s -u admin:admin "http://localhost:3001/api/datasources/proxy/uid/prometheus/api/v1/query?query=up" | python3 -m json.tool | head -20
```

Expected: au moins une série avec `"value"` non vide pour `job="martin"`, `job="postgres"` et `job="geostudio-core"` (ou nom de service équivalent) — confirme que le scraping/l'export alimentent bien Prometheus. Compléter par une inspection visuelle des 4 dashboards sur `http://localhost:3001` (identifiants par défaut `admin`/`admin`).

- [ ] **Step 5: Critère #2 — traçage bout en bout d'une requête lente**

Depuis Grafana Explore (`http://localhost:3001`, datasource Tempo), rechercher les traces récentes du service `geostudio-core` et confirmer qu'un span HTTP contient des spans enfants SQL (auto-instrumentation SQLAlchemy, SP-10a). Documenter le `trace_id` observé dans le rapport de tâche.

- [ ] **Step 6: Critère #3 et #4 — SLO visibles, alerte de test observable**

```bash
curl -s -u admin:admin "http://localhost:3001/api/prometheus/grafana/api/v1/rules" | python3 -c "
import json,sys
d = json.load(sys.stdin)
for g in d['data']['groups']:
    for r in g['rules']:
        print(g['name'], '/', r['name'], '->', r['state'])
"
```

Expected: les 4 règles du dossier `SLO` sont listées (état dépendant du trafic généré). La règle de test reste `isPaused: true` par défaut (committée ainsi en Task 5) — pour observer concrètement l'état `firing`, dépauser temporairement via l'UI Grafana Alerting (`http://localhost:3001/alerting/list`) ou en éditant `deploy/observability/grafana/provisioning/alerting/rules.yaml` localement puis `docker compose --profile observability restart otel-lgtm` (ne pas committer ce changement — la règle doit rester en pause dans le dépôt).

- [ ] **Step 7: Nettoyer**

```bash
docker compose --profile observability down
```

- [ ] **Step 8: Rapport de tâche**

Consigner dans le rapport : capture ou extrait JSON des 4 dashboards avec données, `trace_id` de la Step 5, état des 5 règles d'alerte (avant/après dépause de la règle de test), et toute divergence rencontrée par rapport aux corrections déjà documentées en tête de ce plan.

---

## Self-Review (effectuée à l'écriture du plan)

**Couverture spec** : profil compose (Task 1) ✓, scraping Martin/Postgres (Task 2) ✓, métrique de backlog (Task 3) ✓, 4 dashboards (Task 4) ✓, 5 règles d'alerte (Task 5) ✓, les 5 critères d'acceptation de la spec sont chacun couverts par une étape explicite de Task 6. Le hors-périmètre de la spec (télémétrie navigateur, SLO fraîcheur CDC, notifications externes) n'est traité par aucune tâche — cohérent.

**Placeholders** : aucun ; chaque fichier de config/dashboard/règle est donné en contenu complet et a été testé démarrable/chargeable contre une vraie image avant d'être écrit dans ce plan (cf. §Corrections, qui documente précisément ce qui a été vérifié et pourquoi le texte de la spec a été corrigé sur ces points).

**Cohérence des types/noms** : `register_jobs_backlog_gauge(engine, *, meter=None)` (Task 3) est le seul point d'entrée nouveau côté code Python, son nom de métrique Prometheus final (`geostudio_jobs_backlog`) est utilisé identiquement dans le dashboard Jobs (Task 4) et la règle SLO backlog (Task 5) — vérifié par la même recherche de chaîne dans les trois fichiers.
