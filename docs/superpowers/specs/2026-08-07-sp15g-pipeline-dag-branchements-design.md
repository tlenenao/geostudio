# SP-15g — Canvas visuel DAG : branchements & fusion (design)

> **Date : 2026-08-07 · Statut : validé (brainstorm tenu en session)**
> Septième sous-partie de **SP-15 — ETL no-code « équivalent FME »** (feuille de
> route, jalon **M14**, arbitrage **A39**). Lève la mitigation D1 de l'étude de
> faisabilité amont
> ([`2026-07-22-etude-faisabilite-etl-fme-nocode-design.md`](2026-07-22-etude-faisabilite-etl-fme-nocode-design.md)
> §4.1 : *« borne le MVP à une topologie linéaire+join avant le DAG complet »*)
> et le non-but explicitement acté par
> [`2026-08-05-sp15a-pipeline-socle-design.md`](2026-08-05-sp15a-pipeline-socle-design.md)
> (« Full branching/merge DAGs are explicitly deferred to a later sub-plan »).
>
> Références de code vérifiées en session : `core/app/pipelines/compiler.py`
> (`topological_order` — déjà un vrai Kahn générique, aucune hypothèse
> linéaire ; `predecessor_id` — lève si >1 arête entrante, seule vraie
> contrainte de topologie du code) ; `core/app/pipelines/runtime.py`
> (`_prepare`/`_execute_transform_chain`/`run_pipeline`) ; `core/app/configs/
> schemas.py:168-209` (`PipelineNode`/`PipelineEdge` — `edge.when` déjà
> accepté-mais-non-interprété « avant Phase 3/4 », même idiome réutilisé ici
> pour `edge.role`) ; `core/app/configs/pipeline_validation.py`
> (`_check_linear_topology`, structurel, agnostique du catalogue d'op) ;
> `core/app/pipelines/config_validation.py` (`_validate_node`, seul
> validateur générique enregistré pour tous les op) ; `core/app/pipelines/
> ops/schemas.py` (`OP_KINDS`/`OP_PARAMS`/`ops_catalog()`) ; `core/app/
> pipelines/jobs.py` (`run_pipeline_task` — écrit `node_stats` une seule fois,
> à la fin) ; `shell/src/builder/pipeline/PipelineCanvas.tsx` (React Flow
> `@xyflow/react`, pas du SVG fait main — contrairement à ce que l'étude de
> faisabilité envisageait comme MVP) ; `shell/src/builder/pipeline/graphOps.ts`
> /`validation.ts` (miroir client) ; `shell/src/builder/pipeline/
> PipelinePreviewPanel.tsx` (table-only aujourd'hui) ; `shell/src/builder/
> pipeline/PipelineRunPanel.tsx` (poll 1,5s existant) ; `shell/e2e/
> pipeline-builder.spec.ts` (patron de drag `.react-flow__handle-right/left`,
> patron de poll `runPolls`).

## 1. Objectif & non-buts

**Objectif.** Généraliser la topologie « linéaire+join » du runtime Pipeline
(SP-15a) à un vrai DAG, dans les deux sens laissés ouverts par D1 :

- **Fan-out (branchement)** : un nœud peut déjà alimenter plusieurs nœuds
  avals aujourd'hui — rien dans le schéma, le canvas ou le runtime ne
  l'interdit, mais ce n'est ni testé ni documenté. Ce sous-plan en fait une
  capacité officielle (tests + doc), sans changement de mécanisme.
- **Fan-in (fusion)** : aujourd'hui, `transform.join`/`intersection`/
  `countWithin` ne peuvent joindre qu'une **collection brute** (paramètre
  `withCollectionId`), jamais la sortie déjà transformée d'une autre branche
  du même pipeline. Ce sous-plan ajoute une **seconde entrée par arête**
  (alternative additive à `withCollectionId`, jamais les deux à la fois) pour
  ces 3 op, plus un **nouvel op `transform.merge`** (empilement ligne à ligne,
  `UNION ALL BY NAME`, décision de brainstorm : union des colonnes complétée à
  `NULL`).
- **Visibilité d'exécution** : deux ajouts UX qui accompagnent naturellement
  un DAG plus riche à naviguer — un **aperçu cartographique** en plus de
  l'aperçu tabulaire existant, et une **progression en direct** affichée sur
  le canvas pendant un run (au lieu de découvrir les `node_stats` d'un coup à
  la fin).

**Non-buts explicites** (pour rester borné) :
- **Jamais plus de 2 entrées** sur un nœud (`primary`+`secondary` au plus) —
  pas de fusion/jointure à 3 branches ou plus.
- **`edge.when` (routage conditionnel CEL)** reste accepté-mais-non-interprété
  — différé, comme déjà annoncé par le commentaire de `PipelineEdge` (« Phase
  3/4 », vocabulaire de l'étude de faisabilité, jamais ce sous-plan).
- **`transform.sql` libre sandboxé** reste différé (idem, Phase 4).
- **Aucun nouvel outil MCP** : `create_pipeline`/`run_pipeline`/
  `explain_pipeline` acceptent déjà `nodes`/`edges` génériques ; `edge.role`
  et `transform.merge` y transitent sans changement de signature.
- **Progression en direct reste sur le polling existant** (1,5 s) — pas de
  WebSocket, juste plus de granularité dans une donnée déjà pollée.
- **Pas d'annulation d'un run en cours** — hors sujet DAG, non traité ici.
- **Aucune migration Alembic** — `Pipeline` est un document JSON versionné
  (`BuilderConfig.pipeline`), pas une table SQL ; les champs ajoutés sont
  optionnels et rétrocompatibles avec tout pipeline déjà sauvegardé.

## 2. Modèle de données

### 2.1 `PipelineEdge.role`

```python
class PipelineEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_: str = Field(alias="from")
    to: str
    when: str | None = None
    role: Literal["primary", "secondary"] | None = None  # None ≡ "primary" ;
        # "secondary" = seconde entrée d'un op binaire (§2.2), sans effet sur
        # tout autre op (rejeté à la validation, §4)
```

Rétrocompatible sans migration : tout pipeline existant n'a que des arêtes
`role=None`, strictement équivalentes à `"primary"`.

### 2.2 Quatre opérations « binaires »

`transform.join`, `transform.intersection`, `transform.countWithin`
(existantes) et un nouvel op **`transform.merge`** acceptent désormais leur
seconde entrée par **soit** `withCollectionId` (une collection brute, chemin
existant, inchangé) **soit** une arête entrante `role="secondary"` (la sortie
déjà calculée d'une autre branche du pipeline) — jamais les deux à la fois,
jamais ni l'un ni l'autre (rejeté à la sauvegarde dans les deux cas, §4).

```python
class TransformJoinParams(BaseModel):
    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    on: str
    how: Literal["inner", "left"] = "inner"

# idem pour TransformIntersectionParams.withCollectionId et
# TransformCountWithinParams.withCollectionId (str | None, plus leurs autres
# champs inchangés)

class TransformMergeParams(BaseModel):
    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
```

`transform.merge` n'a pas d'autre paramètre : toujours `UNION ALL BY NAME`
(§3.2), pas de variante `DISTINCT` en v0 (une déduplication silencieuse de
lignes réellement dupliquées serait une surprise, cf. §1 « jamais un résultat
silencieusement faux » déjà en place pour les op spatiales).

Ajouts à `OP_KINDS`/`OP_PARAMS` (`core/app/pipelines/ops/schemas.py`) :

```python
OP_KINDS["transform.merge"] = "transform"
OP_PARAMS["transform.merge"] = TransformMergeParams
```

Le module gagne aussi un ensemble nommé, exporté (pas `_`-préfixé) pour être
importable par `app.pipelines.config_validation` (§4.2, même package
`app.pipelines`, aucune frontière de couches à traverser) :

```python
BINARY_OPS = {"transform.join", "transform.intersection", "transform.countWithin", "transform.merge"}
```

### 2.3 `acceptsSecondaryInput` dans le catalogue

`ops_catalog()` publie un booléen calculé par op, pour que le canvas sache
quels nœuds affichent une seconde poignée d'entrée **sans jamais coder de nom
d'op en dur côté shell** :

```python
def ops_catalog() -> dict[str, dict]:
    return {
        op: {
            "kind": OP_KINDS[op],
            "paramsSchema": model.model_json_schema(),
            "acceptsSecondaryInput": op in BINARY_OPS,
        }
        for op, model in OP_PARAMS.items()
    }
```

## 3. Compilateur & runtime

### 3.1 Résolution de la seconde entrée

`compiler.predecessor_id` ne compte que les arêtes `role != "secondary"`
(inchangé en pratique pour tout pipeline existant). Nouvelle fonction :

```python
def secondary_predecessor_id(node_id: str, edges: list[PipelineEdge]) -> str | None:
    incoming = [e.from_ for e in edges if e.to == node_id and e.role == "secondary"]
    if len(incoming) > 1:
        raise ValueError(f"node '{node_id}' has more than one secondary incoming edge")
    return incoming[0] if incoming else None
```

### 3.2 `compile_transform_sql` / `transform_output_srid`

Nouvelle branche `transform.merge` :

```python
if op == "transform.merge":
    assert join_view is not None, "transform.merge requires join_view"
    return f"SELECT * FROM {_qi(input_view)} UNION ALL BY NAME SELECT * FROM {_qi(join_view)}"
```

`UNION ALL BY NAME` est une fonctionnalité DuckDB native : alignement des
colonnes par **nom** (pas par position), complète à `NULL` toute colonne
absente d'un des deux côtés. `transform_output_srid` traite `transform.merge`
comme `intersection`/`countWithin` : exige `input_srid == join_srid`, sinon
`ValueError` explicite invitant à insérer un `transform.reproject` en amont
(jamais de réconciliation implicite de CRS).

### 3.3 `_prepare` (passe 1)

La boucle qui matérialise le `withCollectionId` des 4 op binaires en vue
`__join` **saute** tout nœud dont `secondary_predecessor_id` retourne une
valeur — pas besoin de matérialiser une collection externe, la vue de la
branche amont sera déjà présente dans `view_by_node`/`srid_by_node` au moment
où l'exécution atteint ce nœud (garanti par l'ordre topologique, qui gère déjà
n'importe quel DAG — `topological_order` n'a jamais eu d'hypothèse
linéaire).

### 3.4 `_execute_transform_chain`

Pour les 4 op binaires, résolution de `join_view`/`join_srid` :

```python
secondary_pred = compiler.secondary_predecessor_id(node.id, edges)
if secondary_pred is not None:
    join_view = view_by_node[secondary_pred]
    join_srid = srid_by_node[secondary_pred]
else:
    join_view = f"node_{node.id}__join"          # chemin withCollectionId existant, inchangé
    join_srid = join_srid_by_node.get(node.id)
```

Aucun changement pour tout pipeline n'utilisant pas d'arête secondaire.

### 3.5 Callback de progression

`run_pipeline`/`_execute_transform_chain`/`_write_collection`/`_write_export`/
`_write_dataset` acceptent un paramètre optionnel :

```python
on_node_complete: Callable[[NodeStat], None] | None = None
```

appelé juste après chaque `stats.append(...)` (readers, transforms, writers).
Signature volontairement découplée de toute session DB — le runtime reste
pur/testable comme aujourd'hui (design SP-15a §1, non-but « aucune
optimisation », même principe de simplicité appliqué ici : c'est l'appelant
qui décide quoi faire de chaque `NodeStat`, jamais `runtime.py`).
`preview_pipeline` ne prend pas ce paramètre (exécution bornée par `up_to`,
jamais un run de fond à observer).

`jobs.py::run_pipeline_task` fournit le callback concret :

```python
def _make_progress_callback(session_factory, *, run_id: str, tenant_id: str):
    def _on_node_complete(stat: NodeStat) -> None:
        with request_scoped_session(session_factory) as s:
            pipelines_repo.append_node_stat(s, tenant_id=tenant_id, run_id=run_id, stat=stat)
    return _on_node_complete
```

`pipelines_repo.append_node_stat` (nouvelle fonction) fusionne dans le JSON
`PipelineRun.node_stats` existant (`{**current, stat.nodeId: stat.to_dict()}`)
et committe — même patron que les `with request_scoped_session(...)` déjà
multiples dans `run_pipeline_task` (`mark_running`, puis ce nouvel appel par
nœud, puis `mark_succeeded`/`mark_failed` à la fin, qui réécrit `node_stats`
en entier une dernière fois par simplicité/robustesse — idempotent, un
`NodeStat` déjà présent est juste réécrit à l'identique).

## 4. Validation (serveur + miroir client)

### 4.1 Structure du graphe — `app.configs.pipeline_validation`

`_check_linear_topology` devient `_check_topology`, toujours agnostique du
catalogue d'op (respecte la frontière déjà documentée par ce module) :

```python
def _check_topology(edges: list[PipelineEdge]) -> None:
    primary_count: dict[str, int] = {}
    secondary_count: dict[str, int] = {}
    for edge in edges:
        bucket = secondary_count if edge.role == "secondary" else primary_count
        bucket[edge.to] = bucket.get(edge.to, 0) + 1
    for node_id, count in primary_count.items():
        if count > 1:
            raise HTTPException(422, f"node '{node_id}' has more than one primary incoming edge")
    for node_id, count in secondary_count.items():
        if count > 1:
            raise HTTPException(422, f"node '{node_id}' has more than one secondary incoming edge")
```

Purement structurel (comptage par rôle) — ce module n'a toujours besoin
d'aucune connaissance de quels op acceptent une arête secondaire.

### 4.2 Cohérence op × arête secondaire — `app.pipelines.config_validation`

`_validate_node` (le **seul** validateur générique déjà enregistré pour tous
les op — pas de ventilation par op à mettre à jour) reçoit désormais `edges`
en plus de `session`/`node`/`user` (signature `NodeValidator` élargie, un
seul point d'enregistrement) :

```python
NodeValidator = Callable[[Session, PipelineNode, list[PipelineEdge], User], None]

# _COLLECTION_PARAM_FIELD (existant, inchangé) mappe déjà les 4 op binaires
# vers "withCollectionId" — même import package (app.pipelines.config_validation
# importe déjà app.pipelines.ops.schemas.OP_PARAMS), donc BINARY_OPS s'importe
# directement, sans duplication.
from app.pipelines.ops.schemas import BINARY_OPS

def _validate_node(session, node, edges, user) -> None:
    params = _validate_params(node)
    has_secondary_edge = any(e.to == node.id and e.role == "secondary" for e in edges)
    field = _COLLECTION_PARAM_FIELD.get(node.op)
    if node.op in BINARY_OPS:
        collection_id = getattr(params, field)
        if has_secondary_edge and collection_id is not None:
            raise HTTPException(422, f"{node.op}: cannot have both '{field}' and a secondary input edge")
        if not has_secondary_edge and collection_id is None:
            raise HTTPException(422, f"{node.op}: requires either '{field}' or a secondary input edge")
        if collection_id is not None:
            _require_readable_collection(session, user=user, collection_id=collection_id)
    elif has_secondary_edge:
        raise HTTPException(422, f"{node.op}: does not accept a secondary input edge")
    elif field is not None:
        # reste de la fonction (collectionId des op non-binaires : reader.collection,
        # writer.collection, writer.dataset) inchangé
        collection_id = getattr(params, field)
        if node.op in _WRITE_OPS:
            _require_writable_collection(session, user=user, collection_id=collection_id)
        else:
            _require_readable_collection(session, user=user, collection_id=collection_id)
```

### 4.3 Miroir client

- **`validation.ts`** : mêmes règles — comptage d'arêtes entrantes par rôle
  (≤1 `primary`, ≤1 `secondary`), XOR `withCollectionId`/arête secondaire
  pour les op où `opsCatalog[op].acceptsSecondaryInput` est vrai, rejet d'une
  arête secondaire ciblant un op où c'est faux. Piloté par le flag du
  catalogue, jamais une liste d'op codée en dur côté client (même principe
  que §2.3).
- **`graphOps.ts`** : `hasIncomingEdge(edges, nodeId, role)` devient sensible
  au rôle, pour que le canvas guide différemment le drag sur la poignée
  primaire vs secondaire. `hasCycle`/`wouldCreateCycle` restent inchangés
  (le rôle ne change pas la structure du graphe pour la détection de cycle).
- **`insertNodeOnEdge`** : en insérant un nœud sur une arête `role="secondary"`,
  la nouvelle arête `nouveauNœud → cible` hérite du rôle d'origine
  (`secondary`) ; celle `source → nouveauNœud` reste `primary`/non défini —
  permet d'insérer un `transform.filter`/`derive` juste avant l'entrée jointe
  d'un op binaire.

## 5. Canvas (shell)

### 5.1 Poignée secondaire

`PipelineNodeBox` (`PipelineCanvas.tsx`) : la poignée cible existante gagne un
`id="primary"` explicite ; pour les op où `acceptsSecondaryInput` est vrai
(lu depuis le catalogue déjà chargé par la page), une seconde `Handle
type="target" id="secondary"` s'ajoute, positionnée en haut du nœud
(`Position.Top`), stylée visuellement distincte (bordure pointillée).

`onConnect` lit `connection.targetHandle` pour poser le `role` de la nouvelle
arête ; la garde devient `hasIncomingEdge(edges, connection.target, role)`
(§4.3). Les arêtes `role="secondary"` sont rendues en tracé pointillé
(variante du edge type `insertable` existant, même bouton « + » d'insertion,
cf. §4.3 `insertNodeOnEdge`) pour rester lisibles dans un graphe qui branche.

`toFlowEdge` doit désormais poser `targetHandle` explicitement
(`e.role === "secondary" ? "secondary" : "primary"`) sur chaque arête rendue —
indispensable dès qu'un nœud a deux poignées cible, sinon React Flow ne peut
pas résoudre à laquelle une arête existante se raccroche à l'affichage.

`transform.merge` rejoint `INSERTABLE_TRANSFORMS` (libellé « Fusionner ») ;
la palette de création de nœuds (pilotée dynamiquement par `ops_catalog()`)
l'expose automatiquement, aucun changement requis là.

### 5.2 Progression en direct sur le canvas

`PipelineBuilderPage` passe `run.nodeStats` (déjà pollé toutes les 1,5 s par
`PipelineRunPanel`, cf. `_make_progress_callback` §3.5) + le statut du run
courant à `PipelineCanvas` → `PipelineNodeBox`. Chaque nœud déjà présent dans
`nodeStats` affiche un badge avec son `rowCount` ; le premier nœud de l'ordre
topologique (calculé côté client, comme le fait déjà `validation.ts`) encore
absent de `nodeStats` affiche un spinner tant que le run est `running`. Pure
lecture d'une donnée déjà pollée — aucun nouveau mécanisme réseau.

### 5.3 Aperçu cartographique

`PipelinePreviewPanel` (aujourd'hui strictement tabulaire) gagne une bascule
Tableau/Carte. `POST /pipelines/{id}/preview` renvoie déjà du GeoJSON décodé
(`ST_AsGeoJSON` côté `preview_pipeline`, aucun changement API) — nouveau
composant `PipelinePreviewMap.tsx` (MapLibre GL, déjà une dépendance du
shell) qui construit une `FeatureCollection` à partir des lignes retournées
et l'affiche (ajustement automatique de l'étendue). Bascule masquée si aucune
colonne `geometry` dans les lignes de l'étape sélectionnée.

## 6. Exposition MCP

Aucun nouvel outil. `explain_pipeline` (existant) expose `transform.merge` et
`acceptsSecondaryInput` gratuitement via `ops_catalog()` (déjà générique).
`create_pipeline`/`run_pipeline` acceptent déjà `nodes`/`edges` génériques —
un agent peut poser `role: "secondary"` sur une arête et créer un nœud
`transform.merge` sans aucun changement de schéma d'outil MCP.

## 7. Tests

### 7.1 Cœur (`core/tests/`)

- **Compilateur** : `compile_transform_sql("transform.merge", ...)` génère le
  bon SQL `UNION ALL BY NAME` ; `transform_output_srid` lève sur CRS
  différents pour `transform.merge` (même message que `intersection`) ;
  `secondary_predecessor_id` lève sur >1 arête secondaire, retourne `None`
  sans arête secondaire.
- **Runtime** :
  - fan-out — 1 `reader.collection` → 2 `writer.collection` distincts,
    assertion que les deux écritures ont bien lieu (première couverture
    explicite de ce cas, jusqu'ici jamais testé) ;
  - fusion par arête secondaire — pour chacun des 4 op binaires, un pipeline
    à 2 branches (2 readers → transform binaire via `role="secondary"`,
    `withCollectionId=None`) produit le résultat attendu ;
  - fusion par `withCollectionId` (chemin existant) — non-régression
    explicite pour les 3 op déjà livrés ;
  - callback `on_node_complete` invoqué exactement une fois par nœud, dans
    l'ordre topologique.
- **Validation** (`test_pipeline_config_validation.py`,
  `test_pipeline_node_validation.py`) : rejet si `withCollectionId` et arête
  secondaire présents ensemble ; rejet si aucun des deux ; rejet d'une arête
  secondaire sur un op non-binaire ; rejet de 2 arêtes primaires ou 2 arêtes
  secondaires vers le même nœud ; acceptation d'un fan-out (2 arêtes
  primaires depuis le **même** nœud source, vers 2 cibles différentes — pas
  la même contrainte que « 2 arêtes vers le même nœud »).
- **Route `GET /pipelines/ops`** : `acceptsSecondaryInput` vrai pour les 4 op
  binaires, faux pour les autres.
- **Job procrastinate** (`test_pipeline_jobs.py`) : `node_stats` se remplit
  de façon incrémentale (assertion sur l'état de `PipelineRun` entre deux
  nœuds, pas seulement à la fin).

### 7.2 Shell

- `graphOps.test.ts`/`validation.test.ts` : règles de rôle (comptage,
  XOR, rejet ciblé), `insertNodeOnEdge` préserve `role` sur l'arête aval.
- `PipelineCanvas.test.tsx` : poignée secondaire rendue seulement pour les op
  `acceptsSecondaryInput` ; connexion sur la poignée secondaire pose bien
  `role: "secondary"` ; badge/spinner de progression à partir de `nodeStats`.
- `PipelinePreviewPanel.test.tsx` : bascule Tableau/Carte, masquée sans
  colonne géométrie.

### 7.3 E2E (`shell/e2e/pipeline-builder.spec.ts`)

Extension du scénario existant : un second reader connecté sur la poignée
secondaire (`.react-flow__handle-top`, même patron que les sélecteurs
`.react-flow__handle-right/left` déjà utilisés) d'un `transform.join`,
assertion sur le résultat fusionné ; vérification qu'un nœud affiche un état
« en cours »/complété entre deux polls du mock `runPolls` déjà existant.

## 8. Compatibilité & risques

Aucune migration Alembic. Aucune route existante retirée ; `POST/PUT
/configs` (pipeline) et `GET /pipelines/ops` restent rétrocompatibles (champs
additionnels optionnels). Tout pipeline sauvegardé avant ce sous-plan continue
de fonctionner à l'identique (`role=None` partout, `withCollectionId` déjà
renseigné sur ses op binaires).

| Risque | Mitigation |
|---|---|
| Une arête secondaire pointe vers un nœud dont le prédécesseur secondaire n'est pas encore dans `view_by_node`/`srid_by_node` au moment de l'exécution (ordre topologique mal calculé) | `topological_order` est un vrai Kahn générique déjà indépendant de la linéarité (vérifié en session) — aucun changement requis là ; test explicite d'un DAG à embranchements profonds (3+ niveaux) pour lever le doute |
| `UNION ALL BY NAME` avec des types de colonnes incompatibles entre les deux branches (ex. `int` vs `text` sur la même colonne) | DuckDB lève une erreur de binder claire à l'exécution — traduite en `PipelineRuntimeError`, jamais un résultat silencieusement faux ; documenté comme comportement voulu, pas un bug à corriger ici |
| Le callback de progression ralentit un run par de trop nombreux commits (pipeline à beaucoup de nœuds) | Un commit par nœud reste largement sous la fréquence de poll du shell (1,5 s) pour tout pipeline réaliste (≤ quelques dizaines de nœuds) ; non traité comme un problème de performance dans ce sous-plan |
| Confusion visuelle sur un canvas très branché (beaucoup d'arêtes primaires/secondaires entremêlées) | Distinction visuelle (pointillé) posée dès ce sous-plan ; un vrai layout automatique reste hors périmètre (non-but §1) |
| La bascule carte affiche une géométrie invalide/non fermée produite par une op amont bugguée | MapLibre ignore silencieusement une géométrie GeoJSON invalide (comportement de la librairie, pas spécifique à ce sous-plan) — pas de validation de géométrie ajoutée ici, cohérent avec le reste du pipeline (aucune op ne valide la géométrie qu'elle produit) |
