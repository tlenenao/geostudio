# SP Geo Limits — restriction géographique de lecture (REV-121 / GAP-27)

Date : 2026-10-10. Statut : conçu, exécuté dans la foulée (voir le plan
`docs/superpowers/plans/2026-10-10-sp-geo-limits.md`).

## 1. Objet

Une **limite géographique** (« Geo Limit », à la GeoNode) est une géométrie
(Polygon/MultiPolygon GeoJSON, WGS84/4326) attachée à un couple
**(collection × cible)** où la cible est un **rôle** (`roles.id`) ou un
**groupe** de partage (`groups.id`). Elle restreint les **entités visibles ET
écrivables** par les utilisateurs portés par cette cible : une entité n'est
visible que si sa géométrie est **entièrement contenue** (`ST_CoveredBy`) dans
la limite ; l'écriture (insert/update) d'une entité hors limite est refusée.

Hors périmètre : limites par utilisateur nominatif, limites sur les `items`
(cartes/apps), limites sur plusieurs géométries par couple, découpage
(clipping) des géométries à la limite, tuiles/agrégats sur le lac pour un
utilisateur limité (refusés, § 5).

## 2. Décision d'autorisation : la porte reste unique

`can()` / `decide()` (`app/sharing/authorization.py`) restent LA décision
« cet utilisateur peut-il lire/écrire cette collection ». Une limite
géographique n'est **pas une seconde autorisation** : c'est une **contrainte
de rétrécissement de l'ensemble de lignes**, appliquée APRÈS un `can()` positif,
comme le masquage de colonnes GAP-22 (`data.view_sensitive`). Elle ne donne
jamais un droit que `can()` refuse. Sa résolution vit dans le même paquet
(`app/sharing/geo_limits.py`), son application est faite par **Postgres**
(RLS), pas par du SQL applicatif — donc valable pour tout code qui s'exécute
sous `rls_scope`.

### 2.1 Qui est limité (résolution)

`resolve_geo_limits(session, user_id, tenant_id)` renvoie, par `table_name`, la
liste des géométries applicables :

