# SP-15b — Pipeline : canvas no-code (design)

> **Date : 2026-08-06 · Statut : validé (brainstorm tenu en session)**
> Deuxième sous-partie de **SP-15 — ETL no-code « équivalent FME »** (feuille de
> route, jalon **M14**, arbitrage **A39**), Phase 2 de l'étude de faisabilité
> [`2026-07-22-etude-faisabilite-etl-fme-nocode-design.md`](2026-07-22-etude-faisabilite-etl-fme-nocode-design.md)
> (§5 « Canvas no-code (le cœur produit) »). SP-15a a livré le socle headless
> (document `Pipeline`, catalogue de 8 op, validation serveur, runtime DuckDB,
> job procrastinate, flag `CORE_ETL_ENABLED`, MCP) — entièrement auteur via
> MCP/REST, sans aucune surface shell. Ce sous-plan ajoute la surface shell :
> un éditeur visuel `PipelineBuilderPage`.
>
> Références : feuille de route (§SP-15, A39) · `CLAUDE.md` (règles
> d'architecture #1-4) · [`2026-08-05-sp15a-pipeline-socle-design.md`](2026-08-05-sp15a-pipeline-socle-design.md)
> (document `Pipeline`, catalogue d'op, routes REST, `CORE_ETL_ENABLED` —
> tout réutilisé tel quel ici) · SP-8a (`WcWidgetManifest`/
> `generatedPropsPanel`, mécanisme de panneau généré depuis un schéma,
> réutilisé pour l'inspecteur) · SP-14a/m (patron `NewItemButton`/
> `CatalogPage` d'ajout d'un nouveau kind d'item) · SP-6a (`ImportFileButton`,
> patron de poll de job asynchrone).

## 1. Objectif & non-buts

**Objectif.** Un utilisateur non-technicien construit visuellement un
pipeline (« nettoyer un CSV importé → écrire dans une collection ») sans
JSON ni MCP : glisser-déposer des opérations depuis une palette sur un
canvas, les relier, éditer leurs paramètres dans un panneau généré, prévisualiser
le résultat borné, puis exécuter et suivre le statut. Tout le calcul et la
validation restent côté serveur (SP-15a inchangé) — ce sous-plan n'ajoute
qu'une **surface d'édition** de plus (règle d'architecture #3 : l'`AppRenderer`
reste distinct du `PipelineBuilder`, deux surfaces d'édition, un seul moteur
analytique en dessous, déjà actée dans l'étude §6.2).

**Non-buts explicites** (reportés à SP-15c et suivants, Phases 3/4 de
l'étude) :

- Transformers spatiaux, sidecar `qgis_process`, `reader.connector`,
  `refreshPolicy`/triggers, `transform.sql` — aucun changement de catalogue
  d'op ici.
- Auto-complétion ou coloration syntaxique sur `filter.expr`/`derive.expr`
  (restent des champs texte bruts, cf. §5) — la validation de l'expression
  reste exclusivement à l'exécution (frontière déjà actée SP-15a §5.1).
- Fusion/push-down de nœuds, optimisation d'exécution — inchangé côté serveur.
- Undo/redo dans l'éditeur de pipeline — dépend de SP-19 (undo/redo général du
  builder), hors périmètre ici comme pour les autres éditeurs du builder
  aujourd'hui.
- Disposition automatique (auto-layout) du graphe — l'utilisateur positionne
  librement les nœuds ; `x`/`y` sont persistés tels quels (champ déjà présent
  dans le schéma depuis SP-15a, posé explicitement pour cet usage).

## 2. Routes & flux de création

### 2.1 `NewItemButton` — kind `"pipeline"`

`shell/src/shell/NewItemButton.tsx` : le type `Kind` gagne `"pipeline"`.
Contrairement à `"dataset"` (qui exige de choisir une collection source dans
le dialogue, car `DatasetPayload` n'a pas de valeur triviale valide), le
dialogue pipeline ne demande **que le titre** — comme `"app"`/`"dashboard"`/
`"map"`/`"site"`. Décision de session : plutôt que pré-remplir un pipeline à
2 nœuds via un choix de collections dans le dialogue, **le pipeline se
construit en local avant toute sauvegarde** (cf. §2.2) — le validateur
serveur exige déjà `≥ 1 reader` et `≥ 1 writer` (SP-15a `PipelinePayload
._validate_graph`), donc il n'existe pas de payload trivial valide à créer
immédiatement comme pour `"app"`. Le bouton « Créer » du dialogue, pour
`kind === "pipeline"`, **n'appelle pas l'API** : il navigue vers
`/pipelines/new` en passant le titre saisi via l'état de route (`navigate(...,
{ state: { title } })`).

### 2.2 `/pipelines/new` — mode brouillon local

Route nouvelle, rend `PipelineBuilderPage` en **mode non persisté** : état
local React (`useState<{ nodes: PipelineNode[]; edges: PipelineEdge[] }>`,
initialisé vide), aucune requête `useItem`/`usePipelineConfig`. Palette et
canvas pleinement utilisables dès l'arrivée sur la page. « Aperçu » et
« Exécuter » sont **désactivés** (les deux endpoints, `POST
/pipelines/{id}/preview` et `POST /pipelines/{id}/run`, exigent un `id`
existant — inapplicable avant la première sauvegarde). « Enregistrer » reste
désactivé tant que le graphe local ne passe pas la validation structurelle
côté client (§4.3) ; une fois valide, cliquer dessus déclenche le premier
`POST /configs` (titre passé par la route + `kind: "pipeline"` + payload
courant), puis `navigate` remplace l'URL par `/pipelines/{pk}/edit` (le
`pk` retourné par la création).

### 2.3 `/pipelines/{pk}/edit` — mode persisté

Même composant `PipelineBuilderPage`, chargé via `useItem(pk)` +
`usePipelineConfig(pk)` (nouveau hook, miroir de `useDatasetConfig`).
« Enregistrer » devient un `PUT` (même primitive que les autres kinds).
« Aperçu » et « Exécuter » s'activent : `pipelineId` est connu.

### 2.4 Catalogue & filtrage par type

`shell/src/api/types.ts` : `ResourceType` (ligne 2, union `"app" | "dashboard"
| "map" | "site" | "dataset" | "external" | "bookmark"`) gagne `"pipeline"`.
`CatalogPage.tsx` gagne l'option `"Pipeline"` dans son select de filtre par
type — même patron additif que `"bookmark"` (SP-14m). Aucune route API
nouvelle : le listing générique `GET /items?type=pipeline` (déjà générique
sur tout kind d'item) suffit.

### 2.5 `etlEnabled` côté shell

`InstanceInfo` (`shell/src/api/types.ts`, ligne 35, aujourd'hui `{ readOnly:
boolean }`) gagne `etlEnabled: boolean`. Le cœur retourne déjà ce champ
depuis SP-15a Task 1 (`GET /instance`) — seul le typage/consommation shell
manquait. `api/hooks.ts` (patron déjà en place ligne ~36-40 pour `readOnly`,
résolution silencieuse à une valeur par défaut sûre si l'endpoint ne répond
pas) applique le même filet à `etlEnabled` : défaut `false`. L'option
`"pipeline"` de `NewItemButton` et toute entrée de navigation pipeline sont
masquées quand `etlEnabled` est `false` — **masquage cosmétique uniquement**,
le vrai verrou reste le `403`/`404` serveur déjà en place (SP-15a §3.2, non
dupliqué ici).

## 3. Canvas — React Flow

### 3.1 Choix de librairie

Nouvelle dépendance shell : `@xyflow/react` (MIT, déjà anticipée comme
option d'évolution par l'étude de faisabilité §4.3). Décision de session :
partir directement sur React Flow plutôt qu'un rendu SVG fait main ou une
liste d'étapes réordonnable — malgré la contrainte serveur « linéaire+join »
(chaque nœud ≤ 1 arête entrante), le produit vise un rendu proche FME/Alteryx
et, avec le choix multi-chaînes (§3.3), un vrai graphe apporte une valeur de
lisibilité qu'une liste linéaire n'aurait pas.

### 3.2 Nœuds & arêtes

Composants de nœud custom par `PipelineNode.kind` (`reader`/`transform`/
`writer` — icône/couleur distinctes), enregistrés via la prop `nodeTypes` de
React Flow. `PipelineNode.x`/`y` (présents dans le schéma depuis SP-15a,
inutilisés jusqu'ici — cf. design SP-15a §4.1, « posés maintenant pour que
SP-15b n'ait pas à migrer le schéma ») se mappent directement sur la
`position` React Flow. L'état de travail du canvas reste `{ nodes:
PipelineNode[]; edges: PipelineEdge[] }` (les types générés depuis l'OpenAPI
du cœur, cf. `CLAUDE.md` « client TS du shell : types générés depuis
l'OpenAPI ») ; les `Node[]`/`Edge[]` React Flow sont **dérivés** à chaque
rendu, jamais un état parallèle à synchroniser.

### 3.3 Palette & multi-chaînes

Barre latérale listant les 8 op de `GET /pipelines/ops` (SP-15a), groupées
en trois sections : Sources (`reader.*`), Transforms (`transform.*`),
Écritures (`writer.*`). Décision de session : le canvas autorise
**plusieurs chaînes reader→writer indépendantes** dans un même document
(le validateur serveur ne l'interdit pas — il exige seulement `≥ 1 reader`,
`≥ 1 writer`, DAG acyclique, et `≤ 1` arête entrante par nœud globalement,
pas une seule chaîne connexe) : les entrées « reader »/« writer » de la
palette ne sont **jamais désactivées**, même si un nœud de ce kind existe
déjà. `POST /pipelines/{id}/preview?upTo={nodeId}` reste correct sans
changement dans ce cas : le compilateur SP-15a résout déjà les prédécesseurs
d'un nœud donné par remontée d'arêtes, indépendamment des autres chaînes du
document.

Glisser une op depuis la palette sur le canvas crée un nœud flottant à
`params: {}` (marqué invalide par l'inspecteur tant qu'il n'est pas
complété, §4.3). Glisser un op `transform.*` **sur une arête existante**
insère le nœud dans la chaîne : l'arête `from→to` est retirée, remplacée par
`from→nouveau` et `nouveau→to`.

### 3.4 Garde de connexion

Le gestionnaire `onConnect` de React Flow refuse (toast, pas d'effet) toute
connexion qui donnerait à un nœud une deuxième arête entrante — reflet côté
client de `app/configs/pipeline_validation.py::_check_linear_topology`
(SP-15a §4.2). Le serveur reste la garde définitive (`422`) ; ce refus
côté canvas n'est qu'un retour immédiat, pas une nouvelle règle.

### 3.5 Suppression

Sélection + touche Suppr (comportement par défaut React Flow), sans
dialogue de confirmation — même choix UX que la suppression de widget dans
le builder d'apps existant.

## 4. Données, validation & inspecteur

### 4.1 Hook de configuration

`usePipelineConfig(pk)` (nouveau, `shell/src/api/hooks.ts`), miroir exact de
`useDatasetConfig` : charge `BuilderConfig` par item, expose
`config.pipeline: PipelinePayload`. `useSavePipeline`/`useCreatePipeline`
(nouveaux hooks) miroir de `useSaveDataset`/`useCreateDataset`.

### 4.2 Catalogue d'op côté shell

Nouveau hook `usePipelineOps()` appelant `GET /pipelines/ops` (SP-15a),
mis en cache React Query — consommé par la palette (§3.3) et l'inspecteur
(§4.4).

### 4.3 Validation structurelle côté client

Nouvelle fonction pure `validatePipelineGraphLocally(nodes, edges)`
(`shell/src/builder/pipeline/validation.ts`) reflétant les quatre
vérifications structurelles serveur (SP-15a `pipeline_validation.py`) :
ids uniques (garanti par construction — chaque nœud créé reçoit un id
généré côté client), arêtes référençant des nœuds existants (idem), DAG
acyclique, `≤ 1` arête entrante par nœud (déjà appliqué en direct par la
garde de connexion §3.4, revérifié ici en défense en profondeur), `≥ 1`
reader, `≥ 1` writer — plus, **par nœud**, une vérification de forme des
`params` contre le JSON Schema de son `op` (réutilise le même mécanisme de
validation que `generatedPropsPanel`, cf. SP-8a). « Enregistrer » reste
désactivé et les nœuds incomplets sont surlignés tant que cette fonction ne
retourne aucune erreur. Le serveur reste autoritaire (revalidation complète
à chaque `POST`/`PUT /configs`, inchangée depuis SP-15a) — ceci n'est qu'un
retour rapide, même esprit que les erreurs de champ déjà remontées ligne à
ligne pour `visibleWhen`/CEL.

### 4.4 Inspecteur de nœud

Sélectionner un nœud ouvre un panneau latéral droit généré depuis le JSON
Schema de son `op` (§4.2), en réutilisant le renderer de
`shell/src/builder/wc/generatedPropsPanel.tsx` (déjà généré depuis un schéma
de props pour les widgets Web Components, SP-8a).

**Ajout côté cœur (petit, additif) — indice `format: "collection-id"`.**
Trois champs de paramètres référencent en réalité une collection :
`ReaderCollectionParams.collectionId`, `WriterCollectionParams.collectionId`,
`TransformJoinParams.withCollectionId` (`core/app/pipelines/ops/schemas.py`,
SP-15a). Sans indice, l'inspecteur générique les rendrait en simple champ
texte. Ces trois champs gagnent
`Field(..., json_schema_extra={"format": "collection-id"})` — additif,
aucune validation de forme changée (Pydantic ignore `json_schema_extra` pour
la validation elle-même, seul le JSON Schema exposé par `GET /pipelines/ops`
change). Le renderer shell branche sur `format: "collection-id"` pour
afficher un sélecteur de collection (même patron que `DataSourceSelect`,
déjà utilisé par le éditeur de dataset) au lieu d'un champ texte — même
convention que `WcWidgetManifest.props[].type === "dataSource"` pour les
widgets (§4.2 du schéma manifest, SP-8a). Le sélecteur de
`reader.collection`/`transform.join` liste les collections **lisibles**
par l'utilisateur courant ; celui de `writer.collection` liste les
collections **éditables** — même distinction que la validation serveur
(SP-15a `config_validation.py::_require_readable_collection`/
`_require_writable_collection`), dupliquée ici uniquement pour peupler le
select, jamais pour décider de l'autorisation (le serveur revalide toujours
à la sauvegarde).

`filter.expr`/`derive.expr`/`aggregate.metrics` restent des champs texte
bruts (pas d'auto-complétion ni de coloration syntaxique dans ce sous-plan,
cf. non-buts §1) — leur syntaxe SQL bornée n'est validée qu'à l'exécution
(frontière déjà actée, SP-15a §5.1, non rouverte ici).

## 5. Aperçu & exécution

### 5.1 Aperçu de données

Sélectionner un nœud (mode persisté uniquement, §2.3) active un panneau
« Aperçu » appelant `POST /pipelines/{id}/preview?upTo={nodeId}` (déjà
livré SP-15a, borné `LIMIT 50`) — rendu en simple tableau, requêté à nouveau
à chaque changement de sélection (pas de rafraîchissement automatique).

### 5.2 Exécution & suivi

Bouton « Exécuter » appelle `POST /pipelines/{id}/run` (déjà livré SP-15a),
puis poll `GET /pipelines/{id}/runs` toutes les 1500 ms — **patron exact**
de `shell/src/shell/ImportFileButton.tsx` (`poll()`, SP-6a) — jusqu'à ce que
le statut du run le plus récent quitte `queued`/`running`. Un historique des
runs (statut, horodatages, erreur si `failed`) s'affiche sous le canvas.

## 6. Permissions & sécurité

Rien de nouveau : le pipeline reste un item, `can(user, action, item)` déjà
en place (SP-15a §7). Les sélecteurs de collection de l'inspecteur (§4.4)
n'exposent que ce que l'utilisateur peut déjà lister/lire via les endpoints
existants — aucune nouvelle surface de lecture. Le masquage `etlEnabled`
(§2.5) est cosmétique, pas une porte d'autorisation (même principe que
`CORE_READ_ONLY_MODE` côté shell, SP-15a §3.2).

## 7. Compatibilité & tests

- Aucune migration : `"pipeline"` s'ajoute à `ResourceType` (shell) comme
  `"bookmark"` l'a fait en SP-14m ; aucun schéma cœur cassé (seul ajout :
  `json_schema_extra` sur 3 champs de params, additif).
- Les 43 specs E2E existantes restent vertes (nouvelle page/route isolée,
  aucune surface partagée modifiée hors `NewItemButton`/`CatalogPage`/
  `InstanceInfo` — additions strictement additives, testées par les specs
  existantes de ces pages).
- Tests Vitest nouveaux (composants) : drag-palette→création de nœud,
  insertion sur arête, garde de connexion (rejet 2e arête entrante),
  `validatePipelineGraphLocally` (cas valides/invalides), rendu du
  sélecteur de collection dans l'inspecteur pour `format: "collection-id"`,
  flux `/pipelines/new` → premier `POST` → redirection `/pipelines/{pk}/edit`.
- Nouvelle spec E2E `e2e/pipeline-builder.spec.ts` : construire un pipeline
  à 3 nœuds (reader→filter→writer) via le canvas contre un cœur mocké
  (interception de routes, même patron que `e2e/ingestion.spec.ts`),
  enregistrer, exécuter, observer le statut pollé jusqu'à succès — le
  livrable Phase 2 de l'étude de faisabilité (« un utilisateur
  non-technicien bâtit le cas d'usage #1 sans code »).
- Test cœur (pytest) : `GET /pipelines/ops` expose bien `format:
  "collection-id"` sur les 3 champs concernés (régression du JSON Schema).

## 8. Risques

| Risque | Garde-fou |
|---|---|
| React Flow habille une topologie qui reste, sémantiquement, contrainte (linéaire+join par nœud) — décalage entre ce que le canvas *montre* comme possible (glisser-déposer libre) et ce que le serveur *accepte* | Garde de connexion client (§3.4) + validation structurelle client (§4.3) donnent un retour immédiat ; le serveur reste la garde définitive, déjà testée SP-15a |
| Le mode brouillon local (`/pipelines/new`) perd le travail de l'utilisateur en cas de rechargement de page avant le premier `Enregistrer` | Accepté pour ce MVP (même risque que n'importe quel formulaire non sauvegardé de l'app aujourd'hui) ; persistance de brouillon (localStorage) laissée à un sous-plan ultérieur si le besoin se confirme |
| Le choix multi-chaînes complique l'aperçu/l'inspection si le graphe devient grand (plusieurs sous-graphes visuellement mélangés) | Pas d'auto-layout dans ce sous-plan (§1) — l'utilisateur organise manuellement ; à revisiter si l'usage réel le justifie |
| `json_schema_extra` sur les 3 champs `collection-id` mal propagé (round-trip Pydantic→JSON Schema→TS) | Test cœur dédié (§7) régresse explicitement sur la présence du `format` dans `GET /pipelines/ops` |
| Deux mécanismes de rendu de panneau (widgets SP-8a vs pipeline) divergent avec le temps | Réutilisation stricte du même renderer `generatedPropsPanel` (§4.4), pas une copie — toute évolution du mécanisme bénéficie aux deux surfaces |
