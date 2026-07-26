# SP-14c — Filtres typés (select/slider) & indicateur de contexte — Progress Ledger

Plan: docs/superpowers/plans/2026-07-26-sp14c-filtres-types-indicateur.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@3874711 (plan + spec SP-14c committés).

Note : ce fichier remplace le ledger SP-Deploy-e (clos, ready-to-merge,
plan non lié — provisioning Proxmox) — même fichier scratch réutilisé par
convention du dépôt ; contenu SP-Deploy-e préservé dans l'historique git.
Le ledger SP-14b (18 tâches, complet, merge-ready) était resté non commité
en fin de session précédente ; mis de côté via `git stash` (message "SP-14b
final ledger/briefs (uncommitted, pre-existing at session start)") avant
réutilisation de ce fichier, pour ne rien perdre.

## Pré-vol

Scan des 6 tâches (Task 1-2 core hooks `AnalyticsContext`/`derivePatch`,
Task 3-4 widgets `selectFilter`/`sliderFilter`, Task 5 indicateur + wiring
`AppRenderer`, Task 6 E2E) contre les 6 contraintes globales (additivité,
zéro changement core, copie française, `aria-label` systématique, 18+
specs E2E inchangées, `originSourceId` = `props.dataSourceId` du widget) :
pas de contradiction. Le plan fournit du code complet et littéral pour
chaque tâche (types, composants, wiring, 4 scénarios E2E) — transcription +
tests, pas de conception à faire. Tâches strictement séquentielles (Task 2
consomme `CrossFilterValue` de Task 1 ; Tasks 3/4 consomment les hooks de
Task 1 ; Task 5 consomme Task 1 et wire `AppRenderer` ; Task 6 exerce les
widgets des Tasks 3-5 via l'UI réelle) — pas de parallélisation possible en
pratique.

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: 3874711
Task 1: complete (commit b651175, review clean — ✅ spec compliant, task
quality Approved). `CrossFilterValue`/`ClearCrossFilter`/`useClearCrossFilter`
transcription exacte du brief, `sameCrossFilterValue` étendu (comparaison
`===` pour deux strings, `JSON.stringify` sinon — couvre range/array).
8/8 tests (5 préexistants + 3 nouveaux). 1 finding Important signalé
plan-mandated (pas une déviation de l'implémenteur) : le test "no-op en
mode manual" du brief (task-1-brief.md, repris verbatim) clique `clear-cf`
sans jamais peupler `crossFilter` au préalable — passe trivialement même
si le guard `if (!active) return` était retiré. Le guard réel EST bien
présent et correct (vérifié par lecture directe du code), seule la preuve
par ce test spécifique est faible ; le test jumeau `setTimeRange` (déjà
existant) prouve, lui, une vraie transition d'état bloquée. Laissé tel
quel (suit le texte du plan à la lettre, cf. précédent SP-14b Task 18/
revue finale : points signalés pour décision humaine sans bloquer
l'exécution) — à trancher par Tanguy en fin de plan si souhaité.

Base Task 2: b651175
Task 2: complete (commit 785814c, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). Nouvelle branche range
transcrite exactement (`analyticsPatch.ts:30-40`), ordre `Array.isArray`
avant `typeof === "object"` confirmé correct par le reviewer (un array est
aussi `typeof "object"` en JS), exclusion `originSourceId` inchangée et
s'applique uniformément aux 3 branches. Comportement scalaire/array
byte-identique au code précédent (seul reformatage bloc if/else if/else).
12/12 tests (10 préexistants + 2 nouveaux).

Base Task 3: 785814c
Task 3: complete (commit fb1a79b, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). Widget `selectFilter`
créé (checkbox multi-valeurs, requête `groupBy` statistics via
`itemClient.queryDataSource`), `toggle()` accumule/retire de l'array et
appelle `clearCrossFilter` (jamais `setCrossFilter([])`) quand vide.
`originSourceId` vérifié = `props.dataSourceId` (jamais `ctx.widgetId`),
tous les éléments interactifs avec `aria-label`. Wiring `index.tsx` (2
lignes). 4/4 nouveaux tests, suite complète 94 fichiers/667 tests (0
régression).

Base Task 4: fb1a79b
Task 4: complete (commit 1ef6de5, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). Widget `sliderFilter`
créé (double poignée, requête statistics `measures:[min,max]`), clamp
croisé correct (`Math.min`/`Math.max`), clear exact aux bornes complètes.
Déviation de test vérifiée indépendamment par le reviewer : brief demandait
`setAttribute`+`dispatchEvent` sur l'input contrôlé (aurait probablement
échoué — value IDL property désynchronisée de l'attribut une fois React
monté), implémenteur a utilisé `fireEvent.change` à la place (mécanisme
standard RTL, mêmes assertions/comportement couverts, cohérent avec le
reste du dépôt qui n'utilise jamais setAttribute+dispatchEvent sur un
contrôlé). 4/4 nouveaux tests, suite complète 94 fichiers/671 tests (0
régression).

Base Task 5: 1ef6de5
Task 5: complete (commit 5833a33, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). `AnalyticsContextIndicator`
transcription exacte (chips période/emprise/cross-filter, `clearAll()`
efface les 3, seuil `chipCount >= 2` pour "Tout effacer"). Wiring
`AppRenderer.tsx` : gating `mode !== "edit" && config.interactions ===
"auto"` posé juste avant `ActionConditionBridge`. Déviation de test
vérifiée indépendamment par le reviewer : le 1er test du brief ("renders
nothing when empty") montait `<Controls/>` (3 boutons) dans le même
render que l'indicateur — `container` ne pouvait jamais être vide, bug
réel du brief. Fix test-only (ce test seul rendu sans `<Controls/>`),
les 4 autres tests inchangés. Test de gating `AppRenderer` signalé
vacuous par construction (config minimale sans chip actif — le brief le
reconnaît lui-même, couverture réelle différée à l'E2E Task 6), pas
imputable à l'implémenteur. 6/6 nouveaux tests (5 indicateur + 1 gating),
suite complète 96 fichiers/677 tests (0 régression).

Base Task 6: 5833a33
Task 6: complete (commit 9a4dfb8, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). 4 scénarios E2E
ajoutés à `analytics-context.spec.ts` (append-only, 5 scénarios
préexistants + helpers intouchés, vérifié par le reviewer sur le hunk
diff). **Fix produit trouvé et corrigé (hors scope Task 6 mais requis
pour builder)** : `AnalyticsContextIndicator.tsx` (Task 5) annotait
`JSX.Element` en type de retour — invalide sous `jsx: "react-jsx"` de ce
dépôt (namespace `JSX` global absent), cassait silencieusement
`tsc --noEmit`/`npm run build`, donc tout `npm run e2e` (webServer en
dépend), pas seulement ce fichier. Retrait de l'annotation (effacée à la
compilation, aucun changement de comportement runtime) — conforme à la
convention du dépôt (aucun autre composant à retour conditionnel `null`
n'annote `JSX.Element`, vérifié par grep global par le reviewer). 3
autres déviations de test vérifiées indépendamment par le reviewer (pas
seulement le rapport) : scénario 9 nécessitait un `.uncheck()` explicite
(nouvelles apps = `interactions:"auto"` par défaut, `itemClient.ts:291`,
déjà documenté par le commentaire du scénario 5 préexistant) ; scénario 9
`.check()`→`.click()`+`not.toBeChecked()` car la checkbox `selectFilter`
n'a aucun état local (pur reflet du contexte partagé, no-op en mode
manual par design, pas un bug) ; scénario 7 slider utilise le trick
native-setter+event `"input"` (React câble `onChange` d'un `<input
type=range>` sur l'event natif `input`, pas `change`, et une assignation
directe `.value=` contourne le tracker de valeur de React) au lieu du
`el.value=`+`dispatchEvent("change")` littéral du brief. Suite E2E
complète 60/60 (18+ specs préexistantes + 9 dans ce fichier), suite
unitaire 96 fichiers/677 tests, build clean — tout re-vérifié par le
reviewer contre le code réel, pas seulement le rapport.

## SP-14c COMPLET — 6 tâches, 0 fix de revue de tâche (les 6 clean au
## premier passage — 1 bug de build réel trouvé et corrigé en cours de
## route par l'implémenteur de Task 6, pas par une revue), tout clean.
## HEAD=9a4dfb8. Reste : revue finale de branche.

## Revue finale de branche (opus, 3874711..9a4dfb8) — 0 Critical, 2
## Important, corrigés. Les 6 contraintes globales tiennent sur le diff
## complet (aucun fichier core/, seul analytics-context.spec.ts touché
## côté E2E et en append-only, aria-label systématique, originSourceId
## identique dans les 2 nouveaux widgets, flux range bout-en-bout
## slider→context→derivePatch→indicateur→E2E confirmé cohérent).

2 Important (les deux dans sliderFilter.tsx, invisibles aux revues de
tâche individuelles — écart de cohérence croisée entre widgets jumeaux
et intégration avec l'indicateur, livrés dans des tâches différentes) :
(1) branche d'erreur morte — l'ordre de garde `isLoading || !query.data`
avant `isError` rendait la branche erreur inatteignable (échec réel →
"Chargement…" perpétuel), incohérent avec `selectFilter.tsx` qui a le
bon ordre ; (2) désynchronisation d'état local — le slider gardait
`from`/`to` en `useState` local, jamais reconnecté au contexte partagé :
effacer le filtre via le nouvel indicateur ("Effacer le filtre …"/"Tout
effacer", la fonctionnalité phare de ce plan) laissait les poignées du
slider figées sur l'ancienne position pendant que les autres widgets se
défiltraient correctement.

Fix (commit a80f35a) : ordre de garde corrigé (`isLoading` puis
`isError || !query.data`, miroir exact de `selectFilter.tsx`) ; `from`/
`to` dérivés à chaque rendu depuis `analyticsCtx.crossFilter[datasetId]`
(quand `field` correspond), repli sur les bornes min/max récupérées sinon
— `useState`/`useEffect` locaux entièrement supprimés, `commit()` continue
d'appeler uniquement `setCrossFilter`/`clearCrossFilter`, clamp croisé
inchangé. 2 nouveaux tests (rendu erreur réel, affichage réinitialisé
après clear externe via `useClearCrossFilter`). Re-revue (opus) sur les 7
commits : les 2 findings marqués **RESOLVED** indépendamment (lecture
directe du code, pas seulement le rapport), aucun nouveau problème
introduit, edge cases vérifiés (drag en vol impossible avant résolution
de la requête, datasetId/field manquants gardés en amont). Suite ciblée
6/6, suite complète 96 fichiers/679 tests, build clean.

## SP-14c COMPLET — 6 tâches + revue finale + 1 round de fix, tout
## vérifié indépendamment à chaque étape. HEAD=a80f35a. E2E complet
## re-vérifié 9/9 après le fix (finishing-a-development-branch). Poussé
## vers origin/dev, PR #52 dev→main ouverte (choix utilisateur : push +
## PR, pas merge local direct, cohérent avec la convention 1 PR par SP
## déjà en place — SP-14a=#50, SP-14b=#51).
