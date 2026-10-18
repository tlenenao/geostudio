# Catalogue des outils MCP

> Fichier **généré** par `core/scripts/gen_mcp_catalog.py` depuis le registre du cœur
> (`app/mcp/tools`) — ne pas l'éditer à la main ; un test échoue s'il est périmé.
> Les outils d'écriture sont refusés quand `CORE_READ_ONLY_MODE=true`.

| Outil | Accès | Description |
|---|---|---|
| `add_group_member` | écriture | Add a member to a sharing group — mirrors POST /groups/{id}/members. Only the group's creator may add a member (repository-enforced) — raises rather than silently no-op-ing on… |
| `create_alert_rule` | écriture | Create an AlertRule — mirrors POST /configs with kind="alert". Registered unconditionally (alerts are not gated by CORE_ETL_ENABLED, unlike pipelines). SP-53. |
| `create_bookmark` | écriture | Save a named analytics view (time range/extent/cross-filter) on an app page — mirrors POST /configs with kind="bookmark". SP-14m. |
| `create_dataset` | écriture | Create a shared dataset (source collection or arcgis) — mirrors POST /configs with kind="dataset" (the path itemClient.ts::createDatasetItem uses). SP-14l. |
| `create_form_app` | écriture | Compose a Carte+Table(+Formulaire if the caller can write) app on an existing collection, from its introspected schema — same shape as the builder's "Application de saisie"… |
| `create_group` | écriture | Create a sharing group — mirrors POST /groups. |
| `create_item` | écriture | Create a new app or dashboard — mirrors POST /configs, including its privilege guard (apps.manage, app.roles.kind_registry:: privilege_for_kind). The item's owner is always the… |
| `create_pipeline` | écriture | Create a Pipeline (reader/transform/writer graph) — mirrors POST /configs with kind="pipeline". Only registered when CORE_ETL_ENABLED is on. SP-15a. |
| `delete_secret` | écriture | Delete a connector secret — mirrors DELETE /secrets/{id}. |
| `explain_alert_rule` | lecture | Describe an AlertRule (dataset, condition, schedule, current state) without evaluating it — mirrors explain_pipeline's shape. Registered unconditionally (no capability flag).… |
| `explain_dataset` | lecture | Describe a dataset's queryable fields before calling run_analytics_query — author metadata (columns/timeField/ reactsToExtent) plus introspected field name+type, so an agent… |
| `explain_pipeline` | lecture | Describe a Pipeline's graph (nodes/ops/edges) without running it — mirrors explain_dataset's shape. Only registered when CORE_ETL_ENABLED is on. SP-15a. |
| `explain_report_schedule` | lecture | Describe a ReportSchedule (target bookmark, cron, channels, last run) without triggering it — mirrors explain_alert_rule's shape. Registered unconditionally (no capability… |
| `generate_attribute_rule` | lecture | Generate a CEL attribute rule draft ({id, kind, field, expression, message, mode}) for a collection from a natural-language question. The collection's columns are the CEL… |
| `generate_cel_expression` | lecture | Generate a CEL expression draft from a natural-language question, for the given context (visibleWhen, computedColumn, actionCondition, binding). Only the references listed in… |
| `generate_sql_query` | lecture | Generate a read-only SQL SELECT draft (DuckDB dialect) from a natural-language question, scoped to one collection. Never executes the query — the caller must insert it as a… |
| `generate_visual_query` | lecture | Generate structured filters/join/summary (matching the visual query wizard's FilterRow[]/JoinConfig/SummaryConfig shapes) from a natural-language question — never creates or… |
| `geocode` | lecture | Geocode a postal address or place name (3-200 characters) into coordinates. Returns {"results": [{"label", "lon", "lat"}]}, at most `limit` (1-10) entries. Read-only. REV-102. |
| `geocode_batch` | lecture | Geocode up to 500 addresses (3-200 characters each) in one call. Returns {"results": [{"address", "status", "label", "lon", "lat"}], "found", "not_found", "errors"}; status is… |
| `get_app_config` | lecture | Get the app/dashboard config for an item — mirrors GET /configs/by-item/{id}. |
| `get_item` | lecture | Get one catalog item by id — mirrors GET /items/{id}. |
| `get_item_impact` | lecture | List what depends on an item (type="item", default) or a collection (type="collection") — i.e. what would break if it were deleted: visible dependents (transitive, with depth)… |
| `get_sharing` | lecture | Get an item's sharing settings — mirrors GET /items/{id}/sharing. |
| `isochrone` | lecture | Travel-time polygons around one origin ({"lon","lat"}) for 1-4 contours of 1-60 minutes. Returns a GeoJSON FeatureCollection (property contour_minutes). Read-only. ARC-34. |
| `list_attachments` | lecture | List the metadata of files attached to one entity of a collection (chantier 4.12) — read-only, never returns file bytes. No fileUrl: the REST proxy-read it would point to (GET… |
| `list_groups` | lecture | List the caller's sharing groups, or search the tenant's groups by name with `q` (>= 2 characters, capped) — mirrors GET /groups. |
| `list_items` | lecture | List catalog items — mirrors GET /items. scope: all\|mine\|shared\|public. |
| `profile_dataset` | lecture | Exploratory profile of a collection-sourced dataset (REV-117, X-rays): per-column null/distinct counts, min/max/quantiles/histogram, top values, geometry extent and types.… |
| `query_features` | lecture | Read features from a collection — mirrors GET /collections/{id}/items (bbox, attribute filters, pagination), same permissions/RLS. No natural-language-to-filter translation:… |
| `raster_zonal_stats` | lecture | Zonal statistics of a raster item (COG) over GeoJSON polygons (Polygon/MultiPolygon, Feature or FeatureCollection, WGS84, at most 1000). `stats` among count, min, max, mean,… |
| `route` | lecture | Compute a route through 2-20 points (each {"lon", "lat"}, WGS84). costing: auto, bicycle, pedestrian, truck, bus or motor_scooter. Returns {"distance_km", "duration_s",… |
| `run_alert_rule` | écriture | Defer an immediate evaluation of an AlertRule — mirrors, for a single rule, what sweep_alert_rules_task does for all due rules. Same route as REST since revue finale Vague C… |
| `run_analytics_query` | lecture | Run a structured aggregate query against a dataset (source collection or arcgis) — mirrors POST /collections/{id}/aggregate and POST /datasets/{id}/arcgis/aggregate, same query… |
| `run_pipeline` | écriture | Defer a run of a Pipeline — mirrors POST /pipelines/{id}/run. Only registered when CORE_ETL_ENABLED is on. SP-15a. `params` : valeurs des paramètres de run déclarés par le… |
| `save_app_config` | écriture | Save (and version) the app/dashboard config for an item — mirrors PUT /configs/by-item/{id}. Pass `expectedVersion` (the `version` read with get_app_config) to refuse the write… |
| `search_catalog` | lecture | Search the catalog (hybrid trigram + vector ranking on q) — items only, not collections. Same permissions/parameters as list_items; registered as its own tool for agent… |
| `search_collections` | lecture | Search collections (hybrid trigram + vector ranking on q, same mechanism as search_catalog for items) — collections were never searchable from an agent before this tool… |
| `service_area` | lecture | Isochrones for 1-10 origins at once (features carry origin_index and contour_minutes). Read-only. ARC-34. |
| `set_sharing` | écriture | Set an item's sharing settings — mirrors PUT /items/{id}/sharing. |
| `travel_matrix` | lecture | Distance (km) and duration (s) between each source and each target (at most 50 each, 1000 cells). Returns {"matrix": [[{"distance_km","duration_s"}]]}. Read-only. ARC-34. |
| `update_item` | écriture | Update an item's catalog metadata — mirrors PATCH /items/{id} (same privilege guards: write access, kind privilege, and catalog.manage for `contentStatus`/`categories`). Pass… |
| `whoami` | lecture | Return the identity of the currently authenticated MCP caller — proves the OAuth handshake resolves to the same User the shell's REST API would resolve for the same Keycloak… |
