# SP-14f — Nouveaux types de graphiques (sankey, treemap, sunburst, funnel, histogramme binné) — Progress Ledger

Plan: docs/superpowers/plans/2026-08-02-sp14f-nouveaux-types-graphiques.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@1888fc1 (plan + spec SP-14f committés).

Note : ce fichier remplace le ledger SP-14e (complet, revue finale
ready-to-merge, HEAD=f136501) — même fichier scratch réutilisé par
convention du dépôt ; contenu SP-14e préservé dans l'historique git.

## Pré-vol

Scan des 12 tâches (1-3 core : groupBy liste + validation, tidy rows
multi-champs, histogramme binné DuckDB ; 4-5 shell plomberie :
itemClient passthrough + id composite, DataSourcePanel groupBy CSV +
bins ; 6-9 chartOption.ts : funnel/histogram, sankey (rôle des nœuds),
treemap/sunburst (hiérarchie), resolveClickFilter généralisé ; 10-11
EChart.tsx (SunburstChart) + chart.tsx (UI builder, handleClick) ; 12
E2E) contre les 7 contraintes globales (zéro changement de comportement
pour les 10 types existants et tous les appelants d'AggregateRequestBody ;
`encodings` réservé à sankey/treemap/sunburst ; funnel réutilise
categoryField/valueField, histogram réutilise valueField+bins
[défaut 10, borné 1-100] ; bucket réservé à un groupBy à un seul champ,
split et groupBy multi-champs mutuellement exclusifs — les deux en
erreur de validation ; sankey v1 = un seul saut, hiérarchie
treemap/sunburst plafonnée à 3 niveaux ; pas de cross-filter au clic sur
histogramme ; commits français / code anglais, branche `dev`) : pas de
contradiction. Le plan fournit du code complet et littéral pour chaque
tâche (types, implémentation, tests unitaires, E2E) — transcription +
tests, pas de conception à faire, comme SP-14e. Dépendances d'interface
notées : Task 2 consomme `_groupby_fields` (Task 1) ; Task 3 consomme la
validation `bins` ajoutée dans `_validate_fields` (Task 1) ; Task 4
(itemClient) consomme les formes de réponse core des Tasks 1-3 ; Task 6
introduit `encodings`/`bins` sur `ChartProps`, consommés par Tasks 7-9 ;
Task 9 (`resolveClickFilter`) consomme le tag `_role` posé par la
branche sankey de Task 7 et les `levels` de la branche treemap/sunburst
de Task 8 ; Task 11 consomme `resolveClickFilter`/`ClickParams` (Task 9)
et `SunburstChart` enregistré (Task 10) ; Task 12 exerce l'UI réelle
produite par Tasks 1-11. Tâches exécutées dans l'ordre du plan (1→12).

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: 1888fc1
Task 1: complete (commit 48d4c17, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). `groupBy`
élargi à `str | list[str] | None`, `bins: int | None = None` déclaré
(inutilisé jusqu'à Task 3), helper `_groupby_fields`, validation
(doublons, champ inconnu, `bucket`+multi-champ, `split`+multi-champ).
Rétrocompatibilité vérifiée par le reviewer contre l'ancien garde
`bucket` et les tests existants. 21/21 tests (17 existants + 4
nouveaux). 3 Minor notés (non bloquants) : un `groupBy` multi-champ
valide sans `bucket`/`split` passe la validation mais provoque un
`AttributeError` non géré plus loin dans `run_collection_aggregate`
(`_qi` appelé sur une liste) — état intermédiaire délibéré, résolu par
Task 2 (prochaine tâche du même plan) ; message de commit en anglais
(CLAUDE.md demande le français, précédent mixte déjà dans l'historique
core) ; décompte de lignes du rapport de l'implémenteur légèrement
inexact (cosmétique, rapport seulement).

Base Task 2: 48d4c17
Task 2: complete (commit d61b699, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). Ferme le
trou laissé par Task 1 : `_pivot_multi_measures` + branche `len(fields)
> 1` dans `run_collection_aggregate`, réutilise intégralement
`_measures_for`/`_agg_expr`/`_qi`/`_dedup_cte`/`_build_where`/
`_fetch_rows` du chemin single-field (pas de réimplémentation
parallèle). `category_key` élargi à `str | list[str]`, chemin
single-field inchangé au runtime (juste un `str()` cosmétique pour le
typage). 24/24 tests (21 existants + 3 nouveaux), requêtes DuckDB
réelles sur parquet, pas de mocks. 3 Minor notés (non bloquants) : un
one-liner `measure_cols` dupliqué entre branches (DRY marginal) ; pas
de test dédié multi-champ + collection vide (chemin trivial partagé,
risque faible) ; les tidy rows gardent les types natifs (`pop` en int)
alors que `_pivot_measures`/`_pivot_split` stringifient — comportement
délibéré conforme au brief, mais incohérence de forme entre les deux
formats de réponse à garder à l'esprit pour les tâches shell (Task 4+).

Base Task 3: d61b699
Task 3: complete (commits 4ce6421, a992b78 ; 1 Important trouvé et
corrigé en 1 round de fix). Histogramme binné DuckDB : validation
`bins` (field requis, exclusif de `groupBy`, borné 1-100),
`_run_binned_histogram` (requête MIN/MAX puis GROUP BY sur bucket
`FLOOR`/`LEAST` clampé), câblé dans `run_collection_aggregate` juste
après `_build_where`. Ordre des placeholders SQL de `bucket_expr`
explicitement revérifié par le reviewer (3 `?` positionnels contre
`params = [bins, lo, width, *where_params]`) : correct. 1 Important
trouvé en 1re revue et confirmé par reproduction directe : corruption
silencieuse — `not_null_clause` filtrait sur la colonne brute au lieu
du résultat `TRY_CAST`, donc une valeur non numérique non nulle (ex.
`"abc"`) devenait `NULL` après cast puis `LEAST(bins-1, NULL)` de
DuckDB (qui ignore les NULL) la comptait silencieusement dans le
dernier bucket au lieu de l'exclure. Fix (a992b78) : `not_null_clause`
filtre maintenant sur `field_expr` (le résultat du `TRY_CAST`) au lieu
de la colonne brute. Test de régression ajouté
(`test_bins_excludes_non_numeric_values_from_top_bucket`), vérifié
RED contre l'ancien code (4 lignes comptées, `{0:2, 2:2}`) et GREEN
contre le correctif (`{0:2, 2:1}`, total 3). Revue 2 : fix vérifié
correct, aucun nouveau problème introduit, test non tautologique
confirmé par traçage manuel du bug. 1 Minor laissé tel quel (non
bloquant) : le `TABLE_INFO` du nouveau test déclare `pop` en
`type="integer"` alors que le test y écrit des chaînes — inoffensif
(DuckDB infère les types du parquet, pas de `ColumnInfo`), juste une
incohérence cosmétique avec la convention du fichier. 7/7 tests bins,
suite complète core 808/808 passés (106 skipped, stable).

Base Task 4: a992b78
Task 4: complete (commit c59950d, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). `bins`
ajouté à `STAT_KEYS`, `buildAggregateBody` transmet `groupBy` tableau
tel quel + `bins` en `Number`, helper `statRowId` (jointure `"|"` pour
id composite multi-champs). Équivalence byte-for-byte du chemin
single-field vérifiée par le reviewer (`String(row[categoryKey] ?? "")`
identique à l'ancien code). `bins` confirmé routé vers le body (via
`STAT_KEYS`) et non vers `filters`. Ligne manquant un champ groupBy
dégrade proprement en segment vide (pas de `"undefined"`). Tests
réels via mock HTTP msw, pas de mocks internes. 86/86 tests (3
nouveaux + 83 existants). 2 Minor notés (non bloquants) : `bins: 0`
traité comme absent (`if (query.bins)` falsy) — cohérent avec le
pattern existant `bucket`/`split`, pas une régression ; rapport de
l'implémenteur un peu redondant avec le diff (pas un défaut de code).

Base Task 5: c59950d
Task 5: complete (commit 567d95d, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). Champ
"Grouper par" gagne `parseGroupBy` (CSV → `string[]`, sinon la valeur
`raw` d'origine retournée telle quelle — byte-for-byte inchangé pour
tout appelant single-field, y compris virgule finale ou espaces,
vérifié par le reviewer sur l'expression de retour elle-même, pas
seulement les tests) + `groupByDisplayValue` miroir. Nouveau champ
"Nombre de classes" écrit `query.bins` via `patchQuery` (merge
superficiel, n'affecte aucun autre champ — vérifié par lecture directe
du helper). Tests réels via `fireEvent`/`userEvent` sur DOM rendu.
10/10 tests (2 nouveaux + 8 existants). 2 Minor notés (non bloquants) :
bornes `min`/`max` sur l'input `bins` sont de simples indices HTML5,
aucune validation cliente réelle (le bornage 1-100 est fait
côté core, Task 3) ; pas de test unitaire dédié aux cas limites de
`parseGroupBy` (virgule finale, double virgule) — corrects par lecture
du code mais non figés par un test.

Base Task 6: 567d95d
Task 6: complete (commits 6a9f447, abbae68 ; 1 Important trouvé et
corrigé en 1 round de fix). `ChartProps.encodings`/`bins` déclarés
(non consommés hors funnel/histogram ici), branches `funnel` (mirroir
de `pie`) et `histogram` (lit `bucketStart`/`bucketEnd`/`count`) ajoutées
avant le fallback bar/line/area/scatter, confirmées ne jamais tomber
dedans. Les 10 types existants byte-for-byte inchangés (vérifié par le
reviewer sur les lignes de contexte du diff). 1 Important trouvé en 1re
revue (hérité du code littéral du brief, pas une déviation de
l'implémenteur) : le trigger de tooltip (`chartOption.ts`) ne couvrait
pas `funnel` dans la liste `pie|doughnut|gauge` → `"item"`, donc
funnel retombait sur `"axis"` (faux, funnel n'a pas d'axe cartésien).
Fix (abbae68) : ajout de `|| type === "funnel"` à la condition. Test
de régression ajouté, vérifié RED contre l'ancien code
(`expected 'axis' to be 'item'`) et GREEN après fix. Revue 2 : fix
vérifié minimal et correct, n'affecte aucun des 10 autres types, ne
touche pas `encodings`/`categoryField`/`valueField`/`bins`. 18/18
tests. 1 Minor laissé tel quel (non bloquant) : le nouveau test duplique
le littéral `funnelRows` déjà défini deux tests plus haut (stylistique).

Base Task 7: abbae68
Task 7: complete (commit ce55a83, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). Branche
`sankey` : lit `source`/`target`/`value` depuis `props.encodings`
(aucun repli sur `categoryField`/`valueField`), tag `_role` par nœud
("source" gagne en cas d'ambiguïté, vérifié à la main par le reviewer
sur le cas "Lyon" du test), single-hop uniquement (ignore `levels`).
Ajout non demandé par le brief mais divulgué explicitement dans le
rapport et jugé correct par le reviewer : `sankey` ajouté à la
condition de trigger tooltip (même défaut que le funnel de Task 6,
proactivement corrigé par l'implémenteur avant même la revue) — noté
comme "process nit" (aurait dû être signalé en attente d'accord
plutôt que committé directement) mais pas un défaut. 19/19 tests.
3 Minor notés (non bloquants) : pas de test dédié pour le trigger
tooltip sankey (contrairement au funnel de Task 6) ; pas de test pour
`encodings` vide ou self-loop (source===target) — comportement tracé
à la main comme sûr par le reviewer, juste non couvert ; la condition
de trigger devient une chaîne `||` à 5 branches, lisibilité en baisse
avec chaque nouveau type non-cartésien (déjà amorcé en Task 6).

Base Task 8: ce55a83
Task 8: complete (commit a1b69a0, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant).
`buildHierarchy` (Map indexé par chemin, sommation bottom-up via
`sumUp`, placeholder `"—"` pour niveau intermédiaire manquant) +
branche `treemap`/`sunburst` partagée. Sommation vérifiée à la main
par le reviewer sur les 3 cas du brief (15/5/10 Nord, 7 Sud, cas
placeholder). Ajout divulgué et jugé nécessaire (pas cosmétique) :
`treemap`/`sunburst` ajoutés au trigger tooltip `"item"` — sans lui
ces types seraient tombés dans le fallback cartésien bar/line/scatter
avec un trigger `"axis"` erroné, car la nouvelle branche treemap/
sunburst ne pose ni xAxis ni yAxis. 22/22 tests. 1 point ⚠️ noté (pas
un défaut de cette tâche) : le plafond "3 niveaux" du plan n'est
imposé nulle part dans `buildHierarchy` lui-même — le reviewer soupçonne
qu'il est appliqué côté UI (à vérifier en Task 11, dont le brief a bien
`{levels.length < 3 && <button>+ Niveau</button>}`). 1 Minor (non
bloquant) : pas de test au plafond exact 3 niveaux ni rows=[] (tracés
sûrs par lecture de code, non exécutés).

Base Task 9: a1b69a0
Task 9: complete (commits 63deb66, f24bfba ; 1 Important trouvé et
corrigé en 1 round de fix). `resolveClickFilter` généralise le
click→cross-filter : histogram → toujours `null` (confirmé
inconditionnel, 1re instruction de la fonction) ; sankey → `_role`
"source" mappe `encodings.source`, "target" mappe `encodings.target`,
rejette les clics d'arête (`dataType !== "node"`) ; treemap/sunburst →
profondeur clampée via `Math.min(Math.max(treePathInfo.length-1,0),
levels.length-1)` (racine → niveau 0, feuille → niveau max, sur-profond
→ clampé sans out-of-bounds, vérifié par trace manuelle). 1 Important
trouvé en 1re revue et vérifié indépendamment contre le code de
production réel de `chart.tsx` (pas seulement le rapport) : la branche
par défaut (bar/pie/line/funnel) retournait `null` dès que
`params.name` était absent, alors que le `handleClick` actuel de
`chart.tsx` ne bloque que sur `categoryField` manquant et retombe sur
`value: ""` sinon — divergence réelle qui aurait cassé l'équivalence
dont Task 11 a besoin pour remplacer la logique câblée en dur. Risque
pratique faible (ECharts fournit quasi toujours `name`) mais explicitement
requis par l'intention du brief ("resolve categoryField, like today").
Fix (f24bfba) : branche par défaut ne bloque plus que sur `field`
manquant, `value` retombe sur `""` si `name` absent — comportement
désormais byte-for-byte identique à `chart.tsx`. Branches
histogram/sankey/treemap/sunburst confirmées intactes (leurs propres
gardes `params.name == null` sont un choix de conception intentionnel
pour ces types neufs, pas une régression). Test de régression vérifié
RED contre l'ancien code puis GREEN après fix. Revue 2 : fix vérifié
minimal et correct, 0 nouveau problème. 28/28 tests. 3 Minor laissés
tels quels de la revue 1 (non bloquants) : pas de test au clamp
sur-profond de treemap ; `_role` ni "source" ni "target" retombe
silencieusement sur `encodings.source` (invariant non vérifié dans ce
diff, posé par `buildOption`) ; petite duplication
`{field, value: String(params.name)}` répétée 3 fois.

Base Task 10: f24bfba
Task 10: complete (commits ba69359, 39eb87d ; 1 Critical + 2 Important
trouvés et corrigés en 1 round de fix). `SunburstChart` importé +
enregistré dans `echarts.use([...])`, type `onClick` élargi en
sur-ensemble strict (vérifié par `tsc --noEmit`). 1 Critical trouvé en
1re revue et vérifié indépendamment par le contrôleur AVANT même la
revue (A/B direct sur `setup.ts` via copie de fichier, pas de commande
git) : l'implémenteur avait ajouté un mock global
`global.ResizeObserver` dans `shell/src/test/setup.ts` (hors périmètre
du brief, qui ne citait que `EChart.tsx`/`EChart.test.tsx`) — ce mock
global inversait une garde intentionnelle d'`AppRenderer.tsx`
(`typeof ResizeObserver === "undefined"`, utilisée pour figer le
breakpoint à "lg" en test) et cassait 2 tests d'`AppRenderer.test.tsx`
déjà verts, contredisant le rapport de l'implémenteur ("no
regressions"). 2 Important additionnels : le test `EChart.test.tsx`
mockait tout `echarts/core`/`echarts/charts`, rendant l'assertion
incapable de détecter un `SunburstChart` non enregistré (aurait
réussi même sans l'enregistrement) ; import `beforeEach` inutilisé
cassait `tsc --noEmit` (`noUnusedLocals`). Fix (39eb87d) : `setup.ts`
intégralement reverté (absent du diff base→head, preuve directe de
réversion complète) ; mock `ResizeObserver` isolé dans
`EChart.test.tsx` via `vi.stubGlobal`/`vi.unstubAllGlobals` en
`beforeEach`/`afterEach` (résout aussi l'import inutilisé) ; nouveau
test `useMock` capturé via `vi.hoisted`, assertion `toContain`
(égalité de référence) au lieu de `arrayContaining` suggéré initialement
par le contrôleur — l'implémenteur a détecté et documenté que
`arrayContaining` aurait été un piège à faux positif (égalité
structurelle : tous les mocks de type de graphique sont des `{}` nus,
donc déep-equal entre eux peu importe lequel est réellement
`SunburstChart`) ; ce point technique reçu comme un vrai constat,
re-vérifié indépendamment par le reviewer en revue 2 (sémantique
`toContain` vs `arrayContaining` confirmée exacte). Vérifié par
suppression temporaire de `SunburstChart` de `echarts.use([...])` :
le nouveau test échoue bien, puis fichier restauré (diff confirmé
identique). `EChart.test.tsx` 2/2, `AppRenderer.test.tsx` 28/28,
`npm run build` propre, suite complète 748/748 (101 fichiers), 0
échec. Revue 2 : les 3 findings vérifiés résolus directement sur le
diff (absence de `setup.ts` du diff = preuve de réversion complète,
pas seulement le rapport), 0 nouveau problème.

Base Task 11: 39eb87d
Task 11: complete (commit 7bbdc5d, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). 5 nouveaux
`CHART_TYPES`, `bins: 10` en défaut, `PropsPanel` gagne des blocs
conditionnels (`showCategoryValue`/`showSankeyEncodings`/
`showHierarchyEncodings`/`showBins`) suivant le pattern déjà établi par
`showCompare`. Plafond "3 niveaux" (laissé non imposé par
`buildHierarchy` en Task 8) atterrit ici côté UI : le bouton
"+ Niveau" disparaît dès `levels.length >= 3`, confirmé par lecture
directe du code. `categoryField`/`valueField` masqués pour
sankey/treemap/sunburst, gardés pour funnel/histogram (conforme au
brief). `handleClick` délègue à `resolveClickFilter` — vérifié que
l'appel ne réintroduit pas le bug `params.name == null` corrigé en
Task 9 (comparé ligne à ligne à l'ancienne logique câblée en dur
supprimée, correspondance verbatim). Scope confirmé strictement
limité à `chart.tsx`/`chart.test.tsx` (pas de `setup.ts`, la régression
de Task 10 ne se reproduit pas). Test d'intégration réel (rendu
`AnalyticsContextProvider`, clic réel, assertion sur l'état
`crossFilter` via un composant `Probe`), pas de mock de la logique
métier. RED 5/5 échoués → GREEN 18/18 `chart.test.tsx` → suite complète
753/753 (101 fichiers) → build propre. 2 Minor notés (non bloquants) :
pas de test à la limite exacte du plafond 3 niveaux (seulement 1→2
testé, la logique elle-même vérifiée correcte par lecture) ; commit en
anglais (cohérent avec le précédent mixte déjà établi dans la série
SP-14f).

Base Task 12: 7bbdc5d
Task 12: complete (commits eea4094, 8d75c24, 5461b34 ; 1 Important
trouvé (plan-mandated, hérité du code littéral du brief) et corrigé en
2 rounds de fix). 4 scénarios E2E ajoutés en append-only à
`analytics-context.spec.ts` (0 scénario existant touché) : clic
funnel → cross-filter réel sur une table (requête filtrée +
disparition visible d'une ligne) ; rendu seul sankey/treemap/sunburst
(3 widgets indépendants, layouts non cliquables de façon fiable —
scope délibérément limité, confirmé respecté) ; histogramme rendu +
absence de cross-filter au clic. L'implémenteur a détecté et corrigé
3 bugs réels dans le code littéral du brief avant même la revue :
mauvais label pour "Champ valeur" (aria-label réel vs texte du
&lt;label&gt;), clic "+ Niveau" manquant avant de remplir "Niveau 1"
(l'input n'existe pas tant qu'aucun niveau n'est ajouté), coordonnée
de clic funnel non fiable (0.25 atterrissait sur canvas transparent,
remplacée par 0.42 — valeur réutilisée d'ailleurs dans le même
fichier, donc déjà éprouvée). Les 3 corrections vérifiées indépendamment
par le reviewer contre le code source réel (chart.tsx, pas seulement
le rapport). 1 Important trouvé en 1re revue, labellisé plan-mandated
(structure identique au snippet littéral du brief) : le scénario
histogramme n'avait aucun widget consommateur (pas de table sur le
même dataset), rendant l'assertion "jamais de cross-filter" vacuously
true — elle aurait réussi identiquement même si `resolveClickFilter`
avait régressé pour histogram. Fix round 1 (8d75c24) : ajout d'une
table réelle sur le même dataset via la technique "promue puis
retypée en statistics" (vérifiée par le reviewer contre le code source
réel de `DataSourcePanel.tsx` — le sélecteur de type ne touche jamais
`datasetId`, confirmé par un spread superficiel, et corroborée par un
usage préexistant identique ailleurs dans le même fichier de specs) +
mock `/collections/pops/items` filtrant sur `city`. Revue round 2 :
fix du round 1 approuvé sur le fond, mais a détecté un NOUVEAU risque
introduit par le fix lui-même — la coordonnée de clic histogramme
(0.5, 0.5) n'avait jamais été vérifiée empiriquement (contrairement au
funnel dans le même commit), et selon la sémantique de dispatch de clic
d'ECharts (tracée dans le code source du reviewer), un clic qui manque
tout élément graphique ne déclenche jamais l'événement "click" —
laissant le test vacuously true par un mécanisme différent (clic dans
le vide plutôt qu'absence d'abonné). Fix round 2 (5461b34) :
échantillonnage de pixels empirique confirmant que (0.5, 0.5) tombait
bien dans l'espace vide entre les deux barres ; remplacé par (0.72,
0.45), vérifié à l'intérieur du remplissage solide de la barre haute.
Preuve décisive : le garde `if (chartType === "histogram") return
null;` désactivé temporairement dans `chartOption.ts` → le test E2E
échoue bien (la table se filtre, une ligne disparaît) → garde restauré
(`git diff` confirmé propre, non commité) → test repasse au vert.
Revue round 3 : `chartOption.ts` confirmé absent du diff final (la
désactivation temporaire n'a pas fuité dans le commit), toujours
exactement 3 scénarios SP-14f, coordonnée cohérente avec les mesures
empiriques documentées en commentaire (même style que le funnel).
Suite E2E ciblée 3/3 à chaque round, suite complète 69/69 (39 specs)
au round final, vérification finale cross-stack (pytest 808/106
skipped, vitest 753/753, tsc+build propre) déjà passée par
l'implémenteur en avance sur la tâche finale du plan.

## SP-14f COMPLET — 12 tâches, 18 commits de tâches + 1 commit de
## revue finale (19 au total). Rounds de fix : Task 3 (1, corruption
## silencieuse), Task 6 (1, tooltip funnel), Task 7 (0, ajout
## proactif divulgué), Task 8 (0, ajout proactif divulgué), Task 9
## (1, divergence clic par défaut), Task 10 (1, régression cross-
## fichier + test non discriminant), Task 12 (2, scénario histogramme
## vacuously true deux fois de suite). HEAD=5461b34 avant revue finale.

## Revue finale de branche (opus, 1888fc1..5461b34, 18 commits) —
## 0 Critical, 1 Important, 3 Minor, ready to merge: With fixes.
## Cohérence cross-tâche vérifiée en profondeur (au-delà des revues
## par tâche) : flux de données bout-en-bout core→itemClient→
## chartOption tracé et confirmé correct (tidy rows multi-champs →
## `statRowId` id composite → branches sankey/treemap) ; forme
## histogramme (`bucketIndex`/`bucketStart`/`bucketEnd`/`count`)
## confirmée identique entre core (Task 3) et chartOption (Task 6) ;
## SQL paramétrée vérifiée sans injection ; contrainte n°1 "zéro
## changement de comportement" tenue et vérifiée indépendamment
## (byte-for-byte sur `statRowId` single-field, `resolveClickFilter`
## default branch, trigger tooltip additif) ; régression Task 10
## confirmée réellement absente du diff final (`setup.ts` absent des
## fichiers modifiés). 1 Important trouvé, propre aux tâches
## individuelles mais invisible à leur échelle (chacune ne voyait
## qu'un fichier) : le contrôle "Nombre de classes" du panneau du
## graphique (`props.bins`, ajouté Task 11) était mort — le
## binning réel passe uniquement par `query.bins` de la source de
## données (Task 5) ; `chartOption.ts` ne lit jamais `props.bins`.
## Pire qu'une redondance : un auteur réglant les classes UNIQUEMENT
## sur le panneau du graphique obtenait un histogramme cassé
## ("NaN–NaN"). Fix (3d28b64) : contrôle mort retiré de `chart.tsx`
## (`showBins`, `defaultProps.bins`) et du type `ChartProps.bins`
## dans `chartOption.ts`, test associé supprimé ; contrôle
## fonctionnel de `DataSourcePanel.tsx` non touché. Vérifié par grep
## qu'aucun autre code ne lisait `ChartProps.bins` avant suppression.
## Tests ciblés 45/45, suite complète 752/752 (101 fichiers), build
## propre, E2E complet 69/69 (39 specs, y compris les 3 scénarios
## SP-14f). Revue de vérification (opus) : suppression confirmée
## complète et sans effet de bord sur le disque réel (pas seulement
## le rapport), contrôle `DataSourcePanel` confirmé intact, commit
## de fix scopé à exactement 3 fichiers (+1/−22 lignes). 3 Minor de
## la revue finale laissés tels quels (non bloquants, cosmétiques/UX
## secondaires) : sankey/treemap/sunburst n'exposent aucune UI pour
## `encodings.value` (toujours inféré, dégénère si la ligne porte une
## dimension non-niveau — touche le smoke test Task 12 dont le
## fixture `levels` ne correspond pas exactement au `groupBy` du
## mock, rendu quand même valide car seul le nombre de canvas est
## vérifié) ; petite duplication `{field, value: String(params.name)}`
## dans `resolveClickFilter` ; bornes `min`/`max` HTML5 sur les inputs
## bins = indicatives seulement (le vrai bornage 1-100 est côté
## serveur, Task 3, ce qui est correct). HEAD=3d28b64.
## SP-14f READY TO MERGE — prêt pour finishing-a-development-branch.
