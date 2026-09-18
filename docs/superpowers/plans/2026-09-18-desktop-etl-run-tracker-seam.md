# Desktop ETL — seam `RunTracker` (socle sidecar, tranche 2) — plan

> **Pour les agents d'exécution :** SOUS-COMPÉTENCE REQUISE : utiliser
> superpowers:subagent-driven-development (recommandé) ou
> superpowers:executing-plans pour exécuter ce plan tâche par tâche. Les
> étapes utilisent la syntaxe case à cocher (`- [ ]`) pour le suivi.

**Objectif :** découpler `core/app/pipelines/jobs.py::run_pipeline_task` de
son appel direct à `app.pipelines.repository.mark_running/mark_succeeded/
mark_failed` (Postgres) en introduisant un Protocol `RunTracker` injecté,
avec une implémentation Postgres par défaut équivalente au comportement
actuel. C'est le point de couplage identifié par
[`docs/superpowers/specs/2026-09-17-desktop-etl-standalone-design.md`](../specs/2026-09-17-desktop-etl-standalone-design.md)
§4 avant qu'un futur sidecar desktop (suivi de run en mémoire, pas de
Postgres) puisse exécuter `app.pipelines.runtime.run_pipeline` sans dupliquer
la logique de transition de statut. Cette tranche fait suite à la tranche 1
(`SecretResolver`, plan
[`2026-09-17-desktop-etl-secret-resolver-seam.md`](2026-09-17-desktop-etl-secret-resolver-seam.md),
déjà exécutée et mergée sur `dev`) — même « socle sidecar » du découpage §11
du design.

**Correction par rapport au brainstorm initial (à consigner, pas à
reproduire ailleurs) :** l'idée d'origine introduisait aussi une fonction
`execute_pipeline_run(...)` séparée pour « l'appel partagé au moteur DAG ».
En relisant le code réel de `jobs.py`, ce n'est pas nécessaire :
`app.pipelines.runtime.run_pipeline()` (ligne 954) est **déjà** la fonction
partagée — elle prend `payload`/`user`/les creds S3 en paramètres explicites,
sans aucune dépendance à procrastinate. Le seul vrai couplage restant est les
3 appels `pipelines_repo.mark_*`, directement inline dans
`run_pipeline_task`. Ajouter une fonction d'orchestration intermédiaire
n'aurait fait qu'ajouter une couche sans réutilisation réelle (YAGNI) — le
futur sidecar desktop appellera directement `run_pipeline()` avec son propre
`RunTracker`, exactement comme `run_pipeline_task` le fait ici avec
`PostgresRunTracker`.

