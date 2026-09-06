# SP-49 — Fiabilité des jobs & cohérence des migrations

**Date** : 2026-09-05
**Statut** : spec, prête à devenir un plan
**Demandeur** : Tanguy (feuille de route révisée, suite SP-42/SP-43)
**Documents liés** : `docs/revue/2026-09-04-analyse-gaps.md` (GAP-56, GAP-63,
GAP-64, GAP-76), `docs/revue/2026-09-04-backlog.md` (REV-026/027/029/030/034/035
et REV-150/157/158/170, qui regroupent les mêmes trouvailles), `CLAUDE.md`
§« Pièges récurrents » (n°3, n°8, n°10, n°12), spec/plan SP-43
(`docs/superpowers/specs/2026-09-04-sp43-refactorisation-structurelle-design.md`,
`docs/superpowers/plans/2026-09-05-sp43-refactorisation-structurelle.md`).

**Portée de ce document** : fermer 4 gaps « Sérieux » de la revue SP-42,
laissés hors périmètre de SP-43 §7 (« la correction du reste des 43
trouvailles confirmées non corrigées non retenues ici ») : GAP-63 (dérive
modèle/migration résiduelle + downgrade cassé), GAP-64 (N+1 sur les
balayages cron et le moissonnage), GAP-56+GAP-76 (reprise de jobs incomplète
sur 3 familles + supervision incomplète). Aucune nouvelle fonctionnalité —
uniquement fiabilité et performance de mécanismes déjà livrés.

---

## 0. État réel vérifié en session (piège CLAUDE.md n°3/n°12 : ne pas se fier au texte des GAP sans relire le code)

Le brief de cette tâche demandait explicitement de vérifier, avant d'écrire
quoi que ce soit, l'état réel de deux dépendances et le périmètre exact déjà
couvert par SP-43. Fait, par lecture directe du code sur `dev` :

### 0.1 `core/tests/test_model_alembic_parity.py` : existe, portée confirmée

Le fichier existe (écrit par SP-43 Étape 0/1), compare `alembic upgrade head`
à `Base.metadata` sur une base Postgres jetable, avec deux pièges déjà
documentés dans son propre docstring (positionner `DATABASE_URL`, peupler
`Base.metadata` via `core_table_names()`) et un troisième trouvé en revue
(aplatir `compare_metadata()` avant de filtrer, cf. `_flatten_diff`). **Ce
test protège uniquement les `server_default=`/types/contraintes — il ne
vérifie ni la présence d'index, ni le comportement de `downgrade()`** : deux
`Index()` manquants côté modèle sur des colonnes déjà indexées ne le feraient
échouer que si l'index existe côté migration mais pas côté modèle (ou
l'inverse) — s'il n'existe **nulle part**, ce test reste vert. C'est
exactement la situation d'`alert_evaluations`/`pipeline_runs` (§0.2) : ce
filet ne les couvre pas aujourd'hui et ne les couvrira pas tant qu'aucun
index n'est ajouté ni côté modèle ni côté migration.

### 0.2 `alert_evaluations`/`pipeline_runs` : SP-43 ne les a PAS indexées — confirmé par trois sources indépendantes

1. **Le code** : `core/alembic/versions/0018_pipeline_runs.py` et
   `0020_alert_evaluations.py` ne contiennent aucun `op.create_index()` ; les
   modèles (`app/pipelines/models.py`, `app/alerts/models.py`) ne déclarent
   aucun `Index`/`index=True`. Confirmé par grep direct sur les deux
   migrations (aucune occurrence de `index` en dehors de `server_default`).
