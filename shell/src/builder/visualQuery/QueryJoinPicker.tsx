// SPDX-License-Identifier: Apache-2.0
import type { CollectionSchema } from "../../api/types";
import { JoinConfig } from "./inferSchema";

export function QueryJoinPicker({
  baseSchema, joinedSchema, collections, value, onChange,
}: {
  baseSchema: CollectionSchema; joinedSchema: CollectionSchema | null;
  collections: { id: string; title: string }[];
  value: JoinConfig; onChange: (next: JoinConfig) => void;
}) {
  const baseNames = new Set(baseSchema.fields.map((f) => f.name));
  const commonColumns = joinedSchema ? joinedSchema.fields.filter((f) => baseNames.has(f.name)) : [];

  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1 text-xs">
        Collection à joindre
        <select
          aria-label="Collection à joindre"
          className="h-8 rounded border border-slate-300 px-2 text-xs"
          value={value.collectionId}
          onChange={(e) => onChange({ ...value, collectionId: e.target.value, on: "" })}
        >
          <option value="">Choisir…</option>
          {collections.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
      </label>
      {joinedSchema && commonColumns.length === 0 && (
        <p className="text-xs text-red-600">
          Aucune colonne commune entre les deux collections — la jointure est impossible.
        </p>
      )}
      {commonColumns.length > 0 && (
        <label className="flex flex-col gap-1 text-xs">
          Colonne de jointure
          <select
            aria-label="Colonne de jointure"
            className="h-8 rounded border border-slate-300 px-2 text-xs"
            value={value.on}
            onChange={(e) => onChange({ ...value, on: e.target.value })}
          >
            <option value="">Choisir…</option>
            {commonColumns.map((f) => <option key={f.name} value={f.name}>{f.name}</option>)}
          </select>
        </label>
      )}
      <label className="flex flex-col gap-1 text-xs">
        Type de jointure
        <select
          aria-label="Type de jointure"
          className="h-8 rounded border border-slate-300 px-2 text-xs"
          value={value.how}
          onChange={(e) => onChange({ ...value, how: e.target.value as "inner" | "left" })}
        >
          <option value="inner">Garder seulement les correspondances</option>
          <option value="left">Garder toutes les lignes de base</option>
        </select>
      </label>
    </div>
  );
}
