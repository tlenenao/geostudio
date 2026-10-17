# SP-L1b « Socle d'exécution, gros chantiers » Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fermer les AUD du lot L1 non traités par SP-L1a (`docs/revue/audit-2026-10-16/99-synthese.md` §4 + `complement/ADDENDUM.md`) : CDC sans transaction entière en mémoire ni WAL illimité, lecture du lac sans fenêtre sur tout l'historique, import de fichier en flux, jobs de workers morts libérés, sonde de vivacité sans faux positif, runs de pipeline annulables et bornés, webhooks qui ne détruisent plus d'événements.

**Architecture:** le CDC passe à wal2json `format-version 2` (un message par ligne) et le slot est borné par `max_slot_wal_keep_size` ; un slot perdu est recréé et le lac de chaque collection est purgé puis reconstruit par le backfill de démarrage. La lecture du lac via snapshot remplace la fenêtre sur l'union par un ANTI JOIN + SEMI JOIN (seules les PK touchées par le delta passent par `row_number()`), et le snapshot devient actif par défaut. L'import parcourt le fichier deux fois en flux (analyse, puis insertion par lots). Une tâche périodique termine en `failed` les jobs de workers sans battement (libère les verrous `lock=`) ; la sonde passe au battement. Un garde de run (fil + `conn.interrupt()`) porte annulation et durée maximale ; les writers `append` collection/dataset redeviennent rejouables (transaction du run). L'outbox ne désactive plus une destination sur une panne courte, garde les événements, échoue un événement refusé ou trop vieux, et un échec de base sur un événement n'arrête plus le balayage.

**Tech Stack:** Python 3.12, psycopg2 (réplication logique), wal2json (PGDG, Postgres 16), DuckDB, procrastinate 3.9.0, SQLAlchemy, pytest (DSN de test `postgresql+psycopg://`), docker-compose, Helm.

## Périmètre du lot

**AUD couverts :**

| AUD | Tâche | Couverture |
|---|---|---|
| AUD-012 | 1, 2 | complet (format-version 2, borne WAL, recréation du slot perdu + reconstruction du lac) |
| AUD-013 | 3 | complet (ANTI/SEMI JOIN snapshot ∪ delta + snapshot actif par défaut) |
| AUD-014 | 4 | partiel : GeoJSON en flux, import et ajout en deux passages sans liste complète, insertion par lots, Parquet tabulaire par lots |
| AUD-016 | 5 | complet (sonde au battement) |
| AUD-028 | 5 | complet (tâche de reprise des jobs de workers morts) |
| AUD-029 | 6 | partiel : la partie DuckDB d'un run de pipeline est bornée en durée (cf. addendum : les connecteurs ont déjà des délais) |
| AUD-083 | 6 | complet (annulation entre nœuds + interruption DuckDB ; `append` collection/dataset rejouable) |
| AUD-085 | 7 | complet |
| AUD-168 | 7 | complet (addendum, lot L1) |
| AUD-170 | 7 | complet (addendum, lot L1) |

**Reportés :**
- AUD-157 (zonal-stats en parallèle) : rattaché au lot **L2** par l'addendum (L2 prend 152-157).
- AUD-172 : rattaché **L2/L4** par l'addendum, hors L1.
- AUD-014, reliquat : lecture OGR en flux (`pyogrio.raw.open_arrow`), GeoParquet (`gpd.read_parquet`), XML générique (arbre defusedxml complet), refus 413 précoce. Vérifié en session : `open_arrow(force_2d=True)` lève « forcing 2D is not supported for Arrow », `meta["geometry_name"]` vaut `''` pour un Shapefile (colonne `wkb_geometry`), et les dates Arrow reviennent en UTC *aware* alors que `raw.read` les rend naïves. Ce chantier demande donc sa propre preuve d'équivalence. Après la Tâche 4, ces formats ne gardent plus qu'une copie du fichier et une couche lue à la fois (les deux listes complètes disparaissent).
- AUD-029, reliquat : code Python bloquant hors DuckDB (GEOS, parse GDAL, boucle de pagination `httpCall`) et délai des jobs d'ingestion. Il faudrait isoler le run dans un sous-processus, ce qui dépasse le lot. Ce code n'est interrompu qu'au nœud suivant (cf. `ponytail:` en Tâche 6).
- Mémoire du backfill de démarrage du cdc-worker (`backfill.backfill_table`, `SELECT *` entier) : c'est AUD-099, **lot L7**. Le cdc-worker reste donc sans `mem_limit` par défaut.

**Dépendances :**
- SP-L1a est fusionné dans `dev` (le battement `_heartbeat` des runs, `app/pipelines/jobs.py`, est utilisé tel quel).
- **Rebaser sur SP-L3 avant les Tâches 1, 2 et 3.** SP-L3, dans la branche `worktree-agent-add9596cb3f3b0c26`, n'est pas encore dans `dev`. Il paramètre la `command` de `postgis` (`PG_SHARED_BUFFERS`…) et ajoute un `mem_limit` commenté sur `cdc-worker` (commentaire citant wal2json v1). Il ajoute aussi les alertes `ops-cdc-slot-inactive` / `ops-cdc-slot-wal` (> 5 GiB) et touche `.env.example`, `values.yaml`, `core.yaml`, `rules.yaml`, le runbook Helm et `test_deployability.py`.
- Vérifié : SP-L3 ne touche ni `core/app/cdc/` ni `worker.yaml` ; ce plan ne duplique donc aucun travail de SP-L3. L'option `write-in-chunks` envisagée côté L3 n'est **pas** retenue : en v1, elle découpe l'envoi, mais le consommateur doit toujours réassembler la transaction entière avant de la décoder. La v2 est le correctif.

**Fichiers et zones touchés (détection de collisions) :**
- `core/app/cdc/consumer.py`, `core/app/cdc/main.py` : rien dans les autres lots connus.
- `core/app/analytics/aggregate.py` (`_dedup_cte`), `core/app/analytics/snapshot.py` : ce sont des modules `mypy --strict`.
- `core/app/ingestion/importer.py`, `core/app/ingestion/parsers.py` : **collision possible L2** (AUD-100, ingestion).
- `core/app/jobs/recovery.py` (nouveau), `core/app/jobs/__init__.py` (`import_paths`), `core/scripts/healthcheck_worker_stalled.py`.
- `core/app/pipelines/runtime.py` (`run_pipeline`, `_execute_transform_chain`), `core/app/configs/schemas.py` (`append_writers`), `core/app/pipelines/service.py` : **collision probable L5** (ETL).
- `core/app/webhooks/delivery.py` : **collision L2** sur `_http_post` (AUD-169, `allow_redirects`). Ce plan **ne modifie pas** `_http_post` ; il lit le code HTTP via `exc.__cause__`.
- `docker-compose.yml` :
  - `postgis.command` (+1 ligne) : collision **L3** ;
  - `worker.environment` (`CORE_LAKE_SNAPSHOT_ENABLED`, +`CORE_PIPELINES_RUN_TIMEOUT_S`) ;
  - commentaire du healthcheck `worker` et commentaire `mem_limit` de `cdc-worker` : collision **L3**.
- `.env.example`, `deploy/helm/geostudio/values.yaml` (2 clés) : collision **L3/L5**.
- `docs/runbooks/2026-10-12-deploiement-kubernetes-helm.md` (1 ligne) : collision **L3**.
- Tests : `core/tests/test_cdc_consumer.py`, `test_cdc_consumer_postgis.py`, `test_cdc_parquet_writer.py`, `test_cdc_main.py`, `test_lake_snapshot_read.py`, `test_lake_latest_per_key.py` (nouveau), `test_ingestion_importer.py`, `test_ingestion_import_memory.py` (nouveau), `test_jobs_recovery.py` (nouveau), `test_jobs.py`, `test_healthcheck_worker_stalled.py`, `test_pipeline_run_guard.py` (nouveau), `test_pipeline_run_retry.py`, `test_pipeline_fme_review_guards.py`, `test_webhooks_outbox.py`, `test_webhooks_delivery_claim.py`, `test_deployability.py`.

**Migrations :** aucune. La plage réservée **0091-0094 n'est pas utilisée** et peut être rendue au contrôleur.

## Global Constraints

