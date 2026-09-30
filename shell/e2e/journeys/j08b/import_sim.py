"""Appelle run_import (le corps du job d'ingestion) avec des quotas d'items/collections saturés.

Lancé par docker exec -i ... python - <tenant> <user_id> <titre> : affiche un JSON avec les
compteurs avant/après et les limites d'environnement.
"""
import json
import os
import sys

from app.db import make_engine, make_session_factory
from app.ingestion.importer import run_import
from app.quotas.service import count_collections_for_tenant, count_items_for_tenant

tenant, user_id, title = sys.argv[1:4]
sf = make_session_factory(make_engine(os.environ["DATABASE_URL"]))
with sf() as s:
    items0 = count_items_for_tenant(s, tenant)
    cols0 = count_collections_for_tenant(s, tenant)
    os.environ["CORE_QUOTAS_ENABLED"] = "true"
    os.environ["CORE_QUOTA_MAX_ITEMS_PER_TENANT"] = str(items0)
    os.environ["CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT"] = str(cols0)
    res = run_import(
        s,
        tenant_id=tenant,
        created_by=user_id,
        filename="quota.csv",
        content=b"nom,lat,lon\nA,45.1,1.5\nB,45.2,1.6\n",
        collection_title=title,
        lat_field="lat",
        lon_field="lon",
    )
    s.commit()
    print(
        json.dumps(
            {
                "items_before": items0,
                "items_after": count_items_for_tenant(s, tenant),
                "collections_before": cols0,
                "collections_after": count_collections_for_tenant(s, tenant),
                "limit_items": os.environ["CORE_QUOTA_MAX_ITEMS_PER_TENANT"],
                "limit_collections": os.environ["CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT"],
            }
        )
    )
