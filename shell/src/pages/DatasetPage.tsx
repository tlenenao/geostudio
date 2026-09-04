// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { DatasetDownloadButtons } from "../builder/DatasetDownloadButtons";
import type { AppConfig } from "../api/types";

registerBuiltinWidgets();

// Synthesized in memory, never persisted — the read-only preview reuses the
// single AppRenderer(config, "runtime") runtime (A31), never a bespoke
// map/table pairing.
function previewConfig(collectionId: string, attachmentField: string | undefined): AppConfig {
  const dataSourceId = "dataset-preview";
  return {
    kind: "app",
    theme: {},
    dataSources: [
      { id: dataSourceId, type: "features", service: "core", layer: collectionId, query: {} },
    ],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "dataset-preview-map",
          widget: "map",
          x: 0,
          y: 0,
          w: 6,
          h: 6,
          props: {
            dataSourceId,
            ...(attachmentField ? { popup: { attachmentField } } : {}),
          },
        },
        {
          id: "dataset-preview-table",
          widget: "table",
          x: 6,
          y: 0,
          w: 6,
          h: 6,
          props: { dataSourceId, columns: [], pageSize: 10 },
        },
      ],
    },
  };
}

export function DatasetPage({ collectionId }: { collectionId: string }) {
  const client = useItemClient();
  const query = useQuery({
    queryKey: ["public-dataset", collectionId],
    queryFn: () => client.getCollection(collectionId),
    retry: false,
  });
  // Non bloquant à dessein (pas de garde `isLoading` supplémentaire, cf.
  // spec §3.4) : tant que le schéma n'a pas résolu, `attachmentField` reste
  // `undefined` et le popup se comporte comme avant SP-40.
  const schemaQuery = useQuery({
    queryKey: ["public-dataset-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId),
    retry: false,
  });
  const attachmentField = schemaQuery.data?.fields.find((f) => f.type === "attachment")?.name;

  if (query.isLoading) {
    return <p role="status">Chargement…</p>;
  }
  if (query.isError || !query.data) {
    return (
      <div className="p-8 text-center">
        <p role="alert" className="text-sm text-slate-600">
          Jeu de données introuvable.
        </p>
      </div>
    );
  }
  const col = query.data;
  return (
    <div className="flex h-full w-full flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-slate-900">{col.title}</h1>
        <p className="text-sm text-slate-600">{col.description}</p>
        <p className="text-xs text-slate-500">{col.featureCount ?? 0} entités</p>
      </header>
      <DatasetDownloadButtons collectionId={collectionId} featureCount={col.featureCount} />
      <div className="h-[480px] w-full">
        <AppRenderer config={previewConfig(collectionId, attachmentField)} mode="runtime" />
      </div>
    </div>
  );
}