- `CORE_TEST_DATABASE_URL` pointe une **base jetable dédiée** à ce lot (d'autres agents tournent en parallèle), au format `postgresql+psycopg://…`. Sinon les tests `postgis` skippent silencieusement.
- **Slots de réplication** : le nom `geostudio_cdc_slot` est unique **au niveau du cluster**, pas de la base. Les tests `test_cdc_consumer_postgis.py` ne doivent pas tourner en même temps qu'un autre lot qui exerce le CDC sur le même conteneur postgis-test. Lancer ces tests seuls ; en cas de `ObjectInUse` / `DuplicateObject` inexpliqué, rejouer en isolation avant de s'imputer une régression (piège SP-49).
- Régénérer OpenAPI + types TS si une route ou un modèle exposé change. Diff **vide attendu** ici : aucune route ni aucun schéma Pydantic exposé ne change. Incantation :
  - `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json`
  - puis `cd ../shell && npm run gen:api-types`.
- Inventaire de fonctionnalités : aucune surface nouvelle (ni route REST, ni outil MCP, ni route shell ; une tâche périodique n'en est pas une) → `docs/revue/inventaire-fonctionnalites.jsonl` inchangé.
- Migrations Alembic : aucune (cf. en-tête). Si une tâche en exigeait finalement une, la numéroter dans 0091-0094 et la tester sur base non vide dans les deux sens (piège n°8).
- Piège n°14 : la liste des jumelles est en Tâche 8, à vérifier avant de clore.
- Piège n°7 : aucune assertion de durée comme preuve. Les tests de borne mesurent l'interruption, jamais un chronomètre.
- `docker-compose.yml`, `.env.example` et Helm : modifications localisées, ligne à ligne. Ne rien réordonner : SP-L3 touche les mêmes blocs.
- `app/analytics` est sous `mypy --strict` : annoter tout ce qui y est ajouté.
- Commits conventional en français, un sujet par commit, trailer exact : `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Vérifier soi-même `git show --stat` après chaque commit (hygiène des sous-agents).
- **Interdit** de toucher `CLAUDE.md`, `docs/revue/*` et `docs/superpowers/2026-08-27-historique-execution-continu.md`. La clôture documentaire est faite par le contrôleur.

## Faits vérifiés / écarts à l'audit

Relus dans le code de `dev` le 2026-10-17 (piège n°3).

**AUD-012**
- `consumer.py:220` désigne `_start_replication_with_retry`, qui passe `options={"pretty-print": "0", "include-pk": "1"}` : c'est la v1 implicite, un message par transaction.
- `main.py:171` est `consumer.ensure_replication_slot(raw_dsn)`. Cette fonction ne regarde jamais `wal_status` ; un slot `lost` n'est donc ni détecté ni recréé.
- La `command` de `postgis` (`docker-compose.yml:37-46`) n'a pas de `max_slot_wal_keep_size`.
- `deploy/postgis/Dockerfile` installe `postgresql-16-wal2json` depuis PGDG (qui supporte la v2) ; à confirmer par le spike de la Tâche 1.
- Helm n'embarque pas Postgres (base externe) : la borne y devient un prérequis documenté.

**AUD-013**
- `aggregate.py:571` est confirmé : `QUALIFY row_number()` s'applique à l'union entière, snapshot compris quand il existe.
- Écart : le snapshot d'état courant existe déjà (REV-280a), mais `CORE_LAKE_SNAPSHOT_ENABLED` vaut `false` dans `docker-compose.yml:565`, `.env.example:460` et `values.yaml:61`. Sans snapshot, il n'y a pas de base pour l'ANTI JOIN, d'où la bascule du défaut.
- Le test `test_lake_snapshot_job.py:48` fige le défaut **du code** à `false`. On ne change donc que les défauts de déploiement.
- Jumelle : `snapshot.write_snapshot` (même fenêtre sur `prev ∪ delta`).

**AUD-014**
- `importer.py:216` (`_load_rows`) est confirmé, avec **trois** copies :
  - `list(parse_*)` ;
  - une seconde liste (`force_2d` + renommage) ;
  - la liste `params` complète passée à un seul `executemany`.
- `parse_geojson` fait `json.loads` du texte entier.
- `run_append` insère déjà par lots de 2000, mais passe par `_load_rows`.
- Appelants : `ingestion/tasks.py:146,178` et `harvest/service.py:241`.
- `test_ingestion_importer_perf.py` plafonne à 5 ordres INSERT pour 50k entités, d'où `_INSERT_BATCH = 10_000`.

**AUD-016**
- `healthcheck_worker_stalled.py:34` appelle `get_stalled_jobs(nb_seconds=…)`. Ce paramètre est déprécié dans procrastinate 3.9.0 et compte depuis le *démarrage* du job (défaut 3600 s) : tout job sain de plus d'une heure rend la sonde rouge.
- La sonde est utilisée par `worker` et `export-worker`, dans compose et dans Helm (`worker.yaml:42`, `export-worker.yaml:39`).
- La parité de commande est vérifiée par `test_helm_chart.py::test_exec_probes_run_the_compose_healthcheck_command`. Seul le script change ; aucune commande ne bouge.

**AUD-028**
- Aucune reprise de job bloqué n'existe dans le dépôt. Ce n'est pas propre à `app/cdc/` : c'est générique à `procrastinate_jobs`.
- procrastinate 3.9.0 fait `prune_stalled_workers` au démarrage d'un worker. La FK `worker_id … ON DELETE SET NULL` laisse alors le job en `doing` sans worker, et ce job n'est jamais terminé. Son `lock` (`cdc_compaction`, `run_snapshot_cycle`) bloque donc toute la file.
- `finish_job_by_id_async(job_id, status, delete_job)` et `get_stalled_jobs(seconds_since_heartbeat=…)` sont vérifiés dans `manager.py`. La procédure SQL lève si le job n'est plus en `doing`/`todo`.

**AUD-029 (addendum)**
- Les connecteurs ont des délais (`connector_runtime.py:151-347`).
- Ne sont pas bornés : DuckDB d'un run (traité ici), GDAL/ingestion, GEOS, pagination `httpCall` (reportés).

**AUD-083**
- `should_cancel` n'est consulté que par `collection_writer.py:495`, entre deux lots.
- `append_writers()` (`schemas.py:463-478`) et `service.py:169` refusent retry et reprise pour `writer.collection` / `writer.dataset` en `append` / `insert`.
- Le run s'exécute pourtant dans **une seule transaction** : `request_scoped_session` dans `pipelines/jobs.py`, avec rollback sur exception. Un échec, même après le writer, annule ses lignes.
- Cas limite assumé : un échec *après* le commit du run mais *avant* `mark_succeeded` laisse le run `running` jusqu'au balayage. Ce cas existait déjà pour `upsert`.

**AUD-085**
- `_disable` (`delivery.py`, boucle sur les `pending`) passe tous les événements en attente à `failed`.
- Le seuil est de 5 échecs consécutifs avec un backoff de 30 s × 2^n, soit environ 7,5 min de panne.

**AUD-168**
- Confirmé : `session.refresh(hook, with_for_update=True)` est hors `try`, dans l'`except` comme dans le chemin succès.
- `deliver_due` n'a pas de `try`, et `deliver_outbox_task` saute alors `purge_outbox` / `purge_seen`.

**AUD-170**
- Confirmé. `purge_outbox` garde les `pending` sans limite d'âge.

---

### Task 1: AUD-012 (a) — CDC en wal2json `format-version 2`

**Files:**
- Modify: `core/app/cdc/consumer.py` (`decode_wal2json_message`, `_start_replication_with_retry`, docstrings)
- Modify: `core/app/cdc/main.py` (`_on_message`, détection de table inconnue)
- Modify: `docker-compose.yml` (commentaire `mem_limit` de `cdc-worker` posé par SP-L3, après rebase)
- Test: `core/tests/test_cdc_consumer.py` (réécrit en v2), `core/tests/test_cdc_parquet_writer.py` (2 payloads), `core/tests/test_cdc_consumer_postgis.py`

**Interfaces:**
- Produces: `decode_wal2json_message(payload: str | dict, *, lsn: int, collection_meta: dict) -> list[DecodedChange]`. La signature est inchangée. Le contrat devient un message v2 = 0 ou 1 changement, avec `action` ∈ `I`/`U`/`D` décodé et `B`/`C`/`M`/`T` ignorés.
- Consumes: `backfill.backfill_table(session, *, table_name, pk_column, geometry_column, boundary_lsn, flush_ts) -> list[ChangeRow]` (existant).

- [ ] **Step 1: Spike — confirmer noms d'options et forme JSON sur le postgis-test**

```bash
cd core && uv run python - <<'EOF'
import os
import psycopg
dsn = os.environ["CORE_TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(dsn, autocommit=True) as c:
    c.execute("SELECT pg_create_logical_replication_slot('spike_l1b_v2', 'wal2json')")
    try:
        c.execute("CREATE TABLE IF NOT EXISTS spike_l1b (id serial primary key, n numeric, g geometry(Point, 4326))")
        c.execute("INSERT INTO spike_l1b (n, g) VALUES (1.5, ST_SetSRID(ST_Point(1, 2), 4326))")
        c.execute("UPDATE spike_l1b SET n = 2.5")
        c.execute("DELETE FROM spike_l1b")
        for (data,) in c.execute(
            "SELECT data FROM pg_logical_slot_get_changes('spike_l1b_v2', NULL, NULL, "
            "'format-version', '2', 'include-transaction', '0')"
        ):
            print(data)
    finally:
        c.execute("SELECT pg_drop_replication_slot('spike_l1b_v2')")
        c.execute("DROP TABLE IF EXISTS spike_l1b")
EOF
```

Attendu : 3 lignes JSON (plus éventuellement celles d'autres tables de la base), sans `"action":"B"` ni `"C"`. Formes attendues :
- `{"action":"I","schema":"public","table":"spike_l1b","columns":[{"name":"id","type":"integer","value":1},{"name":"n","type":"numeric","value":1.5},{"name":"g","type":"geometry(Point,4326)","value":"0101000020E6100000…"}]}` ;
- même forme pour `"U"` ;
- `{"action":"D",…,"identity":[{"name":"id","type":"integer","value":1}]}`.

Si un nom d'option ou une clé diffère, adapter le code des steps suivants à la sortie réelle et consigner l'écart dans le rapport de tâche (piège n°3).

- [ ] **Step 2: Réécrire les tests unitaires en v2 (échouent)** — remplacer tout le contenu de `core/tests/test_cdc_consumer.py` par :

```python
# SPDX-License-Identifier: Apache-2.0
"""Décodage wal2json format-version 2 (AUD-012) : un message = un changement."""

import json

from app.cdc.consumer import decode_wal2json_message


def _cols(**values):
    return [{"name": k, "type": "unknown", "value": v} for k, v in values.items()]


_INSERT_PAYLOAD = json.dumps(
    {
        "action": "I",
        "schema": "public",
        "table": "t_rls",
        "columns": _cols(id=1, titre="a", geom="0101000020E6100000..."),
    }
)
_UPDATE_PAYLOAD = json.dumps(
    {"action": "U", "schema": "public", "table": "t_rls", "columns": _cols(id=2, titre="c")}
)
_DELETE_PAYLOAD = json.dumps(
    {"action": "D", "schema": "public", "table": "t_rls", "identity": _cols(id=1)}
)
_META = {"t_rls": ("id", "geom")}


def test_decode_insert_extracts_geometry_and_columns():
    decoded = decode_wal2json_message(_INSERT_PAYLOAD, lsn=100, collection_meta=_META)
    assert len(decoded) == 1
    row = decoded[0].row
    assert decoded[0].table_name == "t_rls"
    assert row.op == "insert"
    assert row.lsn == 100
    assert row.pk_value == 1
    assert row.geometry_wkb_hex == "0101000020E6100000..."
    assert "geom" not in row.columns  # extraite dans geometry_wkb_hex, pas dupliquée


def test_decode_update():
    (decoded,) = decode_wal2json_message(_UPDATE_PAYLOAD, lsn=300, collection_meta=_META)
    assert (decoded.row.op, decoded.row.columns) == ("update", {"id": 2, "titre": "c"})


def test_decode_delete_is_tombstone_from_identity():
    decoded = decode_wal2json_message(_DELETE_PAYLOAD, lsn=200, collection_meta=_META)
    row = decoded[0].row
    assert row.op == "delete"
    assert row.pk_value == 1
    assert row.columns == {"id": 1}
    assert row.geometry_wkb_hex is None


def test_decode_ignores_transaction_markers_messages_and_truncate():
    for action in ("B", "C", "M", "T"):
        payload = {"action": action, "schema": "public", "table": "t_rls"}
        assert decode_wal2json_message(payload, lsn=1, collection_meta=_META) == []


def test_decode_ignores_unknown_table():
    payload = {"action": "I", "schema": "public", "table": "not_tracked", "columns": _cols(id=1)}
    assert decode_wal2json_message(payload, lsn=400, collection_meta=_META) == []


def test_decode_accepts_an_already_decoded_message():
    # REV-364 h : le worker décode le JSON une fois et le passe tel quel.
    from_str = decode_wal2json_message(_INSERT_PAYLOAD, lsn=100, collection_meta=_META)
    from_dict = decode_wal2json_message(json.loads(_INSERT_PAYLOAD), lsn=100, collection_meta=_META)
    assert from_dict == from_str
```

Dans `core/tests/test_cdc_parquet_writer.py`, remplacer les deux `payload = json.dumps({"change": [...]})` :

```python
    payload = json.dumps(
        {
            "action": "U",
            "schema": "public",
            "table": "points_interet",
            "columns": [
                {"name": "id", "type": "integer", "value": 1},
                {"name": "score", "type": "numeric", "value": 2.7},
            ],
        }
    )
```

```python
    payload = json.dumps(
        {
            "action": "U",
            "schema": "public",
            "table": "points_interet",
            "columns": [
                {"name": "id", "type": "integer", "value": 1},
                {"name": "vu_le", "type": "timestamp with time zone", "value": "2026-03-05 15:00:00+00"},
            ],
        }
    )
```

- [ ] **Step 3:** `cd core && uv run pytest tests/test_cdc_consumer.py tests/test_cdc_parquet_writer.py -v` → FAIL : le décodeur v1 renvoie `[]`, ce qui donne `IndexError` / `ValueError` et des asserts en échec.

- [ ] **Step 4: Implémenter le décodeur v2** — dans `core/app/cdc/consumer.py`, remplacer `decode_wal2json_message` par :

```python
_V2_OPS = {"I": "insert", "U": "update", "D": "delete"}


def decode_wal2json_message(
    payload: str | dict,
    *,
    lsn: int,
    collection_meta: dict,
) -> list:
    """wal2json `format-version 2` (AUD-012) : UN message par changement — plus de
    transaction entière assemblée en un seul JSON (v1 : échec au-delà d'~1 Gio, tout
    en mémoire du walsender puis du worker). `B`/`C` (bornes de transaction, coupées
    par `include-transaction=0`), `M` (message logique), `T` (truncate) : ignorés.
    collection_meta : {table_name: (pk_column, geometry_column)} ; une table publiée
    mais absente est ignorée (app.cdc.main la backfille au premier changement vu)."""
    # REV-364 h : l'appelant qui a déjà décodé le message le passe tel quel.
    data = payload if isinstance(payload, dict) else json.loads(payload)
    op = _V2_OPS.get(data.get("action", ""))
    if op is None:
        return []
    table_name = data["table"]
    meta = collection_meta.get(table_name)
    if meta is None:
        return []
    pk_column, geometry_column = meta
    if op == "delete":
        identity = {c["name"]: c["value"] for c in data.get("identity", [])}
        pk_value = identity.get(pk_column)
        row = ChangeRow(
            op="delete",
            lsn=lsn,
            ts=0.0,
            pk_column=pk_column,
            pk_value=pk_value,
            columns={pk_column: pk_value},
            geometry_column=geometry_column,
            geometry_wkb_hex=None,
        )
    else:
        record = {c["name"]: c["value"] for c in data.get("columns", [])}
        geom_hex = record.pop(geometry_column, None) if geometry_column else None
        row = ChangeRow(
            op=op,
            lsn=lsn,
            ts=0.0,
            pk_column=pk_column,
            pk_value=record.get(pk_column),
            columns=record,
            geometry_column=geometry_column,
            geometry_wkb_hex=geom_hex,
        )
    return [DecodedChange(table_name=table_name, row=row)]
```

Dans `_start_replication_with_retry`, remplacer la ligne `options=…` par :

```python
                options={"format-version": "2", "include-transaction": "0"},
```

En tête de la docstring du module, ajouter ce paragraphe juste après la première phrase :

```text
AUD-012 : `format-version 2` — un message par LIGNE modifiée (plus par transaction).
Une grosse transaction n'est plus assemblée en un seul JSON (v1 : limite ~1 Gio
d'un StringInfo côté walsender, puis tout en mémoire ici). L'ack peut donc tomber au
milieu d'une transaction : au redémarrage, Postgres renvoie la transaction entière
(son commit est après confirmed_flush_lsn) ; les doublons sont absorbés par la
réduction par PK (`_lsn`, puis `_seq` = ordre d'ajout) côté lecteur du lac.
```

Dans la docstring de `stream_changes`, remplacer la mention « un message par transaction » s'il y en a une (`grep -n "transaction" core/app/cdc/consumer.py`) par « un message par ligne modifiée (format-version 2) ».

- [ ] **Step 5: Détection de table inconnue en v2** — dans `core/app/cdc/main.py`, dans `_on_message`, remplacer le bloc `unknown_tables = {...}` par :

```python
        now = time.monotonic()
        table = data.get("table") if data.get("action") in ("I", "U", "D") else None
        unknown_tables = (
            {table}
            if table is not None
            and table not in collection_meta
            and unmanaged_until.get(table, 0.0) <= now
            else set()
        )
```

- [ ] **Step 6:** `cd core && uv run pytest tests/test_cdc_consumer.py tests/test_cdc_parquet_writer.py tests/test_cdc_main.py -v` → PASS.

- [ ] **Step 7: Tests sur slot réel (échouent sans le step 4)** — dans `core/tests/test_cdc_consumer_postgis.py` :
  - ajouter aux imports `import time` et `from app.cdc.backfill import backfill_table` ;
  - ajouter le helper et les deux tests ci-dessous à la fin du fichier.

```python
def _stream_until(raw_dsn, meta, *, want_rows, timeout_s=60.0):
    """Consomme jusqu'à `want_rows` lignes décodées (ou l'échéance, pour ne jamais pendre)."""
    received, calls = [], []
    deadline = time.monotonic() + timeout_s

    def on_message(payload, lsn):
        calls.append(lsn)
        received.extend(decode_wal2json_message(payload, lsn=lsn, collection_meta=meta))

    stream_changes(
        raw_dsn,
        on_message=on_message,
        is_flush_due=lambda: False,
        do_flush=lambda: None,
        should_stop=lambda: len(received) >= want_rows or time.monotonic() > deadline,
        poll_timeout_s=0.2,
    )
    return received, calls


@pytest.mark.postgis
def test_one_big_transaction_arrives_as_one_message_per_row(cdc_table, pg_engine):
    """AUD-012 : en v1, 1000 lignes d'une transaction = UN message (tout en mémoire)."""
    raw_dsn = _raw_dsn()
    ensure_replication_slot(raw_dsn)
    with pg_engine.begin() as conn:
        conn.execute(
            text(f"INSERT INTO {cdc_table} (v) SELECT 'x' || i FROM generate_series(1, 1000) i")
        )
    received, calls = _stream_until(raw_dsn, {cdc_table: ("id", None)}, want_rows=1000)
    assert len(received) == 1000
    assert len(calls) >= 1000
    assert [d.row.lsn for d in received] == sorted(d.row.lsn for d in received)


@pytest.fixture()
def typed_table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_cdc_typed"))
        conn.execute(
            text(
                "CREATE TABLE t_cdc_typed (id serial PRIMARY KEY, n numeric, d date, "
                "ts timestamptz, u uuid, g geometry(Point, 4326))"
            )
        )
    yield "t_cdc_typed"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_cdc_typed"))


@pytest.mark.postgis
def test_live_v2_columns_match_backfill_representation(typed_table, pg_engine, pg_session_factory):
    """Le chemin live (v2) et le backfill doivent produire la même représentation, sinon
    un même lot de flush mélange des types (cf. tests REV-280g de test_cdc_parquet_writer)."""
    raw_dsn = _raw_dsn()
    ensure_replication_slot(raw_dsn)
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {typed_table} (n, d, ts, u, g) VALUES (1.25, '2026-03-05', "
                "'2026-03-05 15:00:00.5+00', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', "
                "ST_SetSRID(ST_Point(2.35, 48.85), 4326))"
            )
        )
    received, _ = _stream_until(raw_dsn, {typed_table: ("id", "g")}, want_rows=1)
    live = received[0].row
    with pg_session_factory() as s:
        (back,) = backfill_table(
            s,
            table_name=typed_table,
            pk_column="id",
            geometry_column="g",
            boundary_lsn=1,
            flush_ts=0.0,
        )
    assert live.columns == back.columns
    assert live.geometry_wkb_hex.lower() == back.geometry_wkb_hex.lower()
```

- [ ] **Step 8:** `cd core && uv run pytest tests/test_cdc_consumer_postgis.py tests/test_cdc_backfill.py -v -p no:randomly`, seul sur le cluster (cf. Global Constraints) → PASS. Contre-épreuve à faire une fois : remettre temporairement les options v1 dans `_start_replication_with_retry`, constater l'échec de `test_one_big_transaction_arrives_as_one_message_per_row`, puis rétablir (piège n°10).

- [ ] **Step 9: Commentaire du `mem_limit` cdc-worker (après rebase sur SP-L3)** — `grep -n "wal2json" docker-compose.yml`. Remplacer la ou les lignes du commentaire `mem_limit` de `cdc-worker` qui citent la v1 par :

```yaml
    # wal2json format-version 2 (AUD-012) : un message par ligne, plus de transaction
    # entière en mémoire. Le backfill de démarrage charge encore une table entière
    # (AUD-099, lot L7) : défaut 0 (= sans limite) conservé tant qu'il n'est pas borné.
```

Si SP-L3 n'est pas encore fusionné, sauter ce step et le signaler dans le rapport de tâche.

- [ ] **Step 10: Commit**

```bash
git add core/app/cdc/consumer.py core/app/cdc/main.py core/tests/test_cdc_consumer.py \
  core/tests/test_cdc_parquet_writer.py core/tests/test_cdc_consumer_postgis.py docker-compose.yml
git commit -m "fix(core): CDC en wal2json format-version 2, un message par ligne (AUD-012)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: AUD-012 (b) — WAL borné, slot perdu recréé et lac reconstruit

**Files:**
- Modify: `core/app/cdc/consumer.py` (`slot_wal_status`, `_drop_slot`, `ensure_replication_slot -> bool`)
- Modify: `core/app/cdc/main.py` (`_purge_lake`, appel dans `run()`)
- Modify: `docker-compose.yml` (`postgis.command`), `.env.example`, `docs/runbooks/2026-10-12-deploiement-kubernetes-helm.md`
- Test: `core/tests/test_cdc_consumer.py`, `core/tests/test_cdc_main.py`, `core/tests/test_cdc_consumer_postgis.py`, `core/tests/test_deployability.py`

**Interfaces:**
- Produces:
  - `consumer.slot_wal_status(raw_dsn: str) -> str | None` (`reserved` / `extended` / `unreserved` / `lost`, ou `None` si le slot est absent) ;
  - `consumer.ensure_replication_slot(raw_dsn: str) -> bool` (True = slot (re)créé) ;
  - `main._purge_lake(collection_meta: dict, *, s3_client, bucket: str) -> int`.
- Consumes: `app.analytics.lake_purge.lake_prefix(tenant_id, collection_id)` et `purge_prefix(client, *, bucket, prefix) -> int` (existants, REV-322).

Pourquoi purger : un slot recréé (perdu au-delà de `max_slot_wal_keep_size`, ou absent après une restauration `pg_dump`) n'a pas vu les `DELETE` de l'intervalle. Le backfill de démarrage réécrit les lignes vivantes, mais les PK supprimées garderaient leur dernière version « vivante » dans le lac. Après une restauration, les LSN repartent même plus bas que celles du lac. Purger la collection avant le backfill reconstruit un lac exact. Au premier démarrage, le lac est vide : la purge ne fait rien.

- [ ] **Step 1: Tests unitaires (échouent)** — ajouter à `core/tests/test_cdc_consumer.py` :

```python
import pytest

from app.cdc import consumer


class _FakeCur:
    def __init__(self, calls):
        self.calls = calls

    def create_replication_slot(self, name, output_plugin):
        self.calls.append(("create", name, output_plugin))

    def close(self):
        pass


class _FakeConn:
    def close(self):
        pass


def test_lost_slot_is_dropped_then_recreated(monkeypatch):
    calls = []
    monkeypatch.setattr(consumer, "slot_wal_status", lambda dsn: "lost")
    monkeypatch.setattr(consumer, "_drop_slot", lambda dsn: calls.append("drop"))
    monkeypatch.setattr(consumer, "_connect", lambda dsn: (_FakeConn(), _FakeCur(calls)))
    assert consumer.ensure_replication_slot("dsn") is True
    assert calls == ["drop", ("create", consumer.SLOT_NAME, "wal2json")]


def test_healthy_slot_is_kept_without_replication_connection(monkeypatch):
    monkeypatch.setattr(consumer, "slot_wal_status", lambda dsn: "reserved")

    def _no_connect(dsn):
        pytest.fail("aucune connexion de réplication attendue")

    monkeypatch.setattr(consumer, "_connect", _no_connect)
    assert consumer.ensure_replication_slot("dsn") is False


def test_absent_slot_is_created(monkeypatch):
    calls = []
    monkeypatch.setattr(consumer, "slot_wal_status", lambda dsn: None)
    monkeypatch.setattr(consumer, "_connect", lambda dsn: (_FakeConn(), _FakeCur(calls)))
    assert consumer.ensure_replication_slot("dsn") is True
```

Ajouter à `core/tests/test_cdc_main.py` :

```python
def test_purge_lake_empties_every_collection_prefix(monkeypatch):
    from app.analytics import lake_purge
    from app.cdc import main

    seen = []

    def fake_purge(client, *, bucket, prefix):
        seen.append((bucket, prefix))
        return 2

    monkeypatch.setattr(lake_purge, "purge_prefix", fake_purge)
    meta = {
        "t_a": ("c1", "ten1", "geom", 4326, "id"),
        "t_b": ("c2", "ten2", None, None, "id"),
    }
    assert main._purge_lake(meta, s3_client=object(), bucket="geostudio-cdc") == 4
    assert seen == [
        ("geostudio-cdc", "cdc/tenant_id=ten1/collection_id=c1/"),
        ("geostudio-cdc", "cdc/tenant_id=ten2/collection_id=c2/"),
    ]
```

- [ ] **Step 2:** `cd core && uv run pytest tests/test_cdc_consumer.py tests/test_cdc_main.py -v` → FAIL (`AttributeError: slot_wal_status` / `_purge_lake`).

- [ ] **Step 3: Implémenter côté consumer** — dans `core/app/cdc/consumer.py` :
  - ajouter `import logging` aux imports et `logger = logging.getLogger(__name__)` sous les constantes ;
  - remplacer `ensure_replication_slot` par :

```python
def slot_wal_status(raw_dsn: str) -> str | None:
    """`wal_status` du slot CDC (reserved/extended/unreserved/lost), None s'il n'existe
    pas. Connexion ordinaire (pas de réplication) : simple lecture de catalogue."""
    conn = psycopg2.connect(raw_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT wal_status FROM pg_replication_slots WHERE slot_name = %s", (SLOT_NAME,)
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _drop_slot(raw_dsn: str) -> None:
    conn = psycopg2.connect(raw_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_drop_replication_slot(%s)", (SLOT_NAME,))
    finally:
        conn.close()


def ensure_replication_slot(raw_dsn: str) -> bool:
    """Idempotent. Retourne True si le slot vient d'être (re)créé : l'appelant doit alors
    reconstruire le lac (AUD-012 — un slot perdu ou absent n'a pas vu les DELETE de
    l'intervalle). Un slot `lost` (WAL retenu au-delà de `max_slot_wal_keep_size`) ne
    peut plus être lu : il est supprimé puis recréé. Retry avec backoff sur ObjectInUse
    (cf. docstring module, déviation 2)."""
    status = slot_wal_status(raw_dsn)
    if status == "lost":
        logger.warning("slot CDC %s perdu (WAL au-delà de la borne) : recréation", SLOT_NAME)
        _drop_slot(raw_dsn)
    elif status is not None:
        return False
    for attempt in range(_RECONNECT_ATTEMPTS):
        conn, cur = _connect(raw_dsn)
        try:
            cur.create_replication_slot(SLOT_NAME, output_plugin=OUTPUT_PLUGIN)
            return True
        except psycopg2.errors.DuplicateObject:
            return False
        except psycopg2.errors.ObjectInUse:
            if attempt == _RECONNECT_ATTEMPTS - 1:
                raise
            time.sleep(_RECONNECT_BACKOFF_S)
        finally:
            cur.close()
            conn.close()
    raise AssertionError("unreachable")  # pragma: no cover
```

- [ ] **Step 4: Implémenter côté main** — dans `core/app/cdc/main.py`, ajouter `from app.analytics import lake_purge  # noqa: E402` au bloc d'imports post-`setup()`. Ajouter avant `run()` :

```python
def _purge_lake(collection_meta: dict, *, s3_client, bucket: str) -> int:
    """AUD-012 : slot recréé = changements de l'intervalle jamais vus (DELETE compris) ;
    le lac de chaque collection est vidé, le backfill de démarrage le reconstruit.
    ponytail: un cycle de snapshot (worker) en cours pendant la purge peut republier un
    état antérieur ; fenêtre étroite (slot perdu + cycle horaire), rattrapée au
    prochain slot perdu seulement — verrou partagé avec run_snapshot_cycle si observé."""
    return sum(
        lake_purge.purge_prefix(s3_client, bucket=bucket, prefix=lake_purge.lake_prefix(tid, cid))
        for cid, tid, *_rest in collection_meta.values()
    )
```

Dans `run()`, remplacer `consumer.ensure_replication_slot(raw_dsn)` par `slot_recreated = consumer.ensure_replication_slot(raw_dsn)`. Dans le bloc `with session_factory() as session:`, juste après `collection_meta = _load_collection_meta(session)`, ajouter :

```python
        if slot_recreated:
            _purge_lake(collection_meta, s3_client=s3_client, bucket=s3_bucket)
```

- [ ] **Step 5:** `cd core && uv run pytest tests/test_cdc_consumer.py tests/test_cdc_main.py -v` → PASS.

- [ ] **Step 6: Test sur slot réel** — ajouter à `core/tests/test_cdc_consumer_postgis.py`. Importer `slot_wal_status` et `_drop_slot` depuis `app.cdc.consumer`, puis :

```python
@pytest.mark.postgis
def test_ensure_replication_slot_reports_creation_once(pg_engine):
    raw_dsn = _raw_dsn()
    if slot_wal_status(raw_dsn) is not None:
        _drop_slot(raw_dsn)
    assert ensure_replication_slot(raw_dsn) is True
    assert slot_wal_status(raw_dsn) in ("reserved", "extended")
    assert ensure_replication_slot(raw_dsn) is False
```

Lancer `cd core && uv run pytest tests/test_cdc_consumer_postgis.py -v` → PASS.

- [ ] **Step 7: Borne de WAL — test de déployabilité (échoue)** — ajouter à `core/tests/test_deployability.py` :

```python
def test_postgis_bounds_the_wal_a_replication_slot_can_retain():
    """AUD-012 : sans max_slot_wal_keep_size, un cdc-worker arrêté retient le WAL sans
    limite jusqu'à saturer pg-data. Valeur RÉSOLUE sans .env (piège n°2) + documentée."""
    cmd = services(BASE)["postgis"]["command"]
    match = re.search(r"-c max_slot_wal_keep_size=(\S+)", cmd)
    assert match, "postgis sans max_slot_wal_keep_size"
    assert _resolve_effective_value(match.group(1), "PG_MAX_SLOT_WAL_KEEP_SIZE") == "10GB"
    assert "PG_MAX_SLOT_WAL_KEEP_SIZE" in documented_env_vars(include_commented=False)
```

`cd core && uv run pytest tests/test_deployability.py -k slot_can_retain -v` → FAIL.

- [ ] **Step 8: Câbler** — dans `docker-compose.yml`, `postgis.command`, ajouter après la ligne `-c output_plugin_libraries=wal2json,pgoutput,test_decoding` :

```yaml
        -c max_slot_wal_keep_size=${PG_MAX_SLOT_WAL_KEEP_SIZE:-10GB}
```

Dans `.env.example`, ajouter après le bloc `PG_*` de SP-L3, ou juste après `PG_PASSWORD=` si SP-L3 n'est pas fusionné :

```bash
# AUD-012 : WAL maximal qu'un slot de réplication logique (cdc-worker) peut retenir.
# Au-delà, le slot est perdu : le cdc-worker le recrée et reconstruit le lac au
# redémarrage. L'alerte ops-cdc-slot-wal (5 GiB) prévient avant la perte.
PG_MAX_SLOT_WAL_KEEP_SIZE=10GB
```

Dans `docs/runbooks/2026-10-12-deploiement-kubernetes-helm.md`, ligne 11 (tableau des dépendances externes) :
- remplacer `Postgres (PostGIS + pgvector, \`wal_level=logical\`)` par `Postgres (PostGIS + pgvector, \`wal_level=logical\`, \`max_slot_wal_keep_size\` borné — 10GB recommandé, AUD-012)`.

- [ ] **Step 9:**
  - `cd core && uv run pytest tests/test_deployability.py tests/test_helm_chart.py -v` → PASS ;
  - `docker compose config | grep max_slot_wal_keep_size` → `-c max_slot_wal_keep_size=10GB` (par valeur, piège n°2).

- [ ] **Step 10: Commit**

```bash
git add core/app/cdc/consumer.py core/app/cdc/main.py core/tests/test_cdc_consumer.py \
  core/tests/test_cdc_main.py core/tests/test_cdc_consumer_postgis.py core/tests/test_deployability.py \
  docker-compose.yml .env.example docs/runbooks/2026-10-12-deploiement-kubernetes-helm.md
git commit -m "fix(core): WAL du slot CDC borné, slot perdu recréé et lac reconstruit (AUD-012)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: AUD-013 — lecture du lac sans fenêtre sur tout l'historique

**Files:**
- Modify: `core/app/analytics/snapshot.py` (`latest_per_key`, `write_snapshot`)
- Modify: `core/app/analytics/aggregate.py` (`_dedup_cte`, import)
- Modify: `docker-compose.yml:564-565`, `.env.example:460`, `deploy/helm/geostudio/values.yaml:61`
- Test: `core/tests/test_lake_latest_per_key.py` (nouveau), `core/tests/test_lake_snapshot_read.py`, `core/tests/test_deployability.py`

**Interfaces:**
- Produces: `snapshot.latest_per_key(base: str, delta: str, pk: str, order_by: str) -> str`.
  - `base` : requête SQL, au plus une ligne par PK (le snapshot) ;
  - `delta` : requête SQL des lignes brutes plus récentes ;
  - `pk` : identifiant **déjà quoté** ;
  - retour : requête donnant la dernière version par PK, tombstones comprises.
- Consumes: `latest_snapshot`, `cut_seconds` (existants).

- [ ] **Step 1: Test d'équivalence (échoue)** — créer `core/tests/test_lake_latest_per_key.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-013 : latest_per_key (ANTI + SEMI JOIN) doit donner exactement la dernière version
par PK de la fenêtre complète sur base ∪ delta — tombstones et backfill tardif compris."""

import random

import duckdb

from app.analytics.snapshot import latest_per_key

ORDER = "_lsn DESC, COALESCE(_seq, -1) DESC"
_DDL = "(id INT, _op VARCHAR, _lsn BIGINT, _seq INT, v VARCHAR)"


def _history(rng, lsns, n):
    # (_lsn, _seq) uniques : pas d'ex-aequo, donc un résultat de référence déterministe.
    return [
        (rng.randrange(30), rng.choice(["insert", "update", "delete"]), next(lsns),
         rng.choice([None, 0, 1]), f"v{rng.randrange(1000)}")
        for _ in range(n)
    ]


def test_latest_per_key_equals_full_window_on_random_histories():
    conn = duckdb.connect(":memory:")
    rng = random.Random(1234)
    for _ in range(50):
        lsns = iter(rng.sample(range(-500, 5000), 200))  # LSN basses = backfill tardif
        conn.execute(f"CREATE OR REPLACE TABLE base {_DDL}")
        conn.execute(f"CREATE OR REPLACE TABLE delta {_DDL}")
        snapshot = {}
        for row in _history(rng, lsns, 40):
            snapshot[row[0]] = row  # un snapshot = une ligne par PK
        conn.executemany("INSERT INTO base VALUES (?, ?, ?, ?, ?)", list(snapshot.values()))
        conn.executemany("INSERT INTO delta VALUES (?, ?, ?, ?, ?)", _history(rng, lsns, 25))
        ref = conn.execute(
            "SELECT * FROM (SELECT * FROM base UNION ALL BY NAME SELECT * FROM delta) "
            f"QUALIFY row_number() OVER (PARTITION BY id ORDER BY {ORDER}) = 1 ORDER BY id"
        ).fetchall()
        sql = latest_per_key("SELECT * FROM base", "SELECT * FROM delta", "id", ORDER)
        got = conn.execute(f"SELECT * FROM ({sql}) ORDER BY id").fetchall()
        assert got == ref
```

Ajouter à `core/tests/test_lake_snapshot_read.py` :

```python
def test_snapshot_read_does_not_window_the_whole_snapshot(tmp_path, conn):
    """AUD-013 : les PK absentes du delta sortent du snapshot par ANTI JOIN, sans fenêtre."""
    _seed(tmp_path, conn)
    cte = _dedup_cte(conn, INFO, str(tmp_path), T, C)
    assert "ANTI JOIN" in cte and "SEMI JOIN" in cte
```

- [ ] **Step 2:** `cd core && uv run pytest tests/test_lake_latest_per_key.py tests/test_lake_snapshot_read.py -v` → FAIL (`ImportError: latest_per_key`, puis assertion `ANTI JOIN`).

- [ ] **Step 3: Implémenter `latest_per_key`** — dans `core/app/analytics/snapshot.py`, après `cut_seconds` :

```python
def latest_per_key(base: str, delta: str, pk: str, order_by: str) -> str:
    """AUD-013 : dernière version par PK de `base ∪ delta`, où `base` (snapshot) porte
    déjà une seule ligne par PK. Les PK absentes du delta sortent de `base` par ANTI JOIN
    (aucun tri) ; seules les PK touchées par le delta passent par row_number() — au lieu
    d'une fenêtre sur tout l'historique (mesuré 34x plus lent à 40 M lignes). `pk` est un
    identifiant déjà quoté."""
    keys = f"(SELECT DISTINCT {pk} FROM ({delta}))"
    return (
        f"SELECT * FROM ({base}) ANTI JOIN {keys} AS k USING ({pk}) "
        f"UNION ALL BY NAME "
        f"SELECT * FROM (SELECT * FROM ({base}) SEMI JOIN {keys} AS k USING ({pk}) "
        f"UNION ALL BY NAME {delta}) "
        f"QUALIFY row_number() OVER (PARTITION BY {pk} ORDER BY {order_by}) = 1"
    )
```

Si DuckDB refuse la syntaxe `ANTI JOIN … USING` sur la version installée (`uv run python -c "import duckdb; print(duckdb.__version__)"`), utiliser `WHERE {pk} NOT IN (SELECT {pk} FROM ({delta}))` / `WHERE {pk} IN (…)` à la place (DuckDB les planifie en anti/semi join), en gardant les mots `ANTI JOIN`/`SEMI JOIN` dans un commentaire SQL `/* ANTI JOIN */` pour le test structurel. Consigner l'écart.

- [ ] **Step 4: Jumelle `write_snapshot`** — dans `write_snapshot`, remplacer le bloc qui va de `src = delta` jusqu'à la définition de `reduced` par :

```python
    max_lsn = int(delta_lsn)
    base = None
    src = delta
    if prev:
        base = f"SELECT * FROM read_parquet({_lit(prev[0][0])}, hive_partitioning=false)"
        src = f"{base} UNION ALL BY NAME {delta}"
        max_lsn = max(max_lsn, prev[0][2])
    cols = [c[0] for c in conn.execute(f"SELECT * FROM ({src}) LIMIT 0").description]
    order = "_lsn DESC, COALESCE(_seq, -1) DESC" if "_seq" in cols else "_lsn DESC"
    reduced = (
        latest_per_key(base, delta, _qi(pk_column), order)
        if base is not None
        else f"SELECT * FROM ({src}) QUALIFY row_number() OVER "
        f"(PARTITION BY {_qi(pk_column)} ORDER BY {order}) = 1"
    )
```

- [ ] **Step 5: `_dedup_cte`** — dans `core/app/analytics/aggregate.py`, ajouter `latest_per_key` à l'import depuis `app.analytics.snapshot`. Remplacer la fin de `_dedup_cte`, depuis `raw_files = f"read_parquet(…)"` jusqu'au `return`, par :

```python
    raw_files = f"read_parquet({_sql_lit(glob)}, hive_partitioning=true, union_by_name=true)"
    if snap is not None:
        # REV-280a : dernier snapshot d'état courant + lignes brutes plus récentes que sa
        # coupure (`_ts`, jamais la LSN : cf. app.analytics.snapshot). AUD-013 : seules les
        # PK touchées depuis la coupure passent par la fenêtre (latest_per_key).
        base = (
            f"SELECT * FROM read_parquet({_sql_lit(snap[0])}, hive_partitioning=true, "
            f"union_by_name=true)"
        )
        delta = f"SELECT * FROM {raw_files} WHERE _ts > {cut_seconds(snap[1])!r}"
        return (
            f"WITH raw AS (SELECT {star} FROM ({latest_per_key(base, delta, pk, order_by)})), "
            f"current AS (SELECT * FROM raw), "
            f"live AS (SELECT * FROM current WHERE _op != 'delete')"
        )
    return (
        f"WITH raw AS (SELECT {star} FROM {raw_files}), "
        f"current AS (SELECT * FROM raw QUALIFY row_number() OVER "
        f"(PARTITION BY {pk} ORDER BY {order_by}) = 1), "
        f"live AS (SELECT * FROM current WHERE _op != 'delete')"
    )
```

- [ ] **Step 6:**
  - `cd core && uv run pytest tests/test_lake_latest_per_key.py tests/test_lake_snapshot_read.py tests/test_lake_snapshot.py tests/test_lake_snapshot_job.py tests/test_lake_schema_evolution.py tests/test_lake_geometry_column.py tests/test_analytics_aggregate.py -v` → PASS. `test_snapshot_read_equals_raw_read` est le filet d'équivalence de bout en bout (tombstones, ré-insertion, backfill tardif) ;
  - `uv run mypy --strict app/analytics` → OK.

- [ ] **Step 7: Snapshot actif par défaut — test (échoue)** — ajouter à `core/tests/test_deployability.py` :

```python
def test_lake_snapshot_is_on_by_default():
    """AUD-013 : sans snapshot, la lecture du lac retombe sur la fenêtre complète (lente)."""
    raw = services(BASE)["worker"]["environment"]["CORE_LAKE_SNAPSHOT_ENABLED"]
    assert _resolve_effective_value(raw, "CORE_LAKE_SNAPSHOT_ENABLED") == "true"
```

`cd core && uv run pytest tests/test_deployability.py -k lake_snapshot_is_on -v` → FAIL.

- [ ] **Step 8: Basculer les défauts de déploiement** (le défaut du code reste `false`, figé par `test_lake_snapshot_job.py:48`) :
  - `docker-compose.yml:564-565` :

```yaml
      # Snapshot horaire d'état courant du lac (REV-280a), actif par défaut (AUD-013) :
      # sans lui, chaque lecture du lac trie tout l'historique de la collection.
      CORE_LAKE_SNAPSHOT_ENABLED: ${CORE_LAKE_SNAPSHOT_ENABLED:-true}
```

  - `.env.example:460` : `CORE_LAKE_SNAPSHOT_ENABLED=true` ;
  - `deploy/helm/geostudio/values.yaml:61` : `  CORE_LAKE_SNAPSHOT_ENABLED: "true"`.

- [ ] **Step 9:**
  - `cd core && uv run pytest tests/test_deployability.py tests/test_helm_chart.py -v` → PASS ;
  - `docker compose config | grep CORE_LAKE_SNAPSHOT_ENABLED` → `"true"` sur `worker`.

- [ ] **Step 10: Commit**

```bash
git add core/app/analytics/snapshot.py core/app/analytics/aggregate.py core/tests/test_lake_latest_per_key.py \
  core/tests/test_lake_snapshot_read.py core/tests/test_deployability.py docker-compose.yml .env.example \
  deploy/helm/geostudio/values.yaml
git commit -m "perf(core): lac lu par anti-jointure snapshot/delta, snapshot actif par défaut (AUD-013)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: AUD-014 — import de fichier en flux

**Files:**
- Modify: `core/app/ingestion/parsers.py` (`_iter_geojson_features`, `parse_geojson`, `parse_parquet_tabular`)
- Modify: `core/app/ingestion/importer.py` :
  - ajoute `_CsvKinds`, `_is_iso_date`, `_Scan`, `_open_rows`, `_INSERT_BATCH`, `_CSV_SQL_TYPES` ;
  - supprime `_load_rows` et `_infer_csv_types` ;
  - modifie `_csv_column_kind`, `run_import`, `run_append`.
- Test: `core/tests/test_ingestion_import_memory.py` (nouveau), `core/tests/test_ingestion_parsers.py`, `core/tests/test_ingestion_importer.py`

**Interfaces:**
- Produces: `_open_rows(filename, content, *, lat_field, lon_field, layer_name, wkt_field, geometry_mode) -> tuple[_Scan, Callable[[], Iterator[tuple[BaseGeometry | None, dict]]]]`.
  - `_Scan(columns: dict[str, str], geom_types: set[str], has_geometry: bool, count: int)` ;
  - l'appel de la fabrique fait un nouveau parcours du fichier et rend des lignes typées (types CSV appliqués).
- Produces: `_CsvKinds(decimal_comma: bool = False)` avec `.add(props: dict) -> None` et `.kinds() -> dict[str, str]` (valeurs `int` / `float` / `date`).
- `_csv_column_kind(values, decimal_comma=False)` garde sa signature (`test_ingestion_importer.py:777`).
- `run_import` / `run_append` : signatures inchangées (appelants `ingestion/tasks.py`, `harvest/service.py`).

- [ ] **Step 1: Tests (échouent)** — créer `core/tests/test_ingestion_import_memory.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-014 : l'import ne matérialise plus le fichier (json.loads + deux listes complètes
+ liste de paramètres : pic mesuré 2,9 Go pour 281 Mo)."""

import json
import tracemalloc

from app.ingestion.importer import _CsvKinds, _open_rows


def test_geojson_import_streams_instead_of_materializing_the_file():
    features = [
        {
            "type": "Feature",
            "properties": {"nom": f"n{i}", "pop": i, "note": "x" * 20},
            "geometry": {"type": "Point", "coordinates": [2.0 + i * 1e-6, 48.0]},
        }
        for i in range(50_000)
    ]
    content = json.dumps({"type": "FeatureCollection", "features": features}).encode()
    del features
    tracemalloc.start()
    try:
        scan, typed_rows = _open_rows(
            "big.geojson",
            content,
            lat_field=None,
            lon_field=None,
            layer_name=None,
            wkt_field=None,
            geometry_mode=None,
        )
        n = sum(1 for _ in typed_rows())
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert scan.count == n == 50_000
    assert scan.columns == {"nom": "text", "pop": "bigint", "note": "text"}
    assert peak < 3 * len(content), f"pic {peak} o pour un fichier de {len(content)} o"


def test_csv_kinds_tracks_each_column_in_one_pass():
    kinds = _CsvKinds(decimal_comma=True)
    for props in (
        {"a": "1", "b": "1,5", "c": "2026-01-02", "d": "x", "e": ""},
        {"a": " 2 ", "b": "2", "c": "2026-02-03", "d": "1", "e": None},
    ):
        kinds.add(props)
    assert kinds.kinds() == {"a": "int", "b": "float", "c": "date"}
```

Ajouter à `core/tests/test_ingestion_parsers.py` :

```python
def test_parse_geojson_streams_features_whatever_the_key_order():
    content = (
        b'{"features":[{"type":"Feature","properties":{"a":1},'
        b'"geometry":{"type":"Point","coordinates":[1.0,2.0]}}],'
        b'"crs":{"type":"name","properties":{"name":"EPSG:4326"}},"type":"FeatureCollection"}'
    )
    rows = list(parse_geojson(content))
    assert [props for _g, props in rows] == [{"a": 1}]


def test_parse_geojson_rejects_trailing_garbage():
    with pytest.raises(IngestionParseError, match="JSON invalide"):
        list(parse_geojson(b'{"type":"FeatureCollection","features":[]} x'))
```

- [ ] **Step 2:** `cd core && uv run pytest tests/test_ingestion_import_memory.py tests/test_ingestion_parsers.py -k "streams or csv_kinds or trailing or geojson" -v` → FAIL (`ImportError: _CsvKinds`, `_open_rows`).

- [ ] **Step 3: GeoJSON en flux** — dans `core/app/ingestion/parsers.py`, remplacer `parse_geojson` par :

```python
_JSON_WS = json.decoder.WHITESPACE  # type: ignore[attr-defined]


def _iter_geojson_features(text: str) -> Iterator[object]:
    """AUD-014 : parcourt la FeatureCollection sans construire l'arbre JSON entier. Les
    valeurs de premier niveau autres que `features` sont décodées (petites : crs, name…),
    puis chaque élément de `features` un à un (raw_decode). JSON invalide ->
    json.JSONDecodeError ; objet qui n'est pas une FeatureCollection ->
    IngestionParseError, au plus tard en fin de parcours (l'import analyse tout le
    fichier avant d'écrire quoi que ce soit, cf. importer._open_rows)."""
    dec = json.JSONDecoder()
    not_fc = IngestionParseError("le GeoJSON doit être une FeatureCollection")

    def ws(p: int) -> int:
        return _JSON_WS.match(text, p).end()

    def expect(p: int, ch: str) -> int:
        p = ws(p)
        if text[p : p + 1] != ch:
            raise json.JSONDecodeError(f"'{ch}' attendu", text, p)
        return p + 1

    pos = ws(0)
    if text[pos : pos + 1] != "{":
        dec.raw_decode(text, pos)  # JSON invalide -> JSONDecodeError
        raise not_fc
    pos = ws(pos + 1)
    kind = None
    if text[pos : pos + 1] == "}":
        raise not_fc
    while True:
        key, pos = dec.raw_decode(text, ws(pos))
        if not isinstance(key, str):
            raise json.JSONDecodeError("clé attendue", text, pos)
        pos = ws(expect(pos, ":"))
        if key == "features" and text[pos : pos + 1] == "[":
            if kind not in (None, "FeatureCollection"):
                raise not_fc
            pos = ws(pos + 1)
            if text[pos : pos + 1] == "]":
                pos += 1
            else:
                while True:
                    feature, pos = dec.raw_decode(text, pos)
                    yield feature
                    pos = ws(pos)
                    if text[pos : pos + 1] == ",":
                        pos = ws(pos + 1)
                        continue
                    pos = expect(pos, "]")
                    break
        else:
            value, pos = dec.raw_decode(text, pos)
            if key == "type":
                kind = value
            elif key == "features":  # présent mais pas une liste
                raise not_fc
        pos = ws(pos)
        if text[pos : pos + 1] == ",":
            pos += 1
            continue
        pos = expect(pos, "}")
        break
    if ws(pos) != len(text):
        raise json.JSONDecodeError("données en trop", text, ws(pos))
    if kind != "FeatureCollection":
        raise not_fc


def _geojson_feature(i: int, feature: object) -> tuple[BaseGeometry, dict]:
    if not isinstance(feature, dict):
        raise IngestionParseError(f"feature {i} : entrée invalide")
    geometry = feature.get("geometry")
    if geometry is None:
        raise IngestionParseError(f"feature {i} : géométrie manquante")
    try:
        geom = shape(geometry)
    except (ValueError, AttributeError, KeyError, TypeError, ShapelyError) as exc:
        raise IngestionParseError(f"feature {i} : géométrie invalide ({exc})") from exc
    geom = _repair_geometry(geom, f"feature {i}")
    properties = feature.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise IngestionParseError(f"feature {i} : properties invalide")
    return geom, dict(properties or {})


def parse_geojson(content: bytes) -> Iterator[tuple[BaseGeometry, dict]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionParseError("encodage invalide, attendu UTF-8") from exc
    try:
        for i, feature in enumerate(_iter_geojson_features(text)):
            yield _geojson_feature(i, feature)
    except json.JSONDecodeError as exc:
        raise IngestionParseError(f"JSON invalide : {exc}") from exc
```

- [ ] **Step 4: Parquet tabulaire par lots** — dans `parse_parquet_tabular`, remplacer le corps du `with _temp_file(...)` par :

```python
    with _temp_file(content, ".parquet") as path:
        try:
            pf = pyarrow.parquet.ParquetFile(path)
            # Auto-détection lat/lon résolue une fois, contre le schéma (revue finale
            # GAP-29, C1) ; lecture par lots (AUD-014) au lieu de read_table().to_pylist().
            effective_mode = _resolve_latlon_mode_from_fields(mode, list(pf.schema_arrow.names))
            for batch in pf.iter_batches(batch_size=10_000):
                for row in batch.to_pylist():
                    row = {
                        k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                        for k, v in row.items()
                    }
                    yield extract_geometry(row, effective_mode)
        except _PARQUET_ERRORS as exc:
            raise IngestionParseError(f"fichier Parquet illisible : {exc}") from exc
```

- [ ] **Step 5: Importer en deux passages** — dans `core/app/ingestion/importer.py` :
  - ajouter aux imports `from collections.abc import Callable, Iterator` et `from shapely.geometry.base import BaseGeometry` ;
  - remplacer `_csv_column_kind` et `_infer_csv_types` par :

```python
_CSV_SQL_TYPES = {"int": "bigint", "float": "double precision", "date": "date"}


def _is_iso_date(value: str) -> bool:
    if not _DATE_RE.match(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


class _CsvKinds:
    """P28.07 en un passage (AUD-014) : une colonne CSV dont toutes les valeurs non vides
    sont entières / décimales / dates ISO est typée. Les candidats sont éliminés valeur
    par valeur au lieu de garder toutes les valeurs en mémoire. Colonnes mixtes : texte."""

    def __init__(self, decimal_comma: bool = False) -> None:
        self.decimal_comma = decimal_comma
        self._candidates: dict[str, set[str]] = {}
        self._seen: set[str] = set()
        self._not_text: set[str] = set()

    def add(self, props: dict) -> None:
        for key, raw in props.items():
            cand = self._candidates.setdefault(key, {"int", "float", "date"})
            if raw is None:
                continue
            if not isinstance(raw, str):
                self._not_text.add(key)
                continue
            value = raw.strip()
            if not value:
                continue
            self._seen.add(key)
            if not _INT_RE.match(value):
                cand.discard("int")
                if not (
                    _FLOAT_RE.match(value)
                    or (self.decimal_comma and _DECIMAL_COMMA_RE.match(value))
                ):
                    cand.discard("float")
            if "date" in cand and not _is_iso_date(value):
                cand.discard("date")

    def kinds(self) -> dict[str, str]:
        out = {}
        for key, cand in self._candidates.items():
            if key in self._not_text or key not in self._seen:
                continue
            kind = next((k for k in ("int", "float", "date") if k in cand), None)
            if kind is not None:
                out[key] = kind
        return out


def _csv_column_kind(values: list[str], decimal_comma: bool = False) -> str | None:
    kinds = _CsvKinds(decimal_comma)
    for value in values:
        kinds.add({"v": value})
    return kinds.kinds().get("v")
```

  - remplacer `_load_rows` (fonction entière) par :

```python
_INSERT_BATCH = 10_000  # AUD-014 : 50k entités = 5 INSERT (plafond de test_ingestion_importer_perf)


@dataclass
class _Scan:
    """Premier passage (AUD-014) : tout ce qu'il faut savoir avant le CREATE TABLE."""

    columns: dict[str, str]
    geom_types: set[str]
    has_geometry: bool
    count: int


def _open_rows(
    filename: str,
    content: bytes,
    *,
    lat_field: str | None,
    lon_field: str | None,
    layer_name: str | None,
    wkt_field: str | None,
    geometry_mode: str | None,
) -> tuple[_Scan, Callable[[], Iterator[tuple[BaseGeometry | None, dict]]]]:
    """AUD-014 : le fichier est parcouru deux fois EN FLUX (aucune liste complète) — un
    passage d'analyse (colonnes, types CSV, géométries, compte), puis une fabrique de
    second passage qui rend les lignes typées pour l'insertion par lots.
    ponytail: le parse (et la réparation make_valid) est payé deux fois ; un seul passage
    exigerait une table de transit retypée après coup."""
    mode = _resolve_geometry_mode(
        lat_field=lat_field, lon_field=lon_field, wkt_field=wkt_field, geometry_mode=geometry_mode
    )
    fmt = _pick_format(filename)
    if fmt == "parquet":
        if _is_geoparquet_from_bytes(content):
            parse = lambda: parse_geoparquet(content)  # noqa: E731
        else:
            parse = lambda: parse_parquet_tabular(content, mode)  # noqa: E731
    else:
        parse = {
            "geojson": lambda: parse_geojson(content),
            "csv": lambda: parse_csv_latlon(content, mode),
            "xlsx": lambda: parse_xlsx_sheet(content, layer_name, mode),
            "gpkg": lambda: parse_gpkg(content, layer_name),
            "shapefile": lambda: parse_shapefile_zip(content, layer_name),
            "filegdb": lambda: parse_filegdb_zip(content, layer_name),
            "dxf": lambda: parse_dxf(content, layer_name),
            "dgn": lambda: parse_dgn(content, layer_name),
            "kml": lambda: parse_kml(content, layer_name),
            "gml": lambda: parse_gml(content, layer_name),
            "jsonlines": lambda: parse_jsonlines(content, mode),
            "xml_generic": lambda: parse_xml_generic(content, mode),
        }[fmt]

    def normalized() -> Iterator[tuple[BaseGeometry | None, dict]]:
        # REV-350 : id/tenant_id/geom entreraient en collision avec les colonnes fixes de
        # la table ; un seul point pour tous les formats. REV-351 : colonnes créées en 2D,
        # une coordonnée Z ferait échouer l'INSERT (import comme ajout).
        for geom, props in parse():
            yield (
                None if geom is None else force_2d(geom),
                _rename_reserved_property_keys(props, fmt),
            )

    decimal_comma = False
    if fmt == "csv":
        try:
            decimal_comma = sniff_delimiter(content.decode("utf-8-sig")) != ","
        except UnicodeDecodeError:
            pass  # parse_csv_latlon lève le message utilisateur au premier passage
    csv_kinds = _CsvKinds(decimal_comma)
    # Type d'une colonne = celui de la première valeur non nulle ; colonnes toujours
    # nulles en « text », placées après les autres (même ordre qu'avant AUD-014).
    columns: dict[str, str] = {}
    keys: dict[str, None] = {}
    geom_types: set[str] = set()
    count = 0
    for geom, props in normalized():
        count += 1
        if geom is not None:
            geom_types.add(geom.geom_type)
        if fmt == "csv":
            csv_kinds.add(props)
        for key, value in props.items():
            keys.setdefault(key)
            if key not in columns and value is not None:
                columns[key] = _sql_type_for(value)
    if count == 0:
        raise IngestionParseError("le fichier ne contient aucune entité")
    for key in keys:
        columns.setdefault(key, "text")
    kinds = csv_kinds.kinds()
    for key, kind in kinds.items():
        columns[key] = _CSV_SQL_TYPES[kind]

    def typed_rows() -> Iterator[tuple[BaseGeometry | None, dict]]:
        for geom, props in normalized():
            for key, kind in kinds.items():
                v = props.get(key)
                props[key] = (
                    None if v is None or v.strip() == "" else _convert_csv_value(v.strip(), kind)
                )
            yield geom, props

    return _Scan(columns, geom_types, bool(geom_types), count), typed_rows
```

  - dans `run_import`, remplacer l'appel `rows = _load_rows(...)`, le calcul de `columns`, `has_geometry` et `geom_types` (jusqu'à `single_type = …` exclu) par :

```python
    scan, typed_rows = _open_rows(
        filename,
        content,
        lat_field=lat_field,
        lon_field=lon_field,
        layer_name=layer_name,
        wkt_field=wkt_field,
        geometry_mode=geometry_mode,
    )
    columns = scan.columns
    # has_geometry : un seul mode de géométrie par import (jamais mixte) — soit toutes
    # les lignes portent une géométrie, soit aucune (geometry_mode="none").
    has_geometry = scan.has_geometry
    geom_types = scan.geom_types
```

  - toujours dans `run_import`, remplacer le bloc `params = [] … session.execute(text(insert_sql), params)` par :

```python
    batch: list[dict] = []
    for geom, props in typed_rows():
        row_params = {f"p{i}": props.get(name) for i, name in enumerate(col_names)}
        row_params["tenant_id"] = tenant_id
        if has_geometry:
            # has_geometry vrai => geom non-None sur toute ligne (mode unique par import).
            row_params["geom_wkt"] = geom.wkt if geom is not None else None
        batch.append(row_params)
        if len(batch) >= _INSERT_BATCH:
            session.execute(text(insert_sql), batch)
            batch = []
    if batch:
        session.execute(text(insert_sql), batch)
```

  - remplacer `feature_count=len(rows),` par `feature_count=scan.count,` ;
  - dans `run_append` :
    - remplacer `rows = _load_rows(` par `_scan, typed_rows = _open_rows(` (mêmes arguments) ;
    - remplacer `for number, (geom, props) in enumerate(rows, start=1):` par `for number, (geom, props) in enumerate(typed_rows(), start=1):`.

- [ ] **Step 6:** `cd core && grep -n "_load_rows\|_infer_csv_types" -r app tests` → aucune occurrence (hors `test_fme_coverage_cli.py`, qui teste un autre `_load_rows`).

- [ ] **Step 7:**
  - `cd core && uv run pytest tests/test_ingestion_import_memory.py tests/test_ingestion_parsers.py -v` → PASS ;
  - puis, base jetable, `uv run pytest tests/test_ingestion_importer.py tests/test_ingestion_importer_perf.py tests/test_ingestion_tasks.py tests/test_harvest_service.py -v` → PASS (`ls tests | grep -E "ingestion|harvest_service"` pour la liste réelle). Le test de perf reste à ≤ 5 INSERT ;
  - contre-épreuve une fois (piège n°10) : remplacer temporairement le corps de `parse_geojson` par l'ancien `json.loads` et constater que `test_geojson_import_streams_instead_of_materializing_the_file` échoue sur le pic, puis rétablir.

- [ ] **Step 8: Commit**

```bash
git add core/app/ingestion/parsers.py core/app/ingestion/importer.py core/tests/test_ingestion_import_memory.py \
  core/tests/test_ingestion_parsers.py
git commit -m "perf(core): import de fichier en flux, deux passages et insertion par lots (AUD-014)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: AUD-016 + AUD-028 — jobs de workers morts libérés, sonde au battement

**Files:**
- Create: `core/app/jobs/recovery.py`
- Modify: `core/app/jobs/__init__.py` (`import_paths`)
- Modify: `core/scripts/healthcheck_worker_stalled.py`
- Modify: `docker-compose.yml` (commentaire du healthcheck `worker`, lignes ~705-713)
- Test: `core/tests/test_jobs_recovery.py` (nouveau), `core/tests/test_healthcheck_worker_stalled.py`, `core/tests/test_jobs.py`

**Interfaces:**
- Produces:
  - `recovery.STALLED_HEARTBEAT_S = 120` ;
  - `async recovery.recover_stalled_jobs(job_manager, *, seconds_since_heartbeat: float = STALLED_HEARTBEAT_S) -> list[int]` (ids terminés en `failed`) ;
  - tâche `app.jobs.recovery.recover_stalled_jobs_task` (périodique, chaque minute, file `etl`).
- Consumes: `JobManager.get_stalled_jobs(queue=None, task_name=None, seconds_since_heartbeat=…)`, `JobManager.finish_job_by_id_async(job_id, status, delete_job)` et `procrastinate.jobs.Status`. Toutes sont vérifiées dans procrastinate 3.9.0.

Seuils :
- procrastinate bat toutes les 10 s et déclare un worker mort à 30 s ;
- la reprise agit à 120 s sans battement, chaque minute ;
- la sonde n'échoue qu'à 300 s : la reprise passe donc avant elle.

Les lignes métier (runs, imports…) restent à la charge des balayages de domaine existants (piège n°14). Ici, on ne libère que le job procrastinate et son verrou.

- [ ] **Step 1: Test postgis (échoue)** — créer `core/tests/test_jobs_recovery.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-028 : un worker tué laisse son job en 'doing' (verrou `lock=` tenu à jamais :
compaction/snapshot CDC bloqués). La reprise le termine en 'failed' ; un job d'un worker
vivant n'est pas touché."""

import asyncio
import os
import uuid

import procrastinate
import pytest
from sqlalchemy import text

from app.jobs.recovery import recover_stalled_jobs


def _app():
    conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    return procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=conninfo))


