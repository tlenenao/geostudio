# GeoStudio SP-3 — Collections & CRUD features

> Design / spec. Le cœur apprend à **écrire des données métier** dans PostGIS
> avec permissions — le prérequis absolu des formulaires (SP-4). Registre de
> collections éditables, introspection de schéma, CRUD de features **OGC API
> Features** (A4), RLS sur les données métier (A3), puis absorption de
> pg_featureserv.
>
> Date : 2026-07-09.
> Statut : design validé ; **SP-3a livré le 2026-07-10** (revue finale de
> branche passée). SP-3b/SP-3c à venir.
> Prérequis : SP-1 livré (items, `can()`, groupes, audit).

---

## Notes de revue SP-3a (2026-07-10) — à traiter en ouverture de SP-3b

1. **✅ Tranché (Tanguy, 2026-07-10) — `tenants.id` est un identifiant
   lisible IMMUABLE** (option A). Le défaut : la migration 0002 seed le
   tenant par défaut avec `id='default'` (littéral lisible) et backfille tout
   le cœur avec, mais `get_or_create_default_tenant` créait un **uuid** quand
   la ligne n'existait pas (bases de test) — le `SET LOCAL app.tenant_id =
   user.tenant_id` de SP-3b aurait rendu toutes les lignes invisibles sous
   RLS selon l'historique de la base. Décision : l'id du tenant est choisi à
   la création (= slug), immuable, lisible dans les données ouvertes
   (GeoParquet, exports — « le format est l'API ») ; le chemin code est
   aligné sur le seed (fix + test dans cette branche) ; **SP-3b peut poser
   `SET LOCAL app.tenant_id = user.tenant_id` tel quel**. Conséquences : un
   futur `create_tenant` reçoit un id lisible immuable explicite ; la PK
   globale `Collection.id` (slug) reste au backlog multi-tenant (passage en
   PK composite à l'activation).
2. Backlog SP-3b (issu des revues de tâches), traité pendant SP-3b sauf
   mention contraire :
   - test RLS sur UPDATE ✅
   - index sur `tenant_id` des tables métier ✅
   - qualification schéma du lookup enum et de `pg_get_serial_sequence` ✅
   - tests des gardes 0-PK / 2-géométries ✅
   - validation des doublons `group_id` dans `Sharing.groups` (défaut partagé
     avec le chemin items depuis SP-1 — corriger les deux) ✅
   - audit du script de seed (`actor_kind="system"`) et gestion
     d'`UnsupportedTable` dans le seed ✅
   - révocation des grants/policy au désenregistrement (hygiène)
     **(reste ouvert)**
3. Backlog SP-3c : `response_model` sur les endpoints collections/users (les
   types TS générés sont `unknown` sans ça) ; le job CI `api-types-drift` ne
   diffe pas `core/openapi.json` lui-même (seulement le `.d.ts` dérivé).

---

## 1. Contexte et périmètre

Aujourd'hui, les données métier PostGIS (`communes`, `points_interet`,
`incidents` — créées par `sql/init.sql`, hors de tout contrôle du cœur) sont
servies en **lecture seule** par deux services tiers connectés en rôle Postgres
unique `gis` : **Martin** (tuiles MVT) et **pg_featureserv** (GeoJSON). Le shell
les consomme via trois fonctions d'`itemClient.ts` : `listLayerSources()`
(catalogue Martin + collections featureserv), `featuresUrl()` et
`queryDataSource()` (les deux construisent
`{featureservUrl}/collections/{layer}/items.json?...`). Aucune écriture,
aucune permission, aucun schéma exposé.

SP-3 déplace cette surface dans le cœur :

- Module **`collections`** : registre des couches éditables (table PostGIS
  déclarée, schéma introspecté, permissions par collection).
- **`GET /collections/{id}/schema`** : l'introspection qui alimentera la
  génération de formulaires (A9 — le couple A4+A9 de la feuille de route).
- Module **`features`** : CRUD conforme **OGC API Features Part 1 + Part 4**
  (sous-ensemble utile, A4), validation par schéma, audit, **RLS** générée par
  collection (A3).
- **Bascule en fin de SP** : `queryDataSource`/`featuresUrl`/`listLayerSources`
  passent sur le cœur, **pg_featureserv sort du compose**.

**Hors périmètre.** Formulaires et widgets d'écriture (SP-4) ; expressions
(SP-5) ; upload/ingestion de fichiers (SP-6 — c'est lui qui *créera* des
tables ; SP-3 ne fait que *déclarer* des tables existantes) ; datasets
analytiques (A28, SP-14) ; reprojection CRS à la volée ; PATCH partiel de
feature ; transactions multi-features ; RLS pour Martin (documenté §5) ;
métadonnées STAC (SP-6, A7).

## 2. Décisions de cadrage

| Sujet | Décision |
|---|---|
| Découpage | **3 sous-phases livrables** : SP-3a registre+introspection (15–25 h), SP-3b CRUD features+RLS (25–40 h), SP-3c bascule shell+démolition (10–25 h). La lecture reste sur pg_featureserv jusqu'à 3c (parité atteinte). |
| Surface OGC (A4) | Part 1 : landing `/`, `/conformance`, `/collections`, `/collections/{cid}`, `/items` (GeoJSON, `limit`/`offset` + liens `next`/`prev`, `bbox`, filtres d'égalité `propriété=valeur`), `/items/{fid}`. Part 4 : `POST` (create), `PUT` (replace), `DELETE`. **Pas de PATCH ni de reprojection en v1** ; CRS déclaré : CRS84 (les données de démo sont en 4326). Conformité progressive — les classes annoncées dans `/conformance` sont celles réellement tenues. |
| Compat filtres | Les filtres d'égalité par paramètre d'URL reproduisent le comportement pg_featureserv **exactement** (le `DataSource.query` du builder passe ses clés en query string — contrat existant à ne pas casser). Les clés stats (`groupBy`, `split`, `agg`, `field`, `measures`) restent exclues côté shell. |
| **Rôle admin** (décision 2026-07-09) | Colonne **`users.is_admin`** (bool, défaut false), gérée par le cœur — cohérent avec A2 (« identité déléguée, autorisation maison »). **Bootstrap** : env `CORE_ADMIN_SUBS` (liste de `sub` OIDC séparés par des virgules), appliquée et rafraîchie à chaque `get_or_create_user` (promouvoir via l'env ne demande qu'un re-login). **Promotion par API** : `PATCH /users/{id} {isAdmin}` réservé aux admins, refus de rétrograder le dernier admin (409), audité (`user.promote`/`user.demote`). En mode `mock`, le user mock est admin (tests/e2e) ; les tests d'authz surchargent par des users non-admin. Périmètre : **registre + pleins droits (read/write/share) sur toutes les collections du tenant** — via la porte `can()` (paramètre `actor_is_admin`, courtcircuit pour `kind="collection"` uniquement). **Aucun droit supplémentaire sur items/configs/groupes** (testé explicitement — la sémantique SP-1 ne bouge pas). |
| Enregistrement | `POST /collections {tableName, title, …}` — **réservé aux admins** ; l'admin appelant devient **owner**. Garde-fous : la table doit exister dans le schéma `public`, avoir une PK simple, 0 ou 1 colonne géométrie ; les tables du cœur (`Base.metadata` + `alembic_version`) et les vues matérialisées sont refusées. Identifiants toujours quotés (jamais interpolés). `DELETE /collections/{cid}` (**admin**) **désenregistre sans dropper la table**. |
| Permissions | Table `collection_shares` (miroir d'`item_shares` : groupe × rôle viewer/editor) ; **`can()` reste l'unique porte**, généralisée : `ItemAccessFacts` devient `AccessFacts` (alias conservé) et le lookup de rôle est routé par un paramètre `kind: "item"\|"collection"`. Owner → tout ; **admin → tout sur les collections** ; editor → write ; viewer/public → read. Motif « 404 avant 403 » conservé (anti-énumération). |
| Accès anonyme | `is_public` sur la collection ⇒ lecture anonyme des features. Implémenté par une dépendance `get_current_user_optional` **sur les routes OGC elles-mêmes** (URLs OGC stables obligatoires — pas de duplication sous `/public`). |
| RLS (A3) | Générée **à l'enregistrement** de la collection : `ADD COLUMN IF NOT EXISTS tenant_id text NOT NULL DEFAULT 'default'`, `ENABLE ROW LEVEL SECURITY`, policies `USING`/`WITH CHECK (tenant_id = current_setting('app.tenant_id'))`. Le cœur exécute chaque transaction feature sous `SET LOCAL ROLE gis_rls` (rôle **non-propriétaire** créé par migration, `SELECT/INSERT/UPDATE/DELETE` accordés par collection) + `SET LOCAL app.tenant_id` — compatible PgBouncer en pool `transaction` (portée transactionnelle). `can()` reste l'enforcement premier ; la RLS est la défense en profondeur. **Martin (rôle `gis`, propriétaire) n'est pas couvert** — écart documenté et assumé par A3 (« Martin devra à terme passer par des vues ou un rôle par tenant »). |
| Introspection | **Vivante** (pg_catalog/information_schema à la requête, pas de cache persistant — pas de schéma périmé). Le registre ne stocke que la déclaration (+ `geometry_type`/`srid`/`pk_column` figés à l'enregistrement pour la validation). Types v1 **bornés** : text, numeric/int, bool, date, timestamptz, enum Postgres ; géométries (Multi)Point/LineString/Polygon. Colonne hors périmètre ⇒ exposée `"unsupported"`, en lecture seule, refusée à l'écriture. |
| Géométrie | SQL brut paramétré via SQLAlchemy `text()` : `ST_AsGeoJSON` en lecture, `ST_SetSRID(ST_GeomFromGeoJSON(:g), srid)` en écriture. **Pas de dépendance geoalchemy2.** |
| Identité des features | `fid` = valeur de la PK introspectée. `POST` sans PK fournie → générée par la base (serial/identity), `201 + Location` ; PK fournie en conflit → `409`. |
| `listLayerSources` | Devient : catalogue **Martin inchangé** (tuiles, appel direct conservé) + **`GET /collections` du cœur** (remplace featureserv). `LayerSource.service` : `"featureserv"` → `"core"`. Les cartes de dev pointant d'anciennes URLs ne sont pas migrées (A15 : re-seed). |
| Config shell | `VITE_FEATURESERV_URL` **supprimée** ; les URLs features dérivent de `VITE_CORE_URL`. |
| Audit | `collection.create/update/delete/share`, `feature.create/update/delete` (payload : `{collection, fid}`) — via `write_audit`, même transaction. Pas d'audit des lectures (volume). |
| Frontières (import-linter) | Deux nouveaux modules dans le contrat layers : `main > public > features > collections > configs > items > sharing > auth > audit > users > tenants`. `features` importe `collections` ; `collections` importe `sharing` (pour `can()`) ; ni `items` ni `configs` ne sont touchés par eux. |
| Tests | Trois étages : logique pure et registre sur **SQLite** (comme aujourd'hui) ; features + introspection + RLS sur **PostGIS réel** (marqueur `postgis`, `CORE_TEST_DATABASE_URL`, skippé localement sans DB, exécuté en CI qui a déjà un service PostGIS) — **nouvelle infrastructure de test, assumée**. E2E : les 4 specs sensibles (map-editor, data-widget, chart, actions) re-mockées vers les URLs du cœur. |

## 3. Modèle de données

```python
class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[str] = mapped_column(String, primary_key=True)   # slug, défaut = table_name
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String, nullable=False)   # unique (tenant_id, table_name)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    pk_column: Mapped[str] = mapped_column(String, nullable=False)
    geometry_column: Mapped[str | None]
    geometry_type: Mapped[str | None]      # "Point" | "MultiPolygon" | … (figé à l'enregistrement)
    srid: Mapped[int | None]
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    editable: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

