// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDeleteItem, useInstanceInfo, useUpdateItem } from "../api/hooks";
import type { Item } from "../api/types";
import { Button } from "../ui/kit/Button";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { Menu } from "../ui/kit/Menu";
import { PublishDialog } from "./PublishDialog";
import { hasPermission } from "../auth/permissions";
import { t } from "../i18n";

type MenuState = "closed" | "delete" | "publish";

const REFERENCING_KINDS = new Set(["map", "app", "dashboard"]);

export function ItemActions({ item, onDeleted }: { item: Item; onDeleted?: () => void }) {
  const navigate = useNavigate();
  const [menu, setMenu] = useState<MenuState>("closed");
  const triggerRef = useRef<HTMLButtonElement>(null);
  const publish = useUpdateItem(item.pk);
  const remove = useDeleteItem();
  // Même garde que NewItemButton sur l'option « Pipeline »/etlEnabled : la
  // création d'un ReportSchedule est refusée en 403 par le cœur quand la
  // capacité export est coupée (revue finale SP-17b, I3), autant ne pas
  // proposer l'entrée.
  const exportEnabled = useInstanceInfo().data?.exportEnabled === true;

  async function togglePublish() {
    // j03-012 : publier une carte/app passe par un dialogue qui signale les
    // collections lues encore privées ; dépublier reste direct.
    if (!item.isPublished && REFERENCING_KINDS.has(item.resourceType)) {
      setMenu("publish");
      return;
    }
    await doTogglePublish();
  }

  async function doTogglePublish() {
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

  const canWrite = hasPermission(item, "write");
  const publishLabel = item.isPublished ? t("actions.unpublish") : t("actions.publish");
  // « Modifier/Publier/Miniature » : verrouillés et expliqués (note du menu) ;
  // « Partager/Supprimer » : absents, pas grisés (doctrine §6.2).
  const items = [
    { label: t("actions.edit"), onSelect: () => goToPanel("edit"), disabled: !canWrite },
    { label: publishLabel, onSelect: () => void togglePublish(), disabled: !canWrite },
    { label: t("actions.thumbnail"), onSelect: () => goToPanel("thumbnail"), disabled: !canWrite },
    ...(item.resourceType === "bookmark" && exportEnabled
      ? [
          {
            label: t("actions.scheduleReport"),
            onSelect: () => navigate("/reports/new", { state: { bookmarkItemId: item.pk } }),
          },
        ]
      : []),
    ...(hasPermission(item, "share")
      ? [{ label: t("actions.share"), onSelect: () => goToPanel("share") }]
      : []),
    ...(hasPermission(item, "delete")
      ? [{ label: t("actions.delete"), onSelect: () => setMenu("delete"), danger: true }]
      : []),
  ];

  return (
    <div className="relative">
      <Menu
        trigger={
          <Button
            ref={triggerRef}
            size="sm"
            variant="ghost"
            aria-label={t("actions.menuFor", { title: item.title })}
          >
            ⋯
          </Button>
        }
        items={items}
        note={canWrite ? undefined : t("locked.needWrite")}
      />

      <PublishDialog
        item={item}
        open={menu === "publish"}
        pending={publish.isPending}
        onPublish={() => void doTogglePublish()}
        onCancel={() => setMenu("closed")}
        returnFocusRef={triggerRef}
      />
      <ConfirmDialog
        open={menu === "delete"}
        title={t("actions.deleteTitle")}
        message={t("actions.deleteMessage", { title: item.title })}
        confirmLabel={t("actions.delete")}
        pending={remove.isPending}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setMenu("closed")}
        returnFocusRef={triggerRef}
      />
      {remove.isError && menu === "delete" && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {t("actions.deleteFailed")}
        </p>
      )}
      {publish.isError && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {t("actions.publishFailed")}
        </p>
      )}
    </div>
  );
}
