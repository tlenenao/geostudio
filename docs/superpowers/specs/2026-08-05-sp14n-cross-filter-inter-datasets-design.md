# SP-14n — Cross-filter inter-datasets (design)

> **Date : 2026-08-05 · Statut : validé (brainstorm)**
> Quatorzième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**, **SP-14b — Contexte analytique
> global & cross-filter**, **SP-14c — Filtres typés & indicateur**,
> **SP-14d — Menu explorer & voir les entités**, **SP-14e — KPI riche &
> séries temporelles comparées**, **SP-14f — Nouveaux types de graphiques**,
> **SP-14g — Tableau croisé / pivot**, **SP-14h — Carte analytique**,
> **SP-14i — SQL Lab**, **SP-14j — Conteneurs**, **SP-14k — Source `arcgis`**,
> **SP-14l — MCP analytique** et **SP-14m — Bookmarks**. Traite le second des
> deux éléments restés explicitement « hors périmètre » depuis 14b (répété
> identique en 14h/14i/14m) : le **cross-filter inter-datasets** — une
> sélection sur un widget d'un dataset qui filtre aussi les widgets d'un
> *autre* dataset. Une fois SP-14n livré, il ne reste au contenu SP-14 de la
> feuille de route que la **requête visuelle**, bloquée sur le moteur de
> pipeline de **SP-15** (A39, ETL no-code, qui n'existe pas encore) — SP-14n
> est donc le dernier chantier non bloqué de SP-14 ; la feuille de route sera
> mise à jour en conséquence (jalon M11 atteint modulo ce blocage) une fois
> l'implémentation livrée.

## 1. Objectif & non-buts

**Objectif.** Aujourd'hui (SP-14b), le cross-filter ne relie que les widgets
d'un **même** dataset (`AnalyticsContextState.crossFilter` est indexé par
`datasetId`, et `derivePatch` ignore toute source dont le `datasetId` diffère
de celui de la sélection). SP-14n permet à un dataset de déclarer un **lien**
vers un autre dataset : dès lors, sélectionner une entité/valeur sur un
widget consommant le dataset A filtre aussi les widgets consommant le
dataset B. Deux mécanismes de correspondance, selon la nature de la relation
entre les deux datasets :

- **Attribut partagé** : les deux datasets ont une colonne de même sens (ex.
  `commune`) — la valeur sélectionnée sur A est reportée telle quelle comme
  filtre sur la colonne correspondante de B.
- **Spatial** : les deux datasets n'ont pas nécessairement de colonne
  commune mais partagent une géométrie — sélectionner une entité sur A filtre
  B par intersection géométrique.

**Non-buts explicites** (pour rester dans une sous-partie livrable) :

- **Requête visuelle.** Dépend de SP-15 (cf. en-tête), inchangé.
- **Propagation transitive** (A→B→C en chaîne). Un lien ne fait réagir que sa
  cible directe ; pas de résolution en graphe, pas de détection de cycle à
  écrire puisqu'il n'y a pas de chaînage.
- **Réciprocité automatique.** Un lien déclaré sur A vers B ne fait réagir
  que B à une sélection sur A. Pour l'inverse, on déclare un second lien
  explicite sur B vers A — pas de mécanisme de symétrie implicite (le mapping
  champ↔champ ou le mode spatial n'a pas toujours un sens symétrique, ex.
  bbox d'un point vs bbox d'un polygone).
- **Cross-filter spatial déclenché par un widget agrégé** (chart, pivot,
  KPI). Ces widgets sélectionnent une *valeur de groupe*, pas une géométrie ;
  seuls les widgets qui portent la géométrie de l'entité cliquée (Carte,
  Table si la source a une colonne géométrie) peuvent déclencher un lien en
  mode spatial. Un lien spatial déclaré mais jamais déclenchable depuis un
  widget géométrique du dashboard reste simplement inerte — pas une erreur.
- **Persistance de la géométrie de sélection** dans l'URL/un bookmark (cf.
  §4) — limite acceptée, pas un défaut à corriger ici.