2. **Git log** : les 5 corrections d'index de SP-43 (commits `ee4c50b4`,
   `01b9d292`, `3ffb28e4`, `6ed0db3c`, `7a767206`, `f97bb43d`) portent sur
   `report_runs`, `terrain3d_jobs`, `tileset3d_jobs`, `export_jobs`,
   `appexport_jobs` et `items.slug` — **jamais** `alert_evaluations` ni
   `pipeline_runs`. Point important pour comprendre la nature du travail
   restant : ces 5 corrections étaient des rattrapages de **parité
   modèle/migration** (l'index existait déjà en base depuis la migration
   d'origine, seul le modèle SQLAlchemy ne le déclarait pas — cf. le
   commentaire du commit `ee4c50b4` : « Additive, correspond exactement à
   l'index déjà posé par la migration »). **Rien de comparable n'existe pour
   `alert_evaluations`/`pipeline_runs` : ici l'index est absent des DEUX
   côtés, en base réelle comme dans le modèle.** Une vraie migration
   `CREATE INDEX` est nécessaire, pas un simple ajout côté modèle.
3. **La spec SP-43 elle-même** (§7, dernier point du « hors périmètre
   explicite ») : « la correction du reste des 43 trouvailles confirmées non
   corrigées non retenues ici (celles qui ne relèvent ni de duplication ni
   de patron divergent — ex. performance N+1 des balayages cron […], index
   manquants sur `alert_evaluations`/`pipeline_runs`) : elles restent au
   backlog SP-42 ». Explicite et sans ambiguïté : ces deux tables et le N+1
   des balayages cron sont **hors périmètre de SP-43 par construction**, pas
   un oubli — c'est très exactement le périmètre de ce document.

### 0.3 `core/app/jobs/common.py` : existe, contrat confirmé

Le module existe (SP-43 Tâche 6/5) et expose trois fonctions déjà consommées
par `app/ingestion/tasks.py` (confirmé par `from app.jobs.common import
notify_best_effort, session_factory` et un `_notify()` local qui les
enveloppe) :

- `session_factory() -> SessionFactory` — engine + session factory depuis
  `DATABASE_URL`, repli SQLite mémoire.
- `resolve_owner_user(session, *, tenant_id, item_id) -> User` — lève
  `LookupError` générique si l'item n'existe pas ; chaque appelant garde son
  propre type d'exception métier via un wrapper local.
- `notify_best_effort(session_factory_fn, *, tenant_id, recipient_user_id,
  kind, status, item_id, item_resource_type, item_title, error=None) ->
  None` — ouvre sa propre session, écrit la notification, avale toute
  exception. **Invariant à préserver dans tout nouvel appelant de ce
  document** : ce bloc doit rester dans un `try/except` strictement séparé
  du bloc qui committe le statut du job (cf. SP-39, deux `UnboundLocalError`
  réels trouvés faute de cette séparation).

Toute nouvelle fonction de reprise (§3.3) doit s'appuyer sur ces trois
fonctions — ne pas écrire une 6e copie de `_session_factory()`/`_notify()`.
`app/ingestion/tasks.py` a déjà un `_notify()` local qui enveloppe
`notify_best_effort` avec la résolution `created_by` propre à l'ingestion
(le job porte directement `created_by`, pas besoin de
`resolve_owner_user()`) — le réutiliser tel quel pour §3.3.

---

## 1. GAP-63 — Dérive résiduelle modèle/migration, `downgrade()` cassé, index manquants

### 1.1 `downgrade()` de la migration 0024 échoue sur une base non vide

`core/alembic/versions/0024_report_runs_nullable_export_job.py` :

```python
def upgrade() -> None:
    op.alter_column("report_runs", "export_job_id", existing_type=sa.String(), nullable=True)

def downgrade() -> None:
    op.alter_column("report_runs", "export_job_id", existing_type=sa.String(), nullable=False)
```

`upgrade()` relâche `export_job_id` en nullable précisément pour permettre
qu'une ligne `report_runs` existe **sans** `export_jobs` derrière elle (un
déclenchement de rapport en échec — propriétaire ayant perdu l'accès,
capacité export coupée — crée quand même une ligne, sinon
`list_due_reports` rejugerait le rapport « dû » à chaque balayage au lieu de
respecter son cron ; cf. `app/reports/models.py`, commentaire de
`export_job_id`). **Toute base ayant ne serait-ce qu'une seule ligne
`report_runs.export_job_id IS NULL` (situation que ce même mécanisme produit
en fonctionnement normal) fait échouer `downgrade()` en `NotNullViolation`.**
Documenté depuis 2026-08-22 par la migration `0028` elle-même (commentaire),
jamais corrigé.

**Décision de conception (reprend la recommandation déjà écrite dans le
backlog, REV-036/§ correctif) : ne pas retendre la contrainte au
downgrade.** Deux options existaient :

- (a) Backfiller les lignes `NULL` avant de retendre la contrainte — perte
  d'information silencieuse, et arbitraire (quelle valeur donner à
  `export_job_id` pour une ligne qui n'a jamais eu d'export réel ?
  `export_jobs.id` n'est même pas une FK SQL ici — cf. commentaire du
  modèle : « pas de FK SQL vers export_jobs.id […] jamais jointe en SQL »).
