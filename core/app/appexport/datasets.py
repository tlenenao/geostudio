# SPDX-License-Identifier: Apache-2.0
"""AUD-003 : une DataSource liée à un dataset (`datasetId`, `layer=""`) est
résolue vers la collection du dataset avant garde/gel/snapshot — jamais de
lecture de `source.layer` brut dans appexport. Même règle que
app.configs.guest_access.resolve_guest_scope (cloisonnement tenant via
get_access_facts). Idempotent."""

from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo


def resolve_dataset_sources(
    session: Session, *, tenant_id: str, config: BuilderConfig
) -> tuple[BuilderConfig, list[str]]:
    reasons: list[str] = []
    sources = []
    for source in config.dataSources:
        if source.type not in ("features", "statistics") or not source.datasetId:
            sources.append(source)
            continue
        facts = items_repo.get_access_facts(session, tenant_id=tenant_id, item_id=source.datasetId)
        ds = configs_repo.get_config_by_item(session, source.datasetId) if facts else None
        payload = ds.config.dataset if ds is not None and ds.kind == "dataset" else None
        if payload is None:
            reasons.append(f"source '{source.id}' : dataset '{source.datasetId}' introuvable")
            sources.append(source)
        elif payload.source != "collection" or not payload.collectionId:
            reasons.append(
                f"source '{source.id}' : l'export ne supporte que les datasets adossés "
                "à une collection (dataset SQL/pipeline/ArcGIS non exportable)"
            )
            sources.append(source)
        else:
            sources.append(
                source.model_copy(update={"layer": payload.collectionId, "datasetId": None})
            )
    return config.model_copy(update={"dataSources": sources}), reasons
