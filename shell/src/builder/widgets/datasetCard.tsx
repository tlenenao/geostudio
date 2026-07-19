// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { DatasetDownloadButtons } from "../DatasetDownloadButtons";
import { useItemClient } from "../../api/ItemClientProvider";

export function registerDatasetCardWidget(): void {
  registerWidget({
    type: "datasetCard",
    label: "Fiche jeu de données",
    defaultProps: { dataSourceId: "", showDownload: true, title: "" },
    defaultSize: { w: 4, h: 4 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect
          value={String(props.dataSourceId ?? "")}
          dataSources={dataSources.filter((s) => s.type === "features")}
          onChange={(id) => onChange({ ...props, dataSourceId: id })}
        />
        <label className="flex flex-col gap-1">Titre (optionnel)
          <input aria-label="Titre (optionnel)" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.title ?? "")} onChange={(e) => onChange({ ...props, title: e.target.value })} />
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" aria-label="Afficher le téléchargement" checked={props.showDownload !== false}
            onChange={(e) => onChange({ ...props, showDownload: e.target.checked })} />
          Afficher le téléchargement
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const client = useItemClient();
      const collectionId = ctx.data?.layer;
      const query = useQuery({
        queryKey: ["dataset-card", collectionId],
        queryFn: () => client.getCollection(collectionId!),
        enabled: Boolean(collectionId),
      });

      if (!collectionId) {
        return <p className="text-xs text-[var(--gs-color-muted)]">Aucune source de données sélectionnée</p>;
      }
      if (query.isLoading) {
        return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      }
      if (query.isError || !query.data) {
        return <p role="alert" className="text-xs text-[var(--gs-color-muted)]">Jeu de données introuvable</p>;
      }
      const col = query.data;
      const showDownload = props.showDownload !== false;
      return (
        <div className="flex h-full flex-col gap-2 rounded-[var(--gs-radius)] border border-[var(--gs-color-border)] bg-[var(--gs-color-surface)] p-4">
          <h3 className="text-sm font-semibold text-[var(--gs-color-text)]">{String(props.title || col.title)}</h3>
          <p className="text-xs text-[var(--gs-color-muted)]">{col.description}</p>
          <p className="text-xs text-[var(--gs-color-muted)]">{col.featureCount ?? 0} entités</p>
          <a
            className="text-sm font-medium text-[var(--gs-color-primary)] underline"
            href={`/public/datasets/${collectionId}`}
          >
            Voir le jeu de données
          </a>
          {showDownload && <DatasetDownloadButtons collectionId={collectionId} featureCount={col.featureCount} />}
        </div>
      );
    },
  });
}