- (b) **Ne pas restaurer la contrainte** : le relâchement de 0024 est
  permanent par construction — la fonctionnalité qu'il active (ligne
  marqueur d'échec sans export réel) n'a pas d'équivalent valide en `NOT
  NULL`, donc aucune restauration honnête n'existe. Documenter
  explicitement ce choix dans le docstring de la migration plutôt que de
  laisser un `ALTER TABLE` brut échouer avec un message Postgres opaque.

Retenu : **(b)**. `downgrade()` devient un no-op documenté pour cette
colonne précise (aucune autre opération de cette migration à annuler — elle
ne fait que cet unique `alter_column`). Toute session qui rejoue `downgrade
0024` réussit désormais inconditionnellement, y compris sur une base non
vide portant des lignes `NULL` — ce qui ferme la classe de bug (CLAUDE.md
piège n°8 : tester une migration sur base non vide, dans les deux sens).

### 1.2 `alert_evaluations`/`pipeline_runs` sans aucun index

Confirmé §0.2. Les deux tables sont interrogées par **exactement** le même
patron, à trois points d'accès chacune :

- `get_latest_run`/`get_latest_evaluation` : `WHERE tenant_id = ? AND
  <item>_id = ? ORDER BY created_at DESC LIMIT 1` — appelé par le
  balayage cron **par objet** (§2) et par tout code applicatif qui a besoin
  du dernier statut.
- `list_runs`/`list_evaluations` : même `WHERE`, sans `LIMIT` — alimente le
  panneau Historique de l'éditeur (`PipelineRunPanel`/`AlertRuleEditor`,
  hors périmètre de correction ici, cf. §5).
- Écriture (`create_run`/`create_evaluation`, `mark_*`) : par `id` (clé
  primaire), déjà indexée nativement.

Sans index sur `(tenant_id, <item>_id)`, chacune des deux premières requêtes
fait un scan séquentiel complet de la table à chaque tick de balayage (5
minutes, cf. §2) — et le tri `ORDER BY created_at DESC` s'ajoute par-dessus
sans support d'index non plus. Un index composite couvrant à la fois le
filtre et le tri évite les deux coûts en une seule structure :

```python
# app/pipelines/models.py
__table_args__ = (Index("ix_pipeline_runs_pipeline", "tenant_id", "pipeline_item_id", "created_at"),)

# app/alerts/models.py
__table_args__ = (Index("ix_alert_evaluations_rule", "tenant_id", "alert_rule_item_id", "created_at"),)
```

Nom `ix_alert_evaluations_rule` repris tel quel du backlog (REV-035, déjà
proposé) ; `ix_pipeline_runs_pipeline` par symétrie. Précédent direct dans
le dépôt pour la forme (`Index(nom, "tenant_id", "colonne_id",
"created_at")`, colonnes dans cet ordre) : `ix_notifications_recipient_created`
(`app/notifications/models.py`, migration `0031`) et
`ix_report_runs_tenant_id` (`app/reports/models.py`, `Index(..., "tenant_id",
"id")` — motif plus simple mais même famille).

Migration nécessaire : nouvelle révision `0035` (tête actuelle : `0034`,
confirmé par `ls core/alembic/versions/`), `op.create_index()` sur les deux
tables ; `downgrade()` fait le `op.drop_index()` symétrique — celui-ci ne
pose aucun problème de contrainte (contrairement à §1.1), donc pas
d'asymétrie à documenter ici.

**Le filet `test_model_alembic_parity.py` doit rester vert** après l'ajout
(l'index doit exister identiquement des deux côtés) — c'est le test de
non-régression naturel pour cette tâche, en plus d'un test dédié qui vérifie
que l'index existe réellement en base (`pg_indexes` ou
`sa.inspect(engine).get_indexes(table_name)`).

---

## 2. GAP-64 — N+1 contre la doctrine « une requête par lot »

### 2.1 Les 3 balayages cron (pipelines, alertes, rapports)

`list_due_pipelines`/`list_due_reports`/`list_due_rules`
(`app/pipelines/repository.py`, `app/reports/repository.py`,
`app/alerts/repository.py`) partagent tous les trois le même patron
vérifié :

```python
for item_id, tenant_id, config in configs_repo.list_configs_by_kind(session, kind="pipeline"):
    ...
    latest = get_latest_run(session, tenant_id=tenant_id, pipeline_item_id=item_id)  # 1 requête PAR itération
    ...
