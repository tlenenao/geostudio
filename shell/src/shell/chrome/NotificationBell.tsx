// SPDX-License-Identifier: Apache-2.0
import { Bell } from "lucide-react";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotificationPreference,
  useNotifications,
  useUnreadNotificationCount,
  useUpdateNotificationPreference,
} from "../../api/hooks";
import type { NotificationPreferenceValue, NotificationSummary } from "../../api/types";
import { Badge } from "../../ui/kit/Badge";
import { Popover } from "../../ui/kit/Popover";
import { t } from "../../i18n";
import type { MessageKey } from "../../i18n";
import { useOpenItem } from "../routes";

const KIND_LABEL_KEYS: Record<NotificationSummary["kind"], MessageKey> = {
  ingestion: "notifications.kindIngestion",
  pipeline: "notifications.kindPipeline",
  export: "notifications.kindExport",
  appexport: "notifications.kindAppexport",
  report: "notifications.kindReport",
};

const PREFERENCE_LABEL_KEYS: Record<NotificationPreferenceValue, MessageKey> = {
  all: "notifications.preferenceAll",
  failuresOnly: "notifications.preferenceFailuresOnly",
  none: "notifications.preferenceNone",
};

function NotificationRow({ notification }: { notification: NotificationSummary }) {
  const { onOpenItem } = useOpenItem();
  const markRead = useMarkNotificationRead();

  const content = (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-2 text-xs text-ink-2">
        <span>{t(KIND_LABEL_KEYS[notification.kind])}</span>
        <Badge variant={notification.status === "failure" ? "danger" : "ok"}>
          {t(
            notification.status === "failure"
              ? "notifications.statusFailure"
              : "notifications.statusSuccess",
          )}
        </Badge>
      </div>
      <span className="text-sm text-ink">
        {notification.itemTitle || t("notifications.deletedItem")}
      </span>
      {notification.errorMessage && (
        <span className="text-xs text-danger">{notification.errorMessage}</span>
      )}
      <span className="text-xs text-ink-2">
        {new Date(notification.createdAt).toLocaleString()}
      </span>
      {markRead.isError && (
        <span role="alert" className="text-xs text-danger">
          {t("notifications.actionError")}
        </span>
      )}
    </div>
  );

  if (notification.itemId === null || notification.itemResourceType === null) {
    return <div className="rounded p-2">{content}</div>;
  }

  const itemId = notification.itemId;
  const resourceType = notification.itemResourceType;
  return (
    <button
      className="w-full rounded p-2 text-left hover:bg-sunken"
      onClick={() => {
        if (notification.readAt === null) markRead.mutate(notification.id);
        onOpenItem(itemId, resourceType);
      }}
    >
      {content}
    </button>
  );
}

export function NotificationBell() {
  const unreadQuery = useUnreadNotificationCount();
  const notificationsQuery = useNotifications({ page: 1, pageSize: 20 });
  const preferenceQuery = useNotificationPreference();
  const updatePreference = useUpdateNotificationPreference();
  const markAllRead = useMarkAllNotificationsRead();
  const unreadCount = unreadQuery.data ?? 0;

  return (
    <Popover
      aria-label={t("notifications.bell")}
      trigger={
        <button aria-label={t("notifications.bell")} className="relative rounded-full p-2">
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <Badge variant="danger" className="absolute -right-1 -top-1">
              {unreadCount}
            </Badge>
          )}
        </button>
      }
    >
      <div className="flex w-72 flex-col gap-2">
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-2">
            <select
              aria-label={t("notifications.bell")}
              className="rounded border border-rule bg-surface px-1 py-0.5 text-xs text-ink"
              value={preferenceQuery.data ?? "all"}
              onChange={(e) =>
                updatePreference.mutate(e.target.value as NotificationPreferenceValue)
              }
            >
              {(["all", "failuresOnly", "none"] as const).map((value) => (
                <option key={value} value={value}>
                  {t(PREFERENCE_LABEL_KEYS[value])}
                </option>
              ))}
            </select>
            <button
              className="text-xs text-ink-2 hover:text-ink"
              onClick={() => markAllRead.mutate()}
            >
              {t("notifications.markAllRead")}
            </button>
          </div>
          {(updatePreference.isError || markAllRead.isError) && (
            <span role="alert" className="text-xs text-danger">
              {t("notifications.actionError")}
            </span>
          )}
        </div>
        <div className="flex max-h-80 flex-col gap-1 overflow-y-auto">
          {(notificationsQuery.isError || unreadQuery.isError) && (
            <p role="alert" className="text-sm text-danger">
              {t("notifications.loadError")}
            </p>
          )}
          {!notificationsQuery.isError &&
            (notificationsQuery.data?.notifications.length ?? 0) === 0 && (
              <span className="text-sm text-ink-2">{t("notifications.empty")}</span>
            )}
          {notificationsQuery.data?.notifications.map((n) => (
            <NotificationRow key={n.id} notification={n} />
          ))}
        </div>
      </div>
    </Popover>
  );
}
