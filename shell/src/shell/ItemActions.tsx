// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDeleteItem, useInstanceInfo, useUpdateItem } from "../api/hooks";
import type { Item } from "../api/types";
import { Button } from "../ui/kit/Button";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { Gate } from "../auth/Gate";
import { Locked } from "../auth/Locked";
import { hasPermission } from "../auth/permissions";
import { t } from "../i18n";

type MenuState = "closed" | "open" | "delete";

export function ItemActions({ item, onDeleted }: { item: Item; onDeleted?: () => void }) {
  const navigate = useNavigate();
  const [menu, setMenu] = useState<MenuState>("closed");
  const publish = useUpdateItem(item.pk);
  const remove = useDeleteItem();
  // Même garde que NewItemButton sur l'option « Pipeline »/etlEnabled : la
  // création d'un ReportSchedule est refusée en 403 par le cœur quand la
  // capacité export est coupée (revue finale SP-17b, I3), autant ne pas
  // proposer l'entrée.
  const exportEnabled = useInstanceInfo().data?.exportEnabled === true;

  async function togglePublish() {
    try {
      await publish.mutateAsync({ isPublished: !item.isPublished });
      setMenu("closed");
    } catch {
      /* surfaced via publish.isError */
    }
  }

  async function confirmDelete() {
    try {
      await remove.mutateAsync(item.pk);
      setMenu("closed");
      onDeleted?.();
    } catch {
      /* surfaced via remove.isError */
    }
  }

  function goToPanel(panel: "edit" | "thumbnail" | "share") {
    setMenu("closed");
    navigate(`/items/${item.pk}?panel=${panel}`);
  }

  return (
    <div className="relative">
      <Button
        size="sm"
        variant="ghost"
        aria-label={t("actions.menu")}
        onClick={() => setMenu(menu === "open" ? "closed" : "open")}
      >
        ⋯
      </Button>

      {menu === "open" && (
        <div className="absolute right-0 z-20 mt-1 flex w-44 flex-col rounded-md border border-rule bg-raised py-1 text-sm shadow-md">
          {hasPermission(item, "write") ? (
            <>
              <button
                className="px-3 py-1.5 text-left text-ink hover:bg-sunken"
                onClick={() => goToPanel("edit")}
              >
                {t("actions.edit")}
              </button>
              <button
                className="px-3 py-1.5 text-left text-ink hover:bg-sunken"
                onClick={() => void togglePublish()}
              >
                {item.isPublished ? t("actions.unpublish") : t("actions.publish")}
              </button>
              <button
                className="px-3 py-1.5 text-left text-ink hover:bg-sunken"
                onClick={() => goToPanel("thumbnail")}
              >
                {t("actions.thumbnail")}
              </button>
            </>
          ) : (
            <Locked reason={t("locked.needWrite")}>
              <button className="px-3 py-1.5 text-left">{t("actions.edit")}</button>
              <button className="px-3 py-1.5 text-left">
                {item.isPublished ? t("actions.unpublish") : t("actions.publish")}
              </button>
              <button className="px-3 py-1.5 text-left">{t("actions.thumbnail")}</button>
            </Locked>
          )}

          {item.resourceType === "bookmark" && exportEnabled && (
            <button
              className="px-3 py-1.5 text-left text-ink hover:bg-sunken"
              onClick={() => {
                setMenu("closed");
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
              className="px-3 py-1.5 text-left text-ink hover:bg-sunken"
              onClick={() => goToPanel("share")}
            >
              {t("actions.share")}
            </button>
          </Gate>

          <Gate on={item} can="delete">
            <button
              className="px-3 py-1.5 text-left text-danger hover:bg-sunken"
              onClick={() => setMenu("delete")}
            >
              {t("actions.delete")}
            </button>
          </Gate>
        </div>
      )}

      <ConfirmDialog
        open={menu === "delete"}
        title={t("actions.deleteTitle")}
        message={t("actions.deleteMessage", { title: item.title })}
        confirmLabel={t("actions.delete")}
        pending={remove.isPending}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setMenu("closed")}
      />
      {remove.isError && menu === "delete" && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {t("actions.deleteFailed")}
        </p>
      )}
      {publish.isError && menu === "open" && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {t("actions.publishFailed")}
        </p>
      )}
    </div>
  );
}
