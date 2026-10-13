# SPDX-License-Identifier: Apache-2.0
"""Points de reprise d'un run de pipeline (ARC-K2/F5).

Les vues DuckDB d'un run vivent dans une connexion `:memory:` perdue avec le
processus : pour « reprendre depuis le nœud en échec » sans rejouer les nœuds
déjà réussis, chaque nœud non-writer d'un pipeline qui porte une politique
`retry` écrit sa sortie en Parquet sous `<base>/<run_racine>/<nœud>.parquet`,
avec un `manifest.json` (SRID, curseur incrémental en attente, empreinte de la
config). La reprise relit ces fichiers à la place de rejouer le nœud.

Garde-fous :
- empreinte de config : une config modifiée entre l'échec et la reprise
  invalide tous les points de reprise (rejeu complet) ;
- rétention bornée (`CORE_PIPELINE_CHECKPOINT_RETENTION_HOURS`, 24 h) purgée
  par le balayage cron ; supprimés dès la réussite du run ;
- le répertoire du run est le SEUL ajouté à `allowed_directories` de DuckDB.
# ponytail: disque LOCAL du worker — une reprise exécutée par un autre worker
# (autre hôte) ne trouve pas les fichiers et rejoue tout ; S3 si multi-worker."""

import hashlib
import json
import os
import shutil
import tempfile
import time
from typing import Any

from app.sql_ident import quote_ident_duckdb as _qi


def base_dir() -> str:
    return os.environ.get("CORE_PIPELINE_CHECKPOINT_DIR") or os.path.join(
        tempfile.gettempdir(), "geostudio-pipeline-checkpoints"
    )


def _retention_s() -> float:
    return float(os.environ.get("CORE_PIPELINE_CHECKPOINT_RETENTION_HOURS") or 24) * 3600


def config_fingerprint(payload) -> str:
    """Empreinte des nœuds+arêtes (params déjà résolus) : change dès qu'un nœud change."""
    raw = json.dumps(
        {
            "nodes": [
                n.model_dump(mode="json", exclude={"x", "y", "title"}) for n in payload.nodes
            ],
            "edges": [e.model_dump(mode="json", by_alias=True) for e in payload.edges],
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def exists(root_run_id: str) -> bool:
    return os.path.isfile(os.path.join(base_dir(), root_run_id, "manifest.json"))


def discard(root_run_id: str) -> None:
    shutil.rmtree(os.path.join(base_dir(), root_run_id), ignore_errors=True)


def purge_expired() -> int:
    """Supprime les répertoires plus vieux que la rétention (balayage cron)."""
    root = base_dir()
    if not os.path.isdir(root):
        return 0
    n = 0
    limit = time.time() - _retention_s()
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if os.path.isdir(path) and os.path.getmtime(path) < limit:
            shutil.rmtree(path, ignore_errors=True)
            n += 1
    return n


class Checkpoint:
    """Points de reprise d'UN run racine ; `fingerprint` = empreinte de la config courante."""

    def __init__(self, root_run_id: str, fingerprint: str) -> None:
        self.dir = os.path.join(base_dir(), root_run_id)
        self.fingerprint = fingerprint
        os.makedirs(self.dir, exist_ok=True)
        self._manifest: dict[str, Any] = {"fingerprint": fingerprint, "nodes": {}}
        self.usable = False  # des points de reprise valides pour CETTE config existent
        path = os.path.join(self.dir, "manifest.json")
        if os.path.isfile(path):
            try:
                with open(path) as fh:
                    loaded = json.load(fh)
            except (OSError, ValueError):
                loaded = {}
            if loaded.get("fingerprint") == fingerprint:
                self._manifest = loaded
                self.usable = True
            else:  # config modifiée : rien de réutilisable, on repart de zéro
                for f in os.listdir(self.dir):
                    os.remove(os.path.join(self.dir, f))

    def has(self, node_id: str) -> bool:
        return self.usable and node_id in self._manifest["nodes"]

    def srid(self, node_id: str) -> int:
        return int(self._manifest["nodes"][node_id]["srid"])

    def cursors(self, node_id: str) -> dict:
        return self._manifest["nodes"][node_id].get("cursors") or {}

    def _file(self, node_id: str) -> str:
        # Nom dérivé d'un hash : jamais le node_id brut dans un chemin.
        return os.path.join(self.dir, f"{hashlib.sha1(node_id.encode()).hexdigest()}.parquet")

    def _ql(self, path: str) -> str:
        return "'" + path.replace("'", "''") + "'"

    def save(self, conn, node_id: str, view: str, srid: int, cursors: dict | None = None) -> None:
        tmp = self._file(node_id) + ".tmp"
        conn.execute(f"COPY (SELECT * FROM {_qi(view)}) TO {self._ql(tmp)} (FORMAT PARQUET)")
        os.replace(tmp, self._file(node_id))
        self._manifest["nodes"][node_id] = {"srid": srid, "cursors": cursors or {}}
        mtmp = os.path.join(self.dir, "manifest.json.tmp")
        with open(mtmp, "w") as fh:
            json.dump(self._manifest, fh)
        os.replace(mtmp, os.path.join(self.dir, "manifest.json"))

    def load(self, conn, node_id: str, view: str) -> int:
        src = self._ql(self._file(node_id))
        conn.execute(f"CREATE TEMP VIEW {_qi(view)} AS SELECT * FROM read_parquet({src})")
        return self.srid(node_id)
