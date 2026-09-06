# GAP-16 — Connecteur entrepôt cloud analytique (Snowflake) + note Redshift (design)

> **Date : 2026-09-06 · Statut : validé (brainstorm tenu avec Tanguy en amont de cette session)**
> Ferme [`docs/revue/2026-09-04-analyse-gaps.md`](../../revue/2026-09-04-analyse-gaps.md)
> **GAP-16** : *« Aucun connecteur natif vers un entrepôt cloud analytique
> (BigQuery, Snowflake, Databricks, Redshift) avec rafraîchissement planifié —
> GeoStudio ne lit que REST/Postgres (via dlt) et moissonne des catalogues
> géospatiaux. »* Sévérité **Sérieux**, effort estimé 5-10.
>
> Patron architectural direct :
> [`2026-08-06-sp15f-reader-connector-dlt-design.md`](2026-08-06-sp15f-reader-connector-dlt-design.md)
> (introduit `reader.connector.rest`/`reader.connector.postgres`) — cette
> spec ne réinvente rien, elle ajoute une troisième op au même catalogue en
> reproduisant le patron `reader.connector.postgres` presque à l'identique.
>
> Références de code vérifiées en session (lues intégralement, pas
> supposées) : `core/app/pipelines/connector_runtime.py`,
> `core/app/pipelines/registries.py`, `core/app/pipelines/egress.py`,
> `core/app/pipelines/ops/schemas.py`, `core/app/pipelines/runtime.py`
> (fonctions `_read_connector_postgres`/`_read_connector_rest`/`_prepare`),
> `core/app/pipelines/config_validation.py` (dispatch générique sur
> `OP_PARAMS`), `core/app/secrets/schemas.py` + `repository.py` +
> `routes.py`, `core/app/pipelines/ops/schemas.py::ReaderConnectorPostgresParams`,
> `shell/src/builder/pipeline/PipelinePalette.tsx`,
> `shell/src/builder/pipeline/PipelineNodeInspector.tsx`,
> `shell/src/builder/pipeline/SecretParamSelect.tsx`,
> `shell/src/api/types.ts` (types `SecretPayload`/`PipelineOpEntry`/
> `PipelineOpParamProperty`), `core/pyproject.toml`,
> `docker-compose.yml` (service `worker`, même image que `core`).
> Documentation tierce vérifiée en session (pas de mémoire) : PyPI
> `snowflake-sqlalchemy` (1.11.1, Apache-2.0) et `snowflake-connector-python`
> (4.7.3, Apache-2.0), `README.md`/`DESCRIPTION.md` du dépôt GitHub
> `snowflakedb/snowflake-sqlalchemy`, pages AWS
> `docs.aws.amazon.com/redshift/latest/dg/c_redshift-and-postgres-sql.html`
> et `.../c_redshift-postgres-jdbc.html` — citations exactes en §5.4.
> Comportement empirique vérifié en session (venv jetable hors dépôt,
> `snowflake-sqlalchemy==1.11.1` + `sqlalchemy>=2.0` installés, aucun réseau
> réel vers un compte Snowflake) : voir §3.3 et §5.3.

## 1. Objectif & non-buts

**Objectif.** Une nouvelle op **reader** dans le catalogue Pipeline
(`core/app/pipelines/ops/schemas.py`) : `reader.connector.snowflake`
(requête SQL libre sur un entrepôt Snowflake distant), authentifiée via un
secret du coffre SP-15e référencé **par son nom**. Comportement et
architecture identiques à `reader.connector.postgres` (dlt complet → DuckDB
scratch éphémère → `ATTACH`, cf. design SP-15f §3.1), la seule différence
substantielle étant le driver SQLAlchemy utilisé pour se connecter à la
source (`snowflake-sqlalchemy` au lieu du dialecte `postgresql` intégré).

**Décision de brainstorm (portée, tranchée, ne se rediscute pas ici) :**

| Entrepôt | Traitement | Justification |
|---|---|---|
| **Snowflake** | Nouvelle op `reader.connector.snowflake` (ce document) | Dialecte SQLAlchemy dédié disponible (`snowflake-sqlalchemy`, Apache-2.0), DSN incompatible avec le dialecte `postgresql` |
| **Redshift** | **Aucun nouveau code** — `reader.connector.postgres` existant fonctionne déjà (§5.4) | Redshift expose le protocole de câblage PostgreSQL — *« Amazon Redshift is based on PostgreSQL »* (AWS, cité en §5.4) ; un DSN `postgresql://...` + un secret `postgres_dsn` suffisent |
| **Databricks** | **Hors périmètre** de ce chantier | Patron déjà prouvé par ce document + SP-15f ; ajout futur mécanique (nouvelle op + nouveau kind de secret + dépendance `databricks-sql-connector`, même forme que ce document) |
| **BigQuery** | **Hors périmètre** de ce chantier | Idem — dialecte SQLAlchemy dédié existant (`sqlalchemy-bigquery`), mais authentification par compte de service JSON (pas un DSN texte simple) mérite sa propre conception de `SecretPayload`, non traitée ici |