- **Résolution des collisions** entre deux liens contradictoires vers la même
  cible (deux datasets liés au même dataset C avec des filtres divergents) :
  dernier résolu gagne, comme le traitement actuel des autres dimensions du
  contexte (`timeRange`, `extent`) — documenté comme limite connue, pas
  arbitré finement.
- **Mise à jour de la feuille de route** (clôture de SP-14/M11). Action de
  suivi post-implémentation, hors périmètre de ce document.

Le modèle reste additif : rien ici ne modifie le comportement existant d'un
dataset sans `crossFilterLinks` déclaré ; les specs E2E existantes restent
vertes sans modification.

## 2. Modèle de données

Nouveau champ optionnel sur `DatasetConfig` (les deux variantes
`collection`/`arcgis`, `shell/src/api/types.ts`), opt-in comme
`reactsToExtent` (A29) :

```ts
export type CrossFilterLink =
  | { targetDatasetId: string; mode: "attribute"; sourceField: string; targetField: string }
  | { targetDatasetId: string; mode: "spatial"; precision: "bbox" | "exact" };

// ajout aux deux variantes de DatasetConfig :
crossFilterLinks?: CrossFilterLink[];
```

- **Mode `attribute`** : s'applique quand une entrée `crossFilter[originDatasetId]`
  a `field === sourceField` — traduit en filtre `targetField=value` (ou
  `__in`/`__gte`/`__lte` selon la forme de `value`, même logique que le
  cross-filter même-dataset existant).
- **Mode `spatial`** : s'applique quand l'entrée porte une géométrie (voir
  §3). `precision: "bbox"` dérive un rectangle englobant côté client (zéro
  capacité cœur nouvelle, réutilise le paramètre `bbox` déjà supporté par
  `features`/`aggregate`) ; `precision: "exact"` envoie la géométrie et
  s'appuie sur la nouvelle capacité cœur générique décrite en §4.

`CrossFilterEntry` (`AnalyticsContext.tsx`) gagne un champ optionnel :

```ts
export type CrossFilterEntry = {
  field: string;
  value: CrossFilterValue;
  originSourceId: string;
  geometry?: GeoJSON.Geometry; // présent uniquement pour une sélection portée par une géométrie
};
```

## 3. Capture de la sélection & résolution (shell)

**Capture.** `useSetCrossFilter` gagne un 5ᵉ paramètre optionnel
`geometry?: GeoJSON.Geometry`. Seuls `mapWidget.tsx` (clic sur une entité de
la carte) et `data.tsx`/Table (clic sur une ligne dont la source a une
colonne géométrie) le renseignent ; `chart.tsx` et `pivot.tsx` continuent
d'appeler `setCrossFilter` sans ce paramètre (ils sélectionnent une valeur de
groupe, jamais une géométrie individuelle — cf. non-but §1).

**Résolution** (`analyticsPatch.ts::derivePatch`). En plus du filtre direct
même-dataset déjà géré (inchangé), pour chaque `DataSource` cible on
parcourt les entrées `crossFilter` des *autres* datasets et on regarde si
`datasets[originDatasetId].crossFilterLinks` contient un lien vers
`source.datasetId` qui matche :

- lien `attribute` dont `sourceField === entry.field` → patch
  `targetField=value` (translittéré selon la forme de `value`, comme pour un
  filtre même-dataset) ;
- lien `spatial` dont `entry.geometry` est défini → `precision: "bbox"` ⇒
  patch `bbox=<bbox de entry.geometry>` (calcul pur côté client, aucun appel
  réseau) ; `precision: "exact"` ⇒ patch `geom_intersects=<GeoJSON de entry.geometry>`.

`derivePatch` reste une fonction pure (même style que testé depuis SP-14b) :
elle ne résout jamais de schéma, elle ne fait que lire les `DatasetConfig`
déjà chargés (même cache que l'existant, `datasets: Record<string, DatasetConfig>`
déjà passé en paramètre).

