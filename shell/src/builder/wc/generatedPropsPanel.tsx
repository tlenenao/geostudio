import type { DataSource } from "../../api/types";
import { DataSourceSelect } from "../DataSourceSelect";
import type { WcWidgetManifest } from "./manifest";

// Filtre d'autorat, pas une frontière de sécurité : n'affecte que les sources
// proposées dans ce panneau. Le module WC arbitraire chargé par l'extension
// peut appeler n'importe quelle collection permise par le token du visiteur —
// la frontière réelle reste can()/RLS côté cœur, inchangée.
function permittedDataSources(dataSources: DataSource[], manifest: WcWidgetManifest): DataSource[] {
  const perm = manifest.permissions;
  if (!perm || perm.collections === "all") return dataSources;
  const allowed = new Set(perm.collections);
  return dataSources.filter((ds) => allowed.has(ds.layer));
}

export function makeGeneratedPropsPanel(manifest: WcWidgetManifest) {
  return function GeneratedPropsPanel({
    props,
    dataSources = [],
    onChange,
  }: {
    props: Record<string, unknown>;
    dataSources?: DataSource[];
    onChange: (props: Record<string, unknown>) => void;
  }) {
    return (
      <div className="flex flex-col gap-2 text-sm">
        {manifest.props.map((p) =>
          p.type === "dataSource" ? (
            <DataSourceSelect
              key={p.name}
              value={String(props[p.name] ?? "")}
              dataSources={permittedDataSources(dataSources, manifest)}
              onChange={(id) => onChange({ ...props, [p.name]: id })}
            />
          ) : (
            <label key={p.name} className="flex flex-col gap-1">
              {p.label}
              {p.type === "boolean" ? (
                <input
                  type="checkbox"
                  aria-label={p.label}
                  checked={Boolean(props[p.name])}
                  onChange={(e) => onChange({ ...props, [p.name]: e.target.checked })}
                />
              ) : (
                <input
                  type={p.type === "number" ? "number" : "text"}
                  aria-label={p.label}
                  className="h-9 rounded-md border border-slate-300 px-2"
                  value={String(props[p.name] ?? "")}
                  onChange={(e) =>
                    onChange({
                      ...props,
                      [p.name]: p.type === "number" ? Number(e.target.value) : e.target.value,
                    })
                  }
                />
              )}
            </label>
          ),
        )}
      </div>
    );
  };
}