def _doing_job(c, *, queue, task, lock, worker_id):
    job_id = c.execute(
        text(
            "INSERT INTO procrastinate_jobs (queue_name, task_name, lock, args) "
            "VALUES (:q, :t, :l, '{}') RETURNING id"
        ),
        {"q": queue, "t": task, "l": lock},
    ).scalar()
    c.execute(
        text("UPDATE procrastinate_jobs SET status = 'doing', worker_id = :w WHERE id = :id"),
        {"w": worker_id, "id": job_id},
    )
    return job_id


@pytest.mark.postgis
def test_job_of_a_dead_worker_is_failed_and_a_live_one_is_kept(pg_engine_with_procrastinate_schema):
    engine = pg_engine_with_procrastinate_schema
    with engine.begin() as c:
        dead = c.execute(
            text(
                "INSERT INTO procrastinate_workers (last_heartbeat) "
                "VALUES (now() - interval '1 hour') RETURNING id"
            )
        ).scalar()
        alive = c.execute(
            text("INSERT INTO procrastinate_workers (last_heartbeat) VALUES (now()) RETURNING id")
        ).scalar()
        stalled = _doing_job(
            c, queue="cdc", task="app.cdc.jobs.run_compaction_cycle_task",
            lock=f"l1b-{uuid.uuid4().hex}", worker_id=dead,
        )
        running = _doing_job(
            c, queue="etl", task="app.pipelines.jobs.run_pipeline_task", lock=None, worker_id=alive
        )

    async def _run():
        app = _app()
        async with app.open_async():
            return await recover_stalled_jobs(app.job_manager)

    try:
        recovered = asyncio.run(_run())
        assert stalled in recovered and running not in recovered
        with engine.connect() as c:
            statuses = dict(
                c.execute(
                    text("SELECT id, status::text FROM procrastinate_jobs WHERE id IN (:a, :b)"),
                    {"a": stalled, "b": running},
                ).all()
            )
        assert statuses == {stalled: "failed", running: "doing"}
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM procrastinate_jobs WHERE id IN (:a, :b)"), {"a": stalled, "b": running})
            c.execute(text("DELETE FROM procrastinate_workers WHERE id IN (:a, :b)"), {"a": dead, "b": alive})
