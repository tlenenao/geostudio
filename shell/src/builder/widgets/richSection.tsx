// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";
import { sanitizeMarkdown } from "./sanitizeMarkdown";

export function registerRichSectionWidget(): void {
  registerWidget({
    type: "richSection",
    label: "Section riche",
    defaultProps: { markdown: "" },
    defaultSize: { w: 12, h: 4 },
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          Markdown
          <textarea
            aria-label="Markdown"
            className="rounded-md border border-slate-300 p-2 font-mono text-xs"
            rows={8}
            value={String(props.markdown ?? "")}
            onChange={(e) => onChange({ ...props, markdown: e.target.value })}
          />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const markdown = String(props.markdown ?? "");
      if (!markdown.trim()) {
        return ctx.mode === "edit" ? (
          <p className="text-xs text-[var(--gs-color-muted)]">
            Section de texte vide — ajoutez du Markdown dans le panneau de propriétés.
          </p>
        ) : null;
      }
      const html = sanitizeMarkdown(markdown);
      return <div className="prose max-w-none text-[var(--gs-color-text)]" dangerouslySetInnerHTML={{ __html: html }} />;
    },
  });
}
