# SP-49 — Fiabilité des jobs & cohérence des migrations : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer 4 gaps « Sérieux » de la revue SP-42, explicitement laissés
hors périmètre de SP-43 (§7 de sa spec) : GAP-63 (`downgrade()` de la
migration 0024 cassé sur base non vide, `alert_evaluations`/`pipeline_runs`
sans aucun index), GAP-64 (N+1 sur les 3 balayages cron pipelines/alertes/
rapports et sur `GET /harvest/layers`/`/feature-layers`), GAP-56+GAP-76
(reprise de jobs incomplète sur export/appexport/ingestion, healthchecks qui
ne détectent qu'un process mort). Aucune nouvelle fonctionnalité — fiabilité
et performance de mécanismes déjà livrés.

**Architecture:** 7 tâches, dans l'ordre du moins au plus risqué (§4 de la
spec) : migrations (Tâche 1-2) → N+1 cron (Tâche 3) → N+1 harvest (Tâche 4)
→ try/except export/appexport (Tâche 5) → reprise appexport/ingestion
(Tâche 6) → healthchecks + doc opérationnelle (Tâche 7). Les Tâches 6 et 3
construisent explicitement sur `core/app/jobs/common.py` (déjà livré par
SP-43) — ne pas recréer de copie locale de `session_factory()`/
`notify_best_effort()`.

**Tech Stack:** Python/FastAPI + SQLAlchemy + Alembic + pytest + procrastinate
3.9.0 (verrouillé, `core/uv.lock`).

**Document source :**
`docs/superpowers/specs/2026-09-05-sp49-fiabilite-jobs-design.md` (sections
citées : §0 état vérifié, §1 GAP-63, §2 GAP-64, §3 GAP-56+GAP-76, §4 ordre,
§5 hors périmètre, §6 risques).

## Global Constraints

- **TDD / filet-avant-code** : chaque tâche pose ou vérifie son filet de
  test **avant** de toucher le code de production qu'elle protège.
- Commits **conventional**, un sujet par commit, français dans les messages
  (`fix(core): ...`, `refactor(core): ...`, `test(core): ...`,
  `feat(core): ...`, `chore(deploy): ...`).
- **Suite complète rejouée avant de clore chaque tâche** — jamais un
  sous-ensemble (piège CLAUDE.md n°6) : `cd core && uv run pytest`. Les
  tâches qui touchent des routes observables (Tâche 4) rejouent aussi
  `cd shell && npm run e2e` si un mock e2e dépend de la forme de réponse
  concernée (à vérifier — les routes touchées ici n'ont probablement aucun
  mock e2e dédié, mais vérifier plutôt que supposer).
- **Toute migration testée sur base non vide, dans les deux sens** (piège
  CLAUDE.md n°8) : upgrade → insérer des lignes qui exercent le cas limite
  → downgrade → (ré-upgrade si pertinent), sur une base Postgres jetable,
  jamais sur le conteneur `postgis-test` partagé pour cette vérification
  précise.
- **Tout filet de test ajouté doit être vérifié par falsification** (piège
  CLAUDE.md n°10) : injecter délibérément le défaut visé, confirmer que le
  test échoue, puis retirer l'injection.
- **Conteneur `postgis-test` non tracké par Alembic** : après la Tâche 2
  (nouvelle migration `0035`), un `ALTER TABLE` manuel peut être nécessaire
  sur ce conteneur avant de rejouer la suite contre lui (CLAUDE.md, suivi
  récurrent) — ou utiliser une base jetable dédiée comme le fait déjà
  `test_model_alembic_parity.py`.
- **Régénérer la spec OpenAPI + types TS** uniquement si une route ou un
  modèle de réponse HTTP change (piège CLAUDE.md n°1). Attendu : diff
  **vide** pour toutes les tâches de ce plan sauf vérification explicite en
  Tâche 4 (les réponses JSON de `/harvest/layers`/`/feature-layers` ne
  changent pas de forme, seulement de mécanisme interne — mais vérifier
  quand même, ne pas supposer).
- **Ne jamais deviner une interface tierce** (piège CLAUDE.md n°3) : chaque
  tâche qui s'appuie sur une API non triviale (procrastinate `JobManager`,
  SQLite window functions) commence par une étape de vérification explicite
  contre le code réellement installé, pas contre la documentation ou la
  mémoire.
- **Hors périmètre explicite** (spec §5), à ne pas toucher dans ce plan :
  pagination complète de GAP-57, N+1 de `configs_repo.list_configs_by_kind`
  sur `_latest_revision`, fragilité de révision relative dans
  `test_metadata_migration_alembic.py`, migration vers l'API heartbeat pure
  de procrastinate pour une future version majeure.

---

## Task 1 (GAP-63.1) : `downgrade()` de la migration 0024

