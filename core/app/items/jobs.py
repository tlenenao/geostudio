# SPDX-License-Identifier: Apache-2.0
"""Job d'embedding d'un item (SP-7) — recalcule embedding après chaque
create/update (app.items.routes), asynchrone (jamais de blocage de
l'écriture sur un fournisseur d'embeddings lent/indisponible). Échec
= log, embedding reste NULL, l'item reste cherchable par trigram seul
(dégradation gracieuse, spec §Pipeline d'embedding)."""
import logging
import os

from sqlalchemy import select

from app.db import make_engine, make_session_factory, request_scoped_session
from app.items.models import Item
from app.jobs import app
from app.search.providers import get_embedding_provider

logger = logging.getLogger(__name__)


def _embed_text(item: Item) -> str:
    return f"{item.title}\n{item.abstract}\n{', '.join(item.keywords or [])}"


@app.task(queue="search")
def embed_item_task(item_id: str, tenant_id: str) -> None:
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    session_factory = make_session_factory(engine)
    try:
        with request_scoped_session(session_factory) as session:
            item = session.scalar(
                select(Item).where(Item.id == item_id, Item.tenant_id == tenant_id)
            )
            if item is None:
                logger.warning("embed_item_task: item %s introuvable (tenant %s)", item_id, tenant_id)
                return
            provider = get_embedding_provider()
            item.embedding = provider.embed(_embed_text(item))
    except Exception:
        logger.exception("embed_item_task: échec du calcul d'embedding pour l'item %s", item_id)
