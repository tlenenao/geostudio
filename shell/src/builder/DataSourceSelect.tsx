import type { DataSource } from "../api/types";

export function DataSourceSelect({
  value,
  dataSources,
  onChange,
}: {
  value: string;
  dataSources: DataSource[];
  onChange: (id: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      Source de données
      <select
        aria-label="Source de données"
        className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Aucune</option>
        {dataSources.map((s) => (
          <option key={s.id} value={s.id}>{s.layer || s.id}</option>
        ))}
      </select>
    </label>
  );
}
