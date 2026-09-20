# Desktop ETL — `reader.file` / `writer.file` côté cœur — plan

> **Pour les agents d'exécution :** SOUS-COMPÉTENCE REQUISE : utiliser
> superpowers:subagent-driven-development (recommandé) ou
> superpowers:executing-plans pour exécuter ce plan tâche par tâche. Les
> étapes utilisent la syntaxe case à cocher (`- [ ]`) pour le suivi.

**Objectif :** ajouter au registre partagé `OPERATIONS`
(`core/app/pipelines/ops/contracts.py`) deux nouvelles op, `reader.file` et
`writer.file`, qui matérialisent/écrivent un fichier géospatial **local** via
DuckDB spatial (`ST_Read`/`COPY ... FORMAT GDAL`) — le mécanisme déjà utilisé
en production pour la sortie du sidecar QGIS
(`_materialize_qgis_output`/`_execute_qgis_transform`, `runtime.py`). C'est le
tronçon « `reader.file`/`writer.file` côté cœur » du découpage §11 de
[`docs/superpowers/specs/2026-09-17-desktop-etl-standalone-design.md`](../specs/2026-09-17-desktop-etl-standalone-design.md)
§3 : un pur changement `core/`, sans dépendance à Tauri/PyInstaller — c'est ce
qui permet à un futur sidecar desktop d'exécuter un pipeline fichier→fichier
sans Postgres ni S3.

