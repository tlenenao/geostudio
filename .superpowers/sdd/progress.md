# SP-14m — Bookmarks (vues analytiques enregistrées) — Progress Ledger

Plan: docs/superpowers/plans/2026-08-05-sp14m-bookmarks.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@1e95253 (HEAD au lancement de cette sous-partie).

Note : ce fichier remplace le ledger SP-14l (complet, READY TO MERGE, HEAD=f8bc295) —
même fichier scratch réutilisé par convention du dépôt ; contenu SP-14l préservé
dans l'historique git (commit f8bc295 et son ledger).

## Pré-vol

Scan des 7 tâches (1: schéma Pydantic `BookmarkPayload` ; 2: validation directe
+ câblage REST `POST /configs` / `PUT /configs/by-item/{id}` ; 3: outil MCP
`create_bookmark` ; 4: shell — types/itemClient/hooks ; 5: `/bookmarks` via
réutilisation `CatalogPage` + navigation d'ouverture consciente des bookmarks ;
6: bouton "Enregistrer la vue" sur `AppRuntimePage` ; 7: E2E sauvegarde/liste/
réouverture) contre les Contraintes Globales (pas de migration Alembic — colonnes
`String` déjà libres ; additif seul, aucune config `kind="bookmark"` dans les
fixtures actuelles ; docs FR / code EN ; commits conventionnels ; TDD systématique ;
hors périmètre : cross-filter cross-dataset, query builder visuel, flux d'édition
de bookmark, snapshot de données, outil MCP `list_bookmarks` dédié, validation
pageId/fraîcheur du contexte) :

Aucune contradiction trouvée. Code littéral complet fourni pour chaque tâche
(imports, helpers, corps de composants, tests) — transcription + intégration,
même style que SP-14l. Task 5's `useOpenItem` factorise un ternaire existant en
un seul point (pas une duplication — extraction, le plan le note explicitement
comme "byte-identical" au comportement non-bookmark préexistant). Aucun test
n'asserte rien de vide. Dépendances d'interface : Task 2 consomme Task 1 ;
Task 3 consomme Task 1+2 ; Task 4 consomme rien (nouveau) mais Task 5/6 en
dépendent ; Task 5 consomme Task 4 ; Task 6 consomme Task 4 ; Task 7 (E2E)
consomme Tasks 4-6 bout en bout.

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: 1e95253
Task 1: complete (commit a461604, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 3 Minor négligeables —
fidélité du rapport de l'implémenteur, pas du code : message de commit et
comptes de lignes inexacts dans le rapport, vérifiés indépendamment par le
reviewer contre `git log`/le diff réel). `BookmarkPayload`/`BookmarkTimeRange`/
`BookmarkCrossFilterEntry` ajoutés, `BuilderConfig.kind` étend le literal,
`_require_kind_payload` étendu — mirror fidèle du pattern `DatasetPayload`
existant. 6/6 tests nouveaux, 867 passed + 112 skipped en suite complète
(0 régression).

