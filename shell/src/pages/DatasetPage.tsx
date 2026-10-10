// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../ui/kit/Button";
import { CollectionProfilePanel } from "./CollectionProfilePanel";
import { useItemClient } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { DatasetDownloadButtons } from "../builder/DatasetDownloadButtons";
import type { AppConfig } from "../api/types";
import { plural, t } from "../i18n";
import { PublicNotFound } from "./PublicNotFound";
import { useDocumentMeta } from "../shell/useDocumentMeta";
import { LoadingState } from "../ui/kit/LoadingState";
import { PageTitle } from "../ui/kit/PageTitle";

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
          ordinal: 1,
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
          ordinal: 1,
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
  const [exploring, setExploring] = useState(false);
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

  // Titre/description/canonical dérivés de la collection (P35.04) ; introuvable
  // = noindex. Appelé avant les retours anticipés (règle des Hooks).
  const notFound = query.isError || (query.isSuccess && !query.data);
  useDocumentMeta({
    title: notFound ? t("datasetPage.notFound") : (query.data?.title ?? t("docTitle.appName")),
    noindex: notFound,
    description: query.data?.description ?? "",
    canonicalUrl: `${window.location.origin}/public/datasets/${encodeURIComponent(collectionId)}`,
  });

  if (query.isLoading) {
    return <LoadingState />;
  }
  if (query.isError || !query.data) {
    return <PublicNotFound message={t("datasetPage.notFound")} />;
  }
  const col = query.data;
  return (
    <main className="flex h-full w-full flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <PageTitle>{col.title}</PageTitle>
        <p className="text-sm text-ink-2">{col.description}</p>
        <p className="text-xs text-ink-3">
          {(() => {
            const n = col.featureCount ?? 0;
            return t(plural(n, "datasetPage.featureCountOne", "datasetPage.featureCountMany"), {
              n,
            });
          })()}
        </p>
      </header>
      <div className="flex flex-wrap items-center gap-2">
        <DatasetDownloadButtons collectionId={collectionId} featureCount={col.featureCount} />
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-expanded={exploring}
          aria-controls="dataset-profile-panel"
          onClick={() => setExploring((v) => !v)}
        >
          {t("datasetProfile.toggle")}
        </Button>
      </div>
      {exploring ? (
        <CollectionProfilePanel collectionId={collectionId} id="dataset-profile-panel" />
      ) : null}
      <div className="h-[480px] w-full">
        <AppRenderer config={previewConfig(collectionId, attachmentField)} mode="runtime" />
      </div>
    </main>
  );
}
