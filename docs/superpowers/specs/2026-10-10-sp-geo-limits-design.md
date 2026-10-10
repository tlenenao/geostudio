# SP Geo Limits — restriction géographique de lecture (REV-121 / GAP-27)

Date : 2026-10-10. Statut : conçu, exécuté dans la foulée (voir le plan
`docs/superpowers/plans/2026-10-10-sp-geo-limits.md`). **v2 (même jour, décisions de
Tanguy)** : découpage à la limite au lieu de l'inclusion stricte (§5, §9 déc. 1),
exemption administrateur (§2.1, §9 déc. 3), règle de changement de type/SRID de la
colonne géométrie (§2.2, §9 déc. 11), unicité sans fuite d'existence (§6, §9 déc. 12).

## 1. Objet

Une **limite géographique** (« Geo Limit », à la GeoNode) est une géométrie
(Polygon/MultiPolygon GeoJSON, WGS84/4326) attachée à un couple
**(collection × cible)** où la cible est un **rôle** (`roles.id`) ou un
**groupe** de partage (`groups.id`). Elle restreint les **entités visibles ET
écrivables** par les utilisateurs portés par cette cible. **Découpage (v2)** : une
entité dont la géométrie **intersecte** la limite est visible, mais la géométrie
qui sort de Postgres est `ST_Intersection(géométrie, limite)` — la géométrie
complète ne quitte jamais la base pour un utilisateur limité, sur aucun chemin
(§5) ; une entité qui ne fait que toucher la limite par un bord (intersection de
dimension inférieure) ou qui est hors limite est invisible. L'écriture
(insert/update) d'une entité dont la géométrie déborde de la limite est refusée.

Hors périmètre : limites par utilisateur nominatif, limites sur les `items`
(cartes/apps), limites sur plusieurs géométries par couple, tuiles/agrégats sur
le lac pour un utilisateur limité (refusés, § 5).

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
- **exemption administrateur (v2)** : un utilisateur dont le rôle porte
  `admin.collections.manage` n'est **jamais** limité (la résolution renvoie `{}`,
  entrées de groupe comprises ; pour un lien de partage, c'est le créateur qui est
  évalué). `PUT .../geo-limits/role/{id}` sur un rôle portant ce privilège est refusé en
  422. Le **propriétaire** de la collection, lui, reste limité (§ 9).

### 2.2 Application : RLS restrictive + source découpée unique

- fonction SQL `public.app_geo_limit(tbl text) RETURNS geometry` (STABLE) lit le
  GUC transactionnel `app.geo_limits` (JSON `{table_name: [GeoJSON, …]}`) et
  renvoie l'union, `GEOMETRYCOLLECTION EMPTY` si la liste est vide, `NULL` si la
  table n'est pas limitée ;
- par collection **géométrique**, quatre policies `AS RESTRICTIVE`
  (`ensure_geo_limit_policy`) : `geo_limit_select`/`geo_limit_update` (USING +
  WITH CHECK) : `app_geo_limit IS NULL OR ST_CoveredBy(geom, limite) OR
  (app.geo_partial = '1' AND ST_Intersects(geom, limite))` ; `geo_limit_insert`
  (WITH CHECK) et `geo_limit_delete` (USING) : contenu strict. Le drapeau GUC
  transactionnel `app.geo_partial` n'est levé que par `geo_source` (lectures
  découpées) et par la mise à jour d'attributs d'une entité à cheval ; **sans lui, un
  lecteur qui oublierait le point central ne voit que des entités ENTIÈREMENT
  contenues** : jamais de géométrie complète au-delà de la limite (fail-closed en base).
  RESTRICTIVE = AND avec `tenant_isolation` ; `gis_rls` et `gis_rls_masked` y sont
  soumis ; géométrie NULL = invisible/non insérable pour un utilisateur limité ;
