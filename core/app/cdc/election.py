# SPDX-License-Identifier: Apache-2.0
"""Élection du cdc-worker actif (ARC-32) par verrou consultatif Postgres de session.

N process `cdc-worker` peuvent tourner ; un seul tient le verrou et consomme le slot, les autres
attendent en boucle. Le verrou vit avec la connexion : si le leader meurt (kill, réseau, bascule
de base), Postgres le libère et un suiveur le prend au prochain sondage (< `poll_s`). Un leader
dont la connexion de garde tombe sort du process (`on_lost`) plutôt que de continuer à consommer
sans verrou — le superviseur (compose `restart`, kubelet) relance un candidat."""

import hashlib
import logging
import os
import threading
import time
from collections.abc import Callable

import psycopg

logger = logging.getLogger(__name__)

# Clé bigint stable dérivée d'un nom (pas de collision avec les verrous procrastinate/Alembic).
LOCK_KEY = int.from_bytes(hashlib.sha256(b"geostudio.cdc-worker.leader").digest()[:8], "big") >> 1


def acquire_leadership(
    dsn: str,
    *,
    poll_s: float = 2.0,
    should_stop: Callable[[], bool] = lambda: False,
    key: int = LOCK_KEY,
) -> psycopg.Connection | None:
    """Bloque jusqu'à détenir le verrou ; renvoie la connexion de garde (à garder ouverte),
    ou None si `should_stop()` devient vrai avant."""
    announced = False
    while not should_stop():
        conn = None
        try:
            conn = psycopg.connect(dsn, autocommit=True, connect_timeout=5)
            if conn.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()[0]:  # type: ignore[index]
                logger.info("cdc-worker : leader élu")
                return conn
            conn.close()
            if not announced:
                logger.info("cdc-worker : suiveur (un autre process est leader)")
                announced = True
        except psycopg.Error:
            logger.warning("cdc-worker : élection impossible, nouvel essai", exc_info=True)
            if conn is not None:
                conn.close()
        time.sleep(poll_s)
    return None


def watch_leadership(
    conn: psycopg.Connection,
    *,
    on_lost: Callable[[], None] = lambda: os._exit(1),
    interval_s: float = 3.0,
) -> threading.Thread:
    """Sonde la connexion de garde ; sur échec, le verrou est perdu -> `on_lost()`."""

    def _loop() -> None:
        while True:
            time.sleep(interval_s)
            try:
                conn.execute("SELECT 1")
            except psycopg.Error:
                logger.error("cdc-worker : verrou de leader perdu, arrêt")
                on_lost()
                return

    thread = threading.Thread(target=_loop, name="cdc-leader-watch", daemon=True)
    thread.start()
    return thread
