# Les quatre bouchons à coût faible (SP-23)

> Étape 4 du séquencement recommandé du plan d'action
> `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` (§6) : chantiers
> **4.18**, **4.6**, **4.15** et **4.16** de la vague 4. Spec écrite le
> 2026-08-21, après vérification de l'état réel du dépôt — les quatre sont
> encore ouverts, et deux d'entre eux se sont révélés plus larges que ce que
> le plan supposait (cf. §3.2 et §3.4).

## 1. Contexte & objectif

Les vagues 0, 1 et 2 du plan d'action sont closes (SP-20 clôture, SP-21
déployabilité, SP-22 filet qualité statique), et la première release `v0.1.0`
est publiée. Le §6 du plan place ensuite « les quatre bouchons à coût faible,
dès que la vague 1 est close » : quatre chantiers marqués **S**, tous adossés
à des fondations déjà livrées et testées, dont le plan dit qu'ils forment
« le meilleur rapport valeur/effort du document, toutes vagues confondues ».

Ce qu'ils ont en commun : dans chaque cas le cœur sait déjà faire la chose, et
c'est la surface exposée à l'utilisateur qui manque ou qui est incomplète.

| # | Chantier | Ce qui existe déjà | Ce qui manque |
|---|---|---|---|
| 4.18 | Historique de versions atteignable | `GET /configs/{id}/revisions` et `POST /configs/{id}/rollback`, audités, depuis SP-0 | `ItemClient` n'a aucune des deux méthodes ; aucune page du shell ne les appelle |
| 4.6 | Le catalogue voit les 12 types | `ResourceType` (TS) porte déjà les 12 valeurs ; `openItemAsync` route déjà 5 types spéciaux | Le `<select>` Type de `CatalogPage` n'en propose que 3 ; `alert` et `external` n'ont pas de destination |
| 4.15 | Agrégats manquants | Un seul modèle Pydantic (`AggregateRequestBody`) partagé par REST, MCP, mini-serveur autoporté et chemin ArcGIS | 5 agrégats seulement (`count`/`sum`/`avg`/`min`/`max`) |
| 4.16 | Grains temporels manquants | `bucket` part directement dans `DATE_TRUNC`, qui accepte les six grains | Le `Literal` n'en autorise que 3 — **et aucune UI du shell ne laisse choisir `bucket`** |

Objectif de sortie : les quatre critères de sortie du plan sont atteints et
prouvés, sans baisse des compteurs de test de référence.

## 2. Périmètre

Les quatre chantiers, avec deux élargissements assumés et tranchés en session
(§4) :

1. **4.15 couvre les deux surfaces d'agrégat**, pas seulement le chemin
   analytique — l'assistant de requête visuelle SP-14o compile ses métriques
   vers du SQL brut par un chemin entièrement distinct.
2. **4.18 corrige au passage un trou de validation** que le chantier rend
   atteignable pour la première fois (`rollback_config` ne repasse par aucun
   validateur de payload).

**Hors périmètre, explicitement** :