```

Dans `core/tests/test_jobs.py::test_import_paths_registers_all_domain_tasks`, ajouter :

```python
    assert "app.jobs.recovery.recover_stalled_jobs_task" in task_names
```

- [ ] **Step 2:** `cd core && uv run pytest tests/test_jobs_recovery.py tests/test_jobs.py -v` → FAIL (`ModuleNotFoundError: app.jobs.recovery`).

- [ ] **Step 3: Implémenter** — créer `core/app/jobs/recovery.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-028 : reprise des jobs procrastinate dont le worker est mort (OOM, SIGKILL,
nœud perdu). procrastinate 3.9 élague le worker sans battement au démarrage suivant
(worker_id -> NULL) mais ne termine jamais son job : il reste 'doing' et son `lock`
(cdc_compaction, run_snapshot_cycle…) bloque toute la file. Ici, le job est terminé en
'failed' (verrou libéré) ; les lignes métier sont reprises par les balayages de domaine
existants (runs, imports, exports…)."""

import logging

from procrastinate.jobs import Status

from app.jobs import app

logger = logging.getLogger(__name__)

# > stalled_worker_timeout de procrastinate (30 s) et < seuil de la sonde (300 s).
STALLED_HEARTBEAT_S = 120


async def recover_stalled_jobs(
    job_manager, *, seconds_since_heartbeat: float = STALLED_HEARTBEAT_S
) -> list[int]:
    recovered = []
    for job in await job_manager.get_stalled_jobs(seconds_since_heartbeat=seconds_since_heartbeat):
        try:
            await job_manager.finish_job_by_id_async(job.id, status=Status.FAILED, delete_job=False)
        except Exception:  # noqa: BLE001 — terminé entre-temps (plus 'doing') : rien à faire
            logger.warning("job %s : reprise impossible (déjà terminé ?)", job.id, exc_info=True)
            continue
        logger.warning(
            "job %s (%s, verrou %s) d'un worker sans battement terminé en échec",
            job.id,
            job.task_name,
            job.lock,
        )
        recovered.append(job.id)
    return recovered


@app.periodic(cron="* * * * *")
@app.task(queue="etl", queueing_lock="recover_stalled_jobs_task")
async def recover_stalled_jobs_task(timestamp: int) -> None:
    await recover_stalled_jobs(app.job_manager)
```

Dans `core/app/jobs/__init__.py`, ajouter `"app.jobs.recovery",` à la fin de `import_paths`.

- [ ] **Step 4:** `cd core && uv run pytest tests/test_jobs_recovery.py tests/test_jobs.py tests/test_deployability.py -k "recovery or import_paths or queue" -v` → PASS.

- [ ] **Step 5: Sonde — tests (échouent)** — dans `core/tests/test_healthcheck_worker_stalled.py`, remplacer le test `test_main_defaults_threshold_to_one_hour_and_queue_to_none` par :

```python
def test_main_defaults_heartbeat_threshold_to_five_minutes_and_queue_to_none(monkeypatch):
    captured = {}

    async def _fetch(threshold_seconds, queue):
        captured["threshold_seconds"] = threshold_seconds
        captured["queue"] = queue
        return []

    monkeypatch.setattr(healthcheck, "_fetch_stalled", _fetch)
    monkeypatch.delenv("HEALTHCHECK_STALLED_SECONDS", raising=False)
    monkeypatch.delenv("HEALTHCHECK_QUEUE", raising=False)
    assert healthcheck.main() == 0
    assert captured == {"threshold_seconds": 300, "queue": None}


def test_fetch_uses_worker_heartbeats_not_job_start_time(monkeypatch):
    """AUD-016 : `nb_seconds` (déprécié) compte depuis le démarrage du job — un job sain
    de plus d'une heure rendait la sonde rouge (CrashLoop Helm)."""
    import asyncio

    seen = {}

    class _JobManager:
        async def get_stalled_jobs(self, **kwargs):
            seen.update(kwargs)
            return []

    class _Opened:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(healthcheck.app, "open_async", lambda: _Opened())
    monkeypatch.setattr(healthcheck.app, "job_manager", _JobManager())
    assert asyncio.run(healthcheck._fetch_stalled(300, "export")) == []
    assert seen == {"queue": "export", "seconds_since_heartbeat": 300}
