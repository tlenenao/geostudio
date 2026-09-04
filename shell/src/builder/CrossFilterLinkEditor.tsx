// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useDatasetConfig } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { CrossFilterLink } from "../api/types";

export function CrossFilterLinkEditor({
  link,
  sourceFields,
  targetOptions,
  onChange,
  onRemove,
}: {
  link: CrossFilterLink;
  sourceFields: string[];
  targetOptions: { pk: string; title: string }[];
  onChange: (next: CrossFilterLink) => void;
  onRemove: () => void;
}) {
  const client = useItemClient();
  const targetConfigQuery = useDatasetConfig(link.targetDatasetId, {
    enabled: Boolean(link.targetDatasetId),
  });
  const targetCollectionId =
    targetConfigQuery.data && targetConfigQuery.data.source === "collection"
      ? targetConfigQuery.data.collectionId
      : undefined;
  const targetSchemaQuery = useQuery({
    queryKey: ["collection-schema", targetCollectionId],
    queryFn: () => client.getCollectionSchema(targetCollectionId!),
    enabled: Boolean(targetCollectionId),
  });
  const targetHasGeometry = Boolean(targetSchemaQuery.data?.geometry);
  const targetFields =
    targetSchemaQuery.data?.fields.filter((f) => f.type !== "attachment").map((f) => f.name) ?? [];

  function changeMode(mode: "attribute" | "spatial") {
    onChange(
      mode === "attribute"
        ? {
            targetDatasetId: link.targetDatasetId,
            mode: "attribute",
            sourceField: "",
            targetField: "",
          }
        : { targetDatasetId: link.targetDatasetId, mode: "spatial", precision: "bbox" },
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded border border-rule p-2 text-xs">
      <label className="flex flex-col gap-1">
        Dataset cible
        <select
          aria-label="Dataset cible"
          className="h-8 rounded border border-rule bg-surface px-2 text-ink"
          value={link.targetDatasetId}
          onChange={(e) => onChange({ ...link, targetDatasetId: e.target.value })}
        >
          <option value="">— choisir —</option>
          {targetOptions.map((d) => (
            <option key={d.pk} value={d.pk}>
              {d.title}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        Mode du lien
        <select
          aria-label="Mode du lien"
          className="h-8 rounded border border-rule bg-surface px-2 text-ink"
          value={link.mode}
          onChange={(e) => changeMode(e.target.value as "attribute" | "spatial")}
        >
          <option value="attribute">Attribut partagé</option>
          <option value="spatial">Spatial</option>
        </select>
      </label>
      {link.mode === "attribute" ? (
        <>
          <label className="flex flex-col gap-1">
            Champ source
            <select
              aria-label="Champ source"
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={link.sourceField}
              onChange={(e) => onChange({ ...link, sourceField: e.target.value })}
            >
              <option value="">— choisir —</option>
              {sourceFields.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            Champ cible
            <select
              aria-label="Champ cible"
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={link.targetField}
              onChange={(e) => onChange({ ...link, targetField: e.target.value })}
            >
              <option value="">— choisir —</option>
              {targetFields.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </label>
        </>
      ) : (
        targetHasGeometry && (
          <label className="flex flex-col gap-1">
            Précision spatiale du lien
            <select
              aria-label="Précision spatiale du lien"
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={link.precision}
              onChange={(e) => onChange({ ...link, precision: e.target.value as "bbox" | "exact" })}
            >
              <option value="bbox">Emprise (rapide)</option>
              <option value="exact">Intersection exacte</option>
            </select>
          </label>
        )
      )}
      <button type="button" className="self-start text-danger underline" onClick={onRemove}>
        Supprimer le lien
      </button>
    </div>
  );
}