- L'auteur d'une révision. `config_revisions` n'a pas d'`actor_id` ; le
  « qui » est déjà dans `audit_log` (`config.update`, `config.rollback`) et
  relève du chantier 4.20 (journal d'audit consultable).
- La prévisualisation d'une version sans la restaurer. Aucune route ne lit
  les données d'une version ancienne ; en ajouter une est un incrément
  séparé.
- Le tri, les facettes et la recherche spatiale du catalogue (4.7, 4.8).
- L'élargissement de l'heuristique `bucketFor()` (§3.4).
- Toute correction fonctionnelle trouvée en passant hors des fichiers déjà
  touchés : notée en suivi non bloquant, pas corrigée ici.

## 3. Mécanisme, par chantier

### 3.1 — Agrégats manquants (4.15)

#### Chemin analytique — `core/app/analytics/aggregate.py`

`AggregateMeasure` gagne un champ `p: float | None = None`. `_agg_expr` gagne
quatre branches :

| `agg` | Expression DuckDB | Vide / indéfini |
|---|---|---|
| `countDistinct` | `COUNT(DISTINCT col)` | `COALESCE(…, 0)` |
| `median` | `QUANTILE_CONT(col, 0.5)` | `null` |
| `percentile` | `QUANTILE_CONT(col, p/100)` | `null` |
| `stddev` | `STDDEV_SAMP(col)` | `null` |

`col` reste `TRY_CAST("nom" AS DOUBLE)` comme pour les agrégats existants,
sauf `countDistinct` qui compte la colonne telle quelle (`_qi(field)`) — une
valeur textuelle distincte n'a pas à être castable en `DOUBLE` pour être
comptée, et un `TRY_CAST` fusionnerait à tort toutes les valeurs non
numériques sur `NULL`.

`_validate_fields` gagne la validation de `p`, appliquée à chaque mesure
(`request.measures[*]`) **et** à la requête simple (`request.p`) :

- `agg == "percentile"` sans `p` → `UnknownAggregateField("p", …)` ;
- `p` hors de `]0, 100[` → refus ;
- `p` fourni avec un autre `agg` → refus (pas d'ignorance silencieuse).

`AggregateRequestBody` gagne symétriquement `p: float | None = None`, pour que
la forme « requête simple » (`agg`/`field` sans `measures`) puisse aussi
demander un percentile — `_measures_for` le propage dans l'unique
`AggregateMeasure` qu'il construit.

**Décision sur la valeur vide.** Les cinq agrégats existants font
`COALESCE(…, 0)`. `countDistinct` garde ce contrat : compter zéro chose
distincte donne bien 0. `median`, `percentile` et `stddev` ne l'appliquent
pas : la médiane d'un ensemble vide et l'écart-type d'une ligne unique ne
valent pas 0, ils sont indéfinis, et renvoyer 0 produirait un graphique
faux plutôt qu'un trou. Ils renvoient `null`. **C'est le premier `null` que
ce chemin peut produire** — les widgets consommateurs doivent l'afficher
« — » et non « 0 », et c'est un point de test à part entière, pas un détail
d'implémentation.

#### Chemin ArcGIS — `core/app/harvest/live_query.py`

`_STAT_TYPES` gagne `stddev` seul : c'est un `statisticType` natif du
Feature Service. `countDistinct`, `median` et `percentile` n'ont pas
d'équivalent et continuent d'échouer par le chemin `ArcgisQueryError` déjà en
place — précédent SP-16b : échouer explicitement plutôt que mal-évaluer en
silence.

**Limite assumée** : le choix de `STDDEV_SAMP` (plutôt que `STDDEV_POP`) côté
DuckDB vise la parité avec ce que renvoie `statisticType: "stddev"` d'ArcGIS.
Cette parité est **affirmée sur la base de la documentation, pas mesurée
contre un service ArcGIS réel** — aucun n'est disponible dans l'environnement
de développement. À vérifier si un écart de valeur est un jour constaté entre
un dataset local et son équivalent moissonné.

#### Assistant de requête visuelle — `shell/src/builder/visualQuery/`

Surface entièrement distincte : les métriques de `transform.aggregate` sont
des **chaînes SQL DuckDB libres**, validées à l'exécution par
`validate_bounded_expr` (`app/pipelines/expr_validation.py`, qui n'autorise
qu'une expression scalaire sans référence de table). Les quatre nouvelles
fonctions passent cette validation telles quelles : **le cœur n'a rien à
changer pour cette surface.**

- `inferSchema.ts` — `MetricFunction` gagne les quatre valeurs ;
  `MetricConfig` gagne `p: number | null`. `inferOutputColumns` classe
  `countDistinct` en `integer` et `median`/`percentile`/`stddev` en
  `double precision`.
- `compilePipeline.ts` — `metricExpr` compile :
  `count(distinct "col")`, `median("col")`, `quantile_cont("col", 0.9)`,
  `stddev_samp("col")`.
- `compilePipeline.ts` — `decompileMetrics` élargit sa reconnaissance. Sa
  regex actuelle est `^(sum|avg|min|max)\("((?:[^"]|"")+)"\)$` ; elle doit
  reconnaître les quatre nouvelles formes **exactement telles que
  `metricExpr` les produit** et ré-extraire le `p` de `quantile_cont`.
- `QuerySummaryBuilder.tsx` — les quatre fonctions dans le `<select>` et son
  `FUNCTION_LABELS` ; un champ numérique `p` affiché uniquement pour
  `percentile`.

**Le risque réel est là.** L'aller-retour compile↔décompile est ce qui permet
de rouvrir « Modifier la requête » ; `decompileMetrics` renvoyant `null` fait
retomber l'utilisateur sur `PipelineBuilderPage` **sans erreur visible** (repli
attendu par conception, cf. le commentaire de
`decompilePipelineToWizardState`). Une forme non reconnue ne casse donc rien
de bruyant — elle dégrade silencieusement. Chaque nouvelle fonction a son test
de round-trip.

#### Chemin analytique — surfaces shell

`DataSourcePanel.tsx` porte **deux** `<select>` d'agrégation (la requête
simple et chaque mesure de la liste) ; les deux listent les cinq mêmes
options en dur. Les quatre nouvelles y sont ajoutées, avec un champ `p`
conditionnel par site. Les libellés français sont définis **une fois** dans
un module partagé, pas dupliqués entre les deux `<select>`.

### 3.2 — Grains temporels manquants (4.16)

`AggregateRequestBody.bucket` passe à
`Literal["hour", "day", "week", "month", "quarter", "year"]`. `DATE_TRUNC`
accepte les six sans changement de SQL — le cœur se limite à cette ligne et à
ses tests.

**Ce que le plan n'avait pas vu.** Aucune UI du shell ne permet aujourd'hui de
choisir `bucket` : `grep bucket` sur `DataSourcePanel.tsx` et
`DatasetEditPage.tsx` ne renvoie rien. Le champ n'est réglable que par MCP,
par l'API ou dans une config brute ; les seuls appels qui le passent viennent
de `bucketFor(timeRange)`, une heuristique automatique de
`comparisonWindow.ts` (`≤ 31 j → day`, `≤ 180 j → week`, sinon `month`)
utilisée par les widgets indicateur et graphique en mode comparaison.

Le critère de sortie du plan — « une série annuelle se construit dans
l'assistant, pas en SQL » — **n'est donc pas atteignable en élargissant le
`Literal` seul**. Il faut créer le contrôle qui manque :

- `DataSourcePanel` gagne un `<select>` « Grain temporel » (option vide =
  aucun regroupement temporel), à côté du champ `groupBy`. Il n'est actif que
  si un `groupBy` **unique** est posé — c'est déjà l'invariant que
  `_validate_fields` impose côté serveur (`bucket requires a single-field
  groupBy`), l'UI ne fait que le refléter au lieu de laisser l'auteur
  construire une requête que le serveur refusera.
- `chartOption.ts` — `offsetLabel` complète ses libellés pour les six unités
  (aujourd'hui `day`/`week` puis un repli « Mois » qui étiquetterait à tort
  une série trimestrielle ou annuelle).
- `comparisonWindow.ts` — le type `BucketGranularity` s'élargit aux six
  valeurs, pour rester le seul nom du concept côté shell.

**`bucketFor()` n'est pas touché.** C'est l'heuristique de la fenêtre de
comparaison, pas un choix d'auteur ; l'élargir à `hour`/`year` changerait le
comportement de widgets déjà livrés et testés sans que personne ne l'ait
demandé. Décision explicite, pas un oubli.

### 3.3 — Le catalogue voit les 12 types (4.6)

**Source unique de vérité.** Un nouveau module
`shell/src/api/resourceTypes.ts` exporte un
`RESOURCE_TYPE_LABELS: Record<ResourceType, string>` **exhaustif** (12
entrées, `Record` et non `Partial<Record>`). `CatalogPage` engendre ses
`<option>` depuis ce record au lieu d'une liste écrite à la main, et
`ItemCard` y lit ses libellés au lieu du `Partial<Record<ResourceType,
string>>` local qu'il porte aujourd'hui (une seule entrée, `external`).

C'est ce qui donne le critère de sortie (« aucun type de `ResourceType` n'est
absent du sélecteur ») : un 13ᵉ type ajouté à `ResourceType` **casse la
compilation** tant qu'il n'a pas son libellé. Même argument d'exhaustivité
prouvée par le typage que `StaticItemClient` en SP-18a — pas une promesse
tenue à la main.

