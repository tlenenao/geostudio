# GAP-16 — Connecteur entrepôt cloud analytique (Snowflake) + note Redshift — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close GAP-16 (`docs/revue/2026-09-04-analyse-gaps.md`) by adding one
new Pipeline reader op, `reader.connector.snowflake` (arbitrary read-only SQL
against a remote Snowflake warehouse), authenticated via the SP-15e secrets
store by name — and, without any new op or code path, document that
`reader.connector.postgres` (existing) already works against an Amazon
Redshift cluster.

**Architecture:** `reader.connector.snowflake` reproduces
`reader.connector.postgres` (`core/app/pipelines/connector_runtime.py`)
almost verbatim: a `dlt` resource wraps a raw SQLAlchemy connection opened
from a secret's DSN, `SELECT`-only heuristic validation via
`app.analytics.sql_sandbox`, materialization through the existing
`_run_dlt_and_attach` → DuckDB `ATTACH` → `TEMP TABLE` pipeline shared by
every reader. The only new moving part is the SQLAlchemy dialect itself
(`snowflake-sqlalchemy`, resolved automatically by `sa.create_engine` once
installed — no explicit import anywhere in this repo's code). A new secret
kind, `snowflake_dsn`, is added to the existing discriminated
`SecretPayload` union (additive, no migration). The Redshift note is a
one-sentence docstring addition on the existing
`ReaderConnectorPostgresParams`, surfaced through a small **generic**
addition to two already-schema-driven shell files (`PipelinePalette.tsx`
gains a tooltip sourced from `paramsSchema.description`, which every future
op benefits from too — not a Postgres-specific branch).

**Tech Stack:** Python/FastAPI (`core/`), `snowflake-sqlalchemy` (Apache-2.0,
new direct dependency, brings `snowflake-connector-python` transitively),
SQLAlchemy (raw SQL against the secret's DSN — same `exec_driver_sql`/
`execution_options(yield_per=...)` pattern already used for Postgres), dlt
(already a dependency since SP-15f), pytest, React/TypeScript (`shell/`).

## Global Constraints

- **Design doc**: `docs/superpowers/specs/2026-09-06-gap16-connecteur-entrepot-design.md`
  — every task below implements a specific section; section refs noted per
  task.
- **No new route, no new MCP tool, no migration** (design §7, §9, §10).
  `GET /pipelines/ops` (`app.pipelines.routes::get_pipeline_ops() -> dict`,
  confirmed untyped/generic — no OpenAPI schema impact) and
  `explain_pipeline` pick up the new op automatically via the already-generic
  `ops_catalog()`. `POST /secrets` (`app.secrets.routes::create_secret_route`)
  derives `kind` from `body.payload.kind` without ever enumerating known
  kinds (confirmed by reading the route body in design §2.1) — adding a
  `SecretPayload` variant needs no route change. **This DOES change
  `POST /secrets`'s request body OpenAPI schema** (a real Pydantic union
  gains a member) — Task 2 regenerates `openapi.json`/`core-schema.d.ts`
  (piège CLAUDE.md n°1), unlike ops-catalog-only changes which don't.
- **No `config_validation.py` change** (design §6). Its
  `for _op in OP_PARAMS: register_pipeline_node_validator(_op, _validate_node)`
  loop (`core/app/pipelines/config_validation.py:131-132`, already generic)
  picks up `reader.connector.snowflake` automatically the moment it's added
  to `OP_PARAMS`; `_COLLECTION_PARAM_FIELD.get("reader.connector.snowflake")`
  returns `None` (no `collectionId`-typed field), same as
  `reader.connector.postgres`. Do not touch this file.
- **No new SSRF guard** (design §5.1). Unlike `reader.connector.rest`,
  neither `reader.connector.postgres` nor `reader.connector.snowflake` ever
  let the pipeline *author* choose the network destination — it's baked
  into a secret's DSN, and `POST /secrets` is gated by
  `require_any_privilege(session, user, [Privilege.ADMIN_SECRETS_MANAGE.value, Privilege.AUTOMATION_SECRETS_MANAGE.value])`
  (`core/app/secrets/routes.py:48-52`). Do not add an `egress.py` import to
  `connector_runtime.py` for the Snowflake path.
- **No `snowflake.sqlalchemy` import anywhere in `core/app`.** SQLAlchemy
  resolves the `snowflake://` dialect via the package's own entry points at
  install time — verified empirically in design §3.3
  (`sa.create_engine("snowflake://...")` resolves `engine.dialect.name ==
  "snowflake"` without ever importing `snowflake.sqlalchemy`). Task 3's
  `materialize_snowflake_connector` therefore needs **zero new imports**
  beyond what `connector_runtime.py` already has (`sqlalchemy as sa` is
  already imported for the Postgres connector).
- **Dependency pin excludes the 2.0.0a2 prerelease deliberately**:
  `snowflake-sqlalchemy>=1.11,<2` (design §7 — 2.0.0a2 is an alpha at the
  time of writing; never let a resolver silently pick a prerelease).
- **The Snowflake round-trip test is permanently manual, never CI-wired**
  (design §12). Unlike the `@pytest.mark.qgis` tests (which run for real in
  a dedicated `core-qgis` CI job against a self-hostable Docker sidecar,
  `.github/workflows/ci.yml:74-133`), there is no self-hostable Snowflake
  emulator — a live round-trip can only run against a real paid account, by
  hand, never in CI. Task 3 adds a `snowflake` pytest marker
  (`core/pyproject.toml`'s `markers` list, mirroring the existing `postgis`/
  `qgis`/`playwright`/`docker` entries) and a session-scoped
  `snowflake_test_dsn` fixture in `core/tests/conftest.py` that
  `pytest.skip()`s when `CORE_TEST_SNOWFLAKE_DSN` is unset (same shape as
  `pg_engine`/`qgis_worker_url`) — **do not** add a CI job for it, and do
  not add a `test_ci_actually_runs_the_snowflake_marked_tests` guard (that
  guard exists for qgis specifically because qgis *was* meant to eventually
  run for real in CI; Snowflake structurally never will).
- **`materialize_postgres_connector` is not touched beyond its docstring**
  (design §9). Its behavior, signature, and tests are unchanged — only the
  class docstring of `ReaderConnectorPostgresParams` (`core/app/pipelines/ops/schemas.py`)
  gains one sentence about Redshift compatibility (Task 1).
