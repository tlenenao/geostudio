# SPDX-License-Identifier: Apache-2.0
"""`PipelineRuntimeError` — module leaf, sans dépendance (revue finale de
branche du chantier IPC d'échange DuckDB↔Arrow, Important #2) : extrait de
`app.pipelines.runtime` pour que `app.pipelines.exchange` (et tout futur
consommateur léger) puisse l'importer sans tirer les imports lourds de
`runtime.py` (SQLAlchemy, httpx, app.analytics, app.collections...) au
niveau module — un `from app.pipelines.exchange import ...` fait depuis le
haut de `runtime.py` lèverait sinon une ImportError sur un module
partiellement initialisé, puisque `runtime.py` définissait cette classe
après son propre bloc d'imports. `runtime.py` réexporte cette classe pour
ne casser aucun des appelants existants (`from app.pipelines.runtime import
PipelineRuntimeError`)."""


class PipelineRuntimeError(Exception):
    """Erreur d'exécution : la tâche procrastinate (Task 9) l'attrape et
    marque le run 'failed', jamais 'zombie'."""
