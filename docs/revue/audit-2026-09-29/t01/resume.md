# t01 — Accessibilité : résumé

## Périmètre couvert
- axe-core (règles par défaut, toutes sévérités relevées, assertions sur critical/serious) sur 28 routes du shell balayées en clair **et** en sombre (`colorScheme` émulé) : `/`, `/items/:pk`, `/bookmarks`, `/maps/:pk`, `/apps/:pk/edit`, `/datasets/:pk/edit`, `/pipelines/new`, `/datasets/visual-query/new`, `/reports`, `/reports/new`, `/analytics/sql`, les 7 pages `/admin/*`, `/internal/kit-gallery`, `/tasks`, `/settings`, `/apps/:pk`, `/sites/:slug`, `/public/items/:pk`, `/public/datasets/:id`, route inconnue. Personas : creator, admin, reader, analyst.
- Parcours clavier : ordre de tabulation et focus visible (catalogue), Drawer « Nouveau » (piège, Échap, restitution), palette ⌘K, cloche de notifications, menu du compte, menu « Actions » de carte, ConfirmDialog, éditeur d'app (sélection clavier, raccourci Suppr), éditeur SQL CodeMirror (piège Tab), tri de tableau au clavier.
- Labels, états de formulaire, `aria-expanded`/`aria-controls` sur panneaux (Collections, Moissonnage, Rôles), radiogroup des paramètres.
- Contrastes AA : ratio calculé depuis les jetons résolus (ink/ink-2/ink-3/warn sur toutes les surfaces, clair et sombre), contraste non textuel des bordures de champs, plus color-contrast d'axe sur pages réelles.
- 40 tests Playwright (`shell/e2e/journeys/t01/`, 4 specs + `helpers.ts`) : 17 passent (régression), 23 sont `test.fixme` avec l'id du finding. Les tests `bug()` sont rejouables pour preuve avec `T01_VERIFY=1` (ils échouent alors sur l'assertion visée). Dernière exécution complète avec `T01_VERIFY=1` : 17 passed, 23 failed (attendu).

## Périmètre NON couvert
- Pipelines (`/pipelines/:pk/edit`, canvas DAG) et Rapports (`/reports/:pk/edit`) : capacités ETL/export désactivées (POST /configs -> 403), seuls `/pipelines/new` et `/reports/new` ont été balayés.
- Admin tools / quotas / copilote LLM : capacités désactivées, panneaux non rendus (donc non auditables).
- Lecteur d'écran réel (NVDA/VoiceOver) : non exécuté ; les constats portent sur l'arbre DOM/ARIA et le comportement clavier.
- Cartes MapLibre : le worker est servi en octet-stream (j12-001), aucune couche vectorielle n'a été rendue ; l'interaction clavier sur les entités de carte, la légende et le mode croquis ne sont pas couverts.
- Zoom 200-400 % et espacement de texte forcé (WCAG 1.4.4/1.4.12) : non mesurés (réflow mobile traité par j12) ; `prefers-reduced-motion` déjà couvert par SP-C2.
- Constats a11y déjà signalés non repris : NotificationBell (j02-013, j09-006), Terrain (j03-014), cibles tactiles < 24 px (j12-005/006/007), BottomNav/onglets mobiles (j12-008/010), domaine verrouillé (j06-010) ; REV-176 (ink-3) et REV-088 (aria-expanded) référencés via `related_gap`.
- Un balayage de l'explorateur de données, des pages d'export d'app et du widget carte multi-couches (requiert des données rendues) n'a pas été fait.

## Méthode
1. Seed via l'API du cœur (persona creator) : dataset, carte, app deux colonnes, site publié, alerte, favori (`helpers.ts::getA11ySeed`, cache disque `aud-t01-seed.json`). Les items privés du creator sont « introuvables » pour l'admin : les routes d'édition sont donc balayées en creator (première passe admin invalidée puis refaite).
2. Balayage axe exploratoire clair/sombre -> agrégation des règles (landmarks, h1, region, contrastes) ; sondes clavier ad hoc (ordre de Tab, focus, Échap) ; lecture du code pour situer la cause (AppLayout, index.css, tokens.css, ItemActions, AppBuilderPage, CatalogSpatialFilter).
3. Chaque bug confirmé est figé en test `bug()` (fixme) ; les comportements sains sont figés en tests de régression qui passent.
4. Les règles `landmark-one-main`/`region`/`page-has-heading-one` sont relevées (t01-001/003) mais `region` n'est pas comptée séparément (conséquence de t01-001).

## Commandes lancées
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/t01` (régression : 17 passed, 23 skipped/fixme)
- `cd shell && T01_VERIFY=1 npx playwright test -c playwright.journeys.config.ts e2e/journeys/t01` (preuve des bugs)
- `cd shell && npx eslint e2e/journeys/t01 && npx prettier --check e2e/journeys/t01`
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/t01 --repo-root ..`

## Points positifs vérifiés (tests qui passent)
Focus visible sur tous les arrêts du catalogue ; Drawer/Dialog/Popover/menu du compte/palette : focus piégé, Échap, restitution ; ConfirmDialog : focus initial sur Annuler ; aucune violation critical/serious en clair sur 28 routes et en sombre sur les pages sobres ; radiogroup de notifications nommé ; tri de tableau au clavier ; `lang=fr`, navigation nommée.