- utilisateur authentifié : entrées dont la cible est son `role_id` ou l'un de
  ses groupes (`group_members`). Plusieurs entrées applicables → **union**
  (la plus permissive des entrées qui s'appliquent à lui). Aucune entrée
  applicable → non limité sur cette collection ;
- invité porteur d'un lien de partage (GAP-19) : limites de **`guest.created_by`**
  (la délégation n'excède jamais le délégant) ;
- anonyme : sur toute collection portant **au moins une** entrée, liste
  **vide** (= ne voit rien). Sans cela, un utilisateur limité n'aurait qu'à se
  déconnecter pour lire une collection publique.
- aucun contournement implicite pour le propriétaire de la collection ni pour
  `is_admin` / `admin.collections.manage` : si une entrée s'applique à
  leur rôle/groupe, elle les limite (choix conservateur, § 9).

### 2.2 Application : RLS restrictive

- fonction SQL `public.app_geo_limit(tbl text) RETURNS geometry` (STABLE) lit le
  GUC transactionnel `app.geo_limits` (JSON `{table_name: [GeoJSON, …]}`) et
  renvoie l'union, `GEOMETRYCOLLECTION EMPTY` si la liste est vide, `NULL` si la
  table n'est pas limitée ;
- par collection **géométrique**, policy `geo_limit` **`AS RESTRICTIVE FOR ALL`**
  (`USING` et `WITH CHECK`) : `(SELECT app_geo_limit('t')) IS NULL OR
  ST_CoveredBy(geom, (SELECT ST_Transform(app_geo_limit('t'), srid)))`.
  RESTRICTIVE = AND avec `tenant_isolation` ; les deux rôles `gis_rls` et
  `gis_rls_masked` y sont soumis ; géométrie NULL = invisible/non insérable
  pour un utilisateur limité ;
- policy posée par `apply_collection_ddl` (idempotent, toute nouvelle
  collection) ET par `ensure_geo_limit_policy` à la création d'une limite
  (collections antérieures) ;
- `rls_scope(session, tenant_id, *, masked, geo_limits)` pose le GUC. La
  dépendance `get_rls_scope` (la seule que les routes consomment) **lie
  `geo_limits` de la requête** (`functools.partial`) : toute route qui passe
  par `rls(...)` est donc limitée sans modifier chaque site d'appel (fail-closed
  par construction). Un garde-fou de test (AST) interdit tout appel
  `rls_scope(` de `app/` sans `geo_limits=` explicite (hors la dépendance).

## 3. Modèle de données

Table `collection_geo_limits` (migration `0051`) : `id` PK, `tenant_id` FK,
`collection_id` FK `collections.id` ON DELETE CASCADE, `target_type`
(`role`|`group`), `target_id`, `geometry` (JSON : GeoJSON normalisé),
`created_by`, `created_at`, `updated_at` ; UNIQUE
`(collection_id, target_type, target_id)` ; index `(tenant_id, collection_id)`.
Chaque écriture est tracée dans `audit_log` (`geo_limit.set` / `geo_limit.delete`).
Ajoutée à `purge_tenant`.

Validation d'une géométrie : GeoJSON `Polygon`/`MultiPolygon`, coordonnées
WGS84 (lon ∈ [-180,180], lat ∈ [-90,90]), non vide, **valide** (shapely
`is_valid`, sinon 422 — pas de réparation silencieuse), ≤ 5 000 sommets (borne de
coût de la policy). Collection sans colonne géométrique : 422.

## 4. API d'administration

Garde : privilège existant **`admin.collections.manage`** (aucun nouveau
privilège → pas de libellé i18n de rôle). Routes sous `/v1` :

- `GET    /collections/{id}/geo-limits` → `{limits: [{targetType, targetId, targetName, geometry, updatedAt}]}`
- `PUT    /collections/{id}/geo-limits/{targetType}/{targetId}` corps `{geometry}` (upsert, 200)
- `DELETE /collections/{id}/geo-limits/{targetType}/{targetId}` (204)

La cible doit exister dans le tenant (404 sinon). Collection non trouvée dans
le tenant : 404.

## 5. Inventaire exhaustif des chemins de lecture (pièges n°11 et n°14)

Méthode : `grep` de `rls_scope`/`get_rls_scope`, `select_features`,
`get_feature`, `ST_AsMVT`, `read_parquet`, `run_collection_aggregate`,
`run_analyst_sql`, `introspect_table`, `FROM public.`, `feature_count`, puis
suivi des appelants réels (pas du vocabulaire).

| # | Chemin | Mécanisme réel | Traitement |
|---|--------|----------------|-----------|
| 1 | OGC Features `GET /collections/{id}/items`, `/items/{fid}` | `rls(...)` (DI) | **COUVERT** (RLS) |
| 2 | OGC Features écritures `POST/PUT/DELETE` | `rls(...)` | **COUVERT** : USING → 404, WITH CHECK → 403 `outside_geo_limit` |
| 3 | Export synchrone `/export/items` et job asynchrone (`dataexport.jobs`, relu à l'exécution avec l'utilisateur du job) | `rls_scope` | **COUVERT** |
| 4 | Tuiles MVT `/tiles/z/x/y.mvt` (+ agrégation basse zoom) | `rls(...)` | **COUVERT** (RLS avant `ST_AsMVT`) |
| 5 | STAC `/stac/collections/{id}/items`, `/items/{id}`, `/search` (GET/POST) | `rls(...)` | **COUVERT** |
| 6 | Emprises STAC/DCAT (`rls_scoped_bbox_4326`) et `GET /collections/{id}` (`extent`) | `rls(...)` / fournisseur inline | **COUVERT** (l'emprise est celle du visible) |
| 7 | MCP `query_features` | `rls_scope` | **COUVERT** |
| 8 | `featureCount` (liste + fiche de collection ; STAC n'en expose pas) | colonne `collections.feature_count` | **MASQUÉ** (`null`) pour l'utilisateur limité |
| 9 | Agrégats `POST /collections/{id}/aggregate`, `/export` (lac GeoParquet/DuckDB) | DuckDB, hors Postgres | **REFUSÉ** 403 `geo_limit_unsupported` |
| 10 | MCP `aggregate_dataset` (`mcp/tools/analytics.py`), évaluation d'alerte (`alerts/jobs.py`) | `run_collection_aggregate` | **REFUSÉ** |
| 11 | SQL Lab `POST /analytics/sql` | vues DuckDB sur le lac | collections limitées **exclues** des tables autorisées (inconnue pour l'utilisateur) |
| 12 | Pipelines : `reader.collection`, jointure `withCollectionId` (lac) | DuckDB | **REFUSÉ** (`PipelineRuntimeError`) |
| 13 | Pipelines : `writer.collection` | `rls_scope` | **COUVERT** (limites du propriétaire du pipeline ; échec explicite si hors limite ; mode `replace` REFUSÉ sur collection limitée, il ne supprimerait que le visible) |
| 14 | Export d'app statique/connecté/autoporté (`appexport.freeze`/`snapshot`) | `rls_scope(masked=True)` + lac | **REFUSÉ** si la collection porte une entrée (un export fige des données pour des tiers anonymes) |
| 15 | Pièces jointes (5 routes REST + MCP `list_attachments`) | table `attachments` par `(collection, fid)`, hors RLS | **REFUSÉ** pour l'utilisateur limité (non vérifiable sans `app.features`, couche supérieure) |
| 16 | Rapports/exports PDF-PNG (worker Playwright) | jeton d'export lié à l'utilisateur → REST | **COUVERT par construction** (mêmes routes REST) |
| 17 | Lac CDC (backfill/compaction) | écrit en système, non lu par un utilisateur | hors périmètre ; ses LECTEURS sont 9–12 |
| 18 | Fédération/moissonnage `/harvest/datasets/*` | données distantes (ArcGIS…), pas des collections | hors périmètre |
| 19 | Recherche sémantique | indexe des `items`, jamais des entités | hors périmètre |
| 20 | `items.bbox` (emprise d'un item carte recalculée à l'écriture) | `configs/bbox.py`, table entière | **NON FAIT, accepté** : métadonnée d'enveloppe, pas une entité (§ 9) |

Jumelles listées avant d'écrire : tuiles ↔ items (même scope), export sync ↔
export job (rejoué à l'exécution), REST ↔ MCP ↔ alertes ↔ pipelines pour le
lac, STAC ↔ DCAT (emprise), 5 routes pièces jointes + MCP.

## 6. Écriture hors limite

La policy porte `WITH CHECK` : un `INSERT`/`UPDATE` dont la géométrie résultante
n'est pas contenue dans la limite lève SQLSTATE 42501, converti en
`403 outside_geo_limit` par les routes d'écriture. Un `UPDATE`/`DELETE` d'une
entité déjà hors limite ne la voit pas (RLS `USING`) : 404, comme une entité
inexistante. `DELETE` en masse (`writer.collection` mode replace) est refusé
sur une collection limitée.

## 7. UI minimale

Dans l'écran de partage de collection (`CollectionSharePanel`), section
« Limites géographiques » (visible avec `admin.collections.manage`) : liste des
limites, formulaire cible (groupe seulement en UI ; les cibles rôle sont API-only) + GeoJSON collé, suppression. Accès
exclusivement via `ItemClient` (`listGeoLimits`/`putGeoLimit`/`deleteGeoLimit`).
Pas d'éditeur cartographique de polygone (non fait).

## 8. Performance (plafond assumé)

La policy évalue `app_geo_limit()` une fois par requête (InitPlan) ; pour un
utilisateur non limité le coût est un test `IS NULL`. Pour un utilisateur limité
`ST_CoveredBy` est indexable GiST. Plafond : 5 000 sommets/limite, union
recalculée par requête.

## 9. Décisions à valider

1. **Contenu strict** (`ST_CoveredBy`) plutôt qu'intersection : une entité à
   cheval sur la limite est invisible (sinon la partie hors limite fuite).
   Alternative : intersection + clipping (non fait).
2. **Union** des entrées applicables (rôle + groupes) : l'utilisateur voit la
   plus large zone qui lui est permise.
3. **Pas d'exemption** admin/propriétaire : une entrée sur le rôle
   Administrateur limiterait réellement les administrateurs.
4. **Anonyme = rien** sur une collection portant au moins une limite.
5. **Invité** = limites du créateur du lien.
6. **Privilège** : `admin.collections.manage` réutilisé (pas de nouveau
   privilège).
7. **Lac/DuckDB, pièces jointes, export d'app : refus** plutôt que contournement
   partiel ; un utilisateur limité perd donc dashboards agrégés, SQL Lab sur
   cette collection et pièces jointes. Suivi : clipping DuckDB (nécessite
   `ST_CoveredBy` sur la géométrie GeoParquet), vérification de visibilité de
   l'entité pour les pièces jointes.
8. `items.bbox` d'une carte reflète les données complètes (enveloppe seulement).
9. Une limite sur une collection dont la table a une géométrie NULL pour
   certaines lignes les cache (fail-closed).
10. SRID de la colonne ≠ 4326 : la limite est reprojetée dans la policy
    (`srid` figé à la pose de la policy).