```

`configs_repo.list_configs_by_kind` fait déjà une seule requête pour charger
tous les `Config` du `kind` demandé (`select(Config).where(Config.kind ==
kind)`, cross-tenant, sans limite — la doctrine SP-29a « une requête par
lot » ne s'applique donc qu'à moitié : le chargement des configs est déjà
groupé, mais le « dernier run » est ensuite refait une fois par config dans
la boucle Python). Avec N pipelines/alertes/rapports actifs sur l'ensemble
des tenants, chaque tick (`*/5 * * * *`, soit toutes les 5 minutes pour les
trois) exécute 1 + N requêtes au lieu de 2.

**Correctif** : une fonction batchée par domaine qui retourne, en une seule
requête, le dernier run/évaluation par `item_id` pour une liste
d'`item_id`s donnée. Approche portable Postgres **et** SQLite (les tests de
sweep — `test_pipeline_sweep.py`, `test_alert_sweep.py`, `test_report_sweep.py`
— tournent contre `sqlite+pysqlite:///:memory:`, confirmé par lecture directe
de leurs fixtures ; pas de `DISTINCT ON` Postgres-only) : fenêtre
`ROW_NUMBER() OVER (PARTITION BY <item>_id ORDER BY created_at DESC)`,
filtrée à `rn = 1` en sous-requête. SQLite ≥ 3.25 supporte les fonctions
fenêtre (la version bundlée avec Python 3.12+ de ce dépôt les supporte —
**à vérifier explicitement en Step 1 du plan avant d'écrire
l'implémentation complète, ne pas supposer** — cf. piège CLAUDE.md n°3).

```python
def get_latest_runs_for_items(
    session: Session, *, tenant_id_by_item: dict[str, str]
) -> dict[str, PipelineRun]:
    item_ids = list(tenant_id_by_item)
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

`list_due_pipelines`/`list_due_reports`/`list_due_rules` appellent cette
fonction **une fois** avec la liste complète des `item_id` retournés par
`list_configs_by_kind`, puis consultent le dict en mémoire dans la boucle
existante (qui garde par ailleurs toute sa logique de décision — cron,
reclaim par âge — inchangée : seul le point d'accès au « dernier run »
change, pas la logique de décision elle-même). Trois implémentations
quasi identiques (une par domaine, `pipeline_item_id`/`report_item_id`/
`alert_rule_item_id`) — pas de généralisation au-delà de ce que permet déjà
`app.jobs.common` (le filtrage par colonne varie), donc trois fonctions,
chacune dans son propre `repository.py`, pas une extraction transverse
supplémentaire.

**Trouvaille annexe, explicitement hors périmètre de ce correctif** :
`configs_repo.list_configs_by_kind` (`app/configs/repository.py:91-120`)
a lui-même un second N+1 non cité par GAP-64/F-performances-01 — il appelle
`_latest_revision(session, record.id)` une fois par `Config` dans sa propre
boucle (ligne 101), pour retrouver la révision courante. Le texte de
GAP-64 et les entrées `F-performances-01/02/03` du backlog ne mentionnent
que le N+1 du « dernier run », pas celui-ci. **Décision de scope prise
ici** : ne pas le corriger dans ce document — `list_configs_by_kind` est un
point d'accès partagé bien au-delà des trois balayages (utilisé par
d'autres domaines, cf. `list_configs_by_kind_and_tenant` sœur), une
correction mal calibrée y créerait un risque de régression sans rapport
avec GAP-64 tel qu'assigné. Noté explicitement pour que Tanguy tranche s'il
veut l'ouvrir séparément (candidat naturel : nouvelle entrée backlog, pas
un ajout silencieux à ce plan).

### 2.2 `GET /harvest/layers` / `GET /harvest/feature-layers`

`app/harvest/routes.py:160-188` (`list_layers`/`list_feature_layers`) :

```python
rows = repo.list_layer_records(session, tenant_id=user.tenant_id, q=q)  # 1 requête, SANS LIMIT
layers = []
for item_id, title, tiles_url, _layer_kind in rows:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)  # 1 req/ligne
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):  # peut ajouter 1 req/ligne
        continue
    layers.append(...)
