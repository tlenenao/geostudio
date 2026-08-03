# SP-14i — SQL Lab (éditeur, exécution, historique local) — Progress Ledger

Plan: docs/superpowers/plans/2026-08-03-sp14i-sql-lab.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@93ccab1 (plan + spec SP-14i committés ; ledger SP-14h et
plans épars SP-14b/14i committés en amont par hygiène de dépôt).

Note : ce fichier remplace le ledger SP-14h (complet, revue finale
ready-to-merge, HEAD=eadbdd7) — même fichier scratch réutilisé par
convention du dépôt ; contenu SP-14h préservé dans l'historique git
(commit 8b06677).

## Pré-vol

Scan des 5 tâches (1: `itemClient.runAnalyticsSql`+`SqlQueryError` ;
2: `sqlLabHistory.ts` module pur localStorage ; 3: `SqlLabPage` — éditeur,
exécution, résultats, historique ; 4: route `/analytics/sql` + lien nav
gardé par `isAnalyst` ; 5: E2E exécution/erreur/garde-analyste) contre les
9 contraintes globales (zéro changement à `core/` — contrat backend
`POST /analytics/sql`/`GET /me.isAnalyst` déjà figé depuis SP-11c ; route
`/analytics/sql` + lien nav conditionné sur `isAnalyst === true`,
indépendant du bloc `isAdmin` ; éditeur = `<textarea>` brut, pas de
dépendance code-editor ; historique `localStorage` seul, clé fixe
`"geostudio.sqlLab.history"`, plafonné à 20, dégrade silencieusement ;
"Enregistrer comme dataset" explicitement hors périmètre ; UI en
français ; en-tête SPDX ; commits conventionnels suffixés (SP-14i) ; 76
E2E existants + suite unitaire complète restent verts) : pas de
contradiction. Le plan fournit du code complet et littéral pour chaque
tâche (types, implémentation, tests unitaires, E2E) — transcription +
tests, pas de conception à faire, comme SP-14e/14f/14g/14h. Dépendances
d'interface notées : Task 3 consomme `runAnalyticsSql`/`SqlQueryError`
(Task 1) et `readSqlHistory`/`appendSqlHistory`/`SqlHistoryEntry`
(Task 2) ; Task 4 consomme `SqlLabPage` (Task 3) ; Task 5 exerce l'UI
réelle produite par Tasks 1-4 (route, lien nav, textarea, bouton
Exécuter, table de résultats, historique). Tâches exécutées dans l'ordre
du plan (1→5), toutes séquentiellement dépendantes sauf 1/2 qui sont
mutuellement indépendantes mais exécutées en séquence par convention de
cette skill (jamais deux implémenteurs en parallèle).

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: 93ccab1
Task 1: complete (commit a7b6078, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). `SqlQueryError`
(itemClient.ts) + `requestAnalyticsSql` (mirrors `requestFeatureWrite`
pattern) + `ItemClient.runAnalyticsSql` (types.ts). Reviewer a vérifié la
forme d'erreur/succès directement contre le vrai contrat backend
(`core/app/features/routes.py` — 400 structured errors, 403 plain
string, 200 columns/rows/truncated), pas seulement contre le mock des
tests. 89/89 tests, `tsc --noEmit` propre. 1 Minor non bloquant : message
de repli 400 en français ("Requête SQL invalide.") alors que les autres
chaînes de repli du fichier sont en anglais — cosmétique, jamais atteint
en pratique (le backend fournit toujours un message sur 400).

