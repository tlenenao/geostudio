# SP-14e — KPI riche & séries temporelles comparées — Progress Ledger

Plan: docs/superpowers/plans/2026-07-28-sp14e-kpi-riche-series-comparees.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@2d18b9c (plan + spec SP-14e committés).

Note : ce fichier remplace le ledger SP-14d (complet, revue finale
ready-to-merge) — même fichier scratch réutilisé par convention du
dépôt ; contenu SP-14d préservé dans l'historique git (commit f88af51
pour la finalisation du ledger, 543e3c8 pour le dernier code).

## Pré-vol

Scan des 6 tâches (Task 1 `bucket` param core, Task 2 passthrough
itemClient, Task 3 `comparisonWindow.ts`, Task 4 `indicator` enrichi,
Task 5 `chart` mode comparaison, Task 6 E2E) contre les 5 contraintes
globales (chaque nouvelle prop optionnelle et absente par défaut = zéro
changement de comportement ; `bucket` absent = comportement inchangé
byte-for-byte, suite `test_analytics_aggregate.py` verte sans
modification ; seulement `previous`/`sameLastYear`, pas de granularité
de bucket configurable, pas de texte de message CEL — juste une
pastille à 3 niveaux ; commits en français / code en anglais ; branche
`dev`) : pas de contradiction. Le plan fournit du code complet et
littéral pour chaque tâche (types, implémentation, tests unitaires et
E2E) — transcription + tests, pas de conception à faire. Dépendances
d'interface : Task 3 (`comparisonWindow.ts`) est consommé directement
par Task 4 et Task 5 ; Task 2 (passthrough `bucket`) est un
prérequis fonctionnel pour que les requêtes bucketées de Task 3/4/5
atteignent réellement le cœur, mais aucune des deux ne l'importe — pas
de couplage de code, juste d'ordre logique ; Task 6 exerce l'UI réelle
produite par Tasks 1-5. Tâches exécutées dans l'ordre du plan (1→6).

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: 2d18b9c
Task 1: complete (commit 1338041, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). `bucket`
transcrit du brief presque littéralement : champ `Literal["day","week",
"month"] | None`, garde `bucket` sans `groupBy` → `UnknownAggregateField`,
`cat_expr` basculé sur `DATE_TRUNC(..., TRY_CAST(... AS TIMESTAMP))`
uniquement quand `bucket` est fourni (branche par défaut inchangée,
comportement byte-for-byte préservé). Réutilise les helpers SQL déjà
audités `_sql_lit`/`_qi`, pas de nouvelle interpolation de chaîne.
4/4 nouveaux tests (day, month, erreur sans groupBy, cas TRY_CAST
NULL/regroupement), suite complète 21/21 (0 régression). 2 Minor notés
par le reviewer (pas bloquants) : pas de test dédié `bucket="week"`
(seuls day/month couverts, conforme au brief) ; le bucket NULL est
sérialisé comme chaîne littérale `"None"` dans `category_key` (via
`_pivot_measures`/`_pivot_split` existants) — à garder à l'esprit côté
shell (Task 3+) si un jour un filtrage sur cette valeur est nécessaire.

Base Task 2: 1338041
Task 2: complete (commit 26d925c, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). `bucket` ajouté à
`STAT_KEYS` et `buildAggregateBody` (transcription exacte du brief).
Bénéfice collatéral relevé par le reviewer : `STAT_KEYS` étant partagé
avec `buildFeaturesUrl`, `bucket` est aussi correctement filtré des
query params `/items` pour les sources `type: "features"` — cohérent
avec le traitement existant de `bbox`/`agg`, aucun effet de bord.
1/1 nouveau test (positif + négatif : `body.bucket` posé, `body.filters`
reste `undefined`), suite complète `itemClient.test.ts` 83/83.

Base Task 3: 26d925c
Task 3: complete (commit a424e0f, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). `comparisonWindow.ts`
créé (fichier pur, 2 nouveaux fichiers, aucun fichier existant modifié).
Signatures réelles de `derivePatch`/`AnalyticsContextState`/
`EMPTY_ANALYTICS_CONTEXT`/`DataSource`/`DatasetConfig` vérifiées par
l'implémenteur ET indépendamment par le reviewer, correspondance exacte
avec le brief. Point de correction subtil bien géré par réutilisation
(pas de logique neuve) : `windowedStatisticsSource` passe
`originSourceId` comme id de la source synthétique, ce qui fait
fonctionner correctement l'auto-exclusion cross-filter de `derivePatch`
(`originSourceId !== source.id`) pour les fenêtres de comparaison.
Arithmétique de dates UTC-safe (`Date.UTC`/`getUTCFullYear` partout,
pas de dérive de fuseau horaire sur des chaînes ISO date-only),
clamping année bissextile testé sur une vraie transition
(2024-02-29 → 2023-02-28). 6/6 tests, comportement calculé réel (pas de
mocks). 2 Minor notés (pas bloquants) : absence de filtre temporel
silencieuse si `dataset.timeField` est absent (héritée du contrat
`derivePatch`, à documenter pour Task 4/5) ; pas de contrainte de type
sur le format `{from,to}` (accepte toute chaîne), non risqué vu les
call sites actuels.

