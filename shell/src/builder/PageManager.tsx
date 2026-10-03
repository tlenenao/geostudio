// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import type { Page } from "../api/types";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { t } from "../i18n";
import { Input } from "../ui/kit/Input";
import { Button } from "../ui/kit/Button";

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
  const [removing, setRemoving] = useState<Page | null>(null);
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
    <>
      <ul className="flex flex-col gap-1">
        {pages.map((p, i) => (
          <li
            key={p.id}
            className={`flex items-center gap-1 rounded border p-1 text-xs ${p.id === activePageId ? "border-accent" : "border-rule"}`}
          >
            <button
              type="button"
              aria-label={t("pageManager.openAria", { id: p.id })}
              className="flex-1 truncate text-left"
              onClick={() => onSelectPage(p.id)}
            >
              {p.name}
            </button>
            <Input
              aria-label={t("pageManager.renameAria", { id: p.id })}
              className="w-28"
              value={p.name}
              onChange={(e) => rename(p.id, e.target.value)}
            />
            <button
              type="button"
              aria-label={t("pageManager.moveUpAria", { id: p.id })}
              disabled={i === 0}
              className="disabled:opacity-30"
              onClick={() => move(p.id, -1)}
            >
              ↑
            </button>
            <button
              type="button"
              aria-label={t("pageManager.moveDownAria", { id: p.id })}
              disabled={i === pages.length - 1}
              className="disabled:opacity-30"
              onClick={() => move(p.id, 1)}
            >
              ↓
            </button>
            <button
              type="button"
              aria-label={t("pageManager.removeAria", { id: p.id })}
              disabled={pages.length <= 1}
              className="text-danger disabled:opacity-30"
              onClick={() => setRemoving(p)}
            >
              ✕
            </button>
          </li>
        ))}
        <li>
          <Button type="button" size="sm" variant="outline" onClick={addPage}>
            {t("pageManager.addButton")}
          </Button>
        </li>
      </ul>
      <ConfirmDialog
        open={!!removing}
        title={t("pageManager.removeTitle")}
        message={
          removing ? t("pageManager.removeMessage", { name: removing.name || removing.id }) : ""
        }
        confirmLabel={t("actions.delete")}
        onCancel={() => setRemoving(null)}
        onConfirm={() => {
          if (removing) remove(removing.id);
          setRemoving(null);
        }}
      />
    </>
  );
}