**Architecture :** `jobs.py` gagne un Protocol `RunTracker`
(`mark_running() -> None`, `mark_succeeded(node_stats: dict) -> None`,
`mark_failed(error: str) -> None`) et une implémentation
`PostgresRunTracker(session_factory, *, run_id, tenant_id)` — chaque méthode
ouvre sa propre transaction courte via `request_scoped_session`, exactement
comme le fait aujourd'hui le code inline (une transaction par transition de
statut, jamais une transaction partagée pour tout le run). `run_pipeline_task`
construit un `PostgresRunTracker` en tête de fonction et remplace ses 3
appels `pipelines_repo.mark_running/mark_succeeded/mark_failed` par
`tracker.mark_running()/mark_succeeded(...)/mark_failed(...)`. Aucun autre
appelant de production n'existe (vérifié : `pipelines_repo.mark_running/
mark_succeeded/mark_failed` ne sont utilisées que dans `jobs.py`) — donc
**aucun changement de comportement observable côté route REST/MCP/UI**.

**Nuance interne acceptée (à documenter, pas à corriger) :** aujourd'hui,
`pipelines_repo.get_run` et `pipelines_repo.mark_running` partagent la même
transaction (`with request_scoped_session(...) as session:` unique). Après
ce refactor, `tracker.mark_running()` ouvre sa propre transaction, séparée
de celle du `get_run` précédent. Deux commits au lieu d'un, même état final
en base, aucune différence observable pour un appelant externe (mêmes lignes
`pipeline_runs` écrites, même ordre logique running→succeeded/failed) —
accepté, comme la tranche 1 avait accepté l'import résiduel de
`app.secrets.repository`.

**Tech Stack :** Python 3.12, `typing.Protocol`, SQLAlchemy `Session`/
`sessionmaker`, pytest.

## Global Constraints

- TDD systématique (CLAUDE.md « Comment on travaille ») : le "rouge" pour
  Task 1 est un import inexistant (`AttributeError`) ; pour Task 2, la
  suite `test_pipeline_jobs.py` existante (déjà verte) sert de filet de
  non-régression — elle ne doit **jamais** rougir après le refactor.
- Commits conventionnels, petits, un sujet par commit
  (`refactor(core): …`/`feat(core): …`), message se terminant par
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Docs et commentaires en français, code/identifiants en anglais (cf.
  conventions déjà en usage dans `jobs.py`).
- **Aucun changement de comportement observable** : aucune route REST,
  aucun outil MCP, aucun schéma Pydantic exposé ne change. Les 3 fonctions
  `pipelines_repo.mark_running/mark_succeeded/mark_failed` ne changent pas
  de signature (seul leur appelant change de forme).
- `core/app/pipelines/` n'est pas dans le périmètre `mypy --strict` listé
  dans `CLAUDE.md` (`app/auth app/secrets app/analytics app/copilot
  app/admin_tools app/roles`) — pas d'obligation de typage strict
  supplémentaire au-delà de ce que ce plan spécifie.
- Ne pas introduire d'abstraction au-delà de ce que ce plan demande — YAGNI,
  pas de fonction d'orchestration intermédiaire (cf. correction ci-dessus),
  pas de config par variable d'environnement dans cette tranche.
- Les nouveaux tests de `PostgresRunTracker` utilisent SQLite en mémoire
  (patron déjà en usage dans `tests/test_pipeline_connector_runtime.py` et
  `tests/test_export_repository.py` — `PipelineRun`/`Item` n'ont aucune
  colonne géométrique, contrairement aux tests de `test_pipeline_jobs.py`
  qui restent `pytest.mark.postgis` à cause de la table `villes_propres`).
  Ne PAS ajouter ces tests au fichier `test_pipeline_jobs.py` existant : son
  `pytestmark = pytest.mark.postgis` de niveau module s'appliquerait à eux
  aussi et les ferait skipper silencieusement sans `CORE_TEST_DATABASE_URL`
  (piège CLAUDE.md « Pièges récurrents » #3/#12) — créer un fichier séparé.
- Lancer `cd core && uv run pytest tests/test_pipeline_run_tracker.py tests/test_pipeline_jobs.py -q`
  avant chaque commit de tâche impactant ces fichiers. `test_pipeline_jobs.py`
  est `postgis`-marqué en entier — s'il skippe silencieusement faute de
  `CORE_TEST_DATABASE_URL`, le noter dans le rapport de tâche plutôt que de
  déclarer la tâche verte sans réserve.

---

## File Structure

- **Modifie `core/app/pipelines/jobs.py`** : ajoute `RunTracker` (Protocol)
  + `PostgresRunTracker` (implémentation par défaut) ; `run_pipeline_task`
  construit un tracker et l'utilise à la place des 3 appels
  `pipelines_repo.mark_*` inline.
- **Crée `core/tests/test_pipeline_run_tracker.py`** : 3 tests unitaires
  pour `PostgresRunTracker` (SQLite en mémoire, sans marqueur `postgis`).
- **Ne modifie pas** `app/pipelines/repository.py`, `app/pipelines/
  runtime.py`, `app/pipelines/service.py`, `app/pipelines/routes.py`, ni
  aucun schéma Pydantic exposé.

---

### Task 1 : `RunTracker` Protocol + `PostgresRunTracker` (additif, ne casse rien)

**Files:**
- Modify: `core/app/pipelines/jobs.py`
- Create: `core/tests/test_pipeline_run_tracker.py`

**Interfaces:**
- Produces: `jobs.RunTracker` (Protocol, méthodes `mark_running(self) ->
  None`, `mark_succeeded(self, node_stats: dict) -> None`,
  `mark_failed(self, error: str) -> None`) ;
  `jobs.PostgresRunTracker(session_factory: sessionmaker[Session], *,
  run_id: str, tenant_id: str)` avec les 3 mêmes méthodes.
- Consumes: `app.pipelines.repository.mark_running/mark_succeeded/
  mark_failed` (déjà importées dans `jobs.py` sous `pipelines_repo`),
  `app.db.request_scoped_session` (déjà importée dans `jobs.py`).

- [ ] **Step 1: Écrire les tests qui échouent (import inexistant)**

Créer `core/tests/test_pipeline_run_tracker.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session_factory():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _seed_run(factory):
    with factory() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="u1",
            username="u1",
            email=None,
            first_name="",
            last_name="",
        )
        item = items_repo.create_item(
            session,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="pipeline",
            title="P",
        )
        session.commit()
        run = pipelines_repo.create_run(session, tenant_id=tenant.id, pipeline_item_id=item.id)
        session.commit()
        return tenant.id, run.id


