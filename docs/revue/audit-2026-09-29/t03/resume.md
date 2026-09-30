# t03 — Performance perçue

## Périmètre couvert
- Bundle : charge initiale (manifeste servi, 694,9 Ko bruts / 209 Ko gzip), découpage par route, livraison statique (cache, compression, fallback, contenu de l'image).
- LCP/CLS : catalogue à froid (sans et avec bridage 4G lente + CPU x4, cache désactivé) ; éditeur de carte vide et à 500k, builder et runtime d'app (table 50k) mesurés en navigation SPA (voir limites).
- Gros volumes : collections de 50 000 et 500 000 points (POST /v1/collections/empty puis INSERT ... generate_series dans leur seule table, POST /v1/uploads étant en 500 : j03-001). API items (page, offset profond, bbox), aggregate, tuiles MVT, export, droits du lecteur, erreurs, collection vide ; carte 500k (repositionnements, images/s), tableau 50k/500k.
- Sondages : cloche de notifications (45 s), pause onglet masqué, reprise au retour ; fuites au démontage (tas, nœuds, écouteurs, contextes WebGL, intervalles).

## Limites et périmètre NON couvert
- Le worker MapLibre est servi en octet-stream (j12-001) : toutes les mesures de rendu carte utilisent le contournement `fixWorkerMime` + fond de carte local (`stubMapEnv`). Elles reflètent le rendu réel une fois ce défaut corrigé, pas l'état livré, où aucune tuile ne se rend. Rendu WebGL logiciel (headless) : les temps d'images sont un majorant.
- LCP/CLS « à froid » n'a de sens que pour `/` : un rechargement dur d'une route authentifiée retombe sur `/` après Keycloak (j02-004). Les autres routes sont mesurées en navigation SPA (temps jusqu'à l'élément prêt + delta CLS), pas en LCP.
- Non couverts : LCP du persona lecteur, appareils réels, réseau réel via Traefik (compression Traefik non exercée : les mesures sont sur nginx :8300), 500k+ polygones/lignes (points seulement), analytics DuckDB/CDC (le lakehouse n'a pas été peuplé ; aggregate répond via Postgres), export/ETL/quotas/LLM (capacités désactivées), builder avec beaucoup de widgets.
- `featureCount` reste à 0 sur les collections seedées par SQL : artefact du seed, non signalé.
- 34 tests écrits (22 verts, 12 fixme) : dépasse le budget indicatif de 25, la suite de régression étant peu coûteuse ; les deux tests de sondage durent ~100 s chacun.

## Méthode
Sondes exploratoires jetables puis specs figées. Chaque `test.fixme` a été exécuté sans son marqueur (copie temporaire supprimée) et a échoué pour la raison attendue. Causalité de t03-005 établie par contrôle : LCP 4,64-4,72 s avec vendor-map contre 2,60-2,64 s quand la requête est bloquée (2 répétitions chacune, cache désactivé). Un premier passage du test de visibilité était vacueux (l'évènement `visibilitychange` doit bubbler jusqu'à window pour react-query) : corrigé et rejoué. Résultats sains : LCP catalogue 0,57 s, CLS < 0,05 partout, cloche 45 s exacte et suspendue en arrière-plan, API 500k < 300 ms, carte 500k p95 33 ms/image.

## Commandes
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/t03` (22 passed, 12 skipped)
- `cd shell && npx eslint e2e/journeys/t03 && npx prettier --check e2e/journeys/t03`
- Validateur : `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/t03 --repo-root ..`
