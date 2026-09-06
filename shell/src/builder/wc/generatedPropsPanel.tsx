// SPDX-License-Identifier: Apache-2.0
import type { DataSource } from "../../api/types";
import { DataSourceSelect } from "../DataSourceSelect";
import type { WcWidgetManifest } from "./manifest";
import { t } from "../../i18n";

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

// Détecte un binding déjà écrit qui pointe vers une source devenue hors
// périmètre (permissions resserrées après coup, config écrite par MCP en
// contournant permittedDataSources() ci-dessus, widget copié depuis un autre
// AppConfig) : le <select> se retrouve avec une value sans <option>
// correspondante, silencieusement. GAP-49.
function boundOutsidePermissions(
  value: string,
  dataSources: DataSource[],
  manifest: WcWidgetManifest,
): boolean {
  const perm = manifest.permissions;
  if (!perm || perm.collections === "all" || !value) return false;
  const source = dataSources.find((ds) => ds.id === value);
  if (!source) return false;
  return !new Set(perm.collections).has(source.layer);
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
            <div key={p.name} className="flex flex-col gap-1">
              <DataSourceSelect
                value={String(props[p.name] ?? "")}
                dataSources={permittedDataSources(dataSources, manifest)}
                onChange={(id) => onChange({ ...props, [p.name]: id })}
              />
              {boundOutsidePermissions(String(props[p.name] ?? ""), dataSources, manifest) && (
                <p role="alert" className="text-xs text-danger">
                  {t("generatedPropsPanel.outOfPermissions")}
                </p>
              )}
            </div>
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