def test_postgres_run_tracker_mark_running_sets_status_and_started_at():
    factory = _session_factory()
    tenant_id, run_id = _seed_run(factory)
    tracker = pipeline_jobs.PostgresRunTracker(factory, run_id=run_id, tenant_id=tenant_id)

    tracker.mark_running()

    with factory() as session:
        run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
        assert run.status == "running"
        assert run.started_at is not None


def test_postgres_run_tracker_mark_succeeded_stores_node_stats():
    factory = _session_factory()
    tenant_id, run_id = _seed_run(factory)
    tracker = pipeline_jobs.PostgresRunTracker(factory, run_id=run_id, tenant_id=tenant_id)

    tracker.mark_succeeded({"n1": {"rows": 3}})

    with factory() as session:
        run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
        assert run.status == "succeeded"
        assert run.node_stats == {"n1": {"rows": 3}}


def test_postgres_run_tracker_mark_failed_stores_error():
    factory = _session_factory()
    tenant_id, run_id = _seed_run(factory)
    tracker = pipeline_jobs.PostgresRunTracker(factory, run_id=run_id, tenant_id=tenant_id)

    tracker.mark_failed("boom")

    with factory() as session:
        run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
        assert run.status == "failed"
        assert run.error == "boom"
```

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd core && uv run pytest tests/test_pipeline_run_tracker.py -v`
Expected: FAIL avec `AttributeError: module 'app.pipelines.jobs' has no
attribute 'PostgresRunTracker'`

- [ ] **Step 3: Ajouter le Protocol et l'implémentation par défaut**

Dans `core/app/pipelines/jobs.py`, ajouter à l'import stdlib en tête de
fichier (juste après `from collections.abc import Callable`, ligne 11) :

```python
from typing import Protocol
```

Puis ajouter les deux classes juste avant `@app.task(queue="etl")` /
`def run_pipeline_task` (ligne 141), après `_make_progress_callback` :

```python
class RunTracker(Protocol):
    """Seam introduit pour découpler run_pipeline_task de
    app.pipelines.repository (Postgres) — un futur sidecar desktop (design
    2026-09-17 §4, suivi de run en mémoire, sans Postgres) fournira sa
    propre implémentation sans dupliquer app.pipelines.runtime.run_pipeline."""

    def mark_running(self) -> None: ...
    def mark_succeeded(self, node_stats: dict) -> None: ...
    def mark_failed(self, error: str) -> None: ...


class PostgresRunTracker:
    """Implémentation par défaut, utilisée par le worker procrastinate —
    une transaction courte par transition de statut, comme l'ancien code
    inline (jamais une transaction partagée pour tout le run)."""

    def __init__(self, session_factory, *, run_id: str, tenant_id: str) -> None:
        self._session_factory = session_factory
        self._run_id = run_id
        self._tenant_id = tenant_id

    def mark_running(self) -> None:
        with request_scoped_session(self._session_factory) as session:
            pipelines_repo.mark_running(session, run_id=self._run_id)

    def mark_succeeded(self, node_stats: dict) -> None:
        with request_scoped_session(self._session_factory) as session:
            pipelines_repo.mark_succeeded(
                session, run_id=self._run_id, node_stats=node_stats
            )

    def mark_failed(self, error: str) -> None:
        with request_scoped_session(self._session_factory) as session:
            pipelines_repo.mark_failed(session, run_id=self._run_id, error=error)
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `cd core && uv run pytest tests/test_pipeline_run_tracker.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Suite pipelines complète (doit rester verte — rien d'autre n'a changé)**

