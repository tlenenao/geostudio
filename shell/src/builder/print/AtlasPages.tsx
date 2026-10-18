// SPDX-License-Identifier: Apache-2.0
// ARC-30 : rendu d'atlas pour le worker d'export — une page (saut de page CSS)
// par entité de la source `atlas.dataSourceId`, plafonnée à `maxPages` ; avec
// `entityId`, une seule fiche (ARC-26). Signale `data-export-ready` une fois
// les pages dans le DOM.
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../../api/ItemClientProvider";
import type { AtlasConfig, DataSource } from "../../api/types";
import { markExportReady } from "../../shell/exportReady";
import { LoadingState } from "../../ui/kit/LoadingState";
import { t } from "../../i18n";
import "../../i18n/domains/widgets";
import { EntityFiche } from "./EntityFiche";

export function AtlasPages({
  atlas,
  dataSources,
  entityId,
}: {
  atlas: AtlasConfig;
  dataSources: DataSource[];
  entityId?: string;
}) {
  const client = useItemClient();
  const source = dataSources.find((s) => s.id === atlas.dataSourceId);
  const query = useQuery({
    queryKey: ["atlas", atlas.dataSourceId, atlas.maxPages, atlas.sortBy ?? null, entityId ?? null],
    // AUD-057 : le plafond et le tri sont poussés au cœur (jamais « tout lire puis couper »,
    // et sans tri l'ordre des pages n'était pas reproductible). Une fiche seule lit la source.
    queryFn: async () => {
      const bounded =
        entityId === undefined && source
          ? {
              ...source,
              query: {
                ...source.query,
                limit: atlas.maxPages,
                ...(atlas.sortBy ? { sortby: atlas.sortBy } : {}),
              },
            }
          : (source as DataSource);
      if (client.queryDataSourcePage) return client.queryDataSourcePage(bounded);
      return { records: await client.queryDataSource(bounded), total: null };
    },
    enabled: Boolean(source),
  });
  const total = query.data?.total ?? null;
  const records = (query.data?.records ?? [])
    .filter((r) => entityId === undefined || String(r.id) === entityId)
    .slice(0, atlas.maxPages);
  const done = query.isSuccess || query.isError || !source;
  useEffect(() => {
    if (done) requestAnimationFrame(() => markExportReady());
  }, [done]);
  if (!source || query.isError) {
    return (
      <p role="alert" className="p-4 text-sm text-danger">
        {t("atlas.sourceError")}
      </p>
    );
  }
  if (!query.isSuccess) return <LoadingState />;
  return (
    <div>
      {entityId === undefined && total !== null && total > records.length ? (
        <p role="status" data-atlas-truncated className="p-2 text-sm text-warn">
          {t("atlas.truncated", { shown: records.length, total })}
        </p>
      ) : null}
      {records.map((r) => (
        <section key={String(r.id)} data-atlas-page className="break-after-page">
          <EntityFiche
            record={r}
            {...(atlas.titleTemplate ? { titleTemplate: atlas.titleTemplate } : {})}
            fields={atlas.fields}
          />
        </section>
      ))}
    </div>
  );
}