- **`SecretParamSelect.tsx`'s new `snowflake_dsn` branch reuses the existing
  `postgres_dsn` JSX block** (design §8) — widen the existing
  `kind === "postgres_dsn"` condition to
  `(kind === "postgres_dsn" || kind === "snowflake_dsn")` rather than adding
  a second, duplicate block. Both kinds have the identical shape
  (`{kind, dsn: string}`) and the existing `secretParamSelect.dsnLabel`/
  `dsnAria` i18n strings are already generic (`"DSN"`, not `"DSN Postgres"`
  — confirmed by reading `shell/src/i18n/catalog.fr.ts:1131-1132`), so no
  copy change is needed there.
- **`PipelinePalette.tsx`'s tooltip is generic, not a Postgres special
  case** (design §9). `opEntry.paramsSchema.description` is rendered as a
  `title` attribute for **any** op that has one — this is what actually
  carries the Redshift hint to the author (a docstring nobody reads is not
  a real UI hint), and it's free for any future op's docstring too, matching
  this repo's existing convention of schema-driven generic rendering
  (`PipelineNodeInspector.tsx`'s own header comment: *"pas de branche
  spécifique à un champ nommé... tout futur champ ... en bénéficiera"*).

---

## Task 1: Op catalog — `ReaderConnectorSnowflakeParams` + Redshift docstring note

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Test: `core/tests/test_pipeline_ops_schemas.py`

**Interfaces:**
- Produces: `app.pipelines.ops.schemas.ReaderConnectorSnowflakeParams`
  (Pydantic `BaseModel`, fields `secretName: str`, `query: str`), plus a new
  `"reader.connector.snowflake"` entry in `OP_KINDS`/`OP_PARAMS`. Consumed
  by Task 3 (`connector_runtime.materialize_snowflake_connector` takes an
  already-validated instance as its `params` argument) and Task 4
  (`runtime.py`'s `_read_connector_snowflake`).

- [ ] **Step 1: Write the failing tests**

Modify `core/tests/test_pipeline_ops_schemas.py` — rename
`test_all_eighteen_ops_are_registered` (this test asserts an **exact** set
equality; adding an op without updating it breaks it) to:

```python
def test_all_nineteen_ops_are_registered():
    assert set(OP_PARAMS) == {
        "reader.collection",
        "transform.filter",
        "transform.select",
        "transform.derive",
        "transform.aggregate",
        "transform.join",
        "writer.collection",
        "writer.export",
        "transform.buffer",
        "transform.reproject",
        "transform.intersection",
        "transform.countWithin",
        "transform.h3Aggregate",
        "writer.dataset",
        "transform.qgis",
        "reader.connector.rest",
        "reader.connector.postgres",
        "transform.merge",
        "reader.connector.snowflake",
    }
    assert set(OP_KINDS) == set(OP_PARAMS)
```

Append at the end of the file:

```python
def test_reader_connector_snowflake_is_kind_reader():
    assert OP_KINDS["reader.connector.snowflake"] == "reader"


def test_reader_connector_snowflake_requires_secret_name_and_query():
    params = parse_op_params(
        "reader.connector.snowflake",
        {"secretName": "warehouse-sf", "query": "SELECT * FROM towns"},
    )
    assert params.secretName == "warehouse-sf"
    assert params.query == "SELECT * FROM towns"
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.snowflake", {"query": "SELECT 1"})
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.snowflake", {"secretName": "x"})


def test_reader_connector_snowflake_appears_in_catalog_with_secret_name_format_hint():
    catalog = ops_catalog()
    assert catalog["reader.connector.snowflake"]["kind"] == "reader"
    props = catalog["reader.connector.snowflake"]["paramsSchema"]["properties"]
    assert "query" in props
    assert props["secretName"]["format"] == "secret-name"


def test_reader_connector_postgres_description_documents_redshift_compatibility():
    # GAP-16 §9 : le docstring de classe devient déjà le paramsSchema.description
    # exposé par GET /pipelines/ops — ce test falsifie qu'ajouter la phrase
    # Redshift au docstring la propage réellement jusqu'au catalogue, pas
    # seulement jusqu'à un commentaire de code invisible à l'auteur du pipeline.
    catalog = ops_catalog()
    description = catalog["reader.connector.postgres"]["paramsSchema"]["description"]
    assert "Redshift" in description
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: FAIL — `test_all_nineteen_ops_are_registered` fails (set mismatch,
`reader.connector.snowflake` missing from `OP_PARAMS`); the three new
`reader_connector_snowflake` tests fail with `ValueError: unknown op
'reader.connector.snowflake'`; `test_reader_connector_postgres_description_documents_redshift_compatibility`
fails with `AssertionError` (docstring doesn't mention Redshift yet).

- [ ] **Step 3: Implement the param model, extend the Postgres docstring, register the op**

Modify `core/app/pipelines/ops/schemas.py` — extend the existing
`ReaderConnectorPostgresParams` docstring (do not touch its fields):

```python
class ReaderConnectorPostgresParams(BaseModel):
    """Lecture d'une requête SQL libre sur un Postgres distant (design
    SP-15f §2). `secretName` référence toujours un secret postgres_dsn
    (SP-15e) — pas de notion de DSN non authentifié, contrairement à REST.
    `query` n'est validée SELECT-only qu'à l'exécution (app.pipelines.connector_runtime),
    jamais ici (forme seulement) ni à la sauvegarde (design §6).

    Fonctionne également contre un cluster Amazon Redshift, sans aucun
    changement de code (GAP-16, design 2026-09-06 §5.4) : Redshift expose le
    protocole de câblage PostgreSQL (AWS, « Amazon Redshift is based on
    PostgreSQL ») — pointez le DSN d'un secret postgres_dsn vers l'endpoint
    du cluster (port 5439 par défaut) plutôt que vers un Postgres ordinaire.
    Limite connue : le SQL Redshift diverge du SQL PostgreSQL sur plusieurs
    points (types/fonctions non supportés) — une requête acceptée par la
    validation SELECT-only heuristique ci-dessus (dialecte DuckDB) peut
    malgré tout échouer côté Redshift avec une erreur explicite."""

    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    query: str
```

Add the new param model, immediately after `ReaderConnectorPostgresParams`
(before `OP_KINDS`):

```python
class ReaderConnectorSnowflakeParams(BaseModel):
    """Lecture d'une requête SQL libre sur un entrepôt Snowflake distant
    (GAP-16, pendant de ReaderConnectorPostgresParams). `secretName`
    référence toujours un secret snowflake_dsn — pas de notion de DSN non
    authentifié, même contrat que reader.connector.postgres. `query` n'est
    validée SELECT-only qu'à l'exécution (app.pipelines.connector_runtime),
    jamais ici (forme seulement) ni à la sauvegarde (design §6) — même
    heuristique que pour Postgres, avec la même limite documentée en §5.3
    (le texte est parsé avec le dialecte SQL DuckDB, pas le dialecte
    SnowSQL réel : QUALIFY/accesseur semi-structuré `:`/LATERAL FLATTEN/
    ILIKE/UNION passent, mais SAMPLE (n)/TOP n/MINUS sont rejetés — à
    reformuler en LIMIT/EXCEPT le cas échéant)."""

    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    query: str
```

Extend `OP_KINDS`/`OP_PARAMS` (add one entry to each dict, alongside the
existing `reader.connector.*` entries):

```python
OP_KINDS: dict[str, str] = {
    "reader.collection": "reader",
    "transform.filter": "transform",
    "transform.select": "transform",
    "transform.derive": "transform",
    "transform.aggregate": "transform",
    "transform.join": "transform",
    "transform.buffer": "transform",
    "transform.reproject": "transform",
    "transform.intersection": "transform",
    "transform.countWithin": "transform",
    "transform.h3Aggregate": "transform",
    "transform.qgis": "transform",
    "writer.collection": "writer",
    "writer.export": "writer",
    "writer.dataset": "writer",
    "reader.connector.rest": "reader",
    "reader.connector.postgres": "reader",
    "reader.connector.snowflake": "reader",
}
OP_KINDS["transform.merge"] = "transform"

OP_PARAMS: dict[str, type[BaseModel]] = {
    "reader.collection": ReaderCollectionParams,
    "transform.filter": TransformFilterParams,
    "transform.select": TransformSelectParams,
    "transform.derive": TransformDeriveParams,
    "transform.aggregate": TransformAggregateParams,
    "transform.join": TransformJoinParams,
    "transform.buffer": TransformBufferParams,
    "transform.reproject": TransformReprojectParams,
    "transform.intersection": TransformIntersectionParams,
    "transform.countWithin": TransformCountWithinParams,
    "transform.h3Aggregate": TransformH3AggregateParams,
    "transform.qgis": TransformQgisParams,
    "writer.collection": WriterCollectionParams,
    "writer.export": WriterExportParams,
    "writer.dataset": WriterDatasetParams,
    "reader.connector.rest": ReaderConnectorRestParams,
    "reader.connector.postgres": ReaderConnectorPostgresParams,
    "reader.connector.snowflake": ReaderConnectorSnowflakeParams,
}
OP_PARAMS["transform.merge"] = TransformMergeParams
```

(Only the two dict literals themselves change — `BINARY_OPS`,
`parse_op_params`, `ops_catalog` are untouched; both already iterate
`OP_PARAMS` generically.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: all pass (19 ops registered, new op in catalog with
`format: "secret-name"` on `secretName`, Postgres description mentions
Redshift).

- [ ] **Step 5: Run the full pipelines test suite to confirm no regression**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py tests/test_pipeline_config_validation.py tests/test_mcp_tools_pipeline.py -v`
Expected: all pass — pure catalog addition + docstring change, no behavior
change to any existing op.

- [ ] **Step 6: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/tests/test_pipeline_ops_schemas.py
git commit -m "feat(core): pipelines — reader.connector.snowflake op catalog entry + Redshift note"
```

---

## Task 2: Secret kind — `snowflake_dsn` + OpenAPI/TS regeneration

**Files:**
- Modify: `core/app/secrets/schemas.py`
- Test: `core/tests/test_secrets_schemas.py`
- Regenerate: `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`

**Interfaces:**
- Produces: `app.secrets.schemas.SnowflakeDsnPayload` (Pydantic `BaseModel`,
  `kind: Literal["snowflake_dsn"] = "snowflake_dsn"`, `dsn: str`), added to
  the `SecretPayload` union and `SECRET_PAYLOAD_ADAPTER`. Consumed by
  Task 3 (`materialize_snowflake_connector` checks `payload.kind ==
  "snowflake_dsn"`).

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_secrets_schemas.py`:

```python
def test_snowflake_dsn_round_trips():
    body = SecretCreate.model_validate(
        {
            "name": "warehouse-sf",
            "payload": {
                "kind": "snowflake_dsn",
                "dsn": "snowflake://u:p@myaccount/mydb/myschema?warehouse=wh1&role=role1",
            },
        }
    )
    assert body.payload.dsn == "snowflake://u:p@myaccount/mydb/myschema?warehouse=wh1&role=role1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_secrets_schemas.py -k snowflake -v`
Expected: FAIL — `pydantic.ValidationError: ... Input tag 'snowflake_dsn'
found using 'kind' does not match any of the expected tags`.

- [ ] **Step 3: Add the payload variant**

Modify `core/app/secrets/schemas.py` — add after `PostgresDsnPayload`:

```python
class SnowflakeDsnPayload(BaseModel):
    """DSN SQLAlchemy complet vers un entrepôt Snowflake (GAP-16), forme
    `snowflake://user:password@account/database/schema?warehouse=...&role=...`
    (vérifiée contre le README du dépôt snowflake-sqlalchemy, design §2.2).
    Comme postgres_dsn : le cœur ne parse ni ne valide ce DSN, il le passe
    tel quel à sa.create_engine()."""

    kind: Literal["snowflake_dsn"] = "snowflake_dsn"
    dsn: str
```

Update the `SecretPayload` union and `SECRET_PAYLOAD_ADAPTER`:

```python
SecretPayload = Annotated[
    ApiKeyPayload
    | BearerTokenPayload
    | BasicAuthPayload
    | OAuth2ClientCredentialsPayload
    | PostgresDsnPayload
    | SmtpCredentialsPayload
    | SnowflakeDsnPayload,
    Field(discriminator="kind"),
]

SECRET_PAYLOAD_ADAPTER: TypeAdapter[
    ApiKeyPayload
    | BearerTokenPayload
    | BasicAuthPayload
    | OAuth2ClientCredentialsPayload
    | PostgresDsnPayload
    | SmtpCredentialsPayload
    | SnowflakeDsnPayload
] = TypeAdapter(SecretPayload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_secrets_schemas.py -v`
Expected: all pass (previous kinds untouched, `snowflake_dsn` round-trips).

- [ ] **Step 5: Run the full secrets test suite to confirm no regression**

Run: `cd core && uv run pytest tests/test_secrets_schemas.py tests/test_secrets_repository.py tests/test_secrets_routes.py -v`
Expected: all pass — additive union member only, `create_secret_route`
derives `kind` from `body.payload.kind` generically (no route code
touched).

- [ ] **Step 6: Regenerate OpenAPI + shell types (piège CLAUDE.md n°1)**

Run:

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Expected: `core/openapi.json` diff is **non-empty** — the `SecretPayload`/
`SecretCreate` request-body schema for `POST /secrets` gains the
`snowflake_dsn` variant (a real Pydantic union member, unlike the untyped
`dict` returned by `GET /pipelines/ops`). `shell/src/api/generated/core-schema.d.ts`
diff reflects the same new union member. Neither diff touches any other
route or model.

- [ ] **Step 7: Commit**

```bash
git add core/app/secrets/schemas.py core/tests/test_secrets_schemas.py \
  core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): secrets — snowflake_dsn payload kind"
```

---

## Task 3: `materialize_snowflake_connector` — dependency + runtime + manual-only round-trip test

**Files:**
- Modify: `core/pyproject.toml` (add `snowflake-sqlalchemy` dependency + `snowflake` marker)
- Modify: `core/app/pipelines/connector_runtime.py`
- Modify: `core/tests/conftest.py` (add `snowflake_test_dsn` fixture)
- Test: `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Consumes: `app.pipelines.ops.schemas.ReaderConnectorSnowflakeParams`
  (Task 1), `app.secrets.repository.get_secret_payload` (existing),
  `app.analytics.sql_sandbox.{parse_ast,validate_select_only,SqlSandboxError}`
  (existing, already imported by this file), `app.pipelines.connector_runtime.{_resolve_secret,_run_dlt_and_attach,ConnectorRuntimeError}`
  (existing, unchanged).
- Produces: `app.pipelines.connector_runtime.materialize_snowflake_connector(conn, *, session, tenant_id, node_id, params, view_name) -> None`.
  Consumed by Task 4 (`runtime.py`'s `_read_connector_snowflake`).

- [ ] **Step 1: Add the `snowflake-sqlalchemy` dependency and the `snowflake` pytest marker**

Modify `core/pyproject.toml` — in `dependencies = [...]`, add after the
`dlt>=1.6` entry:

```toml
    "snowflake-sqlalchemy>=1.11,<2",  # GAP-16 : reader.connector.snowflake —
                       # dialecte SQLAlchemy pour un entrepôt Snowflake
                       # distant, résolu automatiquement par
                       # sa.create_engine("snowflake://...") via les entry
                       # points du paquet (aucun import explicite requis
                       # dans ce dépôt). Borne haute délibérée : 2.0.0a2 est
                       # une pré-version alpha au moment de cet ajout —
                       # jamais installée silencieusement par une
                       # résolution de dépendances. Apache-2.0, comme sa
                       # dépendance transitive snowflake-connector-python
                       # (vérifiées toutes deux sur PyPI).
```

In the `markers = [...]` list (`[tool.pytest.ini_options]`), add after the
existing `qgis` entry:

```toml
    "snowflake: nécessite un compte Snowflake réel (CORE_TEST_SNOWFLAKE_DSN) ; "
    "skippé sinon — JAMAIS câblé en CI (service cloud propriétaire, pas de "
    "sidecar auto-hébergeable équivalent au qgis-worker) ; manuel uniquement",
```

Run: `cd core && uv sync`
Expected: resolves; `snowflake-sqlalchemy` (1.11.x) and its transitive
`snowflake-connector-python` (<5.0.0) are installed. No version conflict
with existing `cryptography>=42.0`/`requests>=2.31`/`pyjwt[crypto]>=2.8`
(design §7 — verified compatible transitively before writing this plan).

- [ ] **Step 2: Add the `snowflake_test_dsn` fixture**

Modify `core/tests/conftest.py` — add after the existing `qgis_scratch_dir`
fixture:

```python
@pytest.fixture(scope="session")
def snowflake_test_dsn():
    # GAP-16 : contrairement à pg_engine (un conteneur postgis-test réel est
    # toujours disponible dans cet environnement) ou qgis_worker_url (un
    # sidecar Docker OSS auto-hébergeable), il n'existe pas d'émulateur
    # Snowflake officiel — ce fixture ne skippe donc JAMAIS pour une raison
    # temporaire : il documente une limite permanente (design §12).
    dsn = os.environ.get("CORE_TEST_SNOWFLAKE_DSN")
    if not dsn:
        pytest.skip(
            "CORE_TEST_SNOWFLAKE_DSN non défini — test snowflake skippé "
            "(manuel uniquement, jamais câblé en CI, GAP-16)"
        )
    return dsn
```

- [ ] **Step 3: Write the failing tests**

Add one import line to `core/tests/test_pipeline_connector_runtime.py`,
immediately after the existing
`from app.pipelines.ops.schemas import ReaderConnectorPostgresParams  # noqa: E402`
line (this file's established convention for a param-model import added by
a later op: mid-file, `# noqa: E402` to silence ruff's "not at top of file"
rule rather than reordering the whole file):

```python
from app.pipelines.ops.schemas import ReaderConnectorSnowflakeParams  # noqa: E402
```

Then append at the end of the file:

```python
def test_materialize_snowflake_connector_rejects_non_select(conn, session, tenant):
    params = ReaderConnectorSnowflakeParams(secretName="does-not-matter", query="DELETE FROM towns")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="query rejected"):
        connector_runtime.materialize_snowflake_connector(
            conn,
            session=session,
            tenant_id=tenant.id,
            node_id="sf1",
            params=params,
            view_name="node_sf1",
        )


def test_materialize_snowflake_connector_wrong_secret_kind_raises(conn, session, tenant, user):
    _create_secret(
        session,
        tenant,
        user,
        name="bearer-secret",
        kind="bearer_token",
        payload={"kind": "bearer_token", "token": "tok"},
    )
    params = ReaderConnectorSnowflakeParams(secretName="bearer-secret", query="SELECT 1")
    with pytest.raises(
        connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.snowflake"
    ):
        connector_runtime.materialize_snowflake_connector(
            conn,
            session=session,
            tenant_id=tenant.id,
            node_id="sf2",
            params=params,
            view_name="node_sf2",
        )


def test_materialize_snowflake_connector_missing_secret_raises(conn, session, tenant):
    params = ReaderConnectorSnowflakeParams(secretName="does-not-exist", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_snowflake_connector(
            conn,
            session=session,
            tenant_id=tenant.id,
            node_id="sf3",
            params=params,
            view_name="node_sf3",
        )


def test_snowflake_dialect_resolves_lazily_without_network():
    # Vérifie la forme du DSN (design §2.2/§3.3) sans se connecter à un
    # compte réel : sa.create_engine() est paresseux (aucun appel réseau
    # avant .connect()) — ce test échouerait si snowflake-sqlalchemy
    # n'était pas installé, ou si le DSN n'était pas de la forme attendue.
    # Aucune fixture DB nécessaire (pas de session, pas de connexion) —
    # import local de sqlalchemy, même convention que le `from sqlalchemy
    # import text` local de test_materialize_postgres_connector_round_trips_query
    # dans ce même fichier (aucun import sqlalchemy au niveau module ici).
    import sqlalchemy as sa

    engine = sa.create_engine(
        "snowflake://u:s3cr3t-pass@myaccount/mydb/myschema?warehouse=wh1&role=role1"
    )
    try:
        assert engine.dialect.name == "snowflake"
        assert "s3cr3t-pass" not in str(engine.url)  # le mot de passe est masqué par défaut
    finally:
        engine.dispose()


@pytest.mark.snowflake
def test_materialize_snowflake_connector_round_trips_query(conn, session, tenant, user, snowflake_test_dsn):
    # MANUEL UNIQUEMENT (design §12/§3.3, Global Constraints) : requiert un
    # compte Snowflake réel, jamais câblé en CI. La table `sp_gap16_towns`
    # doit exister dans le schéma/warehouse référencé par
    # CORE_TEST_SNOWFLAKE_DSN avec au moins les colonnes (id int, name
    # varchar) — à créer manuellement une fois avant de lancer ce test :
    #   CREATE OR REPLACE TABLE sp_gap16_towns (id INT, name VARCHAR);
    #   INSERT INTO sp_gap16_towns VALUES (1, 'Nord'), (2, 'Sud');
    _create_secret(
        session,
        tenant,
        user,
        name="warehouse-sf",
        kind="snowflake_dsn",
        payload={"kind": "snowflake_dsn", "dsn": snowflake_test_dsn},
    )
    params = ReaderConnectorSnowflakeParams(
        secretName="warehouse-sf", query="SELECT id, name FROM sp_gap16_towns ORDER BY id"
    )
    connector_runtime.materialize_snowflake_connector(
        conn, session=session, tenant_id=tenant.id, node_id="sf4", params=params, view_name="node_sf4",
    )
    rows = conn.execute("SELECT id, name FROM node_sf4 ORDER BY id").fetchall()
    assert rows == [(1, "Nord"), (2, "Sud")]
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k snowflake -v`
Expected: 5 collected, mixed outcome —
`test_materialize_snowflake_connector_rejects_non_select`,
`test_materialize_snowflake_connector_wrong_secret_kind_raises`,
`test_materialize_snowflake_connector_missing_secret_raises` FAIL with
`AttributeError: module 'app.pipelines.connector_runtime' has no attribute
'materialize_snowflake_connector'` (the function doesn't exist yet);
`test_snowflake_dialect_resolves_lazily_without_network` already **PASSES**
at this point — it only exercises `sa.create_engine`, which Step 1's
dependency install already satisfies, not
`materialize_snowflake_connector` — this is expected, not a mistake;
`test_materialize_snowflake_connector_round_trips_query` SKIPPED (not
failed) — `CORE_TEST_SNOWFLAKE_DSN` is unset in this environment, exactly
as intended; do not attempt to unskip it.

- [ ] **Step 5: Implement `materialize_snowflake_connector`**

Modify `core/app/pipelines/connector_runtime.py` — add the import (next to
the existing `ReaderConnectorPostgresParams, ReaderConnectorRestParams`
import):

```python
from app.pipelines.ops.schemas import (
    ReaderConnectorPostgresParams,
    ReaderConnectorRestParams,
    ReaderConnectorSnowflakeParams,
)
```

Append at the end of the file (after `materialize_postgres_connector`):

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
    # Pendant exact de materialize_postgres_connector (GAP-16 design §3.1) —
    # même heuristique SELECT-only, même défense en profondeur documentée :
    # `params.query` cible Snowflake mais est parsée avec le dialecte SQL de
    # DuckDB, pas SnowSQL (limites vérifiées empiriquement, design §5.3).
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
        # Aucun import de snowflake.sqlalchemy : le paquet s'enregistre
        # comme dialecte SQLAlchemy via ses entry points au moment de
        # l'installation (vérifié empiriquement, design §3.3) — même
        # patron que le dialecte "postgresql" ci-dessus, jamais importé
        # explicitement non plus.
        engine = sa.create_engine(payload.dsn)
        try:
            with engine.connect() as db_conn:
                rows = db_conn.execution_options(yield_per=1000).exec_driver_sql(params.query)
                yield from (dict(row._mapping) for row in rows)
        finally:
            engine.dispose()

    _run_dlt_and_attach(conn, _records, node_id=node_id, view_name=view_name)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -v`
Expected: all pass (existing REST/Postgres tests unaffected; the four new
non-manual Snowflake tests pass; `test_materialize_snowflake_connector_round_trips_query`
SKIPPED with the message from Step 4).

- [ ] **Step 7: Run the full core test suite to confirm no regression**

Run: `cd core && uv run pytest -v`
Expected: same pass/skip count as before this task, plus the 5 new tests
(4 passed, 1 skipped) — purely additive.

- [ ] **Step 8: Verify no accidental import of `snowflake.sqlalchemy`**

Run: `cd core && grep -rn "import snowflake" app/`
Expected: no output — confirms the "no explicit import" Global Constraint
held in the actual diff, not just in this plan's prose.

- [ ] **Step 9: Commit**

```bash
git add core/pyproject.toml core/uv.lock core/tests/conftest.py \
  core/app/pipelines/connector_runtime.py core/tests/test_pipeline_connector_runtime.py
git commit -m "feat(core): pipelines — reader.connector.snowflake materialization (SELECT-only guard)"
```

---

## Task 4: Wire into the runtime dispatch — `runtime.py` / `registries.py`

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Modify: `core/app/pipelines/registries.py`
- Test: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: `app.pipelines.connector_runtime.materialize_snowflake_connector`,
  `ConnectorRuntimeError` (Task 3); `ReaderConnectorSnowflakeParams` (Task 1).
- Produces: no new public interface — `READERS["reader.connector.snowflake"]`
  now dispatches to a real function. Terminal task of the core-side work.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_pipeline_runtime.py` (mirrors the existing
`test_preview_reader_connector_missing_secret_raises_pipeline_runtime_error`
exactly, substituting the op):

```python
def test_preview_reader_connector_snowflake_missing_secret_raises_pipeline_runtime_error(tmp_path):
    # w1 satisfies PipelinePayload's "at least one writer node" structural
    # validator; never reached — preview_pipeline(up_to="r1") stops the
    # chain at r1, and _prepare() raises on the missing secret while
    # materializing readers, before any writer is touched. Proves the
    # registries.py wiring end-to-end, not just materialize_snowflake_connector
    # in isolation (already covered by Task 3).
    payload_nodes = [
        {
            "id": "r1",
            "kind": "reader",
            "op": "reader.connector.snowflake",
            "params": {"secretName": "does-not-exist", "query": "SELECT 1"},
        },
        {
            "id": "w1",
            "kind": "writer",
            "op": "writer.export",
            "params": {"format": "csv", "key": "out.csv"},
        },
    ]
    edges = [{"id": "e1", "from": "r1", "to": "w1"}]
    from app.configs.schemas import PipelinePayload

    payload = PipelinePayload.model_validate({"nodes": payload_nodes, "edges": edges})

    from app.db import init_db, make_session_factory
    from app.tenants.repository import get_or_create_default_tenant

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        with pytest.raises(runtime.PipelineRuntimeError, match="not found"):
            runtime.preview_pipeline(
                session=session,
                payload=payload,
                tenant_id=tenant.id,
                user=None,
                up_to="r1",
                endpoint_url="http://localhost:9000",
                access_key="x",
                secret_key="y",
                base_uri=str(tmp_path),
                limit=50,
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k snowflake -v`
Expected: FAIL — `KeyError: 'reader.connector.snowflake'` (`registries.py`'s
`READERS` dict has no such key yet, so `_prepare()`'s `READERS[node.op]`
lookup raises before ever reaching a `PipelineRuntimeError`).

- [ ] **Step 3: Add `_read_connector_snowflake` to `runtime.py`**

Modify `core/app/pipelines/runtime.py` — extend the existing
`app.pipelines.ops.schemas` import block (add one name, keeping alphabetical
order among the `ReaderConnector*` entries):

```python
from app.pipelines.ops.schemas import (
    ReaderCollectionParams,
    ReaderConnectorPostgresParams,
    ReaderConnectorRestParams,
    ReaderConnectorSnowflakeParams,
    TransformAggregateParams,
    TransformCountWithinParams,
    TransformDeriveParams,
    TransformFilterParams,
    TransformH3AggregateParams,
    TransformIntersectionParams,
    TransformJoinParams,
    TransformMergeParams,
    TransformQgisParams,
    WriterCollectionParams,
    WriterDatasetParams,
    WriterExportParams,
)
```

Add a new function immediately after `_read_connector_postgres`:

```python
def _read_connector_snowflake(
    conn,
    *,
    session: Session,
    tenant_id: str,
    node_id: str,
    params: dict,
    view_name: str,
    user: User,
    base_uri: str,
) -> int:
    """reader.connector.snowflake (registre READERS) — pendant de
    _read_connector_postgres, même rationale (GAP-16)."""
    p = ReaderConnectorSnowflakeParams.model_validate(params)
    try:
        connector_runtime.materialize_snowflake_connector(
            conn,
            session=session,
            tenant_id=tenant_id,
            node_id=node_id,
            params=p,
            view_name=view_name,
        )
    except connector_runtime.ConnectorRuntimeError as exc:
        raise PipelineRuntimeError(str(exc)) from exc
    return 4326
```

- [ ] **Step 4: Wire it into `registries.py`**

Modify `core/app/pipelines/registries.py` — add one entry to `READERS`:

```python
READERS: dict[str, Callable] = {
    "reader.collection": _runtime._read_collection,
    "reader.connector.rest": _runtime._read_connector_rest,
    "reader.connector.postgres": _runtime._read_connector_postgres,
    "reader.connector.snowflake": _runtime._read_connector_snowflake,
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -v`
Expected: all pass, including the new end-to-end Snowflake test.

- [ ] **Step 6: Verify the layering contract still holds**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.` — no new inter-module import
direction introduced (`runtime.py` already imports `connector_runtime`;
`registries.py` already imports `runtime` at module level, unchanged
shape).

- [ ] **Step 7: Run the full core test suite to confirm no regression**

Run: `cd core && uv run pytest -v`
Expected: all pre-existing tests still pass, plus this task's new test —
purely additive (one new dict entry, one new function, no existing
behavior changed).

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/runtime.py core/app/pipelines/registries.py \
  core/tests/test_pipeline_runtime.py
git commit -m "feat(core): pipelines — wire reader.connector.snowflake into READERS dispatch"
```

---

## Task 5: Shell — `snowflake_dsn` secret kind in `SecretParamSelect`

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/builder/pipeline/SecretParamSelect.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/SecretParamSelect.test.tsx`

**Interfaces:**
- Produces: `SecretPayload` (shell type) gains
  `| { kind: "snowflake_dsn"; dsn: string }`. `SecretParamSelect`'s create
  form accepts `kind="snowflake_dsn"`.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/pipeline/SecretParamSelect.test.tsx` (mirrors
the existing `"un nouveau secret créé est immédiatement sélectionné"` test,
which uses `kindFilter: "smtp"` — this one uses `kindFilter:
"snowflake_dsn"`):

```typescript
test("un secret snowflake_dsn créé est immédiatement sélectionné", async () => {
  const createSecret = vi.fn().mockResolvedValue({
    id: "s9",
    name: "warehouse-sf",
    kind: "snowflake_dsn",
    createdAt: "",
    updatedAt: "",
  });
  const { onChange } = renderSelect({ kindFilter: "snowflake_dsn" }, { createSecret });
  await userEvent.click(screen.getByText("Créer un secret"));
  await userEvent.type(screen.getByLabelText("Nom"), "warehouse-sf");
  await userEvent.type(
    screen.getByLabelText("DSN"),
    "snowflake://u:p@myaccount/mydb/myschema?warehouse=wh1",
  );
  await userEvent.click(screen.getByText("Créer"));

  await waitFor(() => expect(onChange).toHaveBeenCalledWith("warehouse-sf"));
  expect(createSecret).toHaveBeenCalledWith({
    name: "warehouse-sf",
    payload: {
      kind: "snowflake_dsn",
      dsn: "snowflake://u:p@myaccount/mydb/myschema?warehouse=wh1",
    },
  });
});
```

(Mirrors the neighboring `"un nouveau secret créé est immédiatement
sélectionné"` (`smtp`) test in this same file exactly — click
`"Créer un secret"` first to reveal the create form, then fill fields, then
click `"Créer"`. `userEvent`/`waitFor`/`vi` imports and the
`renderSelect(props, overrides)` helper already exist in this file; reuse
them as-is, do not redefine. No `kindFilter` type dropdown to interact with
here since `kindFilter="snowflake_dsn"` hides it, same as the `smtp` test's
`kindFilter="smtp"`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/SecretParamSelect.test.tsx -t snowflake_dsn`
Expected: FAIL — `TestingLibraryElementError: Unable to find a label with
the text of: DSN` (vitest transpiles via esbuild without type-checking, so
the `kindFilter: "snowflake_dsn"` type error doesn't surface here; the real
runtime failure is that the JSX condition gating the DSN field is still
`kind === "postgres_dsn"` only — it never renders for `kind ===
"snowflake_dsn"`). Confirm separately with
`cd shell && npx tsc --noEmit` (Step 7) that the type itself is also
rejected before this task's changes.

- [ ] **Step 3: Add the type**

Modify `shell/src/api/types.ts` — extend the `SecretPayload` union:

```typescript
export type SecretPayload =
  | { kind: "api_key"; location: "header" | "query"; key: string; value: string }
  | { kind: "bearer_token"; token: string }
  | { kind: "basic_auth"; username: string; password: string }
  | { kind: "oauth2_client_credentials"; tokenUrl: string; clientId: string; clientSecret: string }
  | { kind: "postgres_dsn"; dsn: string }
  | {
      kind: "smtp";
      host: string;
      port: number;
      username: string;
      password: string;
      useTls: boolean;
      fromAddress: string;
    }
  | { kind: "snowflake_dsn"; dsn: string };
```

Also extend `PipelineOpEntry.paramsSchema` (needed by Task 6, bundled here
since it's the same file/area — a one-line additive type change):

```typescript
export type PipelineOpEntry = {
  kind: PipelineNodeKind;
  paramsSchema: {
    properties: Record<string, PipelineOpParamProperty>;
    required?: string[];
    description?: string;
  };
  acceptsSecondaryInput?: boolean;
};
```

- [ ] **Step 4: Add the kind to `SecretParamSelect.tsx`**

Modify `shell/src/builder/pipeline/SecretParamSelect.tsx` — extend
`KIND_LABELS`:

```typescript
const KIND_LABELS: Record<SecretPayload["kind"], string> = {
  api_key: t("secretParamSelect.kindApiKey"),
  bearer_token: t("secretParamSelect.kindBearerToken"),
  basic_auth: t("secretParamSelect.kindBasicAuth"),
  oauth2_client_credentials: t("secretParamSelect.kindOAuth2"),
  postgres_dsn: t("secretParamSelect.kindPostgresDsn"),
  smtp: t("secretParamSelect.kindSmtp"),
  snowflake_dsn: t("secretParamSelect.kindSnowflakeDsn"),
};
```

Extend `buildPayload()`'s switch — replace the `case "postgres_dsn":` arm:

```typescript
      case "postgres_dsn":
      case "snowflake_dsn":
        return { kind, dsn: field("dsn") };
```

Widen the JSX condition for the `dsn` field (currently
`{kind === "postgres_dsn" && (...)}`):

```typescript
      {(kind === "postgres_dsn" || kind === "snowflake_dsn") && (
        <label className="flex flex-col gap-1 text-xs">
          {t("secretParamSelect.dsnLabel")}
          <input
            aria-label={t("secretParamSelect.dsnAria")}
            type="password"
            className="h-8 rounded border border-rule bg-surface px-2 text-ink"
            value={field("dsn")}
            onChange={(e) => setFieldValue("dsn", e.target.value)}
          />
        </label>
      )}
```

- [ ] **Step 5: Add the i18n key**

Modify `shell/src/i18n/catalog.fr.ts` — add near `secretParamSelect.kindSmtp`:

```typescript
  "secretParamSelect.kindSnowflakeDsn": "DSN Snowflake",
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/pipeline/SecretParamSelect.test.tsx`
Expected: all pass, including the new `snowflake_dsn` test.

- [ ] **Step 7: Run `tsc --noEmit` to confirm no exhaustiveness break elsewhere**

Run: `cd shell && npx tsc --noEmit`
Expected: no errors — `SecretParamSelect.tsx` was the only file with a
`Record<SecretPayload["kind"], ...>` exhaustive mapping (confirmed by
`grep -rn 'SecretPayload\[.kind.\]\|Record<SecretPayload' src/` before
writing this plan); every other consumer of `SecretPayload` is structural
(no exhaustive switch/Record over its kind), so no other file needs a
change.

- [ ] **Step 8: Commit**

```bash
git add shell/src/api/types.ts shell/src/builder/pipeline/SecretParamSelect.tsx \
  shell/src/i18n/catalog.fr.ts shell/src/builder/pipeline/SecretParamSelect.test.tsx
git commit -m "feat(shell): builder — snowflake_dsn secret kind in SecretParamSelect"
```

---

## Task 6: Shell — palette tooltip from `paramsSchema.description` (carries the Redshift hint)

**Files:**
- Modify: `shell/src/builder/pipeline/PipelinePalette.tsx`
- Test: `shell/src/builder/pipeline/PipelinePalette.test.tsx`

**Interfaces:**
- Consumes: `PipelineOpEntry.paramsSchema.description` (Task 5's type
  addition).
- Produces: no new exported interface — the palette entry gains an optional
  `title` attribute.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/pipeline/PipelinePalette.test.tsx` (add a
`description` to one catalog entry, none to another, to prove the rendering
is conditional and generic — not hardcoded to a specific op name):

```typescript
test("op entries with a paramsSchema.description get it as a hover title", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const catalogWithDescription: PipelineOpsCatalog = {
    ...CATALOG,
    "reader.connector.postgres": {
      kind: "reader",
      paramsSchema: {
        properties: {},
        required: [],
        description: "Fonctionne également contre un cluster Amazon Redshift.",
      },
    },
  };
  const client: Partial<ItemClient> = {
    getPipelineOps: () => Promise.resolve(catalogWithDescription),
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePalette />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(screen.getByText("reader.connector.postgres")).toBeInTheDocument(),
  );
  const entryWithDescription = screen
    .getByText("reader.connector.postgres")
    .closest("[draggable]") as HTMLElement;
  expect(entryWithDescription).toHaveAttribute(
    "title",
    "Fonctionne également contre un cluster Amazon Redshift.",
  );

  // Entry with no description (e.g. "reader.collection" from CATALOG) gets
  // no title attribute at all — never an empty string, which some screen
  // readers/tools would still surface as an (empty) tooltip.
  const entryWithoutDescription = screen
    .getByText("reader.collection")
    .closest("[draggable]") as HTMLElement;
  expect(entryWithoutDescription).not.toHaveAttribute("title");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelinePalette.test.tsx -t "hover title"`
Expected: FAIL — the draggable `<div>` has no `title` attribute at all
today.

- [ ] **Step 3: Implement the tooltip**

Modify `shell/src/builder/pipeline/PipelinePalette.tsx` — the current
render block is:

```typescript
            {byKind[kind].map((op) => (
              <li key={op}>
                <div
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  className="cursor-grab rounded border border-rule bg-surface px-2 py-1 hover:bg-sunken"
                >
                  {op}
                </div>
              </li>
            ))}
```

Replace with (only the `title` prop is new — every other line unchanged):

```typescript
            {byKind[kind].map((op) => (
              <li key={op}>
                <div
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  title={catalog[op]?.paramsSchema.description}
                  className="cursor-grab rounded border border-rule bg-surface px-2 py-1 hover:bg-sunken"
                >
                  {op}
                </div>
              </li>
            ))}
```

(`title={undefined}` renders no `title` attribute at all in React/the DOM —
confirmed behavior, not an empty-string tooltip — so ops without a
description are unaffected.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelinePalette.test.tsx`
Expected: all pass, including both assertions of the new test (description
present → `title` set; description absent → no `title` attribute).

- [ ] **Step 5: Run the full shell test suite to confirm no regression**

Run: `cd shell && npm run test`
Expected: all pre-existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/pipeline/PipelinePalette.tsx \
  shell/src/builder/pipeline/PipelinePalette.test.tsx
git commit -m "feat(shell): builder — palette entries surface paramsSchema.description as a tooltip"
```

---

## Task 7: End-to-end verification, quality gates, GAP-16 closure bookkeeping

**Files:**
- Modify: `docs/revue/2026-09-04-analyse-gaps.md` (GAP-16 row: Ouvert → Fermé)
- Modify: `docs/revue/2026-09-04-matrice-fonctionnalites.md` (relevant
  column(s) for the connector/entrepôt capability)
- Modify: `CLAUDE.md` (`### Livré` — one line)

No new tests in this task — it verifies what the previous six tasks built,
end to end, and closes the paperwork loop the repo's own house rules
require for a closed GAP.

- [ ] **Step 1: Full core suite**

Run: `cd core && uv run pytest --cov=app --cov-report=xml:coverage.xml`
Expected: all pass except the 5 pre-existing `qgis`-marked skips (no
`CORE_TEST_QGIS_WORKER_URL` in this environment) **plus** this plan's new
`test_materialize_snowflake_connector_round_trips_query` skip (no
`CORE_TEST_SNOWFLAKE_DSN`) — 6 skips total is the new expected baseline,
not a regression. Confirm the skip reasons with:
`uv run pytest -rs | grep -i snowflake`
Expected output contains: `SKIPPED ... CORE_TEST_SNOWFLAKE_DSN non défini`.

- [ ] **Step 2: Static gates (core)**

Run:
```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run lint-imports
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```
Expected: all clean — no new ruff violation, no coverage regression below
the committed threshold, `lint-imports` reports `Contracts: 1 kept, 0
broken.` with zero new exemptions.

- [ ] **Step 3: Full shell suite + build**

Run:
```bash
cd shell
npm run test
npm run lint && npm run format:check
npm run build
```
Expected: all pass; `npm run build`'s bundle-size check
(`scripts/check-bundle-size.mjs`) stays under the committed threshold — this
plan adds no new dependency to the shell bundle (no library added, only
existing UI primitives reused).

- [ ] **Step 4: Confirm the manual-only Snowflake test is documented, not silently expected**

Run: `cd core && uv run pytest --markers | grep -A1 snowflake`
Expected: the `snowflake` marker description from Task 3 appears verbatim.

- [ ] **Step 5: Update `docs/revue/2026-09-04-analyse-gaps.md`**

Find the GAP-16 row and change its status column from `Ouvert` to `Fermé`,
adding a reference to this plan/spec pair (mirror the phrasing style
already used by other closed `GAP-nn` rows in the same table — e.g. "Fermé
— reader.connector.snowflake (2026-09-06), reader.connector.postgres
compatible Redshift sans nouveau code").

- [ ] **Step 6: Update `docs/revue/2026-09-04-matrice-fonctionnalites.md`**

Update the row(s) covering "connecteur entrepôt cloud analytique" to
reflect the new `reader.connector.snowflake` op and the Redshift note,
following the existing column conventions of that file.

- [ ] **Step 7: Add the `### Livré` entry to `CLAUDE.md`**

Add one bullet under `### Livré`, following the exact terse style already
used by neighboring entries — for example:

```markdown
- **GAP-16** — connecteur entrepôt cloud analytique : nouvelle op
  `reader.connector.snowflake` (pendant exact de `reader.connector.postgres`,
  dialecte `snowflake-sqlalchemy` résolu par entry point, aucun nouvel
  import), nouveau kind de secret `snowflake_dsn` ; `reader.connector.postgres`
  documenté et confirmé (littérature AWS, pas un cluster réel disponible en
  session) compatible avec un cluster Amazon Redshift sans aucun nouveau
  code. Databricks/BigQuery restent hors périmètre. Round-trip Snowflake
  réel : `@pytest.mark.snowflake`, jamais câblé en CI (pas d'émulateur
  auto-hébergeable), manuel uniquement.
```

- [ ] **Step 8: Commit the documentation updates**

```bash
git add docs/revue/2026-09-04-analyse-gaps.md \
  docs/revue/2026-09-04-matrice-fonctionnalites.md CLAUDE.md
git commit -m "docs: cloture GAP-16 (connecteur entrepot cloud analytique)"
```

---

## Summary of what remains manual / unverified in this environment (do not claim otherwise)

- **`test_materialize_snowflake_connector_round_trips_query`** (Task 3):
  never runs in CI, never ran in this plan's authoring session — requires a
  real Snowflake trial account and `CORE_TEST_SNOWFLAKE_DSN` set by hand,
  plus the one-time `CREATE TABLE sp_gap16_towns (...)` step documented in
  the test's own docstring.
- **Redshift compatibility** (design §5.4): backed by AWS's own
  documentation (quoted verbatim in the design doc) and the fact that
  `sqlalchemy-redshift`'s own dialect is built on `psycopg2` — never
  verified against a real Redshift cluster in this plan, and structurally
  unverifiable in CI (paid AWS service, no emulator).