- **point de lecture unique** `geo_source(session, info, columns=None)`
  (`app/sharing/geo_limits.py`) : renvoie l'élément `FROM` d'une collection —
  la table elle-même si l'appelant n'est pas limité sur elle, sinon une
  sous-requête dont la colonne de géométrie est
  `ST_CollectionExtract(ST_Intersection(ST_MakeValid(geom), limite), dim(geom)+1)`
  (`WHERE NOT ST_IsEmpty`). Tout prédicat (`bbox`, `geom_intersects`, `ST_Extent`,
  `ST_AsMVT`, comptes, tri) porte ainsi sur la géométrie **découpée** — c'est ce qui
  empêche de sonder la partie cachée d'une entité à cheval. Les lectures de
  `app/` passent toutes par lui (`features/repository.py` : liste/détail/comptes ;
  `features/tiles.py` : tuile, sonde, agrégation ; `collections/extent.py` et
  `stac/extent.py` : emprises) ; les exports, STAC, DCAT, MCP, tuiles en héritent. Un
  garde-fou de test (`test_collection_tables_are_only_read_through_geo_source`) échoue
  si une nouvelle lecture SQL brute `FROM public.` d'une table de collection apparaît
  hors liste justifiée ;
- le miroir Python des limites vit dans `session.info["geo_limits"]` (posé par
  `set_geo_limits_guc`, retiré en sortie de scope : le code système lit la table en entier) ;
- policies posées par `apply_collection_ddl` (idempotent, toute nouvelle collection) ET
  par `ensure_geo_limit_policy` à la création d'une limite (collections antérieures). Les
  policies de la v1 (`geo_limit`, contenu strict `FOR ALL`) sont retirées au premier
  `ensure` ; d'ici là elles restent actives (plus strictes : fail-closed, entités à
  cheval masquées) ;
