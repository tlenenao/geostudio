# SPDX-License-Identifier: Apache-2.0
"""Gèle les DataSources "features" d'une config app/dashboard en
"static" (query.records embarqués) — même mécanisme in-process que
app/mcp/tools.py (introspect_table + select_features sous rls_scope), jamais
un self-call HTTP. Le mode Statique n'a alors plus besoin d'aucun réseau au
runtime : ItemClient.queryDataSource traite déjà "static" en local
(shell/src/api/itemClient.ts, branche existante, inchangée).

select_features() ne pose ni rôle ni tenant lui-même (voir
app/features/repository.py's docstring) : chaque table de collection porte
une policy RLS Postgres `USING (tenant_id = current_setting('app.tenant_id'))`
(app/collections/ddl.py's apply_collection_ddl). Sans rls_scope(), la lecture
échouerait (current_setting jamais posé) ou, pire, verrait un tenant
incorrect selon l'état résiduel de la session — même piège déjà documenté
par app/mcp/tools.py:266-267, reproduit ici à l'identique."""

from app.collections import repository as collections_repo
from app.collections.introspection_pg import introspect_table
from app.configs.schemas import BuilderConfig, DataSource
from app.features.repository import select_features
from app.features.rls import rls_scope


def freeze_config(
    session,
    *,
    tenant_id: str,
    config: BuilderConfig,
    max_records_per_source: int = 50_000,
) -> BuilderConfig:
    frozen_sources: list[DataSource] = []
    for source in config.dataSources:
        if source.type != "features":
            frozen_sources.append(source)
            continue
        col = collections_repo.get_collection(
            session, tenant_id=tenant_id, collection_id=source.layer
        )
        info = introspect_table(session, col.table_name)
        records: list[dict] = []
        offset = 0
        page_size = 1000
        with rls_scope(session, tenant_id):
            while len(records) < max_records_per_source:
                page = select_features(
                    session,
                    info,
                    limit=page_size,
                    offset=offset,
                    bbox=None,
                    geom_intersects=None,
                    filters=None,
                )
                records.extend(page.features)
                if len(page.features) < page_size:
                    break
                offset += page_size
        frozen_sources.append(
            DataSource(
                id=source.id,
                type="static",
                service=source.service,
                layer=source.layer,
                query={**source.query, "records": records[:max_records_per_source]},
            )
        )
    return config.model_copy(update={"dataSources": frozen_sources})
