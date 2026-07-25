// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useDatasetConfig, useItem, useSaveDataset, useUpdateItem } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { DatasetColumnMeta, DatasetConfig } from "../api/types";
import { mergeDatasetSchema } from "../lib/datasetSchema";
import { MetadataForm } from "../ui/MetadataForm";
import { Button } from "../ui/button";

export function DatasetEditPage({ pk }: { pk: string }) {
  const itemQuery = useItem(pk);
  const configQuery = useDatasetConfig(pk);
  const save = useSaveDataset(pk);
  const updateItem = useUpdateItem(pk);
  const client = useItemClient();
  const [draft, setDraft] = useState<DatasetConfig | null>(null);

  useEffect(() => {
    if (configQuery.data) setDraft((d) => d ?? configQuery.data);
  }, [configQuery.data]);

  const schemaQuery = useQuery({
    queryKey: ["collection-schema", draft?.collectionId],
    queryFn: () => client.getCollectionSchema(draft!.collectionId),
    enabled: Boolean(draft?.collectionId),
  });

  if (itemQuery.isLoading || configQuery.isLoading || (!draft && !configQuery.isError))
    return <p role="status">Chargement…</p>;
  if (itemQuery.isError || configQuery.isError || !draft || !itemQuery.data)
    return (
      <p role="alert" className="text-sm text-red-600">
        Dataset introuvable.
      </p>
    );

  function setColumn(name: string, patch: DatasetColumnMeta) {
    setDraft((d) => (d ? { ...d, columns: { ...d.columns, [name]: { ...d.columns[name], ...patch } } } : d));
  }

  const merged = schemaQuery.data ? mergeDatasetSchema(schemaQuery.data, draft.columns) : [];

  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="text-xl font-semibold">Dataset partagé — {itemQuery.data.title}</h2>
      <MetadataForm
        initial={{ title: itemQuery.data.title, abstract: itemQuery.data.abstract, keywords: itemQuery.data.keywords ?? [] }}
        onSubmit={(v) => updateItem.mutate(v)}
        onCancel={() => {}}
        pending={updateItem.isPending}
      />
      <div>
        <p className="mb-1 text-xs font-medium text-slate-500">Colonnes</p>
        {schemaQuery.isLoading && <p role="status">Chargement du schéma…</p>}
        {schemaQuery.isError && (
          <p role="alert" className="text-sm text-red-600">
            Collection source introuvable.
          </p>
        )}
        {merged.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500">
                <th className="p-1">Colonne</th>
                <th className="p-1">Libellé</th>
                <th className="p-1">Description</th>
                <th className="p-1">Format</th>
              </tr>
            </thead>
            <tbody>
              {merged.map((f) => (
                <tr key={f.name} className="border-t border-slate-200">
                  <td className="p-1 font-mono text-xs">{f.name}</td>
                  <td className="p-1">
                    <input aria-label={`Libellé de ${f.name}`} className="h-8 w-full rounded border border-slate-300 px-2 text-xs"
                      value={f.label ?? ""} onChange={(e) => setColumn(f.name, { label: e.target.value })} />
                  </td>
                  <td className="p-1">
                    <input aria-label={`Description de ${f.name}`} className="h-8 w-full rounded border border-slate-300 px-2 text-xs"
                      value={f.description ?? ""} onChange={(e) => setColumn(f.name, { description: e.target.value })} />
                  </td>
                  <td className="p-1">
                    <input aria-label={`Format de ${f.name}`} className="h-8 w-full rounded border border-slate-300 px-2 text-xs"
                      value={f.format ?? ""} onChange={(e) => setColumn(f.name, { format: e.target.value })} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <Button size="sm" className="w-fit" disabled={save.isPending} onClick={() => save.mutate(draft)}>
        Enregistrer les colonnes
      </Button>
      {save.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec de l'enregistrement.
        </p>
      )}
    </div>
  );
}