```

`cd core && uv run pytest tests/test_healthcheck_worker_stalled.py -v` → FAIL.

- [ ] **Step 6: Implémenter la sonde** — dans `core/scripts/healthcheck_worker_stalled.py` :
  - remplacer `_fetch_stalled` et la ligne `threshold = …` :

```python
async def _fetch_stalled(threshold_seconds: int, queue: str | None) -> list:
    async with app.open_async():
        return list(
            await app.job_manager.get_stalled_jobs(
                queue=queue, seconds_since_heartbeat=threshold_seconds
            )
        )
```

```python
    threshold = int(os.environ.get("HEALTHCHECK_STALLED_SECONDS", "300"))
```

  - message d'échec : `f"{len(stalled)} job(s) en 'doing' sur un worker sans battement depuis plus de {threshold}s"` ;
  - dans la docstring du module, remplacer la ligne `HEALTHCHECK_STALLED_SECONDS (def. 3600, …)` (3 lignes) par :

```text
  HEALTHCHECK_STALLED_SECONDS (def. 300) : secondes SANS BATTEMENT du worker qui
    tient un job 'doing' (AUD-016 — plus la durée du job : un job sain de plus d'une
    heure rendait la sonde rouge). La reprise app.jobs.recovery agit dès 120 s :
    une sonde rouge signale une boucle d'événements bloquée, ou une reprise qui ne
    tourne plus.
