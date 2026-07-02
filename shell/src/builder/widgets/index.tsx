import { registerWidget } from "../registry";

export function registerBuiltinWidgets(): void {
  registerWidget({
    type: "text",
    label: "Texte",
    defaultProps: { text: "Nouveau texte" },
    defaultSize: { w: 4, h: 2 },
    PropsPanel: ({ props, onChange }) => (
      <label className="flex flex-col gap-1 text-sm">
        Texte
        <textarea
          aria-label="Texte du widget"
          className="rounded-md border border-slate-300 p-2 text-sm"
          value={String(props.text ?? "")}
          onChange={(e) => onChange({ ...props, text: e.target.value })}
        />
      </label>
    ),
    Component: ({ props }) => <p className="whitespace-pre-wrap">{String(props.text ?? "")}</p>,
  });

  registerWidget({
    type: "image",
    label: "Image",
    defaultProps: { src: "", alt: "" },
    defaultSize: { w: 4, h: 4 },
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          URL
          <input
            aria-label="URL de l'image"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.src ?? "")}
            onChange={(e) => onChange({ ...props, src: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          Texte alternatif
          <input
            aria-label="Texte alternatif"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.alt ?? "")}
            onChange={(e) => onChange({ ...props, alt: e.target.value })}
          />
        </label>
      </div>
    ),
    Component: ({ props }) =>
      props.src ? (
        <img className="h-full w-full object-cover" src={String(props.src)} alt={String(props.alt ?? "")} />
      ) : (
        <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">
          Image
        </div>
      ),
  });

  registerWidget({
    type: "button",
    label: "Bouton",
    defaultProps: { label: "Bouton", href: "" },
    defaultSize: { w: 2, h: 1 },
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          Libellé
          <input
            aria-label="Libellé du bouton"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")}
            onChange={(e) => onChange({ ...props, label: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          Lien
          <input
            aria-label="Lien du bouton"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.href ?? "")}
            onChange={(e) => onChange({ ...props, href: e.target.value })}
          />
        </label>
      </div>
    ),
    Component: ({ props }) => (
      <button
        type="button"
        className="rounded-md bg-slate-800 px-3 py-1.5 text-sm text-white"
        onClick={() => {
          const href = String(props.href ?? "");
          if (href) window.open(href, "_blank", "noopener");
        }}
      >
        {String(props.label ?? "Bouton")}
      </button>
    ),
  });
}
