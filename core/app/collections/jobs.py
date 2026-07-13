"""Job d'embedding d'une collection (SP-7) — même patron que
app.items.jobs.embed_item_task."""
import logging
import os

from sqlalchemy import select

from app.collections.models import Collection
from app.db import make_engine, make_session_factory, request_scoped_session
from app.jobs import app
from app.search.providers import get_embedding_provider

logger = logging.getLogger(__name__)


def _embed_text(col: Collection) -> str:
    return f"{col.title}\n{col.description}"


@app.task(queue="search")
def embed_collection_task(collection_id: str, tenant_id: str) -> None:
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    session_factory = make_session_factory(engine)
    try:
        with request_scoped_session(session_factory) as session:
            col = session.scalar(
                select(Collection).where(
                    Collection.id == collection_id, Collection.tenant_id == tenant_id
                )
            )
            if col is None:
                logger.warning(
                    "embed_collection_task: collection %s introuvable (tenant %s)",
                    collection_id, tenant_id,
                )
                return
            provider = get_embedding_provider()
            col.embedding = provider.embed(_embed_text(col))
    except Exception:
        logger.exception(
            "embed_collection_task: échec du calcul d'embedding pour %s", collection_id
        )
