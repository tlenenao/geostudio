# SP-14d — Menu « explorer » & panneau « voir les entités » — Progress Ledger

Plan: docs/superpowers/plans/2026-07-26-sp14d-menu-explorer-voir-entites.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@7ef1f1a (plan + spec SP-14d committés, ledger SP-14c finalisé).

Note : ce fichier remplace le ledger SP-14c (complet, mergé — PR #52
dev->main ouverte) — même fichier scratch réutilisé par convention du
dépôt ; contenu SP-14c préservé dans l'historique git (commit 7ef1f1a
pour la finalisation du ledger, a80f35a pour le code).

## Pré-vol

Scan des 6 tâches (Task 1 `ExplorerContext`, Task 2 `ExplorerMenu`, Task 3
wiring des 5 widgets, Task 4 `ExplorerDrawer`, Task 5 wiring
`AppRenderer`, Task 6 E2E) contre les 6 contraintes globales (zéro
changement core, gating identique à `AnalyticsContextIndicator`
`mode !== "edit" && interactions === "auto"`, exactement 5 types de
widgets éligibles chart/table/list/map/indicator — jamais les filtres,
le tiroir n'écrit jamais dans `AnalyticsContextState`, `aria-label`
systématique, copie française, 18+ specs E2E inchangées, cap 200 lignes
+ pagination 20/page) : pas de contradiction. Le plan fournit du code
complet et littéral pour chaque tâche (types, composants, wiring, 2
scénarios E2E) — transcription + tests, pas de conception à faire.
Tâches strictement séquentielles (Task 2 consomme `ExplorerContext` de
Task 1 ; Task 3 consomme `ExplorerMenu` de Task 2 ; Task 4 consomme
`ExplorerContext` de Task 1 et `derivePatch`/`AnalyticsContext`
existants ; Task 5 consomme Task 1 et Task 4, wire `AppRenderer` ; Task 6
exerce l'UI réelle produite par les Tasks 1-5) — pas de parallélisation
possible en pratique.

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: 7ef1f1a
Task 1: complete (commit 8351e8b, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). `ExplorerContext`
transcription exacte du brief (types, split target/enabled/setters,
gating `open` no-op si `!enabled`, `close` toujours actif). 5/5 tests,
suite complète 684/684 (0 régression).

Base Task 2: 8351e8b
Task 2: complete (commit f3c7856, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). `ExplorerMenu`
transcription exacte, interface Task 1 réellement vérifiée (pas
seulement le brief). 1 Minor noté (pas de fermeture click-outside/
Escape — absent aussi ailleurs dans `shell/src/builder`, pas un écart de
convention, potentiellement à revisiter une fois câblé dans les widgets
réels en Task 3). 4/4 tests, suite complète 98 fichiers/688 tests (0
régression).

Base Task 3: f3c7856
Task 3: complete (commit c048d6c, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). `ExplorerMenu` câblé
dans les 5 chemins de rendu (chart/list/table/map/indicator), premier
enfant d'un wrapper `relative`. Bon réflexe de l'implémenteur :
`mapWidget.tsx` utilise `ctx.data?.datasetId` (pas `data.datasetId` —
ce composant ne déstructure pas de `data` local), déviation du pattern
des 3 autres fichiers vérifiée correcte par le reviewer. Filtres
(`selectFilter`/`sliderFilter`/`dateRangeFilter`) non touchés, gating
laissé à Task 5 comme prévu. 5/5 nouveaux tests (chart, list, table,
map, indicator), suite complète 98 fichiers/693 tests (0 régression),
build clean.

Base Task 4: c048d6c
Task 4: complete (commits 2131705, 76ed868, 1 finding Important x2 corrigés
au 1er round de revue). `ExplorerDrawer` transcription conforme au brief,
tous signatures existantes (`derivePatch`, `AnalyticsContext`, `ItemClient`,
`types.ts`, `MapView`) vérifiées identiques par l'implémenteur, aucune
adaptation requise. Invariant central vérifié indépendamment par le
reviewer : id synthétique `"__explorer__"` jamais un id de widget réel →
exclusion `derivePatch` (`originSourceId !== source.id`) toujours fausse
pour le tiroir → reste filtré même ouvert depuis son propre widget
d'origine. Invariant "jamais d'écriture dans AnalyticsContextState" vérifié
par grep direct (0 occurrence `setCrossFilter`/`setExtent`/`setTimeRange`).
2 Important trouvés en 1re revue et corrigés : (1) `aria-label`/clavier
manquants sur les boutons pagination et la ligne cliquable du tableau
(gap venu du code littéral du brief lui-même, mais contraire à la
contrainte globale du plan — corrigé, pas un conflit réel puisque le
correctif suit la contrainte du plan, pas ne la contredit) ; (2) état de
chargement/erreur du `datasetQuery` masqué (tombait sur "Aucune entité"
pendant le chargement du dataset ou si `getDatasetConfig` échouait) —
corrigé en combinant les deux `useQuery`. Re-revue (sonnet) : les 2
findings marqués RESOLVED indépendamment (lecture directe du code final,
pas seulement le rapport), invariants intacts, nouveaux tests non
tautologiques (clavier Enter/Espace réellement déclenché, promesses
manuelles pour distinguer chargement/vide). 12/12 tests ciblés, suite
complète 99 fichiers/705 tests, build clean.

Base Task 5: 76ed868
Task 5: complete (commits 88d5b14, df409f7). Wiring `AppRenderer` conforme
au brief : `ExplorerProvider enabled={...}` et `<ExplorerDrawer />` montés
autour de l'arbre existant, `ExplorerDrawer` monté une seule fois,
inconditionnel (se gate lui-même via `useExplorerTarget()`/`open()`
no-op si `!enabled`). 1 Important trouvé en 1re revue, labellisé
plan-mandated par le reviewer (le brief donnait littéralement les deux
occurrences du gate `mode !== "edit" && config.interactions === "auto"`
dupliquées) mais approuvé quand même par le reviewer (pas un vrai
conflit de comportement) : risque de désynchronisation future entre le
gate d'`ExplorerProvider` et celui d'`AnalyticsContextIndicator`, deux
littéraux textuellement identiques sans source commune. Corrigé sans
demander (le fix ne contredit aucune exigence du plan, il consolide la
même valeur en un seul `const analyticsUiEnabled`, comportement
strictement inchangé) : hoist en `AppRenderer.tsx:98`, consommé par les
2 sites d'usage. Re-revue (sonnet) : RESOLVED vérifié directement sur le
fichier final, aucune 3e occurrence dupliquée, refactor pur confirmé
sans dérive de comportement. Suite complète 706/706 (les 2 rounds),
build clean.

Base Task 6: df409f7
Task 6: complete (commit 543e3c8, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). 2 scénarios
E2E ajoutés à `analytics-context.spec.ts` (append-only, 120 insertions/
0 suppression, vérifié par le reviewer sur le diff). Scénario 1 prouve
le comportement central du plan : ouvrir « Voir les entités » depuis un
widget différent PUIS depuis le widget d'origine du clic garde les deux
fois les lignes filtrées (id synthétique `"__explorer__"` jamais exclu
par l'auto-exclusion du cross-filter), + fermeture bouton et Échap.
Scénario 2 : non-régression `interactions: "manual"` → 0 bouton
Explorer. 1 ajustement de test (pas de code produit touché) :
`page.getByRole("cell", {name:"Nord"})` ambigu une fois le tiroir ouvert
(la Table sous-jacente affiche aussi "Nord") → scopé à
`page.locator("table").first()`, argument structurel vérifié
indépendamment par le reviewer (ExplorerDrawer monté avant
DataProvider/GridCanvas dans AppRenderer.tsx, aucun createPortal dans le
dépôt) — pas une coïncidence de layout. 1 Minor noté (un `data-testid`
sur le tiroir serait plus robuste qu'un raisonnement sur l'ordre JSX à
long terme, pas bloquant). 11/11 ciblé, suite E2E complète 62/62,
suite unitaire 706/706, build clean.

## SP-14d COMPLET — 6 tâches, 2 rounds de fix (Task 4 : 2 Important —
## aria-label/clavier + état chargement dataset masqué ; Task 5 : 1
## Important — gate dupliqué en 2 littéraux, hoisté en 1 const), tout
## re-vérifié indépendamment à chaque étape (pas seulement les rapports).
## HEAD=543e3c8.

## Revue finale de branche (opus, 7ef1f1a..543e3c8, 8 commits) — 0
## Critical, 0 Important, 3 Minor, ready to merge: Yes. Id synthétique
## `"__explorer__"` tracé bout-en-bout via `derivePatch`/`itemClient`
## (jamais exclu par l'auto-exclusion cross-filter, confirmé sur le code
## réel). Gate `analyticsUiEnabled` bien source unique pour
## `ExplorerProvider` et `AnalyticsContextIndicator`. Tiroir vérifié
## sans écriture dans le contexte analytique. 5 widgets cohérents,
## filtres non touchés, core non touché.

3 Minor (aucun bloquant) : (1) le menu `⋮` disparaît à 0 ligne sur
chart/list/table (early return avant `ExplorerMenu`) mais reste visible
sur indicator/map (pas d'early return) — incohérence mineure entre
widgets jumeaux, acceptable (le tiroir afficherait de toute façon
"Aucune entité" dans cet état) ; (2) `<tr role="button">` autour de
`<td>` questionnable en sémantique ARIA/table (role `row` implicite
écrasé) — accepté tel quel en revue de tâche, refait surface ici pour
mémoire ; (3) locator E2E `page.locator("table").first()` dépend de
l'ordre de montage JSX non verrouillé structurellement (même note que
la revue Task 6) — un `data-testid` serait plus robuste à terme.

## SP-14d COMPLET — 6 tâches + revue finale, tout vérifié
## indépendamment à chaque étape. HEAD=543e3c8. Prêt pour
## finishing-a-development-branch.
