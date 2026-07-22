# SP-11a — Spike CDC + réplication PostgreSQL → GeoParquet — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une écriture PostGIS (API OGC Features, y compris via le widget Formulaire de SP-4) devient visible en GeoParquet sur MinIO en moins de 5 minutes, suppressions comprises, avec reprise sur panne sans perte ni gap — validé d'abord par un spike de go/no-go, puis livré comme worker CDC dédié (`cdc-worker`).

**Architecture:** Nouveau process long-lived `cdc-worker`, connecté DIRECTEMENT à `postgis:5432` (PgBouncer est en `POOL_MODE: transaction`, incompatible avec le protocole de réplication logique). Il consomme un flux de réplication logique PostgreSQL décodé par l'extension `wal2json` sur une publication unique `geostudio_cdc` tenue à jour par `apply_collection_ddl` (SP-3), bufferise les changements en mémoire par table, et les flushe en GeoParquet (append-only change log, colonnes `_op`/`_lsn`/`_ts`) vers MinIO toutes les ~30s ou tous les N changements. Le feedback de position (`confirmed_flush_lsn`) n'est envoyé qu'après un flush réussi → *at-least-once*, jamais de perte.

**Tech Stack:** Python (core existant), `psycopg2-binary` (protocole de réplication logique — `psycopg[binary]>=3.1` déjà présent ne le supporte pas), extension Postgres `wal2json`, `geopandas`/`shapely` (GeoParquet), `boto3` (déjà présent, MinIO), OpenTelemetry (déjà présent).

## Global Constraints

- Connexion cdc-worker → Postgres : **directe** à `postgis:5432`, jamais via `pgbouncer:6432` (PgBouncer `POOL_MODE: transaction` ne supporte pas la réplication logique).
- Publication unique nommée `geostudio_cdc` ; slot de réplication logique unique nommé `geostudio_cdc_slot`, plugin `wal2json`.
- Layout de sortie exact : `s3://<bucket>/cdc/tenant_id=<tenant>/collection_id=<collection>/dt=<YYYY-MM-DD>/part-<uuid>.parquet`.
- Chaque fichier est un lot append-only, jamais un état fusionné. Colonnes fixes : `_op` (`insert`/`update`/`delete`), `_lsn`, `_ts` (horloge murale du flush, pas l'horodatage de l'événement WAL).
- Une ligne `delete` est une tombstone : uniquement la clé primaire + `_op="delete"` (REPLICA IDENTITY par défaut, pas de `REPLICA IDENTITY FULL`).
- Flush au premier seuil atteint parmi : ~30s d'âge du buffer OU N changements (fixé à 500 dans ce plan).
- Feedback de position (`send_feedback`/`confirmed_flush_lsn`) envoyé **seulement après** l'écriture réussie du flush sur MinIO — jamais avant, jamais par message individuel.
- Pas de reprojection forcée : le CRS source (SRID de `Collection.srid`) est préservé tel quel dans les métadonnées GeoParquet.
- `geostudio.cdc.lag_seconds` (`ObservableGauge`, attribut `collection_id`) exporté en OTLP inconditionnel, même patron que `geostudio.jobs.backlog` (SP-10b) — silencieux si aucun collecteur n'écoute.
- `docker compose up` (par défaut, sans flag) démarre `cdc-worker` comme service métier essentiel, pas derrière un profil — aucune régression sur `core`/`worker`/le reste de la stack.
- Toute collection enregistrée (admin SP-3a ou ingestion automatique SP-6a/6b) rejoint `geostudio_cdc` sans opt-in manuel, via le point d'entrée unique déjà partagé par les deux chemins : `app/collections/ddl.py::apply_collection_ddl`.
- Hors périmètre (sous-parties ultérieures de SP-11) : compaction planifiée, module DuckDB, endpoint SQL sandbox, dashboard/alerte Grafana dédiés au lag CDC.

### Décisions de conception prises par ce plan (au-delà du texte de la spec)

La spec (`docs/superpowers/specs/2026-07-17-sp11a-spike-cdc-geoparquet-design.md`) fixe l'architecture ; ce plan tranche deux points d'implémentation qu'elle laisse ouverts :

1. **Driver de réplication : `psycopg2-binary`, pas `psycopg[binary]>=3.1`.** `psycopg` (v3, déjà dépendance du cœur) n'expose pas le protocole de réplication logique côté client. `psycopg2` le fait nativement (`psycopg2.extras.LogicalReplicationConnection`, `cur.create_replication_slot`/`start_replication`/`read_message`/`send_feedback`). Les deux drivers coexistent : `psycopg` reste utilisé partout ailleurs dans `core`, `psycopg2-binary` est ajouté uniquement pour la connexion de réplication du `cdc-worker`. Validé empiriquement par le spike (Task 1) — si l'API diffère de ce que ce plan présume, corriger dans le spike et répercuter la correction sur les tasks suivantes qui en dépendent (Task 7).
2. **Backfill sans `EXPORT_SNAPSHOT`.** La spec mentionne `CREATE_REPLICATION_SLOT ... EXPORT_SNAPSHOT` pour le backfill à froid. Ce plan simplifie : lire `pg_current_wal_lsn()` juste avant de démarrer `START_REPLICATION`, puis `SELECT *` sur chaque collection déjà enregistrée, taguée avec cette LSN comme `_lsn` de backfill. C'est safe parce que le slot de réplication capture déjà, depuis sa création (ou son dernier `confirmed_flush_lsn` sur une reprise), tout changement WAL — un changement qui arrive entre la lecture de la LSN-frontière et le `SELECT *` sera de toute façon redélivré par le flux live avec sa vraie LSN (plus grande), qui l'emporte dans la réduction `(pk, max(_lsn))` côté lecteur : au pire quelques doublons inoffensifs, jamais de perte ni de donnée fantôme. Pour une collection enregistrée **après** que le slot existe déjà (backfill tardif), le déclenchement est **paresseux** : au premier changement vu par `cdc-worker` pour une table inconnue de son cache de métadonnées en mémoire, il recharge les métadonnées de `Collection` et backfille cette table avant de continuer — évite d'avoir à faire pousser une notification depuis `apply_collection_ddl` (process `core`/`worker`) vers `cdc-worker` (process séparé).

---

### Task 1: Spike go/no-go — réplication logique + wal2json (tâche d'ouverture, bloquante)

**Files:**
- Modify: `deploy/postgis/Dockerfile` (ajoute `postgresql-16-wal2json`)
- Modify: `docker-compose.yml` (ajoute `-c wal_level=logical` à `postgis.command`)
- Modify: `core/pyproject.toml` (ajoute `psycopg2-binary>=2.9` à `dependencies`)
- Modify: `core/Dockerfile` (ajoute `"psycopg2-binary>=2.9"` à la ligne `uv pip install --system` — liste synchronisée à la main, cf. commentaire déjà présent dans ce fichier)
- Create: `core/scripts/spike_cdc_replication.py`
- Test: aucun test pytest — c'est un script empirique contre un PostGIS jetable réel, même patron que `core/scripts/spike_pgbouncer_rls.py` (SP-3b)

**Interfaces:**
- Produces: confirmation empirique que `psycopg2.extras.LogicalReplicationConnection` + `wal2json` se comportent comme présumé par ce plan (Tasks 7/8/9). Si un appel diffère du contrat décrit ci-dessous, la correction se fait ICI puis se répercute sur les tasks suivantes avant de les exécuter.

- [ ] **Step 1: Ajouter `wal2json` à l'image PostGIS**

Modifier `deploy/postgis/Dockerfile` :

```dockerfile
# postgis/postgis:16-3.4 ne fournit ni pgvector ni wal2json — le dépôt PGDG
# (déjà configuré dans l'image officielle pour installer les paquets postgis)
# sert aussi les paquets Debian postgresql-16-pgvector (SP-7) et
# postgresql-16-wal2json (SP-11a, décodage JSON du flux de réplication
# logique — pas de protocole binaire pgoutput à implémenter côté client).
FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector postgresql-16-wal2json \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: Activer `wal_level=logical` sur le service `postgis`**

Dans `docker-compose.yml`, modifier le bloc `command:` du service `postgis` :

```yaml
    command: >
      postgres
        -c shared_buffers=2GB
        -c effective_cache_size=6GB
        -c work_mem=64MB
        -c max_connections=200
        -c random_page_cost=1.1
        -c max_parallel_workers_per_gather=4
        -c wal_level=logical
```

`max_wal_senders`/`max_replication_slots` restent aux valeurs par défaut de Postgres 16 (10 chacun) — largement suffisant pour un seul slot ; pas de tuning explicite nécessaire. Un changement de `wal_level` nécessite un redémarrage complet du serveur (pas un simple reload) — `docker compose up -d --build postgis` recrée le conteneur, ce qui redémarre le process Postgres et applique le nouveau flag.

- [ ] **Step 3: Rebuild l'image `postgis` et vérifier `wal_level`**

```bash
docker compose build postgis
docker compose up -d postgis
docker compose exec postgis psql -U gis -d gis -c "SHOW wal_level;"
```

Expected: `logical`.

```bash
docker compose exec postgis psql -U gis -d gis -c "SELECT * FROM pg_available_extensions WHERE name = 'wal2json';"
```

Wal2json est une extension de sortie de plugin de décodage logique, pas une extension SQL installable via `CREATE EXTENSION` — cette requête peut renvoyer 0 ligne, ce n'est pas un échec. La vérification réelle se fait à l'étape 6 (le slot se crée avec `output_plugin="wal2json"` sans erreur).

- [ ] **Step 4: Ajouter `psycopg2-binary` comme dépendance**

Dans `core/pyproject.toml`, dans `[project] dependencies`, ajouter après `"psycopg[binary]>=3.1",` :

```toml
    "psycopg2-binary>=2.9",  # SP-11a : seul driver Python avec support du protocole
                             # de réplication logique (psycopg v3 ne l'expose pas) ;
                             # utilisé uniquement par app/cdc/ pour la connexion de
                             # réplication elle-même, psycopg[binary] reste le driver
                             # de tout le reste du cœur.