class CollectionShare(Base):
    __tablename__ = "collection_shares"
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False)   # "viewer" | "editor"
```

Migration Alembic 0008 : colonne **`users.is_admin`** (bool, non-null, défaut
false), `collections`, `collection_shares`, **rôle Postgres `gis_rls`** (`CREATE ROLE … NOLOGIN`, `GRANT gis_rls TO gis` pour autoriser le
`SET LOCAL ROLE`) — la partie rôle est no-op en SQLite (guard sur le dialecte,
comme le pattern existant `init_db`). Les DDL par collection (tenant_id, RLS,
GRANT) ne sont **pas** dans la migration : ils sont exécutés par le module
`collections` à l'enregistrement (A3 : « politiques générées par collection »).

Réponse de `GET /collections/{cid}/schema` (le contrat consommé par SP-4) :

```json
{
  "collection": "incidents",
  "pk": "id",
  "geometry": { "column": "geom", "type": "Point", "srid": 4326 },
  "fields": [
    { "name": "titre", "type": "string", "required": true, "maxLength": 200 },
    { "name": "gravite", "type": "enum", "required": false, "values": ["faible", "moyenne", "haute"] },
    { "name": "date_incident", "type": "date", "required": false },
    { "name": "resolu", "type": "boolean", "required": false }
  ]
}
```

`required` = `NOT NULL` sans défaut ni identity ; `tenant_id` et la PK
générée n'apparaissent jamais dans `fields`.

## 4. Endpoints

```
# OGC API Features — Part 1 (lecture)
GET    /                                   → landing page (links: conformance, collections)
GET    /conformance                        → classes tenues (core, geojson, oas30 ; + Part 4)
GET    /collections                        → collections visibles (can read ; anonyme → is_public)
GET    /collections/{cid}                  → description OGC (extent spatial calculé, links items)
GET    /collections/{cid}/items            → FeatureCollection GeoJSON
                                             ?limit= (déf. 100, max 1000) &offset= &bbox=
                                             &<propriété>=<valeur>…  (+ liens next/prev)
