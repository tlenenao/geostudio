// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import { csvAvailable, downloadCsv, geojsonDownloadUrl } from "../lib/datasetDownload";

// Plain slate styling (not --gs-* theme vars): this component is reused both
// inside a themed AppRenderer (DatasetCard widget) and outside any theme root
// (DatasetPage's chrome) — see SP-16c plan Task 5 notes.
export function DatasetDownloadButtons({
  collectionId,
  featureCount,
}: {
  collectionId: string;
  featureCount: number | null;
}) {
  const client = useItemClient();
  const schemaQuery = useQuery({
    queryKey: ["dataset-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId),
  });
  const available = csvAvailable(featureCount);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <a
        className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 no-underline hover:bg-slate-100"
        href={geojsonDownloadUrl(client, collectionId)}
        download={`${collectionId}.geojson`}
      >
        Télécharger GeoJSON
      </a>
      <button
        type="button"
        className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={!available || !schemaQuery.data}
        onClick={() => {
          if (!schemaQuery.data || featureCount === null) return;
          void downloadCsv({ client, collectionId, schema: schemaQuery.data, featureCount });
        }}
      >
        Télécharger CSV
      </button>
      {!available && (
        <p className="w-full text-[10px] text-slate-500">
          Jeu de données trop volumineux pour l'export CSV navigateur — export serveur à venir (SP-15).
        </p>
      )}
    </div>
  );
}
