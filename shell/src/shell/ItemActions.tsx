import { useState } from "react";
import { useDeleteItem, useUpdateItem, useUploadThumbnail } from "../api/hooks";
import type { Item } from "../api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { MetadataForm } from "../ui/MetadataForm";
import { ThumbnailUpload } from "../ui/ThumbnailUpload";

type Panel = null | "menu" | "edit" | "thumbnail" | "delete";

export function ItemActions({ item, onDeleted }: { item: Item; onDeleted?: () => void }) {
  const [panel, setPanel] = useState<Panel>(null);
  const update = useUpdateItem(item.pk);
  const thumbnail = useUploadThumbnail(item.pk);
  const remove = useDeleteItem();

  async function save(v: { title: string; abstract: string; keywords: string[] }) {
    try {
      await update.mutateAsync(v);
      setPanel(null);
    } catch {
      /* surfaced via update.isError */
    }
  }

  async function upload(file: File) {
    try {
      await thumbnail.mutateAsync(file);
      setPanel(null);
    } catch {
      /* surfaced via thumbnail.isError */
    }
  }

  async function confirmDelete() {
    try {
      await remove.mutateAsync(item.pk);
      setPanel(null);
      onDeleted?.();
    } catch {
      /* surfaced via remove.isError */
    }
  }

  return (
    <>
      <Button size="sm" variant="ghost" aria-label="Actions" onClick={() => setPanel("menu")}>
        ⋯
      </Button>

      {panel === "menu" && (
        <div className="absolute z-20 mt-8 flex flex-col rounded-md border border-slate-200 bg-white text-sm shadow">
          <button className="px-3 py-1 text-left hover:bg-slate-100" onClick={() => setPanel("edit")}>
            Modifier
          </button>
          <button className="px-3 py-1 text-left hover:bg-slate-100" onClick={() => setPanel("thumbnail")}>
            Miniature
          </button>
          <button className="px-3 py-1 text-left text-red-600 hover:bg-slate-100" onClick={() => setPanel("delete")}>
            Supprimer
          </button>
        </div>
      )}

      <Dialog open={panel === "edit"} onClose={() => setPanel(null)} title="Modifier l'élément">
        <MetadataForm
          initial={{ title: item.title, abstract: item.abstract, keywords: [] }}
          onSubmit={save}
          onCancel={() => setPanel(null)}
          pending={update.isPending}
        />
        {update.isError && (
          <p role="alert" className="mt-2 text-sm text-red-600">
            Échec de l'enregistrement.
          </p>
        )}
      </Dialog>

      <Dialog open={panel === "thumbnail"} onClose={() => setPanel(null)} title="Miniature">
        <ThumbnailUpload onUpload={upload} pending={thumbnail.isPending} />
        {thumbnail.isError && (
          <p role="alert" className="mt-2 text-sm text-red-600">
            Échec de l'envoi.
          </p>
        )}
      </Dialog>

      <ConfirmDialog
        open={panel === "delete"}
        title="Supprimer l'élément"
        message={`Supprimer « ${item.title} » ? Cette action est irréversible.`}
        confirmLabel="Supprimer"
        pending={remove.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setPanel(null)}
      />
    </>
  );
}
