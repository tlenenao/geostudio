# SP-14n — Cross-filter inter-datasets — Progress Ledger

Plan: docs/superpowers/plans/2026-08-05-sp14n-cross-filter-inter-datasets.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@c5e4db1 (HEAD au lancement de cette sous-partie ; SP-14m ledger
committé en amont par hygiène de dépôt).

Note : ce fichier remplace le ledger SP-14m (complet, READY TO MERGE, HEAD=c1b4e46)
— même fichier scratch réutilisé par convention du dépôt ; contenu SP-14m préservé
dans l'historique git (commit c5e4db1).

## Pré-vol

Scan des 10 tâches (1: `geomIntersects` DuckDB aggregate ; 2: `geom_intersects`
OGC API Features ; 3: `crossFilterLinks` sur `DatasetPayload` (core) ; 4: types
shell (`CrossFilterLink`, `CrossFilterEntry.geometry`, `useSetCrossFilter`) ;
5: `bboxFromGeometry` + résolution `derivePatch` ; 6: `geomIntersects` dans le
corps de requête aggregate (shell) ; 7: capture de géométrie au clic
(Carte/Liste/Table) ; 8: `useDatasets()` + indicateur montre les liens
propagés ; 9: `CrossFilterLinkEditor` + câblage `DatasetEditPage` ; 10: E2E
scénario cross-filter inter-datasets) contre les Contraintes Globales
(additif seul — `crossFilterLinks` absent par défaut partout, aucun dataset
existant n'en a ; TDD systématique ; commits conventionnels petits ; docs FR /
code EN ; hors périmètre : query builder visuel, chaînage transitif A→B→C,
réciprocité automatique, résolution de collision au-delà de "dernier résolu
gagne", persistance de la géométrie cross-filter en URL/bookmark ; le patch
`geomIntersects` ne doit atteindre le serveur QUE via le chemin
aggregate/statistics, jamais `_queryParams`/`buildFeaturesUrl` — précédent
`bbox` déjà tranché en SP-14b, ne pas rouvrir) :

Aucune contradiction trouvée. Code littéral complet fourni pour chaque tâche
(imports, helpers, corps de fonctions/composants, tests) — transcription +
intégration, même style que SP-14l/SP-14m. Dépendances d'interface : Task 2
indépendante de Task 1 (core, deux endpoints distincts, même capacité) ; Task 3
indépendante de 1/2 (schéma Pydantic seul) ; Task 4 consomme Task 3 (mirror
field-for-field du schéma core) ; Task 5 consomme Task 4 (`CrossFilterLink`,
`CrossFilterEntry.geometry`) ; Task 6 consomme Task 5 (`query.geomIntersects`
produit par `derivePatch`) et Task 1 (capacité serveur) ; Task 7 consomme
Task 4 (5e paramètre `geometry` de `useSetCrossFilter`) ; Task 8 consomme
Task 4 (`DatasetConfig.crossFilterLinks`) ; Task 9 consomme Task 3/4 (types
+ round-trip) ; Task 10 (E2E) consomme Tasks 4-9 bout en bout, exerce
uniquement le chemin spatial/bbox (le chemin spatial/exact + Task 2 restent
non exercés en E2E, conforme à la note explicite de la tâche 10 sur le
périmètre de ce plan).

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: c5e4db1
Task 1: complete (commit bf29056, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor négligeables —
validation peu profonde du GeoJSON malformé héritée du même niveau que
`bbox`, duplication de 7 lignes entre les deux blocs WHERE mandatée par le
plan et trop petite pour justifier une abstraction). `geomIntersects` sur
`AggregateRequestBody` : mirror fidèle de `bbox` (validation, clause
`ST_Intersects(..., ST_GeomFromGeoJSON(?))` paramétrée, pas d'injection SQL).
Reviewer a vérifié indépendamment que `AggregateRequestBody` est bien le type
de corps consommé par les trois points d'entrée (`features/routes.py`,
`harvest/routes.py`, `mcp/tools.py`) — additif partout sans câblage
supplémentaire nécessaire. 2/2 tests nouveaux, 33/33 tests du fichier
aggregate (0 régression).