Corrige le seul défaut de migration qui casse réellement sur une base non
vide. Risque bas : une seule fonction modifiée, aucune donnée touchée par
la modification elle-même (le no-op ne fait rien, l'ancien comportement
faisait échouer l'opération).

**Files:**
- Modify: `core/alembic/versions/0024_report_runs_nullable_export_job.py`
- Create/Modify: `core/tests/test_migration_0024_downgrade.py` (nom exact à
  choisir en cohérence avec la convention du dépôt — vérifier s'il existe
  déjà un fichier `test_report_runs_migration*.py` avant d'en créer un
  nouveau)

**Interfaces:**
- Consumes : patron de fixture `throwaway_database_url` de
  `core/tests/test_model_alembic_parity.py`/`test_metadata_migration_alembic.py`
  (base Postgres jetable, `Config()` sans fichier ini, positionner
  `DATABASE_URL` en variable d'environnement — `core/alembic/env.py` la lit
  inconditionnellement).
- Produces : rien de nouveau consommé ailleurs — cette migration ne change
  qu'un comportement de `downgrade()`.

- [ ] **Step 1 : vérifier qu'aucun test de migration 0024 n'existe déjà**

```bash
grep -rln "0024" core/tests/*.py
```

Si un test existe déjà et couvre ce cas, l'étendre plutôt que d'en créer un
nouveau — ne pas dupliquer.

- [ ] **Step 2 : écrire le test qui reproduit le défaut AVANT de corriger**

Sur une base jetable (patron `throwaway_database_url`), migrer jusqu'à
`head` (ou au moins jusqu'à une révision après `0024`), insérer une ligne
`report_runs` avec `export_job_id IS NULL` (situation normale de
production, cf. §1.1 de la spec — pas un cas artificiel), puis appeler
`command.downgrade(cfg, "0023")`. **Avant la correction de la Step 3,
cette assertion doit échouer** (le `ALTER TABLE ... SET NOT NULL` lève
`NotNullViolation`) — le confirmer explicitement en exécutant le test AVANT
de toucher la migration (piège CLAUDE.md n°10 : falsifier le filet).

```python
def test_downgrade_0024_succeeds_with_existing_null_export_job_id(throwaway_database_url):
    # migrer jusqu'à head (ou jusqu'à une révision postérieure à 0024)
    # INSERT INTO report_runs (..., export_job_id) VALUES (..., NULL)
    # command.downgrade(cfg, "0023") ne doit PAS lever d'exception
    ...
```

- [ ] **Step 3 : corriger `downgrade()`**

Remplacer le corps de `downgrade()` par un no-op documenté — **ne pas
supprimer la fonction elle-même** (Alembic exige que chaque révision ait
les deux fonctions définies) :

```python
def downgrade() -> None:
    """Ce relâchement de contrainte est permanent par construction : une
    ligne report_runs avec export_job_id NULL marque un déclenchement de
    rapport en échec (propriétaire ayant perdu l'accès, capacité export
    coupée) et n'a par nature aucun export_jobs valide derrière elle — cf.
    app/reports/models.py, commentaire du champ. Aucune valeur ne permet de
    revalider honnêtement la contrainte NOT NULL sans invention de donnée.
    Restaurer l'ancienne contrainte casserait donc `downgrade()` sur toute
    base ayant ne serait-ce qu'une ligne de ce type (situation normale de
    fonctionnement, pas un cas limite) — documenté depuis 2026-08-22
    (migration 0028), corrigé par SP-49 : ce no-op est une décision assumée,
    pas un oubli. Voir docs/superpowers/specs/2026-09-05-sp49-fiabilite-jobs-design.md §1.1.
    """
```

- [ ] **Step 4 : rejouer le test de la Step 2, vérifier qu'il passe désormais**

- [ ] **Step 5 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 6 : commit**

`fix(core): downgrade de la migration 0024 ne retend plus une contrainte irrécupérable`

---

## Task 2 (GAP-63.2) : index manquants sur `alert_evaluations`/`pipeline_runs`

**Files:**
- Create: `core/alembic/versions/0035_alert_pipeline_run_indexes.py`
- Modify: `core/app/alerts/models.py`, `core/app/pipelines/models.py`
- Modify/Create: test dédié (vérifier s'il existe un
  `test_alert_repository.py`/`test_pipeline_repository.py` où ajouter une
  assertion d'index plutôt que créer un fichier séparé)

**Interfaces:**
- Consumes : `core/tests/test_model_alembic_parity.py` (doit rester vert
  après cette tâche — c'est l'oracle principal de parité modèle/migration).
- Produces : rien de nouveau consommé par du code applicatif — l'index est
  transparent pour les requêtes existantes (elles continuent de s'exécuter
  identiquement, seulement plus vite).

- [ ] **Step 1 : confirmer la tête de migration actuelle**

```bash
ls core/alembic/versions/ | sort | tail -3
```

Attendu : `0034_attachments_cascade_delete.py` en tête — la nouvelle
migration est `0035`, `down_revision = "0034"`. **Vérifier ce chiffre au
moment d'exécuter cette tâche** : une session concurrente peut avoir ajouté
une migration entretemps (piège concurrence, cf. CLAUDE.md).

- [ ] **Step 2 : écrire la migration**

```python
# core/alembic/versions/0035_alert_pipeline_run_indexes.py
"""app.alerts/app.pipelines — index manquants sur alert_evaluations/
pipeline_runs (GAP-63, SP-49)

Les deux tables sont interrogées par (tenant_id, <item>_id) puis triées par
created_at DESC à chaque tick de balayage cron (5 minutes) depuis leur
création (migrations 0018/0020) sans qu'aucun index ne le supporte — scan
séquentiel complet à chaque appel de get_latest_run/get_latest_evaluation.

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-05
"""
import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_pipeline_runs_pipeline",
        "pipeline_runs",
        ["tenant_id", "pipeline_item_id", "created_at"],
    )
    op.create_index(
        "ix_alert_evaluations_rule",
        "alert_evaluations",
        ["tenant_id", "alert_rule_item_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_evaluations_rule", table_name="alert_evaluations")
    op.drop_index("ix_pipeline_runs_pipeline", table_name="pipeline_runs")
```

- [ ] **Step 3 : ajouter les `Index` côté modèle (parité, requis par
  `test_model_alembic_parity.py`)**

```python
# app/pipelines/models.py
from sqlalchemy import Index  # ajouter à l'import existant

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        Index("ix_pipeline_runs_pipeline", "tenant_id", "pipeline_item_id", "created_at"),
    )
    ...
```

```python
# app/alerts/models.py
from sqlalchemy import Index  # ajouter à l'import existant

class AlertEvaluation(Base):
    __tablename__ = "alert_evaluations"
    __table_args__ = (
        Index("ix_alert_evaluations_rule", "tenant_id", "alert_rule_item_id", "created_at"),
    )
    ...
```

- [ ] **Step 4 : falsifier — retirer temporairement un des deux `Index()`
  côté modèle, vérifier que `test_model_alembic_parity.py` échoue, puis le
  remettre**

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -x
```

Sans le retrait temporaire, rien ne prouve que ce filet couvre réellement
ce cas (piège CLAUDE.md n°10) — il pourrait très bien rester vert par
accident (ex. si le filtre `_filter_real_diff` absorbait ce type de diff
par erreur).

- [ ] **Step 5 : test dédié de non-régression fonctionnelle sur base non
  vide, dans les deux sens**

Sur une base jetable : `upgrade head` (ou jusqu'à `0035`), insérer plusieurs
lignes `pipeline_runs`/`alert_evaluations` pour un même
`(tenant_id, item_id)` avec des `created_at` différents (pas nécessairement
dans l'ordre d'insertion — cf. Task 3, ce même jeu de données sert aussi à
falsifier le batching), puis `downgrade` vers `0034`, vérifier que les deux
`op.drop_index` réussissent sans erreur, puis re-`upgrade` vers `0035` et
vérifier que les deux index existent de nouveau
(`sa.inspect(engine).get_indexes("pipeline_runs")`/`"alert_evaluations"`).

- [ ] **Step 6 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 7 : commit**

`feat(core): ajoute les index manquants sur alert_evaluations/pipeline_runs`

---

## Task 3 (GAP-64.1) : batching du « dernier run » dans les 3 balayages cron

**Files:**
- Modify: `core/app/pipelines/repository.py`, `core/app/reports/repository.py`,
  `core/app/alerts/repository.py`
- Test existant à étendre (pas créer de nouveau fichier) :
  `core/tests/test_pipeline_sweep.py`, `core/tests/test_report_sweep.py`,
  `core/tests/test_alert_sweep.py` — plus, si pertinent, les tests
  `test_pipeline_repository.py`/`test_report_repository.py`/
  `test_alert_repository.py` pour tester la fonction batchée isolément.

**Interfaces:**
- Consumes : `configs_repo.list_configs_by_kind` (inchangée — fournit déjà
  la liste `(item_id, tenant_id, config)` en une requête).
- Produces : les nouvelles fonctions `get_latest_runs_for_items`/
  `get_latest_evaluations_for_items` remplacent l'appel en boucle à
  `get_latest_run`/`get_latest_evaluation` dans `list_due_*` — ces
  dernières fonctions restent par ailleurs disponibles pour tout autre
  appelant à un seul item (ex. routes de lecture d'un run isolé), ne pas
  les supprimer.

- [ ] **Step 1 : vérifier le support des fonctions fenêtre par la version
  SQLite utilisée en test**

Ne pas supposer — ces tests tournent contre `sqlite+pysqlite:///:memory:`
(confirmé, `test_pipeline_sweep.py` etc.) :

```bash
cd core && uv run python -c "
import sqlite3
print(sqlite3.sqlite_version)
"
```

`ROW_NUMBER() OVER (...)` nécessite SQLite ≥ 3.25 (2018) — quasi certain
d'être satisfait par toute version bundlée avec Python 3.12+, mais à
confirmer avant d'écrire le code plutôt qu'après un échec de test difficile
à diagnostiquer. Si la version est trop ancienne (improbable), utiliser à
la place une sous-requête `GROUP BY item_id, MAX(created_at)` jointe à la
table (fonctionne sur toute version SQLite, un peu moins direct à écrire).

- [ ] **Step 2 : écrire le test caractéristique AVANT la fonction, sur
  `pipeline_runs` (le domaine le mieux couvert par les tests de repository
  existants)**

```python
def test_get_latest_runs_for_items_returns_the_most_recent_run_per_item():
    # 2 pipelines (item A, item B), item A a 3 runs à des created_at
    # DIFFÉRENTS de l'ordre d'insertion (falsifie un ROW_NUMBER() mal
    # ordonné qui retournerait la dernière ligne insérée plutôt que la plus
    # récente par date) ; item B a 1 seul run.
    # get_latest_runs_for_items(session, tenant_id_by_item={"A": t, "B": t})
    # doit retourner {"A": <le run le plus RÉCENT par created_at>, "B": <son seul run>}
    ...


def test_get_latest_runs_for_items_returns_empty_dict_for_empty_input():
    ...
```

- [ ] **Step 3 : implémenter `get_latest_runs_for_items` dans
  `app/pipelines/repository.py`**

```python
from sqlalchemy import func
from sqlalchemy.orm import aliased

def get_latest_runs_for_items(
    session: Session, *, item_ids: list[str]
) -> dict[str, PipelineRun]:
    """Batch de get_latest_run pour une liste d'item_id — remplace le
    get_latest_run() par itération de list_due_pipelines (GAP-64, SP-49) :
    une seule requête au lieu de N. tenant_id n'est volontairement pas un
    paramètre de filtre ici (contrairement à get_latest_run) : les item_id
    proviennent déjà de list_configs_by_kind (cross-tenant par nature pour
    ce balayage système), le tenant_id de chaque run est lu sur la ligne
    retournée si l'appelant en a besoin."""
    if not item_ids:
        return {}
    rn = func.row_number().over(
        partition_by=PipelineRun.pipeline_item_id,
        order_by=PipelineRun.created_at.desc(),
    ).label("rn")
    subq = select(PipelineRun, rn).where(PipelineRun.pipeline_item_id.in_(item_ids)).subquery()
    pr = aliased(PipelineRun, subq)
    rows = session.execute(select(pr).where(subq.c.rn == 1)).scalars().all()
    return {r.pipeline_item_id: r for r in rows}
```

Reproduire la même fonction dans `app/reports/repository.py`
(`get_latest_runs_for_items`, sur `ReportRun`/`report_item_id`) et
`app/alerts/repository.py` (`get_latest_evaluations_for_items`, sur
`AlertEvaluation`/`alert_rule_item_id`). Trois copies quasi identiques,
volontairement non extraites en une fonction générique transverse (colonne
de partition différente par domaine, coût d'abstraction générique jugé
supérieur au gain pour 3 occurrences seulement — cohérent avec le principe
« pas de généralisation au-delà de ce que permet déjà `app.jobs.common` »
de la spec §2.1).

- [ ] **Step 4 : falsifier — construire délibérément un test où l'ordre
  d'insertion diffère de l'ordre chronologique attendu, confirmer que la
  Step 2 (avant Step 3) échoue effectivement sur une implémentation naïve
  (ex. un simple `.first()` sans `ORDER BY`), puis confirmer qu'elle passe
  avec l'implémentation réelle**

- [ ] **Step 5 : brancher dans `list_due_pipelines`/`list_due_reports`/
  `list_due_rules`**

```python
def list_due_pipelines(session: Session) -> list[tuple[str, str]]:
    now = datetime.now(UTC)
    due: list[tuple[str, str]] = []
    candidates = [
        (item_id, tenant_id, config)
        for item_id, tenant_id, config in configs_repo.list_configs_by_kind(session, kind="pipeline")
        if config.pipeline is not None
        and config.pipeline.refreshPolicy is not None
        and config.pipeline.refreshPolicy.enabled
    ]
    latest_by_item = get_latest_runs_for_items(session, item_ids=[c[0] for c in candidates])
    for item_id, tenant_id, config in candidates:
        latest = latest_by_item.get(item_id)
        # ... reste de la logique de décision (cron, reclaim par âge) INCHANGÉ,
        # seule la ligne `latest = get_latest_run(...)` disparaît, remplacée
        # par la consultation du dict ci-dessus.
    return due
```

Attention : le filtre `payload = config.pipeline; if payload is None:
continue` existant doit être reproduit **avant** de construire
`candidates` (ne pas envoyer à `get_latest_runs_for_items` des item_id dont
le payload est invalide — inoffensif niveau correction mais inutilement
large). Reproduire la même restructuration pour `list_due_reports`
(`config.report`) et `list_due_rules` (`config.alert`) — chacune garde sa
propre logique de décision (cron simple pour reports, reclaim par âge à
seuil différent pour pipelines `_RUNNING_RECLAIM_MINUTES=60`/alerts
`_PENDING_RECLAIM_MINUTES=60`), seul le point d'accès au dernier run/
évaluation change.

- [ ] **Step 6 : suite complète des 3 domaines + suite complète du dépôt**

```bash
cd core && uv run pytest tests/test_pipeline_sweep.py tests/test_report_sweep.py tests/test_alert_sweep.py tests/test_pipeline_repository.py tests/test_report_repository.py tests/test_alert_repository.py -v
cd core && uv run pytest
```

- [ ] **Step 7 : commit**

`fix(core): balayages pipelines/rapports/alertes — une requête pour le dernier run au lieu d'une par objet`

---

## Task 4 (GAP-64.2) : N+1 sur `GET /harvest/layers`/`/feature-layers`

**Files:**
- Modify: `core/app/items/repository.py` (nouvelle fonction batchée),
  `core/app/harvest/routes.py`
- Test existant à étendre : chercher le fichier de test des routes harvest
  exact avant de commencer (`grep -rl "list_layers\|feature-layers"
  core/tests/*.py`) — ne pas supposer son nom.

**Interfaces:**
- Consumes : `app.sharing.authorization.decide` (fonction pure, déjà
  utilisée par `app/items/repository.py::_permissions`/`_permissions_by_id`
  — même patron à répliquer ici, pas une nouvelle règle d'autorisation),
  `roles_for_items` (déjà batchée par construction, accepte une liste
  d'`item_ids`).
- Produces : aucun changement de forme de réponse HTTP — vérifier
  explicitement après coup (diff OpenAPI attendu vide, cf. contraintes
  globales).

- [ ] **Step 1 : localiser le test de routes harvest existant**

```bash
grep -rl "list_layers\|/harvest/layers\|/harvest/feature-layers" core/tests/*.py
```

- [ ] **Step 2 : lire `_permissions_by_id` (`app/items/repository.py`)
  comme patron de référence avant d'écrire quoi que ce soit**

```bash
sed -n '/def _permissions_by_id/,/^def /p' core/app/items/repository.py
```

Reproduire la même discipline : un seul appel `roles_for_items` pour tous
les ids restants après filtrage owner/public, puis `decide()` (pure, sans
I/O) par ligne.

- [ ] **Step 3 : écrire le test qui prouve le nombre de requêtes AVANT de
  corriger (falsification piège n°10)**

Utiliser le compteur de requêtes déjà présent dans le dépôt si un tel
utilitaire existe (chercher `query_count`/`statement_count`/
`event.listen(engine, "before_cursor_execute"...)` dans
`core/tests/conftest.py` avant d'en écrire un nouveau) ; sinon un compteur
minimal local au test. Construire 5 layers pour le même utilisateur,
confirmer qu'aujourd'hui l'appel à `list_layers` déclenche bien plus de
2 requêtes DB pour ce jeu de données (borne haute exacte à mesurer, pas à
deviner), puis, après correction, confirmer que le nombre de requêtes ne
croît plus avec le nombre de lignes (constant, indépendant de N).

- [ ] **Step 4 : ajouter la fonction batchée dans `app/items/repository.py`**

```python
def get_access_facts_by_ids(
    session: Session, *, tenant_id: str, item_ids: list[str]
) -> dict[str, ItemAccessFacts]:
    """Batch de get_access_facts pour une liste d'item_id — remplace l'appel
    par ligne dans GET /harvest/layers|feature-layers (GAP-64, SP-49), même
    discipline que _permissions_by_id pour roles_for_items."""
    if not item_ids:
        return {}
    rows = session.execute(
        select(Item.id, Item.tenant_id, Item.owner_id, Item.is_public, Item.is_published).where(
            Item.tenant_id == tenant_id, Item.id.in_(item_ids)
        )
    ).all()
    return {
        row.id: ItemAccessFacts(
            id=row.id, tenant_id=row.tenant_id, owner_id=row.owner_id,
            is_public=row.is_public, is_published=row.is_published,
        )
        for row in rows
    }
```

- [ ] **Step 5 : réécrire `list_layers`/`list_feature_layers`**

```python
@router.get("/harvest/layers")
def list_layers(q: str | None = None, user: User = Depends(get_current_user), session=Depends(get_session)):
    rows = repo.list_layer_records(session, tenant_id=user.tenant_id, q=q, limit=_HARVEST_LIST_LIMIT)
    facts_by_id = items_repo.get_access_facts_by_ids(
        session, tenant_id=user.tenant_id, item_ids=[r[0] for r in rows]
    )
    remaining_ids = [
        item_id for item_id, facts in facts_by_id.items()
        if not (facts.owner_id == user.id or facts.is_public or facts.is_published)
    ]
    roles_by_id = roles_for_items(session, tenant_id=user.tenant_id, user_id=user.id, item_ids=remaining_ids)
    layers = []
    for item_id, title, tiles_url, _layer_kind in rows:
        facts = facts_by_id.get(item_id)
        if facts is None:
            continue
        allowed = decide(
            action="read", kind="item",
            is_owner=facts.owner_id == user.id, is_public=facts.is_public, is_published=facts.is_published,
            roles=roles_by_id.get(item_id, frozenset()), actor_is_admin=False,
        )
        if not allowed:
            continue
        layers.append({"id": item_id, "title": title, "kind": "raster", "tilesUrl": tiles_url})
    return {"layers": layers}
```

Répliquer la même restructuration pour `list_feature_layers`. **Vérifier le
court-circuit `decide()` exact** (relire `app/sharing/authorization.py:30-59`
avant d'écrire — le comportement précis pour `kind="collection"`+admin ne
s'applique pas ici, ces routes portent sur des `items`) pour ne pas
introduire une régression d'autorisation en même temps que la correction de
performance (piège CLAUDE.md n°11 : suivre le chemin d'exécution réel, pas
le vocabulaire).

- [ ] **Step 6 : ajouter un plafond `limit` sur `list_layer_records`/
  `list_feature_layer_records` (`app/harvest/repository.py`)**

Vérifier d'abord la valeur de plafond déjà utilisée par une liste comparable
du dépôt avant de choisir un chiffre (`grep -rn "LIMIT\|\.limit(" core/app/*/repository.py`
pour trouver un précédent — ne pas inventer une constante isolée).

- [ ] **Step 7 : suite complète + vérification OpenAPI**

```bash
cd core && uv run pytest
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
git diff --stat core/openapi.json  # attendu : vide
```

- [ ] **Step 8 : commit**

`fix(core): GET /harvest/layers|feature-layers — accès et rôles vérifiés en lot au lieu d'un par ligne`

---

## Task 5 (GAP-56.1) : `get_job`+`mark_running` dans le bloc `try` (export/appexport)

**Files:**
- Modify: `core/app/export/jobs.py`, `core/app/appexport/jobs.py`
- Test existant à étendre : `core/tests/test_export_jobs.py`,
  `core/tests/test_appexport_jobs.py`

**Interfaces:**
- Consumes : patron déjà écrit dans `app/pipelines/jobs.py::run_pipeline_task`
  et `app/ingestion/tasks.py::run_ingestion_task` (variable de destinataire
  pré-liée à `None` avant `try:`, `get_job`+`mark_running` à l'intérieur).
- Produces : aucun changement de comportement pour le chemin nominal — seul
  un échec de `get_job`/`mark_running` change de traitement (désormais
  capturé au lieu de remonter non géré).

- [ ] **Step 1 : relire le patron exact des deux fichiers de référence**

```bash
sed -n '140,165p' core/app/pipelines/jobs.py
sed -n '60,95p' core/app/ingestion/tasks.py
```

- [ ] **Step 2 : écrire le test qui prouve le défaut actuel AVANT de
  corriger — monkeypatcher `export_repo.get_job` pour lever une exception,
  confirmer qu'aujourd'hui elle remonte non gérée jusqu'à l'appelant du
  test (pas de marquage d'erreur, pas de notification) — falsification du
  filet (piège n°10)**

```python
def test_render_export_task_handles_get_job_failure_gracefully(monkeypatch):
    # monkeypatch export_repo.get_job pour lever RuntimeError("db down")
    # AVANT correction : render_export_task(job_id, tenant_id) laisse
    # l'exception se propager (le test échoue si on s'attend à ce qu'elle
    # soit absorbée) — documenter ce constat par une assertion qui capture
    # explicitement pytest.raises AVANT la correction, ou le confirmer
    # manuellement puis écrire directement le test de l'état corrigé.
    ...
```

- [ ] **Step 3 : réécrire `render_export_task`**

```python
@app.task(queue="export")
def render_export_task(job_id: str, tenant_id: str) -> None:
    factory = session_factory()
    if not is_export_enabled():
        with request_scoped_session(factory) as session:
            export_repo.mark_error(session, job_id=job_id, error="export capability disabled")
        return

    item_id: str | None = None
    user_id: str | None = None
    export_format: str | None = None
    page_id = None
    ctx = None

    try:
        with request_scoped_session(factory) as session:
            job = export_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
            if job is None:
                logger.error("export job %s introuvable (tenant %s)", job_id, tenant_id)
                return
            export_repo.mark_running(session, job_id=job_id)
            item_id, user_id, export_format = job.item_id, job.user_id, job.format
            page_id, ctx = job.page_id, job.ctx

        # ... reste du corps de la fonction, inchangé, maintenant à
        # l'intérieur du même bloc try
    except Exception as exc:
        # ... traitement d'erreur existant, réutilisé tel quel
```

Vérifier attentivement où se trouvait déjà la fin du `try`/le début du
`except` avant cette modification — ne déplacer QUE les deux lignes
`get_job`/`mark_running` et l'affectation des variables locales à
l'intérieur du bloc existant, ne pas réécrire toute la fonction de zéro
(risque de régression sur le reste du corps, déjà correct). Reproduire la
même restructuration minimale pour `build_app_export_task`
(`app/appexport/jobs.py`).

- [ ] **Step 4 : rejouer le test de la Step 2, confirmer qu'il passe
  désormais (l'exception est absorbée par le `except` existant, un
  marquage d'erreur a lieu)**

- [ ] **Step 5 : suite complète**

```bash
cd core && uv run pytest tests/test_export_jobs.py tests/test_appexport_jobs.py -v
cd core && uv run pytest
```

- [ ] **Step 6 : commit**

`fix(core): export/appexport — get_job+mark_running dans le bloc try, comme pipelines/ingestion`

---

## Task 6 (GAP-56.2/56.3) : reprise appexport + ingestion, sur `app.jobs.common`

**Files:**
- Modify: `core/app/appexport/jobs.py` (nouvelle tâche périodique)
- Modify: `core/app/ingestion/repository.py` (nouvelle fonction
  `reclaim_stuck_jobs`), `core/app/ingestion/tasks.py` (nouvelle tâche
  périodique)
- Test existant à étendre : `core/tests/test_appexport_jobs.py`,
  `core/tests/test_appexport_repository.py`, `core/tests/test_ingestion_repository.py`,
  `core/tests/test_ingestion_tasks.py`

**Interfaces:**
- Consumes : `core/app/jobs/common.py::session_factory`/`notify_best_effort`
  (déjà importées par `app/ingestion/tasks.py` — réutiliser le `_notify()`
  local déjà présent, ne pas en écrire un second) ; le contrat de
  `export_repo.reclaim_stuck_jobs` (`app/export/repository.py:89`) comme
  patron exact pour la nouvelle fonction ingestion.
- Produces : `sweep_appexport_jobs_task`, `sweep_ingestion_jobs_task` —
  deux nouvelles tâches `@app.periodic`, à ajouter à `import_paths` de
  `app/jobs/__init__.py` **seulement si elles ne le sont pas déjà** (les
  deux modules `app.appexport.jobs`/`app.ingestion.tasks` y figurent déjà —
  vérifier avant de dupliquer l'entrée).

- [ ] **Step 1 : vérifier la signature exacte de `mark_error` dans
  `app/ingestion/repository.py` avant d'écrire `reclaim_stuck_jobs`**

```bash
grep -n "def mark_error" -A 8 core/app/ingestion/repository.py
```

- [ ] **Step 2 : test AVANT code pour `reclaim_stuck_jobs` (ingestion)**

Copier la structure de
`tests/test_export_repository.py::test_reclaim_stuck_jobs_marks_old_running_jobs_as_error`
et sa sœur `test_reclaim_stuck_jobs_leaves_recent_running_jobs_alone`,
transposées sur `IngestionJob`/`ingestion_repo`.

- [ ] **Step 3 : implémenter `reclaim_stuck_jobs` dans
  `app/ingestion/repository.py`**

```python
_RUNNING_RECLAIM_MINUTES = 60  # même seuil que pipelines/alerts (cohérence
                                # transverse déjà établie dans ce dépôt pour
                                # cette notion de "probablement planté")

def reclaim_stuck_jobs(session: Session, *, older_than_minutes: int = _RUNNING_RECLAIM_MINUTES) -> list[str]:
    threshold = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    rows = session.execute(select(IngestionJob).where(IngestionJob.status == "running")).scalars().all()
    reclaimed: list[str] = []
    for job in rows:
        started_at = job.started_at  # vérifier que ce champ existe — IngestionJob
                                       # a-t-il un started_at ? Vérifier le modèle
                                       # avant d'écrire cette ligne, ne pas supposer
                                       # qu'il est symétrique à AppExportJob/ExportJob.
        ...
    return reclaimed
```

**Point à vérifier avant d'écrire ce code** : `IngestionJob` a-t-il un champ
`started_at` (posé par `mark_running`) comme `ExportJob`/`AppExportJob` ? Si
absent, il faut soit l'ajouter (nouvelle migration, colonne nullable, coût
supplémentaire non anticipé par cette tâche — à signaler avant de
continuer si c'est le cas), soit ancrer la réclamation sur un autre champ
disponible. **Vérifier `app/ingestion/models.py` en premier — ne pas
supposer.**

- [ ] **Step 4 : test AVANT code pour la tâche périodique ingestion**

Sur le patron de `test_pipeline_sweep.py` (sweep pur SQLite, `defer`
monkeypatché n'est pas pertinent ici puisque le reclaim ne défère rien de
nouveau — seulement un changement de statut + notification best-effort).

- [ ] **Step 5 : ajouter `sweep_ingestion_jobs_task` dans
  `app/ingestion/tasks.py`**

```python
@app.periodic(cron="*/15 * * * *")
@app.task(queue="ingestion")
def sweep_ingestion_jobs_task(timestamp: int) -> None:
    factory = session_factory()  # app.jobs.common, déjà importé dans ce fichier
    with request_scoped_session(factory) as session:
        reclaimed = ingestion_repo.reclaim_stuck_jobs(session)
        jobs_for_notify = [...]  # récupérer created_by/collection_title AVANT de sortir
                                  # du bloc de session, comme le fait déjà run_ingestion_task
        session.commit()
    for job in jobs_for_notify:
        _notify(  # le _notify() LOCAL déjà présent dans ce fichier, pas un nouveau
            factory=factory, created_by=job.created_by, collection_title=job.collection_title,
            status="error", error="ingestion timed out (worker crashed or hung)",
        )
```

Vérifier la signature exacte réelle du décorateur `@app.periodic` utilisé
par les 5 tâches existantes (`grep -n "@app.periodic" -A2 core/app/*/jobs.py`)
avant d'écrire cette ébauche — le paramètre `timestamp` et l'ordre des
décorateurs (`@app.periodic` puis `@app.task`, ou l'inverse) doivent
reproduire exactement ce que font les 5 tâches déjà existantes, ne pas
deviner.

- [ ] **Step 6 : ajouter `sweep_appexport_jobs_task` dans
  `app/appexport/jobs.py`** (plus simple — appelle uniquement
  `appexport_repo.reclaim_stuck_jobs(session)`, pas de notification prévue
  par le contrat existant de cette fonction, à moins de décider d'en
  ajouter une par cohérence — **décision à trancher explicitement pendant
  l'exécution de cette tâche, pas implicitement** : le comportement actuel
  de `export_repo.reclaim_stuck_jobs` via le sweep de rapports ne notifie
  pas non plus, donc rester symétrique par défaut est le choix le moins
  risqué)

```python
@app.periodic(cron="*/5 * * * *")
@app.task(queue="appexport")
def sweep_appexport_jobs_task(timestamp: int) -> None:
    factory = _session_factory()
    with request_scoped_session(factory) as session:
        appexport_repo.reclaim_stuck_jobs(session)
        session.commit()
```

- [ ] **Step 7 : corriger le docstring périmé dans
  `test_export_repository.py`** (coût nul, signalé par la spec §3.2 —
  supprimer la mention « pas d'appelant périodique encore câblé (TODO dans
  app/export/jobs.py) », stale depuis SP-17b)

- [ ] **Step 8 : vérifier `app/jobs/__init__.py::import_paths` —
  `app.appexport.jobs`/`app.ingestion.tasks` y figurent déjà (confirmé),
  aucune modification attendue ici, mais vérifier explicitement que les
  nouvelles fonctions `@app.periodic` sont bien importées transitivement
  (elles le sont, mêmes modules) avant de clore cette tâche**

```bash
cd core && uv run pytest tests/test_jobs.py -k import_paths
```

- [ ] **Step 9 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 10 : commit**

`feat(core): reprise périodique des jobs appexport/ingestion bloqués, sur app.jobs.common`

---

## Task 7 (GAP-76) : healthchecks stalled + doc opérationnelle

**Files:**
- Create: `core/scripts/healthcheck_worker_stalled.py`
- Modify: `docker-compose.yml` (healthcheck sur `worker`, `export-worker`),
  possiblement `deploy/qgis-worker/` (healthcheck de process a minima)
- Modify: `README.md` ou `docs/runbooks/2026-07-24-restauration-sauvegardes.md`
  (rappel `GRAFANA_ALERT_WEBHOOK_URL` avant mise en production — un
  paragraphe, pas une nouvelle page)

**Interfaces:**
- Consumes : `app.jobs.app` (l'App procrastinate partagée,
  `core/app/jobs/__init__.py`), `procrastinate.JobManager.get_stalled_jobs`
  (API publique de la version verrouillée 3.9.0).
- Produces : rien de consommé par du code applicatif — un script
  d'exploitation, invoqué uniquement par Docker (`healthcheck.test`).

- [ ] **Step 1 : confirmer la convention d'appel synchrone exacte de
  `JobManager.get_stalled_jobs` sur la version installée (3.9.0) —
  NE PAS SUPPOSER, cette recherche a laissé le point ouvert explicitement**

```bash
cd core && uv run python -c "
import inspect
import procrastinate
print(inspect.signature(procrastinate.manager.JobManager.get_stalled_jobs))
print(inspect.iscoroutinefunction(procrastinate.manager.JobManager.get_stalled_jobs))
"
```

Si la méthode est bien une coroutine sans variante sync exposée sur
`JobManager`, écrire le script autour de `app.open_async()`/
`asyncio.run(...)` :

```python
async def _run(threshold_seconds: int, queue: str | None) -> list:
    async with app.open_async():
        return list(await app.job_manager.get_stalled_jobs(nb_seconds=threshold_seconds, queue=queue))
```

Si une variante sync existe (vérifier aussi
`procrastinate.testing`/`procrastinate.contrib` pour un éventuel wrapper
déjà fourni par la bibliothèque avant d'en écrire un), la préférer — plus
proche du patron `healthcheck_cdc.py` existant (entièrement synchrone).

- [ ] **Step 2 : écrire le script, sur le patron exact de
  `scripts/healthcheck_cdc.py` (sortie 0/1, aucune exception non
  attrapée)**

```python
# core/scripts/healthcheck_worker_stalled.py
"""Sonde de vivacité pour worker/export-worker : détecte un job resté en
'doing' plus longtemps qu'un seuil, contrairement à `procrastinate
healthchecks` (connexion+schéma seulement) — même limite documentée que
pour cdc-worker avant sa propre sonde dédiée (GAP-76, SP-49).

Usage (healthcheck docker) : python -m scripts.healthcheck_worker_stalled
Variables : HEALTHCHECK_STALLED_SECONDS (def. 3600), HEALTHCHECK_QUEUE
(optionnelle, filtre une seule file — utilisée par export-worker)."""
import os
import sys

from app.jobs import app


def main() -> int:
    threshold = int(os.environ.get("HEALTHCHECK_STALLED_SECONDS", "3600"))
    queue = os.environ.get("HEALTHCHECK_QUEUE") or None
    try:
        stalled = ...  # cf. Step 1 — appel sync ou asyncio.run(_run(...))
    except Exception as exc:
        print(f"sonde worker en échec : {exc}", file=sys.stderr)
        return 1
    if stalled:
        print(
            f"{len(stalled)} job(s) bloqué(s) en 'doing' depuis plus de {threshold}s",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3 : test unitaire du script (pas un test d'intégration
  procrastinate complet — monkeypatcher `app.job_manager.get_stalled_jobs`)**

```python
def test_main_returns_1_when_jobs_are_stalled(monkeypatch): ...
def test_main_returns_0_when_no_job_is_stalled(monkeypatch): ...
def test_main_returns_1_and_does_not_raise_on_connection_error(monkeypatch): ...
```

- [ ] **Step 4 : brancher sur `worker` dans `docker-compose.yml`**

Remplacer (ou compléter en deux checks distincts si Docker Compose ne
permet qu'un seul `healthcheck.test` par service — vérifier avant de
choisir : dans ce cas, chaîner les deux commandes dans le même `CMD-SHELL`)
le healthcheck existant :

```yaml
healthcheck:
  test: ["CMD-SHELL", "python -m procrastinate --app app.jobs.app healthchecks && python -m scripts.healthcheck_worker_stalled"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

- [ ] **Step 5 : brancher sur `export-worker` (aucun healthcheck existant
  — en ajouter un, filtré sur la file `export`)**

```yaml
export-worker:
  ...
  environment:
    ...
    HEALTHCHECK_QUEUE: export
  healthcheck:
    test: ["CMD", "python", "-m", "scripts.healthcheck_worker_stalled"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 60s
```

- [ ] **Step 6 : `qgis-worker` — vérifier ce que `server.py` sait répondre
  avant de décider du correctif**

```bash
grep -n "do_GET\|do_POST\|BaseHTTPRequestHandler" -A 10 core/../deploy/qgis-worker/server.py
```

Si une route de vivacité simple existe ou peut être ajoutée à coût
négligeable (`do_GET` répondant 200 sur `/health` sans dépendance QGIS),
l'utiliser pour un `healthcheck.test: curl` classique. Sinon, se limiter à
un healthcheck de process a minima (`pgrep -f server.py`, ou équivalent
compatible avec l'image de base du Dockerfile) — ne pas élargir le
périmètre au sidecar QGIS lui-même (spec SP-43 §5 Étape 9 : composant le
plus risqué du dépôt, prudence déjà actée ailleurs).

- [ ] **Step 7 : renforcer la doc opérationnelle
  `GRAFANA_ALERT_WEBHOOK_URL`**

Un paragraphe dans `README.md` (section déploiement, si elle existe — la
localiser d'abord) ou dans le runbook de restauration existant, listant les
variables à régler avant une mise en production réelle (au minimum
`GRAFANA_ALERT_WEBHOOK_URL`) — ne pas créer un nouveau document séparé pour
une seule ligne.

- [ ] **Step 8 : `docker compose config` — vérifier par valeur (piège
  CLAUDE.md n°2) que les nouveaux healthchecks sont bien dans
  l'`environment:`/`healthcheck:` du bon service, pas seulement documentés**

```bash
docker compose config | grep -A5 "healthcheck" | grep -B2 "healthcheck_worker_stalled"
```

- [ ] **Step 9 : suite complète + `test_deployability.py`**

```bash
cd core && uv run pytest
cd core && uv run pytest tests/test_deployability.py -v
```

- [ ] **Step 10 : commit**

`feat(deploy): healthcheck worker/export-worker détecte un job bloqué, pas seulement un process mort`

---

## Vérification finale de branche (toutes tâches closes)

- [ ] `cd core && uv run pytest` — suite complète, 0 échec.
- [ ] `cd core && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd core && uv run lint-imports`
- [ ] `docker compose config` — healthchecks Task 7 vérifiés par valeur.
- [ ] Relire `docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md`
  (ou son successeur courant) — ajouter l'entrée SP-49 à `CLAUDE.md`
  §Livré, avec mention explicite : GAP-56/63/64/76 clos, ce qui reste
  ouvert (N+1 de `list_configs_by_kind`, pagination GAP-57, montée de
  version procrastinate future).
- [ ] Revue finale de branche distincte de la revue par tâche (piège
  CLAUDE.md n°4) — vérifier en particulier que la Tâche 3 (batching cron)
  et la Tâche 2 (index) sont cohérentes entre elles (l'index créé
  correspond bien aux colonnes réellement utilisées par la requête
  fenêtrée de la Tâche 3, pas seulement à ce que la spec anticipait).
