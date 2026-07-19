# SPDX-License-Identifier: Apache-2.0
"""Instance procrastinate.App partagée par tout le cœur — un seul worker
process (docker-compose.yml, service `worker`) exécute toutes les tâches de
tous les modules `*.jobs`/`*.tasks`, quel que soit le domaine qui les a
déférées. Module volontairement hors du contrat de couches import-linter
(comme app.db) : app.items et app.collections doivent pouvoir l'importer
sans que ce soit une violation de couche.

`import_paths` est nécessaire (pas cosmétique) : docker-compose.yml lance le
worker avec `procrastinate --app app.jobs.app worker ...`, qui n'importe QUE
ce module (pour résoudre `app.jobs.app`) — pas app.ingestion.tasks,
app.items.jobs ni app.collections.jobs, les modules qui enregistrent
réellement les tâches (`@app.task(...)`) sur cette App partagée en import
time. Sans `import_paths`, le worker démarre avec un registre de tâches vide
(hors tâches builtin) et toute tâche déférée par un autre process (qui, lui,
a bien importé ces modules) échoue faute d'être connue du worker. Procrastinate
importe ces chemins lui-même, paresseusement, via `App.perform_import_paths()`
au démarrage du worker (et de `configure_task`) — voir
`tests/test_jobs.py::test_import_paths_registers_all_domain_tasks`."""
import os

import procrastinate

from app import observability

# Le worker réel (docker-compose.yml, `python -m procrastinate --app
# app.jobs.app worker ...`) n'exécute jamais app.main/create_app() — la même
# raison exacte que celle documentée ci-dessus pour import_paths : quel que
# soit le process qui importe ce module EST le point d'entrée du worker.
# setup() doit donc être appelé ici pour que le worker ait un TracerProvider/
# MeterProvider OTLP et des logs JSON — sans quoi otel_worker_middleware crée
# des spans contre un tracer proxy no-op jamais exportés. Idempotent
# (_configured), donc sans risque même si create_app() l'appelle aussi dans
# le même process (API + worker co-localisés, tests, etc.).
observability.setup()


def _conninfo() -> str:
    # .get() avec repli, jamais os.environ[...] : ce module est importé
    # transitivement par app.main dans toute la suite de tests, y compris
    # les tests SQLite qui ne définissent jamais DATABASE_URL — un KeyError
    # ici casserait la collecte pytest entière. Le repli n'est jamais
    # utilisé pour de vrai (le worker/cœur déployés reçoivent toujours
    # DATABASE_URL via docker-compose).
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost/geostudio_dev")
    return database_url.replace("postgresql+psycopg://", "postgresql://")


app = procrastinate.App(
    # PsycopgConnector (async), pas SyncPsycopgConnector : le CLI procrastinate
    # refuse tout connecteur qui n'est pas une sous-classe de BaseAsyncConnector
    # (`procrastinate --app app.jobs.app worker`, la commande exacte de
    # docker-compose.yml, levait "The connector provided by the app is not
    # async" — le worker ne démarrait jamais). PsycopgConnector reste
    # utilisable en synchrone par `.defer(...)` dans les routes FastAPI (non
    # async) : tant qu'il n'est pas ouvert explicitement en async, il crée un
    # SyncPsycopgConnector interne à la demande (get_sync_connector()).
    connector=procrastinate.PsycopgConnector(conninfo=_conninfo()),
    import_paths=[
        "app.ingestion.tasks", "app.items.jobs", "app.collections.jobs",
        "app.cdc.jobs", "app.harvest.jobs",
    ],
    worker_defaults={"worker_middleware": [observability.otel_worker_middleware]},
)