Base Task 4: 26d925c → a424e0f (Task 3)
Task 4: complete (commits aa3be6d, 2646bbe, 3c93ae0 ; 1 Important
trouvé et corrigé en 2 rounds de fix). Réécriture complète
`indicator.tsx`/`indicator.test.tsx` conforme au brief : badge delta
vs référence, sparkline, pastille de seuil CEL à 3 niveaux, tout
strictement additif et gated sur `active = wantsComparison &&
Boolean(dataset?.timeField) && Boolean(timeRange)`. 1 Important trouvé
en 1re revue, **labellisé plan-mandated** (code littéral du brief) :
les clés de cache `useQuery` (`kpi-value`/`kpi-reference`/
`kpi-sparkline`) ne incluaient que `datasetId`/fenêtre/`agg`/`field`,
sans l'id de la source d'origine ni la requête résolue (post-patch
cross-filter) — contrairement au pattern établi `DataContext.tsx`
(`["datasource", s.id, merged.query]`). Risque réel : deux widgets
`indicator` sur le même dataset+métrique auraient pu se marcher dessus
en cache sous cross-filter actif. **Décision utilisateur demandée et
obtenue : corriger.** Fix (2646bbe) : les 3 `useQuery` calculent
maintenant la `DataSource` résolue une fois via `windowedStatisticsSource`
et clés sur `[label, source?.id, source?.query]`, `enabled` inchangé,
0 violation Rules of Hooks. Revue 2 : fix vérifié correct mais a
signalé un 2e Important — aucun test n'exerçait le scénario de
collision à 2 widgets (uniquement raisonnement statique). Fix 2
(3c93ae0) : test ajouté avec 2 widgets partageant un seul `QueryClient`,
cross-filter ciblant l'un et pas l'autre (`originSourceId` test tracé à
la main par le reviewer contre `derivePatch`, confirmé non tautologique
et confirmé qu'il aurait échoué avec l'ancienne clé). Revue finale
(round 3) : les 2 findings marqués RESOLVED indépendamment sur les 3
commits, aucune dérive, 0 changement hors scope. 12/12 tests ciblés,
suite complète 721/721 (100 fichiers), build clean.

Base Task 5: 3c93ae0
Task 5: complete (commits dd896e3, 5dc3f21, review clean au premier
passage — ✅ spec compliant, task quality Approved, 0 finding
bloquant). `buildCompareOption` (chartOption.ts) + mode comparaison
`chart.tsx` conformes au brief : 2 séries alignées sur axe relatif
(Jour/Semaine/Mois N), restreint à line/area, gating identique à
`indicator` (`compareEnabled` + `ctx.timeRange` actif + `timeField` du
dataset, sinon repli sur le graphique normal). Réutilise `valueField`
existant comme mesure (`agg = valueField ? "sum" : "count"`) plutôt
qu'une prop redondante, comme prévu par la note de conception du brief.
**Déviation délibérée du code littéral du brief appliquée dès
l'implémentation** (pas un correctif après-coup cette fois) : mêmes
clés de cache `useQuery` bugguées que Task 4 identifiées dans le code
littéral du brief (`["chart-compare-current", datasetId, timeRange,
bucket, agg, valueField]`, sans id de source ni requête résolue) —
l'implémenteur a été instruit dès le dispatch de suivre le pattern déjà
corrigé et revu d'`indicator.tsx` (`useKpiComparison`) : source résolue
calculée une fois via `windowedStatisticsSource`, clé sur `[label,
source?.id, source?.query]`. Vérifié par le reviewer : structurellement
identique au pattern d'`indicator.tsx`, `enabled` équivalent, aucune
régression introduite. 3 Minor notés (pas bloquants) : état vide en
mode comparaison rend un graphique à axe 0 point plutôt que "Aucune
donnée" (incohérence UX mineure, non spécifiée) ; pas de test dédié
`compareEnabled` sur chartType bar (couvert indirectement) ; pas de
test d'intégration `comparePeriod: "sameLastYear"` au niveau Component
(couvert unitairement en Task 3). Suite complète 727/727 (100
fichiers), build clean.

## Note méthodologique : la déviation de clé de cache d'indicator.tsx
## (Task 4) a été appliquée proactivement à Task 5 dès le dispatch de
## l'implémenteur, évitant un round de fix redondant — decision
## utilisateur du round Task 4 étendue par cohérence à un pattern de
## code identique, pas une nouvelle question posée.