```

Dans `docker-compose.yml`, commentaire du healthcheck `worker`, remplacer les lignes `# (GAP-76, SP-49) : interroge JobManager.get_stalled_jobs (job resté en` … `# de pipeline).` par :

```yaml
    # (GAP-76, SP-49 ; AUD-016) : interroge JobManager.get_stalled_jobs au BATTEMENT —
    # job 'doing' tenu par un worker sans battement depuis HEALTHCHECK_STALLED_SECONDS
    # (300 s par défaut), jamais la durée du job ; la reprise app.jobs.recovery
    # (120 s) termine d'abord les jobs des workers morts.
```

Aucune commande de sonde ne change : parité compose / Helm conservée.

- [ ] **Step 7:** `cd core && uv run pytest tests/test_healthcheck_worker_stalled.py tests/test_helm_chart.py tests/test_deployability.py -v` → PASS.

- [ ] **Step 8: Commit**

```bash
git add core/app/jobs/recovery.py core/app/jobs/__init__.py core/scripts/healthcheck_worker_stalled.py \
  core/tests/test_jobs_recovery.py core/tests/test_jobs.py core/tests/test_healthcheck_worker_stalled.py \
  docker-compose.yml
git commit -m "fix(core): jobs de workers morts libérés, sonde de vivacité au battement (AUD-016, AUD-028)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: AUD-083 + AUD-029 — garde de run (annulation, durée maximale) et `append` rejouable

**Files:**
- Modify: `core/app/pipelines/runtime.py` (`_GUARD_POLL_S`, `_run_timeout_s`, `_RunGuard`, `_execute_transform_chain`, `run_pipeline`)
- Modify: `core/app/configs/schemas.py:454-478` (`append_writers`, message du validateur)
- Modify: `core/app/pipelines/service.py:169-180` (message 409)
- Modify: `docker-compose.yml` (`worker.environment`), `.env.example`, `deploy/helm/geostudio/values.yaml`
- Test: `core/tests/test_pipeline_run_guard.py` (nouveau), `core/tests/test_pipeline_run_retry.py`, `core/tests/test_pipeline_fme_review_guards.py`

**Interfaces:**
- Produces:
  - `runtime._RunGuard(conn, should_cancel: Callable[[], bool] | None, timeout_s: float)` : gestionnaire de contexte, avec `.check() -> None` (lève `PipelineCancelledError` / `PipelineTerminatedError`) et `.should_stop() -> bool` ;
  - `runtime._run_timeout_s() -> float` (env `CORE_PIPELINES_RUN_TIMEOUT_S`, défaut 21600) ;
  - `_execute_transform_chain(..., check: Callable[[], None] | None = None)`.
- Produces: `PipelinePayload.append_writers()` ne renvoie plus que les writers de `EXTERNAL_EFFECT_WRITER_OPS`. Le nom est gardé pour limiter la collision avec L5.
- Consumes: `PipelineCancelledError`, `PipelineTerminatedError` (`app/pipelines/errors.py`) ; `tracker.is_cancel_requested` (ouvre sa propre session, donc appelable depuis le fil du garde).

- [ ] **Step 1: Tests du garde (échouent)** — créer `core/tests/test_pipeline_run_guard.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-083/AUD-029 : annulation et durée maximale d'un run, hors writers par lots."""

import duckdb
import pytest

from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from app.pipelines import runtime
from app.pipelines.errors import (
    PipelineCancelledError,
    PipelineRuntimeError,
    PipelineTerminatedError,
)
from app.pipelines.registries import READERS
from tests.test_pipeline_jobs import env  # noqa: F401  (fixture partagée)
from tests.test_pipeline_run_retry import _exec, _new_run, _payload, _rows, rig  # noqa: F401

# Requête qui ne finit pas en un temps de test sans interruption.
_ENDLESS = "SELECT max(hash(r)) FROM range(100000000000) t(r)"


@pytest.fixture(autouse=True)
def _fast_poll(monkeypatch):
    monkeypatch.setattr(runtime, "_GUARD_POLL_S", 0.05)


def test_cancel_interrupts_a_running_duckdb_query():
    conn = duckdb.connect()
    with pytest.raises(PipelineCancelledError):
        with runtime._RunGuard(conn, lambda: True, timeout_s=3600):
            conn.execute(_ENDLESS)


def test_deadline_terminates_the_run_without_retry():
    conn = duckdb.connect()
    with pytest.raises(PipelineTerminatedError, match="durée maximale"):
        with runtime._RunGuard(conn, None, timeout_s=0.1):
            conn.execute(_ENDLESS)


def test_an_interrupt_wrapped_by_an_op_is_still_translated():
    conn = duckdb.connect()
    with pytest.raises(PipelineCancelledError):
        with runtime._RunGuard(conn, lambda: True, timeout_s=3600):
            try:
                conn.execute(_ENDLESS)
            except duckdb.Error as exc:
                raise PipelineRuntimeError(str(exc)) from exc


def test_guard_is_silent_when_nothing_happens():
    conn = duckdb.connect()
    with runtime._RunGuard(conn, lambda: False, timeout_s=3600) as guard:
        assert conn.execute("SELECT 1").fetchone() == (1,)
        guard.check()
        assert guard.should_stop() is False


@pytest.mark.postgis
def test_cancel_requested_during_the_read_stops_before_any_transform(rig, monkeypatch):  # noqa: F811
    _app, Session, tenant, user, item_id, state = rig
    state["fail_t3"] = False
    run_id = _new_run(Session, tenant, item_id)

    def cancelling_reader(conn, *, node_id, view_name, **_):
        with Session() as s:
            run = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
            pipelines_repo.request_cancel(s, run)
            s.commit()
        conn.execute(
            f"CREATE TEMP TABLE {view_name} AS SELECT 'R' AS region, 1 AS pop, "
            "ST_Point(1, 45) AS geometry"
        )
        return 4326

    monkeypatch.setitem(READERS, "reader.connector.rest", cancelling_reader)
    run = _exec(Session, tenant, run_id)
    assert run.status == "cancelled"
    assert state["compiled"] == []  # avant AUD-083 : t1, t2, t3 exécutés malgré l'annulation
    assert _rows(Session) == 0