**Non-buts explicites** (hérités tels quels de SP-15f §1, aucun n'est
rediscuté ni élargi par ce chantier) :
- Extraction incrémentale / `write_disposition="merge"` — chaque run
  ré-extrait tout (`replace`).
- Tables enfants dlt / détection automatique de géométrie — la nouvelle op
  est purement tabulaire, comme `reader.connector.postgres`.
- Planification/déclenchement — couvert **intégralement, sans travail
  nouveau**, par la planification cron des pipelines existante (SP-15h) :
  la nouvelle op entre dans un pipeline comme n'importe quel autre nœud
  reader, donc dans son `refreshPolicy` déjà existant. C'est un critère
  d'acceptation de ce chantier (§8), pas un chantier à part.
- Exposition MCP des noms de secrets — différée (comme pour SP-15f §8).
- Écriture vers Snowflake/Redshift distant — ces op sont des *readers*,
  aucun `writer.connector`.
- **Un nouveau nœud dédié à Redshift.** Explicitement refusé par la décision
  de brainstorm (§5.4) : ajouter un `reader.connector.redshift` dupliquerait
  `reader.connector.postgres` pour un gain nul (même protocole de câblage,
  même driver `psycopg`, même modèle de paramètres).
- Databricks, BigQuery — cf. tableau ci-dessus.

## 2. Modélisation de l'op (reprend SP-15f §2 verbatim, un connecteur de plus)

```python
class ReaderConnectorSnowflakeParams(BaseModel):
    """Lecture d'une requête SQL libre sur un entrepôt Snowflake distant
    (GAP-16, pendant de ReaderConnectorPostgresParams). `secretName`
    référence toujours un secret snowflake_dsn — pas de notion de DSN non
    authentifié, même contrat que reader.connector.postgres. `query` n'est
    validée SELECT-only qu'à L'EXÉCUTION (app.pipelines.connector_runtime),
    jamais ici (forme seulement) ni à la sauvegarde (§6) — même heuristique
    que pour Postgres, avec la même limite documentée en §5.3 (le texte est
    parsé avec le dialecte SQL DuckDB, pas le dialecte SnowSQL réel)."""

    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    query: str
```

Ajouts à `OP_KINDS`/`OP_PARAMS` (`core/app/pipelines/ops/schemas.py`,
mécanisme inchangé depuis SP-15a, déjà générique sur ces deux dicts) :

```python
OP_KINDS["reader.connector.snowflake"] = "reader"
OP_PARAMS["reader.connector.snowflake"] = ReaderConnectorSnowflakeParams
```

`ops_catalog()` (déjà générique) la publie automatiquement en JSON Schema
via `GET /pipelines/ops` — aucun changement de mécanisme, exactement comme
SP-15f §2 le documentait pour REST/Postgres.

### 2.1 Nouveau kind de secret : `snowflake_dsn`

`core/app/secrets/schemas.py` — union discriminée `SecretPayload`,
additive par construction (comme documenté par le docstring du module :
*« ajouter un kind = ajouter une variante Pydantic, aucune migration requise
pour les lignes existantes »*) :

```python
class SnowflakeDsnPayload(BaseModel):
    kind: Literal["snowflake_dsn"] = "snowflake_dsn"
    dsn: str
```

Ajouté à l'union `SecretPayload` et à `SECRET_PAYLOAD_ADAPTER`. Aucune
route ne change : `POST /secrets` (`core/app/secrets/routes.py`) valide le
corps via `SecretCreate.payload: SecretPayload` et dérive `kind` du
discriminant (`body.payload.kind`) sans jamais énumérer les kinds connus —
vérifié en lisant `create_secret_route` en entier (ligne 62 :
`kind=body.payload.kind`). Le nouveau kind est donc utilisable par
`POST /secrets` sans toucher au fichier `routes.py`.

### 2.2 Forme du DSN (vérifiée contre la source réelle, pas supposée)

Format confirmé contre le `README.md` du dépôt GitHub
`snowflakedb/snowflake-sqlalchemy` (branche `main`, section « Connection
Parameters ») :

```
snowflake://<user_login_name>:<password>@<account_name>/<database_name>/<schema_name>?warehouse=<warehouse_name>&role=<role_name>
```

`<database_name>`, `<schema_name>`, `warehouse`, `role` sont optionnels
(session Snowflake par défaut sinon) — exactement la fourchette anticipée
par le brainstorm. Un mot de passe contenant des caractères spéciaux
(`%`, `@`) doit être URL-encodé par qui crée le secret (`urllib.parse.quote`)
— documenté tel quel par le README amont, aucune validation applicative
ajoutée côté GeoStudio (même posture que `postgres_dsn`, dont le DSN n'est
jamais parsé/validé par le cœur avant d'être passé tel quel à
`sa.create_engine`).

## 3. Runtime d'exécution

### 3.1 `materialize_snowflake_connector` (`core/app/pipelines/connector_runtime.py`)

Reproduit **exactement** `materialize_postgres_connector` (lignes 240-276
du fichier actuel), à trois substitutions près : nom de la fonction, type
de params, et kind de secret attendu.

