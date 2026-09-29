# c08 - Parité REST / MCP / ItemClient (code)

## Périmètre couvert
- Outils MCP (`core/app/mcp/tools/*`) comparés aux routes REST et services partagés (configs, items, sharing, pipelines, analytics, catalogue).
- Schéma BuilderConfig (AppConfig/MapConfig) côté cœur vs types manuscrits du shell (`types.ts`) et types générés.
- Propagation des erreurs RFC 7807 (handlers `main.py`, `parseErrorResponse`, sites fetch directs du shell).
- Sas ItemClient : contournements par fetch nu.

## Non couvert
- Pas de stack ni de base PostGIS : comportements Postgres (OFFSET négatif) non rejoués (c08-003 en `probable`).
- Routes derrière flags (pipelines, exports, sites, tileset3d) absentes de l'OpenAPI exportée sans flags : lues dans le code, pas énumérées automatiquement.
- Outils alerts/reports/query_generation lus en diagonale (pas de divergence trouvée) ; POST /extensions déjà inventorié sans surface (`inventaire-fonctionnalites.jsonl`), non re-signalé.

## Méthode
Lecture des services partagés, énumération OpenAPI vs `@server.tool()`, sondes exécutées sous `probes/` (pytest sqlite, script TestClient, tsc de dérive de types).

## Commandes lancées
- `uv run python scripts/export_openapi.py` (énumération des routes)
- `probes/test_c08_probes.py` (3 tests verts : lien de partage inter-item, pagination MCP, widget inconnu)
- `probes/probe_7807.py`, `probes/probe_schema.py`, `npx tsc -p probes/tsconfig.json`
- validateur `audit_findings.py validate`
