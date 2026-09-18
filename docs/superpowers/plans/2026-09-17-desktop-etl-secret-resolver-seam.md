# Desktop ETL — seam `SecretResolver` (socle sidecar, tranche 1) — plan

> **Pour les agents d'exécution :** SOUS-COMPÉTENCE REQUISE : utiliser
> superpowers:subagent-driven-development (recommandé) ou
> superpowers:executing-plans pour exécuter ce plan tâche par tâche. Les
> étapes utilisent la syntaxe case à cocher (`- [ ]`) pour le suivi.

**Objectif :** découpler `core/app/pipelines/connector_runtime.py` de son
import direct de `app.secrets.repository` (Postgres) en introduisant un
Protocol `SecretResolver` injecté, avec une implémentation Postgres par
défaut équivalente au comportement actuel. C'est le seul « vrai point de
couplage » identifié par
[`docs/superpowers/specs/2026-09-17-desktop-etl-standalone-design.md`](../specs/2026-09-17-desktop-etl-standalone-design.md)
§3 avant qu'un futur sidecar desktop (trousseau OS, pas de Postgres) puisse
réutiliser le même moteur de pipeline sans fork.

**Architecture :** `connector_runtime.py` gagne un Protocol `SecretResolver`
(`get(name: str) -> SecretPayload`) et une implémentation
`PostgresSecretResolver` (même requête que l'actuel `_resolve_secret`). Les 3
fonctions `materialize_*_connector` reçoivent désormais `secret_resolver`
au lieu de `session`/`tenant_id`. `runtime.py` (seul appelant de ces 3
fonctions) construit le résolveur Postgres au point d'appel — signature
uniforme du registre `READERS` (`registries.py`) inchangée, donc **aucun
changement de comportement observable côté route REST/MCP**. C'est
uniquement la tranche « seam secrets » de la phase « socle sidecar » du
design (§11) — la tranche suivante (API loopback HTTP + extraction
`defer_task`) est un plan séparé, cette API n'étant pas encore spécifiée à
un niveau assez précis pour être planifiée avec du code exact (ports HTTP,
forme SSE, tracking de run en mémoire — cf. § "Découpage attendu" du design).

**Tech Stack :** Python 3.12, `typing.Protocol`, SQLAlchemy `Session`,
pytest (fixtures `session`/`tenant`/`conn`/`httpserver` déjà présentes dans
`tests/test_pipeline_connector_runtime.py`).

## Global Constraints

- TDD systématique (CLAUDE.md « Comment on travaille ») : pour un
  refactor de signature comme celui-ci, le "rouge" est la suite de tests
  existante qui casse après le changement de production — vérifié
  explicitement à chaque tâche avant de corriger les appelants.
- Commits conventionnels, petits, un sujet par commit
  (`refactor(core): …`), message se terminant par
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Docs et commentaires en français, code/identifiants en anglais (cf.
  conventions déjà en usage dans `connector_runtime.py`/`runtime.py`).
- **Aucun changement de comportement observable** : aucune route REST,
  aucun outil MCP, aucun schéma Pydantic exposé ne change. La signature du
  registre `READERS` (`registries.py`) reste
  `(conn, *, session, tenant_id, node_id, params, view_name, user,
  base_uri) -> int` à l'identique — seul l'intérieur des 3
  `_read_connector_*` change.
- `core/app/pipelines/` n'est pas dans le périmètre `mypy --strict` listé
  dans `CLAUDE.md` (`app/auth app/secrets app/analytics app/copilot
  app/admin_tools app/roles`) — pas d'obligation de typage strict
  supplémentaire au-delà de ce que ce plan spécifie.
- Ne pas introduire d'abstraction au-delà de ce que le design demande
  (un seul Protocol, une seule implémentation par défaut) — YAGNI, pas de
  registre de résolveurs, pas de config par variable d'environnement dans
  cette tranche.
- Lancer `cd core && uv run pytest tests/test_pipeline_connector_runtime.py tests/test_pipeline_runtime.py -q`
  avant chaque commit de tâche impactant ces fichiers ; ce sont des tests
  `postgis`-marqués en partie (fixture `pg_engine`/`pg_secret`) — s'ils
  skippent silencieusement faute de `CORE_TEST_DATABASE_URL`, le noter dans
  le rapport de tâche plutôt que de déclarer la tâche verte sans réserve
  (piège CLAUDE.md « Pièges récurrents » #3/#12).

---

## File Structure

- **Modifie `core/app/pipelines/connector_runtime.py`** : ajoute
  `SecretResolver` (Protocol) + `PostgresSecretResolver` (implémentation par
  défaut) ; change la signature de `_resolve_secret` et des 3
  `materialize_*_connector`.
- **Modifie `core/app/pipelines/runtime.py`** : les 3 fonctions
  `_read_connector_rest`/`_read_connector_postgres`/`_read_connector_snowflake`
  construisent `PostgresSecretResolver(session, tenant_id)` et le passent en
  `secret_resolver=` au lieu de `session=`/`tenant_id=`.
- **Modifie `core/scripts/pipeline_sidecar_spike.py`** : son unique appel à
  `materialize_rest_connector` passe désormais `secret_resolver=None` au
  lieu de `session=None, tenant_id="spike"`.
- **Modifie `core/tests/test_pipeline_connector_runtime.py`** : 19 sites
  d'appel à `materialize_*_connector` passent `secret_resolver=` construit
  inline au lieu de `session=`/`tenant_id=`. Ajoute 2 tests unitaires pour
  `PostgresSecretResolver`.
- **Ne modifie pas** `registries.py`, `routes.py`, `service.py`, `jobs.py`,
  ni aucun schéma Pydantic exposé.

---

### Task 1 : `SecretResolver` Protocol + `PostgresSecretResolver` (additif, ne casse rien)

**Files:**
- Modify: `core/app/pipelines/connector_runtime.py`
- Test: `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Produces: `connector_runtime.SecretResolver` (Protocol, méthode
  `get(self, name: str) -> SecretPayload`, lève `KeyError` si absent) ;
  `connector_runtime.PostgresSecretResolver(session: Session, tenant_id: str)`
  avec la même méthode `get`.
- Consumes: `app.secrets.repository.get_secret_payload(session, *,
  tenant_id, name) -> SecretPayload | None` (déjà importé dans ce fichier
  sous `secrets_repo`).

- [ ] **Step 1: Écrire les tests qui échouent (import inexistant)**

Ajouter à la fin de `core/tests/test_pipeline_connector_runtime.py` :

```python
def test_postgres_secret_resolver_get_returns_payload(session, tenant, user):
    _create_secret(
        session,
        tenant,
        user,
        name="my-bearer",
        kind="bearer_token",
        payload={"kind": "bearer_token", "token": "s3cr3t-tok"},
    )
    resolver = connector_runtime.PostgresSecretResolver(session, tenant.id)
    payload = resolver.get("my-bearer")
    assert payload.kind == "bearer_token"
    assert payload.token == "s3cr3t-tok"


def test_postgres_secret_resolver_get_raises_keyerror_when_missing(session, tenant):
    resolver = connector_runtime.PostgresSecretResolver(session, tenant.id)
    with pytest.raises(KeyError):
        resolver.get("does-not-exist")
```

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k postgres_secret_resolver -v`
Expected: FAIL avec `AttributeError: module 'app.pipelines.connector_runtime' has no attribute 'PostgresSecretResolver'`

- [ ] **Step 3: Ajouter le Protocol et l'implémentation par défaut**

Dans `core/app/pipelines/connector_runtime.py`, ajouter l'import et les deux
classes juste avant `class ConnectorRuntimeError(Exception):` (ligne 57) :

```python
from typing import Protocol

...

class SecretResolver(Protocol):
    """Seam introduit pour découpler ce module de app.secrets.repository
    (Postgres, tenant-scopé) — un futur runtime hors serveur (sidecar
    desktop sans Postgres, design 2026-09-17 §3/§6) fournira sa propre
    implémentation (trousseau OS) sans toucher ce module une deuxième fois."""

    def get(self, name: str) -> SecretPayload: ...


class PostgresSecretResolver:
    """Implémentation par défaut, utilisée par le cœur serveur — même
    requête que l'ancien _resolve_secret(session, tenant_id, ...)."""

    def __init__(self, session: Session, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def get(self, name: str) -> SecretPayload:
        payload = secrets_repo.get_secret_payload(
            self._session, tenant_id=self._tenant_id, name=name
        )
        if payload is None:
            raise KeyError(name)
        return payload
```

(`from typing import Protocol` va avec les imports stdlib en tête de
fichier, juste après `import uuid` ligne 18 — pas au milieu du fichier.)

- [ ] **Step 4: Vérifier que les tests passent**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k postgres_secret_resolver -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Suite complète du fichier (doit rester verte — rien d'autre n'a changé)**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -q`
Expected: tous les tests déjà existants PASS (cette tâche est purement
additive, aucune signature existante n'a encore changé).

- [ ] **Step 6: Commit**

```bash
cd core
git add app/pipelines/connector_runtime.py tests/test_pipeline_connector_runtime.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute le Protocol SecretResolver au moteur de connecteurs

Prépare la réutilisation de connector_runtime.py par un futur sidecar
desktop sans Postgres (design 2026-09-17 §3) : PostgresSecretResolver
reproduit à l'identique le comportement actuel de _resolve_secret, point
d'extension pour une implémentation trousseau OS à venir. Additif, aucune
signature existante ne change à cette étape.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2 : `materialize_*_connector` prennent `secret_resolver` au lieu de `session`/`tenant_id`

**Files:**
- Modify: `core/app/pipelines/connector_runtime.py`
- Modify: `core/tests/test_pipeline_connector_runtime.py`
- Modify: `core/scripts/pipeline_sidecar_spike.py`

**Interfaces:**
- Consumes: `connector_runtime.SecretResolver`/`PostgresSecretResolver`
  (Task 1).
- Produces: nouvelles signatures —
  `materialize_rest_connector(conn, *, secret_resolver: SecretResolver | None, node_id: str, params: ReaderConnectorRestParams, view_name: str) -> None`,
  `materialize_postgres_connector(conn, *, secret_resolver: SecretResolver | None, node_id: str, params: ReaderConnectorPostgresParams, view_name: str) -> None`,
  `materialize_snowflake_connector(conn, *, secret_resolver: SecretResolver | None, node_id: str, params: ReaderConnectorSnowflakeParams, view_name: str) -> None`.
  `secret_resolver` reste optionnel (`None`) uniquement pour le cas où
  `params.secretName is None` (REST non-authentifié) — préserve le
  comportement du spike PyInstaller qui n'a pas de session DB du tout.

- [ ] **Step 1: Modifier `_resolve_secret` pour consommer le resolver**

Dans `core/app/pipelines/connector_runtime.py`, remplacer (lignes 63-71) :

```python
def _resolve_secret(
    session: Session, tenant_id: str, secret_name: str | None
) -> SecretPayload | None:
    if secret_name is None:
        return None
    payload = secrets_repo.get_secret_payload(session, tenant_id=tenant_id, name=secret_name)
    if payload is None:
        raise ConnectorRuntimeError(f"secret '{secret_name}' not found")
    return payload
```

par :

```python
def _resolve_secret(
    resolver: SecretResolver | None, secret_name: str | None
) -> SecretPayload | None:
    if secret_name is None:
        return None
    assert resolver is not None, "secret_resolver requis quand secretName est renseigné"
    try:
        return resolver.get(secret_name)
    except KeyError:
        raise ConnectorRuntimeError(f"secret '{secret_name}' not found") from None
```

- [ ] **Step 2: Modifier les 3 signatures `materialize_*_connector`**

Dans le même fichier, `materialize_rest_connector` (ligne 217) :

```python
def materialize_rest_connector(
    conn,
    *,
    secret_resolver: SecretResolver | None,
    node_id: str,
    params: ReaderConnectorRestParams,
    view_name: str,
) -> None:
    payload = _resolve_secret(secret_resolver, params.secretName)
```

(reste du corps de la fonction inchangé — `auth = _build_auth(payload)` etc.)

`materialize_postgres_connector` (ligne 244) :

```python
def materialize_postgres_connector(
    conn,
    *,
    secret_resolver: SecretResolver | None,
    node_id: str,
    params: ReaderConnectorPostgresParams,
    view_name: str,
) -> None:
    try:
        validate_select_only(parse_ast(conn, params.query))
    except SqlSandboxError as exc:
        raise ConnectorRuntimeError(f"reader.connector.postgres query rejected: {exc}") from exc

    payload = _resolve_secret(secret_resolver, params.secretName)
```
(reste du corps inchangé)

`materialize_snowflake_connector` (ligne 283) : même transformation —
`session: Session, tenant_id: str,` → `secret_resolver: SecretResolver | None,`
dans la signature, et `payload = _resolve_secret(secret_resolver, params.secretName)`
à la place de `payload = _resolve_secret(session, tenant_id, params.secretName)`.

- [ ] **Step 3: Vérifier que la suite casse (confirme le couplage réel)**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -q`
Expected: FAIL — `TypeError: materialize_rest_connector() got an unexpected
keyword argument 'session'` (et pareil pour postgres/snowflake) sur tous les
tests appelant directement ces fonctions.

- [ ] **Step 4: Corriger les 19 sites d'appel du fichier de test**

```bash
cd core
perl -0pi -e 's/        session=session,\n        tenant_id=tenant\.id,\n/        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),\n/g' tests/test_pipeline_connector_runtime.py
grep -c 'secret_resolver=connector_runtime.PostgresSecretResolver' tests/test_pipeline_connector_runtime.py
```
Expected: la commande `grep -c` imprime `19`.

- [ ] **Step 5: Corriger l'appel du spike PyInstaller**

Dans `core/scripts/pipeline_sidecar_spike.py`, remplacer :

```python
        materialize_rest_connector(
            conn,
            # secretName reste None (défaut) => _resolve_secret court-circuite
            # avant tout accès DB : session=None est donc valide ICI
            # uniquement (cf. Global Constraints du plan).
            session=None,  # type: ignore[arg-type]
            tenant_id="spike",
            node_id="n1",
            params=params,
            view_name="v1",
        )
```

par :

```python
        materialize_rest_connector(
            conn,
            # secretName reste None (défaut) => _resolve_secret court-circuite
            # avant tout accès au resolver : secret_resolver=None est donc
            # valide ICI uniquement (aucune session DB dans ce spike).
            secret_resolver=None,
            node_id="n1",
            params=params,
            view_name="v1",
        )
```

- [ ] **Step 6: Vérifier que tout repasse au vert**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -q`
Expected: PASS (tous les tests, y compris les 2 ajoutés en Task 1).

Run (contrôle non gelé du spike, doit rester valide après le renommage) :
`cd core && PYTHONPATH=. uv run python scripts/pipeline_sidecar_spike.py`
Expected: `OK: 3 rows materialized via reader.connector.rest`, code de
sortie 0.

- [ ] **Step 7: Commit**

```bash
cd core
git add app/pipelines/connector_runtime.py tests/test_pipeline_connector_runtime.py scripts/pipeline_sidecar_spike.py
git commit -m "$(cat <<'EOF'
refactor(core): materialize_*_connector consomment SecretResolver

_resolve_secret et les 3 matérialiseurs de connecteur (rest/postgres/
snowflake) ne dépendent plus directement de session+tenant_id : ils
reçoivent le SecretResolver introduit à l'étape précédente. Comportement
observable inchangé (mêmes messages d'erreur, même court-circuit quand
secretName est absent) — seuls les appelants directs (tests, spike
PyInstaller) sont mis à jour ; app/pipelines/runtime.py (seul appelant de
production) est traité dans la tâche suivante.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3 : `runtime.py` construit le `PostgresSecretResolver` au point d'appel

**Files:**
- Modify: `core/app/pipelines/runtime.py`

**Interfaces:**
- Consumes: `connector_runtime.PostgresSecretResolver` (Task 1),
  `connector_runtime.materialize_{rest,postgres,snowflake}_connector` avec
  la signature `secret_resolver=` (Task 2).
- Produces: aucune interface nouvelle — `_read_connector_rest`/
  `_read_connector_postgres`/`_read_connector_snowflake` gardent
  exactement leur signature actuelle (celle du registre `READERS`), donc
  aucun appelant de `runtime.py` n'est affecté.

- [ ] **Step 1: Modifier les 3 wrappers `_read_connector_*`**

Dans `core/app/pipelines/runtime.py`, `_read_connector_rest` (ligne 240) :

```python
def _read_connector_rest(
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
    """reader.connector.rest (registre READERS) — même comportement que
    l'ancienne branche inline de _prepare(). `user`/`base_uri` ignorés
    (ce reader n'en a pas besoin) : présents uniquement pour que READERS
    expose un appel uniforme à _prepare() (cf. app.pipelines.registries)."""
    p = ReaderConnectorRestParams.model_validate(params)
    resolver = connector_runtime.PostgresSecretResolver(session, tenant_id)
    try:
        connector_runtime.materialize_rest_connector(
            conn,
            secret_resolver=resolver,
            node_id=node_id,
            params=p,
            view_name=view_name,
        )
    except connector_runtime.ConnectorRuntimeError as exc:
        raise PipelineRuntimeError(str(exc)) from exc
    return 4326
```

`_read_connector_postgres` (ligne 270), même transformation :

```python
def _read_connector_postgres(
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
    """reader.connector.postgres (registre READERS) — pendant de
    _read_connector_rest ci-dessus, même rationale."""
    p = ReaderConnectorPostgresParams.model_validate(params)
    resolver = connector_runtime.PostgresSecretResolver(session, tenant_id)
    try:
        connector_runtime.materialize_postgres_connector(
            conn,
            secret_resolver=resolver,
            node_id=node_id,
            params=p,
            view_name=view_name,
        )
    except connector_runtime.ConnectorRuntimeError as exc:
        raise PipelineRuntimeError(str(exc)) from exc
    return 4326
```

`_read_connector_snowflake` (ligne 298), même transformation :

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
    resolver = connector_runtime.PostgresSecretResolver(session, tenant_id)
    try:
        connector_runtime.materialize_snowflake_connector(
            conn,
            secret_resolver=resolver,
            node_id=node_id,
            params=p,
            view_name=view_name,
        )
    except connector_runtime.ConnectorRuntimeError as exc:
        raise PipelineRuntimeError(str(exc)) from exc
    return 4326
```

- [ ] **Step 2: Vérifier la suite runtime complète**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -q`
Expected: PASS, y compris
`test_preview_reader_connector_missing_secret_raises_pipeline_runtime_error`
et `test_preview_reader_connector_snowflake_missing_secret_raises_pipeline_runtime_error`
(chemin bout-en-bout `preview_pipeline` → `_prepare` →
`_read_connector_{postgres,snowflake}` → nouveau resolver → « not found »,
non touché par cette tâche mais premier test à révéler une régression s'il
y en avait une).

- [ ] **Step 3: Suite connecteur (non-régression croisée)**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -q`
Expected: PASS (déjà vérifié en Task 2, revérifié ici après le changement
du seul appelant de production).

- [ ] **Step 4: Commit**

```bash
cd core
git add app/pipelines/runtime.py
git commit -m "$(cat <<'EOF'
refactor(core): runtime.py construit PostgresSecretResolver au point d'appel

Les 3 wrappers _read_connector_{rest,postgres,snowflake} (registre READERS)
gardent leur signature uniforme inchangée ; ils construisent désormais le
SecretResolver Postgres localement avant d'appeler connector_runtime, qui
n'a plus de dépendance directe à app.secrets.repository. Clôt la tranche
"seam secrets" du design desktop-etl (2026-09-17 §3) — comportement
observable strictement inchangé côté route REST/MCP.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4 : suite complète du module pipelines + couverture

**Files:**
- None créé/modifié — vérification uniquement.

- [ ] **Step 1: Suite pipelines complète**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py tests/test_pipeline_runtime.py tests/test_pipeline_routes.py tests/test_pipeline_registries.py -q`

(Adapter la liste aux fichiers de test réellement présents sous
`core/tests/` si les noms diffèrent légèrement — lister d'abord avec
`ls core/tests/ | grep pipeline` si un des noms ci-dessus n'existe pas.)

Expected: PASS. Si des tests `postgis`/`pg_engine` skippent faute de
`CORE_TEST_DATABASE_URL`, le signaler explicitement (piège CLAUDE.md #3)
plutôt que de conclure "entièrement vert" sans réserve.

- [ ] **Step 2: Suite complète du cœur + seuil de couverture**

Run: `cd core && uv run pytest -q`
Run: `cd core && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold`
Expected: 0 échec, couverture ≥ seuil (85, cf. CLAUDE.md § Commandes).

- [ ] **Step 3: Portes de qualité statique**

Run:
```bash
cd core
uv run ruff check .
uv run ruff format --check .
uv run lint-imports
```
Expected: aucune violation (aucun nouveau chemin d'import inter-module créé
par ce plan — `connector_runtime.py` et `runtime.py` avaient déjà une
dépendance directe l'un vers l'autre).

- [ ] **Step 4: Rapport de fin de plan**

Pas de commit de code à cette étape (vérification seule). Si tout est vert,
passer à `superpowers:requesting-code-review` avant de considérer cette
tranche du chantier desktop-etl terminée, conformément à CLAUDE.md
(« une revue par tâche et une revue finale de branche »).

---

## Ce que ce plan ne couvre pas (volontairement)

- **API loopback HTTP du sidecar** (`GET /ops`, `POST /pipelines/validate`,
  `POST /pipelines/run`, `POST /pipelines/preview`), le suivi de run en
  mémoire, et l'extraction de la partie partagée de `run_pipeline_task`
  (design §4, §11) — sous-chantier distinct, pas encore assez spécifié
  pour être planifié avec du code exact (forme SSE, framework HTTP,
  gestion du port éphémère restent à trancher). À reprendre avec
  `superpowers:writing-plans` une fois cette tranche mergée.
- **`reader.file`/`writer.file`** côté cœur (design §3) — dépend d'abord
  du sort du risque résiduel identifié par
  [`docs/superpowers/specs/2026-09-17-desktop-etl-spike-01-findings.md`](../specs/2026-09-17-desktop-etl-spike-01-findings.md)
  (extension spatiale DuckDB en binaire gelé, jamais prouvée par le spike
  01 qui ne portait que sur `dlt`/`duckdb`/`sqlalchemy`/REST) : un spike 02
  ciblé sur `ST_Read`/l'extension `spatial` de DuckDB en binaire PyInstaller
  reste à faire avant ce sous-chantier.
- **Dossier `desktop-etl/` (Tauri, canvas React, packaging)** — non créé
  par ce plan : rien dans ce plan ne dépend de son existence, et le design
  §11 le place après le socle sidecar complet.

Plan complet et sauvegardé dans
`docs/superpowers/plans/2026-09-17-desktop-etl-secret-resolver-seam.md`.
