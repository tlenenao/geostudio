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
    queryKey: ["atlas", atlas.dataSourceId],
    queryFn: () => client.queryDataSource(source as DataSource),
    enabled: Boolean(source),
  });
  const records = (query.data ?? [])
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