```python
def materialize_snowflake_connector(
    conn,
    *,
    session: Session,
    tenant_id: str,
    node_id: str,
    params: ReaderConnectorSnowflakeParams,
    view_name: str,
) -> None:
    # Défense en profondeur heuristique, pas une garantie (§5.3) — même
    # rationale exacte que materialize_postgres_connector : `params.query`
    # cible Snowflake mais est parsée avec le dialecte SQL de DuckDB.
    try:
        validate_select_only(parse_ast(conn, params.query))
    except SqlSandboxError as exc:
        raise ConnectorRuntimeError(f"reader.connector.snowflake query rejected: {exc}") from exc

    payload = _resolve_secret(session, tenant_id, params.secretName)
    if payload.kind != "snowflake_dsn":
        raise ConnectorRuntimeError(
            f"secret has kind '{payload.kind}', not usable by reader.connector.snowflake "
            "(expected snowflake_dsn)"
        )

    @dlt.resource(name="records", write_disposition="replace")
    def _records():
        engine = sa.create_engine(payload.dsn)
        try:
            with engine.connect() as db_conn:
                rows = db_conn.execution_options(yield_per=1000).exec_driver_sql(params.query)
                yield from (dict(row._mapping) for row in rows)
        finally:
            engine.dispose()

    _run_dlt_and_attach(conn, _records, node_id=node_id, view_name=view_name)
```

**Aucun import de `snowflake.sqlalchemy` nécessaire** dans ce fichier —
vérifié empiriquement en session (§3.3) : `snowflake-sqlalchemy` s'enregistre
comme dialecte SQLAlchemy via les *entry points* du paquet au moment de
l'installation ; `sa.create_engine("snowflake://...")` résout le dialecte
tout seul dès que le paquet est présent dans l'environnement, exactement
comme `postgresql://` résout aujourd'hui vers `psycopg`/`psycopg2` sans
qu'aucun `import psycopg` n'apparaisse dans `connector_runtime.py`. Le seul
changement de ce fichier est : une nouvelle fonction, aucune nouvelle
`import` en tête de module.

`_run_dlt_and_attach`, `_resolve_secret`, `_find_egress_blocked_cause` :
**inchangés**, réutilisés tels quels (déjà génériques sur la ressource dlt
passée).

### 3.2 Câblage `runtime.py` / `registries.py`

`core/app/pipelines/runtime.py` — nouvelle fonction `_read_connector_snowflake`,
pendant exact de `_read_connector_postgres` (lignes 273-298 actuelles) :

```python
def _read_connector_snowflake(
    conn, *, session, tenant_id, node_id, params, view_name, user, base_uri,
) -> int:
    """reader.connector.snowflake (registre READERS) — pendant de
    _read_connector_postgres, même rationale (GAP-16)."""
    p = ReaderConnectorSnowflakeParams.model_validate(params)
    try:
        connector_runtime.materialize_snowflake_connector(
            conn, session=session, tenant_id=tenant_id, node_id=node_id,
            params=p, view_name=view_name,
        )
    except connector_runtime.ConnectorRuntimeError as exc:
        raise PipelineRuntimeError(str(exc)) from exc
    return 4326
```

`core/app/pipelines/registries.py` — une entrée de plus dans `READERS`
(dict littéral, aucun autre changement) :

```python
READERS: dict[str, Callable] = {
    "reader.collection": _runtime._read_collection,
    "reader.connector.rest": _runtime._read_connector_rest,
    "reader.connector.postgres": _runtime._read_connector_postgres,
    "reader.connector.snowflake": _runtime._read_connector_snowflake,
}
```