**Correction par rapport au texte du design (à consigner, vérifiée
empiriquement avant d'écrire ce plan, cf. piège CLAUDE.md #3) :**

1. Le design (§3) dit que `writer.file` réutilise « déjà le mécanisme de
   `writer.export` » — faux à la lecture du code réel : `_write_export`
   sérialise manuellement en CSV/JSON, il n'appelle jamais GDAL. Le vrai
   mécanisme réutilisable est le `COPY (...) TO ... WITH (FORMAT GDAL,
   DRIVER ..., SRS ...)` de `_execute_qgis_transform` (ligne 515), déjà
   prouvé en production pour écrire un GPKG.
2. **Trouvaille non documentée par le design, bloquante si ignorée — même
   classe de bug que SP-44 (« `_lock_down()` bloquait `transform.qgis` »).**
   `_prepare()` appelle `_lock_down(conn)` (`runtime.py:439`) qui pose
   `allowed_directories = ['/scratch']` puis `enable_external_access =
   false` **avant** que les writers ne s'exécutent (readers déjà
   matérialisés avant ce point, donc `reader.file` n'est pas concerné).
   `writer.file` écrit vers un chemin **arbitraire**, jamais `/scratch` :
   sans changement, `COPY ... TO '<chemin utilisateur>'` échoue après
   verrouillage avec `PermissionException: file system operations are
   disabled by configuration` — vérifié empiriquement (reproduit puis
   corrigé avant d'écrire ce plan, cf. Tâche 3). `reader.file` n'a besoin
   d'aucun changement équivalent : il s'exécute dans la boucle reader de
   `_prepare()`, avant l'appel à `_lock_down()`.
3. Le SRID à passer en `SRS` de `writer.file` n'est **pas** à recalculer :
   `srid_by_node` (retourné par `_prepare()`, alimenté aussi pour les nœuds
   `transform` par `_execute_transform_chain`, ligne 590/632) contient déjà
   le SRID du prédécesseur de n'importe quel nœud au moment où la boucle
   writer de `run_pipeline()` s'exécute — `srid_by_node[pred_id]` suffit,
   aucun nouveau calcul.
4. Détection du SRID en lecture : DuckDB spatial expose `st_crs(geometry)`
   (chaîne `'EPSG:NNNN'` ou `NULL` si le fichier n'a pas de CRS) — pas de
   fonction `ST_SRID` scalaire (contrairement à l'intuition), vérifié
   empiriquement.
5. GDAL/GPKG réserve `fid`/`OGC_FID` comme nom de champ d'identifiant de
   ligne : un `writer.file` en aval d'un `reader.file` qui laisse passer
   cette colonne (GeoJSON→GDAL la synthétise sous `OGC_FID`) fait échouer
   `COPY ... DRIVER 'GPKG'` avec `Cannot find OGR field for Arrow array
   OGC_FID` — vérifié empiriquement, à exclure explicitement (même
   précédent que le "fid" déjà éliminé par `_materialize_qgis_output` pour
   la sortie QGIS→GPKG, mais dans l'autre sens ici : en entrée d'un writer,
   pas en sortie).

**Architecture :**

- `app/auth/dependency.py` gagne `is_pipeline_file_io_enabled()`
  (`CORE_PIPELINE_FILE_IO_ENABLED`, défaut `false`) — même patron que
  `is_etl_enabled()` : lu à chaque appel, jamais caché. Défaut désactivé
  côté cœur serveur (accès disque arbitraire = risque de traversée de
  chemin sur un cœur multi-tenant, cf. design §3) ; le futur sidecar
  desktop l'activera dans son propre environnement (hors périmètre de ce
  plan).
- `OperationContract` (`ops/contracts.py`) gagne un champ
  `enabled_when: Callable[[], bool] | None = None` ; `ops_catalog()` ignore
  toute op dont `enabled_when()` renvoie `False` — mécanisme générique,
  réutilisable par toute future op instance-optionnelle, pas un
  `if op == "reader.file"` codé en dur.
- `reader.file`/`writer.file` (`runtime.py`) vérifient
  `is_pipeline_file_io_enabled()` en **premier**, avant tout accès disque —
  garde-fou au point d'exécution réel (même précédent que
  `_write_dataset`/`Privilege.DATA_MANAGE`, SP-42) : les 4 points d'entrée
  qui peuvent déclencher un run (route REST, outil MCP, balayage cron,
  webhook) convergent tous sur `run_pipeline()`/`READERS`/`WRITERS`, donc
  sur ce point unique — `ops_catalog()` n'est qu'une exclusion cosmétique
  côté palette, jamais le vrai garde-fou de sécurité.
- `_lock_down()` gagne un paramètre `extra_allowed_dirs`, alimenté par
  `_prepare()` à partir des chemins de tous les nœuds `writer.file` du
  payload, calculé **avant** l'appel à `_lock_down()`.

**Tech Stack :** Python 3.12, DuckDB spatial (`ST_Read`/`COPY ... FORMAT
GDAL`), Pydantic, pytest.

## Global Constraints

- TDD systématique (CLAUDE.md « Comment on travaille »).
- Commits conventionnels, petits, un sujet par commit (`feat(core): …`),
  message se terminant par `Co-Authored-By: Claude Sonnet 5
  <noreply@anthropic.com>`.
- Docs et commentaires en français, code/identifiants en anglais.
- `app/auth/dependency.py` est dans le périmètre `mypy --strict` listé par
  CLAUDE.md (`app/auth app/secrets app/analytics app/copilot
  app/admin_tools app/roles`) : `is_pipeline_file_io_enabled() -> bool` doit
  typer proprement sans `Any` ni `# type: ignore`. `app/pipelines/` n'est
  **pas** dans ce périmètre.
- Aucun paramètre lié (`?`) n'existe pour l'argument chemin de `ST_Read`/
  `COPY ... TO` en DuckDB : tout chemin utilisateur (`p.path`) et tout
  littéral de driver (`p.driver`) interpolés dans le SQL DOIVENT passer par
  le helper d'échappement de littéral `_ql()` introduit en Tâche 3 — jamais
  une f-string nue. Patron déjà en usage ailleurs dans le dépôt
  (`app/collections/ddl.py::_quote_literal`,
  `app/analytics/aggregate.py::_quote_literal`,
  `app/harvest/live_query.py`) : `"'" + value.replace("'", "''") + "'"`.
  Les noms de colonnes restent quotés par `_qi()` (identifiant), jamais par
  `_ql()` (littéral) — ne pas confondre les deux dans les nouvelles
  fonctions.
- Ne pas introduire d'abstraction au-delà de ce que ce plan demande (YAGNI) :
  pas de sandbox/jail de chemin pour `reader.file`/`writer.file` au-delà du
  flag on/off — la mitigation du risque de traversée de chemin est le flag
  désactivé par défaut côté serveur, pas une restriction de répertoire (le
  desktop, cible réelle, doit pouvoir lire/écrire n'importe où sur le poste
  de son utilisateur).
- Pas de nouveau flag exposé sur `GET /v1/instance` : contrairement à
  `CORE_ETL_ENABLED`/`CORE_EXPORT_ENABLED`, cette capacité ne gate pas
  l'affichage d'un pan entier du shell (le pipeline builder reste gardé par
  `CORE_ETL_ENABLED` seul) — `ops_catalog()` suffit comme mécanisme de
  découvrabilité, ne pas dupliquer.
- Ne pas ajouter `CORE_PIPELINE_FILE_IO_ENABLED` à `.env.example` : la
  capacité reste désactivée par défaut, aucun service du compose serveur
  n'en dépend dans ce plan — l'y ajouter créerait l'illusion d'un câblage
  qui n'existe pas encore (piège CLAUDE.md #2).
- Ne PAS lancer `scripts/export_openapi.py`/`npm run gen:api-types` pour ce
  plan : `GET /pipelines/ops` a pour `response_model` un `dict` nu (pas de
  schéma Pydantic figé dans l'OpenAPI), et aucune route/schéma exposé ne
  change de forme — vérifié en lisant `routes.py` avant d'écrire ce plan
  (piège CLAUDE.md #1, exclusion explicitement vérifiée, pas supposée).

---

## File Structure

- **Modifie `core/app/auth/dependency.py`** : ajoute
  `is_pipeline_file_io_enabled()`.
- **Modifie `core/app/pipelines/ops/schemas.py`** : ajoute
  `ReaderFileParams`/`WriterFileParams`.
- **Modifie `core/app/pipelines/ops/contracts.py`** : ajoute le champ
  `enabled_when` à `OperationContract`, les 2 entrées `OPERATIONS`, filtre
  `ops_catalog()`.
- **Modifie `core/app/pipelines/runtime.py`** : ajoute `_ql()`, `_read_file`,
  `_write_file`, élargit `_lock_down()`/`_prepare()`, ajoute la branche
  `writer.file` dans `run_pipeline()`.
- **Modifie `core/app/pipelines/registries.py`** : ajoute les 2 entrées
  `READERS`/`WRITERS`, étend le docstring qui énumère les fonctions.
- **Crée `core/tests/test_pipeline_file_io.py`** : toutes les tests de ce
  plan (flag, catalogue, `_read_file`, `_write_file`, bout-en-bout).
- **Ne modifie pas** `app/pipelines/config_validation.py` (vérifié : aucun
  changement requis, cf. note ci-dessous), `app/configs/schemas.py`
  (`PipelineNode.op: str` déjà libre, pas d'enum à étendre),
  `app/pipelines/routes.py`, `app/pipelines/service.py`, aucun schéma
  exposé côté shell.

**Note sur `config_validation.py` (pourquoi zéro changement) :**
`_validate_node` cherche `node.op` dans `_COLLECTION_PARAM_FIELD` — absent
pour `reader.file`/`writer.file` (ils ne référencent aucune collection) —
`field` vaut `None`, la fonction retourne après la seule validation de forme
Pydantic (`_validate_params`, déjà générique via `OP_PARAMS`). Une pipeline
config référençant `reader.file` peut donc être **sauvegardée** même si
`CORE_PIPELINE_FILE_IO_ENABLED` est éteint — cohérent avec la philosophie
déjà documentée en tête de ce module (« a bad expression fails the run
clearly, it never blocks saving the pipeline ») : le vrai garde-fou est à
l'exécution (Tâches 4/5), jamais à la sauvegarde.

---

### Tâche 1 : flag `CORE_PIPELINE_FILE_IO_ENABLED`

**Files:**
- Modify: `core/app/auth/dependency.py`
- Create: `core/tests/test_pipeline_file_io.py`

**Interfaces:**
- Produces: `app.auth.dependency.is_pipeline_file_io_enabled() -> bool`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `core/tests/test_pipeline_file_io.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.auth.dependency import is_pipeline_file_io_enabled


def test_is_pipeline_file_io_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    assert is_pipeline_file_io_enabled() is False


def test_is_pipeline_file_io_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    assert is_pipeline_file_io_enabled() is True
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "false")
    assert is_pipeline_file_io_enabled() is False
```

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py -v`
Expected: FAIL avec `ImportError: cannot import name
'is_pipeline_file_io_enabled'`

- [ ] **Step 3: Ajouter le flag**

Dans `core/app/auth/dependency.py`, ajouter juste après `is_etl_enabled()`
(après la ligne `return os.environ.get("CORE_ETL_ENABLED", "false").lower()
== "true"`) :

```python
def is_pipeline_file_io_enabled() -> bool:
    """CORE_PIPELINE_FILE_IO_ENABLED (design desktop-etl §3) — capacité
    instance-wide optionnelle, même convention que is_etl_enabled : lue à
    chaque appel, sans cache. Défaut false : reader.file/writer.file font de
    l'accès disque arbitraire (chemin choisi par l'auteur du pipeline), un
    risque de traversée de chemin inacceptable sur un cœur hébergé
    multi-tenant — le futur sidecar desktop (poste mono-utilisateur, design
    §1) l'activera dans son propre environnement, jamais par défaut ici."""
    return os.environ.get("CORE_PIPELINE_FILE_IO_ENABLED", "false").lower() == "true"
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: mypy --strict sur app/auth**

Run: `cd core && uv run mypy --strict app/auth`
Expected: `Success: no issues found`

- [ ] **Step 6: Commit**

```bash
cd core
git add app/auth/dependency.py tests/test_pipeline_file_io.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute le flag CORE_PIPELINE_FILE_IO_ENABLED

Prépare reader.file/writer.file (design desktop-etl §3) : capacité
instance-wide désactivée par défaut côté cœur serveur (accès disque
arbitraire = risque de traversée de chemin), même patron que
CORE_ETL_ENABLED. N'est encore consommée par aucune op à cette étape.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Tâche 2 : schémas + `OperationContract.enabled_when` + entrées `OPERATIONS` + filtrage du catalogue

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Modify: `core/tests/test_pipeline_file_io.py`

**Interfaces:**
- Consumes: `app.auth.dependency.is_pipeline_file_io_enabled` (Tâche 1).
- Produces: `ops.schemas.ReaderFileParams(path: str, srid: int | None =
  None)`, `ops.schemas.WriterFileParams(path: str, driver: str = "GPKG")` ;
  `ops.contracts.OperationContract.enabled_when: Callable[[], bool] | None`
  ; `OPERATIONS["reader.file"]`/`OPERATIONS["writer.file"]`.

- [ ] **Step 1: Ajouter les schémas de params**

À la fin de `core/app/pipelines/ops/schemas.py` (après
`TransformFormatCoordinatesParams`, dernière classe du fichier), ajouter :

```python


class ReaderFileParams(BaseModel):
    """reader.file (design desktop-etl §3) : chemin local absolu, lu via
    ST_Read() (DuckDB spatial/GDAL) — jamais une collection. srid optionnel :
    si absent, détecté depuis le CRS du fichier (st_crs()), repli sur 4326
    si le fichier n'en porte aucun (même repli que table_info.srid or 4326
    pour reader.collection)."""

    path: str
    srid: int | None = None


class WriterFileParams(BaseModel):
    """writer.file (design desktop-etl §3) : chemin local absolu, écrit via
    COPY ... FORMAT GDAL DRIVER <driver> — n'importe quel driver vectoriel
    GDAL (GPKG par défaut, vérifié empiriquement ; GeoJSON aussi vérifié).
    Les drivers non vectoriels (ex. CSV) échouent à l'écriture d'une colonne
    géométrie — pas garanti par ce schéma, mais par COPY lui-même à
    l'exécution."""

    path: str
    driver: str = "GPKG"
```

- [ ] **Step 2: Ajouter `enabled_when` au contrat**

Dans `core/app/pipelines/ops/contracts.py`, dans `OperationContract`, ajouter
le champ juste après `exchange` (dernier champ du dataclass, avant
`__post_init__`) :

```python
    # Design docs/superpowers/specs/2026-09-17-desktop-etl-standalone-design.md
    # §3 : capacité instance-wide optionnelle (même patron que
    # is_etl_enabled) qui gate la VISIBILITÉ de l'op dans ops_catalog() —
    # PAS le garde-fou de sécurité réel, qui vit au point d'exécution
    # (app.pipelines.runtime, jamais ici) : ce champ ne remplace aucune
    # vérification, il évite seulement de proposer une op inutilisable dans
    # la palette de l'éditeur.
    enabled_when: Callable[[], bool] | None = None
```

Puis importer le flag et ajouter les 2 entrées. Ajouter à l'import existant
(en tête du fichier) :

```python
from app.auth.dependency import is_pipeline_file_io_enabled
```

Ajouter aux imports depuis `app.pipelines.ops.schemas` (liste alphabétique
existante) : `ReaderFileParams` (après `ReaderConnectorSnowflakeParams`) et
`WriterFileParams` (après `WriterExportParams`).

Puis, juste avant la fermeture `}` de `OPERATIONS` (juste après l'entrée
`"transform.formatCoordinates"`), ajouter :

```python
    "reader.file": OperationContract(
        op="reader.file",
        kind="reader",
        params_schema=ReaderFileParams,
        enabled_when=is_pipeline_file_io_enabled,
    ),
    "writer.file": OperationContract(
        op="writer.file",
        kind="writer",
        params_schema=WriterFileParams,
        enabled_when=is_pipeline_file_io_enabled,
    ),
```

- [ ] **Step 3: Filtrer `ops_catalog()`**

Dans `core/app/pipelines/ops/contracts.py`, remplacer le corps de
`ops_catalog()` :

```python
def ops_catalog() -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for op, model in OP_PARAMS.items():
        contract = OPERATIONS[op]
        if contract.enabled_when is not None and not contract.enabled_when():
            continue
        schema = model.model_json_schema()
        if schema.get("description"):
            schema["description"] = _user_facing_description(schema["description"])
        catalog[op] = {
            "kind": OP_KINDS[op],
            "paramsSchema": schema,
            "acceptsSecondaryInput": op in BINARY_OPS,
        }
    return catalog
```

- [ ] **Step 4: Ajouter les tests de visibilité du catalogue**

Ajouter à `core/tests/test_pipeline_file_io.py` :

```python
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog


def test_reader_file_and_writer_file_hidden_from_catalog_by_default(monkeypatch):
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    catalog = ops_catalog()
    assert "reader.file" not in catalog
    assert "writer.file" not in catalog


def test_reader_file_and_writer_file_visible_in_catalog_when_enabled(monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    catalog = ops_catalog()
    assert catalog["reader.file"]["kind"] == "reader"
    assert catalog["writer.file"]["kind"] == "writer"


def test_operations_registry_has_reader_and_writer_file_contracts():
    assert OPERATIONS["reader.file"].kind == "reader"
    assert OPERATIONS["writer.file"].kind == "writer"
```

- [ ] **Step 5: Vérifier que les tests passent + non-régression catalogue**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py -v`
Expected: PASS (5 tests au total : 2 de la Tâche 1 + 3 ci-dessus)

Run: `cd core && uv run pytest tests/test_pipeline_ops_contracts.py -q`
(adapter le nom si différent — lister d'abord avec `ls core/tests/ | grep
contracts` si absent). Expected: PASS, aucune régression sur les 34 op
existantes (le catalogue n'a changé que pour les 2 nouvelles entrées).

- [ ] **Step 6: Commit**

```bash
cd core
git add app/pipelines/ops/schemas.py app/pipelines/ops/contracts.py \
  tests/test_pipeline_file_io.py
git commit -m "$(cat <<'EOF'
feat(core): ajoute reader.file/writer.file au registre OPERATIONS

Schémas de params + OperationContract.enabled_when (mécanisme générique de
visibilité instance-wide dans ops_catalog(), pas un if/elif codé en dur) —
gatées par CORE_PIPELINE_FILE_IO_ENABLED (Tâche précédente). Additif pur :
aucune fonction reader/writer réelle encore branchée, aucun run possible
avec ces 2 op à cette étape (READERS/WRITERS ne les connaissent pas
encore).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Tâche 3 : `_lock_down()` autorise les répertoires cibles de `writer.file`

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Modify: `core/tests/test_pipeline_file_io.py`

**Interfaces:**
- Produces: `runtime._ql(value: str) -> str` ; `runtime._lock_down(conn, *,
  extra_allowed_dirs: list[str] | None = None) -> None` (signature élargie,
  compatible avec les appels existants sans argument).
- Consumes: `app.analytics.duckdb_conn.open_connection` (déjà importée dans
  `runtime.py`).

**Pourquoi cette tâche existe séparément (pas fondue dans la Tâche 5)** :
c'est la correction n°2 documentée en tête de ce plan — un bug de la même
classe que « `_lock_down()` bloquait `transform.qgis` » (SP-44). Le
vérifier en isolation, contre un `_lock_down()` appelé directement sur une
connexion réellement verrouillée, plutôt que noyé dans un test de
`_write_file` de bout en bout, pour qu'un échec ici pointe sans ambiguïté
vers ce mécanisme précis.

- [ ] **Step 1: Écrire le test qui échoue (verrouillage réel, écriture hors `/scratch`)**

Ajouter à `core/tests/test_pipeline_file_io.py` :

```python
import os

import duckdb

from app.analytics.duckdb_conn import open_connection
from app.pipelines import runtime


def _connection() -> duckdb.DuckDBPyConnection:
    return open_connection(
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y"
    )


def test_lock_down_without_extra_dirs_blocks_arbitrary_write(tmp_path):
    conn = _connection()
    conn.execute("CREATE TEMP TABLE t AS SELECT 1 AS n")
    runtime._lock_down(conn)
    out_path = str(tmp_path / "out.csv")
    with pytest.raises(duckdb.PermissionException):
        conn.execute(f"COPY (SELECT * FROM t) TO '{out_path}' WITH (FORMAT CSV)")


def test_lock_down_with_extra_dirs_allows_write_under_them(tmp_path):
    conn = _connection()
    conn.execute("CREATE TEMP TABLE t AS SELECT 1 AS n")
    runtime._lock_down(conn, extra_allowed_dirs=[str(tmp_path)])
    out_path = str(tmp_path / "out.csv")
    conn.execute(f"COPY (SELECT * FROM t) TO '{out_path}' WITH (FORMAT CSV)")
    assert os.path.exists(out_path)


def test_lock_down_with_extra_dirs_still_blocks_paths_outside_them(tmp_path):
    conn = _connection()
    conn.execute("CREATE TEMP TABLE t AS SELECT 1 AS n")
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    runtime._lock_down(conn, extra_allowed_dirs=[str(allowed_dir)])
    out_path = str(other_dir / "out.csv")
    with pytest.raises(duckdb.PermissionException):
        conn.execute(f"COPY (SELECT * FROM t) TO '{out_path}' WITH (FORMAT CSV)")
```

Ajouter `import pytest` en tête du fichier de test s'il n'y est pas déjà.

- [ ] **Step 2: Vérifier que les 2 derniers tests échouent**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py -k lock_down -v`
Expected: `test_lock_down_without_extra_dirs_blocks_arbitrary_write` PASS
(comportement déjà correct aujourd'hui) ; les 2 autres FAIL avec
`TypeError: _lock_down() got an unexpected keyword argument
'extra_allowed_dirs'`.

- [ ] **Step 3: Élargir `_lock_down()` + ajouter `_ql()`**

Dans `core/app/pipelines/runtime.py`, ajouter `_ql()` juste après `_qi()`
(après la ligne `return '"' + name.replace('"', '""') + '"'`) :

```python


def _ql(value: str) -> str:
    # Littéral SQL DuckDB (jamais un identifiant, contrairement à _qi
    # ci-dessus) — ST_Read()/COPY ... TO n'acceptent pas de paramètre lié
    # pour leur argument chemin, donc tout chemin utilisateur interpolé DOIT
    # passer par ici. Même patron que app.collections.ddl._quote_literal /
    # app.analytics.aggregate._quote_literal (duplication déjà acceptée
    # dans ce dépôt, même raisonnement que _qi lui-même).
    return "'" + value.replace("'", "''") + "'"
```

Puis remplacer le corps de `_lock_down()` (actuellement lignes 326-338) :

```python
def _lock_down(
    conn: duckdb.DuckDBPyConnection, *, extra_allowed_dirs: list[str] | None = None
) -> None:
    # allowed_directories doit être posé AVANT enable_external_access=false :
    # c'est la seule échappatoire documentée par DuckDB ("List of
    # directories/prefixes that are ALWAYS allowed to be queried — even when
    # enable_external_access is false"), sans laquelle _execute_qgis_transform
    # ne peut plus écrire in.gpkg vers _QGIS_SCRATCH_ROOT après ce
    # verrouillage (PermissionException réelle, jamais vue avant faute
    # d'avoir exécuté ce chemin contre une connexion réellement verrouillée —
    # cf. M14/REV-095). extra_allowed_dirs (design desktop-etl §3, réutilise
    # la même échappatoire) : répertoires cibles de tout nœud writer.file du
    # payload, calculés par l'appelant (_prepare()) AVANT ce verrouillage —
    # même bug évité une seconde fois, cette fois pour un chemin arbitraire
    # choisi par l'auteur du pipeline, jamais fixe comme _QGIS_SCRATCH_ROOT.
    allowed_dirs = [_QGIS_SCRATCH_ROOT, *(extra_allowed_dirs or [])]
    quoted = ", ".join(_ql(d) for d in allowed_dirs)
    conn.execute(f"SET allowed_directories = [{quoted}]")
    conn.execute("SET enable_external_access = false")
    conn.execute("SET lock_configuration = true")
```

- [ ] **Step 4: Propager depuis `_prepare()`**

Dans `core/app/pipelines/runtime.py`, remplacer l'appel `_lock_down(conn)`
(actuellement seul sur sa ligne, juste avant `return ordered, view_by_node,
srid_by_node, join_srid_by_node`) par :

```python
    writer_file_dirs = [
        os.path.dirname(node.params["path"])
        for node in payload.nodes
        if node.op == "writer.file" and isinstance(node.params.get("path"), str)
    ]
    _lock_down(conn, extra_allowed_dirs=writer_file_dirs)
```

(`os` est déjà importé en tête de `runtime.py` ; `payload.nodes` est déjà en
scope dans `_prepare()`, qui le reçoit en paramètre.)

- [ ] **Step 5: Vérifier que les 3 tests passent**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py -k lock_down -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Suite pipelines complète (non-régression QGIS)**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py tests/test_pipeline_runtime.py -q`
Expected: PASS. Si des tests `qgis`/`postgis` skippent faute de
`CORE_TEST_QGIS_WORKER_URL`/`CORE_TEST_DATABASE_URL`, le signaler
explicitement (piège CLAUDE.md #3) plutôt que conclure "vert" sans réserve —
`_lock_down()` est exercé par `_execute_qgis_transform`, dont les tests
`@pytest.mark.qgis` sont le seul filet contre un sidecar réel.

- [ ] **Step 7: Commit**

```bash
cd core
git add app/pipelines/runtime.py tests/test_pipeline_file_io.py
git commit -m "$(cat <<'EOF'
feat(core): _lock_down() autorise les répertoires cibles de writer.file

_prepare() verrouille la connexion DuckDB (allowed_directories=['/scratch'],
enable_external_access=false) avant que les writers ne s'exécutent — un
writer.file vers un chemin arbitraire y échouerait sans ce changement (même
classe de bug que SP-44 : _lock_down() bloquait déjà transform.qgis avant
d'inclure son propre répertoire scratch). Vérifié en isolation contre une
connexion réellement verrouillée, pas seulement unitairement.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Tâche 4 : `_read_file` + registre `READERS`

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Modify: `core/app/pipelines/registries.py`
- Modify: `core/tests/test_pipeline_file_io.py`

**Interfaces:**
- Consumes: `ops.schemas.ReaderFileParams` (Tâche 2),
  `app.auth.dependency.is_pipeline_file_io_enabled` (Tâche 1), `_qi`/`_ql`
  (déjà dans `runtime.py`).
- Produces: `runtime._read_file(conn, *, session, tenant_id, node_id,
  params, view_name, user, base_uri) -> int` (même signature uniforme que
  tous les readers du registre `READERS`) ; `registries.READERS["reader.file"]`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `core/tests/test_pipeline_file_io.py` :

```python
import json

from app.pipelines import registries
from app.pipelines.errors import PipelineRuntimeError


def _write_geojson(tmp_path, *, name="in.geojson"):
    path = tmp_path / name
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"label": "a"},
                "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
            },
            {
                "type": "Feature",
                "properties": {"label": "b"},
                "geometry": {"type": "Point", "coordinates": [3.0, 4.0]},
            },
        ],
    }
    path.write_text(json.dumps(feature_collection))
    return str(path)


def test_read_file_raises_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    path = _write_geojson(tmp_path)
    conn = _connection()
    with pytest.raises(PipelineRuntimeError, match="CORE_PIPELINE_FILE_IO_ENABLED"):
        runtime._read_file(
            conn,
            session=None,
            tenant_id="t1",
            node_id="r1",
            params={"path": path},
            view_name="node_r1",
            user=None,
            base_uri="unused",
        )


def test_read_file_materializes_geojson_with_detected_srid(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    path = _write_geojson(tmp_path)
    conn = _connection()
    srid = runtime._read_file(
        conn,
        session=None,
        tenant_id="t1",
        node_id="r1",
        params={"path": path},
        view_name="node_r1",
        user=None,
        base_uri="unused",
    )
    assert srid == 4326
    rows = conn.execute("SELECT label FROM node_r1 ORDER BY label").fetchall()
    assert rows == [("a",), ("b",)]
    cols = {d[0] for d in conn.execute("SELECT * FROM node_r1 LIMIT 0").description}
    assert "geometry" in cols


def test_read_file_srid_param_overrides_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    path = _write_geojson(tmp_path)
    conn = _connection()
    srid = runtime._read_file(
        conn,
        session=None,
        tenant_id="t1",
        node_id="r1",
        params={"path": path, "srid": 2154},
        view_name="node_r1",
        user=None,
        base_uri="unused",
    )
    assert srid == 2154


def test_readers_registry_has_reader_file():
    assert registries.READERS["reader.file"] is runtime._read_file
```

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py -k read_file -v`
Expected: FAIL avec `AttributeError: module 'app.pipelines.runtime' has no
attribute '_read_file'` (les 3 premiers, qui appellent `runtime._read_file`
directement) ; `test_readers_registry_has_reader_file` échoue avec la même
`AttributeError` tant que `_read_file` n'existe pas — la refaire tourner
seule après le Step 3 (avant le Step 4) reproduirait alors `KeyError:
'reader.file'` (READERS ne connaît pas encore l'entrée).

- [ ] **Step 3: Implémenter `_read_file`**

Dans `core/app/pipelines/runtime.py`, ajouter l'import
`is_pipeline_file_io_enabled` (avec les autres imports `app.*`, ordre
alphabétique : juste avant `from app.collections import repository as
collections_repo`) :

```python
from app.auth.dependency import is_pipeline_file_io_enabled
```

Ajouter `ReaderFileParams` à l'import existant depuis
`app.pipelines.ops.schemas` (ordre alphabétique, après
`ReaderConnectorSnowflakeParams`).

Puis ajouter la fonction juste après `_read_connector_snowflake` (avant
`def _lock_down`) :

```python
def _read_file(
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
    """reader.file (registre READERS, design desktop-etl §3) — matérialise
    un fichier local via ST_Read() (DuckDB spatial/GDAL), même mécanisme que
    _materialize_qgis_output pour la sortie du sidecar QGIS.
    session/tenant_id/node_id/user/base_uri ignorés (même convention que
    _read_connector_rest) : accès disque local, jamais de collection ni de
    secret. S'exécute dans la boucle reader de _prepare(), AVANT
    _lock_down() : aucun besoin d'un répertoire autorisé, contrairement à
    writer.file."""
    if not is_pipeline_file_io_enabled():
        raise PipelineRuntimeError("reader.file requires CORE_PIPELINE_FILE_IO_ENABLED=true")
    p = ReaderFileParams.model_validate(params)
    probe_cols = conn.execute(f"SELECT * FROM ST_Read({_ql(p.path)}) LIMIT 0").description
    geom_cols = [d[0] for d in probe_cols if d[1].id == "geometry"]
    if not geom_cols:
        raise PipelineRuntimeError(f"reader.file: '{p.path}' has no geometry column")
    geom_col = geom_cols[0]
    other_cols = [d[0] for d in probe_cols if d[0] != geom_col]
    select_list = ", ".join([_qi(c) for c in other_cols] + [f"{_qi(geom_col)} AS geometry"])
    conn.execute(
        f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT {select_list} FROM ST_Read({_ql(p.path)})"
    )
    if p.srid is not None:
        return p.srid
    row = conn.execute(f"SELECT st_crs(geometry) FROM {_qi(view_name)} LIMIT 1").fetchone()
    crs = row[0] if row else None
    if crs and crs.upper().startswith("EPSG:"):
        return int(crs.split(":", 1)[1])
    return 4326
```

- [ ] **Step 4: Enregistrer dans `READERS`**

Dans `core/app/pipelines/registries.py`, ajouter à `READERS` (après
`"reader.connector.snowflake"`) :

```python
    "reader.file": _runtime._read_file,
```

Étendre le docstring du module (paragraphe énumérant les fonctions
agrégées) pour ajouter `_read_file` à la liste `_read_collection,
_read_connector_rest, _read_connector_postgres, _read_connector_snowflake,
_read_file, ...`.

- [ ] **Step 5: Vérifier que les tests passent**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py -k read_file -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
cd core
git add app/pipelines/runtime.py app/pipelines/registries.py \
  tests/test_pipeline_file_io.py
git commit -m "$(cat <<'EOF'
feat(core): implémente reader.file (ST_Read local, gardé par le flag)

Matérialise un fichier géospatial local via DuckDB spatial, même mécanisme
que _materialize_qgis_output. Garde-fou CORE_PIPELINE_FILE_IO_ENABLED posé
en premier, au point d'exécution réel — ops_catalog() (tâche précédente)
n'en est que le reflet côté palette. SRID détecté via st_crs(), overridable
par le param, repli sur 4326 sinon.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Tâche 5 : `_write_file` + branche `run_pipeline()` + registre `WRITERS`

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Modify: `core/app/pipelines/registries.py`
- Modify: `core/tests/test_pipeline_file_io.py`

**Interfaces:**
- Consumes: `ops.schemas.WriterFileParams` (Tâche 2), `_qi`/`_ql`
  (`runtime.py`), `NodeStat` (déjà défini dans `runtime.py`).
- Produces: `runtime._write_file(conn, *, node, view_by_node, srid) ->
  NodeStat` ; `registries.WRITERS["writer.file"]` ; `run_pipeline()` gagne
  une branche `elif node.op == "writer.file":`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `core/tests/test_pipeline_file_io.py` :

```python
from app.configs.schemas import PipelineNode
from app.pipelines.runtime import NodeStat


def _materialized_view(conn, *, view_name="node_r1"):
    conn.execute("INSTALL spatial; LOAD spatial;")
    conn.execute(
        f"CREATE TEMP TABLE {view_name} AS "
        "SELECT 'a' AS label, ST_Point(1, 2) AS geometry "
        "UNION ALL SELECT 'b', ST_Point(3, 4)"
    )
    return view_name


def test_write_file_raises_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    conn = _connection()
    view_name = _materialized_view(conn)
    node = PipelineNode(
        id="w1", kind="writer", op="writer.file", params={"path": str(tmp_path / "out.gpkg")}
    )
    with pytest.raises(PipelineRuntimeError, match="CORE_PIPELINE_FILE_IO_ENABLED"):
        runtime._write_file(
            conn, node=node, view_by_node={"w1": view_name}, srid=4326
        )


def test_write_file_writes_readable_gpkg(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    conn = _connection()
    view_name = _materialized_view(conn)
    out_path = tmp_path / "out.gpkg"
    node = PipelineNode(
        id="w1", kind="writer", op="writer.file", params={"path": str(out_path)}
    )
    stat = runtime._write_file(conn, node=node, view_by_node={"w1": view_name}, srid=4326)
    assert stat.rowCount == 2
    check_conn = _connection()
    rows = check_conn.execute(
        f"SELECT label FROM ST_Read('{out_path}') ORDER BY label"
    ).fetchall()
    assert rows == [("a",), ("b",)]


def test_write_file_excludes_reserved_fid_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    conn = _connection()
    view_name = "node_r1"
    conn.execute(
        f"CREATE TEMP TABLE {view_name} AS "
        "SELECT 1 AS \"OGC_FID\", 'a' AS label, ST_Point(1, 2) AS geometry"
    )
    out_path = tmp_path / "out.gpkg"
    node = PipelineNode(
        id="w1", kind="writer", op="writer.file", params={"path": str(out_path)}
    )
    stat = runtime._write_file(conn, node=node, view_by_node={"w1": view_name}, srid=4326)
    assert stat.rowCount == 1
    assert out_path.exists()


def test_writers_registry_has_writer_file():
    assert registries.WRITERS["writer.file"] is runtime._write_file
```

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py -k write_file -v`
Expected: FAIL avec `AttributeError: module 'app.pipelines.runtime' has no
attribute '_write_file'`.

- [ ] **Step 3: Implémenter `_write_file`**

Dans `core/app/pipelines/runtime.py`, ajouter `WriterFileParams` à l'import
existant depuis `app.pipelines.ops.schemas` (ordre alphabétique, après
`WriterExportParams`).

Ajouter la fonction juste après `_write_export` (avant `def run_pipeline`) :

```python
def _write_file(conn, *, node: PipelineNode, view_by_node: dict, srid: int) -> NodeStat:
    """writer.file (registre WRITERS, design desktop-etl §3) — écrit via
    COPY ... FORMAT GDAL DRIVER ... (même mécanisme que le in_path de
    _execute_qgis_transform), pas la sérialisation manuelle de
    _write_export. Signature sans session/tenant_id/user (même traitement
    que writer.export, cf. registries.py) : accès disque local, jamais de
    collection."""
    if not is_pipeline_file_io_enabled():
        raise PipelineRuntimeError("writer.file requires CORE_PIPELINE_FILE_IO_ENABLED=true")
    p = WriterFileParams.model_validate(node.params)
    input_view = view_by_node[node.id]
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {_qi(input_view)} LIMIT 0").description]
    # "fid"/"OGC_FID" sont les noms synthétiques que GDAL réserve à son
    # propre champ d'identifiant de ligne — un writer.file en aval d'un
    # reader.file qui les a laissés passer fait échouer COPY ... DRIVER
    # 'GPKG' ("Cannot find OGR field for Arrow array OGC_FID"), vérifié
    # empiriquement avant d'écrire ce plan.
    keep = [c for c in cols if c.lower() not in ("fid", "ogc_fid")]
    select_list = ", ".join(_qi(c) for c in keep)
    conn.execute(
        f"COPY (SELECT {select_list} FROM {_qi(input_view)}) TO {_ql(p.path)} "
        f"WITH (FORMAT GDAL, DRIVER {_ql(p.driver)}, SRS {_ql(f'EPSG:{srid}')})"
    )
    row_count = conn.execute(f"SELECT count(*) FROM {_qi(input_view)}").fetchone()[0]
    return NodeStat(node.id, node.op, row_count)
```

- [ ] **Step 4: Brancher dans `run_pipeline()` + registre `WRITERS`**

Dans `core/app/pipelines/runtime.py`, dans `run_pipeline()`, remplacer :

```python
            if node.op == "writer.export":
                assert s3_client is not None and exports_bucket is not None
                stat = writer_fn(
                    conn, s3_client, exports_bucket, node=node, view_by_node=view_by_node
                )
            else:
```

par :

```python
            if node.op == "writer.export":
                assert s3_client is not None and exports_bucket is not None
                stat = writer_fn(
                    conn, s3_client, exports_bucket, node=node, view_by_node=view_by_node
                )
            elif node.op == "writer.file":
                stat = writer_fn(
                    conn, node=node, view_by_node=view_by_node, srid=srid_by_node[pred_id]
                )
            else:
```

(le commentaire juste au-dessus, qui dit « writer.export a une signature
hétérogène... contrairement aux deux autres writers », reste correct au
sens large — pas besoin de le réécrire, il ne nomme aucun op précis.)

Dans `core/app/pipelines/registries.py`, ajouter à `WRITERS` (après
`"writer.export"`) :

```python
    "writer.file": _runtime._write_file,
```

Étendre le docstring du module pour ajouter `_write_file` à la liste des
fonctions agrégées.

- [ ] **Step 5: Vérifier que les tests passent**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py -k write_file -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
cd core
git add app/pipelines/runtime.py app/pipelines/registries.py \
  tests/test_pipeline_file_io.py
git commit -m "$(cat <<'EOF'
feat(core): implémente writer.file (COPY GDAL local, gardé par le flag)

Écrit un fichier géospatial local via DuckDB spatial (même mécanisme que le
in_path de _execute_qgis_transform), pas la sérialisation manuelle de
writer.export. srid pris depuis srid_by_node[pred_id], déjà calculé par
_prepare()/_execute_transform_chain — aucun nouveau calcul. Colonnes fid/
OGC_FID réservées par GDAL exclues explicitement (vérifié empiriquement :
sans ça, COPY ... DRIVER 'GPKG' échoue sur un passthrough reader.file ->
writer.file).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Tâche 6 : bout-en-bout + suite complète + portes de qualité

**Files:**
- Modify: `core/tests/test_pipeline_file_io.py`
- None autre créé/modifié — vérification et un dernier test d'intégration.

- [ ] **Step 1: Écrire le test bout-en-bout qui échoue si mal câblé**

Ajouter à `core/tests/test_pipeline_file_io.py` :

```python
from app.configs.schemas import PipelinePayload
from app.pipelines.runtime import run_pipeline


def test_run_pipeline_file_to_file_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    in_path = _write_geojson(tmp_path, name="in.geojson")
    out_path = tmp_path / "subdir" / "out.gpkg"
    payload = PipelinePayload.model_validate(
        {
            "nodes": [
                {
                    "id": "r1",
                    "kind": "reader",
                    "op": "reader.file",
                    "params": {"path": in_path},
                },
                {
                    "id": "t1",
                    "kind": "transform",
                    "op": "transform.select",
                    # TransformSelectParams.columns : dict {source: renommage
                    # optionnel | None}, PAS une liste — vérifié dans
                    # app/pipelines/compiler.py::_compile_select avant
                    # d'écrire ce test.
                    "params": {"columns": {"label": None, "geometry": None}},
                },
                {
                    "id": "w1",
                    "kind": "writer",
                    "op": "writer.file",
                    "params": {"path": str(out_path)},
                },
            ],
            "edges": [
                {"id": "e1", "from": "r1", "to": "t1"},
                {"id": "e2", "from": "t1", "to": "w1"},
            ],
        }
    )
    stats = run_pipeline(
        session=None,
        payload=payload,
        tenant_id="t1",
        user=None,
        endpoint_url="http://localhost:9000",
        access_key="x",
        secret_key="y",
        base_uri=str(tmp_path),
    )
    assert {s.op for s in stats} == {"reader.file", "transform.select", "writer.file"}
    check_conn = _connection()
    rows = check_conn.execute(
        f"SELECT label FROM ST_Read('{out_path}') ORDER BY label"
    ).fetchall()
    assert rows == [("a",), ("b",)]
```

(Le champ `columns` de `TransformSelectParams` est un dict `{source:
renommage optionnel}`, pas une liste — déjà pris en compte ci-dessus, cf.
`app/pipelines/compiler.py::_compile_select`, vérifié avant d'écrire ce
plan.)

- [ ] **Step 2: Vérifier, corriger, faire passer**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py -v`
Expected: PASS (17 tests au total : 16 des tâches précédentes + celui-ci).

- [ ] **Step 3: Suite pipelines complète**

Run: `cd core && uv run pytest tests/test_pipeline_file_io.py tests/test_pipeline_runtime.py tests/test_pipeline_ops_contracts.py tests/test_pipeline_ops_schemas.py tests/test_pipeline_routes.py -q`

(Il n'existe pas de `test_pipeline_registries.py` dédié — `READERS`/
`WRITERS` sont couverts par ce plan lui-même
(`test_readers_registry_has_reader_file`/`test_writers_registry_has_writer_file`,
Tâches 4/5) et indirectement par `test_pipeline_runtime.py`. Vérifié avec
`ls core/tests/ | grep pipeline` avant d'écrire ce plan — si un nom a
changé depuis, relister avant de lancer cette commande.)

Expected: PASS. Si des tests `qgis`/`postgis` skippent faute de
`CORE_TEST_QGIS_WORKER_URL`/`CORE_TEST_DATABASE_URL`, le signaler
explicitement (piège CLAUDE.md #3/#12) plutôt que conclure "entièrement
vert" sans réserve.

- [ ] **Step 4: Suite complète du cœur + seuil de couverture**

Run: `cd core && uv run pytest -q`
Run: `cd core && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold`
Expected: 0 échec, couverture ≥ seuil (85).

- [ ] **Step 5: Portes de qualité statique**

Run:
```bash
cd core
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
```
Expected: aucune violation. `lint-imports` vérifie en particulier que
`app.pipelines.ops.contracts -> app.auth.dependency` et
`app.pipelines.runtime -> app.auth.dependency` sont autorisés — déjà le cas
pour `app.pipelines.jobs -> app.auth.dependency` (import identique,
existant avant ce plan), donc attendu sans exemption nouvelle. Si le
contrat les refuse malgré tout, ne PAS ajouter d'exemption sans
comprendre pourquoi `jobs.py` y échappait — le signaler plutôt que
contourner.

- [ ] **Step 6: Rapport de fin de plan**

Pas de commit de code à cette étape (vérification seule, sauf si le Step 2
a nécessité une correction du test — dans ce cas, committer cette
correction seule d'abord). Si tout est vert, passer à
`superpowers:requesting-code-review` avant de considérer cette tranche du
chantier desktop-etl terminée, conformément à CLAUDE.md (« une revue par
tâche et une revue finale de branche »).

```bash
cd core
git add tests/test_pipeline_file_io.py
git commit -m "$(cat <<'EOF'
test(core): pipeline reader.file -> transform -> writer.file bout-en-bout

Preuve d'intégration que les 3 tâches précédentes (flag, _lock_down élargi,
reader.file, writer.file) composent réellement : un pipeline fichier local
vers fichier local, en passant par un transform, tourne sans Postgres ni S3
réel — le scénario que le futur sidecar desktop devra exécuter.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Ce que ce plan ne couvre pas (volontairement)

- **Spike PyInstaller pour DuckDB spatial gelé** (geopandas/shapely/pyproj —
  résidu non prouvé du spike 01, cf.
  [`docs/superpowers/specs/2026-09-17-desktop-etl-spike-01-findings.md`](../specs/2026-09-17-desktop-etl-spike-01-findings.md)).
  Ce plan implémente et teste `reader.file`/`writer.file` en Python
  **non gelé** (`uv run pytest`, comme le reste du cœur) : le mécanisme
  ST_Read/COPY GDAL est déjà utilisé en production non gelée par
  `transform.qgis` — le risque de freeze PyInstaller ne concerne que
  l'empaquetage du futur sidecar desktop, pas cette tranche. À revérifier
  avant (pas pendant) la construction du binaire desktop.
- **API loopback HTTP du sidecar**, **implémentations en mémoire de
  `RunTracker`/`SecretResolver`**, **dossier `desktop-etl/` (Tauri, canvas
  React)** — inchangés depuis les tranches précédentes, toujours à
  reprendre avec `superpowers:brainstorming` puis
  `superpowers:writing-plans`.
- **UI shell pour choisir un fichier local** (`CollectionParamSelect` →
  sélecteur de fichier, design §2) : `reader.file`/`writer.file` restent
  invisibles dans la palette de l'éditeur de pipeline shell tant que
  `CORE_PIPELINE_FILE_IO_ENABLED` est éteint (défaut serveur) — et même
  activés, aucun sélecteur de fichier dédié n'existe côté shell à ce stade,
  seul un payload construit à la main (comme dans ce plan) peut les
  utiliser. Hors périmètre, explicitement du côté « intégration Tauri +
  réutilisation UI » du découpage §11.
- **Drivers GDAL autres que GPKG/GeoJSON** : `WriterFileParams.driver` est
  une chaîne libre, aucune restriction — seuls GPKG et GeoJSON sont
  vérifiés empiriquement par ce plan (CSV échoue à l'écriture d'une colonne
  géométrie via ce mécanisme, vérifié aussi, mais pas exclu par schéma :
  l'erreur GDAL à l'exécution suffit, cohérent avec le reste du module).

Plan complet et sauvegardé dans
`docs/superpowers/plans/2026-09-18-desktop-etl-reader-writer-file.md`.
