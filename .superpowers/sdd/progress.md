# SP-19 — Undo/redo général du builder — Progress Ledger

Plan: docs/superpowers/plans/2026-08-15-sp19-undo-redo-builder.md
Spec: docs/superpowers/specs/2026-08-05-undo-redo-builder-design.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).

## Note de reprise

Trouvé au démarrage : ledger de SP-18c (14/14 tâches, clos) — déjà
committé (294ab31 `docs(sp18c): session ledger...`), donc sûr à écraser
sans perte. Repartant de zéro pour SP-19.

Avant dispatch : committé la correction de spec (§3/§4, granularité
centralisée) + le fichier de plan, qui étaient présents non commités au
démarrage de session (commit 03c3ce1).

## Pre-flight plan review

4 tâches, code complet à chaque étape. Aucune contradiction interne.
Vérifié verbatim contre le fichier réel avant dispatch : les 5 snippets
de recherche/remplacement de Task 3 (import, déclarations useState
draft/selectedId, effet de seeding, ligne toolbar mode==="edit",
`ml-2 flex items-center gap-1`) matchent tous exactement
`shell/src/pages/AppBuilderPage.tsx` en l'état actuel. Plan exact,
aucun écart trouvé.

## Tâches
Task 1: complete (commit 82357a0, review clean — 0 Critical/Important/Minor).
`shell/src/builder/undoStack.ts` : `UndoStack<T>`/`UNDO_STACK_MAX_DEPTH`(50)/
`createUndoStack`/`pushUndo`/`applyUndo`/`applyRedo`, transcription verbatim
du brief, pur/framework-free confirmé (0 import React). 7 tests, TDD RED→GREEN
vérifié par le reviewer.
Task 2: complete (commit fa614ad, review clean — 0 Critical/Important/Minor).
`shell/src/builder/useUndoableDraft.ts` : hook wrappant undoStack.ts (Task 1)
avec coalescing 400ms (COALESCE_WINDOW_MS), flush synchrone dans undo()/redo(),
seedDraft (prev ?? value) sans pas d'historique. 8 tests (fake timers), setDraft
même signature que le useState remplacé. Transcription verbatim du brief.
Task 3: complete (commit ad67989, review clean — 0 Critical/Important, 1 Minor
FYI hors périmètre). `AppBuilderPage.tsx` bascule sur `useUndoableDraft` :
boutons "Annuler"/"Rétablir", raccourcis Ctrl+Z/Ctrl+Shift+Z globaux (gardés
tant que le focus est dans un champ texte), `seedDraft` pour l'effet de
seeding. **Déviation trouvée et corrigée par l'implémenteur, vérifiée
indépendamment par le reviewer** (lecture réelle de useUndoableDraft.ts +
re-run du fichier ciblé) : un des 5 tests du brief tel qu'écrit littéralement
était mathématiquement auto-contradictoire sous timers réels (ajout de widget
par clic immédiatement suivi de frappe → même rafale de coalescing 400ms que
Task 2 →  ses deux assertions ne peuvent jamais être vraies simultanément,
quelle que soit la synchronisation). Corrigé en réécrivant uniquement ce test
pour semer le widget (getAppConfig) au lieu de l'ajouter par clic, isolant la
rafale testée aux seules frappes visibleWhen — motif déjà utilisé par les
tests GridCanvas voisins du même fichier. `useUndoableDraft.ts` (Task 2) non
touché. Suppression de l'import `AppConfig` désormais inutilisé (conséquence
directe et nécessaire du swap useState→hook pour `tsc --noEmit`, pas du
scope creep). 18/18 tests fichier ciblé (stable sur 3 runs), suite complète
1208/1208, tsc clean. Minor FYI (garde clavier vs shadow DOM des widgets Web
Components SP-8) : présent verbatim dans le brief, non bloquant, hors
périmètre de cette tâche.
Task 4: complete (commit bf011ce, review clean — 0 issues). E2E ajouté à
`shell/e2e/app-builder.spec.ts` : créer app → ajouter widget Texte →
Ctrl+Z le retire (Annuler désactivé) → Ctrl+Shift+Z le restaure. 2/2 tests
passent en navigateur réel (649ms le nouveau). Transcription verbatim du
brief, aucun code applicatif touché.

