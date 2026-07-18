# SPDX-License-Identifier: Apache-2.0
"""Une seule instance procrastinate.App pour tout le process (Task 1, SP-7) —
sinon une tâche déférée par un module et exécutée par le worker d'un autre
App échoue (nom de tâche absent de son registre)."""
import subprocess
import sys
from pathlib import Path

import procrastinate

from app import jobs
from app.ingestion import tasks as ingestion_tasks


def test_jobs_app_is_a_procrastinate_app():
    assert isinstance(jobs.app, procrastinate.App)


def test_ingestion_tasks_reuses_the_shared_app():
    assert ingestion_tasks.app is jobs.app


def test_import_paths_registers_all_domain_tasks():
    """Fix de la régression critique trouvée en revue finale de branche SP-7 :
    docker-compose.yml lance le worker avec
    `procrastinate --app app.jobs.app worker -q ingestion,search`, qui
    n'importe QUE le module app.jobs pour résoudre le chemin pointé
    (`App.from_path`) — jamais app.ingestion.tasks, app.items.jobs ni
    app.collections.jobs, les modules qui enregistrent réellement les
    tâches (`@app.task(...)`) sur l'App partagée en import time. Sans
    `import_paths` sur l'App, le worker démarre avec un registre de tâches
    vide (hors tâches builtin) : toute tâche déférée par le process API
    (qui, lui, a bien importé ces modules) est introuvable côté worker.

    Ce test reproduit fidèlement ce que fait le worker CLI au démarrage
    (App.from_path puis App.perform_import_paths(), voir
    procrastinate.cli.load_app / procrastinate.app.App.run_worker_async)
    dans un SOUS-PROCESS FRAIS qui n'importe qu'app.jobs — un test in-process
    ne serait pas fiable : d'autres modules de tests important déjà
    app.ingestion.tasks/app.items.jobs/app.collections.jobs directement dans
    le même process pytest, ces décorateurs se seraient déjà exécutés sur le
    singleton partagé même si import_paths était resté vide, masquant la
    régression.

    RED sur `import_paths=[]` (état avant fix) : seules les tâches builtin
    de procrastinate apparaissent. GREEN après avoir passé
    `import_paths=["app.ingestion.tasks", "app.items.jobs",
    "app.collections.jobs"]` au constructeur de app.jobs.app."""
    core_dir = Path(__file__).resolve().parents[1]
    script = (
        "from app import jobs\n"
        "jobs.app.perform_import_paths()\n"
        "print('\\n'.join(sorted(jobs.app.tasks.keys())))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=core_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"sous-process d'import a échoué : {result.stderr}"
    )
    task_names = set(result.stdout.strip().splitlines())
    assert "app.ingestion.tasks.run_ingestion_task" in task_names
    assert "app.items.jobs.embed_item_task" in task_names
    assert "app.collections.jobs.embed_collection_task" in task_names
    assert "app.cdc.jobs.run_compaction_cycle_task" in task_names
