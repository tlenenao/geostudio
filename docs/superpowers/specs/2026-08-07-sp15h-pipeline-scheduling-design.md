# SP-15h — Planification simple des pipelines (design)

> **Date : 2026-08-07 · Statut : validé (brainstorm tenu en session)**
> Huitième sous-partie de **SP-15 — ETL no-code « équivalent FME »** (feuille
> de route, jalon **M14**, arbitrage **A39**). Ferme le dernier point que le
> résumé SP-15a-g qualifiait de non planifié côté feuille de route : « reste
> automatisation/déclencheurs au-delà de la planification simple ». Les
> **triggers événementiels durables** restent explicitement différés (feuille
> de route §9 : *« Restent différés : les triggers durables événementiels
> au-delà de la planification simple (Phase 4 de SP-15, sur demande) »*) — ce
> sous-plan livre exactement la partie qui entre au périmètre, rien de plus.
>
> Références de code vérifiées en session :
> `core/app/configs/schemas.py:168-213` (`PipelineNode`/`PipelineEdge`/
> `PipelinePayload` — pas de champ planification aujourd'hui) ;
> `core/app/harvest/jobs.py` (`run_harvest_sweep_task`, patron de balayage
> périodique `@app.periodic(cron="*/15 * * * *")` + garde `is_read_only_mode`)
> et `core/app/harvest/repository.py:158-188` (`list_due_sources` — candidats
> scannés en Python, garde de concurrence par âge `_RUNNING_RECLAIM_MINUTES`,
> patron repris ici) ; `core/app/pipelines/jobs.py` (`run_pipeline_task` —
> chemin d'exécution manuel existant, réutilisé tel quel par le sweep) ;
> `core/app/pipelines/repository.py` (`create_run`/`list_runs`/`mark_*` — pas
> de « dernier run » à `LIMIT 1` aujourd'hui) ; `core/app/configs/models.py`
> (`Config`/`ConfigRevision` — contenu en JSON, pas de colonnes filtrables en
> SQL pour un champ interne au payload) ; `core/app/configs/repository.py`
> (pas de `list_configs_by_kind` cross-tenant aujourd'hui) ;
> `core/app/auth/dependency.py` (`is_etl_enabled()`) ;
> `core/app/pipelines/routes.py` (routes montées uniquement si
> `CORE_ETL_ENABLED`) ; `core/app/mcp/tools.py:611-694` (`create_pipeline`/
> `run_pipeline`/`explain_pipeline` — signatures vérifiées, aucun changement
> de signature prévu) ; `/home/lenen/projets/geostudio/core/.venv/lib/
> python3.14/site-packages/procrastinate/periodic.py` (`croniter` déjà
> dépendance transitive de procrastinate, utilisée en interne par
> `@app.periodic`) ; `shell/src/pages/HarvestSourcesAdminPage.tsx` (patron UI
> existant le plus proche — un simple champ numérique `intervalMinutes`, pas
> d'éditeur visuel de planification dans le shell à ce jour, confirmé par
> recherche `cron|intervalMinutes` sans résultat en dehors des types générés).

## 1. Objectif & non-buts

**Objectif.** Un pipeline sauvegardé peut s'exécuter tout seul selon un
calendrier récurrent (cron), sans qu'un humain ou un agent MCP déclenche
chaque run manuellement. Couvre les cas d'usage cités par l'étude de
faisabilité amont (§5, Phase 4) : « sync ArcGIS nocturne », « export
open-data planifié », « toutes les 15 minutes ».

**Non-buts explicites** (pour rester borné à la « planification simple ») :
- **Aucun trigger événementiel** (webhook entrant, événement CDC, fichier
  déposé…) — reste différé, sur demande réelle, hors de ce sous-plan.
- **Aucun nouvel outil MCP.** `create_pipeline`/`run_pipeline` gardent leur
  signature actuelle ; `refreshPolicy` transite par le PATCH de config
  générique déjà utilisé par le builder pour `nodes`/`edges`. Seul
  `explain_pipeline` gagne un champ dans sa sortie (pas une nouvelle
  signature d'entrée).
- **`transform.sql` sandboxé** reste différé (Phase 4 de l'étude de
  faisabilité, mais hors du périmètre tranché en session pour ce sous-plan).
- **Gabarit galerie, parité FME** restent différés — aucune demande réelle
  actuellement.
- **Pas d'affichage « prochaine exécution »** dans l'UI (calcul cron
  généraliste côté client, hors scope MVP) — seul le dernier run (déjà
  affiché par `PipelineRunPanel`) reste visible.
- **Précision au grain du balayage (5 minutes), pas à la seconde** — même
  limitation déjà acceptée pour le CDC (10 min) et le moissonnage (15 min) ;
  documentée, pas un bug.
- **Pas de table opérationnelle séparée** (`PipelineSchedule` à la
  `HarvestSource`) — `refreshPolicy` vit dans le document `Pipeline`
  versionné, « dernier run » dérivé de `pipeline_runs` existant. Décision de
  brainstorm : un pipeline reste un unique document déclaratif, cohérent avec
  la règle d'architecture #2.
- **Aucune migration Alembic** — `refreshPolicy` est un champ optionnel du
  JSON `PipelinePayload`, rétrocompatible avec tout pipeline déjà sauvegardé
  (`None` par défaut = comportement actuel inchangé).

## 2. Modèle de données

### 2.1 `PipelineRefreshPolicy`

Nouveau modèle dans `core/app/configs/schemas.py`, à côté de `PipelinePayload` :

```python
class PipelineRefreshPolicy(BaseModel):
    enabled: bool = False
    cron: str

    @model_validator(mode="after")
    def _require_valid_cron(self) -> "PipelineRefreshPolicy":
        import croniter
        if not croniter.croniter.is_valid(self.cron):
            raise ValueError(f"invalid cron expression: {self.cron!r}")
        return self


class PipelinePayload(BaseModel):
    nodes: list[PipelineNode] = Field(default_factory=list)
    edges: list[PipelineEdge] = Field(default_factory=list)
    refreshPolicy: PipelineRefreshPolicy | None = None
    ...
```

La validation cron est un `model_validator` Pydantic, au même niveau que les
autres checks de forme déjà présents dans ce fichier (p. ex.
`BookmarkPayload._require_non_empty_page_id`) — elle rejette une expression
invalide à la sauvegarde (422), avant même que le pipeline puisse atteindre
la queue. `cron` est requis dès que `refreshPolicy` est présent (même quand
`enabled=False`) pour que l'UI puisse toujours pré-remplir un cron valide en
mémoire quand l'auteur bascule le toggle.

`croniter` passe de dépendance transitive (via `procrastinate`) à dépendance
directe déclarée dans `core/pyproject.toml`, puisqu'il est désormais importé
directement par `app.configs`.

### 2.2 Pas de nouvelle table

Le « dernier run » et l'état « en cours » nécessaires au calcul de dû
(§3.2) sont dérivés de `pipeline_runs` (déjà là, `core/app/pipelines/
models.py`), pas dupliqués dans une colonne séparée. Une seule nouvelle
fonction dans `core/app/pipelines/repository.py` :

```python
def get_latest_run(session: Session, *, tenant_id: str, pipeline_item_id: str) -> PipelineRun | None:
    return session.execute(
        select(PipelineRun)
        .where(PipelineRun.tenant_id == tenant_id, PipelineRun.pipeline_item_id == pipeline_item_id)
        .order_by(PipelineRun.created_at.desc())
        .limit(1)
    ).scalars().first()
```

## 3. Runtime — balayage périodique

### 3.1 Nouvelle tâche procrastinate

`core/app/pipelines/jobs.py`, à côté de `run_pipeline_task` :

```python
@app.periodic(cron="*/5 * * * *")
@app.task(queue="etl")
def run_pipeline_sweep_task(timestamp: int) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : balayage de planification ignoré")
        return
    if not is_etl_enabled():
        return
    session_factory = _session_factory()
    with request_scoped_session(session_factory) as session:
        due = _list_due_pipelines(session)
        for item_id, tenant_id in due:
            run = pipelines_repo.create_run(session, tenant_id=tenant_id, pipeline_item_id=item_id)
            run_pipeline_task.defer(run_id=run.id, tenant_id=tenant_id)
```

Garde `is_etl_enabled()` **explicite et nécessaire ici** : contrairement aux
routes REST/MCP (montées seulement si le flag est actif, cf. commentaire en
tête de `routes.py`) et contrairement à `run_pipeline_task` (jamais enfilée
sans passer par une route déjà gardée), une tâche `@app.periodic` s'enregistre
et se déclenche indépendamment de ce flag — sans ce garde, le sweep
continuerait de créer des runs même instance CORE_ETL_ENABLED=false.

### 3.2 Calcul du dû

```python
def _list_due_pipelines(session: Session) -> list[tuple[str, str]]:  # [(item_id, tenant_id)]
    configs = configs_repo.list_configs_by_kind(session, kind="pipeline")  # nouvelle fonction
    now = _now()
    due = []
    for config in configs:
        policy = config.config.pipeline.refreshPolicy if config.config.pipeline else None
        if policy is None or not policy.enabled:
            continue
        latest = pipelines_repo.get_latest_run(session, tenant_id=config.tenant_id, pipeline_item_id=config.item_id)
        if latest is not None and latest.status in ("queued", "running"):
            age = now - latest.created_at
            if age < timedelta(minutes=_RUNNING_RECLAIM_MINUTES):
                continue  # déjà en cours, pas de double-run
            # sinon présumé planté (même reclaim-par-âge que le moissonnage) → due
        elif latest is not None:
            next_tick = croniter.croniter(policy.cron, latest.created_at).get_next(datetime)
            if next_tick > now:
                continue
        due.append((config.item_id, config.tenant_id))
    return due
```

`configs_repo.list_configs_by_kind` est une nouvelle fonction cross-tenant
(pas de filtre `tenant_id`, même posture que `harvest_repo.list_due_sources`
— un balayage système n'est scopé à aucun tenant, il défère ensuite des
tâches individuelles avec le `tenant_id` correct chacune). Le filtre
`refreshPolicy.enabled` se fait **en Python après chargement**, pas en SQL :
le contenu du pipeline est un JSON opaque en base (`ConfigRevision.data`),
filtrer une clé imbriquée en SQL diffère entre SQLite (tests) et Postgres
(prod) — cohérent avec la volumétrie attendue (un pipeline est un objet
d'auteur technique, pas un objet de masse comme les features).

### 3.3 Chemin d'exécution unique

Le sweep appelle `pipelines_repo.create_run` + `run_pipeline_task.defer`
— **exactement** le même chemin que `POST /pipelines/{id}/run` et l'outil
MCP `run_pipeline`. Aucune divergence d'exécution entre un run manuel et un
run planifié ; seule la décision « faut-il en créer un » diffère.

## 4. Surface REST/MCP

**Aucune nouvelle route, aucun nouvel outil.** `refreshPolicy` est un champ
de plus dans `PipelinePayload`, il transite par le `PATCH /configs/{id}`
générique déjà utilisé par `PipelineBuilderPage` pour sauvegarder
`nodes`/`edges` — même round-trip, même audit (`config.update`), même
versioning/rollback.

Seul changement : `explain_pipeline` (MCP, `core/app/mcp/tools.py:670-695`)
inclut `refreshPolicy` dans sa sortie, pour qu'un agent MCP puisse voir
qu'un pipeline est planifié sans avoir à connaître le format de payload REST.

```python
return {
    "title": item.title,
    "nodes": [...],
    "edges": [...],
    "refreshPolicy": payload.refreshPolicy.model_dump() if payload.refreshPolicy else None,
}
```

## 5. UI shell — éditeur visuel de planification

Nouveau composant `shell/src/builder/pipeline/PipelineScheduleEditor.tsx`,
monté dans `PipelineRunPanel.tsx` (là où les runs existants sont déjà
listés/pollés).

**Toggle** « Planification automatique » (`refreshPolicy.enabled`). Une fois
activé, un sélecteur de **mode** avec 3 presets + un mode texte libre — les
presets se compilent en cron par interpolation de chaîne simple, **aucune
librairie cron JS ajoutée** :

| Mode | Champs | Cron généré |
|---|---|---|
| Toutes les N minutes | nombre `N` | `*/N * * * *` |
| Quotidien | `<input type="time">` HH:MM | `M H * * *` |
| Hebdomadaire | jour (0-6) + HH:MM | `M H * * D` |
| Cron avancé | texte libre | passthrough tel quel |

**Reconnaissance à l'ouverture** : le cron stocké est comparé par
pattern-matching (regex simple) contre les 3 formes ci-dessus ; s'il matche,
l'éditeur s'ouvre dans le mode correspondant avec les champs pré-remplis ;
sinon il s'ouvre en mode « avancé » avec le cron brut affiché tel quel — pas
de perte, y compris pour un cron écrit à la main via MCP/REST/curl.

**Validation** : légère côté client en mode avancé (regex : 5 champs
séparés par des espaces) pour un feedback immédiat ; autorité finale =
l'erreur 422 serveur (`invalid cron expression`) remontée inline sous le
champ, comme les autres erreurs de validation de pipeline déjà affichées par
`PipelineNodeInspector`.

Sauvegarde : `refreshPolicy` fait partie du payload `PipelinePayload`
existant, donc du même `PATCH /configs/{id}` que le reste du canvas — pas de
bouton « enregistrer la planification » séparé, elle suit le cycle de
sauvegarde du pipeline.

## 6. Tests

**Core (`core/tests/`)** :
- `PipelineRefreshPolicy` : cron valide accepté, cron invalide → `ValueError`
  à la construction / 422 via la route de sauvegarde de config.
- `_list_due_pipelines` (ou fonction équivalente testée directement) :
  jamais exécuté → dû ; dernier run ancien selon cron → dû ; dernier run
  récent selon cron → pas dû ; dernier run `"running"` frais → pas dû ;
  dernier run `"running"` vieux (> `_RUNNING_RECLAIM_MINUTES`) → dû (reclaim) ;
  `refreshPolicy.enabled=False` → jamais dû, quel que soit le cron.
- `run_pipeline_sweep_task` : garde `is_read_only_mode` et `is_etl_enabled`
  vérifiées (aucun run créé si l'une des deux est vraie/fausse).
- `get_latest_run` : round-trip simple (plusieurs runs, le plus récent
  remonté).

**Shell (`shell/src/builder/pipeline/`)** :
- `PipelineScheduleEditor` : les 3 presets génèrent le cron attendu ; un
  cron non reconnu ouvre le mode avancé avec la valeur brute intacte ;
  toggle désactivé n'affiche pas les champs de mode ; erreur 422 serveur
  affichée inline.

**E2E (`shell/e2e/pipeline-builder.spec.ts` ou nouveau spec)** : activer une
planification quotidienne sur un pipeline existant depuis le canvas, la
sauvegarder, recharger la page, vérifier qu'elle est toujours affichée
(round-trip complet config→UI). Le déclenchement réel du sweep n'est pas
testable en E2E navigateur (tâche worker asynchrone) — couvert uniquement
par les tests core ci-dessus, cohérent avec la façon dont SP-12c teste déjà
`run_harvest_sweep_task`.

## 7. Risques & arbitrages

| Risque | Mitigation |
|---|---|
| Balayage cross-tenant coûteux si beaucoup de pipelines | Volumétrie attendue faible (objet d'auteur technique) ; filtre Python après chargement, pas de jointure lourde ; grain 5 min, pas agressif |
| Double-run si le worker est lent à marquer `"running"` | Même garde qu'`run_pipeline_task` déjà en place (`mark_running` avant tout traitement) ; le sweep ne recrée pas de run pour un pipeline déjà `"queued"`/`"running"` frais |
| Run planifié bloqué en `"running"` pour toujours (crash worker) | Reclaim par âge identique au moissonnage (`_RUNNING_RECLAIM_MINUTES`) — pas un nouveau mécanisme |
| Cron mal formé sauvegardé malgré tout (contournement de l'UI, appel API direct) | Validation serveur (`croniter.is_valid`) au niveau du schéma Pydantic, pas seulement côté UI — impossible à contourner via REST/MCP direct |
| `CORE_ETL_ENABLED=false` après coup, pipelines déjà planifiés | Le sweep vérifie le flag à chaque tick (pas seulement au démarrage du worker) — désactiver l'instance coupe immédiatement toute planification, cohérent avec le reste de la capacité (routes/MCP déjà gardées pareil) |

## 8. Critères d'acceptation

- Un auteur active une planification quotidienne sur un pipeline existant
  depuis le canvas, sans écrire de cron à la main.
- Le pipeline s'exécute automatiquement au sweep suivant sa planification
  due, sans action manuelle, en écrivant un `PipelineRun` identique à un run
  manuel.
- Un cron invalide est rejeté à la sauvegarde (422), jamais silencieusement
  ignoré.
- `CORE_ETL_ENABLED=false` : aucun run planifié ne se déclenche, même avec
  des pipelines `refreshPolicy.enabled=true` existants.
- Un pipeline déjà en cours d'exécution n'est jamais relancé en double par
  le sweep tant qu'il n'est pas bloqué au-delà du délai de reclaim.
