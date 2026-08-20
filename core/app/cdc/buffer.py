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