**Navigation.** `openItemAsync` (`shell/src/shell/routes.tsx`) gagne deux
branches :

- `external` → `/items/{pk}`. Item moissonné, aucune config éditable —
  exactement la raison pour laquelle `tileset3d`/`terrain3d` y vont déjà.
- `alert` → lecture de la config puis `/datasets/{datasetItemId}/edit`
  (`AlertRulePayload.datasetItemId`), une règle d'alerte s'éditant dans la
  section « Alertes » de la page de son dataset. Copie du patron async déjà
  écrit pour `bookmark`, y compris le `catch` qui lève `openError` —
  l'appelant est un `(pk, type) => void` fire-and-forget, une promesse rejetée
  y serait une unhandled rejection sans retour utilisateur.

`site` n'est pas touché : `/apps/{pk}/edit` est déjà sa bonne destination,
c'est là que `NewItemButton` l'envoie après création.

### 3.4 — Historique de versions atteignable (4.18)

#### Cœur — le garde-fou que ce chantier rend nécessaire

`rollback_config` (`core/app/configs/routes.py`) **ne repasse par aucun** des
huit validateurs `_validate_*` que `update_config` exécute (dataset, bookmark,
pipeline, alert, report, tileset3d, terrain3d, portée d'extension), ni par
`_require_etl_enabled_for_pipeline` / `_require_export_enabled_for_report`.

Tant que rien dans le shell n'appelait la route, c'était théorique. La câbler
sur cinq éditeurs la rend atteignable : restaurer une vieille version d'un
pipeline ou d'une alerte peut ressusciter une référence vers une collection
supprimée depuis, ou réactiver une capacité désactivée depuis. La route
exécute donc **la même séquence de validation que `update_config`** sur la
config restaurée, avant d'écrire la version N+1, et répond 422 sinon (message
nommant la version refusée et la raison). Sans ce garde-fou, 4.18 livre un
bouton capable de casser une config — c'est un correctif appartenant au
chantier, pas un élargissement.

