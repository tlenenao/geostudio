"""Rattrapage de l'emprise spatiale (SP-55 §2.5, GAP-06) pour les items
`map` créés avant ce SP : leur config n'a jamais été réécrite depuis, donc
`recompute_item_bbox` (câblé dans app.configs.repository.create_config/
update_config/rollback_config) ne s'est jamais exécuté pour eux. Idempotent,
rejouable sans effet de bord — recalcule la même valeur si rien n'a changé.

Usage : DATABASE_URL=postgresql+psycopg://… uv run python -m scripts.backfill_item_bbox
"""

import os

from app.configs.bbox import recompute_item_bbox
from app.configs.repository import list_configs_by_kind
from app.db import make_engine, make_session_factory
from app.items.models import Item


def backfill(session) -> int:
    updated = 0
    for item_id, tenant_id, config in list_configs_by_kind(session, "map"):
        item = session.get(Item, item_id)
        if item is None:
            continue
        recompute_item_bbox(session, item=item, config=config, tenant_id=tenant_id)
        updated += 1
    session.commit()
    return updated


def main() -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    Session = make_session_factory(engine)
    with Session() as session:
        count = backfill(session)
    print(f"bbox recalculée pour {count} item(s) map")


if __name__ == "__main__":
    main()
