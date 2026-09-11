# GAP-17 — Génération NL→SQL / NL→requête-visuelle dans le copilote

Date : 2026-09-06. Ferme **GAP-17**
(`docs/revue/2026-09-04-analyse-gaps.md:253`) : « Aucune génération de requête
en langage naturel avec revue humaine avant exécution (NL→SQL ou NL→CEL) —
GeoStudio a un copilote orchestrant des outils MCP, mais pas de génération de
requête analytique en langage naturel dans SQL Lab ou la requête visuelle.
Felt (« AI SQL »), Metabase (Metabot), FME (AI Assist) le font tous, avec le
même patron « montre la requête générée, l'utilisateur valide ». »

**Portée** : brainstormée avec Tanguy à ~5-8 j-h dans l'analyse de gaps
initiale ; l'exploration menée pour ce document confirme qu'elle est
significativement plus large (~12-18 j-h, cf. §1) — Tanguy en a été informé
et a choisi de garder la pleine portée plutôt que de la réduire (couvrir SQL
Lab **et** les trois volets Filtrer/Joindre/Résumer de la requête visuelle,
sur les deux pages). Ce document explique pourquoi (§1.4-1.6) et documente
l'architecture retenue en conséquence.

## 0. Décisions déjà prises (brainstorm, non re-débattues ici)

1. SQL Lab : génération NL→SQL complète.
2. Requête visuelle : génération NL→filtres **et** NL→jointure **et**
   NL→métriques — les trois volets de la pipeline Filtrer→Joindre→Résumer,
   pas seulement les filtres.
3. Mécanisme : nouveaux outils **MCP** dans le copilote existant (pas un
   endpoint dédié séparé) — appellent le LLM via `llm_provider.py`, ne
   modifient jamais l'état de la page ni la base pendant la conversation
   (règle déjà actée par `tools_allowlist.py`, cf. §1.1).
4. Portage du `CopilotPanel` (ou variante) sur `SqlLabPage.tsx` **et**
   `VisualQueryWizardPage.tsx` — aujourd'hui monté uniquement sur
   `AppBuilderPage.tsx`.
5. Nouveaux outils **CLIENT** (patron `addWidget`/`setFilter`) pour insérer
   le résultat généré comme brouillon — jamais exécuté automatiquement.
6. Revue humaine obligatoire : le SQL/la config générée n'est jamais
   auto-exécutée — apparaît comme un brouillon, l'utilisateur valide
   explicitement (bouton « Exécuter » de SQL Lab, action explicite du
   wizard).
7. Frontière de sécurité SQL inchangée : le SQL généré emprunte exactement
   le même chemin d'exécution (`run_analyst_sql`, sandbox DuckDB) que le SQL
   tapé à la main — jamais de raccourci.

## 1. Vérifié avant d'écrire (piège CLAUDE.md n°3/12)

### 1.1 Règle architecturale du copilote (`app/copilot/tools_allowlist.py`)

```python
ALLOWED_MCP_TOOL_NAMES = frozenset({
    "search_catalog", "list_items", "explain_dataset", "run_analytics_query",
    "create_item", "create_form_app",
})
```

Docstring : « le copilote édite la config déjà ouverte dans le builder
uniquement via des opérations côté client (clientOps, jamais écrites en base
pendant la conversation) ; il peut CRÉER un nouvel item via les mêmes outils
qu'un agent MCP externe, jamais muter un item existant directement. » Les
deux nouveaux outils (`generate_sql_query`, `generate_visual_query`)
respectent cette règle à la lettre : ils lisent (introspection de schéma) et
génèrent (appel LLM), ne créent et n'écrivent jamais rien. Le docstring sera
mis à jour pour les nommer explicitement (Task dédiée, §3.10).

### 1.2 Boucle d'orchestration (`app/copilot/routes.py::_run_turn`)