Le rollback reste **non destructif et en avant** : il crée une version N+1
copiant les données de la version choisie, il n'efface aucune révision. Ce
comportement existant n'est pas modifié.

#### `ItemClient`

Deux méthodes nouvelles — les premières du sas sur les révisions, **clés par
`pk` d'item** et non par `configId` :

- `listConfigRevisions(pk): Promise<{ version: number; createdAt: string }[]>`
- `rollbackConfig(pk, version): Promise<void>`

Ce choix de clé n'est pas cosmétique : **aucun des cinq éditeurs ne connaît
son `configId`** (vérifié, `grep configId` ne renvoie rien sur les cinq
fichiers) — ils travaillent tous par `pk` d'item. `CoreItemClient` résout donc
par `GET /configs/by-item/{pk}`, qui renvoie l'`id`, avant d'appeler
`/configs/{id}/revisions` et `/configs/{id}/rollback`. C'est déjà la monnaie
courante du client (dix appels `by-item` existants), et cela évite d'ajouter
deux routes serveur `by-item` supplémentaires. Coût : un aller-retour de plus
à l'ouverture du panneau, mis en cache par react-query.

`rollbackConfig` renvoie `void` : l'éditeur recharge ensuite sa config par le
getter typé qu'il utilise déjà (`getAppConfig`, `getMapConfig`, …). C'est la
convention en place — `saveAppConfig` renvoie déjà `void`, et `ItemClient`
n'expose jamais un `ConfigRead` brut, dont le champ `config` est l'union des
onze `kind`.

`StaticItemClient`
(SP-18a) doit les écrire aussi : elle passe de 83 à 85 signatures explicites,
**sans cast d'échappement** — c'est la discipline qui fait que TypeScript
prouve qu'aucune méthode n'a été oubliée. Un bundle statique n'a pas de cœur
en ligne : les deux rejettent avec l'erreur « non disponible hors ligne »
utilisée par ses autres méthodes d'écriture.

Aucune route serveur n'est ajoutée ni modifiée dans sa signature (le 422 du
garde-fou ci-dessus ne change pas le schéma de réponse), donc la
régénération OpenAPI/TS doit produire un diff **vide** — à vérifier, pas à
supposer : c'est la classe d'oubli la plus récurrente de ce dépôt.

#### Shell — `ConfigHistoryPanel`

Un composant unique `ConfigHistoryPanel({ pk, onRestored })` :

- liste des versions (la plus récente en tête), format « Version 7 —
  14/08/2026 10:32 », la version courante marquée ;
