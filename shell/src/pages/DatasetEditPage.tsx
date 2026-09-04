// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  useDatasetConfig,
  useItem,
  useItems,
  useMetadataCatalog,
  useSaveDataset,
  useUpdateItem,
} from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { CrossFilterLink, DatasetColumnMeta, DatasetConfig } from "../api/types";
import { mergeDatasetSchema } from "../lib/datasetSchema";
import { MetadataForm } from "../ui/MetadataForm";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { CrossFilterLinkEditor } from "../builder/CrossFilterLinkEditor";
import { AlertRuleEditor } from "../builder/AlertRuleEditor";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

export function DatasetEditPage({ pk }: { pk: string }) {
  const itemQuery = useItem(pk);
  const configQuery = useDatasetConfig(pk);
  const save = useSaveDataset(pk);
  const updateItem = useUpdateItem(pk);
  const catalogQuery = useMetadataCatalog();
  const client = useItemClient();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<DatasetConfig | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportingFormat, setExportingFormat] = useState<string | null>(null);

  useEffect(() => {
    if (configQuery.data) setDraft((d) => d ?? configQuery.data);
  }, [configQuery.data]);

  const draftCollectionId = draft && draft.source === "collection" ? draft.collectionId : undefined;
  const schemaQuery = useQuery({
    queryKey: ["collection-schema", draftCollectionId],
    queryFn: () => client.getCollectionSchema(draftCollectionId!),
    enabled: Boolean(draftCollectionId),
  });
  const otherDatasetsQuery = useItems({ type: "dataset", pageSize: 100 });

  if (itemQuery.isLoading || configQuery.isLoading || (!draft && !configQuery.isError))
    return <p role="status">Chargement…</p>;
  if (itemQuery.isError || configQuery.isError || !draft || !itemQuery.data)
    return (
      <p role="alert" className="text-sm text-danger">
        Dataset partagé introuvable.
      </p>
    );

  const item = itemQuery.data;

  function setColumn(name: string, patch: DatasetColumnMeta) {
    setDraft((d) =>
      d ? { ...d, columns: { ...d.columns, [name]: { ...d.columns[name], ...patch } } } : d,
    );
  }

  const targetOptions = (otherDatasetsQuery.data?.items ?? [])
    .filter((d) => d.pk !== pk)
    .map((d) => ({ pk: d.pk, title: d.title }));

  function addCrossFilterLink() {
    setDraft((d) =>
      d
        ? {
            ...d,
            crossFilterLinks: [
              ...(d.crossFilterLinks ?? []),
              { targetDatasetId: "", mode: "attribute" as const, sourceField: "", targetField: "" },
            ],
          }
        : d,
    );
  }
  function updateCrossFilterLink(index: number, next: CrossFilterLink) {
    setDraft((d) => {
      if (!d) return d;
      const links = [...(d.crossFilterLinks ?? [])];
      links[index] = next;
      return { ...d, crossFilterLinks: links };
    });
  }
  function removeCrossFilterLink(index: number) {
    setDraft((d) => {
      if (!d) return d;
      const links = (d.crossFilterLinks ?? []).filter((_, i) => i !== index);
      return { ...d, crossFilterLinks: links };
    });
  }

  const merged = schemaQuery.data ? mergeDatasetSchema(schemaQuery.data, draft.columns) : [];

  const hasGeometry = draft.source === "arcgis" ? true : Boolean(schemaQuery.data?.geometry);
  const exportFormats = hasGeometry ? ["csv", "xlsx", "geojson", "gpkg"] : ["csv", "xlsx"];

  async function handleExport(format: string) {
    const source = {
      id: "__dataset-export__",
      type: "features" as const,
      service: "core",
      layer: "",
      datasetId: pk,
      query: {},
    };
    setExportError(null);
    setExportingFormat(format);
    try {
      const { blob, filename } = await client.exportDataSource(source, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Échec de l'export.");
    } finally {
      setExportingFormat(null);
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="dataset"
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
              <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs text-ink-2">
                <dt>Type</dt>
                <dd>Dataset</dd>
                <dt>Modifié</dt>
                <dd>{item.date || "—"}</dd>
              </dl>
            </Panel>
          ),
        }}
        work={{
          id: "dataset",
          label: "Dataset",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h2 className="text-xl font-semibold text-ink">Dataset partagé — {item.title}</h2>
              <MetadataForm
                initial={{
                  title: item.title,
                  abstract: item.abstract,
                  keywords: item.keywords ?? [],
                  license: item.license,
                  language: item.language,
                }}
                licenses={catalogQuery.data?.licenses ?? []}
                languages={catalogQuery.data?.languages ?? []}
                onSubmit={(v) => updateItem.mutate(v)}
                onCancel={() => {}}
                pending={updateItem.isPending}
              />
              <div>
                <p className="mb-1 text-xs font-medium text-ink-2">Colonnes</p>
                {schemaQuery.isLoading && <p role="status">Chargement du schéma…</p>}
                {schemaQuery.isError && (
                  <p role="alert" className="text-sm text-danger">
                    Collection source introuvable.
                  </p>
                )}
                {merged.length > 0 && (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-ink-2">
                        <th className="p-1">Colonne</th>
                        <th className="p-1">Libellé</th>
                        <th className="p-1">Description</th>
                        <th className="p-1">Format</th>
                      </tr>
                    </thead>
                    <tbody>
                      {merged.map((f) => (
                        <tr key={f.name} className="border-t border-rule">
                          <td className="p-1 font-mono text-xs">{f.name}</td>
                          <td className="p-1">
                            <input
                              aria-label={`Libellé de ${f.name}`}
                              className="h-8 w-full rounded border border-rule bg-surface px-2 text-xs text-ink"
                              value={f.label ?? ""}
                              onChange={(e) => setColumn(f.name, { label: e.target.value })}
                            />
                          </td>
                          <td className="p-1">
                            <input
                              aria-label={`Description de ${f.name}`}
                              className="h-8 w-full rounded border border-rule bg-surface px-2 text-xs text-ink"
                              value={f.description ?? ""}
                              onChange={(e) => setColumn(f.name, { description: e.target.value })}
                            />
                          </td>
                          <td className="p-1">
                            <input
                              aria-label={`Format de ${f.name}`}
                              className="h-8 w-full rounded border border-rule bg-surface px-2 text-xs text-ink"
                              value={f.format ?? ""}
                              onChange={(e) => setColumn(f.name, { format: e.target.value })}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <label className="mt-2 flex flex-col gap-1 text-xs">
                  Colonne temporelle
                  <select
                    aria-label="Colonne temporelle"
                    className="h-8 w-full rounded border border-rule bg-surface px-2 text-xs text-ink"
                    value={draft.timeField ?? ""}
                    onChange={(e) =>
                      setDraft((d) => (d ? { ...d, timeField: e.target.value || null } : d))
                    }
                  >
                    <option value="">— aucune —</option>
                    {merged.map((f) => (
                      <option key={f.name} value={f.name}>
                        {f.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    aria-label="Réagir au déplacement de la carte"
                    checked={Boolean(draft.reactsToExtent)}
                    onChange={(e) =>
                      setDraft((d) => (d ? { ...d, reactsToExtent: e.target.checked } : d))
                    }
                  />
                  Réagir au déplacement de la carte
                </label>
                <div className="mt-2 flex flex-col gap-2">
                  <p className="text-xs font-medium text-ink-2">Liens cross-filter</p>
                  {(draft.crossFilterLinks ?? []).map((link, i) => (
                    <CrossFilterLinkEditor
                      key={i}
                      link={link}
                      sourceFields={merged.map((f) => f.name)}
                      targetOptions={targetOptions}
                      onChange={(next) => updateCrossFilterLink(i, next)}
                      onRemove={() => removeCrossFilterLink(i)}
                    />
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="w-fit"
                    onClick={addCrossFilterLink}
                  >
                    Ajouter un lien
                  </Button>
                </div>
              </div>
            </div>
          ),
        }}
        inspect={{
          id: "settings",
          label: "Réglages",
          content: (
            <div className="flex flex-col gap-4 p-3">
              <div className="flex flex-col gap-2">
                <p className="text-xs font-medium text-ink-2">Export</p>
                <div className="flex gap-2">
                  {exportFormats.map((format) => (
                    <button
                      key={format}
                      type="button"
                      aria-label={`Exporter en ${format.toUpperCase()}`}
                      disabled={exportingFormat === format}
                      className="rounded border border-rule px-2 py-1 text-xs text-ink hover:bg-sunken disabled:opacity-50"
                      onClick={() => void handleExport(format)}
                    >
                      {format.toUpperCase()}
                    </button>
                  ))}
                </div>
                {exportError && (
                  <p role="alert" className="text-sm text-danger">
                    {exportError}
                  </p>
                )}
              </div>
              <AlertRuleEditor datasetItemId={pk} owner={item.owner} />
              <ConfigHistoryPanel
                pk={pk}
                currentVersion={null}
                onRestored={async () => setDraft(await client.getDatasetConfig(pk))}
              />
              {draft.sourcePipelineId && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="w-fit"
                  onClick={() => navigate(`/datasets/visual-query/${draft.sourcePipelineId}/edit`)}
                >
                  Modifier la requête
                </Button>
              )}
              <Button
                size="sm"
                className="w-fit"
                disabled={save.isPending}
                onClick={() => save.mutate(draft)}
              >
                Enregistrer les colonnes
              </Button>
              {save.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec de l'enregistrement.
                </p>
              )}
            </div>
          ),
        }}
      />
    </div>
  );
}
