# SP-14j — Conteneurs (onglets, modale, tiroir) — Progress Ledger

Plan: docs/superpowers/plans/2026-08-03-sp14j-conteneurs.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@6886015 (plan + spec SP-14j committés).

Note : ce fichier remplace le ledger SP-14i (complet, READY TO MERGE,
HEAD=27428d4) — même fichier scratch réutilisé par convention du dépôt ;
contenu SP-14i préservé dans l'historique git.

## Pré-vol

Scan des 8 tâches (1: `WidgetContext.breakpoint` threading ; 2: `WidgetPalette`
`exclude` filter ; 3: `Dialog` `wide` variant ; 4: `LayoutEditor` — éditeur
nested réutilisable ; 5: widget `tabs` ; 6: widget `modal` ; 7: widget
`drawer` ; 8: E2E `containers.spec.ts`) contre les 7 contraintes globales
(additive only, aucun changement à AppConfig/AppBuilderPage.tsx/core/ ou aux
19 widgets existants ; un seul niveau de nesting — tabs/modal/drawer exclus
de la palette d'un LayoutEditor ; modal/drawer s'ouvrent uniquement via
ActionBus open/close déjà existant, câblé par ActionsPanel — aucun nouveau
mécanisme de déclenchement ; en-tête SPDX sur tout nouveau fichier ; UI en
français ; commits conventionnels suffixés (SP-14j) ; 76+ E2E + suite
unitaire complète restent verts) : une lacune trouvée — le bloc de code
fourni pour `shell/e2e/containers.spec.ts` (Task 8) ne contient pas
d'en-tête SPDX, alors que la contrainte globale l'exige pour tout nouveau
fichier. Même lacune que SP-14i (`sql-lab.spec.ts`), corrigée alors en fin
de revue de branche (round-trip de fix). Pas une contradiction de fond
(rien n'exempte les specs E2E) — décision prise sans interrompre
l'exécution : le dispatch de Task 8 inclura explicitement l'ajout de
l'en-tête SPDX en première ligne pour éviter de reproduire ce round-trip.

Le plan fournit du code complet et littéral pour chaque tâche (types,
implémentation, tests unitaires, E2E) — transcription + tests, pas de
conception à faire, comme SP-14e→14i. Dépendances d'interface notées :
Task 4 (LayoutEditor) consomme WidgetPalette.exclude (Task 2) ; Tasks 5-7
consomment LayoutEditor (Task 4), Dialog.wide (Task 3, Task 6 seulement) et
WidgetContext.breakpoint (Task 1) ; Task 8 exerce l'UI réelle produite par
Tasks 1-7. Tâches 1-3 mutuellement indépendantes mais exécutées en séquence
par convention de cette skill (jamais deux implémenteurs en parallèle).
Ordre du plan (1→8) respecté.

Poursuite sans confirmation utilisateur (scan de contradictions clean à
l'exception de la lacune SPDX ci-dessus, résolue sans ambiguïté).

## Tasks

Base Task 1: 6886015
Task 1: complete (commit 3b9558b, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). `WidgetContext.breakpoint`
(registry.ts) + prop `WidgetHost` + forward `bp` depuis `AppRenderer`.
Aucun widget existant ne consomme encore le champ (attendu, réservé aux
Tasks 5-7). 12/12 + 28/28 tests, `tsc --noEmit` propre.

Base Task 2: 3b9558b
Task 2: complete (commit 0f094a7, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). `WidgetPalette` gagne
`exclude?: string[]` (défaut `[]`), filtre `listWidgets()` par `type`.
2/2 tests.

Base Task 3: 0f094a7
Task 3: complete (commit a297b76, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). `Dialog` gagne
`wide?: boolean` (défaut `false`, `max-w-md`→`max-w-2xl`). Comportement
Escape/backdrop/role inchangé. 4/4 tests.

Base Task 4: a297b76
Task 4: complete (commit 7041603, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). `LayoutEditor.tsx`
(nouveau) compose WidgetPalette(exclude=NESTED_EXCLUDE)+GridCanvas+
WidgetHost+PropsPanel, byte-for-byte conforme au brief. Écart mineur
justifié et vérifié indépendamment par le reviewer : le fichier de test
du brief manquait `AuthProvider` mock + wrapper `ItemClientProvider`/
`QueryClientProvider` (nécessaires dès qu'un item réel "text" est rendu) —
ajoutés en copiant mot pour mot les patterns déjà établis dans
`WidgetHost.test.tsx`/`PropsPanel.test.tsx`, aucun changement à
`LayoutEditor.tsx` lui-même. 4/4 tests fichier, 816/816 suite complète,
`tsc --noEmit` propre, build OK.

Base Task 5: 7041603
Task 5: complete (commit 78b1229, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). Widget `tabs`
(`widgets/tabs.tsx`) : `props.tabs: {id,label,items}[]`, PropsPanel
ajout/renommage/réordonnancement/suppression (dernier onglet protégé),
LayoutEditor par onglet actif ; runtime clic-pour-switcher, édition
statique. 2 écarts au code littéral du brief, vérifiés indépendamment par
le reviewer et jugés justifiés : (1) scaffolding de test identique à
LayoutEditor.test.tsx (AuthProvider mock + wrapper ItemClientProvider/
QueryClientProvider, chemins d'import adaptés) ; (2) `breakpoint=
{ctx.breakpoint}` ajouté au WidgetHost imbriqué (le brief ne le passait
qu'au GridCanvas englobant) — corrige un bug latent, cohérent avec le
pattern AppRenderer.tsx:198, jugé correct à garder sans test dédié. 6/6
tests fichier, 822/822 suite complète.

Base Task 6: 78b1229
Task 6: complete (commit 15f921f, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). Widget `modal`
(`widgets/modal.tsx`) : `props {title,items,wide?}`, `actions:
["open","close"]` via `useBusAction`/ActionBus, contenu dans `Dialog`
(wide de Task 3), édition statique en mode edit. 2 écarts justifiés et
vérifiés indépendamment : (1) même fix `breakpoint={ctx.breakpoint}` que
Task 5 sur le WidgetHost imbriqué ; (2) test "closes on the close action
too" du brief était flaky (assertion synchrone après bus.emit sans
attendre le flush React) — corrigé avec `await waitFor(...)`, précédent
identique vérifié dans `form.test.tsx`. 5/5 tests fichier, 827/827 suite
complète.

Base Task 7: 15f921f
Task 7: complete (commit 2889853, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). Widget `drawer`
(`widgets/drawer.tsx`) : `props {title,items,side}`, `actions:
["open","close"]`, chrome slide-over écrit inline (pas de réutilisation
de `Dialog`, choix documenté par le plan), Escape+clic-backdrop+
role="dialog"/aria-label vérifiés identiques à `Dialog`. Même fix
`breakpoint={ctx.breakpoint}` que Tasks 5/6, vérifié cohérent. 4/4 tests
fichier, 831/831 suite complète, `tsc --noEmit` propre. Les 3 widgets
conteneurs (tabs/modal/drawer) sont maintenant tous livrés.

Base Task 8: 2889853
Task 8: complete (commit 700084e, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding). E2E
`shell/e2e/containers.spec.ts` (nouveau, 3 scénarios) : onglets bascule le
contenu visible ; bouton ouvre une modale via ActionBus + Escape ferme ;
bouton ouvre un tiroir via ActionBus + Escape ferme. En-tête SPDX ajouté
en ligne 1 par instruction explicite du dispatch (lacune connue du plan,
identique à SP-14i, corrigée avant plutôt qu'après revue cette fois — pas
de round-trip). Zéro écart au code littéral du brief hors le header,
confirmé par diff direct par le reviewer. 3/3 spec ciblée, 82/82 suite
E2E complète (79 préexistants + 3 nouveaux), 831/831 suite unitaire,
build propre.

## SP-14j COMPLET — 8 tâches, 8 commits de tâches (3b9558b, 0f094a7,
## a297b76, 7041603, 78b1229, 15f921f, 2889853, 700084e), 0 round de fix
## (les 8 tâches approuvées au premier passage). HEAD=700084e, prêt pour
## la revue finale de branche. Aucun Minor non résolu à trianger (chaque
## tâche est ressortie "0 finding" du reviewer, y compris après
## vérification indépendante des écarts au brief signalés par les
## implémenteurs : scaffolding de test AuthProvider/ItemClientProvider
## (Tasks 4/5/6), propagation `breakpoint` au WidgetHost imbriqué (Tasks
## 5/6/7), fix `waitFor` sur un test flaky du brief (Task 6), en-tête
## SPDX ajouté par instruction explicite (Task 8).

## Revue finale de branche (opus, 6886015..700084e, 8 commits) — 0
## finding, READY TO MERGE. Vérifié indépendamment (pas seulement sur la
## foi du ledger) : chaînage `breakpoint` bout en bout cohérent dans les
## 3 conteneurs (tabs.tsx:138, modal.tsx:73, drawer.tsx:89) ; contrainte
## de nesting à un seul niveau structurellement étanche (NESTED_EXCLUDE
## est le seul chemin qui peuple items[], aucun clone/duplicate ne peut
## l'contourner) ; modal/drawer n'exposent que ["open","close"], aucun
## déclencheur alternatif ; aucune surface XSS (pas de
## dangerouslySetInnerHTML, labels/titres rendus en children React
## échappés) ; écarts cumulés (scaffolding de test, propagation
## breakpoint, fix waitFor, header SPDX) jugés sans effet composé
## préoccupant ; duplication tabs/modal/drawer et non-réutilisation de
## Dialog par drawer confirmées être des choix déjà documentés par le
## plan, pas des lacunes. 2 observations non bloquantes notées (édition
## imbriquée toujours en breakpoint="lg", cellule modal/drawer occupe une
## zone vide en fermé) — pas d'action requise.
## SP-14j READY TO MERGE — prêt pour finishing-a-development-branch.
## HEAD=700084e.

## Gate final (build + 831 tests unitaires + E2E) re-exécuté directement
## avant push : build propre, 831/831 unitaires, E2E complète 82/82 au
## second passage (1 échec flaky isolé sur `publication.spec.ts` au
## premier passage — hors diff SP-14j, capture de miniature, reproduit
## comme faux positif : passe seul et repasse propre au second run
## complet). Poussé sur `origin/dev` (décision utilisateur) : c845e66..
## 700084e. SP-14j TERMINÉ ET POUSSÉ.