```

Dans `core/Dockerfile`, ajouter `"psycopg2-binary>=2.9"` dans la liste `uv pip install --system --no-cache` (même liste que `pyproject.toml`, synchronisée à la main — cf. le commentaire déjà présent au-dessus de cette commande dans ce fichier, qui documente explicitement ce risque de dérive).

```bash
cd core && uv sync
```

- [ ] **Step 5: Écrire le script spike**

Créer `core/scripts/spike_cdc_replication.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Spike SP-11a : CDC via réplication logique PostgreSQL + wal2json.

Vérifie, DANS L'ORDRE, contre un PostGIS jetable réel (wal_level=logical,
extension wal2json installée — cf. deploy/postgis/Dockerfile) :
1. création idempotente d'un slot de réplication logique avec le plugin
   wal2json ;
2. insert/update/delete sur une table avec colonne géométrie, décodés
   correctement depuis le flux wal2json ;
3. ALTER PUBLICATION ... ADD TABLE dynamique alors que le slot existe déjà
   (la nouvelle table doit apparaître dans le flux sans recréer le slot) ;
4. un cycle crash-simulé/redémarrage : un message consommé mais jamais
   confirmé (send_feedback) doit être rejoué à l'identique après
   reconnexion sur le même slot (at-least-once, jamais de perte).

Si un de ces points échoue durement, le plan s'arrête avant d'investir dans
le worker complet (spec SP-11a §Risques) — documenter l'échec et retourner
en brainstorm/spec plutôt que de continuer sur les tasks suivantes.

Usage :
  SPIKE_DATABASE_URL=postgresql://gis:<PG_PASSWORD>@127.0.0.1:5432/gis \
    uv run python -m scripts.spike_cdc_replication
Connexion DIRECTE à postgis (pas pgbouncer:6432) — le protocole de
réplication logique n'est pas supporté en pool "transaction".
Sort avec le code 0 (PASS) ou 1 (FAIL, échecs listés).
"""
import json
import os
import select
import sys
import time

import psycopg2
import psycopg2.errors
import psycopg2.extras
from sqlalchemy import create_engine, text

SLOT_NAME = "spike_cdc_slot"
PUBLICATION_NAME = "spike_cdc_pub"


def _setup_tables(dsn: str) -> None:
    engine = create_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))
    with engine.begin() as c:
        c.execute(text(f"DROP PUBLICATION IF EXISTS {PUBLICATION_NAME}"))
        c.execute(text("DROP TABLE IF EXISTS spike_cdc_t1, spike_cdc_t2"))
        c.execute(text(
            "CREATE TABLE spike_cdc_t1 (id serial PRIMARY KEY, v text, "
            "geom geometry(Point, 4326))"
        ))
        c.execute(text("CREATE TABLE spike_cdc_t2 (id serial PRIMARY KEY, v text)"))
        c.execute(text(f"CREATE PUBLICATION {PUBLICATION_NAME} FOR TABLE spike_cdc_t1"))
    engine.dispose()


def _ensure_slot(raw_dsn: str) -> None:
    conn = psycopg2.connect(raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection)
    cur = conn.cursor()
    try:
        cur.create_replication_slot(SLOT_NAME, output_plugin="wal2json")
    except psycopg2.errors.DuplicateObject:
        pass
    cur.close()
    conn.close()


def _drain_messages(raw_dsn: str, *, ack: bool, timeout_s: float = 5.0) -> list[dict]:
    """Consomme le flux pendant `timeout_s`. N'accuse réception (send_feedback)
    qu'à la fin, et seulement si `ack=True` — reproduit le contrat "flush S3
    réussi -> feedback" du worker réel : tant que `ack=False`, un redémarrage
    doit tout rejouer."""
    conn = psycopg2.connect(raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection)
    cur = conn.cursor()
    cur.start_replication(slot_name=SLOT_NAME, options={"pretty-print": "0"})
    messages: list[dict] = []
    last_lsn = None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        msg = cur.read_message()
        if msg:
            messages.append(json.loads(msg.payload))
            last_lsn = msg.data_start
            continue
        select.select([conn], [], [], 0.5)
    if ack and last_lsn is not None:
        cur.send_feedback(flush_lsn=last_lsn, reply=True)
    cur.close()
    conn.close()
    return messages


def main() -> int:
    dsn = os.environ["SPIKE_DATABASE_URL"]
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    _setup_tables(dsn)

    # 1. Création idempotente du slot.
    _ensure_slot(dsn)
    _ensure_slot(dsn)  # ne doit pas lever la deuxième fois
    check("slot créé de façon idempotente", True)

    # 2. insert/update/delete décodés, géométrie présente.
    engine = create_engine(dsn.replace("postgresql://", "postgresql+psycopg://"))
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO spike_cdc_t1 (v, geom) VALUES "
            "('a', ST_SetSRID(ST_MakePoint(2.3, 48.8), 4326))"
        ))
        c.execute(text("UPDATE spike_cdc_t1 SET v = 'b' WHERE v = 'a'"))
        c.execute(text("DELETE FROM spike_cdc_t1 WHERE v = 'b'"))
    msgs = _drain_messages(dsn, ack=False)
    changes = [ch for m in msgs for ch in m.get("change", [])]
    kinds = [ch["kind"] for ch in changes]
    check("insert/update/delete tous décodés", kinds == ["insert", "update", "delete"])
    insert_change = changes[0]
    geom_idx = insert_change["columnnames"].index("geom")
    geom_value = insert_change["columnvalues"][geom_idx]
    check("colonne géométrie présente et non vide", bool(geom_value))
    delete_change = changes[2]
    check("delete n'expose que la clé (oldkeys)", "oldkeys" in delete_change)

    # 3. ALTER PUBLICATION ADD TABLE dynamique, slot déjà existant.
    with engine.begin() as c:
        c.execute(text(f"ALTER PUBLICATION {PUBLICATION_NAME} ADD TABLE spike_cdc_t2"))
        c.execute(text("INSERT INTO spike_cdc_t2 (v) VALUES ('new-table')"))
    msgs2 = _drain_messages(dsn, ack=True, timeout_s=5.0)
    changes2 = [ch for m in msgs2 for ch in m.get("change", [])]
    check(
        "table ajoutée après coup apparaît dans le flux sans recréer le slot",
        any(ch["table"] == "spike_cdc_t2" for ch in changes2),
    )

    # 4. Crash simulé : message consommé sans ack, doit être rejoué.
    with engine.begin() as c:
        c.execute(text("INSERT INTO spike_cdc_t1 (v, geom) VALUES ('crash-test', NULL)"))
    first_drain = _drain_messages(dsn, ack=False, timeout_s=3.0)
    first_changes = [ch for m in first_drain for ch in m.get("change", [])]
    check("message crash-test bien reçu avant le crash simulé", len(first_changes) == 1)
    second_drain = _drain_messages(dsn, ack=False, timeout_s=3.0)  # "redémarrage" : nouvelle connexion, même slot
    second_changes = [ch for m in second_drain for ch in m.get("change", [])]
    check(
        "message non-acké rejoué à l'identique après reconnexion",
        second_changes == first_changes,
    )
    _drain_messages(dsn, ack=True, timeout_s=3.0)  # ack final, nettoyage
    third_drain = _drain_messages(dsn, ack=False, timeout_s=2.0)
    check("plus rien à rejouer une fois acké", third_drain == [])

    with engine.begin() as c:
        c.execute(text(f"DROP PUBLICATION IF EXISTS {PUBLICATION_NAME}"))
        c.execute(text("DROP TABLE IF EXISTS spike_cdc_t1, spike_cdc_t2"))
    conn = psycopg2.connect(dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection)
    cur = conn.cursor()
    try:
        cur.drop_replication_slot(SLOT_NAME)
    except Exception:
        pass
    cur.close()
    conn.close()
    engine.dispose()

    print("\nRésultat spike :", "PASS" if not failures else f"FAIL ({failures})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Exécuter le spike contre un PostGIS jetable réel**

```bash
docker compose up -d postgis
# attendre postgis healthy, puis :
cd core && SPIKE_DATABASE_URL="postgresql://gis:${PG_PASSWORD}@127.0.0.1:5432/gis" \
  uv run python -m scripts.spike_cdc_replication
```

Expected: `Résultat spike : PASS`. Si des signatures psycopg2 (`create_replication_slot`, `start_replication`, `read_message`, `send_feedback`) diffèrent de celles utilisées ci-dessus (l'API de `psycopg2.extras` a pu évoluer), corriger le script jusqu'à obtenir un PASS réel — documenter tout écart trouvé, il doit être répercuté sur Task 7 (`app/cdc/consumer.py` reprend le même contrat).

**GATE — si le spike ne passe pas PASS après investigation raisonnable (documenter ce qui a été essayé) : arrêter le plan ici.** Ne pas continuer vers Task 2 sans un PASS réel contre un PostGIS jetable — c'est le go/no-go que la spec impose explicitement (§Risques : « le morceau le plus délicat de la feuille de route »).

- [ ] **Step 7: Commit**

```bash
git add deploy/postgis/Dockerfile docker-compose.yml core/pyproject.toml core/Dockerfile core/uv.lock core/scripts/spike_cdc_replication.py
git commit -m "feat(core): SP-11a — spike go/no-go CDC réplication logique + wal2json"
```

---

### Task 2: Gestion de la publication `geostudio_cdc`

**Files:**
- Create: `core/app/collections/publication.py`
- Modify: `core/app/collections/ddl.py` (appelle `add_table_to_publication` en fin d'`apply_collection_ddl`)
- Modify: `core/app/collections/routes.py` (appelle `remove_table_from_publication` dans `unregister_collection`, avant `repo.delete_collection`)
- Test: `core/tests/test_collections_publication.py`

**Interfaces:**
- Consumes: `Session` (SQLAlchemy), pattern `quote_ident`-style déjà en usage dans `ddl.py` (mais réimplémenté localement — voir Step 1, pour éviter un cycle d'import `ddl.py` ↔ `publication.py`).
- Produces: `PUBLICATION_NAME = "geostudio_cdc"` ; `ensure_publication_exists(session)`, `add_table_to_publication(session, table_name)`, `remove_table_from_publication(session, table_name)` — tous idempotents, réutilisés par Task 9 (`app/cdc/main.py` ne les appelle jamais — seuls `core`/`worker` les appellent, via `apply_collection_ddl`/`unregister_collection`).

- [ ] **Step 1: Écrire `core/app/collections/publication.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Publication PostgreSQL pour le CDC (SP-11a, arbitrage A16) : une seule
publication `geostudio_cdc`, tenue à jour par apply_collection_ddl (register
manuel SP-3a et ingestion automatique SP-6a/6b partagent ce point d'entrée
unique, cf. app.ingestion.importer.run_import) et par unregister_collection.
cdc-worker ne touche jamais à cette publication — il ne fait que la
consommer (app.cdc.consumer).

Pas d'import de app.collections.ddl.quote_ident ici (le quoting est
réimplémenté localement) : ddl.py importe ce module pour appeler
add_table_to_publication depuis apply_collection_ddl, un import dans l'autre
sens créerait un cycle."""
from sqlalchemy import text
from sqlalchemy.orm import Session