Base Task 6: 5dc3f21
Task 6: complete (commits ce7ea2a, 503faf3, 1 Important trouvé et
corrigé en 1 round de fix). 4 scénarios E2E ajoutés à
`analytics-context.spec.ts` (append-only, 15 scénarios au total,
0 code produit modifié, 0 scénario existant/helper touché). Scénarios
12/14/15 transcription fidèle du brief. Le brief lui-même contenait un
bug réel dans le scénario 13 : `page.getByLabelText(...)` n'existe pas
dans l'API Playwright (syntaxe Testing Library, pas Playwright) —
correction nécessaire, pas une déviation de spec. 1 Important trouvé
en 1re revue sur le correctif choisi par l'implémenteur : sélecteur CSS
`[aria-label*="critique"], [title*="critique"]` (match partiel sur 2
attributs, dont `title` qui n'est jamais posé nulle part dans le code —
confirmé par grep, ainsi que par un script Playwright autonome montrant
que l'équivalent Playwright réel `page.getByLabel("Seuil critique
atteint")` (match exact) fonctionne correctement contre le
`<span aria-label="...">` réel d'`indicator.tsx`) — risque de masquage
de régression future via le match partiel. Fix (503faf3) : remplacé
par `page.getByLabel("Seuil critique atteint")`, exact, cohérent avec
le style du reste du fichier. Revue 2 : fix vérifié, diff strictement
scopé à la ligne concernée, rien d'autre n'a bougé. 1 Minor laissé tel
quel (non bloquant, hors scope de la revue) : une route mock
`/collections/analytics/aggregate` ajoutée au scénario 13 n'est en
réalité jamais appelée (le KPI de ce scénario n'a ni `referencePeriod`
ni `sparkline`, donc `useKpiComparison` reste inactif et la valeur
affichée vient du chemin `flatValue`/`ctx.data` existant, pas de
l'agrégat) — route inoffensive mais diagnostic de la justification
initialement incorrect, à noter pour la revue finale de branche.
4/4 scénarios ciblés + suite E2E complète 66/66 (18 specs), à chaque
round.

## SP-14e COMPLET — 6 tâches, 3 rounds de fix au total (Task 4 : 2
## Important — clé de cache dupliquée puis test de régression manquant ;
## Task 6 : 1 Important — sélecteur E2E trop permissif), tout re-vérifié
## indépendamment à chaque étape (pas seulement les rapports). Décision
## utilisateur obtenue explicitement pour le premier finding
## plan-mandated (Task 4, clé de cache), puis le même pattern de
## correctif appliqué proactivement à Task 5 sans re-demander (code
## identique, décision déjà prise). HEAD=503faf3. Prêt pour la revue
## finale de branche.

## Revue finale de branche (opus, 2d18b9c..503faf3, 10 commits) —
## 0 Critical, 1 Important, 6 Minor, ready to merge: With fixes.
## Cohérence cross-task confirmée : les 2 correctifs de clé de cache
## (Task 4 réactif, Task 5 proactif) convergent réellement vers le même
## pattern `[label, source?.id, source?.query]`, identique à l'idiome
## `DataContext.tsx` (`["datasource", s.id, merged.query]`) — vérifié
## sur le code final, pas seulement les rapports. `bucket` tracé
## bout-en-bout core→itemClient→comparisonWindow→widgets, aucune
## injection SQL (Literal fermé + `_sql_lit`). Contrainte "zéro
## changement de comportement" tenue par construction et vérifiée E2E
## (scénario 15). 1 Important : asymétrie de couverture — `indicator`
## avait un test dédié de non-collision à 2 widgets (exigé par la
## revue Task 4) mais `chart` (qui porte le même correctif appliqué
## proactivement en Task 5) n'en avait pas. Fix (commit f136501) :
## test ajouté à `chart.test.tsx`, vérifie l'isolation via les
## arguments d'appel du mock `queryDataSource` (pas le DOM, le mock
## EChart n'exposant que le nombre de séries) — prouvé qu'il aurait
## échoué avec l'ancienne forme de clé (les 6 entrées identiques pour
## les 2 widgets → dédoublonnage TanStack Query → un seul appel
## `queryFn` → assertion double impossible à satisfaire). Revue ciblée
## du fix : Approved, 0 issue, scope propre (1 fichier test seul).
## 6 Minor non bloquants (déjà notés dans les tâches individuelles +
## nouveaux) : pas d'état vide dédié en mode comparaison chart (rend un
## axe 0 point plutôt que "Aucune donnée") ; `chartType: "area"` rendu
## en `type: "line"` dans `buildCompareOption` (conforme au code
## littéral du plan, à confirmer délibéré) ; bucket `"week"` jamais
## testé côté core ; chevauchement de borne `from` entre fenêtre
## courante et référence pour `referenceWindow("previous")` (inhérent
## à la conception du plan, testé tel quel) ; `ChartProps` n'inclut pas
## `compareEnabled`/`comparePeriod` dans son typage (lus depuis
## `props` brut, cosmétique) ; route mock inutilisée scénario 13 E2E.
## HEAD=f136501. SP-14e prêt pour finishing-a-development-branch.