## 4. Cœur : nouveau filtre spatial générique `geom_intersects`

Le paramètre est ajouté comme **capacité générique** de l'API
features/aggregate — disponible pour toute collection avec géométrie, pas
réservé au cross-filter (le cross-filter inter-datasets n'en est qu'un
appelant parmi d'autres possibles : SQL Lab, MCP, un futur widget « sélection
libre » sur la carte).

- `features/routes.py` : nouveau paramètre de requête `geom_intersects`
  (GeoJSON sérialisé en JSON), parsé comme `bbox` l'est aujourd'hui
  (`_parse_bbox`) — ajouté à `RESERVED_QUERY_PARAMS`.
- `features/repository.py::_where` : traduit en
  `ST_Intersects(geom, ST_Transform(ST_GeomFromGeoJSON(:geom), :srid))`,
  même colonne géométrie / SRID que le bbox existant (`info.geometry_column`,
  `info.srid`), même garde `"collection has no geometry"` si absente. Noter
  la différence avec `bbox` : le filtre `bbox` actuel utilise l'opérateur
  `&&` (chevauchement d'enveloppes, index GiST, approximatif) — `geom_intersects`
  utilise `ST_Intersects` (test géométrique exact, plus coûteux mais précis).
- `analytics/aggregate.py` : même paramètre optionnel, même clause, pour que
  les widgets agrégés (chart/KPI/pivot) sur le dataset cible en bénéficient
  aussi, pas seulement Table/Carte.

Pas de nouvel endpoint, pas de nouveau module — extension mécanique du
filtre spatial déjà en place, dans l'esprit du garde-fou de la feuille de
route SP-14 (« la soupape est le SQL analyste, pas l'ORM qui enfle ») : on
n'ajoute ici qu'un paramètre au vocabulaire de filtre existant, pas un nouveau
langage de requête.

**Limite acceptée — non-persistance de la géométrie.** La géométrie de
sélection (mode `exact` comme `bbox`, dérivée côté client) est tenue en
mémoire pour la session mais **n'est pas persistée** dans l'URL (`?ctx=`,
SP-14b) ni dans un bookmark (SP-14m) — contrairement aux `field`/`value`
scalaires du cross-filter classique. Un bookmark rouvert restaure
normalement le cross-filter inter-dataset en mode `attribute`, mais un lien
`spatial` actif au moment de la sauvegarde n'est pas rejoué (l'entrée
`crossFilter` restaurée n'a pas de `geometry`, donc aucun lien spatial ne
matche à la résolution). Cohérent avec le fait que SP-14m ne portait déjà que
des valeurs scalaires ; documenté comme non-but plutôt que traité.

## 5. UI d'auteur (`DatasetEditPage.tsx`)

Nouvelle section « Liens cross-filter », à côté de `timeField`/`reactsToExtent` :
liste de liens sortants, chacun avec :

- un select « dataset cible » — parmi les autres datasets accessibles à
  l'utilisateur courant (même filtrage par permissions que le picker de
  source existant) ;
