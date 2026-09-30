# j04 — Créateur d'app / dashboard

## Couvert
- Builder d'app (persona `audit-creator`, OIDC réel) : ajout/édition/suppression de widget, undo/redo (boutons, clavier, coalescing), garde de brouillon (navigation interne, après enregistrement, beforeunload), condition d'affichage CEL invalide, pages (ajout/renommage/ordre/suppression), variables typées, câblage d'actions (Filtre -> variable, Filtre -> Table), visibleWhen (runtime et Édition/Aperçu), message d'action et son aller-retour cœur, historique/restauration, déplacement (bornes, superposition), raccourcis clavier.
- Runtime : Table sur collection, source cassée, source orphelin, filtre inter-widgets, état vide, page inconnue, fuite de données (app partagée / collection privée), carte multi-couches, formulaire (schéma de collection, champ requis, soumission).
- Droits : lecteur viewer (builder verrouillé, PUT refusé), lecteur sans partage, analyste.
- API : validation sémantique du cœur, concurrence d'édition.
- 40 tests max dans `shell/e2e/journeys/j04/` ; 12 tests `fixme` (un par finding vérifié, rejouables avec `J04_VERIFY=1`), les autres passent (régression).

## Non couvert
- Import de fichier (cassé, j03-001/002) : jeux de données créés par API + INSERT SQL.
- Écriture de features via formulaire jusqu'au succès (bloquée côté cœur, cf. j02-003) ; widgets chart/pivot/indicator/gallery/hero/modal/drawer/tabs/navigation, cross-filter inter-datasets, interactions auto, story onEnter/flyTo, export d'app, copilote (flag), miniature, responsive breakpoints : non testés faute de budget de tests (40) ou de flag.
- Pas de test de charge (grosse config) ni d'a11y automatisée.

## Méthode
Lecture de AppBuilderPage, AppRenderer, PageManager, VariablesPanel, ActionsPanel, GridCanvas, schémas cœur `configs`, puis specs Playwright sur stack réelle ; chaque bug cité est rejoué (`J04_VERIFY=1`) avant classement `verified`. Le numéro j04-007 n'est pas utilisé (hypothèse invalidée par exécution : retirer une source délie bien le widget).

## Commandes
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j04` (1 worker)
- `J04_VERIFY=1 ...` pour exécuter les tests `fixme`.
- Validateur : `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j04 --repo-root ..`
