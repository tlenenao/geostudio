// SPDX-License-Identifier: Apache-2.0
import type { Page } from "../api/types";

export function PageManager({
  pages,
  activePageId,
  onChange,
  onSelectPage,
}: {
  pages: Page[];
  activePageId: string;
  onChange: (pages: Page[]) => void;
  onSelectPage: (pageId: string) => void;
}) {
  function addPage() {
    const newPage: Page = {
      id: crypto.randomUUID(),
      name: `Page ${pages.length + 1}`,
      layout: { type: "grid", breakpoints: {}, items: [] },
    };
    onChange([...pages, newPage]);
    onSelectPage(newPage.id);
  }
  function remove(id: string) {
    if (pages.length <= 1) return;
    const next = pages.filter((p) => p.id !== id);
    onChange(next);
    if (activePageId === id) onSelectPage(next[0].id);
  }
  function rename(id: string, name: string) {
    onChange(pages.map((p) => (p.id === id ? { ...p, name } : p)));
  }
  function move(id: string, dir: -1 | 1) {
    const i = pages.findIndex((p) => p.id === id);
    const j = i + dir;
    if (j < 0 || j >= pages.length) return;
    const next = [...pages];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  }
  return (
    <ul className="flex flex-col gap-1">
      {pages.map((p, i) => (
        <li
          key={p.id}
          className={`flex items-center gap-1 rounded border p-1 text-xs ${p.id === activePageId ? "border-blue-500" : "border-slate-200"}`}
        >
          <button type="button" aria-label={`Ouvrir la page ${p.id}`} className="flex-1 truncate text-left" onClick={() => onSelectPage(p.id)}>
            {p.name}
          </button>
          <input
            aria-label={`Renommer la page ${p.id}`}
            className="w-16 rounded border border-slate-300 px-1"
            value={p.name}
            onChange={(e) => rename(p.id, e.target.value)}
          />
          <button type="button" aria-label={`Monter la page ${p.id}`} disabled={i === 0} className="disabled:opacity-30" onClick={() => move(p.id, -1)}>↑</button>
          <button type="button" aria-label={`Descendre la page ${p.id}`} disabled={i === pages.length - 1} className="disabled:opacity-30" onClick={() => move(p.id, 1)}>↓</button>
          <button type="button" aria-label={`Retirer la page ${p.id}`} disabled={pages.length <= 1} className="text-red-600 disabled:opacity-30" onClick={() => remove(p.id)}>✕</button>
        </li>
      ))}
      <li>
        <button type="button" className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-100" onClick={addPage}>
          Ajouter une page
        </button>
      </li>
    </ul>
  );
}
