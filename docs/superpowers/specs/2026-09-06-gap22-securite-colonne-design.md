# GAP-22 — Sécurité au niveau colonne (masquage de champ sensible)

**Date** : 2026-09-06
**Statut** : spec, prête à devenir un plan
**Demandeur** : Tanguy (brainstorm préalable, décisions déjà tranchées — cf. §2)
**Documents liés** : `docs/revue/2026-09-04-analyse-gaps.md` (GAP-22, comparaison
explicite à Metabase « row & column security » et Superset « RLS
extensible »).

---

## 1. Contexte : ce que le code fait déjà

### 1.1 Trois mécanismes de lecture distincts, pas un seul

GAP-22 a été cadré par brainstorm en supposant que toute lecture de données
passe par le même rôle Postgres. **Faux** — vérifié en lisant le code, pas
supposé (CLAUDE.md piège n°3). Ce dépôt a **trois** chemins de lecture
totalement différents, et une protection efficace contre un « masquage
purement applicatif » (le risque que Décision 3 du brief vise explicitement)
doit couvrir les trois :

**(A) Lecture Postgres directe, sous RLS.** `core/app/features/rls.py::
rls_scope(session, tenant_id)` : `SET LOCAL ROLE gis_rls` (rôle non-
propriétaire, spec SP-3 §2/§5) + GUC transactionnel `app.tenant_id`. Chaque
table de collection est grantée `GRANT SELECT, INSERT, UPDATE, DELETE ON
public.<table> TO gis_rls` par `app/collections/ddl.py::apply_collection_ddl`
(chokepoint DDL unique, appelé par `register_collection`
(`app/collections/routes.py:73-75`) et par l'import (`app/ingestion/
importer.py:179`)). Consommateurs de `rls_scope` (recherche exhaustive
`grep -rn "rls_scope\|gis_rls" app --include="*.py"`, hors tests) :

| Fichier | Fonction | Lecture ou écriture |
|---|---|---|
| `app/features/routes.py:200` | `list_features` (GET `/collections/{id}/items`) | lecture |
| `app/features/routes.py:360` | `export_collection_items` (GET `/collections/{id}/export/items`, CSV/XLSX/GeoJSON/GPKG) | lecture |
| `app/features/routes.py:506` | `get_single_feature` (GET `/collections/{id}/items/{fid}`) | lecture |
| `app/features/routes.py:551` | `create_feature` (POST) | écriture |
| `app/features/routes.py:599` | `put_feature` (PUT) | écriture |
| `app/features/routes.py:633` | `remove_feature` (DELETE) | écriture |
| `app/features/tiles.py:122` (`get_collection_tile`, tuiles MVT `ST_AsMVT`) | | lecture |
| `app/mcp/tools/catalog.py:160` (`query_features`, tool MCP) | | lecture |
| `app/pipelines/runtime.py:729` (`writer.collection`, écrit les features produites par un pipeline) | | écriture |
| `app/appexport/freeze.py:43` (`freeze_config`, gèle un dataSource « features » en enregistrements statiques pour l'export « Statique ») | | lecture |
| `app/appexport/snapshot.py:59` (`write_snapshot`, écrit un instantané GeoParquet pour l'export « Autoporté ») | | lecture |

`app/collections/routes.py::get_extent_provider` pose aussi `SET LOCAL ROLE
gis_rls` inline (pas via `rls_scope`, import interdit par le contrat de
couches, cf. son commentaire) pour calculer l'emprise bbox d'une collection —
ne lit que la colonne géométrie, jamais une propriété métier : **hors
périmètre de ce chantier par construction**, aucun changement nécessaire.

**(B) Agrégats structurés DuckDB sur le lakehouse GeoParquet.**
`app/analytics/aggregate.py::run_collection_aggregate` (+ `_dedup_cte`,
`_valid_column_names`) — utilisé par `POST /collections/{id}/aggregate`
(`app/features/routes.py:252`), `POST /collections/{id}/export`
(export CSV/XLSX de l'agrégat, `app/features/routes.py:287`, même fonction
sous-jacente) et le tool MCP `run_analytics_query`
(`app/mcp/tools/analytics.py:108`). **Ce chemin ne pose JAMAIS `rls_scope` ni
aucun rôle Postgres** — il lit un GeoParquet partitionné
(`tenant_id=X/collection_id=Y/dt=*/*.parquet`, écrit par le worker CDC, SP-11)
via DuckDB, en dehors de toute session Postgres. L'isolation tenant vient du
chemin de fichier (`tenant_id=` dans le glob), la visibilité de collection de
`list_visible_collections`/`require_collection_read` (contrôle au niveau
collection, jamais colonne). `_validate_fields` rejette déjà un `groupBy`/
`field`/mesure hors de `_valid_column_names(table_info)` — **c'est le point
d'ancrage naturel du masquage pour ce chemin** (§3.5).

**(C) SQL Lab — SQL arbitraire sur le même lakehouse DuckDB.**
`app/analytics/sql_sandbox.py::run_analyst_sql` (route `POST /analytics/sql`,
`app/features/routes.py:432`, gardée par `Privilege.ANALYTICS_SQL_LAB_ACCESS`).
Même absence totale de Postgres/`rls_scope` que (B) — la frontière de
sécurité documentée dans le module est `enable_external_access=false` +
`lock_configuration=true` côté DuckDB (isolation *processus*, pas *colonne*).
`_materialize` matérialise chaque collection référencée en `CREATE TEMP TABLE
... AS ... SELECT * FROM live` — **`SELECT *`, pas une liste explicite** :
tout ce qui existe dans le GeoParquet (y compris les colonnes de plomberie
CDC `_lsn`/`_op`/`_seq`, un défaut préexistant sans rapport direct avec ce
GAP mais que le correctif de masquage supprime en même temps, cf. §3.5.2)
est visible à l'analyste. C'est le chemin que Décision 3 du brief vise
explicitement (« masquage purement applicatif ne protégerait jamais un
`SELECT champ_sensible FROM ...` tapé à la main ») — **et il ne peut PAS
être fermé par un choix de rôle Postgres, puisqu'aucun rôle Postgres
n'intervient dans ce chemin.** Le mécanisme retenu par le brief (§3.3 du
prompt de cadrage : « SQL Lab doit aussi choisir son rôle Postgres sous-
jacent ») **ne s'applique donc pas tel quel** — corrigé par cette spec en
§2.3 et §3.5.

### 1.2 Rôle Postgres `gis_rls` et sémantique GRANT/REVOKE par colonne

`app/collections/ddl.py::apply_collection_ddl` grante aujourd'hui `gis_rls`
au niveau **table** (`GRANT SELECT, INSERT, UPDATE, DELETE ON public.<t> TO
gis_rls`). C'est délibéré et reste inchangé pour `gis_rls` — décision 1 du
brief ne demande aucune granularité par colonne pour un porteur du privilège.

Point technique vérifié (documentation Postgres, comportement des ACL) qui
détermine toute l'architecture du nouveau rôle masqué (§3.3) : un `GRANT
SELECT ON table TO role` couvre la table entière, **colonnes futures
comprises**, et un `REVOKE SELECT (colonne) ON table FROM role` exécuté
*après* n'a **aucun effet tant que le GRANT table-level tient** — Postgres
évalue « le rôle a-t-il SELECT sur la table (oui) OU sur la colonne
(non-pertinent) » et autorise dans les deux cas. **Le nouveau rôle
`gis_rls_masked` ne doit donc JAMAIS recevoir de `GRANT SELECT` au niveau
table** — uniquement des `GRANT SELECT (col1, col2, ...)` par colonne,
recalculés en entier à chaque changement de `sensitive_fields` (§3.3). Point
à re-vérifier empiriquement contre un vrai Postgres à l'exécution du plan
(CLAUDE.md piège n°3) — en particulier si l'évaluation de la policy RLS
elle-même (`USING (tenant_id = current_setting(...))`) exige que l'exécutant
ait SELECT sur `tenant_id` : cette spec grante `tenant_id` sans condition
(jamais marquable sensible, §3.2) précisément pour ne jamais dépendre de la
réponse à cette question.

### 1.3 Privilèges et patron de migration à réutiliser

`app/roles/privileges.py` : 19 valeurs `Privilege` (`StrEnum`), convention
`domaine.action` (ex. `DATA_VIEW = "data.view"`, `DATA_MANAGE =
"data.manage"`). `PRIVILEGE_METADATA` associe domaine shell + clé i18n
(jamais de libellé français côté cœur, A12). `BUILT_IN_ROLE_PRIVILEGES["admin"]
= [p for p in ALL_PRIVILEGE_VALUES if p != Privilege.COMPLIANCE_MANAGE.value]`
— **toute nouvelle valeur d'enum rejoint automatiquement l'Administrateur**
sauf exclusion explicite (patron posé par SP-58 pour `compliance.manage`).
Aucune raison de l'exclure ici : voir un champ sensible n'est pas une action
destructrice, contrairement à la purge de tenant qui justifiait
l'exclusion de SP-58.

`app/roles/guards.py` : `has_privilege(session, user, privilege) -> bool`,
`require_privilege`, `require_any_privilege` (SP-47, OR de plusieurs
privilèges). Aucun changement nécessaire à ce module — le nouveau privilège
s'utilise avec les fonctions existantes.

`Collection.attachment_fields` (`app/collections/models.py:51-53`,
`Mapped[list]`, `JSON`, `default=list`, `server_default="[]"`) est le patron
exact à reproduire pour `sensitive_fields` : même type, même défaut, même
mécanique de migration additive (`alembic/versions/0032_attachments.py:40-43`,
`op.add_column("collections", sa.Column("attachment_fields", sa.JSON(),
nullable=False, server_default="[]"))`).

`alembic/versions/0008_collections_admin.py:58-65` est le patron exact pour
la création idempotente du rôle Postgres `gis_rls` (`DO $$ BEGIN IF NOT
EXISTS (...) THEN CREATE ROLE gis_rls NOLOGIN; END IF; END $$;` + `GRANT
gis_rls TO current_user`), avec son `downgrade()` symétrique (`DROP OWNED
BY`/`DROP ROLE IF EXISTS`) — à reproduire à l'identique pour `gis_rls_masked`.

Tête de migration constatée à l'écriture de cette spec : `0040`
(`alembic/versions/0040_share_links.py`) — **à revérifier au moment de
l'exécution** (`ls core/alembic/versions | sort | tail`, ne pas supposer,
CLAUDE.md piège n°3), cette spec suppose `0041` par la suite.

### 1.4 Édition de collection : chokepoint existant à réutiliser

`app/collections/routes.py::patch_collection` (`PATCH /collections/{id}`,
ligne 522) est le chokepoint unique déjà en place pour éditer les métadonnées
d'une collection, y compris `attachmentFields` (schéma proche : liste
validée sans doublon au niveau Pydantic
`CollectionPatch._reject_duplicate_attachment_field_keys`, puis validée
contre les colonnes réelles au niveau route
`_reject_attachment_field_collisions`, qui a besoin de l'introspecteur donc
ne peut pas vivre dans le schéma Pydantic seul). `sensitiveFields` suit
exactement ce même schéma à deux étages (§3.2), mais avec une validation
**inversée** : `attachmentFields` doit **éviter** de collider avec une
colonne réelle (ce sont des champs virtuels) ; `sensitiveFields` doit **être
strictement composé** de colonnes réelles (`{c.name for c in
info.columns} - {pk, tenant_id, geometry}` — exactement l'ensemble que
`app/collections/schema_json.py::table_info_to_schema` utilise déjà pour
lister les champs d'une collection, lignes 10-12).

`_collection_json` (`app/collections/routes.py:153-178`) construit le JSON
retourné au shell pour une collection — porte déjà `attachmentFields`,
`license`, etc. **Chemin de lecture à ne pas oublier (CLAUDE.md piège n°5)** :
`sensitiveFields` doit y être ajouté, sinon la valeur ne survit pas à un
rechargement de l'écran d'administration.

Côté shell, le patron à reproduire est `shell/src/shell/EditCollectionPanel.tsx`
(édition de `attachmentFields`, liste key/label) et `shell/src/api/types.ts`
(`CollectionRead.attachmentFields`, `CollectionUpdate.attachmentFields?`) +
`shell/src/api/domains/collectionsAdmin.ts`/`collectionsAdmin.hooks.ts`
(domaine `ItemClient` qui appelle `PATCH /collections/{id}`, découpage
SP-43).

### 1.5 Deux chemins de lecture supplémentaires découverts pendant l'exploration, hors périmètre explicite

Le prompt de cadrage demandait de vérifier si un chemin de lecture contourne
`rls_scope()` « d'une manière ou d'une autre » pour les exports/MCP — la
recherche exhaustive en a trouvé **deux de plus**, non mentionnés par le
brainstorm, tous deux du même type que (B)/(C) (DuckDB sur GeoParquet, sans
notion de colonne sensible) :

- **`app/pipelines/runtime.py::_read_collection`/`_materialize_reader`**
  (`reader.collection`, registre `READERS`, `app/pipelines/registries.py:47`)
  — un pipeline no-code peut lire n'importe quelle collection source dans un
  DAG de transformation, puis ré-exporter ses colonnes (y compris
  potentiellement sensibles) vers une autre collection (`writer.collection`)
  ou un export sec (`writer.export`), **sans aucune vérification de
  privilège au niveau colonne** — `_materialize_reader` construit déjà une
  liste explicite de colonnes (pas `SELECT *`, contrairement à (C)) à partir
  de `table_info.columns`, mais sans filtrer sur `sensitive_fields`. Le
  paramètre `user: User` existe déjà dans la signature de `_read_collection`
  mais n'est utilisé pour aucune vérification de ce type aujourd'hui.
- **`app/appexport/freeze.py::freeze_config`** (export « Statique », dataSource
  gelé en enregistrements JSON embarqués dans la config) et
  **`app/appexport/snapshot.py::write_snapshot`** (export « Autoporté »,
  instantané GeoParquet) — les deux appellent `rls_scope(session,
  tenant_id)` mais **sans aucun utilisateur en paramètre** (seulement
  `tenant_id`), donc rien à threader pour choisir `gis_rls_masked` sans
  changer leur signature et celle de leurs appelants (jobs `appexport`).

**Décision de cette spec (§2.2)** : les deux restent explicitement **hors
périmètre**, documentés ici plutôt que silencieusement absorbés (CLAUDE.md
piège n°3/n°12). Les inclure changerait la nature de ce chantier (toucher
`app/pipelines/registries.py` + les jobs `appexport` + leur file
`procrastinate`, bien au-delà des deux chokepoints que le brief a
explicitement demandés) et risquerait de retarder la fermeture de GAP-22 sur
son périmètre réel. Un futur GAP/REV distinct devra couvrir : « un pipeline
peut faire fuir une colonne sensible d'une collection source vers une
collection/un export cible » et « un export Statique/Autoporté embarque
toutes les colonnes, y compris sensibles, indépendamment du privilège du
déclencheur ».

---

## 2. Décisions

### 2.1 Décision 1 — un privilège global unique

`Privilege.DATA_VIEW_SENSITIVE = "data.view_sensitive"` (20e valeur de
l'enum, domaine shell `"data"` — déjà existant, pas de nouveau `DomainId` —
clé i18n `roles.privilege.dataViewSensitive`). Porté ou non par
l'utilisateur ; s'il l'est, il voit tous les champs sensibles de toutes les
collections du tenant. Pas de granularité par collection/rôle — écartée
explicitement par Tanguy (coût d'administration/audit). Rejoint
automatiquement `BUILT_IN_ROLE_PRIVILEGES["admin"]` (§1.3) ; aucun des trois
autres rôles prédéfinis (Créateur/Analyste/Lecteur) ne le porte par défaut.

### 2.2 Décision 2 — marquage uniforme par collection

`Collection.sensitive_fields: Mapped[list] = mapped_column(JSON,
default=list, nullable=False, server_default="[]")` — mêmes noms de colonnes
SQL réelles que celles introspectées (jamais un champ `attachment`, jamais
`pk_column`/`geometry_column`/`tenant_id`). Édité depuis `PATCH
/collections/{id}` (§1.4), affiché/édité dans `EditCollectionPanel.tsx` à
côté d'`attachmentFields`.

### 2.3 Décision 3 (corrigée) — le mécanisme réel par chemin de lecture

Le brief supposait un mécanisme unique (« SQL Lab bascule de rôle Postgres
»). Le code réel (§1.1) exige **deux** mécanismes distincts, un par famille
de chemin de lecture :

- **Chemin (A), Postgres/RLS** : nouveau rôle non-propriétaire
  `gis_rls_masked`, choisi par `rls_scope` à la place de `gis_rls` quand
  l'utilisateur ne porte pas `DATA_VIEW_SENSITIVE` — colonnes sensibles
  jamais grantées à ce rôle (§3.3/§3.4).
- **Chemins (B)/(C), DuckDB/GeoParquet (agrégats structurés + SQL Lab)** :
  aucun rôle Postgres n'existe sur ce chemin — le masquage se fait en
  excluant les colonnes sensibles de la liste de colonnes **matérialisée**
  par DuckDB (`_dedup_cte`/`_materialize`), jamais par un choix de rôle
  (§3.5). C'est le mécanisme qui répond réellement à l'exigence du brief
  « SQL Lab DOIT être couvert, un masquage applicatif ne suffit pas » : la
  colonne n'existe tout simplement plus dans la table temporaire DuckDB
  contre laquelle l'analyste exécute son SQL arbitraire — aucune requête,
  aussi habile soit-elle, ne peut la lire.

---

## 3. Design

### 3.1 Nouveau privilège (`app/roles/privileges.py`)

```python
class Privilege(StrEnum):
    ...
    DATA_VIEW_SENSITIVE = "data.view_sensitive"  # 20e valeur, après COMPLIANCE_MANAGE
```

`PRIVILEGE_METADATA[Privilege.DATA_VIEW_SENSITIVE] = ("data",
"roles.privilege.dataViewSensitive")`. Aucun `BUILT_IN_ROLE_PRIVILEGES` à
modifier explicitement (rejoint `"admin"` automatiquement via
`list(ALL_PRIVILEGE_VALUES)` moins l'exclusion `COMPLIANCE_MANAGE`
existante — vérifier qu'aucune exclusion supplémentaire n'est nécessaire,
elle ne l'est pas ici : voir un champ n'est pas une action irréversible).

### 3.2 `Collection.sensitive_fields` + validation (couche `app.collections`)

**Modèle** (`app/collections/models.py`), immédiatement après
`attachment_fields` :

```python
sensitive_fields: Mapped[list] = mapped_column(
    JSON, default=list, nullable=False, server_default="[]"
)
```

**Migration** (`alembic/versions/0041_sensitive_fields.py`, numéro à
reconfirmer, §1.3) :

```python
def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("sensitive_fields", sa.JSON(), nullable=False, server_default="[]"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN IF NOT EXISTS "
            "(SELECT FROM pg_roles WHERE rolname = 'gis_rls_masked') "
            "THEN CREATE ROLE gis_rls_masked NOLOGIN; END IF; END $$;"
        )
        op.execute("GRANT gis_rls_masked TO current_user")
        # Backfill : toute collection déjà enregistrée avant cette migration a
        # `sensitive_fields = []` par construction (colonne neuve) — le rôle
        # masqué doit donc voir TOUTES ses colonnes réelles dès l'activation,
        # sinon la première requête sous gis_rls_masked contre une collection
        # préexistante échoue en "permission denied for table" (aucune
        # colonne grantée). Recalcule dynamiquement (nom de table/colonnes
        # inconnus statiquement) via un bloc PL/pgSQL, même patron que
        # sync_masked_role_grants (§3.3) mais en SQL pur (une migration
        # n'importe pas app.collections.ddl).
        op.execute(
            """
            DO $$
            DECLARE
                col RECORD;
                colname text;
            BEGIN
                FOR col IN SELECT table_name FROM collections LOOP
                    FOR colname IN
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = col.table_name
                    LOOP
                        EXECUTE format(
                            'GRANT SELECT (%I) ON public.%I TO gis_rls_masked',
                            colname, col.table_name
                        );
                    END LOOP;
                END LOOP;
            END $$;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP OWNED BY gis_rls_masked")
        op.execute("DROP ROLE IF EXISTS gis_rls_masked")
    op.drop_column("collections", "sensitive_fields")
```

Testée dans les deux sens sur base non vide (CLAUDE.md piège n°8) — au
moins une collection déjà enregistrée avec des lignes, pour vérifier
concrètement que le backfill grante bien toutes ses colonnes.

**Validation Pydantic** (`app/collections/schemas.py::CollectionPatch`) :
nouveau champ `sensitiveFields: list[str] | None = None` + validateur
`_reject_duplicate_sensitive_field_names` (même forme que
`_reject_duplicate_attachment_field_keys`, sans DB).

**Validation DB** (`app/collections/routes.py`, nouvelle fonction
`_reject_invalid_sensitive_fields(session, col, sensitive_fields,
introspect)`, appelée depuis `patch_collection` si `body.sensitiveFields is
not None`, même emplacement que `_reject_attachment_field_collisions`) :

```python
def _reject_invalid_sensitive_fields(session, col, sensitive_fields, introspect):
    if not sensitive_fields:
        return
    try:
        info = introspect(session, col.table_name)
    except (TableNotFound, UnsupportedTable):
        return  # même discipline que _reject_attachment_field_collisions
    valid = {c.name for c in info.columns} - {info.pk_column, "tenant_id", info.geometry_column}
    unknown = sorted(set(sensitive_fields) - valid)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"sensitiveFields must be real, non-reserved column(s): {', '.join(unknown)}",
        )
```

`patch_collection` : après validation, si `body.sensitiveFields is not
None`, appelle `sync_masked_role_grants(session, col.table_name,
body.sensitiveFields)` (§3.3) **avant** d'affecter `col.sensitive_fields =
body.sensitiveFields` (ordre sans conséquence pratique ici — pas de
contrainte d'ordre transactionnelle entre le GRANT/REVOKE DDL et l'UPDATE
ORM, tous deux dans la même transaction — mais gardé pour lisibilité :
appliquer d'abord l'effet Postgres réel, puis refléter l'intention côté
modèle).

`_collection_json` (§1.4) : ajoute `"sensitiveFields": col.sensitive_fields`.

`app/collections/schema_json.py::table_info_to_schema` : **inchangé** —
décision explicite (§4, hors périmètre) de ne pas masquer la découverte de
schéma (noms/types de champs), seulement les valeurs.

### 3.3 Rôle `gis_rls_masked` et GRANT/REVOKE par colonne (`app/collections/ddl.py`)

Nouvelle fonction, exportée aux côtés d'`apply_collection_ddl` :

```python
def _all_real_columns(session: Session, table_name: str) -> list[str]:
    return list(
        session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": table_name},
        ).scalars()
    )


def sync_masked_role_grants(
    session: Session, table_name: str, sensitive_fields: list[str]
) -> None:
    """(Re)calcule en entier les GRANT/REVOKE SELECT par colonne pour
    gis_rls_masked (GAP-22) — jamais un GRANT SELECT au niveau table (§1.2 :
    un REVOKE(colonne) ultérieur serait alors sans effet). Idempotent :
    recalcule l'état complet à partir de `sensitive_fields`, ne diffuse pas
    un delta contre un état précédent inconnu de l'appelant."""
    t = quote_ident(session, table_name)
    all_cols = _all_real_columns(session, table_name)
    sensitive = set(sensitive_fields) & set(all_cols)
    visible = [c for c in all_cols if c not in sensitive]
    if visible:
        cols_sql = ", ".join(quote_ident(session, c) for c in visible)
        session.execute(text(f"GRANT SELECT ({cols_sql}) ON public.{t} TO gis_rls_masked"))
    if sensitive:
        cols_sql = ", ".join(quote_ident(session, c) for c in sorted(sensitive))
        session.execute(text(f"REVOKE SELECT ({cols_sql}) ON public.{t} FROM gis_rls_masked"))
```

`apply_collection_ddl` (registration/ingestion, `sensitive_fields` toujours
`[]` à ce stade puisque la `Collection` vient d'être créée) gagne un appel
`sync_masked_role_grants(session, table_name, [])` juste après le `GRANT`
existant à `gis_rls` — grante donc SELECT sur toutes les colonnes réelles à
`gis_rls_masked`, rien à révoquer. `sync_masked_role_grants` est ensuite
ré-appelée par `patch_collection` (§3.2) à chaque changement de
`sensitiveFields`.

`gis_rls_masked` ne reçoit **jamais** de GRANT sur les séquences (pas
d'INSERT depuis ce rôle, cf. §3.4) ni de GRANT INSERT/UPDATE/DELETE.

### 3.4 `rls_scope` : signature étendue, sans casser les appelants existants

`app/features/rls.py` :

```python
@contextmanager
def rls_scope(session: Session, tenant_id: str, *, masked: bool = False):
    role = "gis_rls_masked" if masked else "gis_rls"
    session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_id})
    session.execute(text(f"SET LOCAL ROLE {role}"))
    try:
        yield
    finally:
        ...  # inchangé
```

`role` interpolé (pas de paramètre lié possible sur `SET LOCAL ROLE`, comme
le `_quote_literal` déjà documenté dans `ddl.py` pour une raison identique)
mais **jamais** dérivé d'une entrée utilisateur — seulement de la constante
`"gis_rls_masked"` ou `"gis_rls"` choisie en Python, aucune injection
possible.

`masked` est **mot-clé uniquement, défaut `False`** — préserve à l'identique
les **7 appelants existants qui ne le passent pas** : les 3 routes
d'écriture de `features/routes.py` (masquage sans objet pour une écriture,
décision explicite §4), `pipelines/runtime.py:729` (écriture), et les 3
chemins hors périmètre §1.5 (`appexport/freeze.py`, `appexport/snapshot.py`
— restent délibérément non masqués, cf. §1.5). Zéro régression sur ces
7 sites, zéro changement de code nécessaire pour eux.

`app/features/routes.py::null_rls_scope` (override SQLite) gagne le même
paramètre, ignoré :

```python
@contextmanager
def null_rls_scope(session, tenant_id, *, masked: bool = False):
    yield
```

**Nouvelle dépendance FastAPI**, capturant l'utilisateur (optionnel — les
routes concernées acceptent déjà un lecteur anonyme sur collection
publique) :

```python
def get_masked_for_user(
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> bool:
    if user is None:
        return True  # jamais faire confiance à un lecteur anonyme pour du sensible
    return not has_privilege(session, user, Privilege.DATA_VIEW_SENSITIVE.value)
```

Câblée sur les **4 sites de lecture** identifiés en §1.1(A) :

- `list_features` (`features/routes.py:189`) : `masked: bool =
  Depends(get_masked_for_user)`, puis `with rls(session, col.tenant_id,
  masked=masked):`.
- `export_collection_items` (`features/routes.py:350`) : idem — bien que
  cette route dépende de `get_current_user` (obligatoire) pour son propre
  paramètre `user`, `get_masked_for_user` peut dépendre séparément de
  `get_current_user_optional` (FastAPI résout et met en cache chaque
  dépendance par défaut ; un appel supplémentaire de décodage JWT est
  négligeable sur une route d'export, déjà coûteuse en pagination).
- `get_single_feature` (`features/routes.py:499`) : idem.
- `get_collection_tile` (`features/tiles.py:114`) : idem — importe
  `get_masked_for_user` depuis `app.features.routes`, comme il importe déjà
  `get_rls_scope` de là.

Les 3 routes d'écriture de `features/routes.py` (`create_feature`,
`put_feature`, `remove_feature`) **ne changent pas** — `masked` reste à son
défaut `False`, exactement le comportement actuel.

`app/mcp/tools/catalog.py::query_features` (pas de FastAPI `Depends`, appel
manuel) :

```python
masked = user is None or not has_privilege(session, user, Privilege.DATA_VIEW_SENSITIVE.value)
with rls_scope(session, col.tenant_id, masked=masked):
    ...
```

(`user` y est toujours résolu via `resolve_actor`, jamais `None` en
pratique dans ce module — la clause `user is None` est une défense en
profondeur, cohérente avec `get_masked_for_user`.)

### 3.5 Masquage DuckDB (chemins B/C — `app/analytics/*`)

`app.analytics` est **au plus bas du contrat de couches**
(`pyproject.toml`, confirmé §1.1) : il ne peut importer ni `app.roles` ni
`app.features`. Les fonctions de ce module restent donc **agnostiques du
privilège** — elles reçoivent un ensemble de noms de colonnes déjà résolu
par l'appelant (qui, lui, est dans une couche où `app.roles` est
accessible), jamais un objet `User`/`Privilege`.

**3.5.1 — Agrégats structurés (`app/analytics/aggregate.py`)**

```python
def _valid_column_names(table_info: TableInfo, masked_fields: frozenset[str] = frozenset()) -> set[str]:
    names = {c.name for c in table_info.columns} | {table_info.pk_column}
    if table_info.geometry_column:
        names.add(table_info.geometry_column)
    return names - _EXCLUDED_PROPERTIES - masked_fields
```

`_validate_fields(request, table_info, masked_fields=frozenset())` relaie
`masked_fields` à `_valid_column_names`. `run_collection_aggregate(conn, *,
base_uri, tenant_id, collection_id, table_info, request, masked_fields:
frozenset[str] = frozenset())` relaie à `_validate_fields` — **une
référence à un champ sensible dans `groupBy`/`field`/une mesure devient un
`UnknownAggregateField`, exactement comme un nom de champ qui n'existe
pas.** Conforme à la décision « champ visible en entier ou totalement
absent, jamais partiel » (§4) : du point de vue de l'agrégat structuré, un
champ masqué n'existe pas.

Trois appelants à mettre à jour, chacun calcule
`masked_fields = frozenset() if has_privilege(session, user,
Privilege.DATA_VIEW_SENSITIVE.value) else frozenset(col.sensitive_fields)`
puis le relaie :

- `aggregate_features` (`POST /collections/{id}/aggregate`,
  `features/routes.py:252`).
- `export_collection_aggregate` (`POST /collections/{id}/export`,
  `features/routes.py:287` — même fonction sous-jacente, même garde).
- `run_analytics_query` (tool MCP, `mcp/tools/analytics.py:108`) — nouvel
  import `from app.roles.guards import has_privilege` +
  `from app.roles.privileges import Privilege` dans ce fichier (`app.mcp`
  est au-dessus d'`app.roles` dans le contrat, déjà le cas dans
  `mcp/tools/catalog.py` — aucune exemption nouvelle attendue, à vérifier
  par `lint-imports` à l'exécution).

**3.5.2 — SQL Lab (`app/analytics/sql_sandbox.py`)**

`_materialize` construit aujourd'hui `CREATE TEMP TABLE {name} AS {cte}
SELECT * FROM live` — remplacé par une liste explicite de colonnes,
excluant à la fois les colonnes réservées déjà exclues ailleurs
(`tenant_id`, cf. `_EXCLUDED_PROPERTIES` d'`aggregate.py`, réutilisé par
import) et les colonnes de `masked_fields` :

```python
def _materialize(
    conn: duckdb.DuckDBPyConnection,
    *,
    name: str,
    table_info: TableInfo,
    base_uri: str,
    tenant_id: str,
    masked_fields: frozenset[str] = frozenset(),
) -> None:
    if not _has_any_file(conn, base_uri, tenant_id, name):
        raise SqlSandboxError(f"collection '{name}' has no data yet")
    cte = _dedup_cte(conn, table_info, base_uri, tenant_id, name)
    reserved = {table_info.pk_column, "tenant_id"} | masked_fields
    cols = [table_info.pk_column] + [
        c.name for c in table_info.columns if c.name not in reserved
    ]
    if table_info.geometry_column and table_info.geometry_column not in reserved:
        cols.append(table_info.geometry_column)
    select_list = ", ".join(_qi(c) for c in cols)
    conn.execute(f"CREATE TEMP TABLE {_qi(name)} AS {cte} SELECT {select_list} FROM live")
```

**Effet de bord positif documenté, pas le but premier de ce chantier** : les
colonnes de plomberie CDC (`_lsn`/`_op`/`_seq`) et les colonnes virtuelles de
hive-partitioning (`tenant_id=`/`collection_id=`/`dt=`, exposées par
`read_parquet(hive_partitioning=true)`) disparaissent aussi de la table
temporaire exposée à l'analyste SQL Lab — un défaut préexistant sans rapport
direct avec GAP-22, fermé en même temps par construction (même motif que
`_materialize_reader`, déjà correct sur ce point, `app/pipelines/runtime.py:
180-193`). À couvrir par un test dédié, falsifié (§5).

`run_analyst_sql(conn, *, sql, allowed, base_uri, tenant_id,
masked_fields_by_collection: dict[str, frozenset[str]] | None = None)` —
relaie `(masked_fields_by_collection or {}).get(name, frozenset())` à chaque
appel de `_materialize` dans sa boucle de matérialisation.

`analytics_sql` (`features/routes.py:432`) : construit
`masked_fields_by_collection` en même temps que `allowed`, un privilège
lu une seule fois pour toute la requête :

```python
sensitive_ok = has_privilege(session, user, Privilege.DATA_VIEW_SENSITIVE.value)
allowed: dict[str, TableInfo] = {}
masked_fields_by_collection: dict[str, frozenset[str]] = {}
for col in cols:
    try:
        allowed[col.id] = introspect(session, col.table_name)
    except TableNotFound:
        continue
    masked_fields_by_collection[col.id] = (
        frozenset() if sensitive_ok else frozenset(col.sensitive_fields)
    )
```

### 3.6 Shell

- `shell/src/api/types.ts` : `CollectionRead.sensitiveFields: string[]`,
  `CollectionUpdate.sensitiveFields?: string[]`.
- `shell/src/shell/EditCollectionPanel.tsx` : section « Champs sensibles »,
  à côté d'« Pièces jointes » — une liste de cases à cocher sur les champs
  réels de la collection (source : `GET /collections/{id}/schema`, déjà
  chargé pour l'éditeur de pièces jointes, `table_info_to_schema` inchangé
  §3.2), jamais une saisie libre de nom de colonne (élimine toute la classe
  d'erreur que `_reject_invalid_sensitive_fields` gère déjà côté serveur,
  mais une UI qui ne peut pas soumettre une valeur invalide est un meilleur
  filet que la validation serveur seule).
- `shell/src/api/domains/collectionsAdmin.ts`/`.hooks.ts` : relaient
  `sensitiveFields` dans le corps de `PATCH /collections/{id}`, même patron
  qu'`attachmentFields`.
- `shell/src/auth/capabilities.ts` : aucun changement — domaine `"data"`
  déjà défini, `DATA_VIEW_SENSITIVE` n'a pas besoin d'un `DomainId` propre
  (décision symétrique à `COMPLIANCE_MANAGE`/domaine `"settings"`, SP-58).
- `shell/src/i18n/catalog.fr.ts` + `shell/src/i18n/
  rolePrivilegeCatalog.test.ts` (`CORE_PRIVILEGE_LABEL_KEYS`, miroir figé de
  `PRIVILEGE_METADATA`) : nouvelle entrée `roles.privilege.dataViewSensitive`
  dans les deux — piège déjà documenté (CLAUDE.md SP-47 : « 4 fixtures
  miroir du rôle Créateur trouvées », même classe de dérive appliquée ici à
  un miroir de catalogue de privilèges plutôt qu'à un rôle).
- `shell/src/pages/RolesAdminPage.tsx` (ou équivalent, création/édition de
  rôle sur mesure) : aucun changement de code attendu — le catalogue de
  privilèges y est déjà rendu dynamiquement depuis `GET /roles/{id}`,
  vérifié par le test miroir ci-dessus plutôt que recodé.

---

## 4. Hors périmètre (explicite)

- **Granularité par collection/rôle** — écartée par Tanguy (§2.1) : un seul
  privilège global, jamais un « champ sensible pour le rôle Analyste mais
  pas pour le rôle Créateur ».
- **Masquage partiel/anonymisation d'une valeur** (troncature, hachage,
  généralisation type k-anonymat) — un champ sensible est présent en entier
  ou totalement absent, jamais une version dégradée.
- **UI de simulation « voir comme un rôle sans le privilège »** — suivi
  possible, non demandé ici.
- **Masquage en écriture** (`create_feature`/`put_feature`/`writer.collection`
  d'un pipeline) — un utilisateur sans `DATA_VIEW_SENSITIVE` mais avec
  `data.manage` peut toujours écrire une valeur dans un champ sensible qu'il
  ne peut pas relire ensuite. Cohérent avec la formulation du brief
  (« masquage de champ », toujours au sens lecture, comparaison à Metabase/
  Superset qui sont des outils de *consultation*) — mais **limite connue à
  documenter explicitement dans l'entrée `### Livré`** de CLAUDE.md à la
  clôture, pas un oubli silencieux.
- **Masquage de la découverte de schéma** (`GET /collections/{id}/schema`,
  `explain_dataset` MCP) — les noms/types de champs restent visibles à tout
  lecteur de la collection, y compris les champs marqués sensibles ; seule
  la **valeur** est masquée. Décision motivée en §1.4/§3.2 : masquer aussi
  le schéma créerait une dépendance circulaire pour l'écran d'administration
  lui-même (un admin porteur d'`admin.collections.manage` mais pas de
  `data.view_sensitive` doit pouvoir voir la liste des champs pour choisir
  lesquels marquer sensibles).
- **`app/pipelines/runtime.py::_read_collection`/`_materialize_reader`**
  (lecture d'une collection par un pipeline no-code) — bypass réel
  découvert en §1.5, documenté, non traité par ce plan.
- **`app/appexport/freeze.py`/`snapshot.py`** (exports Statique/Autoporté) —
  bypass réel découvert en §1.5, documenté, non traité par ce plan.
- **Exposition MCP d'un outil qui listerait/modifierait `sensitive_fields`
  directement** — l'édition reste une action d'administration humaine via
  `PATCH /collections/{id}` (REST), pas un outil MCP allowlisté séparé.
  `query_features`/`run_analytics_query` (déjà allowlistés) héritent du
  masquage automatiquement via §3.4/§3.5, sans qu'aucun nouvel outil ne soit
  nécessaire.

---

## 5. Critères d'acceptation

1. `Privilege.DATA_VIEW_SENSITIVE` existe, 20e valeur, rejoint
   automatiquement `BUILT_IN_ROLE_PRIVILEGES["admin"]`, absent des 3 autres
   rôles prédéfinis. Test miroir shell (`rolePrivilegeCatalog.test.ts`) mis
   à jour et vert.
2. `PATCH /collections/{id}` avec `sensitiveFields: ["salary"]` sur une
   collection portant une colonne réelle `salary` : succès, `GET
   /collections/{id}` renvoie `sensitiveFields: ["salary"]`. Avec un nom de
   colonne inexistant ou réservé (pk/geometry/tenant_id) : 422.
3. **Chemin Postgres (A)** : un utilisateur SANS `DATA_VIEW_SENSITIVE`
   appelant `GET /collections/{id}/items` sur une collection avec `salary`
   marqué sensible reçoit des features dont `properties` ne contient PAS
   `salary` (absente, pas `null`) ; un utilisateur AVEC le privilège la
   reçoit. Même test pour `GET /collections/{id}/export/items?format=csv`
   (colonne absente de l'export), `GET /collections/{id}/items/{fid}`, et
   la tuile MVT (`GET /collections/{id}/tiles/{z}/{x}/{y}.mvt`, décodée dans
   le test pour vérifier l'absence de la propriété).
4. **Test direct du rôle Postgres**, sans passer par une route HTTP
   (falsifie le mécanisme lui-même, pas seulement son câblage) : un test
   `@pytest.mark.postgis` (patron `test_features_rls.py::pg_rls_table`,
   §1.3) crée une table avec RLS + `gis_rls_masked` grantée sur un
   sous-ensemble de colonnes, exécute `SET LOCAL ROLE gis_rls_masked`, et
   vérifie qu'un `SELECT colonne_sensible FROM table` échoue en
   `InsufficientPrivilege`/`permission denied`, alors qu'un `SELECT
   colonne_non_sensible FROM table` réussit.
5. **Chemin DuckDB (B)** : `POST /collections/{id}/aggregate` avec
   `groupBy: "salary"` par un utilisateur sans le privilège échoue avec
   `unknown field 'salary'` (comme un champ qui n'existe pas) ; avec le
   privilège, réussit et agrège correctement.
6. **Chemin DuckDB (C), SQL Lab — le critère central de ce chantier** : un
   test qui écrit un GeoParquet de fixture (patron
   `test_analytics_sql_sandbox.py::_write`) pour une collection dont
   `salary` est marqué sensible, puis appelle **`run_analyst_sql` avec `sql
   = "SELECT * FROM <collection>"` ou `"SELECT salary FROM <collection>"`**
   directement (pas via la route HTTP — prouve le mécanisme, pas seulement
   son câblage REST) avec `masked_fields_by_collection = {"<collection>":
   frozenset({"salary"})}` : le premier renvoie des colonnes qui ne
   contiennent PAS `salary` (`"columns"` ne liste pas le nom) ; le second
   lève `SqlSandboxError` (référence à une colonne qui n'existe pas dans la
   table DuckDB matérialisée — `BinderException` DuckDB capturée par le
   `except duckdb.Error` déjà en place). Un test complémentaire avec
   `masked_fields_by_collection={}` (utilisateur privilégié) confirme que
   les deux requêtes réussissent et renvoient `salary`.
7. **Test de non-régression du plomberie CDC** (§3.5.2, effet de bord) :
   `SELECT _lsn FROM <collection>` échoue désormais dans SQL Lab (colonne
   absente de la table matérialisée), qu'un champ soit marqué sensible ou
   non.
8. Les 7 appelants existants de `rls_scope` qui ne passent pas `masked=`
   (§3.4) continuent de fonctionner sans modification de leur code — vérifié
   en rejouant leurs suites de tests existantes sans aucune régression.
9. `test_model_alembic_parity.py` vert après la migration (nouvelle colonne
   couverte). Migration testée upgrade/downgrade/upgrade sur base non vide,
   avec au moins une collection préexistante et des lignes réelles
   (vérifie le backfill du GRANT initial, §3.2).
10. `ruff`/`ruff format --check`/`mypy --strict` (modules concernés déjà
    dans le périmètre `--strict` : `app.roles` en fait partie, `app.
    collections`/`app.analytics`/`app.features` n'en font pas partie
    aujourd'hui — vérifier au moment du plan s'ils y entrent, ne pas
    supposer) / `lint-imports` tous verts, aucune exemption de couche
    nouvelle attendue (à confirmer, pas à garantir a priori).
11. Diff `openapi.json`/`core-schema.d.ts` non vide et cohérent
    (`sensitiveFields` sur le schéma de `Collection`/`CollectionPatch`) —
    régénéré (CLAUDE.md piège n°1).
12. Suite complète cœur + shell + E2E sans régression de compte (CLAUDE.md
    piège n°6).

---

## 6. Risques

- **Sémantique GRANT/REVOKE par colonne mal vérifiée contre un vrai
  Postgres** (§1.2) — le risque le plus élevé de cette spec, parce que
  l'intuition la plus commune (« un REVOKE annule toujours l'accès ») est
  fausse dans ce cas précis. Le critère d'acceptation 4 (test direct du
  rôle, sans HTTP) est la seule protection réelle contre ce risque —
  impératif de l'exécuter tôt dans le plan, avant de câbler quoi que ce
  soit dessus.
- **Évaluation de la policy RLS elle-même sous `gis_rls_masked`** — si
  Postgres exige que le rôle exécutant ait SELECT sur `tenant_id` pour
  évaluer `USING (tenant_id = current_setting(...))`, l'omission de
  `tenant_id` dans le GRANT casserait silencieusement toute lecture sous ce
  rôle. Cette spec grante `tenant_id` sans condition (§3.2/§3.3, jamais
  marquable sensible) précisément pour ne pas dépendre de la réponse — mais
  à vérifier empiriquement (le test du critère 4 le fait déjà, sans
  isoler cette variable précise ; un test dédié qui grante délibérément
  toutes les colonnes SAUF `tenant_id` et vérifie que la RLS échoue quand
  même serait la preuve la plus directe, à la discrétion de l'exécution du
  plan).
- **Backfill de migration incomplet sur une base réelle volumineuse** — le
  bloc PL/pgSQL (§3.2) itère toutes les collections et toutes leurs
  colonnes ; sur un tenant avec des centaines de collections, ce peut être
  lent (DDL, pas de verrou de ligne, mais chaque `GRANT` est une écriture au
  catalogue système). Acceptable pour ce chantier (pas de contrainte de
  temps de migration documentée ailleurs dans ce dépôt), mais à mesurer
  empiriquement sur `postgis-test` avant de considérer la tâche close.
- **Un futur champ personnel ajouté sans jamais être marquable sensible** —
  contrairement à `toFrontLayer()` (CLAUDE.md piège n°5), il n'y a pas de
  filet de compilation qui rappellerait qu'une nouvelle collection/colonne
  devrait être examinée pour ce marquage — c'est un choix humain conscient
  (l'administrateur de collection décide), pas une omission technique à
  corriger.
- **Confusion entre `DATA_MANAGE` (écrire) et `DATA_VIEW_SENSITIVE` (lire
  du sensible)** côté futurs rôles sur mesure — un rôle qui porte les deux
  peut écrire et lire un champ sensible ; un rôle qui n'a que
  `DATA_VIEW_SENSITIVE` sans `DATA_VIEW` n'a par ailleurs aucun accès en
  lecture du tout (le privilège sensible ne lève jamais, à lui seul, la
  garde de lecture générale d'une collection) — à documenter clairement
  dans le libellé i18n du privilège pour éviter toute confusion à la
  création d'un rôle sur mesure.

---

## 7. Ce que cette spec ne tranche pas

- Le libellé français exact de `roles.privilege.dataViewSensitive` (à
  écrire au moment du plan, cohérent avec les 19 libellés existants).
- L'ordre précis des deux validations dans `patch_collection`
  (`_reject_invalid_sensitive_fields` avant ou après
  `_reject_attachment_field_collisions`) — sans conséquence fonctionnelle,
  à trancher pour la lisibilité du diff au moment de l'implémentation.
- Si `app.collections`/`app.analytics`/`app.features` doivent rejoindre le
  périmètre `mypy --strict` à cette occasion (actuellement seuls
  `app.auth`/`app.secrets`/`app.analytics`/`app.copilot`/`app.admin_tools`/
  `app.roles` en font partie d'après `CLAUDE.md` — `app.analytics` y est
  déjà, à vérifier si les nouveaux paramètres `masked_fields`/
  `frozenset[str]` typent proprement sous ce mode strict, sinon
  corriger les annotations plutôt que d'élargir le périmètre).
