import type { WcWidgetManifest } from "./manifest";

export function makeGeneratedPropsPanel(manifest: WcWidgetManifest) {
  return function GeneratedPropsPanel({
    props,
    onChange,
  }: {
    props: Record<string, unknown>;
    onChange: (props: Record<string, unknown>) => void;
  }) {
    return (
      <div className="flex flex-col gap-2 text-sm">
        {manifest.props.map((p) => (
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
        ))}
      </div>
    );
  };
}
