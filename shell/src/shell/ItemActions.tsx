// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDeleteItem, useInstanceInfo, useUpdateItem, useUploadThumbnail } from "../api/hooks";
import type { Item } from "../api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { MetadataForm } from "../ui/MetadataForm";
import { ThumbnailUpload } from "../ui/ThumbnailUpload";
import { ShareDialog } from "./ShareDialog";
import { Gate } from "../auth/Gate";
import { Locked } from "../auth/Locked";
import { hasPermission } from "../auth/permissions";
import { t } from "../i18n";

type Panel = null | "menu" | "edit" | "thumbnail" | "share" | "delete";

export function ItemActions({ item, onDeleted }: { item: Item; onDeleted?: () => void }) {
  const navigate = useNavigate();
  const [panel, setPanel] = useState<Panel>(null);
  const update = useUpdateItem(item.pk);
  const publish = useUpdateItem(item.pk);
  const thumbnail = useUploadThumbnail(item.pk);
  const remove = useDeleteItem();
  // Même garde que NewItemButton sur l'option « Pipeline »/etlEnabled : la
  // création d'un ReportSchedule est refusée en 403 par le cœur quand la
  // capacité export est coupée (revue finale SP-17b, I3), autant ne pas
  // proposer l'entrée.
  const exportEnabled = useInstanceInfo().data?.exportEnabled === true;

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

  async function togglePublish() {
    try {
      await publish.mutateAsync({ isPublished: !item.isPublished });
      setPanel(null);
    } catch {
      /* surfaced via publish.isError */
    }
  }

  return (
    <div className="relative">
      <Button
        size="sm"
        variant="ghost"
        aria-label={t("actions.menu")}
        onClick={() => setPanel("menu")}
      >
        ⋯
      </Button>

      {panel === "menu" && (
        <div className="absolute z-20 mt-8 flex flex-col rounded-md border border-slate-200 bg-white text-sm shadow">
          {hasPermission(item, "write") ? (
            <>
              <button
                className="px-3 py-1 text-left hover:bg-slate-100"
                onClick={() => setPanel("edit")}
              >
                {t("actions.edit")}
              </button>
              <button
                className="px-3 py-1 text-left hover:bg-slate-100"
                onClick={() => void togglePublish()}
              >
                {item.isPublished ? t("actions.unpublish") : t("actions.publish")}
              </button>
              <button
                className="px-3 py-1 text-left hover:bg-slate-100"
                onClick={() => setPanel("thumbnail")}
              >
                {t("actions.thumbnail")}
              </button>
            </>
          ) : (
            <Locked reason={t("locked.needWrite")}>
              <button className="px-3 py-1 text-left">{t("actions.edit")}</button>
              <button className="px-3 py-1 text-left">
                {item.isPublished ? t("actions.unpublish") : t("actions.publish")}
              </button>
              <button className="px-3 py-1 text-left">{t("actions.thumbnail")}</button>
            </Locked>
          )}

          {item.resourceType === "bookmark" && exportEnabled && (
            <button
              className="px-3 py-1 text-left hover:bg-slate-100"
              onClick={() => {
                setPanel(null);
                navigate("/reports/new", { state: { bookmarkItemId: item.pk } });
              }}
            >
              {t("actions.scheduleReport")}
            </button>
          )}

          {/* Partager et Supprimer : traitement « absent », pas « verrouillé ».
              Les montrer grisées sur chaque ligne d'un catalogue partagé
              encombrerait sans rien apprendre (doctrine §6.2). */}
          <Gate on={item} can="share">
            <button
              className="px-3 py-1 text-left hover:bg-slate-100"
              onClick={() => setPanel("share")}
            >
              {t("actions.share")}
            </button>
          </Gate>

          <Gate on={item} can="delete">
            <button
              className="px-3 py-1 text-left text-red-600 hover:bg-slate-100"
              onClick={() => setPanel("delete")}
            >
              {t("actions.delete")}
            </button>
          </Gate>
        </div>
      )}

      <Dialog open={panel === "edit"} onClose={() => setPanel(null)} title={t("actions.editTitle")}>
        <MetadataForm
          initial={{ title: item.title, abstract: item.abstract, keywords: [] }}
          onSubmit={(v) => void save(v)}
          onCancel={() => setPanel(null)}
          pending={update.isPending}
        />
        {update.isError && (
          <p role="alert" className="mt-2 text-sm text-red-600">
            {t("actions.saveFailed")}
          </p>
        )}
      </Dialog>

      <Dialog
        open={panel === "thumbnail"}
        onClose={() => setPanel(null)}
        title={t("actions.thumbnailTitle")}
      >
        <ThumbnailUpload onUpload={(file) => void upload(file)} pending={thumbnail.isPending} />
        {thumbnail.isError && (
          <p role="alert" className="mt-2 text-sm text-red-600">
            {t("actions.uploadFailed")}
          </p>
        )}
      </Dialog>

      <ShareDialog item={item} open={panel === "share"} onClose={() => setPanel(null)} />

      <ConfirmDialog
        open={panel === "delete"}
        title={t("actions.deleteTitle")}
        message={t("actions.deleteMessage", { title: item.title })}
        confirmLabel={t("actions.delete")}
        pending={remove.isPending}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPanel(null)}
      />
      {remove.isError && panel === "delete" && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {t("actions.deleteFailed")}
        </p>
      )}
      {publish.isError && panel === "menu" && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {t("actions.publishFailed")}
        </p>
      )}
    </div>
  );
}