- un bouton « Restaurer » par ligne, absent sur la version courante ;
- états de chargement / d'erreur explicites — une liste vide ne doit jamais
  être indiscernable d'un échec réseau (défaut déjà rencontré en SP-16b et
  SP-17b).

Monté sur les cinq éditeurs adossés à une config : `AppBuilderPage`,
`MapEditorPage`, `DatasetEditPage`, `PipelineBuilderPage`, `ReportEditPage`.
La route serveur étant générique (`/configs/{id}`), le coût marginal par
éditeur est le point de montage seul.

#### Interaction avec l'undo/redo SP-19

« Restaurer » avec un brouillon modifié ouvre une **confirmation** disant que
les modifications non enregistrées seront perdues. Après confirmation :
`POST rollback`, le brouillon est remplacé par la réponse, **et la pile undo
SP-19 est réinitialisée**.

La réinitialisation n'est pas un détail : la pile ne peut pas défaire une
écriture serveur, et la laisser pleine ferait croire à l'auteur qu'un
`Ctrl+Z` annule la restauration alors qu'il ne toucherait que son brouillon
local, le serveur portant déjà la version N+1. C'est un point d'intégration
réel avec `useUndoableDraft` (`shell/src/pages/AppBuilderPage.tsx`) : le hook
doit exposer une capacité de reset qu'il n'a pas aujourd'hui, et cette
capacité doit être posée **sans** remuter une ref à l'intérieur d'un updater
`useState` — c'est exactement le défaut Critical trouvé en revue finale de
SP-19, invisible en E2E (qui tourne contre un build de prod) et visible
uniquement sous `<StrictMode>`.

## 4. Décisions prises en session (2026-08-21)

1. **Périmètre du SP** : les quatre bouchons (4.18, 4.6, 4.15, 4.16), suivant
   l'étape 4 du séquencement du plan — pas le lot Carte (étape 5), pas la
   vague 3.
2. **4.18 monté sur les cinq éditeurs**, pas seulement le builder d'app : la
   route est déjà générique, et un composant unique évite quatre panneaux
   divergents plus tard.
3. **4.18 sans auteur de révision** : version + date seulement, aucune
   migration. Le « qui » relève de 4.20.