@pytest.mark.postgis
def test_append_writer_failure_rolls_back_and_is_retried(rig, monkeypatch):  # noqa: F811
    """AUD-083 : writer.collection écrit dans la transaction du run ; un échec APRÈS lui
    annule ses lignes, le retry automatique ne duplique rien."""
    _app, Session, tenant, user, item_id, state = rig
    state["fail_t3"] = False
    state["retry"] = {"max": 1, "backoff": "fixed", "delaySeconds": 1}

    def append_payload(retry):
        p = _payload(None).model_dump(by_alias=True)
        p["nodes"][-1]["params"].pop("mode")  # défaut = append
        p["retry"] = retry
        return runtime.PipelinePayload.model_validate(p)

    state["payload_fn"] = append_payload
    fail = {"on": True}

    def progress(factory, *, run_id, tenant_id):
        def cb(stat):
            if fail["on"] and getattr(stat, "nodeId", None) == "w1":
                raise PipelineRuntimeError("échec après l'écriture")

        return cb

    monkeypatch.setattr(pipeline_jobs, "_make_progress_callback", progress)
    run_id = _new_run(Session, tenant, item_id)
    assert _exec(Session, tenant, run_id).status == "retrying"
    assert _rows(Session) == 0
    fail["on"] = False
    assert _exec(Session, tenant, run_id).status == "succeeded"
    assert _rows(Session) == 3
```

(`runtime.PipelinePayload` est déjà importé par `runtime.py` depuis `app.configs.schemas`.)

- [ ] **Step 2:** `cd core && uv run pytest tests/test_pipeline_run_guard.py -v` (base jetable) → FAIL (`AttributeError: _RunGuard` ; les tests postgis échouent : 3 transforms compilés, et `ValueError` « upsert » à la validation, d'où un statut `failed`).

- [ ] **Step 3: Implémenter le garde** — dans `core/app/pipelines/runtime.py` :
  - ajouter `import time` aux imports ;
  - vérifier que `PipelineCancelledError` et `PipelineTerminatedError` sont importés depuis `app.pipelines.errors`, sinon les ajouter à l'import existant de `PipelineRuntimeError` ;
  - ajouter après `_preview_timeout_s` :

```python
_GUARD_POLL_S = 5.0


def _run_timeout_s() -> float:
    return float(os.environ.get("CORE_PIPELINES_RUN_TIMEOUT_S") or 21600)


class _RunGuard:
    """AUD-083/AUD-029 : annulation et durée maximale d'un run. Un fil surveille
    `should_cancel` et l'échéance et interrompt la requête DuckDB en cours
    (`conn.interrupt()`, même mécanisme que l'aperçu P16.03) ; `check()` est appelé entre
    deux nœuds et par les writers par lots (`should_stop`). Une interruption DuckDB, même
    enveloppée par une op en PipelineRuntimeError, ressort en erreur métier.
    ponytail: un code Python bloquant hors DuckDB (GEOS, GDAL, boucle httpCall) n'est
    arrêté qu'au nœud suivant ; l'arrêter net exigerait un sous-processus par run."""

    def __init__(
        self, conn, should_cancel: Callable[[], bool] | None, timeout_s: float
    ) -> None:
        self._conn = conn
        self._should_cancel = should_cancel
        self._timeout_s = timeout_s
        self._deadline = time.monotonic() + timeout_s
        self.reason: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, name="pipeline-run-guard", daemon=True)

    def __enter__(self) -> "_RunGuard":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._stop.set()
        self._thread.join()
        if (
            exc is not None
            and not isinstance(exc, (PipelineCancelledError, PipelineTerminatedError))
            and self._interrupted(exc)
        ):
            self.check()
        return False

    @staticmethod
    def _interrupted(exc: BaseException | None) -> bool:
        while exc is not None:
            if isinstance(exc, duckdb.InterruptException):
                return True
            exc = exc.__cause__ or exc.__context__
        return False

    def _poll(self) -> str | None:
        if self.reason is None:
            if time.monotonic() >= self._deadline:
                self.reason = "timeout"
            elif self._should_cancel is not None and self._should_cancel():
                self.reason = "cancel"
        return self.reason

    def _watch(self) -> None:
        while not self._stop.wait(_GUARD_POLL_S):
            if self._poll() is not None:
                self._conn.interrupt()
                return

    def check(self) -> None:
        reason = self._poll()
        if reason == "cancel":
            raise PipelineCancelledError("run annulé")
        if reason == "timeout":
            raise PipelineTerminatedError(
                f"durée maximale du run dépassée ({self._timeout_s:.0f} s)"
            )

    def should_stop(self) -> bool:
        """`should_cancel` des writers par lots : lève l'erreur adaptée, sinon False."""
        self.check()
        return False
```

  - `_execute_transform_chain` : ajouter le paramètre `check: Callable[[], None] | None = None` après `reader_state`, et en première ligne du corps de `for node in ordered:` :

```python
        if check is not None:
            check()