Reste défini dans `runtime.py`, pas dans `registries.py` : même rationale
documentée par le docstring du module (`monkeypatch.setattr(runtime, ...)`
se résout par le namespace de définition, pas d'appel).

### 3.3 Vérification empirique du dialecte (session, sans réseau réel)

Vérifié dans un venv jetable hors dépôt (`snowflake-sqlalchemy==1.11.1`,
`sqlalchemy>=2.0`, aucune connexion vers un compte réel) :

- `sa.create_engine("snowflake://user:password@myaccount/mydb/myschema?warehouse=wh1&role=role1")`
  ne fait **aucun appel réseau** (comme tout `create_engine` SQLAlchemy —
  paresseux jusqu'à `.connect()`) et résout `engine.dialect.name == "snowflake"`
  sans jamais importer `snowflake.sqlalchemy` explicitement dans le script
  de test — confirme le point du §3.1.
- `engine.dialect.driver == "snowflake"`, mot de passe masqué par
  `str(engine.url)` (`snowflake://user:***@...`) — même comportement que
  le dialecte `postgresql` déjà en usage.
- `Connection.execution_options`/`Connection.exec_driver_sql` : API
  génériques de `sqlalchemy.engine.Connection`, pas spécifiques à un
  dialecte — le corps de `materialize_postgres_connector` est donc
  reproductible **verbatim** (aucune méthode Snowflake-spécifique requise).
- Un DSN pointant vers un hôte inexistant (`nonexistent-account-xyz123`)
  échoue **vite** (quelques secondes, pas de blocage long) avec
  `sqlalchemy.exc.DBAPIError` enveloppant un
  `snowflake.connector.errors.HttpError` — **le mot de passe du DSN
  n'apparaît pas dans `str(exc)`** (vérifié par assertion directe sur la
  chaîne). Confirme, pour Snowflake, la même propriété déjà documentée en
  commentaire pour Postgres dans `_run_dlt_and_attach` (« aucune des deux
  formes n'inclut le DSN complet ni le mot de passe ») — **note de
  différence réelle avec Postgres** : l'échec observé n'est pas un refus
  TCP/`Connection refused` mais une réponse HTTP 404 du point de terminaison
  `<account>.snowflakecomputing.com` — cf. §5.1, le connecteur Snowflake
  parle HTTPS, pas un protocole binaire brut comme `libpq`.
- Ce test n'a **jamais** contacté un compte Snowflake réel — aucun
  identifiant valide, aucune donnée transitée. Il ne prouve donc pas qu'une
  requête `SELECT` round-trippe réellement contre un entrepôt Snowflake vivant
  (cf. §8, limite assumée).

## 4. Résolution du secret

Inchangé : `_resolve_secret` (déjà générique, retourne l'union
`SecretPayload` sans connaître `snowflake_dsn`) est appelé tel quel.
`materialize_snowflake_connector` (pas `_resolve_secret`) vérifie que
`payload.kind == "snowflake_dsn"` — même séparation des responsabilités que
documentée par SP-15f §4 pour les deux connecteurs existants. Un
`secretName` de type `postgres_dsn` référencé par erreur dans
`reader.connector.snowflake` (ou l'inverse) échoue donc à l'exécution avec
un message explicite, jamais silencieusement — testé en §8 (mêmes deux cas
que SP-15f, un de plus par symétrie : `postgres_dsn` rejeté par
`reader.connector.snowflake`).

## 5. Sécurité

### 5.1 Pas de garde SSRF dédiée — raisonnement explicite (pas un oubli)

**Constat qui distingue ce connecteur de `reader.connector.postgres` :**
contrairement à Postgres (protocole binaire `libpq` brut sur TCP), le
connecteur Snowflake **parle HTTPS** vers
`https://<account>.snowflakecomputing.com` (confirmé empiriquement en §3.3
— l'échec de connexion observé est une `HttpError`, pas une erreur TCP). Un
lecteur pressé pourrait donc s'attendre à la même garde
`assert_egress_allowed`/adaptateur `requests` gardé que celle qui protège
`reader.connector.rest` (design SP-15f §5.1, `core/app/pipelines/egress.py`).

**Ce n'est délibérément pas le cas ici**, et le raisonnement de SP-15f §5.1
pour `reader.connector.postgres` reste intégralement valable — pas parce
que le protocole est HTTP ou non (ce critère, en y regardant de plus près,
ne tenait déjà pas la route de façon générale), mais parce que **la cible
réseau n'est jamais fournie par l'auteur du pipeline** : elle est entièrement
contenue dans le DSN du secret, et ce DSN n'est manipulable que par
quelqu'un habilité à créer un secret. Vérifié en session (pas supposé) sur
`core/app/secrets/routes.py::create_secret_route` : la route est gardée par
`require_any_privilege(session, user, [Privilege.ADMIN_SECRETS_MANAGE.value, Privilege.AUTOMATION_SECRETS_MANAGE.value])`
— un auteur de pipeline qui n'a que le droit d'écriture sur l'item Pipeline
(pas l'un de ces deux privilèges) ne peut créer aucun secret, donc ne peut
jamais faire pointer un DSN vers une adresse de son choix. C'est
exactement l'inverse de `reader.connector.rest`, où `baseUrl`/`path` sont
des champs du **node** — donc écrits par l'auteur du pipeline lui-même,
sans validation par un tiers habilité — d'où la garde SSRF dédiée à cette
seule op.

Autrement dit : le critère qui déclenche une garde SSRF dans ce dépôt n'est
pas « ce connecteur émet-il du HTTP ? » mais « la cible réseau est-elle
choisie par un principal moins habilité que celui qui la valide ? ». Pour
`reader.connector.postgres` et `reader.connector.snowflake`, la réponse est
non des deux côtés (le DSN est posé par un titulaire d'un privilège de
gestion de secrets) — aucune garde requise, cohérent avec le traitement déjà
accepté pour Postgres. Documenté explicitement ici pour qu'une revue future
ne rouvre pas ce point en pensant à un oubli (piège CLAUDE.md n°12 : ne pas
laisser un futur lecteur re-débattre un point déjà tranché sans code
disponible expliquant pourquoi).

### 5.2 Résiduel accepté

Comme pour `postgres_dsn` : si un secret `snowflake_dsn` est mal configuré
ou compromis par quelqu'un qui a déjà le privilège de le créer, aucune
garde applicative ne l'en empêche — le secret lui-même est la frontière de
confiance. Pas un résiduel nouveau, le même que celui déjà accepté par
SP-15e/SP-15f pour `postgres_dsn`.

### 5.3 Garde-fou `SELECT`-only — vérifié empiriquement contre DuckDB (pas supposé)

Réutilise **tel quel** `app.analytics.sql_sandbox.parse_ast` +
`validate_select_only`, exactement comme `reader.connector.postgres` (design
SP-15f §5.2). Défense en profondeur heuristique, **pas une garantie** — le
texte est parsé avec le dialecte SQL de **DuckDB**, pas SnowSQL. Vérifié
empiriquement en session (`json_serialize_sql`, DuckDB 1.5.4, le même
mécanisme que `parse_ast` utilise) contre un échantillon de constructions
SnowSQL réelles :

| Requête SnowSQL | Résultat DuckDB |
|---|---|
| `SELECT a FROM t QUALIFY ROW_NUMBER() OVER (...) = 1` | ✅ accepté (`SELECT_NODE`) |
| `SELECT payload:field::string FROM t` (accesseur semi-structuré `:`) | ✅ accepté |
| `SELECT a FROM t, LATERAL FLATTEN(input => t.arr) f` | ✅ accepté |
| `SELECT a ILIKE '%x%' FROM t` | ✅ accepté |
| `WITH x AS (SELECT 1) SELECT * FROM x` | ✅ accepté |
| `SELECT OBJECT_CONSTRUCT('a', 1)` | ✅ accepté |
| `SELECT * FROM t UNION SELECT * FROM u` | ✅ accepté (`SET_OPERATION_NODE`) |
| `SELECT * FROM t SAMPLE (10)` | ❌ **rejeté** (`syntax error at or near "10"`) — DuckDB exige une autre forme de `SAMPLE` |
| `SELECT TOP 10 a FROM t` | ❌ **rejeté** (`syntax error at or near "10"`) — DuckDB n'a pas `TOP`, seulement `LIMIT` |
| `SELECT a FROM t MINUS SELECT b FROM u` | ❌ **rejeté** (`syntax error at or near "SELECT"`) — DuckDB n'a pas l'opérateur `MINUS`, seulement `EXCEPT` |

**Conclusion vérifiée** : la majorité des idiomes SnowSQL utiles (accesseur
semi-structuré, `QUALIFY`, `LATERAL FLATTEN`, CTE, `UNION`) **passent** cette
validation heuristique sans adaptation. Trois constructions Snowflake
légitimes (`SAMPLE (n)` sans `ROWS`, `TOP n`, `MINUS`) sont rejetées comme
**faux négatifs** — un auteur de pipeline dont la requête réelle utilise
l'une de ces trois formes doit la reformuler (`LIMIT` au lieu de `TOP`,
`EXCEPT` au lieu de `MINUS`, `SAMPLE (n ROWS)` ou omettre `SAMPLE`) avant de
pouvoir l'exécuter — un échec de **validation**, à la sauvegarde… non, à
l'**exécution** (§6), avec un message clair, jamais un comportement
dégradé silencieux. C'est un vrai résiduel d'usabilité (pas de sécurité :
le sens du rejet est toujours « bloque une requête légitime », jamais
« laisse passer un DML déguisé ») — documenté ici explicitement plutôt que
découvert en revue.

### 5.4 Vérification Redshift (littérature, pas un compte réel — assumé explicitement)

**Aucun cluster Redshift réel n'est disponible dans cet environnement de
session** (service AWS payant, pas d'émulateur officiel auto-hébergeable
contrairement au sidecar `qgis-worker`, docker OSS gratuit, qui a permis de
vérifier M14 pour de vrai en SP-44). La validation ci-dessous est donc
**théorique**, appuyée sur la documentation AWS officielle citée
verbatim — **jamais présentée comme une vérification en conditions
réelles** (piège CLAUDE.md n°3).

Citations exactes, récupérées en session (2026-09-06) :

- `docs.aws.amazon.com/redshift/latest/dg/c_redshift-and-postgres-sql.html` :
  *« Amazon Redshift is based on PostgreSQL. »*
- `docs.aws.amazon.com/redshift/latest/dg/c_redshift-postgres-jdbc.html` :
  *« Because Amazon Redshift is based on PostgreSQL, we previously
  recommended using JDBC4 Postgresql driver version 8.4.703 and psqlODBC
  version 9.x drivers. If you are currently using those drivers, we
  recommend moving to the new Amazon Redshift–specific drivers going
  forward. »* — confirme que le pilote PostgreSQL générique **fonctionne**
  (AWS l'a recommandé pendant des années), la recommandation actuelle
  d'en changer est une question de fonctionnalités/performance, pas de
  rupture de compatibilité protocolaire.
- Recherche complémentaire (PyPI `sqlalchemy-redshift`) : le dialecte
  SQLAlchemy communautaire dédié à Redshift **s'appuie lui-même sur
  `psycopg2`** comme driver bas niveau — confirme que `psycopg2` (le driver
  par défaut résolu par `sa.create_engine("postgresql://...")`, déjà celui
  qu'utilise `materialize_postgres_connector` sans changement) parle
  couramment avec un cluster Redshift.

**Conséquence pratique** : un DSN de la forme
`postgresql://user:password@<cluster>.<region>.redshift.amazonaws.com:5439/<db>`,
stocké dans un secret de kind **`postgres_dsn` existant** (aucun nouveau
kind), référencé par un node **`reader.connector.postgres` existant**
(aucune nouvelle op), doit fonctionner sans aucune modification de code.
**Réserve documentée, non vérifiée empiriquement** : les pages AWS
listées ci-dessus (« Features that are implemented differently »,
« Unsupported PostgreSQL features/data types/functions ») indiquent que le
SQL Redshift diverge du SQL PostgreSQL sur plusieurs points — une requête
`params.query` syntaxiquement valide pour PostgreSQL **et** acceptée par la
validation heuristique DuckDB (§5.3, même mécanisme) peut malgré tout
échouer côté Redshift avec une erreur explicite. Résiduel déjà accepté
pour tout usage de `reader.connector.postgres` contre une base non
PostgreSQL stricte — pas un risque nouveau introduit par ce document.

### 5.5 Permissions

Aucune nouvelle porte. Reprend la posture SP-15e/SP-15f : n'importe quel
auteur de pipeline ayant les droits d'écriture sur l'item Pipeline peut
référencer un secret existant par son nom ; la valeur en clair n'apparaît
jamais dans le JSON du Pipeline, une réponse MCP, une sortie de preview,
des statistiques de run ou une entrée d'audit — uniquement `secretName`.

## 6. Validation à la sauvegarde vs à l'exécution

Aucun changement à `app.pipelines.config_validation` : la boucle
`for _op in OP_PARAMS: register_pipeline_node_validator(_op, _validate_node)`
(déjà présente, ligne 131-132 du fichier) itère dynamiquement sur
`OP_PARAMS` — elle enregistre le validateur générique
(forme Pydantic seule) pour `reader.connector.snowflake` automatiquement
dès que l'entrée est ajoutée à `OP_PARAMS`, sans qu'aucune ligne de ce
fichier ne soit éditée. `_COLLECTION_PARAM_FIELD.get("reader.connector.snowflake")`
retourne `None` (pas de champ `collectionId`), même comportement que pour
`reader.connector.postgres`. Vérifié en lisant le fichier en entier, pas
supposé par analogie.

Un `secretName`/`query` invalide, sauvegardable, qui échoue proprement au
run, est le comportement voulu — même philosophie que documentée SP-15f §6.

## 7. Déploiement

- **Nouvelle dépendance directe** `core/pyproject.toml` :
  `snowflake-sqlalchemy>=1.11,<2` (borne haute délibérée : `2.0.0a2` est une
  pré-version alpha au moment de cette session — casse la compatibilité
  SQLAlchemy 1.4, sans intérêt ici puisque le cœur exige déjà
  `sqlalchemy>=2.0`, mais une alpha ne doit jamais être installée
  silencieusement par une résolution de dépendances). Transitives vérifiées
  compatibles avec les contraintes déjà déclarées par `core/pyproject.toml`
  (aucun conflit détecté par une résolution réelle en venv jetable) :
  `snowflake-connector-python<5.0.0` (requiert `cryptography>=46.0.5`,
  `requests>=2.32.4`, `pyjwt>=2.10.1` — tous des planchers, compatibles avec
  les bornes basses déjà présentes `cryptography>=42.0`/`requests>=2.31`/
  `pyjwt[crypto]>=2.8`), `boto3`/`botocore` (déjà présents transitivement
  dans ce dépôt via un autre chemin, confirmé par le lockfile existant).
  Licence Apache-2.0 pour les deux paquets (`snowflake-sqlalchemy` et
  `snowflake-connector-python`), vérifiée sur PyPI (champ `license` et
  classifieur `License :: OSI Approved :: Apache Software License`) — aucune
  notice GPL/AGPL à ajouter (patron SP-9/SP-21).
- **Aucun nouveau service compose** — comme `dlt` pour REST/Postgres,
  `snowflake-sqlalchemy` est une bibliothèque Python in-process dans le
  `worker` existant (`docker-compose.yml`, service `worker` :
  `build: ./core`, même image que `core`) : le seul point de câblage réel
  est que `core/pyproject.toml` (donc l'image partagée par les deux
  services) porte la dépendance — pas de fichier compose à toucher.
- **Aucun nouvel environnement/secret d'instance** — `CORE_ETL_ENABLED`
  (capacité instance-wide existante, SP-15a) couvre cette op comme toutes
  les autres. Le `snowflake_dsn` est un secret **par tenant**, créé via
  `POST /secrets` comme tout autre kind — pas une variable d'environnement
  du service.
- **Régénération OpenAPI/TS obligatoire** (piège CLAUDE.md n°1) : le corps
  de `POST /secrets` (`SecretCreate.payload: SecretPayload`) change de
  forme (nouvelle variante d'union) — diff `openapi.json` non vide attendu
  même si aucune route n'est ajoutée ni modifiée. `shell/src/api/types.ts`
  porte sa propre définition **manuscrite** de `SecretPayload` (pas générée
  depuis `core-schema.d.ts` pour ce type précis, vérifié en lisant le
  fichier) — à mettre à jour manuellement en plus de la régénération, les
  deux ne se substituent pas l'une à l'autre.

## 8. Surface shell — entièrement générique, un seul point non générique à toucher

**Constat central (vérifié en lisant les trois fichiers en entier, pas
supposé) :** `PipelinePalette.tsx` liste les op depuis `usePipelineOps()`
(`GET /pipelines/ops`) sans aucune liste figée par op — une nouvelle entrée
de catalogue apparaît dans la palette **sans aucune modification de ce
fichier**. `PipelineNodeInspector.tsx` rend les champs de n'importe quelle
op depuis son JSON Schema (`format: "collection-id"` → sélecteur de
collection, `format: "secret-name"` → `SecretParamSelect`, `enum` → menu,
`type: "object"`/`"array"` → éditeurs génériques, défaut → champ texte/nombre)
— une nouvelle op dont les params suivent ces conventions (c'est le cas de
`ReaderConnectorSnowflakeParams` : `secretName` porte déjà
`format: "secret-name"`, `query` est un `str` nu) se rend **automatiquement**
sans aucune modification de ce fichier non plus.

**Le seul point non générique** est `SecretParamSelect.tsx` : le formulaire
de création de secret est « un formulaire minimal par variante, pas un
générateur JSON Schema complet — les kinds de `SecretPayload` sont fixes et
connus » (commentaire du fichier, assumé, pas un défaut à corriger ici).
Ajouter le kind `snowflake_dsn` y est donc un changement de code réel,
minimal :

1. `shell/src/api/types.ts` — ajouter la variante à l'union `SecretPayload` :
   `| { kind: "snowflake_dsn"; dsn: string }`.
2. `SecretParamSelect.tsx` — `KIND_LABELS` gagne
   `snowflake_dsn: t("secretParamSelect.kindSnowflakeDsn")` (`ALL_KINDS` en
   dérive automatiquement, `Object.keys(KIND_LABELS)`).
3. `buildPayload()` — `snowflake_dsn` a **la même forme** que `postgres_dsn`
   (`{kind, dsn}`, un seul champ texte) : élargir la condition existante
   plutôt que dupliquer une branche entière —
   `case "postgres_dsn": case "snowflake_dsn": return { kind, dsn: field("dsn") };`.
4. Le bloc JSX du champ `dsn` (actuellement `{kind === "postgres_dsn" && (...)}`)
   — élargir la condition à
   `{(kind === "postgres_dsn" || kind === "snowflake_dsn") && (...)}` : même
   label/aria (`secretParamSelect.dsnLabel`/`dsnAria`, vérifiés déjà
   génériques — texte français actuel « DSN », pas « DSN Postgres » —
   aucune reformulation nécessaire).
5. `shell/src/i18n/catalog.fr.ts` — une clé `secretParamSelect.kindSnowflakeDsn`.

Aucun autre fichier shell ne change. Pas de nouveau composant, pas de
nouvelle route, pas de nouveau hook.

## 9. Note Redshift — indice UI/documentation sur le nœud Postgres existant

Décision de brainstorm §1 : documenter la compatibilité Redshift **sur le
nœud existant**, jamais un nouveau nœud. Mécanisme retenu, vérifié
faisable en session :

- Le docstring de classe d'un `BaseModel` Pydantic apparaît déjà tel quel
  dans `model_json_schema()["description"]` (vérifié empiriquement :
  `ReaderConnectorPostgresParams.model_json_schema()["description"]`
  contient déjà son docstring actuel) — et `ops_catalog()` le propage déjà
  jusqu'à `paramsSchema.description` dans la réponse de
  `GET /pipelines/ops` (vérifié : `"description" in cat["reader.connector.postgres"]["paramsSchema"]`
  est `True` sans aucun changement de code).
- **Ce que le shell n'expose pas encore** (vérifié en lisant
  `PipelineOpEntry`/`PipelineOpParamProperty`, `shell/src/api/types.ts`
  lignes 1064-1086) : le type `PipelineOpEntry.paramsSchema` ne déclare
  que `properties`/`required`, pas `description` — le champ existe déjà
  dans la réponse JSON réelle mais n'est pas typé côté shell, donc jamais
  rendu.

**Changement retenu** (générique, pas un cas spécial Postgres — même
philosophie que `PipelineNodeInspector.renderField`, qui commente
explicitement : *« pas de branche spécifique à un champ nommé... tout futur
champ ... en bénéficiera »*) :

1. `core/app/pipelines/ops/schemas.py::ReaderConnectorPostgresParams` —
   étendre le docstring existant d'une phrase mentionnant la compatibilité
   Redshift (cf. §5.4), sans toucher aux champs du modèle.
2. `shell/src/api/types.ts::PipelineOpEntry.paramsSchema` — ajouter
   `description?: string;` (champ optionnel, déjà présent côté JSON,
   simplement pas encore typé).
3. `PipelinePalette.tsx` — poser un attribut `title={catalog[op]?.paramsSchema.description}`
   (tooltip HTML natif, aucune dépendance nouvelle) sur l'entrée
   draggable, **pour toute op qui porte une description**, pas seulement
   `reader.connector.postgres` — bénéfice immédiat et gratuit pour les
   futures op qui documenteront leur docstring (ex. une future op
   Databricks/BigQuery, hors périmètre ici, en profitera sans rien faire
   de plus).

Résultat : survoler l'entrée « reader.connector.postgres » dans la palette
affiche désormais un texte mentionnant la compatibilité Redshift — un
indice réel, pas un commentaire de code invisible à l'auteur du pipeline.

## 10. Exposition MCP

Aucun nouvel outil. `explain_pipeline` (existant) expose la nouvelle op
gratuitement via `ops_catalog()` — même constat que SP-15f §8. La liste des
noms de secrets pour guider un agent auteur reste différée (non construite
ici, ni par ce chantier ni par SP-15f).

## 11. Critères d'acceptation

1. `reader.connector.snowflake` apparaît dans `GET /pipelines/ops` avec son
   `paramsSchema` (`secretName` avec `format: "secret-name"`, `query`
   requis).
2. Un pipeline avec un node `reader.connector.snowflake` référençant un
   secret `snowflake_dsn` valide s'exécute et matérialise ses lignes en
   `TEMP TABLE`, consommable par n'importe quel transform/writer en aval —
   **vérifié uniquement en mode mocké/théorique dans ce dépôt** (§12,
   aucun compte Snowflake réel disponible en session ni en CI).
3. Un secret du mauvais kind (`postgres_dsn` référencé par
   `reader.connector.snowflake`, ou l'inverse) échoue à l'**exécution**
   avec un message explicite, jamais à la sauvegarde.
4. Un secret manquant échoue à l'exécution avec un message explicite.
5. Une `query` non-`SELECT` est rejetée avant toute tentative de connexion
   (même heuristique que Postgres, limites documentées §5.3).
6. Aucune valeur de secret (mot de passe/DSN complet) n'apparaît dans une
   sortie de preview, des statistiques de run, ou une entrée `audit_log`.
7. Le nouveau node est planifiable via le mécanisme cron existant
   (`Pipeline.refreshPolicy`, SP-15h) **sans aucun changement de code** —
   satisfait par construction (l'op entre dans le même graphe que toute
   autre reader), vérifié en confirmant qu'aucune logique de planification
   ne discrimine par `op` (grep sur `refreshPolicy`/le module de
   planification, aucune branche par nom d'op trouvée).
8. Le formulaire de création de secret du builder (`SecretParamSelect`)
   propose `snowflake_dsn` comme kind, avec un champ DSN masqué
   (`type="password"`).
9. Le nœud `reader.connector.postgres` affiche, au survol dans la palette,
   une mention de sa compatibilité avec un cluster Redshift.
10. `lint-imports` reste vert sans nouvelle exemption (aucun nouvel import
    inter-couches — `sa.create_engine` résout le dialecte par entry point,
    pas par import explicite d'un module `app.*`).
11. Suites existantes (`core` pytest, `shell` vitest/e2e) restent vertes —
    extension additive pure.

## 12. Hors périmètre (explicite, pour qu'une revue future ne le redécouvre pas comme un oubli)

- **Databricks, BigQuery** : aucune op, aucun kind de secret, aucune
  dépendance ajoutée par ce chantier. Le patron de ce document (une op +
  un kind de secret + une fonction `materialize_*_connector` + deux lignes
  de registre) s'y applique mécaniquement le jour où ils seront demandés —
  BigQuery mérite une conception de `SecretPayload` dédiée (compte de
  service JSON, pas un DSN texte) qui n'est pas traitée ici.
- **Un node `reader.connector.redshift` dédié** : refusé par la décision de
  brainstorm §1 — dupliquerait `reader.connector.postgres` sans gain.
- **Vérification empirique contre un vrai compte Snowflake** : aucun compte
  disponible dans cet environnement de session ni, structurellement, en CI
  (service cloud propriétaire payant — contrairement au sidecar
  `qgis-worker`, il n'existe pas d'image Docker officielle auto-hébergeable
  équivalente à un entrepôt Snowflake réel). Le plan d'exécution (document
  séparé) documente précisément ce qui est vérifié en mocké/isolé vs ce qui
  resterait à faire à la main par un opérateur disposant d'un compte
  d'essai — **jamais présenté comme déjà vérifié**.
- **Vérification empirique contre un vrai cluster Redshift** : même
  limite, service AWS payant. §5.4 documente une validation par la
  littérature officielle uniquement.
- **Extraction incrémentale, tables enfants dlt, écriture vers l'entrepôt** :
  hérités tels quels des non-buts SP-15f §1, non rediscutés.
- **Un connecteur générique "n'importe quel dialecte SQLAlchemy"** (au lieu
  d'une op nommée par entrepôt) : écarté pour la même raison que SP-15f §2
  a choisi deux op séparées plutôt qu'une op à discriminant — chaque
  entrepôt a ses propres subtilités de DSN/authentification qui méritent
  un schéma de params dédié et lisible, pas un champ `dialect: str` libre
  qui déplacerait toute la validation de forme vers l'exécution.
