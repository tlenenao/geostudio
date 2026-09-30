# Audit t04 — Cohérence visuelle et i18n

## Périmètre couvert

- Garde-fous de tokens et d'i18n (`check-raw-colors`, `check-arbitrary-text-size`, `check-i18n-coverage`) : exécutés (verts) puis leurs angles morts cherchés dans les sources (.ts, gabarits, hex, styles en ligne) : t04-018, 023, 025, 026, 027.
- Sondes d'exécution sur la stack OIDC réelle (personas creator, admin, reader, navigateur en-US) : catalogue, fiche d'item, tiroir « Nouveau », éditeurs d'app / carte / dataset, sélecteur de couche, /reports, /tasks, Paramètres, cloche de notifications, pages d'administration.
- Libellés bruts, dates, nombres, pluriels, vocabulaire (t04-001 à 005, 013 à 017, 019, 022).
- Mesures de hauteurs de contrôles et de styles de titres entre pages similaires (t04-006 à 008, 021).
- États d'erreur (lectures du cœur mockées en 500), de chargement (lectures retardées de 5 s), d'accès refusé, d'état vide (t04-009 à 012, 015, 023).
- Suite : 30 tests (`shell/e2e/journeys/t04/`), 10 en `fixme`/bug-révélateur rejouables via `T04_VERIFY=1`, les autres passent et restent en régression. ESLint et Prettier propres.

## Périmètre NON couvert

- ETL, export, admin tools, quotas, LLM désactivés sur la stack : validation de graphe de pipeline (t04-024 par lecture seule, probable), page Infrastructure (t04-025 partiel par lecture).
- Rendu MapLibre réel (worker servi en octet-stream, j12-001) : contrôles de carte sondés via le stub de j12 ; légende de symbologie lue dans le code seulement.
- Envoi de fichier (`POST /v1/uploads` en 500, j03-001).
- Thème sombre et contraste (t01), performance (t03), mobile (j12) : hors périmètre, non re-signalés.
- Comparaison pixel par pixel : remplacée par des mesures DOM (hauteur, taille de police, graisse), plus robustes.

## Méthode

Lecture des trois scripts de garde puis des kit `ui/kit`, du catalogue `i18n` et des pages ; sondes Playwright avec `page.route` pour forcer erreurs et lenteurs ; mesure via `getBoundingClientRect`/`getComputedStyle` ; `grep` de dénombrement pour les dettes transverses. Les findings déjà connus (j01-j13, t01, t03) sont référencés via `related_gap`, jamais dupliqués (j02-012 filtre vide, t01-019/020 accessibilité).

## Commandes lancées

- `cd shell && node scripts/check-raw-colors.mjs && node scripts/check-arbitrary-text-size.mjs && node scripts/check-i18n-coverage.mjs`
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/t04` (nominal : passent ; bugs : fixme)
- `cd shell && T04_VERIFY=1 npx playwright test -c playwright.journeys.config.ts e2e/journeys/t04/<spec>` (rejoue les tests bug ; 8 échecs attendus sur consistency et states, les autres confirmés à l'exécution précédente)
- `cd shell && npx eslint e2e/journeys/t04 && npx prettier --check e2e/journeys/t04`
- `grep -rn` de dénombrement (états de chargement, alertes, hex, `(s)`, `toLocaleString`)
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/t04 --repo-root ..`
