"""Instance procrastinate.App partagée par tout le cœur — un seul worker
process (docker-compose.yml, service `worker`) exécute toutes les tâches de
tous les modules `*.jobs`/`*.tasks`, quel que soit le domaine qui les a
déférées. Module volontairement hors du contrat de couches import-linter
(comme app.db) : app.items et app.collections doivent pouvoir l'importer
sans que ce soit une violation de couche."""
import os

import procrastinate


def _conninfo() -> str:
    # .get() avec repli, jamais os.environ[...] : ce module est importé
    # transitivement par app.main dans toute la suite de tests, y compris
    # les tests SQLite qui ne définissent jamais DATABASE_URL — un KeyError
    # ici casserait la collecte pytest entière. Le repli n'est jamais
    # utilisé pour de vrai (le worker/cœur déployés reçoivent toujours
    # DATABASE_URL via docker-compose).
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost/geostudio_dev")
    return database_url.replace("postgresql+psycopg://", "postgresql://")


app = procrastinate.App(connector=procrastinate.SyncPsycopgConnector(conninfo=_conninfo()))