Un tour : `provider.chat(messages, all_tools)` → si `tool_calls`, chaque
appel dont le nom est dans `ALLOWED_MCP_TOOL_NAMES` part en loopback HTTP vers
`/mcp` (`McpLoopbackSession.call_tool`), son résultat texte est réinjecté
comme message `role: "tool"`, et la boucle continue (jusqu'à
`MAX_TOOL_ITERATIONS=6`) ; tout nom hors de cet ensemble devient un
`ClientOp` renvoyé tel quel dans la réponse HTTP, **jamais exécuté côté
serveur**, et clôt le tour (retour immédiat dès qu'un `client_ops` existe).
`TURN_TIMEOUT_SECONDS=30.0` enveloppe tout `_run_turn` via
`asyncio.wait_for`.

**Implication pour les 2 nouveaux outils MCP** : ils s'exécutent comme
`generate_sql_query`/`generate_visual_query` — un appel *outil* qui, dans son
propre corps, fait un **second** appel LLM (`get_llm_provider().chat(...)`,
imbriqué dans l'appel-outil lui-même, lequel est déjà dans une itération de
la boucle qui vient d'appeler le LLM une première fois pour décider d'invoquer
l'outil). Un tour realistic-case portant un appel `generate_*` consomme donc
potentiellement **2 à 3 appels LLM séquentiels** (décision d'appeler l'outil →
appel interne au corps de l'outil → décision finale de répondre/d'appeler
`applyXxxDraft`) dans le même budget de 30 s — un risque de latence réel,
documenté en §6, non traité par une nouvelle politique de budget dédiée (hors
périmètre assumé, cf. §5).

### 1.3 Fournisseur LLM et garde d'egress (`llm_provider.py` + `egress.py`)

`get_llm_provider()` retourne `FakeLLMProvider` (dev/test, scripté par
liste de `LLMTurn`) ou `OpenAICompatibleLLMProvider` (prod,
`CORE_LLM_API_URL`/`CORE_LLM_API_KEY`/`CORE_LLM_MODEL`), toujours derrière
`build_guarded_async_client` (SSRF, `CORE_LLM_EGRESS_ALLOWLIST`). Les deux
nouveaux outils **réutilisent** `get_llm_provider()` tel quel — aucune
deuxième voie d'egress, aucune nouvelle allowlist.

### 1.4 Où vit `CopilotPanel` et ce qu'il suppose déjà — **le point qui change tout**

`shell/src/builder/copilot/CopilotPanel.tsx` est monté à un seul endroit :
`shell/src/pages/AppBuilderPage.tsx:510`, à l'intérieur du panneau de
réglages du builder, gardé par `copilotEnabled` (capacité instance-wide,
`InstanceInfo.copilotEnabled`, indépendante de la page). Sa signature :

```ts
CopilotPanel({ itemId: string; config: AppConfig; activePageId: string;
  setDraft: (update: (prev: AppConfig | null) => AppConfig | null) => void })
```

Trois suppositions internes, chacune fausse sur les deux pages cibles :

1. **`config: AppConfig`** — le type exact de `ItemClient.copilotTurn`
   (`shell/src/api/types.ts:439-448`) déclare littéralement
   `currentConfig: AppConfig`, pas `Record<string, unknown>`. Côté cœur, le
   champ est déjà générique (`CopilotTurnRequest.currentConfig:
   dict[str, Any]`, `routes.py:51`) — **seule l'interface TS est trop
   étroite**. Ni `SqlLabPage` (état = une chaîne SQL + un historique local,
   `shell/src/lib/sqlLabHistory.ts`) ni `VisualQueryWizardPage` (état =
   `title`/`baseCollectionId`/`filters: FilterRow[]`/`join: JoinConfig |
   null`/`summary: SummaryConfig | null`/`refreshPolicy`, six `useState`
   distincts) n'ont de `AppConfig`.
2. **`setDraft`** — le mécanisme d'application des `clientOps` est
   `applyClientOp(op, config, activePageId)` (`applyClientOp.ts`), qui
   mute un **objet `AppConfig` unique** via `getPageLayout`/`setPageLayout`.
   Aucune des deux pages cibles n'a d'objet de configuration unique à
   patcher de cette façon — leurs états sont des primitives/objets plats
   locaux au composant.
3. **`itemId: string` (obligatoire, `min_length=1`)** — `SqlLabPage` n'a
   **aucun** concept d'item (ce n'est pas un éditeur d'un item unique).
   `VisualQueryWizardPage` a un `pipelinePk: string | null` — `null` en mode
   création, exactement le cas qui échouerait la validation Pydantic actuelle
   (`itemId: str = Field(min_length=1, ...)`).

**Conclusion (répond explicitement à la question posée par la tâche)** : le
montage n'est **pas trivial**. `CopilotPanel` tel quel n'est réutilisable ni
sur `SqlLabPage` ni sur `VisualQueryWizardPage` sans un refactor. La
correction consiste à extraire la mécanique de conversation (historique,
envoi, jeton MCP, rendu du fil de discussion) dans un composant générique
neutre vis-à-vis du type de configuration, et à garder trois enveloppes
fines par surface (§2.6).

`useMcpToken()` (`shell/src/builder/copilot/useMcpToken.ts`), en revanche,
est déjà totalement générique (aucune dépendance au builder) — réutilisable
tel quel par les trois enveloppes.

### 1.5 Formes d'état exactes de la requête visuelle (`shell/src/builder/visualQuery/*`)

- **`FilterRow`** (`compileFilter.ts:5`) : `{ column: string; operator:
  "eq"|"neq"|"gt"|"gte"|"lt"|"lte"|"contains"; value: string }`. Un pont
  SQL↔`FilterRow[]` **existe déjà** :
  `compileFilterRowsToSql(rows, schema): string` et
  `decompileSqlToFilterRows(expr): FilterRow[] | null` — mais c'est un
  parseur *best-effort*, couplé au caractère près à la forme exacte que
  `compileFilterRowsToSql` émet elle-même (regex ancrée sur
  `"col" = 'val'` avec échappement précis des guillemets, `LIKE '%…%'`
  pour `contains`, etc. — cf. le commentaire de `decompileSqlToFilterRows` :
  « best-effort : ne comprend que la forme exacte produite par
  compileFilterRowsToSql »). **Décision (§2.7)** : ne pas emprunter ce pont
  pour le LLM — demander à `generate_visual_query` de produire directement
  du JSON `FilterRow[]` plutôt que du SQL à redécompiler (le format
  s'y prête, mais mal : un pont conçu pour rouvrir un pipeline
  **auto-généré par ce même code** n'a aucune raison de tolérer la syntaxe
  SQL variable qu'un LLM produirait pour la même intention).
- **`JoinConfig`** (`inferSchema.ts:4`) : `{ collectionId: string; on:
  string; how: "inner" | "left" }` — structure déjà plate, aucun pont
  SQL↔JSON n'existe et **aucun n'est nécessaire** : c'est directement la
  forme que `QueryJoinPicker` consomme comme `value`/`onChange`. Le LLM peut
  la produire telle quelle.
- **`SummaryConfig`** (`inferSchema.ts:16`) : `{ groupBy: string[]; metrics:
  MetricConfig[] }`, avec `MetricConfig = { alias: string; function:
  "count"|"countDistinct"|"sum"|"avg"|"median"|"percentile"|"stddev"|
  "min"|"max"; sourceColumn: string | null; p: number | null }`. Un pont
  **existe** dans l'autre sens : `decompileMetrics(metrics: Record<alias,
  sqlExpr>): MetricConfig[] | null` (`compilePipeline.ts:180`), lui aussi
  *best-effort*, ancré sur les expressions SQL exactes que `metricExpr`
  produit (`count(*)`, `count(distinct "col")`, `quantile_cont("col",
  0.95)`, `stddev_samp("col")`…). **Même décision** : ne pas l'emprunter —
  demander du JSON `MetricConfig[]` directement.

**Conclusion sur la représentation retenue (répond explicitement à la
question posée)** : aucun des deux ponts SQL↔JSON existants n'est réutilisé
pour la génération LLM→wizard. Les deux sont conçus pour un usage différent
(round-trip d'un pipeline **déjà compilé par ce code**, pas parsing de sortie
libre d'un LLM) et leur nature *best-effort*/silencieusement-`null`-sur-forme-
inattendue en ferait un point d'échec silencieux mal diagnostiqué si on
l'exposait à du texte généré. `generate_visual_query` renvoie donc du JSON
structuré, validé côté serveur par des modèles Pydantic dédiés (mêmes
énumérations que `FilterOperator`/`MetricFunction`/`JoinConfig.how`, cf.
§2.1.2), puis re-validé côté client de façon tolérante (même patron que
`applyClientOp.ts::updateWidgetProps`, qui ignore silencieusement toute clé
hors schéma plutôt que de faire confiance à l'entrée).

### 1.6 Frontière de sécurité SQL (`app/analytics/sql_sandbox.py`)

`run_analyst_sql` : matérialise chaque collection référencée dans une vue
temporaire (`_materialize`, nom = `col.id` quoté par
`app.sql_ident.quote_ident_duckdb`), **puis** verrouille
(`enable_external_access=false`, `lock_configuration=true`), **puis**
exécute — jamais l'inverse. La frontière réelle est DuckDB, pas l'AST
(`parse_ast`/`validate_select_only`/`collect_table_refs` ne servent qu'à
rejeter tôt le non-SELECT et décider quoi matérialiser). Exposée par
`POST /v1/analytics/sql` (`app/features/routes.py:431`), gardée par
`Privilege.ANALYTICS_SQL_LAB_ACCESS`, `allowed` = toutes les collections
visibles de l'utilisateur (`list_visible_collections`, `can_see_all` selon
`Privilege.ADMIN_COLLECTIONS_MANAGE`), keyed par `col.id` — **c'est le nom de
table que le SQL généré doit utiliser dans `FROM`**.

**Critère d'acceptation direct** : `generate_sql_query` ne fait **jamais**
d'appel à `run_analyst_sql`/`conn.execute` — il produit une chaîne de
caractères, point. Le SQL retourné n'est exécuté que si l'utilisateur clique
« Exécuter » dans `SqlLabPage`, qui appelle exactement le même
`client.runAnalyticsSql(sql)` → `POST /v1/analytics/sql` →
`run_analyst_sql` que pour du SQL tapé à la main — aucun nouveau chemin
d'exécution.

### 1.7 Où vivent les nouveaux outils MCP (contrat de couches)

`app/mcp/tools/` est un paquet d'un module par domaine depuis SP-43
(`analytics.py`, `pipelines.py`, etc.), enregistré par
`app/mcp/tools/__init__.py::register_tools`. Le contrat de couches
(`pyproject.toml`, `[[tool.importlinter.contracts]]`) place `app.mcp`
**au-dessus** d'`app.copilot` (`layers = ["app.main", "app.mcp",
"app.copilot", "app.public", ...]`) — un module `app.mcp.tools.*` peut donc
importer `app.copilot.llm_provider`/`app.copilot.egress` sans exemption
nouvelle (import descendant, direction déjà permise). C'est la direction
inverse de l'appel réseau existant (`app.copilot.routes` appelle `/mcp` en
loopback HTTP, jamais un import direct d'`app.mcp`) — aucun cycle introduit,
c'est un second usage, indépendant, de `llm_provider.py` par un module situé
plus haut dans le contrat.

Nouveau fichier : `core/app/mcp/tools/query_generation.py` (pas ajouté à
`analytics.py`, pour ne pas mélanger deux responsabilités — agrégation
structurée existante vs génération LLM), enregistré dans
`register_tools()` aux côtés des onze modules existants.

### 1.8 Mode démo / lecture seule

`is_copilot_enabled()` (`app/auth/dependency.py:85`) retourne déjà `False`
en mode démo (I6 de la revue de projet 2026-08-20) — le routeur
`/v1/copilot/turn` n'est alors pas monté du tout
(`test_route_is_not_mounted_in_read_only_mode`). Les deux nouveaux outils
héritent de cette garde automatiquement, sans changement : ils ne sont
enregistrés côté MCP que si `is_copilot_enabled()` est vrai au démarrage — à
vérifier explicitement (Task dédiée), mais aucune nouvelle garde à écrire.

### 1.9 Privilège des nouveaux outils

`POST /v1/analytics/sql` exige `Privilege.ANALYTICS_SQL_LAB_ACCESS` en plus
de la visibilité de collection. `generate_sql_query` réplique cette même
garde (`require_privilege(session, user,
Privilege.ANALYTICS_SQL_LAB_ACCESS.value)`) avant tout accès schéma/appel
LLM — défense en profondeur : un jeton MCP valide ne doit pas contourner ce
qu'impose la route REST équivalente. `generate_visual_query` ne crée ni
n'écrit rien (la création réelle de pipeline/collection reste derrière ses
propres gardes existantes, inchangées, au moment de `handleCreate()`) — sa
seule garde nécessaire est `require_collection_read` par collection
consultée (déjà une vérification d'accès complète), sans privilège
supplémentaire.

## 2. Architecture

### 2.1 Outils MCP

#### 2.1.1 `generate_sql_query`

```python
@server.tool()
async def generate_sql_query(ctx: Context, collectionId: str, question: str) -> dict:
```

- `access_token = get_access_token()`, `resolve_actor` (patron identique à
  tous les tools de `app/mcp/tools/*`).
- `require_privilege(session, user, Privilege.ANALYTICS_SQL_LAB_ACCESS.value)`
  — lève `ValueError` (pas `HTTPException`, patron MCP existant) si absent ;
  `require_privilege` prend déjà cette forme ou est enveloppée pour le faire
  (vérifier la signature réelle avant d'écrire ce wrapper, elle peut déjà
  lever `HTTPException` seulement — dans ce cas, dupliquer la vérification
  via `has_privilege` + `raise ValueError` explicite, patron déjà utilisé par
  `require_collection_read`/`require_access` d'`identity.py`).
- `col = require_collection_read(session, user=user, collection_id=collectionId)`.
- `info = introspect_table(session, col.table_name)` (capturer
  `TableNotFound`/`UnsupportedTable` → `ValueError`, patron
  `analytics.py::run_analytics_query`).
- `schema = table_info_to_schema(info)` — même forme JSON que
  `GET /v1/collections/{id}/schema` (`CollectionSchema` côté TS).
- Construit un message utilisateur pour le LLM :
  « Écris une unique requête SQL SELECT (DuckDB) en lecture seule répondant à
  la question, en utilisant EXACTEMENT `"{collectionId}"` comme nom de table
  dans FROM. Colonnes disponibles : {schema JSON}. N'ajoute aucun texte hors
  SQL, aucune ponctuation de fermeture de bloc de code n'est nécessaire mais
  tolérée. Question : {question} ».
- `provider = get_llm_provider(); turn = await provider.chat(messages=[...],
  tools=[])` — **`tools=[]`** : c'est un appel de génération one-shot, pas un
  nouveau tour d'orchestration (le protocole `LLMProvider.chat` accepte déjà
  une liste vide).
- Nettoyage : retire un éventuel bloc de code Markdown (`` ```sql `` /
  `` ``` ``) en tête/fin de `turn.text` (fonction utilitaire dédiée,
  testée avec/sans fence, avec langage annoté ou non).
- Si le texte nettoyé est vide → `raise ValueError("le fournisseur LLM n'a
  renvoyé aucun SQL")`.
- Retourne `{"sql": cleaned_text}` — **jamais** un objet enrichi
  d'« explication » : un objet plus simple à valider/appliquer, cohérent
  avec le patron « montre la requête, l'utilisateur valide » du benchmark
  cité par GAP-17 (Felt/Metabot montrent le SQL brut).
- Ne fait **jamais** `conn.execute`/`run_analyst_sql` (critère
  d'acceptation, §3).

#### 2.1.2 `generate_visual_query`

```python
@server.tool()
async def generate_visual_query(
    ctx: Context, baseCollectionId: str, question: str, joinCollectionId: str | None = None
) -> dict:
```

- `col = require_collection_read(session, user=user, collection_id=baseCollectionId)`,
  introspection → `base_schema` (`table_info_to_schema`).
- Si `joinCollectionId` fourni : même résolution → `joined_schema` (aucune
  garde de privilège supplémentaire au-delà de la lecture — cohérent avec
  §1.9).
- Prompt : donne les deux schémas (ou un seul), la liste exacte des
  opérateurs de filtre valides (`eq`/`neq`/`gt`/`gte`/`lt`/`lte`/`contains`),
  des fonctions de métrique valides
  (`count`/`countDistinct`/`sum`/`avg`/`median`/`percentile`/`stddev`/
  `min`/`max`, avec la règle `p` uniquement pour `percentile`, `0 < p <
  100`), des types de jointure (`inner`/`left`), et un exemple de forme JSON
  de sortie attendue. Demande une réponse **JSON uniquement**, de forme :
  `{"filters": [...], "join": null | {...}, "summary": null | {...}}`.
- `turn = await provider.chat(messages=[...], tools=[])`.
- Extraction JSON : retire les fences Markdown éventuelles, puis
  `json.loads`. `json.JSONDecodeError` → `ValueError("réponse LLM non-JSON")`.
- **Validation stricte** par modèles Pydantic dédiés (nouveaux, dans
  `query_generation.py`, jamais réutilisés comme modèles API publics — noms
  distincts des types TS pour ne pas laisser croire à un contrat partagé
  généré) :
  ```python
  class GeneratedFilterRow(BaseModel):
      column: str
      operator: Literal["eq", "neq", "gt", "gte", "lt", "lte", "contains"]
      value: str

  class GeneratedJoin(BaseModel):
      collectionId: str
      on: str
      how: Literal["inner", "left"]

  class GeneratedMetric(BaseModel):
      alias: str
      function: Literal["count", "countDistinct", "sum", "avg", "median",
                         "percentile", "stddev", "min", "max"]
      sourceColumn: str | None = None
      p: float | None = None

  class GeneratedSummary(BaseModel):
      groupBy: list[str] = []
      metrics: list[GeneratedMetric] = []

  class GeneratedVisualQuery(BaseModel):
      filters: list[GeneratedFilterRow] = []
      join: GeneratedJoin | None = None
      summary: GeneratedSummary | None = None
  ```
  `GeneratedVisualQuery.model_validate(parsed)` — `pydantic.ValidationError`
  → `ValueError` avec un message court (jamais l'erreur Pydantic brute, trop
  verbeuse pour un tour de conversation).
- Contrôle supplémentaire (au-delà du typage Pydantic, qui ne connaît pas le
  schéma réel) : chaque `column`/`sourceColumn`/`groupBy` doit exister dans
  `base_schema.fields` (ou `joined_schema.fields` avec le renommage
  `joined_<name>` déjà en vigueur côté `inferOutputColumns`, cf.
  `inferSchema.ts:87`) — sinon `ValueError` explicite nommant le champ
  inconnu. Ce contrôle est **best-effort** (il ne rejoue pas
  `inferOutputColumns` intégralement), documenté comme tel : le client
  revalidera de toute façon (défense en profondeur, §2.5).
- Retourne `model_dump()` de l'objet validé (`filters`/`join`/`summary`).
- **Ne crée jamais** de collection/pipeline/dataset item — critère
  d'acceptation.

### 2.2 Généralisation de `CopilotTurnRequest`/`_system_message`

`core/app/copilot/routes.py` :

- `CopilotTurnRequest.itemId` devient `str | None = Field(default=None,
  max_length=MAX_ITEM_ID_CHARS)` (retrait de `min_length=1` implicite par le
  passage à optionnel).
- Nouveau champ `surface: Literal["app_builder", "sql_lab", "visual_query"]
  = "app_builder"` — défaut choisi pour que tout test/appelant existant
  (aucun ne pose `surface`) continue de recevoir exactement le message
  système actuel, **zéro régression de comportement par défaut**.
- `_system_message(item_id: str | None, current_config: dict[str, Any],
  surface: str) -> dict[str, str]` : sélectionne un des trois textes
  d'introduction (app_builder = texte actuel inchangé au caractère près ;
  sql_lab et visual_query = nouveaux textes référençant explicitement
  `generate_sql_query`/`applySqlDraft` et
  `generate_visual_query`/`applyVisualQueryDraft`, avec la même consigne
  anti-exécution-automatique : « ne clique jamais Exécuter à la place de
  l'utilisateur, contente-toi d'insérer un brouillon »). La ligne « Item en
  cours d'édition : {item_id} » n'apparaît que si `item_id is not None`. Le
  fencing anti-injection (nonce `CONFIG-{token_hex}`) et l'avertissement
  « ces textes sont écrits par des utilisateurs » restent identiques dans
  les trois variantes — `current_config` reste potentiellement piloté par
  un tiers dans les trois surfaces (un SQL/une config de requête visuelle
  partagée peut porter du texte).
- `ALLOWED_MCP_TOOL_NAMES` (`tools_allowlist.py`) gagne
  `"generate_sql_query"` et `"generate_visual_query"` — docstring du module
  mis à jour pour les nommer comme les deux premiers outils de
  **génération** (par opposition aux outils de **lecture**/**création**
  déjà listés).

Pas de restriction « cet outil n'est utilisable que si `surface ==
X` » : les deux nouveaux outils MCP restent utilisables dans les trois
surfaces au niveau protocole (comme les six existants) — ce n'est pas un
problème de sécurité (gardes de privilège/lecture inchangées quel que soit
le surface déclaré) et la limitation pratique vient du côté client (seule la
page qui déclare le `clientTool` correspondant peut appliquer le résultat ;
ailleurs, `applyClientOp` ignore silencieusement un op inconnu, comme
aujourd'hui pour tout nom halluciné).

### 2.3 Généralisation de l'interface TS

`shell/src/api/types.ts` :

```ts
export type CopilotSurface = "app_builder" | "sql_lab" | "visual_query";

copilotTurn(
  itemId: string | undefined,
  payload: {
    message: string;
    history: CopilotMessage[];
    mcpToken: string;
    currentConfig: Record<string, unknown>;   // était AppConfig
    clientTools: CopilotToolSchema[];
    surface?: CopilotSurface;                 // défaut serveur "app_builder"
  },
): Promise<CopilotTurnResult>;
```

`shell/src/api/domains/apps.ts::copilotTurn` (implémentation) ne change pas
de corps (`request("POST", "/copilot/turn", { itemId, ...payload })` —
`JSON.stringify` élide déjà une clé `undefined`, donc `itemId: undefined`
part bien comme absent, pas comme `null`) ; conservé dans ce fichier plutôt
que déplacé (l'interface `ItemClient` reste unique et plate, la localisation
du fichier d'implémentation est un détail d'organisation interne, aucun
appelant n'y est sensible).

`CopilotPanel.tsx` (App Builder) passe explicitement `surface:
"app_builder"` bien que ce soit le défaut serveur — lisibilité, et
robustesse si le défaut change un jour.

### 2.4 Outils CLIENT

`shell/src/builder/copilot/sqlLabClientTools.ts` (nouveau) :

```ts
export function buildSqlLabClientToolSchemas(): ClientToolSchema[] {
  return [{
    name: "applySqlDraft",
    description:
      "Insère une requête SQL générée comme brouillon dans l'éditeur SQL Lab. " +
      "Ne l'exécute jamais — l'utilisateur doit cliquer sur Exécuter.",
    inputSchema: {
      type: "object",
      properties: { sql: { type: "string", description: "Requête SQL brouillon" } },
      required: ["sql"],
    },
  }];
}
```

`shell/src/builder/copilot/applySqlLabClientOp.ts` (nouveau) :

```ts
export function applySqlLabClientOp(raw: RawClientOp, setSql: (sql: string) => void): void {
  if (raw.op !== "applySqlDraft") return;
  const sql = String(raw.args.sql ?? "").trim();
  if (!sql) return;
  setSql(sql);
}
```

`shell/src/builder/copilot/visualQueryClientTools.ts` (nouveau) — schéma
englobant les trois volets en un seul outil (cohérent avec la décision de
fusion/merge déjà en vigueur pour `setFilter`) :

```ts
export function buildVisualQueryClientToolSchemas(): ClientToolSchema[] {
  return [{
    name: "applyVisualQueryDraft",
    description:
      "Applique des filtres/une jointure/un résumé générés à la requête visuelle en cours " +
      "d'édition. Ne crée ni n'exécute rien — l'utilisateur doit valider le formulaire.",
    inputSchema: {
      type: "object",
      properties: {
        filters: { type: "array", items: FILTER_ROW_JSON_SCHEMA },
        join: { type: ["object", "null"], properties: JOIN_JSON_SCHEMA_PROPERTIES },
        summary: { type: ["object", "null"], properties: SUMMARY_JSON_SCHEMA_PROPERTIES },
      },
    },
  }];
}
```

`shell/src/builder/copilot/applyVisualQueryClientOp.ts` (nouveau) :

```ts
export function applyVisualQueryClientOp(
  raw: RawClientOp,
  setters: {
    setFilters: (rows: FilterRow[]) => void;
    setJoin: (join: JoinConfig | null) => void;
    setSummary: (summary: SummaryConfig | null) => void;
  },
): void {
  if (raw.op !== "applyVisualQueryDraft") return;
  const args = raw.args as { filters?: unknown; join?: unknown; summary?: unknown };
  if (Array.isArray(args.filters)) {
    setters.setFilters(args.filters.filter(isValidGeneratedFilterRow));
  }
  if (args.join === null) setters.setJoin(null);
  else if (isValidGeneratedJoin(args.join)) setters.setJoin(args.join);
  if (args.summary === null) setters.setSummary(null);
  else if (isValidGeneratedSummary(args.summary)) setters.setSummary(args.summary);
}
```

`isValidGeneratedFilterRow`/`isValidGeneratedJoin`/`isValidGeneratedSummary`
sont des gardes de type locales à ce fichier, réutilisant les unions
littérales déjà exportées (`FilterOperator` de `compileFilter.ts`,
`MetricFunction`/`JoinConfig["how"]` de `inferSchema.ts`) — jamais de
confiance aveugle dans le JSON reçu, même s'il a déjà été validé côté
serveur (défense en profondeur, patron déjà en vigueur dans
`applyClientOp.ts::updateWidgetProps`). Un filtre/une jointure/un résumé
mal formé est silencieusement ignoré (même choix que le reste
d'`applyClientOp.ts` — jamais une exception qui casserait tout le tour).

### 2.5 Extraction de `CopilotChat` (composant générique)

`shell/src/builder/copilot/CopilotChat.tsx` (nouveau) — extrait de
`CopilotPanel.tsx` toute la mécanique indépendante d'`AppConfig` : état
`history`/`input`/`sending`/`error`/`lastOpsSummary`, `useMcpToken()`, appel
`client.copilotTurn`, rendu du fil de discussion/formulaire d'envoi.

```ts
function CopilotChat({
  itemId,
  surface,
  contextPayload,
  clientTools,
  opLabels,
  onClientOps,
}: {
  itemId?: string;
  surface: CopilotSurface;
  contextPayload: Record<string, unknown>;
  clientTools: CopilotToolSchema[];
  opLabels: Record<string, string>;
  onClientOps: (ops: CopilotClientOp[]) => void;
}): JSX.Element
```

`CopilotPanel.tsx` (App Builder, **signature externe inchangée** —
`itemId`/`config`/`activePageId`/`setDraft`, les tests existants
(`CopilotPanel.test.tsx`) continuent de passer sans modification) devient
un enveloppe fine :

```tsx
export function CopilotPanel({ itemId, config, activePageId, setDraft }: {...}) {
  return (
    <CopilotChat
      itemId={itemId}
      surface="app_builder"
      contextPayload={config}
      clientTools={buildClientToolSchemas()}
      opLabels={OP_LABELS}
      onClientOps={(ops) =>
        setDraft((d) =>
          d === null
            ? d
            : (ops as RawClientOp[]).reduce(
                (acc, op) => applyClientOp(op, acc, activePageId),
                d,
              ),
        )
      }
    />
  );
}
```

`shell/src/builder/copilot/SqlLabCopilotPanel.tsx` (nouveau) :

```tsx
export function SqlLabCopilotPanel({ sql, setSql }: { sql: string; setSql: (s: string) => void }) {
  return (
    <CopilotChat
      surface="sql_lab"
      contextPayload={{ sql }}
      clientTools={buildSqlLabClientToolSchemas()}
      opLabels={{ applySqlDraft: t("copilot.opSqlDraftApplied") }}
      onClientOps={(ops) =>
        (ops as RawClientOp[]).forEach((op) => applySqlLabClientOp(op, setSql))
      }
    />
  );
}
```

`shell/src/builder/copilot/VisualQueryCopilotPanel.tsx` (nouveau), mêmes
principes, `contextPayload={{ baseCollectionId, filters, join, summary }}`,
`onClientOps` appelant `applyVisualQueryClientOp` avec les trois setters du
wizard.

Pas d'`itemId` transmis par les deux nouvelles enveloppes — absent (`undefined`),
cohérent avec §1.4.3/§2.2.

### 2.6 Montage sur les deux pages

`shell/src/pages/SqlLabPage.tsx` : ajoute, dans le slot `inspect` existant
(actuellement occupé seulement par l'historique), un bloc conditionnel
`{copilotEnabled && <SqlLabCopilotPanel sql={sql} setSql={setSql} />}` —
`copilotEnabled` lu via `useInstanceInfo()`/`getInstanceInfo()` (même patron
que `AppBuilderPage.tsx:68`, nouvel appel dans ce fichier qui ne l'utilise
pas aujourd'hui).

`shell/src/pages/VisualQueryWizardPage.tsx` : ajoute, dans le slot
`inspect` (aux côtés de `PipelineScheduleEditor`), un bloc conditionnel
`{copilotEnabled && baseSchema && <VisualQueryCopilotPanel ... />}` —
gardé en plus par `baseSchema` (une collection de base doit être choisie
avant de pouvoir générer quoi que ce soit, `generate_visual_query` exige
`baseCollectionId`), même style de garde que le bloc `{baseSchema && (...)}`
déjà présent pour `QueryFilterBuilder`/`QueryJoinPicker`/`QuerySummaryBuilder`.

### 2.7 Décision sur la représentation structurée (rappel, cf. §1.5)

Confirmé après exploration complète : **aucun** des deux ponts SQL↔JSON
existants (`compileFilterRowsToSql`/`decompileSqlToFilterRows`,
`decompileMetrics`) n'est réutilisé pour la génération LLM. Le format de
sortie retenu pour `generate_visual_query` est du JSON structuré direct,
correspondant terme à terme aux types TS `FilterRow`/`JoinConfig`/
`SummaryConfig`, validé côté serveur (Pydantic, §2.1.2) puis re-validé côté
client (§2.4). C'est un écart assumé par rapport à la piste suggérée par la
tâche (« réutiliser `decompileSqlToFilterRows` si le format s'y prête ») —
documenté ici plutôt qu'exécuté à la lettre, cf. piège CLAUDE.md n°3.

### 2.8 Point d'arrêt humain — où il vit, précisément, pour chaque cible

- **SQL Lab** : `applySqlDraft` écrit dans `SqlLabPage`'s `sql` (état React
  local, `useState`). Rien n'appelle `run.mutate(sql)` (la mutation qui
  déclenche `POST /v1/analytics/sql`) automatiquement — ce bouton
  (`t("sqlLab.runButton")`) reste le seul déclencheur, actionné par
  l'utilisateur. Le brouillon généré est visible, éditable, dans le même
  `<textarea>` que le SQL tapé à la main — aucune distinction visuelle
  requise par ce plan (hors périmètre, cf. §4).
- **Requête visuelle** : `applyVisualQueryDraft` écrit dans `filters`/
  `join`/`summary` (état React local du wizard). Rien n'appelle
  `handleCreate()` (qui provisionne la collection de sortie et lance le
  pipeline) automatiquement — le bouton « Créer »/« Mettre à jour »
  (`t("visualQuery.createButton")`/`updateButton`) reste l'unique
  déclencheur. Les mêmes gardes de validité déjà en vigueur
  (`filtersValid`/`joinValid`/`summaryValid`, `isFilterRowValueValid`)
  s'appliquent identiquement à un état posé par le copilote ou par la main
  de l'utilisateur — aucun contournement possible : ce sont des dérivations
  pures de l'état React, pas des gardes conscientes de la provenance de la
  valeur.

## 3. Critères d'acceptation

1. `generate_sql_query`/`generate_visual_query` ne font, dans leur corps,
   **aucun** appel à `run_analyst_sql`/`conn.execute`/`create_item`/
   `create_pipeline_item`/toute route d'écriture — vérifié par lecture du
   code et par un test qui espionne (`monkeypatch`) chacune de ces fonctions
   et assure qu'elle n'est jamais appelée pendant l'exécution du tool.
2. Le SQL retourné par `generate_sql_query`, une fois copié tel quel dans
   `SqlLabPage` et soumis via `client.runAnalyticsSql`, traverse exactement
   `POST /v1/analytics/sql` → `run_analyst_sql` — un test d'intégration
   bout-en-bout (FakeLLMProvider scripté pour renvoyer un SQL valide sur une
   collection de test réelle, sous `postgis-test`) prouve le round-trip
   génération→exécution sans nouveau chemin.
3. Aucun tour de conversation n'exécute automatiquement le SQL/la config
   générée : un test qui scripte un `FakeLLMProvider` appelant
   `generate_sql_query` puis `applySqlDraft` vérifie que la réponse HTTP du
   tour ne contient qu'un `ClientOp` (jamais un résultat de requête exécutée)
   et que rien côté serveur n'a touché la base au-delà de la lecture de
   schéma.
4. `generate_visual_query` rejette (ValueError → `isError` tool result)
   toute sortie LLM qui référence une colonne absente du schéma introspecté,
   un opérateur/une fonction hors énumération, ou un JSON malformé — chaque
   cas a un test dédié.
5. `itemId` absent (SQL Lab) ou `null`/absent (requête visuelle en création)
   ne fait plus échouer `POST /v1/copilot/turn` — test de non-régression sur
   `CopilotTurnRequest` sans `itemId`.
6. Le message système par défaut (`surface` omis) reste caractère-pour-
   caractère identique à l'actuel — tous les tests existants de
   `test_copilot_routes.py` passent sans modification.
7. `CopilotPanel.tsx` (App Builder) — tests existants
   (`CopilotPanel.test.tsx`) passent sans modification après le refactor
   d'extraction de `CopilotChat` (caractérisation, pas de régression de
   comportement observable).
8. `is_copilot_enabled() == False` continue de désactiver les deux
   nouveaux outils exactement comme les six existants (routeur non monté) —
   test de non-régression explicite.
9. `uv run lint-imports` reste vert sans nouvelle exemption (la direction
   `app.mcp.tools.query_generation -> app.copilot.llm_provider`/`egress`
   est déjà permise par l'ordre de couches existant, cf. §1.7).
10. Diff `openapi.json`/`core-schema.d.ts` non vide et cohérent : le seul
    schéma qui change de forme est `CopilotTurnRequest` (`itemId` optionnel,
    `surface` ajouté) — aucune route n'apparaît/disparaît (aucune nouvelle
    route REST, seulement de nouveaux tools MCP, invisibles dans
    `openapi.json`, cf. piège CLAUDE.md n°1 — le diff attendu ici est donc
    **petit**, pas vide : à vérifier, pas supposer).

## 4. Hors périmètre (explicite)

- **NL→CEL générique** hors SQL Lab/requête visuelle (expressions CEL du
  builder no-code, `visibleWhen`, colonnes calculées) — mentionné par
  GAP-17 comme alternative, mais le brainstorm a tranché sur NL→SQL et
  NL→requête-visuelle uniquement.
- Apprentissage/fine-tuning d'un modèle sur les requêtes de ce tenant.
- Historique des prompts de génération (au-delà de l'historique de
  conversation déjà existant, `CopilotMessage[]`, borné à
  `MAX_HISTORY_MESSAGES=40`) — pas de journal dédié « SQL généré par IA »
  distinct de l'historique SQL Lab existant (`sqlLabHistory.ts`), qui ne
  distingue déjà pas l'origine d'une requête (tapée ou insérée par le
  copilote) — un signal visuel « généré par le copilote » n'est pas ajouté.
- Génération **multi-tables sans collection de base explicite** pour
  `generate_sql_query` : le tool nécessite un `collectionId` — pas de
  résolution automatique « devine la bonne table depuis la question »
  (le LLM peut déjà, dans la même conversation, utiliser `search_catalog`/
  `list_items`/`explain_dataset` — outils déjà allowlistés — pour identifier
  la collection à cibler avant d'appeler `generate_sql_query`, mais ce
  chantier n'ajoute aucune résolution serveur dédiée).
- Distinction visuelle (badge, couleur) entre un SQL/une config posée par
  l'utilisateur et un brouillon généré par le copilote, dans `SqlLabPage`/
  `VisualQueryWizardPage`.
- Nouvelle politique de budget de latence pour les appels LLM imbriqués
  (§1.2) — `TURN_TIMEOUT_SECONDS`/`LLM_CALL_TIMEOUT_SECONDS` restent
  inchangés à 30 s chacun.
- Réachabilité de navigation de `SqlLabPage`/`VisualQueryWizardPage`
  (GAP-80/GAP-81, notés par SP-61 comme des gaps distincts) — hors périmètre
  de GAP-17, non traité ici.
- Restriction de `ALLOWED_MCP_TOOL_NAMES` par `surface` (cf. §2.2) —
  les deux nouveaux outils restent utilisables au niveau protocole dans les
  trois surfaces.

## 5. Risques et limites assumées

- **Latence des appels imbriqués** (§1.2) : un tour portant un
  `generate_*` peut approcher ou dépasser 30 s en usage réel — non résolu,
  documenté. Le filet existant (`asyncio.wait_for` → 504) reste le seul
  garde-fou.
- **Validation « colonne existe » best-effort** côté `generate_visual_query`
  (§2.1.2) : ne rejoue pas `inferOutputColumns` intégralement (pas de
  vérification de compatibilité de type, seulement d'existence du nom) — le
  garde-fou fort reste `filtersValid`/`joinValid`/`summaryValid` côté
  client, inchangés, qui s'appliquent quelle que soit la provenance de
  l'état.
- **Fidélité du LLM aux instructions de chaînage** (« appelle `generate_*`
  PUIS `applyXxxDraft` ») : comme pour `addWidget`/`setFilter` existants,
  rien ne garantit qu'un vrai fournisseur LLM respecte cette consigne plutôt
  que de décrire le SQL en prose dans sa réponse texte — risque déjà présent
  pour les 6 outils existants, pas une nouvelle classe de risque introduite
  par ce chantier.