**SP-19 fonctionnellement complet (4/4 tâches, 0 Critical/Important non
résolu sur les 4 revues de tâche).**

## Revue finale de branche

Diff `778429b..bf011ce` (5 commits, 4 tâches). **2 Critical + 1 Important + 1
Minor pris en compte** (invisibles à la revue par tâche — c'est exactement
la classe de bug que ce niveau de revue existe pour attraper) :

- **C1** : `undo()`/`redo()` mutaient `stackRef`/`pendingBaselineRef`/
  `timerRef` *à l'intérieur* de la fonction passée à `setDraftState(...)`.
  React double-invoque les updaters `useState` sous `<StrictMode>` (qui
  enveloppe toute l'app, `main.tsx`, actif en `npm run dev`, absent des
  builds de prod) — la double invocation corrompait/perdait l'historique.
  Reproduit par le reviewer : un seul edit puis Ctrl+Z ne faisait rien,
  mais `canUndo` passait quand même à `false` comme si l'undo avait
  réussi. **Invisible aux trois paliers de test** (tests unitaires jamais
  en StrictMode, E2E tourne contre un build de prod où le double-invoke
  DEV est compilé). Aucun test ni brief ne demandait StrictMode — un vrai
  angle mort structurel de la couverture existante, pas un oubli de
  tâche.
- **C2** : `activePageId` (state à part, hors pile undo) devenait
  orphelin après annulation de « Ajouter une page » → `setPageLayout`
  (`pages.ts`) no-ope silencieusement tout edit ultérieur sur un
  `pageId` inconnu → tout ajout de widget disparaissait silencieusement,
  "Enregistrer" sauvegardait sans erreur. Reproduit contre la vraie page.
  Invisible à Task 3 (qui n'exerçait que GridCanvas/visibleWhen, jamais
  pages × undo).
- **I1** : timer de coalescing jamais nettoyé au démontage.
- **M2** (même classe que C2, corrigé dans la même passe sur demande du
  reviewer) : `selectedId` non réconcilié après undo/redo.

**Fix** (commit a2de1a8) : `draftRef` synchrone remplace toute mutation de
ref à l'intérieur d'un updater — `setDraftState` n'est plus jamais appelé
avec une fonction (élimine le vecteur, pas seulement le rend pur). `activePage`
dérivé et validé contre `draft.pages` à chaque render (auto-guérison, pas de
useState/useEffect supplémentaire). Cleanup effect pour le timer. Effet de
réconciliation pour `selectedId`. 3 nouveaux tests (StrictMode double-step
undo/redo, composition synchrone de deux `setDraft` dans le même handler,
pages × undo × widget). RED→GREEN vérifié par stash/restore pour C1 et C2.

**Re-revue** (diff bf011ce..a2de1a8) : les deux Critical **structurellement**
corrigés (pas de patch de symptôme) — vérifié indépendamment par traçage du
code source React 19.2.7 lui-même (double-invoke bien recréé pour prouver
que le test StrictMode aurait échoué sur l'ancien code) et par grep de tous
les points de lecture de `activePageId` (aucune fuite résiduelle). 0
Critical/Important non résolu. 2 Minor résiduels notés (non bloquants,
changements de comportement mineurs induits par M2 : la sélection ne
survit plus à un undo→redo, ni à un changement de page — comportement
défendable mais non testé explicitement ; `activePageId` lui-même reste
non réconcilié, seule sa dérivation l'est). Suite ciblée 29/29, suite
complète 146 fichiers/1211 tests, tsc clean.

**E2E re-exécuté par le contrôleur avant clôture** (assurance bon marché
suggérée par le re-reviewer) : 2/2 passent (929ms + 644ms).

**SP-19 clos : 0 Critical/Important non résolu au merge.**