- **changement de type/SRID de la colonne géométrie (règle, déc. 11)** : Postgres refuse
  `ALTER COLUMN TYPE` sur une colonne citée par une policy, et le SRID est figé dans la
  policy. Tout code qui modifie type ou SRID de cette colonne passe par
  `alter_geometry_column` (`app/collections/ddl.py`) : retrait des policies, `ALTER`,
  `ensure_geo_limit_policy`. Aucun chemin de `app/` ne le fait aujourd'hui (la
  réingestion crée une nouvelle table + `apply_collection_ddl`) ; le test
  `test_geometry_column_alter_has_a_single_entry_point` échoue si un `ALTER COLUMN` /
  `UpdateGeometrySRID` / `ALTER TABLE … TYPE` apparaît ailleurs dans `app/` (les
  migrations Alembic ne sont pas couvertes : toute migration touchant la colonne
  géométrie d'une collection doit appeler la même fonction) ;
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
le tenant : 404. Cible `role` portant `admin.collections.manage` : 422 (exemption
administrateur, § 2.1).

## 5. Inventaire exhaustif des chemins de lecture (pièges n°11 et n°14)

Méthode : `grep` de `rls_scope`/`get_rls_scope`, `select_features`,
`get_feature`, `ST_AsMVT`, `read_parquet`, `run_collection_aggregate`,
`run_analyst_sql`, `introspect_table`, `FROM public.`, `feature_count`, puis
suivi des appelants réels (pas du vocabulaire).

| # | Chemin | Mécanisme réel | Traitement |
|---|--------|----------------|-----------|
| 1 | OGC Features `GET /collections/{id}/items`, `/items/{fid}` | `rls(...)` (DI) + `geo_source` | **DÉCOUPÉ** (géométrie, filtres, `numberMatched`) |
| 2 | OGC Features écritures `POST/PUT/DELETE` | `rls(...)` | **COUVERT** : insert/update hors limite → 403 `outside_geo_limit` ; entité à cheval : attributs seulement (403 `geo_limit_straddling` si la géométrie change), suppression → 404 (§ 6) |
| 3 | Export synchrone `/export/items` et job asynchrone (`dataexport.jobs`, relu à l'exécution avec l'utilisateur du job) | `rls_scope` + `geo_source` | **DÉCOUPÉ** |
| 4 | Tuiles MVT `/tiles/z/x/y.mvt` (+ agrégation basse zoom) | `rls(...)` + `geo_source` | **DÉCOUPÉ** (sonde, tuile brute et agrégation lisent la source découpée) |
| 5 | STAC `/stac/collections/{id}/items`, `/items/{id}`, `/search` (GET/POST) | `rls(...)` + `geo_source` | **DÉCOUPÉ** (`geometry` et `bbox` de l'item sur la géométrie rendue) |
| 6 | Emprises STAC/DCAT (`rls_scoped_bbox_4326`) et `GET /collections/{id}` (`extent`) | `rls(...)` / fournisseur inline + `geo_source(columns=())` | **DÉCOUPÉ** (emprise de la géométrie découpée) |
| 7 | MCP `query_features` | `rls_scope` + `geo_source` | **DÉCOUPÉ** |
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

## 6. Écriture (hors limite, entité à cheval, unicité)

- **Hors limite** : l'`INSERT` (policy `geo_limit_insert`) ou l'`UPDATE` (WITH CHECK) dont la
  géométrie résultante n'est pas **entièrement contenue** lève SQLSTATE 42501, converti
  en `403 outside_geo_limit` par les routes d'écriture. Géométrie NULL : idem.
- **Entité à cheval (v2)** : visible (découpée) mais jamais écrasable par sa version
  découpée. `PUT` : attributs seulement. La géométrie du corps doit être absente/NULL ou
  égale (`ST_Equals`, grille 1e-6) à la version découpée renvoyée par la lecture — le
  renvoi tel quel par le shell est donc accepté, sans toucher la géométrie en base ;
  toute autre géométrie → `403 geo_limit_straddling` (fail-closed, base intacte).
  `DELETE` d'une entité à cheval → 404 (policy `geo_limit_delete` contenu strict : la
  partie cachée serait détruite). `DELETE` en masse (`writer.collection` mode replace)
  est refusé sur une collection limitée. Un `UPDATE`/`DELETE` d'une entité entièrement
  hors limite : 404, comme une entité inexistante.
- **Unicité (v2)** : un `INSERT`/`PUT` qui viole une contrainte d'unicité renvoie le même
  `409 feature conflicts with an existing row` que la ligne en collision soit visible ou
  cachée par la limite (aucun détail Postgres dans la réponse ; `POST` et `PUT`).
  Une PK choisie par le client n'existe pas : `id` de premier niveau et propriété `id`
  sont ignorés (la PK est un serial), donc aucun sondage d'existence par collision de PK.
  Les écarts de séquence (`serial`) restent un canal d'inférence du nombre de lignes
  cachées (accepté, § 9).

## 7. UI minimale

Dans l'écran de partage de collection (`CollectionSharePanel`), section
« Limites géographiques » (visible avec `admin.collections.manage`) : liste des
limites, formulaire cible (groupe seulement en UI ; les cibles rôle sont API-only) + GeoJSON collé, suppression. Accès
exclusivement via `ItemClient` (`listGeoLimits`/`putGeoLimit`/`deleteGeoLimit`).
Pas d'éditeur cartographique de polygone (non fait).
Le texte d'aide annonce deux règles : les géométries sont **découpées** à la limite
(`geoLimits.help`) et les titulaires de `admin.collections.manage` ne sont **jamais
limités** (`geoLimits.adminExempt`) ; l'API refuse (422) une limite sur un rôle qui porte
ce privilège.

## 8. Performance (plafond assumé)

La policy évalue `app_geo_limit()` une fois par requête (InitPlan) ; pour un
utilisateur non limité le coût est un test `IS NULL` et la source est la table
elle-même (index GiST intacts). Pour un utilisateur limité, la policy
(`ST_Intersects`/`ST_CoveredBy`) est indexable GiST, mais les prédicats `bbox` /
tuile portent sur la géométrie **découpée** (expression, non indexable) : le coût est
celui d'un `ST_Intersection` par ligne candidate. Plafond : 5 000 sommets/limite,
union recalculée par requête.

## 9. Décisions à valider

1. **Découpage (v2, remplace « contenu strict »)** : une entité qui intersecte la limite
   est visible et sa géométrie est `ST_Intersection(géométrie, limite)` partout (§ 2.2,
   § 5). Les entités qui ne touchent la limite que par un bord (intersection de dimension
   inférieure) sont invisibles ; les `GEOMETRYCOLLECTION` sont ramenées à la dimension
   d'origine (`ST_CollectionExtract`). Écriture : géométrie débordante refusée ; entité à
   cheval modifiable en attributs seulement, non supprimable (§ 6). `featureCount` reste
   masqué. **Résidu assumé** : un attribut stocké dérivé de la géométrie complète (aire,
   longueur, centroïde calculés à l'import) reste lisible tel quel — le découpage ne
   protège que la géométrie ; et un utilisateur limité peut déduire qu'une entité
   « déborde » (sa géométrie découpée touche la frontière, ou `PUT` renvoie
   `geo_limit_straddling`).
2. **Union** des entrées applicables (rôle + groupes) : l'utilisateur voit la
   plus large zone qui lui est permise.
3. **Exemption administrateur seulement (v2, remplace « pas d'exemption »)** : porter
   `admin.collections.manage` = jamais limité ; le rôle Administrateur n'est plus limitable
   (API 422, résolution ignore les entrées existantes). Le propriétaire de la collection
   reste limité.
4. **Anonyme = rien** sur une collection portant au moins une limite.
5. **Invité** = limites du créateur du lien (donc exempt si le créateur est administrateur).
6. **Privilège** : `admin.collections.manage` réutilisé (pas de nouveau
   privilège).
7. **Lac/DuckDB, pièces jointes, export d'app : refus** plutôt que contournement
   partiel ; un utilisateur limité perd donc dashboards agrégés, SQL Lab sur
   cette collection et pièces jointes. Suivi : clipping DuckDB (nécessite
   `ST_Intersection` sur la géométrie GeoParquet), vérification de visibilité de
   l'entité pour les pièces jointes.
8. `items.bbox` d'une carte reflète les données complètes (enveloppe seulement) : calculé
   à l'écriture de la config par le code système (hors scope utilisateur), il est commun à
   tous les lecteurs du catalogue et ne peut pas être par-utilisateur. À valider : c'est
   la seule enveloppe dérivée de la géométrie complète qui reste lisible.
9. Une limite sur une collection dont la table a une géométrie NULL pour
   certaines lignes les cache (fail-closed).
10. SRID de la colonne ≠ 4326 : la limite est reprojetée dans la policy et dans la
    source découpée (`srid` figé à la pose de la policy, relu par `alter_geometry_column`).
11. **Changement de type/SRID de la colonne géométrie (règle, v2)** : unique point
    `alter_geometry_column` (retrait/recréation des policies autour de l'`ALTER`), garde AST
    (§ 2.2).
12. **Unicité (règle, v2)** : même `409` générique pour une collision avec une ligne cachée
    ou visible ; pas de PK client (§ 6). Choix : réponse identique plutôt que rejet de PK
    client, la PK étant déjà non écrivable par les routes.
13. **Mécanisme du découpage** : sous-requête `geo_source` côté lecteur + drapeau GUC
    `app.geo_partial` en base (rejeté : vue par collection — figée sur la liste de
    colonnes, incompatible avec le masquage par colonne GAP-22 car une vue
    `security_invoker` exige l'accès à toutes ses colonnes ; rejeté : expression de
    découpage recopiée dans chaque lecteur). Fail-closed : un lecteur qui ignore
    `geo_source` ne voit que des entités entièrement contenues.
