# SPDX-License-Identifier: Apache-2.0
"""Job d'embedding d'un item (SP-7) — recalcule embedding après chaque
create/update (app.items.routes), asynchrone (jamais de blocage de
l'écriture sur un fournisseur d'embeddings lent/indisponible). Échec
= log, embedding reste NULL, l'item reste cherchable par trigram seul
(dégradation gracieuse, spec §Pipeline d'embedding)."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import request_scoped_session
from app.items.models import Item
from app.jobs import app
from app.jobs.engine import session_factory as common_session_factory
from app.search.providers import get_embedding_provider

logger = logging.getLogger(__name__)


def _embed_text(item: Item) -> str:
    return f"{item.title}\n{item.abstract}\n{', '.join(item.keywords or [])}"


@app.task(queue="search")
def embed_item_task(item_id: str, tenant_id: str) -> None:
    session_factory = common_session_factory()
    try:
        with request_scoped_session(session_factory) as session:
            item = session.scalar(
                select(Item).where(Item.id == item_id, Item.tenant_id == tenant_id)
            )
            if item is None:
                logger.warning(
                    "embed_item_task: item %s introuvable (tenant %s)", item_id, tenant_id
                )
                return
            provider = get_embedding_provider()
            item.embedding = provider.embed(_embed_text(item))
    except Exception:
        logger.exception("embed_item_task: échec du calcul d'embedding pour l'item %s", item_id)


_SWEEP_BATCH = 100
_SWEEP_GRACE = timedelta(minutes=10)


@app.periodic(cron="*/15 * * * *")
@app.task(queue="search", queueing_lock="sweep_missing_embeddings_task")
def sweep_missing_embeddings_task(timestamp: int) -> None:
    """REV-346 : re-défère l'embedding des items restés sans vecteur (defer perdu, worker
    tué, fournisseur en panne), au-delà d'un délai de grâce. Balayage borné, plus récents
    d'abord.
    # ponytail: un item en échec permanent (>100) peut affamer les plus anciens."""
    factory = common_session_factory()
    cutoff = datetime.now(UTC).replace(tzinfo=None) - _SWEEP_GRACE
    with request_scoped_session(factory) as session:
        rows = session.execute(
            select(Item.id, Item.tenant_id)
            .where(Item.embedding.is_(None), Item.updated_at < cutoff)
            .order_by(Item.updated_at.desc())
            .limit(_SWEEP_BATCH)
        ).all()
    for item_id, tenant_id in rows:
        embed_item_task.defer(item_id=item_id, tenant_id=tenant_id)