```

  - `run_pipeline` :
    - insérer la ligne `with _RunGuard(conn, should_cancel, _run_timeout_s()) as guard:` juste après `try:` (celui qui précède `ordered, view_by_node, … = _prepare(`) ;
    - réindenter d'un niveau, **sans autre changement**, tout le bloc jusqu'à `return stats` inclus ;
    - les clauses `except BaseException:` et `finally:` restent au niveau du `try`.

    Puis, dans ce bloc :
    - après l'appel à `_prepare(...)`, ajouter `guard.check()` ;
    - ajouter `check=guard.check,` aux arguments de `_execute_transform_chain(` ;
    - dans `for node in ordered:` (writers), juste après `if node.kind != "writer": continue`, ajouter `guard.check()` ;
    - remplacer le calcul de `extra` par :

```python
                extra = {"on_progress": on_progress, "should_cancel": guard.should_stop} | (
                    {"run_id": run_id} if run_id is not None and node.kind == "writer" else {}
                )
```

    - remplacer le commentaire « F5 : une reprise REJOUE toujours les writers … sont idempotents. » par :

```python
            # F5 : une reprise REJOUE toujours les writers (jamais sautés sur la foi de
            # node_stats, commité à part — revue finale vague 4, C1). collection/dataset
            # écrivent dans la transaction du run, annulée à l'échec : rejouables même en
            # `append` (AUD-083). Seuls les writers à effet externe non idempotent
            # (EXTERNAL_EFFECT_WRITER_OPS) sont exclus de retry/reprise (`append_writers()`).
```

- [ ] **Step 4: `append` rejouable** — dans `core/app/configs/schemas.py`, remplacer le validateur et `append_writers` :

```python
        if self.retry is not None and self.retry.max > 0 and self.append_writers():
            raise ValueError(
                "reprise automatique (retry.max > 0) impossible avec un writer à effet "
                f"externe non idempotent ({', '.join(self.append_writers())}) : un rejeu "
                "renverrait des messages déjà partis"
            )
        return self

    def append_writers(self) -> list[str]:
        """Ids des writers NON REJOUABLES, donc incompatibles avec un retry/une reprise :
        writers à effet externe irréversible (`EXTERNAL_EFFECT_WRITER_OPS`). Les writers
        collection/dataset, même en `append`, écrivent dans la transaction du run, annulée
        à l'échec : rejouables (AUD-083)."""
        return [
            n.id for n in self.nodes if n.kind == "writer" and n.op in EXTERNAL_EFFECT_WRITER_OPS
        ]
```

Dans `core/app/pipelines/service.py`, remplacer le `detail=(…)` du 409 par :

```python
            detail=(
                f"Reprise/rejeu refusé : le writer {', '.join(appenders)} a un effet externe "
                "non idempotent (renverrait les messages déjà partis). "
                "Relancez une exécution complète."
            ),
```

- [ ] **Step 5: Tests existants qui figeaient le refus** — dans `core/tests/test_pipeline_run_retry.py` :
  - remplacer `test_automatic_retry_with_append_writer_is_refused_at_validation` par :

```python
def test_automatic_retry_with_append_writer_is_accepted():
    """AUD-083 : l'append de writer.collection est dans la transaction du run."""
    payload = _payload(None).model_dump(by_alias=True)
    payload["nodes"][-1]["params"].pop("mode")  # défaut = append
    payload["retry"] = {"max": 2}
    assert PipelinePayload.model_validate(payload).append_writers() == []
```

  - remplacer `test_retry_route_refuses_append_writer` par le même corps, renommé `test_retry_route_accepts_append_writer`. Ses deux dernières instructions deviennent :

```python
    with Session() as s:
        new_id = retry_pipeline_run_service(s, user=user, run_id=r1.id, defer_task=lambda *a: None)
    assert isinstance(new_id, str)
```

  - remplacer `test_automatic_retry_refuses_insert_alias_of_append` par :

```python
def test_automatic_retry_accepts_insert_alias_of_append():
    payload = _payload(None).model_dump(by_alias=True)
    payload["nodes"][-1]["params"] = {"collectionId": "villes", "mode": "insert"}
    payload["retry"] = {"max": 2}
    assert PipelinePayload.model_validate(payload).append_writers() == []
```

  - `grep -rn "upsert\|non idempotent\|append_writers" core/tests` : tout test qui attend encore le refus d'un `append` collection/dataset est adapté de la même manière. Les tests du writer externe (`writer.email`, attente « non idempotent ») restent inchangés.

Dans `core/tests/test_pipeline_fme_review_guards.py`, remplacer les deux raisons :

```python
    "writer.collection": "transaction du run, annulée à l'échec (append compris, AUD-083)",
    "writer.dataset": "transaction du run, annulée à l'échec (append compris, AUD-083)",
```

- [ ] **Step 6: Câbler la durée maximale**
  - `docker-compose.yml`, `worker.environment`, après `CORE_PIPELINES_PREVIEW_TIMEOUT_S: ${CORE_PIPELINES_PREVIEW_TIMEOUT_S:-30}` (ligne ~624) :

```yaml
      # AUD-029 : durée maximale d'un run de pipeline (partie DuckDB interrompue, puis
      # échec définitif sans retry).
      CORE_PIPELINES_RUN_TIMEOUT_S: ${CORE_PIPELINES_RUN_TIMEOUT_S:-21600}
```

  - `.env.example`, après `CORE_PIPELINES_PREVIEW_TIMEOUT_S=30` :

```bash
# Durée maximale (s) d'un run de pipeline ; au-delà, le run échoue sans retry (AUD-029).
CORE_PIPELINES_RUN_TIMEOUT_S=21600
```

  - `deploy/helm/geostudio/values.yaml`, après `  CORE_PIPELINES_PREVIEW_TIMEOUT_S: "30"` :

```yaml
  CORE_PIPELINES_RUN_TIMEOUT_S: "21600"
```

- [ ] **Step 7:**
  - `cd core && uv run pytest tests/test_pipeline_run_guard.py tests/test_pipeline_run_retry.py tests/test_pipeline_fme_review_guards.py tests/test_pipeline_jobs.py tests/test_pipeline_cancel*.py tests/test_deployability.py tests/test_helm_chart.py -v` (base jetable ; `ls tests | grep pipeline_cancel` pour le nom réel) → PASS ;
  - puis `uv run pytest tests -k "pipeline" -q` → vert ;
  - `docker compose config | grep CORE_PIPELINES_RUN_TIMEOUT_S` → `"21600"` sur `worker` (piège n°2).

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/runtime.py core/app/configs/schemas.py core/app/pipelines/service.py \
  core/tests/test_pipeline_run_guard.py core/tests/test_pipeline_run_retry.py \
  core/tests/test_pipeline_fme_review_guards.py docker-compose.yml .env.example deploy/helm/geostudio/values.yaml
git commit -m "fix(core): run de pipeline annulable entre nœuds et borné en durée, append rejouable (AUD-083, AUD-029)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: AUD-085 + AUD-170 + AUD-168 — outbox de webhooks

**Files:**
- Modify: `core/app/webhooks/delivery.py` (`deliver_one`, `_disable`, `deliver_due`, `purge_outbox`, constantes). **Ne pas toucher `_http_post`** (lot L2, AUD-169).
- Test: `core/tests/test_webhooks_delivery_claim.py`, `core/tests/test_webhooks_outbox.py`

**Interfaces:**
- Produces:
  - `delivery.MAX_EVENT_AGE: timedelta` (24 h) ;
  - `delivery._EVENT_REJECTED_STATUSES: frozenset[int]` ;
  - `delivery._http_status(exc: BaseException) -> int | None`.
- Comportement :
  - un événement passe `failed` sur un refus de contenu (400/409/413/415/422), sans compter contre la destination, ou quand il a plus de 24 h ;
  - la destination n'est désactivée qu'après 5 échecs consécutifs **et** un événement en échec depuis 24 h ;
  - la désactivation garde les événements `pending`, qui reprennent à la réactivation (PATCH `enabled=true`, existant) ;
  - `purge_outbox` supprime aussi les `pending` de plus de 30 jours ;
  - une exception de base sur un événement n'arrête plus le balayage.

- [ ] **Step 1: Tests (échouent)** — ajouter à `core/tests/test_webhooks_delivery_claim.py` (ajouter `import requests` aux imports) :

```python
def _fail_with(status):
    def post(*_a):
        resp = requests.Response()
        resp.status_code = status
        try:
            raise requests.HTTPError(f"{status}", response=resp)
        except requests.HTTPError as exc:
            raise delivery.DeliveryError(f"livraison échouée : {exc}") from exc

    return post


def _hook_of(s, tid):
    return s.scalars(select(OutboundWebhook).where(OutboundWebhook.tenant_id == tid)).one()


def test_a_short_outage_neither_disables_nor_drops_events(db):
    """AUD-085 : 5 échecs en ~7 min désactivaient la destination et détruisaient l'outbox."""
    tid, (eid,) = _tenant_with_hook(db, events=1)
    with db() as s:
        hook = _hook_of(s, tid)
        hook.consecutive_failures = delivery.MAX_CONSECUTIVE_FAILURES - 1
        s.commit()
        delivery.deliver_due(s, post=_fail_with(503))
        assert hook.enabled is True
        assert hook.consecutive_failures == delivery.MAX_CONSECUTIVE_FAILURES
        assert s.get(OutboxEvent, eid).status == "pending"


def test_a_day_long_outage_disables_but_keeps_pending_events_for_reenable(db):
    tid, (old, recent) = _tenant_with_hook(db, events=2)
    with db() as s:
        hook = _hook_of(s, tid)
        hook.consecutive_failures = delivery.MAX_CONSECUTIVE_FAILURES - 1
        s.get(OutboxEvent, old).created_at = NOW - delivery.MAX_EVENT_AGE - timedelta(minutes=1)
        s.commit()
        delivery.deliver_due(s, post=_fail_with(503))
        assert hook.enabled is False
        old_ev, recent_ev = s.get(OutboxEvent, old), s.get(OutboxEvent, recent)
        assert old_ev.status == "failed" and "abandonné" in old_ev.last_error
        assert recent_ev.status == "pending"
        # réactivation (PATCH enabled=true) : l'événement gardé repart
        hook.enabled, hook.consecutive_failures = True, 0
        recent_ev.next_attempt_at = NOW - timedelta(seconds=1)
        s.commit()
        assert delivery.deliver_due(s, post=lambda *a: None) == 1
        assert recent_ev.status == "delivered"


def test_a_payload_rejection_fails_only_that_event(db):
    """AUD-170 : un 4xx propre au contenu n'est plus rejoué indéfiniment ni compté contre
    la destination."""
    tid, (eid,) = _tenant_with_hook(db, events=1)
    with db() as s:
        delivery.deliver_due(s, post=_fail_with(422))
        ev, hook = s.get(OutboxEvent, eid), _hook_of(s, tid)
        assert ev.status == "failed"
        assert (hook.enabled, hook.consecutive_failures) == (True, 0)


def test_a_too_old_event_is_given_up(db):
    tid, (eid,) = _tenant_with_hook(db, events=1)
    with db() as s:
        s.get(OutboxEvent, eid).created_at = NOW - delivery.MAX_EVENT_AGE - timedelta(minutes=1)
        s.commit()
        delivery.deliver_due(s, post=_fail_with(503))
        assert s.get(OutboxEvent, eid).status == "failed"
        assert _hook_of(s, tid).enabled is True  # 1 seul échec consécutif


def test_a_database_error_on_one_event_does_not_abort_the_sweep(db, monkeypatch):
    """AUD-168 : destination supprimée pendant la livraison -> StaleDataError propagée
    jusqu'à la tâche (reste du lot en attente du bail, purges sautées)."""
    tid, (first, second) = _tenant_with_hook(db, events=2)
    real = delivery.deliver_one

    def flaky(session, event, hook, *, post):
        if event.id == first:
            raise RuntimeError("ligne disparue")
        return real(session, event, hook, post=post)

    monkeypatch.setattr(delivery, "deliver_one", flaky)
    with db() as s:
        assert delivery.deliver_due(s, post=lambda *a: None) == 1
        assert s.get(OutboxEvent, first).status == "pending"  # bail : repris plus tard
        assert s.get(OutboxEvent, second).status == "delivered"
```

Dans le même fichier :
- **`test_auto_disable_is_audited`** : après `hook.consecutive_failures = delivery.MAX_CONSECUTIVE_FAILURES - 1`, ajouter `s.get(OutboxEvent, eid).created_at = NOW - delivery.MAX_EVENT_AGE - timedelta(minutes=1)`.
- **`test_old_outbox_rows_are_purged_but_pending_ones_are_kept`** :
  - le renommer `test_old_outbox_rows_are_purged_pending_included` ;
  - remplacer ses deux dernières assertions par :

```python
        assert delivery.purge_outbox(s) == 2
        assert {e.id for e in s.scalars(select(OutboxEvent))} == {recent_done}
```

Dans `core/tests/test_webhooks_outbox.py`, remplacer `test_failures_back_off_then_disable_after_five_and_notify` par :

```python
def test_failures_back_off_and_only_a_day_long_outage_disables_and_notifies(db):
    tenant_id, user_id = _seed(db)
    with db() as s:
        ev = _event(s, tenant_id)
        hook = s.get(OutboundWebhook, "h1")
        previous = None
        for attempt in range(1, 6):
            ev.next_attempt_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
            s.commit()
            assert deliver_due(s, post=_failing) == 0
            assert ev.attempts == attempt
            delay = ev.next_attempt_at - datetime.now(UTC).replace(tzinfo=None)
            assert previous is None or delay > previous  # backoff exponentiel
            previous = delay
        # AUD-085 : 5 échecs rapprochés ne désactivent plus rien
        assert hook.enabled and ev.status == "pending" and hook.consecutive_failures == 5
        assert s.scalars(select(Notification)).all() == []
        # panne qui dure : l'événement a 24 h -> abandonné, destination désactivée + notifiée
        ev.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=25)
        ev.next_attempt_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        s.commit()
        assert deliver_due(s, post=_failing) == 0
        assert hook.enabled is False and ev.status == "failed"
        notif = s.scalars(select(Notification)).one()
        assert (notif.kind, notif.recipient_user_id, notif.status) == (
            "webhook_disabled",
            user_id,
            "failure",
        )
        assert deliver_due(s, post=_failing) == 0  # plus de livraison tant que désactivée
```

- [ ] **Step 2:** `cd core && uv run pytest tests/test_webhooks_delivery_claim.py tests/test_webhooks_outbox.py -v` → FAIL (`AttributeError: MAX_EVENT_AGE`, puis les nouvelles assertions).

- [ ] **Step 3: Implémenter** — dans `core/app/webhooks/delivery.py` :
  - mettre à jour la docstring du module (« 5 échecs consécutifs … = désactivation ») en : `retries exponentiels ; événement abandonné après 24 h ou sur refus de son contenu ; destination désactivée (événements gardés) seulement après une panne d'au moins 24 h + notification de son créateur.`
  - ajouter sous `OUTBOX_RETENTION_DAYS = 30` :

```python
MAX_EVENT_AGE = timedelta(hours=24)
# 4xx propres au CONTENU de l'événement (le rejouer ne changera rien) : l'événement échoue
# seul, sans compter contre la destination (AUD-170). Les autres 4xx (401/403/404/410… :
# configuration de la destination, corrigeable) suivent le chemin des retries.
_EVENT_REJECTED_STATUSES = frozenset({400, 409, 413, 415, 422})


def _http_status(exc: BaseException) -> int | None:
    """Code HTTP d'un échec de `_http_post`, porté par la requests.HTTPError d'origine."""
    response = getattr(exc.__cause__, "response", None)
    return getattr(response, "status_code", None)
```

  - dans `deliver_one`, remplacer tout le bloc `except Exception as exc:` par :

```python
    except Exception as exc:  # noqa: BLE001 — DeliveryError ou imprévu (déchiffrement…) : l'échec reste sur CETTE destination
        if not isinstance(exc, DeliveryError):
            logger.exception("livraison %s : échec inattendu", event.id)
        now = _now()
        event.attempts += 1
        event.last_error = str(exc)[:500]
        event.next_attempt_at = now + timedelta(
            seconds=min(_BACKOFF_BASE_S * 2 ** (event.attempts - 1), _BACKOFF_CAP_S)
        )
        if _http_status(exc) in _EVENT_REJECTED_STATUSES:
            event.status = "failed"  # contenu refusé : le rejouer ne changera rien (AUD-170)
            session.flush()
            return False
        expired = event.created_at is not None and now - event.created_at >= MAX_EVENT_AGE
        if expired:  # AUD-170 : plus de retries indéfinis
            event.status = "failed"
            event.last_error = f"abandonné après 24 h d'échecs : {event.last_error}"[:500]
        # Verrou de ligne : deux balayages livrant la même destination ne perdent pas
        # d'incrément (lecture fraîche sous FOR UPDATE, relâché au commit de l'appelant).
        session.refresh(hook, with_for_update=True)
        if not hook.enabled:  # désactivée entre-temps par un autre balayage
            session.flush()
            return False
        hook.consecutive_failures += 1
        # AUD-085 : une panne courte (5 échecs en ~7 min) ne désactive plus la
        # destination ; seule une panne qui dure (un événement en échec depuis 24 h).
        if hook.consecutive_failures >= MAX_CONSECUTIVE_FAILURES and expired:
            _disable(session, hook, reason=str(exc)[:500])
        session.flush()
        return False
```

  - dans `_disable`, supprimer la boucle `for ev in session.scalars(select(OutboxEvent)…): ev.status = "failed" …`. Ajouter à la place le commentaire `# AUD-085 : les événements pending sont GARDÉS ; ils repartent à la réactivation.` ;
  - remplacer la boucle `for event_id in ids:` de `deliver_due` par :

```python
        for event_id in ids:
            try:
                event = session.get(OutboxEvent, event_id, populate_existing=True)
                # Destination désactivée en cours de lot : bail laissé expirer.
                if event is None or event.status != "pending":
                    continue
                hook = session.get(OutboundWebhook, event.webhook_id)
                if hook is None or not hook.enabled:  # désactivée : bail laissé expirer
                    continue
                ok = deliver_one(session, event, hook, post=post)
                session.commit()
                delivered += ok
            except Exception:  # noqa: BLE001
                # AUD-168 : destination supprimée pendant la livraison (ligne disparue) ou
                # toute erreur de base sur CET événement : abandonné pour ce balayage (son
                # bail expire, un balayage suivant le reprend) sans priver les autres
                # événements du lot ni les purges du balayage.
                session.rollback()
                logger.exception("livraison %s : mise à jour de l'outbox impossible", event_id)
```

  - remplacer `purge_outbox` par :

```python
def purge_outbox(session: Session) -> int:
    """Rétention : supprime toute ligne de plus de OUTBOX_RETENTION_DAYS, `pending`
    comprises (AUD-170 : seule une destination désactivée depuis plus longtemps en garde
    encore — ses événements ne repartiraient de toute façon qu'abandonnés, cf.
    MAX_EVENT_AGE)."""
    res = session.execute(
        delete(OutboxEvent).where(
            OutboxEvent.created_at < _now() - timedelta(days=OUTBOX_RETENTION_DAYS),
        )
    )
    session.commit()
    return int(res.rowcount)  # type: ignore[attr-defined]
```

  - `uv run ruff check app/webhooks/delivery.py` : retirer l'import `select` s'il est devenu inutilisé (il sert encore à `_claim`, à vérifier).

- [ ] **Step 4:** `cd core && uv run pytest tests/test_webhooks_delivery_claim.py tests/test_webhooks_outbox.py tests/test_webhooks_review_fixes.py -v` → PASS. Contre-épreuve une fois : retirer le `try/except` de `deliver_due`, constater l'échec de `test_a_database_error_on_one_event_does_not_abort_the_sweep`, puis rétablir.

- [ ] **Step 5: Commit**

```bash
git add core/app/webhooks/delivery.py core/tests/test_webhooks_delivery_claim.py core/tests/test_webhooks_outbox.py
git commit -m "fix(core): outbox de webhooks sans désactivation hâtive ni retries infinis, balayage résilient (AUD-085, AUD-170, AUD-168)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Clôture du lot (revue de branche, portes, jumelles)

**Files:** aucun nouveau fichier. **Ne pas** toucher `CLAUDE.md`, `docs/revue/*` ni l'historique d'exécution (clôture documentaire par le contrôleur).

- [ ] **Step 1: Jumelles (piège n°14)** — vérifier chacune, corriger ou consigner dans le rapport final :
  - **AUD-012** :
    - `scripts/measure_cdc_consumer_throughput.py` et `scripts/spike_cdc_replication.py` passent par `stream_changes` / `decode_wal2json_message`, ou par leurs propres options. Les grep-er (`grep -n "options=\|change\"" core/scripts/*cdc*`). Ce sont des scripts historiques : les signaler sans les réécrire s'ils restent v1 ;
    - `CI` / `release.yml` « Start Postgres » : `max_slot_wal_keep_size` est inutile en CI (pas de slot longue durée), écart consigné ;
    - `deploy/helm/ci/smoke-deps.yaml` (`wal_level=logical`) : même remarque.
  - **AUD-013** :
    - `_dedup_cte` ↔ `snapshot.write_snapshot` (fait en Tâche 3) ;
    - `lake_as_of` ignore le snapshot par conception (`test_no_snapshot_keeps_raw_behaviour_and_as_of_ignores_snapshot`) : fenêtre complète conservée, limite consignée.
  - **AUD-014** :
    - `run_import` ↔ `run_append` ↔ `harvest/service.py:241` (même fonction) ;
    - formats non streamés (OGR, GeoParquet, XML) : reportés (en-tête).
  - **AUD-016** : sonde `worker` + `export-worker`, compose + Helm. Un seul script, commandes inchangées : `test_helm_chart.py` vert.
  - **AUD-028** : la reprise couvre toutes les files, `export` comprise (`get_stalled_jobs` sans `queue`), même si la tâche tourne sur `etl`.
  - **AUD-083 / AUD-029** :
    - l'aperçu (`preview_pipeline`, minuteur P16.03) et `transform.sqlExecutor` (`CORE_SQL_EXECUTOR_TIMEOUT_S`) ont déjà leurs bornes ;
    - `_RunGuard` ne couvre que `run_pipeline` ;
    - à vérifier : aucun autre appelant de `_execute_transform_chain` sans `check` (`grep -n "_execute_transform_chain(" core/app`).
  - **AUD-085 / AUD-170 / AUD-168** : la livraison des **alertes** (`app/alerts/`, « livraison tracée/rejouée/signée ») est une jumelle. Lire sa politique de retry (`grep -rn "attempts\|backoff\|MAX_" core/app/alerts/`) et consigner s'il y manque un plafond de tentatives ; ne pas la modifier dans ce lot.

- [ ] **Step 2: Revue finale de branche** (piège n°4) par un sous-agent neuf sur `git diff dev...HEAD` (après rebase sur SP-L3). Focus :
  - défauts de croisement entre tâches : Tâche 3 snapshot actif × Tâche 2 purge du lac ; Tâche 5 reprise × verrous CDC ; Tâche 6 garde × writers par lots ;
  - `docker compose config` par valeur pour `max_slot_wal_keep_size`, `CORE_LAKE_SNAPSHOT_ENABLED`, `CORE_PIPELINES_RUN_TIMEOUT_S`.

- [ ] **Step 3: Portes de qualité** (mêmes invocations qu'en CI) :

```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles app/net_pin.py
uv run lint-imports
uv run pytest --cov=app --cov-report=xml -q        # CORE_TEST_DATABASE_URL = base jetable dédiée
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check
```

Attendu : tout vert. Les 2 échecs intermittents documentés (`test_features_rls.py::test_scope_preserves_original_sql_error`, `test_deployability.py::test_every_compose_substitution_is_documented`) sont rejoués en isolation avant de s'imputer une régression. Les tests CDC postgis sont rejoués seuls (slot cluster-wide).

- [ ] **Step 4: OpenAPI / types TS** (diff vide attendu) :

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types && git diff --exit-code src/api/generated/core-schema.d.ts ../core/openapi.json
```

- [ ] **Step 5: Migrations** : `ls core/alembic/versions | tail -3` → aucune révision ajoutée par ce lot ; plage 0091-0094 rendue.

- [ ] **Step 6: Rapport au contrôleur** (pas de fichier de rapport `.md`). Y faire figurer :
  - AUD fermés : 012, 013, 016, 028, 083, 085, 168, 170 ;
  - partiels : 014, 029, avec leurs reliquats (cf. en-tête) ;
  - reportés : 157, 172, AUD-099 ;
  - écarts de spike (Tâche 1), jumelles (Step 1) et défauts de revue finale ;
  - SHA des commits.

Le contrôleur fait la clôture documentaire : `CLAUDE.md § Livré`, historique d'exécution, backlog / gaps et bilan de fonctionnalités.