Run: `cd core && uv run pytest tests/test_pipeline_jobs.py -q`
Expected: tous les tests déjà existants PASS ou skip `postgis` (cette tâche
est purement additive, `run_pipeline_task` n'a pas encore changé).

- [ ] **Step 6: Commit**

```bash
cd core
git add app/pipelines/jobs.py tests/test_pipeline_run_tracker.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute le Protocol RunTracker au job de pipeline

Prépare la réutilisation de app.pipelines.runtime.run_pipeline par un futur
sidecar desktop sans Postgres (design 2026-09-17 §4) : PostgresRunTracker
reproduit à l'identique le comportement actuel des 3 appels
pipelines_repo.mark_running/mark_succeeded/mark_failed, point d'extension
pour un suivi de run en mémoire à venir. Additif, run_pipeline_task ne
change pas encore à cette étape.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2 : `run_pipeline_task` utilise `PostgresRunTracker` au lieu de `pipelines_repo.mark_*` inline

**Files:**
- Modify: `core/app/pipelines/jobs.py`

**Interfaces:**
- Consumes: `jobs.RunTracker`/`jobs.PostgresRunTracker` (Task 1).
- Produces: aucune interface nouvelle — `run_pipeline_task` garde
  exactement sa signature actuelle (`(run_id: str, tenant_id: str) ->
  None`, tâche procrastinate), donc aucun appelant (`service.py`,
  `run_pipeline_sweep_task`) n'est affecté.

- [ ] **Step 1: Remplacer le corps de `run_pipeline_task`**

Dans `core/app/pipelines/jobs.py`, remplacer la fonction complète (lignes
141-219) par :

```python
@app.task(queue="etl")
def run_pipeline_task(run_id: str, tenant_id: str) -> None:
    factory = _session_factory()
    tracker = PostgresRunTracker(factory, run_id=run_id, tenant_id=tenant_id)
    # Toujours lié avant le premier bloc protégé : si get_run lève avant
    # l'affectation réelle (ci-dessous), les handlers `except` doivent
    # pouvoir le lire sans UnboundLocalError (même piège que
    # app.ingestion.tasks._notify, trouvé en revue de la Tâche 4, SP-39) —
    # None encode "item inconnu", donc pas de notification best-effort
    # possible dans ce cas (le statut du run est déjà marqué "failed" par
    # ailleurs, la garantie best-effort porte sur la notification, pas sur
    # le statut du run).
    item_id: str | None = None

    try:
        with request_scoped_session(factory) as session:
            run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
            if run is None:
                logger.error("pipeline run %s introuvable (tenant %s)", run_id, tenant_id)
                return
            item_id = run.pipeline_item_id
        tracker.mark_running()

        with request_scoped_session(factory) as session:
            payload = _get_pipeline_payload(session, item_id=item_id)
            user = _acting_user(session, tenant_id=tenant_id, item_id=item_id)
            stats = run_pipeline(
                session,
                payload=payload,
                tenant_id=tenant_id,
                user=user,
                endpoint_url=os.environ["S3_ENDPOINT_URL"],
                access_key=os.environ["S3_ACCESS_KEY"],
                secret_key=os.environ["S3_SECRET_KEY"],
                base_uri=_analytics_base_uri(),
                s3_client=_s3_client_from_env(),
                exports_bucket=os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"),
                qgis_worker_url=os.environ.get("QGIS_WORKER_URL", ""),
                qgis_worker_timeout_seconds=int(
                    os.environ.get("QGIS_WORKER_TIMEOUT_SECONDS", "600")
                ),
                on_node_complete=_make_progress_callback(
                    factory, run_id=run_id, tenant_id=tenant_id
                ),
            )
        tracker.mark_succeeded({s.nodeId: s.to_dict() for s in stats})
        assert item_id is not None  # affecté ci-dessus, jamais atteint sinon (cf. return/raise)
        _notify(factory, tenant_id=tenant_id, item_id=item_id, status="success")
    except (PipelineRuntimeError, ValueError) as exc:
        tracker.mark_failed(str(exc))
        if item_id is not None:
            _notify(
                factory,
                tenant_id=tenant_id,
                item_id=item_id,
                status="failure",
                error=str(exc),
            )
        else:
            logger.info("pipeline run %s : notification ignorée (item inconnu)", run_id)
    except Exception as exc:  # toute erreur inattendue finit "failed", jamais zombie
        logger.exception("pipeline run %s : erreur inattendue", run_id)
        tracker.mark_failed(f"erreur interne : {exc}")
        if item_id is not None:
            _notify(
                factory,
                tenant_id=tenant_id,
                item_id=item_id,
                status="failure",
                error=f"erreur interne : {exc}",
            )
        else:
            logger.info("pipeline run %s : notification ignorée (item inconnu)", run_id)
```

(Seuls changements réels : `tracker = PostgresRunTracker(...)` ajouté en
tête ; `pipelines_repo.mark_running(session, run_id=run_id)` retiré du
premier bloc `with`, remplacé par `tracker.mark_running()` juste après ;
les 2 blocs `with request_scoped_session(factory) as session:
pipelines_repo.mark_succeeded(...)` et `mark_failed(...)` × 2 remplacés par
un appel direct `tracker.mark_succeeded(...)`/`tracker.mark_failed(...)`.
Tout le reste — `_get_pipeline_payload`, `_acting_user`, `run_pipeline(...)`,
`_notify(...)`, les 2 branches `except`, les logs — est identique caractère
pour caractère à l'original.)

- [ ] **Step 2: Vérifier que la suite `test_pipeline_jobs.py` reste verte**

Run: `cd core && uv run pytest tests/test_pipeline_jobs.py -q`
Expected: PASS (tous les tests déjà existants — `marks_run_succeeded`,
`marks_run_failed_never_zombie`, `writes_a_notification_for_the_item_owner`,
`writes_a_notification` (échec), `notification_write_failure_does_not_affect_run_status`,
`early_failure_before_item_id_bound_does_not_crash`,
`writes_node_stats_incrementally_before_failure`,
`marks_run_failed_on_unexpected_exception_never_zombie`,
`refuses_writer_dataset_without_data_manage`). Si ces tests skippent
silencieusement faute de `CORE_TEST_DATABASE_URL` (marqueur `postgis` de
module), le signaler explicitement dans le rapport de tâche (piège CLAUDE.md
#3/#12) plutôt que de conclure "vert" sans réserve — dans ce cas, relancer
avec un `CORE_TEST_DATABASE_URL` valide avant de committer si l'environnement
le permet.

- [ ] **Step 3: Suite `PostgresRunTracker` (non-régression croisée)**

Run: `cd core && uv run pytest tests/test_pipeline_run_tracker.py -q`
Expected: PASS (3 tests, déjà vérifiés en Task 1, revérifiés ici après le
seul appelant de production).

- [ ] **Step 4: Commit**

```bash
cd core
git add app/pipelines/jobs.py
git commit -m "$(cat <<'EOF'
refactor(core): run_pipeline_task utilise PostgresRunTracker

Les 3 appels pipelines_repo.mark_running/mark_succeeded/mark_failed inline
sont remplacés par le RunTracker introduit à l'étape précédente. Comportement
observable inchangé (mêmes lignes pipeline_runs écrites, même séquence
running -> succeeded/failed, mêmes notifications) — seule différence interne
acceptée : mark_running ouvre désormais sa propre transaction courte au lieu
de partager celle de get_run (deux commits au lieu d'un, même état final).
Clôt la tranche "seam RunTracker" du socle sidecar desktop-etl (design
2026-09-17 §4) — comportement observable strictement inchangé côté route
REST/MCP/UI.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3 : suite complète du module pipelines + couverture

**Files:**
- None créé/modifié — vérification uniquement.

- [ ] **Step 1: Suite pipelines complète**

Run: `cd core && uv run pytest tests/test_pipeline_run_tracker.py tests/test_pipeline_jobs.py tests/test_pipeline_connector_runtime.py tests/test_pipeline_runtime.py tests/test_pipeline_routes.py tests/test_pipeline_registries.py -q`

(Adapter la liste aux fichiers de test réellement présents sous
`core/tests/` si les noms diffèrent légèrement — lister d'abord avec
`ls core/tests/ | grep pipeline` si un des noms ci-dessus n'existe pas.)

Expected: PASS. Si des tests `postgis`/`pg_engine` skippent faute de
`CORE_TEST_DATABASE_URL`, le signaler explicitement (piège CLAUDE.md #3)
plutôt que de conclure "entièrement vert" sans réserve.

- [ ] **Step 2: Suite complète du cœur + seuil de couverture**

Run: `cd core && uv run pytest -q`
Run: `cd core && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold`
Expected: 0 échec, couverture ≥ seuil (85, cf. CLAUDE.md § Commandes).

- [ ] **Step 3: Portes de qualité statique**

Run:
```bash
cd core
uv run ruff check .
uv run ruff format --check .
uv run lint-imports
```
Expected: aucune violation (aucun nouveau chemin d'import inter-module créé
par ce plan — `jobs.py` avait déjà tous les imports utilisés).

- [ ] **Step 4: Rapport de fin de plan**

Pas de commit de code à cette étape (vérification seule). Si tout est vert,
passer à `superpowers:requesting-code-review` avant de considérer cette
tranche du chantier desktop-etl terminée, conformément à CLAUDE.md
(« une revue par tâche et une revue finale de branche »).

---

## Ce que ce plan ne couvre pas (volontairement)

- **API loopback HTTP du sidecar** (`GET /ops`, `POST /pipelines/validate`,
  `POST /pipelines/run`, `POST /pipelines/preview`), le framework HTTP à
  choisir, la forme SSE de la progression, et la négociation du port
  éphémère (design §2) — sous-chantier distinct, toujours pas assez
  spécifié pour être planifié avec du code exact. À reprendre avec
  `superpowers:brainstorming` puis `superpowers:writing-plans` une fois
  cette tranche mergée.
- **Implémentation en mémoire de `RunTracker`** côté desktop — seam sans
  deuxième implémentation pour l'instant (même précédent que
  `SecretResolver`/`PostgresSecretResolver`, tranche 1). N'existe qu'une
  fois le sidecar desktop lui-même en cours de construction.
- **`reader.file`/`writer.file` côté cœur** (design §3) — dépend d'abord du
  spike 02 DuckDB spatial en binaire gelé, jamais fait (cf.
  [`docs/superpowers/specs/2026-09-17-desktop-etl-spike-01-findings.md`](../specs/2026-09-17-desktop-etl-spike-01-findings.md)).
  `session: Session` continue de traverser `run_pipeline()`/le registre
  `READERS` sans changement dans cette tranche — le rendre optionnel pour
  un contexte sans Postgres est le travail de ce sous-chantier, pas de
  celui-ci.
- **Dossier `desktop-etl/` (Tauri, canvas React, packaging)** — non créé
  par ce plan.

Plan complet et sauvegardé dans
`docs/superpowers/plans/2026-09-18-desktop-etl-run-tracker-seam.md`.