- un select de mode (attribut / spatial) ;
- selon le mode :
  - **attribut** : deux selects de champ — source parmi les colonnes du
    dataset courant (déjà chargées via `mergeDatasetSchema`), cible parmi les
    colonnes du dataset cible (nécessite de charger son schéma le temps de la
    configuration du lien, même mécanisme `useQuery` que `schemaQuery`
    existant, appliqué à la collection du dataset cible) ;
  - **spatial** : un select de précision (bbox / exact), affiché seulement si
    la collection cible a une colonne géométrie (garde côté UI en plus de la
    garde cœur — un lien spatial vers une collection sans géométrie n'a pas
    de sens et n'est pas proposé).

## 6. Indicateur de contexte (`AnalyticsContextIndicator.tsx`, SP-14c)

L'indicateur existant (qui affiche déjà le cross-filter actif même-dataset)
liste en plus les datasets filtrés *par ricochet* via un lien (ex.
« Communes → Incidents : commune = Brive »), avec le même bouton d'effacement
que pour un filtre direct (`clearCrossFilter(originDatasetId)` — effacer à la
source efface aussi ses effets propagés, pas de bouton séparé par lien).

## 7. Bookmarks & compatibilité

**Aucun changement de schéma bookmark** (`BookmarkPayload`,
`core/app/configs/schemas.py`, SP-14m) : `crossFilter` porte déjà l'entrée
d'origine (`field`/`value`/`originSourceId`) ; la résolution vers les
datasets liés se refait à la lecture depuis les `crossFilterLinks` déclarés
sur les `DatasetConfig` au moment de l'ouverture, pas depuis le bookmark
lui-même (cf. limite §4 pour le cas spatial).

Compatibilité : `crossFilterLinks` est un champ additif absent par défaut ;
aucun dataset existant n'en a. Les specs E2E existantes restent vertes sans
modification.

## 8. Tests

**Core (unitaires)** :
- `geom_intersects` (features) : filtre correctement une collection avec
  géométrie ; 400 explicite (`FilterError`) si la collection n'a pas de
  géométrie, GeoJSON malformé rejeté proprement (même style d'erreur que
  `_parse_bbox`).
- Même filtre côté `analytics/aggregate.py` : une agrégation groupée ne
  compte que les lignes intersectant la géométrie fournie.

**Shell (unitaires)** :
- `derivePatch` : un lien `attribute` traduit correctement une sélection sur
  A en filtre sur une source de B ; absent de `crossFilterLinks` ⇒ aucun
  effet (comportement actuel inchangé) ; un lien `spatial/bbox` dérive le bon
  rectangle depuis une géométrie de test ; un lien `spatial/exact` produit un
  patch `geom_intersects` avec la géométrie telle quelle.
- `setCrossFilter` avec `geometry` : l'entrée stockée porte bien le champ
  `geometry` ; sans lui, comportement identique à avant (pas de régression
  sur le cross-filter même-dataset de SP-14b).
- `DatasetEditPage` : ajout/suppression d'un lien dans le draft ; le select
  de précision spatiale est masqué si la collection cible n'a pas de
  géométrie.

**E2E nouvelle** (calquée sur les specs `analytics-context`/`bookmarks`
existantes) : deux datasets sur des collections distinctes (une couche de
communes en polygones, une couche d'incidents en points) affichés sur un même
dashboard `interactions: "auto"`, dataset « incidents » lié en mode spatial
(`bbox`) au dataset « communes » ; cliquer une commune sur la carte filtre le
widget Table des incidents à ceux dans son emprise ; l'indicateur de contexte
affiche le lien propagé ; effacer le cross-filter sur la carte lève aussi le
filtre sur la table des incidents.

## 9. Risques

| Risque | Garde-fou |
|---|---|
| `ST_Intersects` plus coûteux que le `&&` du bbox existant sur de grosses collections | Mode `bbox` disponible et recommandé par défaut dans l'UI d'auteur pour les cas où l'approximation rectangulaire suffit ; `exact` réservé aux cas qui l'exigent réellement |
| Confusion pour l'utilisateur si un lien spatial est déclaré mais jamais déclenchable (aucun widget géométrique sur le dashboard consommant ce dataset) | Comportement inerte documenté (§1) plutôt qu'une erreur — cohérent avec le traitement des datasets orphelins ailleurs dans SP-14 |
| Collision entre deux liens contradictoires vers la même cible | Dernier résolu gagne, documenté comme limite connue (§1), pas résolu ici |
| Sur-ingénierie prématurée (chaînage transitif, réciprocité automatique, persistance de la géométrie en bookmark) | Explicitement hors périmètre (§1/§4) ; modèle additif pour une sous-partie ultérieure si le besoin émerge |
| SP-14n clôt le contenu SP-14 de la feuille de route modulo la requête visuelle bloquée sur SP-15 | Mise à jour de la feuille de route en action de suivi post-implémentation (cf. en-tête), pas dans ce document |
