# j10b — Sites, storytelling, export d'apps (passe flags allumés, 2026-09-30)

## Périmètre couvert
- Export d'apps en exécution réelle, modes Statique / Connecté / Autoporté : création de job, garde (collection non publique, widget tiers, widget imbriqué, variableInput), gel, instantané GeoParquet, contenu des zips, droits (lecteur : 404), champs sensibles, troncature à 50 000, export d'un item qui n'est pas une app.
- Ouverture des bundles dans Chromium : Statique (aucun appel au cœur), Connecté (GET anonymes uniquement, sans Authorization), Autoporté (conteneur jetable de l'image `geostudio-appexport-standalone:local`).
- CORS étroit du mode Connecté : lectures anonymes listées (ACAO `*`), écritures et routes privées sans en-tête, préflight.
- Builder : avertissement « widget d'écriture » avant export.
- tileset3d : proxy de lecture d'un tileset finalisé (200, 404, traversée, 401, privé/publié), droits sur l'envoi ; terrain3d et tileset3d : routes d'envoi.
- Confirmation de j10-007, j10-008, j10-009, j10-010 (de « probable/lecture » à « verified ») via j10b-006, -004, -003, -005.

## Périmètre NON couvert (et pourquoi)
- Impression PDF (`printLayout`) et `ReportSchedule` : le worker d'export redémarre / est « health: starting », cœur injoignable depuis lui (j05b-008, connu), `POST /v1/export` et rapports planifiés en 500 (j09b, connus). Seule la validation du `printLayout` avait été couverte en première passe.
- Conversion terrain3d (COG via titiler) et tuiles terrain : l'envoi est bloqué par j10b-012 ; conversion et lecture de tuiles non exercées.
- Sites, storytelling, PageManager : déjà couverts par j10 (23 tests) ; aucun drapeau supplémentaire ne change ce périmètre.
- Bloc observabilité absent de la stack (profil non démarré).
- Le bouton « Télécharger » n'a pas pu être suivi : lien inaccessible (j10b-008).

## Méthode
Lecture du code (appexport routes/jobs/guard/freeze/snapshot/bundler/miniserver, tileset3d/terrain3d routes, base.ts), puis 25 tests Playwright (`shell/e2e/journeys/j10b/`). Contournements : `POST /v1/app-exports` répond 500 (AppNotOpen) mais commit le job ; le test lit la ligne `app_export_jobs` et rejoue `build_app_export_task` dans le conteneur worker (`run_export.py`, copié dans le conteneur) avec `ensure_uploads_bucket` neutralisé (PutBucketCors non implémenté, j10b-002) ; le zip est récupéré par `docker cp`, extrait et servi par un mini serveur HTTP local. Le conteneur autoporté est lancé en `docker run` jetable (supprimé en `finally`) avec le code `core/app` courant monté (l'image locale du 15 août est périmée, j10b-009) et le volume `geostudio_appexport-runtime`. Les tilesets sont créés par `finalize_tileset3d_task` rejouée dans le worker (la config ne se crée pas par l'API).

Résultat : 14 tests passent (régression), 11 sont `test.fixme` avec l'id du finding, chacun vérifié en échec réel avant marquage. 13 findings (12 verified, 1 probable).

## Commandes lancées
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j10b` (14 passed, 11 skipped)
- `npx eslint e2e/journeys/j10b && npx prettier --check e2e/journeys/j10b`
- sondes : `curl` CORS sur :8200, `docker exec geostudio-worker-1 python` (tâches appexport/tileset3d), `docker run` jetable de l'image autoportée, `psql` (app_export_jobs)
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j10b --repo-root ..`