Base Task 2: bf29056
Task 2: complete (commit 7aebb6d, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor négligeables —
`GeometryCollection` rejeté par le check de forme `type`/`coordinates` (même
niveau de rigueur que `bbox`, pas une régression), type GeoJSON non validé en
profondeur (erreur DB 500 possible plutôt que 400 propre, pattern déjà présent
sur `_parse_bbox`). `geom_intersects` sur `select_features`/`_where` (mirror
`bbox`, paramètre lié `:gi`/`:gisrid`, pas d'injection) + route
`_parse_geom_intersects` (mirror `_parse_bbox`, code `invalid_geom_intersects`)
+ `RESERVED_QUERY_PARAMS` étendu. Reviewer a vérifié indépendamment que la
signature keyword-only de `select_features` rend l'ajout non cassant pour les
3 autres call sites (`stac/routes.py`, `mcp/tools.py`). Docker/postgis
disponible dans cet environnement : tests postgis-marqués réellement exécutés
(pas skippés) — 16/16 repo + 7/7 route, 997 passed suite complète avec DB
configurée (0 régression).

Base Task 3: 7aebb6d
Task 3: complete (commit d98db7c, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor négligeables —
alias de type `DatasetCrossFilterLink` sans commentaire dédié, pas de test de
champ requis manquant dans une branche de l'union). `DatasetCrossFilterLinkAttribute`/
`DatasetCrossFilterLinkSpatial` + union discriminée sur `mode` + `crossFilterLinks`
sur `DatasetPayload` — noms/types/défauts vérifiés caractère pour caractère par
le reviewer contre le brief (load-bearing pour Task 4 shell qui les mirror).
Discriminateur réellement exercé (pas juste déclaré) : test "unknown mode"
prouve un vrai `ValidationError` Pydantic. 5/5 tests nouveaux, 888 passed +
114 skipped suite complète (0 régression).

Base Task 4: d98db7c
Task 4: complete (commit 7e1bde4, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 1 Minor confirmé non
problématique — 1 test préexistant (`itemClient.test.ts` `toEqual` sur
`getDatasetConfig`) étendu avec `crossFilterLinks: []`, vérifié indépendamment
par le reviewer comme inévitable (code littéral du brief renvoie
inconditionnellement le champ) et non-affaiblissant (étend, ne dilue pas).
`CrossFilterLink` (union discriminée mirror fidèle du schéma core Task 3),
`CrossFilterEntry.geometry?`, `useSetCrossFilter` 5e paramètre optionnel,
`crossFilterLinks` par défaut `[]` sur les 4 points d'accès itemClient —
vérifiés caractère pour caractère contre le brief. `tsc --noEmit` propre.
856/856 tests suite complète (0 régression).

Base Task 5: 7e1bde4
Task 5: complete (commit 4debf7d, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 3 Minor négligeables —
coverage manquante sur `coordinates: []`/leaves non-numériques dans
`bboxFromGeometry` (comportement sûr vérifié par trace), branche
attribute/spatial reposant implicitement sur l'union à 2 membres plutôt qu'un
`else if` explicite, pas de test dédié à la collision "dernier résolu gagne").
Tâche la plus dense en logique du plan (double boucle : résolution
same-dataset préexistante + nouvelle résolution cross-dataset) — reviewer a
tracé le code ligne par ligne pour confirmer les 3 garde-fous (pas de
double-fire self-link, `field === sourceField` pour attribute, `geometry !==
undefined` pour spatial) et l'absence de propagation transitive (un seul
saut). `applyCrossFilterValue` confirmé extraction verbatim (0 dérive de
comportement). `bboxFromGeometry` (nouveau, pur, pas de dépendance turf).
23 tests nouveaux (4 geometryBbox + 19 analyticsPatch), 867/867 suite
complète, tsc propre (0 régression).

Base Task 6: 4debf7d
Task 6: complete (commit 1e9f120, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 1 Minor cosmétique —
le `&&` de garde court-circuite avant le `typeof`, donc `null` est exclu par
la vérification de vérité pas par `typeof`, comportement correct mais fragile
si le `&&` était retiré un jour ; non bloquant). `buildAggregateBody` transmet
`query.geomIntersects` tel quel dans `body.geomIntersects`. Reviewer a
vérifié que seul `buildAggregateBody` est touché — `_queryParams`,
`buildFeaturesUrl`, `STAT_KEYS` absents du diff (précédent `bbox` SP-14b non
rouvert). 1 test nouveau (msw réel), 868/868 suite complète (0 régression).

Base Task 7: 1e9f120
Task 7: complete (commit 02cafa0, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 1 Minor préexistant —
`selectRecord` liste/table byte-for-byte identiques hors JSX environnant,
duplication antérieure à cette tâche, pas introduite ici). Les 3 sites d'appel
(`mapWidget.tsx` `onFeatureClick`, `data.tsx` liste + table `selectRecord`)
transmettent `.geometry` en 5e argument. `chart.tsx`/`pivot.tsx` confirmés
absents du diff. Tests distinguant réellement présence (`geom={...}`) et
absence (`geom=null`) de géométrie, pas juste re-vérification du clic.
869/869 suite complète (0 régression).

Base Task 8: 02cafa0
Task 8: complete (commits 0576311 puis 95696b3, 1 round de fix). Review round 1
: ❌ Important trouvé, étiqueté plan-mandated — le test négatif fourni
verbatim par le brief (`renderIndicator()` sans `DatasetsContext.Provider`)
ne prouvait que "aucun dataset configuré → pas de flèche", pas le vrai risque
de régression (dataset configuré avec un lien `crossFilterLinks` dont le mode
ne correspond pas au filtre actif → pas de flèche). Jugé comme une lacune de
couverture de test, pas un choix de design mandaté — fix dispatché sans
arbitrage humain (purement additif, ne contredit aucune contrainte globale).
Fix : nouveau test avec un vrai `DatasetsContext.Provider` + lien
`sourceField` non correspondant, vérifié par le fixeur en retirant
temporairement le prédicat `.filter()` pour confirmer que le test échoue bien
sans lui. Re-review round 2 : ✅ spec compliant, task quality Approved, 0
finding bloquant, 1 Minor cosmétique (nom du test dit "mode" alors que c'est
`sourceField` qui diffère — sémantique du test correcte malgré le nom).
`useDatasets()` mirror fidèle de `useDataStates()` ; déplacement de
`AnalyticsContextIndicator` dans l'arbre React confirmé neutre pour le DOM
(`DataProvider` ne rend aucun élément) ; E2E scénarios 8/9 confirmés verts par
l'implémenteur (25/25 `analytics-context.spec.ts`). 872/872 suite complète
unitaire (0 régression).

Base Task 9: 95696b3
Task 9: complete (commit cc9f424, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor plan-mandated
négligeables — `key={i}` sur liste réordonnable/supprimable et duplication du
pattern query-key `["collection-schema", ...]` entre `DatasetEditPage` et
`CrossFilterLinkEditor`, tous deux verbatim dans le code littéral du brief,
pas introduits par l'implémenteur). Implémenteur a corrigé deux défauts
réels du code littéral du brief pendant la transcription, vérifiés
indépendamment par le reviewer contre le fichier brief lui-même : (1) violation
Rules-of-Hooks — le brief plaçait `useItems(...)` après les guards de retour
anticipé de `DatasetEditPage`, l'implémenteur l'a remonté à côté de
`schemaQuery` (0 delta de comportement observable) ; (2) fixture de test
`CollectionSchemaField` incomplète (`required` manquant, `tsc` en échec) —
complétée. `CrossFilterLinkEditor` (nouveau composant) + câblage
`DatasetEditPage` (rendu par lien + bouton "Ajouter un lien" + inclusion dans
le payload de sauvegarde). Tous les aria-labels/textes de bouton
load-bearing pour l'E2E de Task 10 vérifiés verbatim contre le diff. 11 tests
nouveaux (6 + 5), 880/880 suite complète (0 régression), tsc propre.

Base Task 10: cc9f424
Task 10: complete (commit 3012192, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 1 Minor — le fait que
`AppBuilderPage.promoteSource` crée toujours un nouveau dataset (jamais de
réutilisation) n'est documenté nulle part hors du fichier E2E, note pour un
futur travail sur `promoteSource`, hors périmètre de cette tâche). Deux
déviations structurelles (pas cosmétiques) explicitement signalées par
l'implémenteur et tracées à la main par le reviewer contre le code de
production réel (pas de confiance sur "les tests passent") : (1) ajout des
étapes de config du widget Indicateur (Agrégation=Somme, Champ agrégé=value)
— sans cela le widget affiche `records.length` (toujours 1) et n'observe
jamais le changement 5→2, confirmé contre `indicator.tsx` ; (2) réordonnancement
de la création des datasets après la promotion dans le app-builder plutôt
qu'avant — `promoteSource` crée toujours un nouveau dataset item, jamais de
réutilisation (confirmé contre `AppBuilderPage.tsx`), donc l'ordre littéral du
brief aurait déclaré le lien sur des datasets orphelins jamais interrogés par
l'app. Reviewer a tracé le flux d'id complet (Table→dataset-1/communes,
Indicateur→dataset-2/incidents-pts, lien authored sur dataset-1→dataset-2) et
vérifié contre `analyticsPatch.ts` (Task 5) que la direction du lien
correspond exactement à la sémantique de résolution réelle — pas une
coïncidence de chaînes d'id. Scénario stable sur 3 exécutions isolées + 2
exécutions du fichier complet (26 tests) + suite E2E complète 86/86 (0
régression). Diff pur ajout, aucun scénario existant modifié.

## SP-14n COMPLET — 10 tâches, 13 commits de tâches (bf29056, 7aebb6d,
## d98db7c, 7e1bde4, 4debf7d, 1e9f120, 02cafa0, 0576311, 95696b3[fix],
## cc9f424, 3012192 — 11 listés, 1 round de fix sur 10 tâches (Task 8 :
## test négatif du brief ne couvrant pas le vrai risque de régression du
## mode-gating). Le fix a été dispatché sans arbitrage humain — lacune de
## couverture de test, pas un choix de design mandaté, correction purement
## additive n'entrant en conflit avec aucune Contrainte Globale. Task 9 et
## Task 10 ont chacune eu des déviations du code littéral du brief
## (Rules-of-Hooks + fixture de test pour Task 9 ; réordonnancement E2E +
## config widget pour Task 10), toutes vérifiées indépendamment par les
## reviewers comme des corrections légitimes de vraies lacunes du brief,
## jamais du scope creep, jamais des passes accidentels. Minors non bloquants
## à transmettre à la revue finale de branche : Task 1 (validation GeoJSON
## peu profonde, duplication bbox/geomIntersects mandatée), Task 2
## (GeometryCollection rejeté, type GeoJSON non validé en profondeur), Task 3
## (alias de type sans commentaire, pas de test de champ requis manquant),
## Task 4 (aucun — tout Approved sans réserve), Task 5 (coverage
## coordinates vides, branche implicite sur union à 2 membres, pas de test
## de collision "dernier gagne"), Task 6 (garde `&&`/`typeof` fragile si
## retirée), Task 7 (duplication liste/table préexistante), Task 8 (nom de
## test imprécis "mode" vs "field"), Task 9 (key={i}, duplication query-key
## collection-schema — toutes deux plan-mandated), Task 10 (comportement de
## `promoteSource` non documenté hors du fichier E2E). HEAD=3012192, prêt
## pour la revue finale de branche.

## Revue finale de branche (opus, c5e4db1..3012192, 11 commits) — 0 Critical,
## 0 Important, 4 Minor. Vérifications transversales que les revues par tâche
## ne pouvaient pas voir : chaîne clic→SQL tracée bout en bout (click→
## setCrossFilter→derivePatch→buildAggregateBody→AggregateRequestBody) ;
## absence de propagation transitive/réciprocité garantie structurellement
## (la boucle lit `crossFilterLinks` des datasets à filtre actif direct
## seulement, n'écrit jamais dans `ctx.crossFilter`) ; paramétrage SQL
## confirmé sur les deux endpoints (DuckDB + PostGIS, pas d'injection) ;
## `_queryParams` confirmé droppant silencieusement `geomIntersects` (objet)
## donc le scope "aggregate seul" tient sans garde supplémentaire ; 244 tests
## (190 shell + 54 core sur les fichiers touchés) verts, tsc propre.
## 4 Minor : (1) l'indicateur affiche une flèche de propagation pour un lien
## spatial/exact même quand la cible n'est consommée que par des widgets
## carte/liste/table — `geomIntersects` n'atteint le serveur que par le
## chemin aggregate (scope ratifié du plan), donc l'UX suggère une
## propagation qui ne se produit pas, silencieusement ; (2) collision de clé
## `bbox` entre l'emprise carte (`reactsToExtent`) et un lien spatial/bbox
## actif — un dataset cible des deux verrait son bbox figé par le filtre tant
## qu'il est actif, interaction SP-14b×SP-14n invisible dans un seul diff de
## tâche ; (3) validation structurelle de `geomIntersects` incohérente entre
## les deux endpoints core (OGC rejette proprement en 400, aggregate laisse
## remonter une erreur DuckDB probable 500) ; (4) `geomIntersects` absent de
## `STAT_KEYS` (exclusion accidentelle par type plutôt qu'intentionnelle par
## clé, actuellement sans effet). Les 4 sont Minor, aucun ne bloque le merge.
## Signalés à l'humain pour arbitrage sur suite à donner (documentation
## "Suivis non bloquants" vs. correctif), pas de fix dispatché — aucun
## Critical/Important à cette étape.

## **SP-14n READY TO MERGE** — HEAD=3012192, 11 commits (10 tâches + 1 fix sur
## Task 8), 1 round de fix sur 10 tâches, revue finale de branche clean au
## premier passage (0 Critical, 0 Important), prêt pour
## finishing-a-development-branch.