PUBLICATION_NAME = "geostudio_cdc"


def _qi(session: Session, identifier: str) -> str:
    return session.get_bind().dialect.identifier_preparer.quote(identifier)


def ensure_publication_exists(session: Session) -> None:
    exists = session.execute(
        text("SELECT 1 FROM pg_publication WHERE pubname = :name"),
        {"name": PUBLICATION_NAME},
    ).scalar()
    if not exists:
        session.execute(text(f"CREATE PUBLICATION {PUBLICATION_NAME}"))


def add_table_to_publication(session: Session, table_name: str) -> None:
    ensure_publication_exists(session)
    already = session.execute(
        text(
            "SELECT 1 FROM pg_publication_tables "
            "WHERE pubname = :name AND schemaname = 'public' AND tablename = :t"
        ),
        {"name": PUBLICATION_NAME, "t": table_name},
    ).scalar()
    if not already:
        t = _qi(session, table_name)
        session.execute(text(f"ALTER PUBLICATION {PUBLICATION_NAME} ADD TABLE public.{t}"))


def remove_table_from_publication(session: Session, table_name: str) -> None:
    exists_pub = session.execute(
        text("SELECT 1 FROM pg_publication WHERE pubname = :name"),
        {"name": PUBLICATION_NAME},
    ).scalar()
    if not exists_pub:
        return
    member = session.execute(
        text(
            "SELECT 1 FROM pg_publication_tables "
            "WHERE pubname = :name AND schemaname = 'public' AND tablename = :t"
        ),
        {"name": PUBLICATION_NAME, "t": table_name},
    ).scalar()
    if member:
        t = _qi(session, table_name)
        session.execute(text(f"ALTER PUBLICATION {PUBLICATION_NAME} DROP TABLE public.{t}"))
```

- [ ] **Step 2: Écrire le test (échoue d'abord — pas de wiring encore)**

Créer `core/tests/test_collections_publication.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import text

