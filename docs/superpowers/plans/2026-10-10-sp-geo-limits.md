# Plan SP Geo Limits (spec `2026-10-10-sp-geo-limits-design.md`)

TDD, une tâche = un commit conventionnel. Tests ciblés, base PostGIS privée.

1. **Modèle + migration 0051** `collection_geo_limits` ; test migration base non
   vide, deux sens ; ajout à `purge_tenant`.
2. **Noyau `app/sharing/geo_limits.py`** : validation GeoJSON (shapely), CRUD,
   `resolve_geo_limits`, `GeoLimitRefused`. Tests SQLite.
3. **RLS** : `app_geo_limit()` + policy restrictive (`ddl.py`),
   `rls_scope(geo_limits=)`, dépendance `get_rls_scope` liée, fournisseur
   d'emprise `collections`. Tests PostGIS (lecture, écriture, tuiles, masked).
4. **Chemins refusés** : agrégats REST, MCP analytics, alertes, SQL Lab (exclusion),
   pipelines (reader/join), appexport, pièces jointes (REST + MCP) ;
   `featureCount` masqué. Mapping 42501 → 403 sur les écritures.
5. **API d'administration** (`/collections/{id}/geo-limits`), audit, tests.
6. **OpenAPI + types TS**, `ItemClient` + UI du panneau de partage, vitest.
7. **Inventaire** (`inventaire-fonctionnalites.jsonl`), bilan, garde-fou AST.
8. **Revue adversariale** de la branche (un contournement par chemin de lecture).
