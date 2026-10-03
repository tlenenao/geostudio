// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import {
  GEOJSON_DOWNLOAD_LIMIT,
  csvAvailable,
  csvTooLarge,
  downloadCsv,
  geojsonDownloadUrl,
  geojsonTruncated,
} from "../lib/datasetDownload";
import { t } from "../i18n";

// Tokens sémantiques --gs-* globaux (tokens.css, importé sans condition
// par index.css) — pas les variables --gs-color-* propres au Theme d'une
// app (builder/theme.ts, posées uniquement sur le conteneur racine
// d'AppRenderer). Ce composant est réutilisé à la fois dans un
// AppRenderer thémé (widget DatasetCard) et hors de toute racine de thème
// (chrome de DatasetPage) : ces deux jeux de variables sont distincts et
// ne se recouvrent pas, donc les tokens sémantiques du studio (text-ink-2,
// border-rule, bg-sunken…) résolvent correctement dans les deux contextes.
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
        className="rounded-md border border-rule px-3 py-1.5 text-xs font-medium text-ink-2 no-underline hover:bg-sunken"
        href={geojsonDownloadUrl(client, collectionId)}
        download={`${collectionId}.geojson`}
      >
        {t("datasetDownload.geojsonButton")}
      </a>
      <button
        type="button"
        className="rounded-md border border-rule px-3 py-1.5 text-xs font-medium text-ink-2 hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-50"
        disabled={!available || !schemaQuery.data}
        onClick={() => {
          if (!schemaQuery.data || featureCount === null) return;
          void downloadCsv({ client, collectionId, schema: schemaQuery.data, featureCount });
        }}
      >
        {t("datasetDownload.csvButton")}
      </button>
      {geojsonTruncated(featureCount) && (
        <p className="w-full text-xs text-ink-3">
          {t("datasetDownload.geojsonTruncated", {
            count: GEOJSON_DOWNLOAD_LIMIT,
            total: featureCount ?? 0,
          })}
        </p>
      )}
      {csvTooLarge(featureCount) && (
        <p className="w-full text-xs text-ink-3">{t("datasetDownload.tooLarge")}</p>
      )}
    </div>
  );
}
