# SPDX-License-Identifier: Apache-2.0
"""REV-322 : purge du lac CDC (bucket CDC, préfixe `cdc/`) d'une collection ou
d'un tenant — partitions `dt=*` ET `snapshot/`. Dans app.analytics (couche la
plus basse) pour être importable par app.collections et app.compliance."""

from typing import Any

from botocore.exceptions import ClientError

_DELETE_MAX_KEYS = 1000  # limite dure de DeleteObjects


def lake_prefix(tenant_id: str, collection_id: str | None = None) -> str:
    """Même layout que app.cdc.main.build_s3_key / app.analytics.snapshot."""
    base = f"cdc/tenant_id={tenant_id}/"
    return base if collection_id is None else f"{base}collection_id={collection_id}/"


def purge_prefix(client: Any, *, bucket: str, prefix: str) -> int:
    """Supprime tout objet sous `prefix`. Relit depuis le début après chaque
    lot supprimé (la liste rétrécit, pas de jeton). Bucket absent (CDC jamais
    activé) = rien à purger."""
    total = 0
    while True:
        try:
            page = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchBucket":
                return total
            raise
        keys = [o["Key"] for o in page.get("Contents", [])]
        if not keys:
            return total
        for i in range(0, len(keys), _DELETE_MAX_KEYS):
            chunk = keys[i : i + _DELETE_MAX_KEYS]
            client.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in chunk]})
        total += len(keys)