from app.collections.publication import (
    add_table_to_publication, remove_table_from_publication,
)

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_table(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_pub"))
        conn.execute(text("CREATE TABLE t_pub (id serial PRIMARY KEY, v text)"))
    yield "t_pub"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP PUBLICATION IF EXISTS geostudio_cdc"))
        conn.execute(text("DROP TABLE IF EXISTS t_pub"))


def _is_member(pg_engine, table_name: str) -> bool:
    with pg_engine.begin() as conn:
        return bool(conn.execute(
            text(
                "SELECT 1 FROM pg_publication_tables WHERE pubname = 'geostudio_cdc' "
                "AND schemaname = 'public' AND tablename = :t"
            ),
            {"t": table_name},
        ).scalar())


def test_add_table_creates_publication_and_adds_table(pg_table, pg_session_factory, pg_engine):
    with pg_session_factory() as session:
        add_table_to_publication(session, pg_table)
        session.commit()
    assert _is_member(pg_engine, pg_table)


def test_add_table_is_idempotent(pg_table, pg_session_factory, pg_engine):
    with pg_session_factory() as session:
        add_table_to_publication(session, pg_table)
        add_table_to_publication(session, pg_table)  # ne doit pas lever
        session.commit()
    assert _is_member(pg_engine, pg_table)


def test_remove_table_drops_membership_but_keeps_publication(pg_table, pg_session_factory, pg_engine):
    with pg_session_factory() as session:
        add_table_to_publication(session, pg_table)
        session.commit()
    with pg_session_factory() as session:
        remove_table_from_publication(session, pg_table)
        session.commit()
    assert not _is_member(pg_engine, pg_table)
    with pg_engine.begin() as conn:
        assert conn.execute(
            text("SELECT 1 FROM pg_publication WHERE pubname = 'geostudio_cdc'")
        ).scalar()  # la publication elle-même survit


def test_remove_table_is_idempotent_when_never_added(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        remove_table_from_publication(session, pg_table)  # ne doit pas lever
        session.commit()
```

- [ ] **Step 3: Lancer les tests, vérifier qu'ils passent déjà (le module ne dépend d'aucun wiring)**

```bash
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:${PG_PASSWORD}@127.0.0.1:5432/gis" \
  uv run pytest tests/test_collections_publication.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Wirer dans `apply_collection_ddl`**

Modifier `core/app/collections/ddl.py` — ajouter l'import et l'appel en fin de fonction :

```python
from app.collections.publication import add_table_to_publication
```

```python
def apply_collection_ddl(session: Session, table_name: str) -> None:
    t = _qi(session, table_name)
    stmts = [
        # ... (statements existants, inchangés)
    ]
    for stmt in stmts:
        session.execute(text(stmt))
    seq = session.execute(
        # ... (inchangé)
    ).scalar()
    if seq:
        session.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE {seq} TO gis_rls"))
    add_table_to_publication(session, table_name)
```

- [ ] **Step 5: Wirer dans `unregister_collection`**

Modifier `core/app/collections/routes.py` :

```python
from app.collections.publication import remove_table_from_publication
```

```python
@router.delete("/collections/{collection_id}", status_code=204)
def unregister_collection(
    collection_id: str,
    user=Depends(get_current_user), session: Session = Depends(get_session),
):
    col = get_readable_collection(session, user, collection_id)
    _require_admin(user)  # après le 404 : un non-admin qui la voit reçoit 403
    remove_table_from_publication(session, col.table_name)
    repo.delete_collection(session, col)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="collection.delete", object_type="collection", object_id=collection_id,
                payload={})
```

- [ ] **Step 6: Test de régression sur `test_collections_ddl.py` (aucune modification attendue, juste non-cassé)**

```bash
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:${PG_PASSWORD}@127.0.0.1:5432/gis" \
  uv run pytest tests/test_collections_ddl.py tests/test_collections_publication.py tests/test_collections_routes.py -v
```

Expected: tous verts. `test_ddl_is_idempotent` doit rester vert (appeler `apply_collection_ddl` deux fois n'échoue pas, y compris avec l'ajout à la publication).

- [ ] **Step 7: Commit**

```bash
git add core/app/collections/publication.py core/app/collections/ddl.py core/app/collections/routes.py core/tests/test_collections_publication.py
git commit -m "feat(core): SP-11a — publication geostudio_cdc tenue à jour par apply_collection_ddl/unregister_collection"
```

---

### Task 3: Gauge `geostudio.cdc.lag_seconds`

**Files:**
- Modify: `core/app/observability.py` (ajoute `register_cdc_lag_gauge`)
- Test: `core/tests/test_observability_cdc_lag.py`

**Interfaces:**
- Produces: `observability.register_cdc_lag_gauge(get_lag_seconds: Callable[[], dict[str, float]], *, meter=None) -> None`. `get_lag_seconds` est fourni par `app/cdc/main.py` (Task 9) — état en mémoire du process cdc-worker, pas une requête DB (contrairement à `register_jobs_backlog_gauge`).

- [ ] **Step 1: Écrire le test (échoue — la fonction n'existe pas)**

Créer `core/tests/test_observability_cdc_lag.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app import observability


def _read_lag(reader: InMemoryMetricReader) -> dict[str, float]:
    data = reader.get_metrics_data()
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == "geostudio.cdc.lag_seconds":
                    return {dp.attributes["collection_id"]: dp.value for dp in metric.data.data_points}
    return {}


def test_cdc_lag_gauge_reports_per_collection_lag():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test")

    observability.register_cdc_lag_gauge(lambda: {"parcelles": 12.5, "routes": 3.0}, meter=meter)

    assert _read_lag(reader) == {"parcelles": 12.5, "routes": 3.0}


def test_cdc_lag_gauge_reports_empty_when_no_collection_tracked():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test")

    observability.register_cdc_lag_gauge(lambda: {}, meter=meter)

    assert _read_lag(reader) == {}
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_observability_cdc_lag.py -v
```

Expected: FAIL — `AttributeError: module 'app.observability' has no attribute 'register_cdc_lag_gauge'`.

- [ ] **Step 3: Ajouter `register_cdc_lag_gauge` à `core/app/observability.py`**

Ajouter à la fin du fichier, après `register_jobs_backlog_gauge` :

```python
def register_cdc_lag_gauge(get_lag_seconds, *, meter=None) -> None:
    """ObservableGauge geostudio.cdc.lag_seconds (SP-11a), un point de donnée
    par collection (attribut collection_id) — écart en secondes entre
    l'horloge murale et l'horodatage du dernier flush GeoParquet réussi pour
    cette collection. `get_lag_seconds` est un callable fourni par le
    cdc-worker (état en mémoire du process, pas une requête DB —
    contrairement à register_jobs_backlog_gauge) qui retourne
    {collection_id: lag_secondes} à l'instant de l'appel ; c'est lui qui
    calcule time.time() - last_flush_ts, pas ce module, pour rester
    testable sans horloge réelle (cf. test_observability_cdc_lag.py)."""
    from opentelemetry.metrics import Observation

    meter = meter or metrics.get_meter(__name__)

    def _callback(options):
        return [
            Observation(lag, {"collection_id": collection_id})
            for collection_id, lag in get_lag_seconds().items()
        ]

    meter.create_observable_gauge(
        "geostudio.cdc.lag_seconds",
        callbacks=[_callback],
        unit="s",
        description=(
            "Écart entre l'horloge murale et le dernier flush GeoParquet "
            "réussi, par collection"
        ),
    )
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_observability_cdc_lag.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/observability.py core/tests/test_observability_cdc_lag.py
git commit -m "feat(core): SP-11a — gauge geostudio.cdc.lag_seconds"
```

---

### Task 4: Écriture GeoParquet (`app/cdc/parquet_writer.py`)

**Files:**
- Create: `core/app/cdc/__init__.py` (vide)
- Create: `core/app/cdc/parquet_writer.py`
- Modify: `core/pyproject.toml` (ajoute `geopandas>=0.14`)
- Modify: `core/Dockerfile` (ajoute `"geopandas>=0.14"` à la liste `uv pip install --system`)
- Test: `core/tests/test_cdc_parquet_writer.py`

**Interfaces:**
- Produces: `ChangeRow` (dataclass : `op: str`, `lsn: int`, `ts: float`, `pk_column: str`, `pk_value`, `columns: dict`, `geometry_column: str | None`, `geometry_wkb_hex: str | None`) ; `build_geodataframe(rows, *, srid) -> geopandas.GeoDataFrame` ; `write_geoparquet(rows, *, srid, path) -> None`. Consommé par Task 6 (buffer) et Task 9 (entrypoint).

- [ ] **Step 1: Ajouter `geopandas` comme dépendance**

Dans `core/pyproject.toml`, ajouter dans `dependencies` après `"pyproj>=3.6",` :

```toml
    "geopandas>=0.14",  # SP-11a : GeoDataFrame.to_parquet gère nativement les
                        # métadonnées GeoParquet 1.0 ; s'appuie sur shapely,
                        # déjà présent.
```

Dans `core/Dockerfile`, ajouter `"geopandas>=0.14"` à la liste `uv pip install --system --no-cache`.

```bash
cd core && uv sync
```

- [ ] **Step 2: Écrire le test (échoue — le module n'existe pas)**

Créer `core/app/cdc/__init__.py` (vide) et `core/tests/test_cdc_parquet_writer.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import geopandas as gpd
import pandas as pd
import shapely.wkb
from shapely.geometry import Point

from app.cdc.parquet_writer import ChangeRow, build_geodataframe, write_geoparquet


def _hex(geom) -> str:
    return shapely.wkb.dumps(geom, hex=True)


def test_build_geodataframe_insert_and_update():
    rows = [
        ChangeRow(op="insert", lsn=100, ts=1721212121.0, pk_column="id", pk_value=1,
                  columns={"id": 1, "titre": "a"}, geometry_column="geom",
                  geometry_wkb_hex=_hex(Point(2.3, 48.8))),
        ChangeRow(op="update", lsn=105, ts=1721212125.0, pk_column="id", pk_value=1,
                  columns={"id": 1, "titre": "b"}, geometry_column="geom",
                  geometry_wkb_hex=_hex(Point(2.4, 48.9))),
    ]
    gdf = build_geodataframe(rows, srid=4326)
    assert list(gdf["_op"]) == ["insert", "update"]
    assert list(gdf["_lsn"]) == [100, 105]
    assert list(gdf["_ts"]) == [1721212121.0, 1721212125.0]
    assert list(gdf["titre"]) == ["a", "b"]
    assert gdf.crs.to_epsg() == 4326
    assert gdf.geometry.iloc[1].equals(Point(2.4, 48.9))


def test_build_geodataframe_delete_is_tombstone_only():
    rows = [
        ChangeRow(op="insert", lsn=1, ts=1.0, pk_column="id", pk_value=1,
                  columns={"id": 1, "titre": "a"}, geometry_column="geom",
                  geometry_wkb_hex=_hex(Point(0, 0))),
        ChangeRow(op="delete", lsn=2, ts=2.0, pk_column="id", pk_value=1,
                  columns={"id": 1}, geometry_column="geom", geometry_wkb_hex=None),
    ]
    gdf = build_geodataframe(rows, srid=4326)
    assert gdf["_op"].iloc[1] == "delete"
    assert pd.isna(gdf["titre"].iloc[1])  # tombstone : pas de colonnes métier hors PK
    assert gdf.geometry.iloc[1] is None


def test_write_geoparquet_roundtrip_preserves_crs_and_columns(tmp_path):
    rows = [ChangeRow(op="insert", lsn=1, ts=1.0, pk_column="id", pk_value=1,
                       columns={"id": 1, "titre": "a"}, geometry_column="geom",
                       geometry_wkb_hex=_hex(Point(0, 0)))]
    path = str(tmp_path / "part.parquet")
    write_geoparquet(rows, srid=2154, path=path)
    gdf = gpd.read_parquet(path)
    assert gdf.crs.to_epsg() == 2154
    assert len(gdf) == 1
    assert gdf["_op"].iloc[0] == "insert"
```

- [ ] **Step 3: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_cdc_parquet_writer.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.cdc.parquet_writer'`.

- [ ] **Step 4: Écrire `core/app/cdc/parquet_writer.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Écriture GeoParquet 1.0 pour les lots de changements CDC (SP-11a §Format
de sortie) : append-only change log, jamais un état fusionné. Une ligne
"delete" est une tombstone — seules la PK et _op sont renseignées (REPLICA
IDENTITY par défaut n'expose que la PK sur delete, pas besoin de REPLICA
IDENTITY FULL). Pas de reprojection : le SRID source (Collection.srid) est
passé tel quel par l'appelant et posé comme CRS de sortie."""
from dataclasses import dataclass

import geopandas as gpd
import shapely.wkb
from shapely.geometry.base import BaseGeometry


@dataclass
class ChangeRow:
    op: str  # "insert" | "update" | "delete"
    lsn: int
    ts: float  # horloge murale d'écriture du FLUSH (pas l'horodatage wal2json)
    pk_column: str
    pk_value: object
    columns: dict  # colonnes métier ; {pk_column: pk_value} seulement si op == "delete"
    geometry_column: str | None
    geometry_wkb_hex: str | None  # hex EWKB ; None pour une tombstone ou une table sans géométrie


def _decode_geometry(wkb_hex: str | None) -> BaseGeometry | None:
    if wkb_hex is None:
        return None
    return shapely.wkb.loads(bytes.fromhex(wkb_hex))


def build_geodataframe(rows: list[ChangeRow], *, srid: int) -> gpd.GeoDataFrame:
    records = []
    geometries = []
    for row in rows:
        record = dict(row.columns)
        record[row.pk_column] = row.pk_value
        record["_op"] = row.op
        record["_lsn"] = row.lsn
        record["_ts"] = row.ts
        records.append(record)
        geometries.append(_decode_geometry(row.geometry_wkb_hex))
    crs = f"EPSG:{srid}" if srid else None
    return gpd.GeoDataFrame(records, geometry=geometries, crs=crs)


def write_geoparquet(rows: list[ChangeRow], *, srid: int, path: str) -> None:
    gdf = build_geodataframe(rows, srid=srid)
    gdf.to_parquet(path)
```

- [ ] **Step 5: Lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_cdc_parquet_writer.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add core/app/cdc/__init__.py core/app/cdc/parquet_writer.py core/pyproject.toml core/Dockerfile core/uv.lock core/tests/test_cdc_parquet_writer.py
git commit -m "feat(core): SP-11a — écriture GeoParquet (app.cdc.parquet_writer)"
```

---

### Task 5: Stockage S3/MinIO pour le worker CDC (`app/cdc/storage.py`)

**Files:**
- Create: `core/app/cdc/storage.py`
- Test: `core/tests/test_cdc_storage.py`

**Interfaces:**
- Consumes: `app.ingestion.storage.make_s3_client` (ré-exporté).
- Produces: `make_s3_client` (ré-export), `ensure_cdc_bucket(client, bucket)`, `upload_parquet_file(client, *, bucket, key, local_path)`. Consommé par Task 9 (entrypoint).

- [ ] **Step 1: Écrire le test (échoue — le module n'existe pas)**

Créer `core/tests/test_cdc_storage.py`, même patron `_FakeS3Client` que `test_ingestion_storage.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Wrapper S3 fin — testé avec un client boto3 factice (pas de MinIO réel
nécessaire), même patron que test_ingestion_storage.py (SP-6a)."""
from app.cdc.storage import ensure_cdc_bucket, upload_parquet_file


class _FakeS3Client:
    def __init__(self):
        self.created_buckets: list[str] = []
        self.uploaded: list[tuple[str, str, str]] = []  # (local_path, bucket, key)

    def create_bucket(self, Bucket):  # noqa: N803 - signature boto3
        self.created_buckets.append(Bucket)

    def upload_file(self, Filename, Bucket, Key):  # noqa: N803
        self.uploaded.append((Filename, Bucket, Key))


def test_ensure_cdc_bucket_creates_bucket():
    client = _FakeS3Client()
    ensure_cdc_bucket(client, "geostudio-cdc")
    assert client.created_buckets == ["geostudio-cdc"]


def test_ensure_cdc_bucket_ignores_already_exists():
    from botocore.exceptions import ClientError

    class _AlreadyExistsClient(_FakeS3Client):
        def create_bucket(self, Bucket):  # noqa: N803
            raise ClientError(
                {"Error": {"Code": "BucketAlreadyOwnedByYou"}}, "CreateBucket",
            )

    ensure_cdc_bucket(_AlreadyExistsClient(), "geostudio-cdc")  # ne doit pas lever


def test_upload_parquet_file_targets_upload_file():
    client = _FakeS3Client()
    upload_parquet_file(client, bucket="geostudio-cdc", key="cdc/part-1.parquet", local_path="/tmp/part-1.parquet")
    assert client.uploaded == [("/tmp/part-1.parquet", "geostudio-cdc", "cdc/part-1.parquet")]
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_cdc_storage.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.cdc.storage'`.

- [ ] **Step 3: Écrire `core/app/cdc/storage.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Upload S3/MinIO pour les fichiers GeoParquet CDC (SP-11a). Réutilise
make_s3_client (app.ingestion.storage, SP-6a) — même client boto3, bucket
dédié (S3_CDC_BUCKET) plutôt que le bucket d'uploads."""
from botocore.exceptions import ClientError

from app.ingestion.storage import make_s3_client  # noqa: F401  (ré-export pour app.cdc.main)


def ensure_cdc_bucket(client, bucket: str) -> None:
    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise


def upload_parquet_file(client, *, bucket: str, key: str, local_path: str) -> None:
    client.upload_file(local_path, bucket, key)
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_cdc_storage.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/cdc/storage.py core/tests/test_cdc_storage.py
git commit -m "feat(core): SP-11a — stockage S3/MinIO du worker CDC (app.cdc.storage)"
```

---

### Task 6: Buffer en mémoire par collection + calcul du feedback sûr (`app/cdc/buffer.py`)

**Files:**
- Create: `core/app/cdc/buffer.py`
- Test: `core/tests/test_cdc_buffer.py`

**Interfaces:**
- Consumes: `app.cdc.parquet_writer.ChangeRow`.
- Produces: `CdcBufferManager` avec `.add(table_name, row)`, `.tables_due_for_flush() -> list[str]`, `.drain(table_name, flush_ts) -> list[ChangeRow]`, `.safe_ack_lsn(last_seen_lsn) -> int`. Consommé par Task 9.

- [ ] **Step 1: Écrire le test (échoue — le module n'existe pas)**

Créer `core/tests/test_cdc_buffer.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.cdc.buffer import CdcBufferManager
from app.cdc.parquet_writer import ChangeRow


def _row(lsn: int) -> ChangeRow:
    return ChangeRow(op="insert", lsn=lsn, ts=0.0, pk_column="id", pk_value=lsn,
                      columns={"id": lsn}, geometry_column=None, geometry_wkb_hex=None)


def test_flush_due_on_row_count_threshold():
    mgr = CdcBufferManager()
    for i in range(500):
        mgr.add("t1", _row(i))
    assert "t1" in mgr.tables_due_for_flush()


def test_flush_not_due_below_threshold():
    mgr = CdcBufferManager()
    mgr.add("t1", _row(1))
    assert mgr.tables_due_for_flush() == []


def test_flush_due_on_age_threshold(monkeypatch):
    times = iter([100.0, 100.0, 131.0])  # opened_at capturé au 1er add, puis vérifié plus tard
    monkeypatch.setattr("app.cdc.buffer.time.monotonic", lambda: next(times))
    mgr = CdcBufferManager()
    mgr.add("t1", _row(1))
    assert "t1" in mgr.tables_due_for_flush()


def test_drain_empties_buffer_and_stamps_flush_ts():
    mgr = CdcBufferManager()
    mgr.add("t1", _row(1))
    rows = mgr.drain("t1", flush_ts=42.0)
    assert [r.ts for r in rows] == [42.0]
    assert mgr.tables_due_for_flush() == []


def test_safe_ack_lsn_bounded_by_oldest_pending_across_tables():
    mgr = CdcBufferManager()
    mgr.add("t1", _row(10))
    mgr.add("t2", _row(5))
    # t2 a un message plus ancien (lsn=5) encore non flushé : on ne peut
    # jamais accuser réception au-delà de lsn=4, même si t1 a déjà tout
    # flushé, sans quoi un crash perdrait la ligne lsn=5 de t2.
    assert mgr.safe_ack_lsn(last_seen_lsn=10) == 4


def test_safe_ack_lsn_is_last_seen_when_everything_flushed():
    mgr = CdcBufferManager()
    mgr.add("t1", _row(10))
    mgr.drain("t1", flush_ts=0.0)
    assert mgr.safe_ack_lsn(last_seen_lsn=10) == 10
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_cdc_buffer.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.cdc.buffer'`.

- [ ] **Step 3: Écrire `core/app/cdc/buffer.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Bufferisation en mémoire des changements CDC par table et calcul du point
de feedback sûr (SP-11a §Flux continu / §Reprise sur panne) : flush toutes
les ~30s OU tous les N changements, le premier seuil atteint. Le feedback de
réplication ne peut jamais avancer au-delà du message le plus ancien encore
non flushé, TOUTES tables confondues (confirmed_flush_lsn est une position
dans le flux WAL global, pas par table) — safe_ack_lsn() porte cette
garantie."""
import time
from dataclasses import dataclass, field

from app.cdc.parquet_writer import ChangeRow

FLUSH_MAX_AGE_S = 30.0
FLUSH_MAX_ROWS = 500


@dataclass
class _TableBuffer:
    rows: list = field(default_factory=list)
    opened_at: float | None = None

    def add(self, row: ChangeRow) -> None:
        if not self.rows:
            self.opened_at = time.monotonic()
        self.rows.append(row)

    def is_flush_due(self) -> bool:
        if not self.rows:
            return False
        return (
            len(self.rows) >= FLUSH_MAX_ROWS
            or (time.monotonic() - self.opened_at) >= FLUSH_MAX_AGE_S
        )

    def drain(self, flush_ts: float) -> list:
        for row in self.rows:
            row.ts = flush_ts
        rows, self.rows = self.rows, []
        self.opened_at = None
        return rows


class CdcBufferManager:
    """Un _TableBuffer par table_name suivie. table_name identifie la
    collection sans ambiguïté (schéma public, une seule table physique par
    nom — contrairement à Collection.id qui est un slug par tenant, la table
    physique n'existe qu'une fois dans cette base)."""

    def __init__(self) -> None:
        self._buffers: dict[str, _TableBuffer] = {}

    def add(self, table_name: str, row: ChangeRow) -> None:
        self._buffers.setdefault(table_name, _TableBuffer()).add(row)

    def tables_due_for_flush(self) -> list[str]:
        return [t for t, buf in self._buffers.items() if buf.is_flush_due()]

    def drain(self, table_name: str, flush_ts: float) -> list:
        return self._buffers[table_name].drain(flush_ts)

    def safe_ack_lsn(self, *, last_seen_lsn: int) -> int:
        oldest_pending = min(
            (buf.rows[0].lsn for buf in self._buffers.values() if buf.rows),
            default=None,
        )
        if oldest_pending is None:
            return last_seen_lsn
        return oldest_pending - 1
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_cdc_buffer.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/cdc/buffer.py core/tests/test_cdc_buffer.py
git commit -m "feat(core): SP-11a — buffer CDC en mémoire + calcul du feedback sûr (app.cdc.buffer)"
```

---

### Task 7: Décodage wal2json + consommation du flux de réplication (`app/cdc/consumer.py`)

**Files:**
- Create: `core/app/cdc/consumer.py`
- Test: `core/tests/test_cdc_consumer.py` (partie décodage : pas de marqueur `postgis`) et `core/tests/test_cdc_consumer_postgis.py` (partie flux réel : marqueur `postgis`)

**Interfaces:**
- Consumes: `app.cdc.parquet_writer.ChangeRow` ; contrat psycopg2 validé par le spike (Task 1).
- Produces: `SLOT_NAME = "geostudio_cdc_slot"` ; `ensure_replication_slot(raw_dsn)` ; `DecodedChange` (dataclass : `table_name`, `row`) ; `decode_wal2json_message(payload, *, lsn, collection_meta) -> list[DecodedChange]` où `collection_meta: dict[str, tuple[str, str | None]]` = `{table_name: (pk_column, geometry_column)}` ; `stream_changes(raw_dsn, *, on_message, is_flush_due, do_flush, should_stop=lambda: False, poll_timeout_s=1.0)`. Consommé par Task 9.

- [ ] **Step 1: Écrire le test de décodage (pur, sans DB — échoue, le module n'existe pas)**

Créer `core/tests/test_cdc_consumer.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import json

from app.cdc.consumer import decode_wal2json_message

_INSERT_PAYLOAD = json.dumps({
    "change": [{
        "kind": "insert", "table": "t_rls",
        "columnnames": ["id", "titre", "geom"],
        "columnvalues": [1, "a", "0101000020E6100000..."],
    }]
})

_DELETE_PAYLOAD = json.dumps({
    "change": [{
        "kind": "delete", "table": "t_rls",
        "oldkeys": {"keynames": ["id"], "keyvalues": [1]},
    }]
})

_MULTI_CHANGE_PAYLOAD = json.dumps({
    "change": [
        {"kind": "insert", "table": "t_rls", "columnnames": ["id", "titre"], "columnvalues": [2, "b"]},
        {"kind": "update", "table": "t_rls", "columnnames": ["id", "titre"], "columnvalues": [2, "c"]},
    ]
})

_UNKNOWN_TABLE_PAYLOAD = json.dumps({
    "change": [{"kind": "insert", "table": "not_tracked", "columnnames": ["id"], "columnvalues": [1]}]
})

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


def test_decode_delete_is_tombstone_from_oldkeys():
    decoded = decode_wal2json_message(_DELETE_PAYLOAD, lsn=200, collection_meta=_META)
    row = decoded[0].row
    assert row.op == "delete"
    assert row.pk_value == 1
    assert row.columns == {"id": 1}
    assert row.geometry_wkb_hex is None


def test_decode_message_with_multiple_changes():
    decoded = decode_wal2json_message(_MULTI_CHANGE_PAYLOAD, lsn=300, collection_meta=_META)
    assert [d.row.op for d in decoded] == ["insert", "update"]
    assert all(d.row.lsn == 300 for d in decoded)  # même LSN de message, suffisant pour max(_lsn)


def test_decode_ignores_unknown_table():
    decoded = decode_wal2json_message(_UNKNOWN_TABLE_PAYLOAD, lsn=400, collection_meta=_META)
    assert decoded == []
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_cdc_consumer.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.cdc.consumer'`.

- [ ] **Step 3: Écrire `core/app/cdc/consumer.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Consommateur du flux de réplication logique (SP-11a) : décode les messages
wal2json et pilote le feedback (confirmed_flush_lsn), borné par
CdcBufferManager.safe_ack_lsn côté appelant — jamais après un simple insert,
seulement après un flush GeoParquet réussi (app.cdc.main, Task 9).

Boucle manuelle (read_message + select), pas consume_stream() : il faut
pouvoir déclencher un flush sur seuil de TEMPS même en l'absence de nouveau
message, ce que consume_stream() (bloquant, un seul callback par message
reçu) ne permet pas. Contrat psycopg2 validé empiriquement par le spike
(core/scripts/spike_cdc_replication.py, Task 1) — ajuster ici si le spike a
trouvé un contrat différent des signatures utilisées ci-dessous."""
import json
import select

import psycopg2
import psycopg2.errors
import psycopg2.extras
from dataclasses import dataclass

from app.cdc.parquet_writer import ChangeRow

SLOT_NAME = "geostudio_cdc_slot"
OUTPUT_PLUGIN = "wal2json"


def ensure_replication_slot(raw_dsn: str) -> None:
    conn = psycopg2.connect(raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection)
    cur = conn.cursor()
    try:
        cur.create_replication_slot(SLOT_NAME, output_plugin=OUTPUT_PLUGIN)
    except psycopg2.errors.DuplicateObject:
        pass
    finally:
        cur.close()
        conn.close()


@dataclass
class DecodedChange:
    table_name: str
    row: ChangeRow


def decode_wal2json_message(
    payload: str, *, lsn: int, collection_meta: dict,
) -> list:
    """collection_meta : {table_name: (pk_column, geometry_column)} — résolu
    par app.cdc.main depuis app.collections.models.Collection. Une table
    publiée mais absente de collection_meta (désenregistrée entre-temps, ou
    jamais backfillée par ce process) est ignorée — app.cdc.main la recharge
    et backfille au premier changement vu (Task 8/9)."""
    data = json.loads(payload)
    out = []
    for change in data.get("change", []):
        table_name = change["table"]
        meta = collection_meta.get(table_name)
        if meta is None:
            continue
        pk_column, geometry_column = meta
        kind = change["kind"]
        if kind == "delete":
            keynames = change.get("oldkeys", {}).get("keynames", [])
            keyvalues = change.get("oldkeys", {}).get("keyvalues", [])
            oldkeys = dict(zip(keynames, keyvalues))
            pk_value = oldkeys.get(pk_column)
            row = ChangeRow(
                op="delete", lsn=lsn, ts=0.0, pk_column=pk_column, pk_value=pk_value,
                columns={pk_column: pk_value}, geometry_column=geometry_column,
                geometry_wkb_hex=None,
            )
        else:
            record = dict(zip(change.get("columnnames", []), change.get("columnvalues", [])))
            geom_hex = record.pop(geometry_column, None) if geometry_column else None
            row = ChangeRow(
                op=kind, lsn=lsn, ts=0.0, pk_column=pk_column,
                pk_value=record.get(pk_column), columns=record,
                geometry_column=geometry_column, geometry_wkb_hex=geom_hex,
            )
        out.append(DecodedChange(table_name=table_name, row=row))
    return out


def stream_changes(
    raw_dsn: str, *, on_message, is_flush_due, do_flush,
    should_stop=lambda: False, poll_timeout_s: float = 1.0,
) -> None:
    """Boucle jusqu'à should_stop() (par défaut : jamais — le process
    cdc-worker tourne indéfiniment). `on_message(payload, lsn)` décode et
    bufferise ; `is_flush_due()`/`do_flush()` sont rappelés à CHAQUE
    itération, message reçu ou non — c'est ce qui permet le flush par âge
    (30s) sur un flux calme. `do_flush()` retourne la LSN à confirmer (ou
    None si rien à confirmer)."""
    conn = psycopg2.connect(raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection)
    cur = conn.cursor()
    cur.start_replication(
        slot_name=SLOT_NAME,
        options={"pretty-print": "0", "include-pk": "1"},
    )
    try:
        while not should_stop():
            msg = cur.read_message()
            if msg:
                on_message(msg.payload, msg.data_start)
            if is_flush_due():
                ack_lsn = do_flush()
                if ack_lsn is not None:
                    cur.send_feedback(flush_lsn=ack_lsn, reply=True)
            if not msg:
                select.select([conn], [], [], poll_timeout_s)
    finally:
        cur.close()
        conn.close()
```

- [ ] **Step 4: Lancer le test de décodage, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_cdc_consumer.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Écrire le test d'intégration réel (marqueur `postgis`)**

Créer `core/tests/test_cdc_consumer_postgis.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import os

import pytest
from sqlalchemy import text

from app.cdc.consumer import decode_wal2json_message, ensure_replication_slot, stream_changes

pytestmark = pytest.mark.postgis


@pytest.fixture()
def cdc_table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP PUBLICATION IF EXISTS test_cdc_pub"))
        conn.execute(text("DROP TABLE IF EXISTS t_cdc_consumer"))
        conn.execute(text(
            "CREATE TABLE t_cdc_consumer (id serial PRIMARY KEY, v text)"
        ))
        conn.execute(text("CREATE PUBLICATION test_cdc_pub FOR TABLE t_cdc_consumer"))
    yield "t_cdc_consumer"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP PUBLICATION IF EXISTS test_cdc_pub"))
        conn.execute(text("DROP TABLE IF EXISTS t_cdc_consumer"))


def _raw_dsn() -> str:
    # CORE_TEST_DATABASE_URL est au format SQLAlchemy (postgresql+psycopg://) ;
    # psycopg2 attend un DSN postgresql:// nu.
    return os.environ["CORE_TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


def test_stream_changes_decodes_and_stops_on_should_stop(cdc_table, pg_engine):
    raw_dsn = _raw_dsn()
    ensure_replication_slot(raw_dsn)
    try:
        with pg_engine.begin() as conn:
            conn.execute(text(f"INSERT INTO {cdc_table} (v) VALUES ('a')"))

        received = []
        state = {"count": 0}

        def on_message(payload, lsn):
            for decoded in decode_wal2json_message(payload, lsn=lsn, collection_meta={cdc_table: ("id", None)}):
                received.append(decoded)
                state["count"] += 1

        stream_changes(
            raw_dsn, on_message=on_message,
            is_flush_due=lambda: False, do_flush=lambda: None,
            should_stop=lambda: state["count"] >= 1,
            poll_timeout_s=0.2,
        )
        assert len(received) == 1
        assert received[0].table_name == cdc_table
        assert received[0].row.op == "insert"
    finally:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(raw_dsn, connection_factory=psycopg2.extras.LogicalReplicationConnection)
        cur = conn.cursor()
        try:
            cur.drop_replication_slot("geostudio_cdc_slot")
        except Exception:
            pass
        cur.close()
        conn.close()
```

- [ ] **Step 6: Lancer le test d'intégration**

```bash
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:${PG_PASSWORD}@127.0.0.1:5432/gis" \
  uv run pytest tests/test_cdc_consumer_postgis.py -v
```

Expected: 1 passed. Si `should_stop` ne fait jamais avancer la boucle au-delà du premier `select.select` timeout (le test reste bloqué), vérifier que `wal_level=logical` est bien actif sur la base de test (Task 1, Step 3) et que le rôle utilisé a le privilège `REPLICATION` (le rôle `gis` bootstrap du conteneur `postgis` en dispose nativement en tant que superuser).

- [ ] **Step 7: Commit**

```bash
git add core/app/cdc/consumer.py core/tests/test_cdc_consumer.py core/tests/test_cdc_consumer_postgis.py
git commit -m "feat(core): SP-11a — décodage wal2json + boucle de consommation (app.cdc.consumer)"
```

---

### Task 8: Backfill (démarrage à froid + collection tardive)

**Files:**
- Create: `core/app/cdc/backfill.py`
- Test: `core/tests/test_cdc_backfill.py` (marqueur `postgis`)

**Interfaces:**
- Consumes: `app.cdc.parquet_writer.ChangeRow`.
- Produces: `current_wal_lsn(session) -> int` ; `backfill_table(session, *, table_name, pk_column, geometry_column, boundary_lsn, flush_ts) -> list[ChangeRow]`. Consommé par Task 9.

- [ ] **Step 1: Écrire le test (échoue — le module n'existe pas)**

Créer `core/tests/test_cdc_backfill.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import text

from app.cdc.backfill import backfill_table, current_wal_lsn

pytestmark = pytest.mark.postgis


@pytest.fixture()
def seeded_table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill"))
        conn.execute(text(
            "CREATE TABLE t_backfill (id serial PRIMARY KEY, v text, "
            "geom geometry(Point, 4326))"
        ))
        conn.execute(text(
            "INSERT INTO t_backfill (v, geom) VALUES "
            "('a', ST_SetSRID(ST_MakePoint(1, 1), 4326)), "
            "('b', ST_SetSRID(ST_MakePoint(2, 2), 4326))"
        ))
    yield "t_backfill"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill"))


def test_current_wal_lsn_returns_positive_int(pg_session_factory):
    with pg_session_factory() as session:
        lsn = current_wal_lsn(session)
    assert isinstance(lsn, int)
    assert lsn > 0


def test_backfill_table_reads_all_rows_as_inserts(seeded_table, pg_session_factory):
    with pg_session_factory() as session:
        boundary = current_wal_lsn(session)
        rows = backfill_table(
            session, table_name=seeded_table, pk_column="id", geometry_column="geom",
            boundary_lsn=boundary, flush_ts=42.0,
        )
    assert len(rows) == 2
    assert all(r.op == "insert" for r in rows)
    assert all(r.lsn == boundary for r in rows)
    assert all(r.ts == 42.0 for r in rows)
    assert all(r.geometry_wkb_hex is not None for r in rows)


def test_backfill_table_without_geometry_column(pg_session_factory, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill_nogeom"))
        conn.execute(text("CREATE TABLE t_backfill_nogeom (id serial PRIMARY KEY, v text)"))
        conn.execute(text("INSERT INTO t_backfill_nogeom (v) VALUES ('x')"))
    with pg_session_factory() as session:
        rows = backfill_table(
            session, table_name="t_backfill_nogeom", pk_column="id", geometry_column=None,
            boundary_lsn=1, flush_ts=0.0,
        )
    assert len(rows) == 1
    assert rows[0].geometry_wkb_hex is None
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill_nogeom"))
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:${PG_PASSWORD}@127.0.0.1:5432/gis" \
  uv run pytest tests/test_cdc_backfill.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.cdc.backfill'`.

- [ ] **Step 3: Écrire `core/app/cdc/backfill.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Backfill initial par collection (SP-11a §Flux de données/Backfill initial).

Décision de conception (ce plan, au-delà du texte de la spec) : pas
d'EXPORT_SNAPSHOT. On lit pg_current_wal_lsn() juste avant de démarrer
START_REPLICATION, puis on SELECT * chaque collection déjà enregistrée,
taguée avec cette LSN comme borne. C'est safe parce que le slot capture déjà,
depuis sa création (ou son dernier confirmed_flush_lsn sur une reprise), tout
changement WAL — un changement qui arrive entre la lecture de la LSN-frontière
et le SELECT * sera de toute façon redélivré par le flux live avec sa vraie
LSN (plus grande), qui l'emporte dans la réduction (pk, max(_lsn)) côté
lecteur : au pire quelques doublons inoffensifs, jamais de perte ni de
fantôme. Pour une collection enregistrée APRÈS que le slot existe déjà, le
même mécanisme s'applique au premier changement vu pour une table inconnue
(app.cdc.main, Task 9) — pas de notification poussée depuis apply_collection_ddl."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cdc.parquet_writer import ChangeRow
from app.collections.ddl import quote_ident


def current_wal_lsn(session: Session) -> int:
    lsn_text = session.execute(text("SELECT pg_current_wal_lsn()")).scalar()
    # pg_current_wal_lsn() renvoie "X/Y" (deux parties hexadécimales) ; les
    # LSN décodées par psycopg2 (msg.data_start) sont des entiers — même
    # espace de valeurs (pg_lsn == uint64 sur 64 bits), conversion nécessaire
    # pour comparer les deux dans la réduction max(_lsn) côté lecteur.
    hi, lo = lsn_text.split("/")
    return (int(hi, 16) << 32) + int(lo, 16)


def backfill_table(
    session: Session, *, table_name: str, pk_column: str, geometry_column: str | None,
    boundary_lsn: int, flush_ts: float,
) -> list:
    """Lit l'état courant de la table et produit des ChangeRow op="insert"
    tagués `boundary_lsn`. La colonne géométrie est lue en texte (format de
    sortie par défaut de Postgres pour le type `geometry` = hex EWKB), même
    représentation que celle produite par wal2json — aucune conversion
    supplémentaire nécessaire côté parquet_writer."""
    t = quote_ident(session, table_name)
    rows = session.execute(text(f'SELECT * FROM public.{t}')).mappings().all()
    out = []
    for r in rows:
        record = dict(r)
        geom_wkb_hex = None
        if geometry_column and record.get(geometry_column) is not None:
            geom_wkb_hex = record.pop(geometry_column)
        pk_value = record.get(pk_column)
        out.append(ChangeRow(
            op="insert", lsn=boundary_lsn, ts=flush_ts, pk_column=pk_column,
            pk_value=pk_value, columns=record, geometry_column=geometry_column,
            geometry_wkb_hex=geom_wkb_hex,
        ))
    return out
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

```bash
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:${PG_PASSWORD}@127.0.0.1:5432/gis" \
  uv run pytest tests/test_cdc_backfill.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/cdc/backfill.py core/tests/test_cdc_backfill.py
git commit -m "feat(core): SP-11a — backfill par collection sans EXPORT_SNAPSHOT (app.cdc.backfill)"
```

---

### Task 9: Point d'entrée du process `cdc-worker` (`app/cdc/main.py`)

**Files:**
- Create: `core/app/cdc/main.py`
- Test: `core/tests/test_cdc_main.py` (assemblage, sans process réel — teste `_load_collection_meta`, `_WorkerState`, la construction de la clé S3, via un stub minimal)

**Interfaces:**
- Consumes: tous les modules des Tasks 3–8 (`observability.register_cdc_lag_gauge`, `app.cdc.storage`, `app.cdc.buffer.CdcBufferManager`, `app.cdc.consumer.{ensure_replication_slot,decode_wal2json_message,stream_changes}`, `app.cdc.backfill.{current_wal_lsn,backfill_table}`, `app.cdc.parquet_writer.write_geoparquet`, `app.collections.models.Collection`, `app.db.{make_engine,make_session_factory}`).
- Produces: `run() -> None` (boucle bloquante, jamais retourne en fonctionnement normal), point d'entrée `python -m app.cdc.main`.

- [ ] **Step 1: Écrire le test de la partie testable sans process (clé S3 + métadonnées)**

Créer `core/tests/test_cdc_main.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import time

from app.cdc.main import _WorkerState, build_s3_key


def test_build_s3_key_matches_layout_convention():
    key = build_s3_key(tenant_id="acme", collection_id="parcelles", dt="2026-07-17")
    assert key.startswith("cdc/tenant_id=acme/collection_id=parcelles/dt=2026-07-17/part-")
    assert key.endswith(".parquet")


def test_worker_state_tracks_last_seen_lsn():
    state = _WorkerState()
    assert state.last_seen_lsn == 0
    state.last_seen_lsn = 42
    assert state.last_seen_lsn == 42


def test_get_lag_seconds_computes_elapsed_time_since_last_flush():
    state = _WorkerState()
    state.last_flush_ts["parcelles"] = time.time() - 5
    lag = state.get_lag_seconds()
    assert 4.5 <= lag["parcelles"] <= 6.0  # marge pour l'exécution du test elle-même
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_cdc_main.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.cdc.main'`.

- [ ] **Step 3: Écrire `core/app/cdc/main.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Point d'entrée process du worker CDC (SP-11a) — service `cdc-worker` du
compose, jamais démarré via create_app()/app.main : observability.setup()
est donc appelé ici au niveau module, même patron et même raison que
app/jobs.py (SP-10a) — quel que soit le process qui importe ce module EST le
point d'entrée du worker."""
import os
import time
import uuid

from sqlalchemy import select

from app import observability

observability.setup()

from app.cdc import backfill, consumer, storage  # noqa: E402  (après setup(), même patron que app.jobs)
from app.cdc.buffer import CdcBufferManager
from app.cdc.parquet_writer import write_geoparquet
from app.collections.models import Collection
from app.db import make_engine, make_session_factory


class _WorkerState:
    """État en mémoire du process — un seul cdc-worker à la fois, pas de
    partage entre threads/process. last_seen_lsn : LSN du dernier message
    reçu du flux (toutes tables confondues), utilisé pour borner le feedback
    via CdcBufferManager.safe_ack_lsn même quand aucun flush n'a eu lieu à
    cette itération. last_flush_ts : collection_id -> epoch du dernier flush
    GeoParquet réussi, source de la gauge geostudio.cdc.lag_seconds."""

    def __init__(self) -> None:
        self.last_seen_lsn = 0
        self.last_flush_ts: dict = {}

    def get_lag_seconds(self) -> dict:
        now = time.time()
        return {cid: now - ts for cid, ts in self.last_flush_ts.items()}


def build_s3_key(*, tenant_id: str, collection_id: str, dt: str) -> str:
    return f"cdc/tenant_id={tenant_id}/collection_id={collection_id}/dt={dt}/part-{uuid.uuid4().hex}.parquet"


def _load_collection_meta(session) -> dict:
    """table_name -> (collection_id, tenant_id, geometry_column, srid, pk_column)."""
    return {
        c.table_name: (c.id, c.tenant_id, c.geometry_column, c.srid, c.pk_column)
        for c in session.scalars(select(Collection)).all()
    }


def run() -> None:
    raw_dsn = os.environ["CDC_DATABASE_URL"]
    engine = make_engine(raw_dsn.replace("postgresql://", "postgresql+psycopg://"))
    session_factory = make_session_factory(engine)
    s3_bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    s3_client = storage.make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    storage.ensure_cdc_bucket(s3_client, s3_bucket)

    state = _WorkerState()
    observability.register_cdc_lag_gauge(state.get_lag_seconds)

    consumer.ensure_replication_slot(raw_dsn)

    buffer = CdcBufferManager()
    with session_factory() as session:
        collection_meta = _load_collection_meta(session)
        boundary_lsn = backfill.current_wal_lsn(session)
        for table_name, (_cid, _tid, geometry_column, _srid, pk_column) in collection_meta.items():
            rows = backfill.backfill_table(
                session, table_name=table_name, pk_column=pk_column,
                geometry_column=geometry_column, boundary_lsn=boundary_lsn, flush_ts=time.time(),
            )
            for row in rows:
                buffer.add(table_name, row)

    def _flush_table(table_name: str) -> None:
        collection_id, tenant_id, _geometry_column, srid, _pk_column = collection_meta[table_name]
        rows = buffer.drain(table_name, flush_ts=time.time())
        if not rows:
            return
        dt = time.strftime("%Y-%m-%d", time.gmtime())
        key = build_s3_key(tenant_id=tenant_id, collection_id=collection_id, dt=dt)
        local_path = f"/tmp/cdc-{uuid.uuid4().hex}.parquet"
        write_geoparquet(rows, srid=srid or 4326, path=local_path)
        storage.upload_parquet_file(s3_client, bucket=s3_bucket, key=key, local_path=local_path)
        os.remove(local_path)
        state.last_flush_ts[collection_id] = time.time()

    def _do_flush():
        for table_name in buffer.tables_due_for_flush():
            _flush_table(table_name)
        return buffer.safe_ack_lsn(last_seen_lsn=state.last_seen_lsn)

    def _on_message(payload: str, lsn: int) -> None:
        state.last_seen_lsn = lsn
        meta_by_table = {t: (pk, geom) for t, (_cid, _tid, geom, _srid, pk) in collection_meta.items()}
        for decoded in consumer.decode_wal2json_message(payload, lsn=lsn, collection_meta=meta_by_table):
            buffer.add(decoded.table_name, decoded.row)

        # Table publiée mais inconnue de collection_meta : collection créée
        # après le dernier chargement — backfill paresseux au premier
        # changement vu (Task 8 §Décision de conception), avant de traiter
        # le message lui-même sur la prochaine itération.
        import json
        unknown_tables = {
            change["table"] for change in json.loads(payload).get("change", [])
            if change["table"] not in collection_meta
        }
        for table_name in unknown_tables:
            with session_factory() as session:
                fresh = session.scalar(select(Collection).where(Collection.table_name == table_name))
            if fresh is None:
                continue
            collection_meta[table_name] = (fresh.id, fresh.tenant_id, fresh.geometry_column, fresh.srid, fresh.pk_column)
            with session_factory() as session:
                backfill_rows = backfill.backfill_table(
                    session, table_name=table_name, pk_column=fresh.pk_column,
                    geometry_column=fresh.geometry_column, boundary_lsn=lsn - 1, flush_ts=time.time(),
                )
            for row in backfill_rows:
                buffer.add(table_name, row)

    consumer.stream_changes(
        raw_dsn, on_message=_on_message,
        is_flush_due=lambda: bool(buffer.tables_due_for_flush()),
        do_flush=_do_flush,
    )


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_cdc_main.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Vérifier qu'aucune régression n'apparaît sur la suite complète**

```bash
cd core && uv run pytest -v 2>&1 | tail -30
```

Expected: tous les tests non-`postgis` passent (les tests `postgis` sont skippés sans `CORE_TEST_DATABASE_URL`, comportement inchangé).

- [ ] **Step 6: Commit**

```bash
git add core/app/cdc/main.py core/tests/test_cdc_main.py
git commit -m "feat(core): SP-11a — point d'entrée du process cdc-worker (app.cdc.main)"
```

---

### Task 10: Service `cdc-worker` dans `docker-compose.yml`

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: service `cdc-worker`, démarré par défaut (`docker compose up`, sans profil), connecté directement à `postgis:5432`.

- [ ] **Step 1: Ajouter le service `cdc-worker`**

Dans `docker-compose.yml`, juste après le service `worker` (avant la section `# ─── Observabilité`) :

```yaml
  # Worker CDC (SP-11a) — même image que le cœur, process séparé (arbitrage
  # A16). Connexion DIRECTE à postgis:5432, PAS à pgbouncer:6432 : PgBouncer
  # est en POOL_MODE transaction, incompatible avec le protocole de
  # réplication logique. Service métier essentiel dès que SP-11 est livré,
  # pas un outil d'exploitation optionnel — pas de profil, comme core/worker.
  cdc-worker:
    build: ./core
    command: python -m app.cdc.main
    environment:
      CDC_DATABASE_URL: postgresql://gis:${PG_PASSWORD}@postgis:5432/gis
      S3_ENDPOINT_URL: http://minio:9000
      S3_ACCESS_KEY: ${MINIO_USER}
      S3_SECRET_KEY: ${MINIO_PASSWORD}
      S3_CDC_BUCKET: geostudio-cdc
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-lgtm:4318
      OTEL_SERVICE_NAME: geostudio-cdc-worker
    networks: [gis-net]
    depends_on:
      postgis:
        condition: service_healthy
      minio:
        condition: service_healthy
    restart: unless-stopped
```

- [ ] **Step 2: Build et démarrage réel**

```bash
docker compose build cdc-worker
docker compose up -d postgis minio
docker compose up -d cdc-worker
docker compose logs -f cdc-worker
```

Expected: aucune exception au démarrage (connexion réussie, slot créé/réutilisé, boucle de consommation lancée — pas de crash-loop). Interrompre le `logs -f` une fois confirmé stable (`Ctrl-C`, ne tue pas le conteneur).

- [ ] **Step 3: Vérifier qu'un `docker compose up` par défaut (sans flag) démarre bien `cdc-worker` avec le reste**

```bash
docker compose down
docker compose up -d
docker compose ps
```

Expected: `cdc-worker` apparaît dans la liste des services `Up`, aux côtés de `core`/`worker`, sans avoir passé de `--profile`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(deploy): SP-11a — service cdc-worker (docker-compose), connexion directe à postgis"
```

---

### Task 11: Validation empirique de bout en bout (critères d'acceptation)

**Files:** aucun fichier de code — validation manuelle scriptée contre la stack réelle, documentée dans le rapport d'exécution.

**Interfaces:** aucune — cette task vérifie les 5 critères d'acceptation de la spec contre le système assemblé par les Tasks 1–10.

- [ ] **Step 1: Écriture visible en < 5 min, suppression comprise (critère 1)**

```bash
docker compose up -d
# Créer une collection de test via l'API OGC Features (ou via le widget
# Formulaire du shell) — exemple direct API, en supposant une collection
# "demo_points" déjà enregistrée avec une colonne géométrie :
curl -X POST http://localhost:8200/collections/demo_points/items \
  -H "Content-Type: application/geo+json" \
  -d '{"type":"Feature","geometry":{"type":"Point","coordinates":[2.3,48.8]},"properties":{"titre":"test-sp11a"}}'
```

Attendre jusqu'à 5 minutes (le flush par âge du buffer, 30s, devrait être largement suffisant en pratique), puis :

```bash
docker compose exec minio mc alias set local http://localhost:9000 "$MINIO_USER" "$MINIO_PASSWORD"
docker compose exec minio mc ls --recursive local/geostudio-cdc/cdc/
```

Expected: un fichier `part-*.parquet` apparaît sous `tenant_id=.../collection_id=demo_points/dt=<aujourd'hui>/` en moins de 5 minutes. Lire son contenu :

```bash
docker compose exec minio mc cp local/geostudio-cdc/cdc/.../part-XXXX.parquet /tmp/part.parquet
python3 -c "
import geopandas as gpd
gdf = gpd.read_parquet('/tmp/part.parquet')
print(gdf[['_op', '_lsn', '_ts', 'titre']])
"
```

Expected: une ligne `_op="insert"`, `titre="test-sp11a"`. Puis supprimer l'entité :

```bash
curl -X DELETE http://localhost:8200/collections/demo_points/items/<id>
```

Attendre le prochain flush, télécharger le nouveau fichier, confirmer une ligne `_op="delete"` avec seulement la PK renseignée (pas de colonne `titre`).

- [ ] **Step 2: Collection enregistrée après démarrage, backfillée puis suivie (critère 2)**

Avec `cdc-worker` déjà up depuis un moment, enregistrer une **nouvelle** collection (admin, via `POST /collections` ou l'UI d'administration SP-9), avec des lignes déjà présentes dans la table PostGIS candidate avant l'enregistrement. Écrire une nouvelle feature dans cette collection juste après l'enregistrement pour déclencher le mécanisme de backfill paresseux (Task 8/9 §Décision de conception). Vérifier dans MinIO que le fichier GeoParquet produit contient à la fois les lignes préexistantes (backfill, `_lsn` = frontière) et la nouvelle ligne (`_lsn` > frontière).

- [ ] **Step 3: Redémarrage sans perte après arrêt brutal (critère 3)**

```bash
# Écrire plusieurs features rapidement, puis tuer le worker AVANT le prochain flush (30s) :
docker compose kill -9 cdc-worker
docker compose up -d cdc-worker
docker compose logs cdc-worker | tail -50
```

Expected : au redémarrage, le worker recrée sa connexion sur le même slot (`ensure_replication_slot` idempotent) et les changements écrits avant le kill (non encore flushés, donc jamais ackés) réapparaissent dans le flux et finissent flushés — vérifier dans MinIO que TOUTES les features écrites avant le kill sont présentes dans un fichier GeoParquet (au pire dupliquées entre deux fichiers, jamais absentes).

- [ ] **Step 4: Gauge exportée par collection (critère 4)**

```bash
docker compose --profile observability up -d otel-lgtm
# (cdc-worker exporte déjà en OTLP inconditionnel, cf. Task 10 — pas de redémarrage nécessaire)
```

Ouvrir Grafana (`http://localhost:3001`), Explore → Prometheus, requête `geostudio_cdc_lag_seconds` — confirmer une série par `collection_id` suivi, valeur cohérente (quelques secondes à quelques dizaines de secondes selon le rythme des flushs).

- [ ] **Step 5: `docker compose up` par défaut inchangé pour le reste de la stack (critère 5)**

```bash
docker compose down
docker compose up -d
docker compose ps
```

Expected : `core`, `worker`, `shell`, `postgis`, `minio`, `martin`, `titiler`, `keycloak`, `traefik`, `pgbouncer` tous `Up` comme avant cette branche — `cdc-worker` en plus, sans qu'aucun autre service n'ait changé de comportement. Lancer la suite E2E complète pour confirmer l'absence de régression shell :

```bash
cd shell && npm run e2e
```

Expected : 37/37 specs vertes (aucune modification shell dans ce plan — ce test confirme simplement l'absence d'effet de bord).

- [ ] **Step 6: Documenter les résultats dans le rapport d'exécution**

Consigner, pour chaque critère 1–5 : PASS/FAIL, les valeurs mesurées (temps de latence observé, contenu des fichiers GeoParquet inspectés), et tout écart empirique trouvé par rapport à ce plan (signatures psycopg2 ajustées au Step 6 de Task 1, comportement du backfill tardif, etc.) — même patron que les rapports d'exécution SP-6b/SP-9/SP-10b déjà présents dans ce dépôt.