Base Task 2: a7b6078
Task 2: complete (commit 55bbdfb, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). `sqlLabHistory.ts`
(module pur, zéro import) : `SqlHistoryEntry`, `readSqlHistory`/`appendSqlHistory`,
clé `"geostudio.sqlLab.history"`, plafond 20 entrées (plus ancienne
évincée), échec silencieux lecture ET écriture (try/catch scindé
correctement — ne masque rien d'autre). 4/4 tests contre un vrai
`localStorage` jsdom (pas de mock). 1 Minor non bloquant : cast
`as SqlHistoryEntry[]` après seul `Array.isArray`, sans validation de
forme par élément — conforme au brief, latent seulement si une future
migration de schéma laisse des données mal formées en stockage.

Base Task 3: 55bbdfb
Task 3: complete (commit 1e5bd05, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). `SqlLabPage.tsx` :
éditeur `<textarea>` brut (pas de CodeMirror/Monaco), garde `isAnalyst`,
`useMutation` sur `runAnalyticsSql`, table de résultats, notice de
troncature, historique cliquable (recharge sans exécuter). Aucune
réimplémentation des interfaces Task 1/Task 2 — consommées telles
quelles, vérifié par le reviewer contre le code source réel de
`useMe`/`useItemClient`/`Button`. Ordre des hooks correct (tous appelés
avant les deux early-return). "Enregistrer comme dataset" absent (hors
périmètre respecté). 5/5 tests (Testing Library + MSW, vrai rendu), 106
fichiers/805 tests suite complète, `tsc --noEmit` propre. 2 Minor non
bloquants : cast `as Error` redondant (TanStack Query type déjà `Error`
par défaut) ; état `isLoading`/`Chargement…` non exercé par un test
(hors périmètre du brief, pas un gap).

Base Task 4: 1e5bd05
Task 4: complete (commit 51a7f43, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). Route
`/analytics/sql` (routes.tsx, dans `<ProtectedLayout>`, aucune collision
— pas de route catch-all dans le fichier) + lien nav "SQL Lab"
(AppLayout.tsx) en frère (pas imbriqué) du bloc `isAdmin`, confirmé
inchangé octet pour octet par le reviewer. Styling identique au premier
lien du bloc admin. 807/807 suite complète, build propre. 2 Minor non
bloquants (déjà notés par le plan lui-même, pas des déviations de
l'implémenteur) : le test "cache le lien pour un non-analyste" ne
surcharge pas `/me`, s'appuie sur le mock partagé qui omet `isAnalyst`
(passerait même si le bloc conditionnel était supprimé — le brief
l'annonçait déjà "passes trivially") ; `Me.isAnalyst` est un champ requis
dans `types.ts` mais absent du mock MSW par défaut (dérive pré-existante,
hors diff de cette tâche).

Base Task 5: 51a7f43
Task 5: complete (commit f7f7b6d, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). 3 scénarios
E2E ajoutés (`shell/e2e/sql-lab.spec.ts`, fichier neuf, zéro changement
de code applicatif) : exécution + rechargement depuis l'historique ;
message d'erreur serveur + texte préservé dans l'éditeur ; non-analyste
refusé + lien absent + aucun appel SQL. Reviewer a vérifié chaque
assertion contre le vrai code (`SqlLabPage.tsx`, `AppLayout.tsx`,
`itemClient.ts`), pas seulement le rapport. Route mockée host-scoped
(`https://core.test/analytics/sql`), pas path-only — rationale vérifiée
correcte (la route client `/analytics/sql` de l'app collisionnerait avec
un glob path-only, même précédent que `admin-extensions.spec.ts`).
Sélecteurs uniformément role/label, `expect.poll` pour l'observation
async, pas de sleep arbitraire. Spec seule 3/3, suite E2E complète
79/79 (deux fois), suite unitaire 807/807, `tsc --noEmit` propre. 1
Minor non bloquant : `.count()` manuel au lieu de `toHaveCount()`
auto-retry (ligne 89, cosmétique).

## SP-14i COMPLET — 5 tâches, 5 commits de tâches (a7b6078, 55bbdfb,
## 1e5bd05, 51a7f43, f7f7b6d), 0 round de fix (les 5 tâches approuvées
## au premier passage). HEAD=f7f7b6d, prêt pour la revue finale de
## branche. Minors cumulés à trianger par la revue finale (aucun
## bloquant à ce stade) : message de repli 400 en français isolé
## (Task 1) ; cast as SqlHistoryEntry[] sans validation par élément
## (Task 2) ; cast as Error redondant + Chargement… non testé (Task 3) ;
## test négatif "cache le lien" plan-mandated faible + Me.isAnalyst
## requis mais absent du mock MSW par défaut, pré-existant (Task 4) ;
## .count() manuel vs toHaveCount() (Task 5).

## Revue finale de branche (opus, 93ccab1..f7f7b6d, 5 commits) —
## 1 Important, 0 Critical, plusieurs Minor confirmés non bloquants
## à l'échelle de la branche (cf. liste ci-dessus, tous re-confirmés
## comme non bloquants par ce reviewer indépendant), "With fixes".
## Important : en-tête SPDX manquant sur `shell/e2e/sql-lab.spec.ts`
## (Task 5) — violation vérifiable de la contrainte globale du plan
## ("Every new file starts with SPDX..."), aucun autre nouveau fichier
## de la branche n'a cette lacune. Intégration cross-tâche vérifiée
## saine (SqlLabPage consomme runAnalyticsSql/SqlQueryError et
## sqlLabHistory sans écart d'interface ; route/nav Task 4 cohérente
## avec ce qu'exerce l'E2E Task 5). Aucune surface XSS/injection
## introduite (rendu React échappé, SQL envoyé en corps JSON, sandbox
## backend non touché). Dispatch d'un fixer unique pour le seul
## Important.

## Fix (commit 27428d4) : en-tête SPDX ajouté en première ligne de
## `sql-lab.spec.ts`, rien d'autre touché (2 insertions, 0 suppression).
## 3/3 E2E ciblé re-vérifié par l'implémenteur.

## Re-vérification finale (opus, commit 27428d4 isolé) : fix confirmé
## correct et isolé (diff --stat : 1 fichier, 2 insertions ; header en
## ligne 1 ; aucune logique de test modifiée). Aucun nouveau problème
## introduit. READY TO MERGE (Yes).
## SP-14i READY TO MERGE — prêt pour finishing-a-development-branch.
## HEAD=27428d4.




