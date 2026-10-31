# SPDX-License-Identifier: Apache-2.0
"""Flux SSE de la cloche de notifications (L13 / D7, AUD-131).

Sans état de process côté données (ADR 0019) : chaque tick relit l'état en base
(compte de non-lues + dernière notification) dans une session éphémère, donc
n'importe quel réplica sert n'importe quel client et la reconnexion est
gratuite. Ni LISTEN/NOTIFY (inutilisable derrière PgBouncer en transaction) ni
file en mémoire. Le flux se ferme de lui-même après `STREAM_LIFETIME_S` : le
client se reconnecte (jeton renouvelé, session OIDC revérifiée), et le sondage
de 45 s du shell reste le repli si le flux est coupé (proxy, plafond atteint).
"""

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import contextmanager

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import db
from app.notifications.models import Notification
from app.notifications.repository import count_unread_notifications, get_notification_preference

POLL_INTERVAL_S = 5.0
STREAM_LIFETIME_S = 55.0
MAX_STREAMS_PER_USER = 3
MAX_STREAMS_PER_TENANT = 200

# ponytail: baux datés par process (garde de ressource, pas un état métier) : ils
# expirent seuls, sans `release` à fuiter si le client part avant le 1er octet.
# Plafond effectif = N réplicas x limite ; partager via Postgres si ça compte.
_lock = threading.Lock()
_leases: dict[tuple[str, str], list[float]] = {}  # (tenant, user) -> échéances


def try_acquire(tenant_id: str, user_id: str) -> bool:
    now = time.monotonic()
    with _lock:
        for key in list(_leases):
            _leases[key] = [t for t in _leases[key] if t > now]
            if not _leases[key]:
                del _leases[key]
        mine = _leases.get((tenant_id, user_id), [])
        tenant_total = sum(len(v) for (t, _), v in _leases.items() if t == tenant_id)
        if len(mine) >= MAX_STREAMS_PER_USER or tenant_total >= MAX_STREAMS_PER_TENANT:
            return False
        _leases.setdefault((tenant_id, user_id), []).append(now + STREAM_LIFETIME_S + 5)
        return True


def _snapshot(session: Session, tenant_id: str, user_id: str) -> tuple[int, str | None]:
    preference = get_notification_preference(session, tenant_id=tenant_id, user_id=user_id)
    unread = count_unread_notifications(
        session, tenant_id=tenant_id, recipient_user_id=user_id, preference=preference
    )
    latest = None
    if preference != "none":
        latest = session.scalar(
            select(func.max(Notification.created_at)).where(
                Notification.tenant_id == tenant_id,
                Notification.recipient_user_id == user_id,
            )
        )
    return unread, latest.isoformat() if latest is not None else None


async def event_stream(request: Request, tenant_id: str, user_id: str) -> AsyncIterator[str]:
    # Session de l'application (surchargeable en test), ouverte le temps d'un tick.
    dep: Callable = request.app.dependency_overrides.get(db.get_session, db.get_session)
    session_scope = contextmanager(dep)

    def read() -> tuple[int, str | None]:
        with session_scope() as session:
            return _snapshot(session, tenant_id, user_id)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + STREAM_LIFETIME_S
    last: tuple[int, str | None] | None = None
    yield "retry: 5000\n\n"
    first = True  # au moins un tick : une base lente ne doit pas produire un flux vide
    while first or (loop.time() < deadline and not await request.is_disconnected()):
        first = False
        state = await run_in_threadpool(read)
        if state != last:  # premier tick = synchronisation initiale
            last = state
            yield f"event: notifications\ndata: {json.dumps({'unread': state[0]})}\n\n"
        else:
            yield ": ping\n\n"
        await asyncio.sleep(POLL_INTERVAL_S)