GET    /collections/{cid}/items/{fid}      → Feature | 404

# OGC API Features — Part 4 (écriture ; requiert editor ou owner)
POST   /collections/{cid}/items            → 201 + Location (valide payload ↔ schéma)
PUT    /collections/{cid}/items/{fid}      → 204 (remplacement complet)
DELETE /collections/{cid}/items/{fid}      → 204

# Gestion du registre (hors spec OGC, même conventions que /items)
POST   /collections                        → enregistre une table existante (admin ; devient owner)
PATCH  /collections/{cid}                  → title, description, isPublic, editable (owner ou admin)
DELETE /collections/{cid}                  → désenregistre, la table survit (admin)
GET    /collections/{cid}/schema           → introspection (voir §3)
GET    /collections/{cid}/sharing          → comme /items/{id}/sharing (owner ou admin)
PUT    /collections/{cid}/sharing          → idem (groupes × viewer/editor)

# Administration des utilisateurs (rôle admin)
GET    /users?page=&pageSize=              → listing minimal (id, username, isAdmin)
PATCH  /users/{id}                         → { isAdmin } ; 409 si dernier admin rétrogradé
```

Contrainte de frontières : `users` est sous `auth` dans le contrat layers (il ne
peut pas importer `get_current_user`) — les routes `/users` vivent donc dans
`app/auth/routes.py`, qui importe déjà le repository users. Pas de nouveau
module pour deux endpoints.

Écritures features : payload = GeoJSON Feature (`properties` + `geometry`
optionnelle si la collection n'a pas de géométrie ou si la colonne est
nullable). Validation contre l'introspection : propriété inconnue → 400, type
incompatible → 400, valeur hors enum → 400, type géométrique ≠ colonne → 400 —
messages structurés (`{field, code, message}`) pour que SP-4 les affiche champ
par champ. Chaque mutation : `can(write)` → `SET LOCAL ROLE gis_rls` +
`SET LOCAL app.tenant_id` → SQL paramétré → `write_audit` — une transaction.

Les tables de démo `incidents` et `points_interet` sont déclarées comme
collections éditables (et `is_public=true`) par un **script de seed idempotent**
(`core/scripts/seed_demo.py`, invoqué dans la doc d'install) — pas par
migration : l'enregistrement exige un owner. Le script écrit en base
directement et prend `--owner <username>` (défaut : le premier admin trouvé,
créé depuis `CORE_ADMIN_SUBS` si nécessaire).

## 5. RLS — limites explicites

Ce que la RLS de SP-3 garantit : toute requête feature passée par le cœur est
bornée au tenant courant **même si un bug applicatif contourne `can()`** ; un
`INSERT/UPDATE` ne peut pas écrire dans un autre tenant (`WITH CHECK`).

Ce qu'elle ne garantit **pas** (assumé, A3) : Martin et TiTiler se connectent
en rôle `gis` (propriétaire → bypass RLS) ; les tuiles restent non filtrées.
Sans FORCE RLS (qu'on n'active pas, précisément pour ne pas casser Martin), le
chemin tuiles est inchangé. À réévaluer quand le multi-tenant s'activera
(différé §9 de la feuille de route).

## 6. Bascule shell (SP-3c)

- `itemClient.ts` : `fetchFeatureservSources` → `fetchCoreCollections`
  (`GET {coreUrl}/collections`, mapping vers `LayerSource{service:"core",
  kind:"feature", url:"{coreUrl}/collections/{id}/items"}`) ;
  `buildFeaturesUrl` pointe sur le cœur (mêmes règles : tri des clés, exclusion
  `STAT_KEYS`) ; en-tête `Bearer` déjà en place.
- `types.ts` : `LayerSource.service: "martin" | "core"` ;
  `DataSource.service` idem (valeur `"featureserv"` migrée à l'ouverture des
  configs — même mécanique de compat que les configs v1).
- `config.ts` / `App.tsx` / `.env*` : suppression de `VITE_FEATURESERV_URL`.
- E2E : `mocks.ts` remplace `**/collections*` featureserv par les routes du
  cœur ; les 4 specs sensibles ajustées, **les 13 restent vertes**.
- `docker-compose.yml` : **retrait du service `pg-featureserv`** (10 → 9
  services) ; README/CLAUDE.md mis à jour.

## 7. Gestion d'erreurs

- Collection inconnue **ou** non lisible → `404` (anti-énumération, comme
  items) ; écriture sans rôle editor → `403` ; anonyme sur collection non
  publique → `404`.
- Enregistrement / désenregistrement par un non-admin → `403` (la collection
  est listable, donc pas d'anti-énumération à préserver ici) ; `PATCH /users`
  par un non-admin → `403` ; rétrogradation du dernier admin → `409`.
- Enregistrement : table inexistante / vue matérialisée / table du cœur / PK
  absente ou composite / deux colonnes géométrie → `400` avec raison précise ;
  `table_name` déjà enregistré dans le tenant → `409`.
- Écriture feature : erreurs de validation en `400` structuré (voir §4) ;
  `fid` inconnu sur PUT/DELETE → `404` ; conflit PK sur POST → `409` ;
  violation de contrainte DB imprévue → `409` générique (jamais de SQL brut
  dans la réponse).
- Lecture : `limit` > 1000 → plafonné (pas d'erreur) ; `bbox` malformée → `400` ;
  propriété de filtre inconnue → `400` (pg_featureserv l'ignore ; on préfère
  échouer bruyamment — seule divergence de compat assumée, invisible pour le
  builder qui ne produit que des clés valides).

## 8. Stratégie de tests

- **Pur (pytest, sans DB)** : mapping introspection→schéma JSON ; validation
  payload↔schéma (matrice types × erreurs) ; construction SQL (identifiants
  quotés — test dédié avec noms hostiles `"communes; drop table--"`) ;
  génération des liens `next`/`prev`.
- **SQLite (pattern existant)** : CRUD du registre, `PATCH`, désenregistrement,
  sharing de collections, matrice `can()` généralisée (**admin**/owner/editor/
  viewer/stranger/anonyme × read/write/share — répliquée de
  `test_sharing_authorization.py`, isolation cross-tenant comprise) ; bootstrap
  admin depuis `CORE_ADMIN_SUBS` (promotion au token, rafraîchie) ; garde du
  dernier admin ; **test anti-régression : un admin n'a aucun droit
  supplémentaire sur items/configs** (la matrice SP-1 reste inchangée).
- **PostGIS réel (nouveau, marqueur `postgis`)** : enregistrement complet
  (tenant_id ajouté, RLS activée, policies créées, GRANT) ; CRUD features avec
  géométrie ; filtres/bbox/pagination ; **RLS effective** (une session forcée
  sur un mauvais `app.tenant_id` ne voit/n'écrit rien, y compris `can()`
  court-circuité) ; `SET LOCAL` sous PgBouncer vérifié dans le job CI (le
  service PostGIS existe déjà pour le job `migrations` ; PgBouncer ajouté au
  job ou validé par un spike court en ouverture de SP-3b).
- **Vitest shell** : `buildFeaturesUrl`/`fetchCoreCollections` adaptés.
- **E2E** : les 13 specs vertes sur les mocks re-câblés ; critère de 3c.
- **CI** : `api-types-drift` couvre automatiquement les nouveaux endpoints
  (OpenAPI→TS, A11).

## 9. Critères d'acceptation

- Un `editor` crée, modifie et supprime une feature (géométrie comprise) via
  l'API OGC ; un `viewer` reçoit 403 en écriture ; un anonyme lit une
  collection publique et reçoit 404 sur une privée ; un **admin** enregistre
  une collection et écrit dans toute collection du tenant, un non-admin reçoit
  403 sur `POST /collections`. *(matrice testée)*
- `GET /collections/{cid}/schema` sur `incidents` renvoie champs, types, enums
  et contrainte `required` exacts — le contrat que SP-4 consommera.
- Une feature créée via l'API est **immédiatement visible dans les tuiles
  Martin** (`get_incidents_tiles`) et dans le widget carte du builder.
- Chaque mutation (collection et feature) produit sa ligne `audit_log`.
- Une requête forgée avec le mauvais tenant est bloquée par la RLS même sans
  `can()` (test d'intégration dédié).
- Après SP-3c : `docker compose up` sans pg_featureserv ; les 13 specs E2E
  passent ; `queryDataSource`/`featuresUrl`/`listLayerSources` ne parlent
  qu'au cœur et à Martin ; zéro occurrence de `VITE_FEATURESERV_URL`.

## 10. Risques

- **Généricité du CRUD** (le risque n° 1 de la feuille de route) : bornée par
  la liste fermée de types v1 + `"unsupported"` en lecture seule — toute
  extension de type est un incrément ultérieur, pas un débordement de SP-3.
- **RLS × PgBouncer × rôles** : `SET LOCAL` est transactionnel donc sûr en
  pool `transaction`, mais c'est la première fois que le projet touche aux
  rôles Postgres — spike court en ouverture de SP-3b (créer le rôle, une
  policy, un test) avant d'industrialiser ; repli documenté : RLS différée à
  SP-6 avec `can()` seul (A3 resterait à amender explicitement).
- **Nouvelle infra de test PostGIS** : coût d'entrée réel (fixtures, CI) mais
  inévitable — la géométrie et la RLS ne se testent pas sur SQLite ; cette
  infra resservira à SP-6 (ingestion) et SP-11 (CDC).
- **Compat du contrat de filtres** : la bascule 3c change l'URL mais pas la
  sémantique ; les tests Vitest sur `buildFeaturesUrl` + les 4 E2E sensibles
  sont le filet.
- **Vues matérialisées `communes_z8/z12`** : non rafraîchies à l'écriture —
  sans objet en v1 (`communes` n'est pas déclarée éditable), noté pour SP-6.