```

`can()` (`app/sharing/authorization.py:62-98`) court-circuite sans requête
supplémentaire seulement si l'appelant est propriétaire ou si l'item est
public/publié pour une lecture ; sinon il appelle `roles_for_items(...,
item_ids=[item.id])` — une requête de rôles **par ligne**. Confirmé : 1 à 2
requêtes par ligne, sans pagination en amont sur `list_layer_records`/
`list_feature_layer_records` (confirmé : aucun `LIMIT` dans ces deux
fonctions du repository harvest).

**Correctif** : le dépôt a déjà, à deux endroits différents, le motif de
correction recommandé — pas besoin d'en inventer un troisième :

1. `app/items/repository.py::_permissions_by_id` (utilisé par
   `list_items`) : batch **exactement** ce cas — un seul appel à
   `roles_for_items(session, tenant_id=..., user_id=..., item_ids=[...])`
   pour la liste complète, puis `decide()` (fonction pure, sans I/O) par
   ligne en mémoire. C'est le précédent le plus direct ici, puisque
   `harvest/layers` porte lui aussi sur des `items` (pas des collections).
2. `app/collections/repository.py::list_visible_collections` : pousse le
   filtre de visibilité dans le `WHERE` SQL lui-même (jointure sur
   `CollectionShare`/`GroupMember`) plutôt que de filtrer après coup —
   alternative valable mais qui suppose un modèle de partage identique à
   celui des collections ; moins direct à transposer ici que (1).

Retenu : suivre le patron (1). Ajouter une fonction batchée
`get_access_facts_by_ids(session, *, tenant_id, item_ids) ->
dict[str, ItemAccessFacts]` dans `app/items/repository.py` (une seule
requête `WHERE id IN (...)`), puis dans `list_layers`/`list_feature_layers` :
un seul appel à `roles_for_items(item_ids=[...])` pour les ids restants
après filtrage owner/public en mémoire (même schéma que
`_permissions_by_id`), puis `decide()` par ligne. Ajouter aussi un `LIMIT`
raisonnable (proposition : 200, aligné sur les autres listes paginées du
dépôt — à confirmer contre une page existante avant de coder, ne pas
deviner un chiffre) sur `list_layer_records`/`list_feature_layer_records` —
**note de scope** : la pagination complète (curseur, `page`/`page_size`
symétriques à `GET /items`) est le sujet de GAP-57, **pas** assigné à ce
document ; un simple plafond dur (sans curseur) suffit ici pour fermer le
risque N+1/DoS mémoire immédiat sans empiéter sur GAP-57.

---

## 3. GAP-56 + GAP-76 — Reprise de jobs incomplète, supervision incomplète

Les deux GAP se recoupent explicitement dans l'analyse (« GAP-76 […]
recoupe GAP-56 ») — traités ensemble ici, sous-sections distinctes pour
suivre les 3 familles citées.

### 3.1 `export`/`appexport` : `get_job`+`mark_running` hors du bloc `try`

Confirmé par lecture directe :

- `app/export/jobs.py:150-159` (`render_export_task`) : `job =
  export_repo.get_job(...)` puis `export_repo.mark_running(...)` sont dans
  un `with request_scoped_session(...)` **avant** le `try:` de la ligne
  159.
- `app/appexport/jobs.py:103-113` (`build_app_export_task`) : même patron,
  `try:` commence ligne 113, après `get_job`/`mark_running`.
- **Contre-exemple correct, déjà dans le dépôt** : `app/pipelines/jobs.py`
  (`run_pipeline_task`) et `app/ingestion/tasks.py`
  (`run_ingestion_task`) placent ces deux appels **à l'intérieur** du
  premier bloc `try`, avec une variable de destinataire pré-initialisée à
  `None` avant le `try` (pattern déjà documenté en commentaire dans les deux
  fichiers, hérité de la correction SP-39 des deux `UnboundLocalError`
  réels).

Conséquence : si `get_job` ou `mark_running` lève (incident DB transitoire —
le cas exact que le reste du fichier gère soigneusement pour toutes les
étapes suivantes), l'exception remonte **hors** de toute gestion —
`export`/`appexport` n'a alors ni notification best-effort, ni marquage
d'erreur : le job reste `pending` indéfiniment, invisible à tout mécanisme
de reprise par âge (qui ne surveille que `running`, cf. §3.2).

**Correctif** : reprendre à l'identique le patron pipelines/ingestion —
variable de destinataire (`item_id`/`user_id`/etc. selon le domaine)
pré-liée à `None` avant le `try`, `get_job`+`mark_running` déplacés à
l'intérieur. Aucun changement de comportement pour le chemin nominal (le
job continue de passer en `running` avant le reste du traitement) — le seul
changement observable est qu'un échec de ces deux appels précis est
désormais capturé et traité comme les autres échecs de la même fonction.

### 3.2 `appexport_repo.reclaim_stuck_jobs` : jamais appelé

`app/appexport/repository.py:78-102` définit `reclaim_stuck_jobs(session,
older_than_minutes=...)` — même contrat que `export_repo.reclaim_stuck_jobs`
(marque en erreur tout job `running` dont `started_at` dépasse le seuil).
**Confirmé par grep sur tout `app/` : aucun site n'appelle cette fonction.**
Contrairement à `export_repo.reclaim_stuck_jobs`, appelé depuis
`app/reports/jobs.py:285` (`_trigger_due_reports`, fin de tick — couplage
un peu surprenant entre domaines mais fonctionnel, câblé depuis SP-17b) —
**et** contrairement au commentaire de `app/export/jobs.py:137-140` qui
documente correctement ce câblage. Un test existe déjà et prouve que la
fonction elle-même marche
(`tests/test_export_repository.py::test_reclaim_stuck_jobs_marks_old_running_jobs_as_error`,
transposable telle quelle côté appexport si le test correspondant n'existe
pas déjà) — ce qui manque est uniquement l'appelant périodique.
**Docstring périmé associé** (minor, corrigé au passage sans tâche dédiée,
coût nul) : le commentaire au-dessus de `test_reclaim_stuck_jobs_marks_old_running_jobs_as_error`
dans `test_export_repository.py` affirme encore « pas d'appelant périodique
encore câblé (TODO dans app/export/jobs.py) » — stale depuis le câblage
SP-17b, aucun TODO ne subsiste dans ce fichier.

**Correctif** : `app/appexport/jobs.py` n'a aujourd'hui **aucune** tâche
`@app.periodic` (confirmé — les seuls `@app.periodic` du dépôt sont dans
`cdc/jobs.py`, `alerts/jobs.py`, `harvest/jobs.py`, `pipelines/jobs.py`,
`reports/jobs.py`). Ajouter une tâche périodique dédiée
`sweep_appexport_jobs_task` (cron `*/5 * * * *`, aligné sur les 3 balayages
existants) dont le seul rôle est d'appeler
`appexport_repo.reclaim_stuck_jobs(session)` — pas de logique de
déclenchement à ajouter (appexport ne s'auto-déclenche jamais sur cron,
seulement à la demande via `POST /appexport`), donc une tâche minimale,
symétrique à ce que `export/jobs.py` obtient gratuitement du sweep de
rapports.

### 3.3 Ingestion : aucun mécanisme de réclamation

Confirmé : `app/ingestion/repository.py` expose `create_job`/`get_job`/
`mark_running`/`mark_done`/`mark_error` — **aucune fonction
`reclaim_stuck_jobs`**, et aucune tâche périodique ne surveille les jobs
`ingestion_jobs` restés `running`. Un worker tué en cours d'import (process
killé, OOM) laisse le job `running` à vie — aucun mécanisme, même manuel,
ne le détecte aujourd'hui.

**Correctif** : ajouter `reclaim_stuck_jobs(session, *, older_than_minutes:
int = 60) -> list[str]` dans `app/ingestion/repository.py`, même contrat et
même corps que `export_repo.reclaim_stuck_jobs`/`appexport_repo.reclaim_stuck_jobs`
(marque `error` avec un message explicite, `error_message` déjà porté par
`mark_error` existant — vérifier la signature exacte avant d'écrire, ne pas
supposer un nom de paramètre identique aux deux autres). Ajouter une tâche
périodique dédiée `sweep_ingestion_jobs_task` dans `app/ingestion/tasks.py`
(cron `*/15 * * * *`, aligné sur le balayage harvest existant — l'ingestion
n'a pas de contrainte de fraîcheur aussi serrée que les 3 familles `*/5`) :
appelle `reclaim_stuck_jobs`, puis — réutilisant le `_notify()` local déjà
présent dans ce fichier (lui-même bâti sur `app.jobs.common`, cf. §0.3) —
notifie `created_by` (déjà porté directement par `IngestionJob`, pas besoin
de `resolve_owner_user()`) pour chaque job réclamé, dans le même bloc
try/except strictement séparé du commit de statut.

### 3.4 Supervision : `GRAFANA_ALERT_WEBHOOK_URL` et healthchecks

**GRAFANA_ALERT_WEBHOOK_URL** : contrairement à ce que le texte brut de
GAP-76 pourrait laisser penser, ceci **n'est pas un défaut de code non
traité** — vérifié directement dans `docker-compose.yml:577` et
`.env.example:260` : le défaut est déjà délibérément un localhost
inatteignable (`http://127.0.0.1:1/grafana-alert-webhook-not-configured`,
pas une chaîne vide), avec un commentaire de 8 lignes expliquant
qu'une URL vide ferait échouer le provisioning Grafana au démarrage
(vérifié empiriquement selon ce même commentaire). Le seul manque réel
restant est **documentaire** : `.env.example` porte déjà une phrase
(« Régler cette valeur pour recevoir une vraie notification ») mais aucun
document de type « check-list avant mise en production » n'existe dans ce
dépôt pour la mettre en avant (confirmé : aucun fichier
`checklist`/`readiness` sous `docs/` en dehors de la vision/revue). Correctif
proposé, minimal : renforcer le commentaire `.env.example` existant (déjà
fait, correct) n'est pas suffisant en soi — ajouter un rappel explicite
dans `docs/runbooks/2026-07-24-restauration-sauvegardes.md` ou un nouveau
paragraphe court dans le `README.md` (section déploiement) listant les
variables à régler avant la mise en production réelle, dont
`GRAFANA_ALERT_WEBHOOK_URL`. Coût trivial (≤ 0.5j), **non retenu comme
tâche séparée du plan** — à traiter en fin de Tâche 7 comme un correctif
d'une ligne, pas une tâche à part entière.

