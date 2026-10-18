# Lot L13 : plan (2026-10-19)

Ordre d'exécution, un commit par AUD, TDD, tests ciblés puis portes complètes en fin de lot.

1. AUD-063 : `aggregate.py` (top-N, opérateurs, cache) + `tests/test_analytics_aggregate_aud063.py`.
2. AUD-062 : domaine `saved_queries` + migration 0172 + shell (`savedQueries` domaine/hooks, SqlLabPage, i18n fr/en, `StaticItemClient`/`DesktopItemClient` en stub).
3. AUD-131 : `DataSource.refreshSeconds` + `DataContext` + sélecteur de pas.
4. AUD-142 : route `point` raster + schéma + tests (même fixture que les tuiles).
5. AUD-143 : `.fgb` (parsers, importer, `accept` du bouton d'import).
6. Revue finale de branche (jumelles : autres points de dispatch de format, autres consommateurs des filtres d'agrégat), régénération OpenAPI/types, portes.

Surfaces à inventorier (hors périmètre de ce couloir) : 4 routes `/v1/analytics/sql/saved*`, `GET /v1/raster/{id}/point`.
