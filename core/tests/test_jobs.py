"""Une seule instance procrastinate.App pour tout le process (Task 1, SP-7) —
sinon une tâche déférée par un module et exécutée par le worker d'un autre
App échoue (nom de tâche absent de son registre)."""
import procrastinate

from app import jobs
from app.ingestion import tasks as ingestion_tasks


def test_jobs_app_is_a_procrastinate_app():
    assert isinstance(jobs.app, procrastinate.App)


def test_ingestion_tasks_reuses_the_shared_app():
    assert ingestion_tasks.app is jobs.app