**Healthchecks** : le texte de GAP-76 (« seul cdc-worker détecte un worker
occupé indéfiniment, les 3 autres sondes ne détectent qu'un process mort »)
est **imprécis une fois vérifié contre le compose réel** — à corriger avant
de concevoir le correctif (piège CLAUDE.md n°3/12) :

| Service | Healthcheck actuel | Ce qu'il détecte réellement |
|---|---|---|
| `worker` | `procrastinate --app app.jobs.app healthchecks` (ligne 444) | Connexion DB + schéma procrastinate présent — **pas** process/job coincé |
| `export-worker` | **aucun** (confirmé : bloc `healthcheck:` absent de sa définition, lignes 491-518) | Rien — seul `restart: unless-stopped` réagit à un crash de process |
| `qgis-worker` | **aucun** (confirmé, lignes 475-483) | Idem |
| `cdc-worker` | `scripts/healthcheck_cdc.py` (slot de réplication PostgreSQL actif) | Consommation réelle du flux CDC, pas seulement le process vivant |

Il n'existe donc qu'**une seule** sonde comparable à celle de `cdc-worker`
dans sa forme (`worker`), et elle ne couvre que la connectivité, pas un job
bloqué — les deux autres services de traitement (`export-worker`,
`qgis-worker`) n'ont **aucune** sonde du tout, ce qui est un manque plus
sévère que ce que le texte du GAP suggère (pas de dégradation
« process mort seulement » — carrément aucune détection). `qgis-worker`
n'est en outre pas un worker procrastinate (`command` absent du bloc
service : l'image lance `server.py`, un serveur HTTP `http.server` minimal
appelé en synchrone par le sidecar QGIS depuis `pipelines/runtime.py` — pas
une file de jobs), donc le mécanisme de correctif diffère de celui de
`worker`/`export-worker`.