Base Task 2: a461604
Task 2: complete (commit c346c2d, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor — couverture
"dashboard" du tuple accepté non testée par le texte littéral du plan, et une
petite optimisation possible get_access_facts+get_item→get_item seul, ni l'un
ni l'autre bloquant). `bookmark_validation.py` créé, mirror volontaire du
style `dataset_validation.py` (même message 422 "app not found" pour
inexistant/illisible/mauvais type, pas de leak d'existence) — câblé
uniquement dans `create_config`/`update_config_by_item`, `update_config`
(par config-id) explicitement hors périmètre et vérifié absent par le
reviewer via lecture directe de routes.py. 5/5 tests nouveaux, 872 passed +
112 skipped en suite complète (0 régression), lint-imports vert.

Base Task 3: c346c2d
Task 3: complete (commit 5edaa5b, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor négligeables —
assertion faible pageId vide plan-mandated, croissance continue de
tools.py suivant le précédent établi). `create_bookmark` MCP : mirror fidèle
de `create_dataset` (gate `is_read_only_mode()` avant toute session, acteur
via `_resolve_actor`, `_validate_bookmark` délègue à `validate_bookmark_payload`
(Task 2) inchangé plutôt que de le réimplémenter — vérifié par lecture directe
par le reviewer —, deux `write_audit` agent, refus avant création d'item
orphelin). `READ_ONLY_TOOLS` étendu à 6 entrées. 13/13 tests (5 nouveaux +
8 read-only mode), 878 passed + 112 skipped en suite complète (0 régression).

Base Task 4: 5edaa5b (bascule core→shell)
Task 4: complete (commits 4677132 puis e1cc4d6, 1 round de fix). Review round 1
: ❌ Important trouvé — `BookmarkPayload.crossFilter` (`Record<string,
BookmarkCrossFilterEntry>`) ne correspondait pas à `AnalyticsContextState.
crossFilter` (`Record<string, CrossFilterEntry | undefined>`), le `| undefined`
manquant violant l'exigence explicite du brief ("byte-for-byte mirror... so no
client-side translation is ever needed"). Vérifié indépendamment par le
contrôleur en lisant les deux fichiers avant de dispatcher le fix — traité
comme une coquille du texte du plan (comme le comptage d'outils SP-14l), pas
un choix de design mandaté à faire trancher par l'humain, car corriger va
dans le sens de l'intention explicite du plan, pas contre elle. Fix : type
élargi + commentaire d'écho documenté ajouté (convention `WcWidgetManifest`).
Re-review round 2 : ✅ spec compliant, task quality Approved, 0 finding —
correction vérifiée caractère pour caractère contre `AnalyticsContext.tsx`
directement dans le diff. 4/4 tests nouveaux (121/121 focus, 844/844 suite
complète, build/tsc propre), 0 régression.

Base Task 5: e1cc4d6
Task 5: complete (commits 04dc6a4 puis 29929aa, 1 round de fix). Review round 1
: ❌ Important trouvé — `useOpenItem()` branche bookmark faisait `await
client.getBookmarkConfig(pk)` sans try/catch, et le seul appelant (`ItemCard`)
n'attend ni ne catch la promesse retournée → rejet non géré, "Ouvrir" ne
faisait silencieusement rien en cas d'échec (config supprimée, réseau). Jugé
comme une lacune que le plan a laissée ouverte, pas un choix de design
mandaté — fix dispatché sans arbitrage humain. Fix : try/catch ajouté,
convention `role="alert"` existante réutilisée (repérée dans
`HarvestSourcesAdminPage.tsx`, pas inventée), `useOpenItem()` retourne
maintenant `{ onOpenItem, openError }` — absorbé avant `CatalogPage` donc son
contrat externe `(pk, type) => void` reste inchangé (vérifié par le reviewer).
Re-review round 2 : ✅ spec compliant, task quality Approved, 0 finding
bloquant, 2 Minor (reset d'`openError` asymétrique sur la branche non-bookmark,
warning setState-on-unmount possible si navigation pendant le fetch — ni l'un
ni l'autre bloquant). Extraction `useOpenItem()` branche non-bookmark
confirmée byte-identique (test préexistant "app builder on open" intact,
vérifié absent de tout hunk du diff). 5 tests nouveaux (14/14 focus, 848/848
suite complète), build/tsc propre.

Base Task 6: 29929aa
Task 6: complete (commit 1e4c507, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 3 Minor négligeables —
chemin d'échec `isError` non testé directement, `createBookmark.reset()`
mort sur le chemin succès, style de commit déjà établi dans la série). Bouton
"Enregistrer la vue" affiché seulement si `interactions === "auto"`, dialog
+ `useCreateBookmark().mutateAsync` avec `title`/`owner`/`appId`/`pageId` +
contexte analytique courant étalé. Deux risques nommés vérifiés
indépendamment par le reviewer : `createBookmark.isError` bien positionné par
react-query indépendamment du `catch {}` vide du composant (le catch évite
juste un warning unhandled-rejection) ; `handleAnalyticsContextChange`
original inchangé, appelé tel quel depuis le nouveau wrapper (pas
d'interférence avec le debounce d'écriture URL). 3 tests nouveaux, 851/851
suite complète, build/tsc propre.

Base Task 7: 1e4c507
Task 7: complete (commit 57e54e4, review clean au premier passage — ✅ spec
compliant, task quality Approved, 0 finding bloquant, 2 Minor héritées du
texte littéral du brief, pas introduites par l'implémenteur — titre du test 1
mentionnant "cross-filter" alors que seul le time-range est exercé (aucune
assertion sur `crossFilter` dans le body posté), et un override `**/items*`
redondant dans le test 2 avec le comportement déjà par défaut de `mocks.ts`
pour `scope=mine`. Trois écarts du texte littéral du plan trouvés et vérifiés
indépendamment par le reviewer contre le code applicatif réel (pas des
lacunes masquées) : pas de bouton "Ajouter un widget" (les boutons de palette
sont directement cliquables, confirmé dans `WidgetPalette.tsx` + grep vide +
`analytics-context.spec.ts` existant qui fait pareil) ; ajout d'un widget
Table nécessaire aux assertions sur les cellules du brief lui-même (le widget
Plage de dates ne rend aucune cellule) ; clic "Enregistrer" scopé au dialog
(`role="dialog"` + `aria-label={title}` confirmé dans `dialog.tsx`) pour lever
une ambiguïté de mode strict réelle entre le bouton déclencheur et le bouton
de soumission. 2/2 tests E2E nouveaux (stables sur 3 exécutions), 85/85 suite
E2E complète, 851/851 suite unitaire, build propre.

## SP-14m COMPLET — 7 tâches, 10 commits de tâches (a461604, c346c2d, 5edaa5b,
## 4677132, e1cc4d6[fix], 04dc6a4, 29929aa[fix], 1e4c507, 57e54e4 — 9 listés,
## 2 rounds de fix sur 7 tâches (Task 4 : type crossFilter désaligné de
## AnalyticsContextState ; Task 5 : rejet de promesse non géré à l'ouverture
## d'un bookmark cassé). Les deux fix ont été dispatchés sans arbitrage
## humain — dans les deux cas la lacune trouvée n'était pas un choix de
## design mandaté par le texte du plan, corriger allait dans le sens de
## l'intention explicite du plan (mirror byte-for-byte ; pas de UX
## silencieusement cassée), pas contre elle. Minors non bloquants à
## transmettre à la revue finale de branche : Task 2 (dashboard non testé,
## double requête access+item), Task 3 (assertion faible pageId vide,
## croissance de tools.py), Task 5 (reset openError asymétrique, warning
## setState-on-unmount potentiel), Task 6 (chemin d'échec isError non testé
## directement, reset() mort), Task 7 (titre de test trompeur sur
## "cross-filter" non exercé, override redondant dans mocks.ts). HEAD=57e54e4,
## prêt pour la revue finale de branche.

## Revue finale de branche round 1 (opus, 1e95253..57e54e4, 9 commits) — 2
## Important trouvés et vérifiés indépendamment par le contrôleur avant tout
## fix (pas de confiance aveugle dans le rapport du reviewer) :
## 1. `BookmarkCrossFilterEntry.value` (str | list[str]) rejetait la forme
##    `{from, to}` réellement produite par le widget curseur natif
##    (`sliderFilter.tsx:71`) — un bookmark avec cross-filter de plage actif
##    échouait en 422 à l'enregistrement. Confirmé en lisant `sliderFilter.tsx`
##    et `AnalyticsContext.tsx` directement.
## 2. Asymétrie de validation : `PUT /configs/{config_id}` (par config-id)
##    validait les datasets mais pas les bookmarks, contrairement aux deux
##    autres endpoints d'écriture bookmark — confirmé en lisant `routes.py`
##    directement (dataset_validation présente, bookmark absente).
## Ni l'un ni l'autre n'était un choix de design mandaté par le plan (aucune
## clause ne justifie ces lacunes) — fixes dispatchés en parallèle sans
## arbitrage humain : 7b3baae (forme range du crossFilter, réutilise
## `BookmarkTimeRange` existant plutôt qu'un nouveau type) + fe183cf
## (validation ajoutée sur `update_config`), côté core ; c1b4e46 côté E2E pour
## exercer réellement un cross-filter curseur (deux sources sur la même
## collection, `derivePatch()` n'appliquant un cross-filter qu'aux sources
## différentes de `originSourceId`) et prouver la restauration après
## réouverture. 880/880 core (+2 tests), 851/851 shell unitaire, 85/85 E2E
## (1 flake transitoire pré-existant sur `publication.spec.ts`, non lié,
## confirmé disparu sur re-run complet indépendant du contrôleur), build
## propre.

## Revue finale de branche round 2 (opus, 1e95253..c1b4e46, 12 commits) —
## les deux fixes vérifiés directement dans le diff (ordre de déclaration
## BookmarkTimeRange avant BookmarkCrossFilterEntry correct, pas de
## sur-validation introduite sur update_config — early-return préservé pour
## les kinds non-bookmark, pas d'ambiguïté d'union Pydantic), aucune
## régression introduite, 0 Critical, 0 Important. Minors reportés confirmés
## non bloquants par le reviewer (branche "dashboard" non testée, asymétrie
## openError, reset() mort, croissance tools.py).

## **SP-14m READY TO MERGE** — HEAD=c1b4e46, 12 commits, 2 rounds de fix sur
## 7 tâches + 1 round de fix sur la revue finale de branche (2 findings),
## prêt pour finishing-a-development-branch.
