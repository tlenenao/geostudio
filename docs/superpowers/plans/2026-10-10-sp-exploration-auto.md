# Plan — SP exploration automatique (REV-117 / GAP-23)

Spec : `docs/superpowers/specs/2026-10-10-sp-exploration-auto-design.md`. TDD, tests ciblés.

1. **Cœur analytique** — `core/tests/test_analytics_profile.py` (lac local tmp_path) puis
   `core/app/analytics/profile.py` : colonnes numériques/texte/date, nulls, top, histogramme,
   emprise + types de géométrie, masquage, lac vide (`pending`), cap de colonnes, échantillon.
2. **REST** — `GET /v1/collections/{id}/profile` + tests de route (`test_features_profile_routes.py` :
   200, 404 non lisible, masquage sans `data.view_sensitive`, `pending`).
3. **MCP** — outil `profile_dataset` + test postgis (`test_mcp_tools_profile_dataset.py`).
4. **OpenAPI + types TS** — régénération (incantation CLAUDE.md).
5. **Shell** — `getCollectionProfile` (types + domaine), hook, `CollectionProfilePanel`,
   intégration `DatasetPage`, clés i18n ; tests vitest.
6. **Inventaire** — entrée `docs/revue/inventaire-fonctionnalites.jsonl` (REST + MCP + shell)
   puis `feature_health_cli --write`.
7. **Portes** — ruff, lint-imports, mypy (si module listé), vitest ciblés, `npm run lint`,
   `format:check`, `build`. Revue de branche (jumelles de garde, livré ≠ câblé).