**Correctif pour `worker`/`export-worker` (les deux tournent
`procrastinate --app app.jobs.app worker -q <queue>`, la même `App`
partagée — `app/jobs/__init__.py` confirmé)** : le paquet `procrastinate`
(version verrouillée **3.9.0**, `core/uv.lock` confirmé) expose
`JobManager.get_stalled_jobs(nb_seconds=None, queue=None, task_name=None,
seconds_since_heartbeat=30)` — méthode publique documentée de la classe
`App.job_manager`. Deux modes internes, vérifiés dans
`procrastinate/sql/queries.sql` :

- `seconds_since_heartbeat` (le défaut) : compare le `last_heartbeat` du
  **worker** (mis à jour toutes les 10s par une tâche asyncio indépendante
  de l'exécution des jobs, `Worker._update_heartbeat`) — ne détecte qu'un
  process totalement figé (event loop bloqué), **pas** un job unique
  coincé pendant que le reste du worker continue de battre — ce n'est pas
  ce que demande GAP-76.
- `nb_seconds` (paramètre marqué déprécié dans cette version, mais
  fonctionnel) : requête `select_stalled_jobs_by_started`, indépendante du
  heartbeat — sélectionne tout job `status = 'doing'` dont l'évènement
  `started` dans `procrastinate_events` date de plus de `nb_seconds`. C'est
  **exactement** le signal recherché (« worker occupé indéfiniment par une
  tâche qui ne rend jamais la main »), au même titre que
  `scripts/healthcheck_cdc.py` interroge un signal serveur plutôt qu'un
  process vivant.

Un script `core/scripts/healthcheck_worker_stalled.py`, sur le patron exact
de `healthcheck_cdc.py` (sortie 0/1, jamais d'exception non attrapée),
appelant `app.job_manager.get_stalled_jobs(nb_seconds=<seuil>, queue=<queue
ou None>)` via `app` importé depuis `app.jobs` (déjà l'App partagée,
`import_paths` déjà enregistrés) — retourne 1 si la liste n'est pas vide.
Seuil proposé : 3600s (aligné sur `_RUNNING_RECLAIM_MINUTES`/
`_PENDING_RECLAIM_MINUTES` déjà utilisés ailleurs dans ce dépôt pour la
même notion de « probablement planté » — 60 minutes). Paramétrer par
variable d'environnement (`HEALTHCHECK_STALLED_SECONDS`, `HEALTHCHECK_QUEUE`
optionnelle pour filtrer `export-worker` sur sa seule file) plutôt que de
coder en dur, cohérent avec le reste du compose.

**Point à vérifier explicitement en Step 1 du plan, non résolu par cette
recherche** : `get_stalled_jobs` est déclarée `async def` sur `JobManager` ;
`app.open()` (sync) ouvre un connecteur synchrone (confirmé,
`connector.get_sync_connector()`), mais l'appel à une coroutine nécessite
malgré tout soit `asyncio.run(...)`, soit une éventuelle variante
synchrone déjà exposée par `JobManager` (le fichier `manager.py` mêle des
paires `list_jobs`/`list_jobs_async` avec et sans suffixe — vérifier si
`get_stalled_jobs` a un miroir sans suffixe avant de choisir l'approche
finale, ne pas deviner). Si aucune variante sync n'existe, le script
utilisera `app.open_async()`/`asyncio.run()`, toujours un script
autonome exécutable en `CMD`/`healthcheck.test` Docker (pas de contrainte
d'exécution synchrone imposée par Docker lui-même).

**Correctif pour `qgis-worker`** : hors du périmètre naturel de reprise de
jobs (ce n'est pas un worker procrastinate) — ajouter au minimum un
healthcheck HTTP basique si `deploy/qgis-worker/server.py` expose (ou peut
exposer à moindre coût) un point de vivacité ; **à vérifier en début de
tâche** ce que `server.py` sait répondre aujourd'hui (le fichier n'a été lu
que partiellement pendant cette recherche — vérifier ses méthodes
`do_POST`/`do_GET` avant de décider). Ce correctif est nettement plus petit
en portée que celui de `worker`/`export-worker` (juste combler l'absence
totale de sonde, pas détecter un job bloqué au sens procrastinate) — si le
serveur ne répond qu'à des `POST` métier sans route de vivacité, le
correctif minimal viable est un healthcheck de process
(`pgrep -f server.py` ou équivalent), pas un blocage sur une fonctionnalité
HTTP à ajouter au sidecar (qui sort du périmètre fiabilité des jobs pour
entrer dans le périmètre du sidecar QGIS lui-même, plus risqué — cf. spec
SP-43 §5 Étape 9 sur la prudence requise autour de ce composant).

---

## 4. Ordre de traitement proposé, du moins au plus risqué

1. **Migrations (GAP-63)** — fondation, aucune dépendance vers les tâches
   suivantes, risque bas (additif pour les index, correction ciblée pour
   le downgrade).
2. **N+1 des balayages cron (GAP-64.1)** — touche 3 fichiers repository
   déjà couverts par des tests de sweep existants (oracle de
   non-régression comportementale immédiat).
3. **N+1 harvest (GAP-64.2)** — un seul fichier routes + une fonction
   batchée nouvelle dans `items/repository.py`, réutilise un patron déjà
   éprouvé ailleurs dans le dépôt.
4. **Try/except export/appexport (GAP-56.1)** — changement mécanique,
   patron déjà écrit deux fois dans le dépôt (pipelines/ingestion) à
   copier, pas à réinventer.
5. **Reclaim appexport + ingestion (GAP-56.2/56.3)** — construit sur
   `app.jobs.common` (§0.3) et sur les fonctions `reclaim_stuck_jobs`
   déjà existantes/à répliquer.
6. **Healthchecks + doc opérationnelle (GAP-76)** — le plus exploratoire
   (API procrastinate à confirmer avant de coder), placé en dernier.

## 5. Hors périmètre explicite

- **GAP-57** (pagination `GET /collections`, `GET /stac/collections`,
  `GET /dcat/catalog`, historiques `runs`/`evaluations` sans limite) —
  gap distinct, non assigné à ce document. Le plafond dur ajouté sur
  `list_layer_records`/`list_feature_layer_records` (§2.2) n'anticipe pas
  une pagination complète, seulement un garde-fou de volumétrie immédiat.
- **`configs_repo.list_configs_by_kind` N+1 sur `_latest_revision`** —
  trouvaille annexe (§2.1), explicitement descopée, à ouvrir séparément si
  voulu.
- **Fragilité de révision relative dans `test_metadata_migration_alembic.py`**
  (`command.downgrade(alembic_cfg, "-1")`, REV-037 du backlog) — préexistante,
  sans rapport avec ce document ; la nouvelle migration `0035` (§1.2)
  déplace mécaniquement où `"-1"` pointe, mais ce n'est pas une régression
  introduite ici — le risque existait déjà avant ce plan.
- **`get_stalled_jobs`/heartbeat pour une future version de procrastinate** —
  le paramètre `nb_seconds` utilisé en §3.4 est marqué déprécié dans la
  version verrouillée (3.9.0) ; une montée de version majeure future de
  procrastinate pourrait le retirer, ce qui demanderait alors un correctif
  distinct (probablement : faire battre le heartbeat manuellement à
  l'intérieur des tâches longues). Hors périmètre de ce document.
- **Toute nouvelle fonctionnalité utilisateur** — ce document ne touche
  qu'à la fiabilité de mécanismes déjà livrés.

## 6. Risques

- **Index (§1.2)** : un mauvais ordre de colonnes dans l'`Index()` (ex.
  `created_at` avant `<item>_id`) rendrait l'index inutile pour le filtre
  `WHERE tenant_id = ? AND <item>_id = ?` — vérifier l'ordre par un test
  qui inspecte le plan de requête (`EXPLAIN`) n'est pas strictement
  nécessaire (Postgres choisit l'index correct indépendamment de l'ordre
  de déclaration tant que les colonnes filtrées sont en tête), mais
  vérifier au moins que l'index existe bien avec les 3 colonnes attendues,
  dans l'ordre documenté ici, via `sa.inspect(engine).get_indexes(...)`.
- **Downgrade 0024 (§1.1)** : transformer `downgrade()` en no-op documenté
  change la sémantique du terme « downgrade » pour cette migration
  précise — s'assurer que le docstring l'explicite clairement pour éviter
  qu'une session future ne le lise comme un bug plutôt qu'une décision
  assumée.
- **Batching des balayages (§2.1)** : la fonction fenêtrée doit être
  falsifiée (piège CLAUDE.md n°10) — vérifier qu'elle retourne bien **la
  plus récente** ligne par `item_id` et pas une ligne arbitraire (bug
  classique d'un `ROW_NUMBER()` mal ordonné), avec un cas de test à
  plusieurs runs par pipeline dont l'ordre d'insertion diffère de l'ordre
  chronologique attendu.
- **Reclaim ingestion/appexport (§3.2/3.3)** : reproduire la vérification
  déjà faite côté export (`test_reclaim_stuck_jobs_marks_old_running_jobs_as_error`
  et sa sœur « laisse les jobs récents tranquilles ») — un seuil d'âge mal
  calibré marquerait en erreur un job légitimement long.
- **Healthcheck stalled (§3.4)** : un seuil trop bas ferait basculer
  `worker`/`export-worker` en `unhealthy` pendant un traitement
  légitimement long (rendu Playwright volumineux, import GeoPackage 50k
  lignes) — choisir un seuil nettement supérieur à la durée p99 connue de
  ces traitements, pas une valeur arbitraire.