4. **4.18, brouillon sale** : confirmation bloquante + réinitialisation de la
   pile undo. Écarté : rendre la restauration annulable par `Ctrl+Z` (deux
   notions d'annulation qui divergent) et ajouter une route de
   prévisualisation.
5. **4.15, `percentile` paramétré** par un champ `p` sur la mesure, plutôt que
   trois agrégats fixes `p50`/`p90`/`p95`.
6. **4.15, chemin ArcGIS** : `stddev` ajouté (natif), les trois autres
   refusés proprement. Écarté : désactiver les agrégats non supportés dans
   l'UI selon la source — cela imposerait au shell une matrice de capacités
   par source qui n'existe nulle part.
7. **4.15 couvre les deux surfaces**, y compris l'assistant de requête
   visuelle. Élargissement assumé : il fait sortir 4.15 du calibre « S ».
8. **`bucketFor()` non touché** (§3.2).
9. **`median`/`percentile`/`stddev` renvoient `null`** sur un ensemble vide,
   `countDistinct` renvoie 0 (§3.1).

## 5. Ordre d'exécution recommandé

Les quatre chantiers sont indépendants. Ordre proposé, du plus contraint au
moins contraint :

1. **4.15 cœur** (`aggregate.py`, `live_query.py`) — c'est là que vivent les
   décisions de sémantique (`null`, `p`, `STDDEV_SAMP`) dont tout le reste
   dépend.
2. **4.16 cœur** (une ligne + tests), immédiatement après : même fichier.
3. **4.15/4.16 shell, chemin analytique** (`DataSourcePanel`, `chartOption`,
   `comparisonWindow`, rendu `null` des widgets).
4. **4.15 shell, assistant de requête visuelle** — isolé, avec ses tests de
   round-trip.
5. **4.18 cœur** (validateurs sur le rollback) puis **`ItemClient` +
   `StaticItemClient`** puis **`ConfigHistoryPanel`** puis les cinq points de
   montage.
6. **4.6** — le plus petit et le plus indépendant ; il peut se faire à
   n'importe quel moment.

## 6. Validation & preuves de sortie

**Preuves de sortie du plan d'action, une par chantier :**

| # | Preuve |
|---|---|
| 4.15 | Un indicateur « nombre de communes distinctes » et un « revenu médian » se construisent sans SQL Lab. |
| 4.16 | Une série annuelle se construit dans l'assistant, pas en SQL. |
| 4.6 | Filtrer sur « Dataset » ramène les datasets ; aucun type de `ResourceType` n'est absent du sélecteur. |
| 4.18 | Restaurer une version antérieure d'une app depuis le builder, sans appel d'API à la main. |

**Cœur (TDD, `uv run pytest`)** — les quatre agrégats sur données réelles ;
`p` absent / hors bornes / fourni pour un autre agrégat ; `null` sur ensemble
vide pour les trois agrégats indéfinis et `0` pour `countDistinct` ; les six
grains temporels ; `stddev` accepté et les trois autres refusés sur le chemin
ArcGIS ; rollback d'une config valide accepté, rollback d'une config devenue
invalide refusé en 422 (au moins un validateur par famille sensible :
pipeline et alert).

**Shell (`npm run test`)** — round-trip compile↔décompile pour chacune des
quatre fonctions, `p` compris ; exhaustivité du `Record<ResourceType, string>`
(un test qui échoue à la compilation si une entrée manque, doublé d'un test
runtime sur le nombre d'options rendues) ; navigation `alert` et `external` ;
`ConfigHistoryPanel` (liste, erreur réseau distincte d'une liste vide,
confirmation sur brouillon sale, réinitialisation de la pile undo).

**E2E (`npm run e2e`)** — deux specs, une par critère de sortie visible :
filtrer le catalogue sur « Dataset » ramène les datasets ; restaurer une
version antérieure d'une app depuis le builder revient à l'état antérieur.

**Non-régression** — compteurs de référence mesurés le 2026-08-21 : core
**1653 passed / 153 skipped / 0 failed**, shell **152 fichiers / 1235
tests**. Aucune baisse admise. `ruff check`, `ruff format --check`,
`mypy --strict` (4 modules), `lint-imports`, `npm run lint`,
`npm run format:check`, `npm run build` verts. Seuils de couverture
`core/.coverage-threshold` (85) et `shell/.coverage-threshold` (88) tenus.

**Régénération OpenAPI/TS** — à vérifier explicitement, pas à supposer : c'est
la classe d'oubli la plus récurrente du dépôt (5 occurrences recensées).

## 7. Risques et limites connues

- **`decompileMetrics` dégrade en silence.** Une forme SQL non reconnue fait
  retomber l'utilisateur sur `PipelineBuilderPage` sans erreur — repli attendu
  par conception, mais qui rend un bug de round-trip invisible sans test
  dédié. C'est le point le plus fragile du SP.
- **Le `null` des agrégats indéfinis traverse tout le chemin d'affichage.**
  Six widgets analytiques, l'export CSV/XLSX (SP-16a), le rendu PDF (SP-17a)
  et le mini-serveur autoporté (SP-18c) consomment ces valeurs. Le test doit
  couvrir au moins le rendu widget et un export ; les autres surfaces sont
  vérifiées par lecture.
- **Parité `stddev` ArcGIS affirmée, pas mesurée** (§3.1).
- **`list_revisions` n'est pas paginée** et ne filtre pas par tenant (elle
  s'appuie sur l'unicité de `config_id` et sur le contrôle d'accès par item).
  Une config éditée des centaines de fois renvoie toutes ses révisions d'un
  coup. Acceptable au volume actuel ; à revoir si le panneau devient lent.
- **Le reset de la pile undo touche `useUndoableDraft`**, dont la revue
  finale SP-19 a montré qu'il est piégeux : toute mutation de ref à
  l'intérieur d'un updater `useState` est cassée sous `<StrictMode>`, donc en
  `npm run dev` mais jamais en E2E. Le test doit s'exécuter en mode strict.
- **4.16 est plus large que « S »** (§3.2) et **4.15 aussi** (décision 7). Le
  SP dans son ensemble reste nettement en deçà d'un lot Carte, mais ce n'est
  pas quatre chantiers d'une session.
