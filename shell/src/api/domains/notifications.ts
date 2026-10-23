// SPDX-License-Identifier: Apache-2.0
import type { ItemClient, NotificationPreferenceValue, NotificationSummary } from "../types";
import { ensureOk, type ItemClientBase } from "../base";

function _preferenceToCore(value: NotificationPreferenceValue): string {
  return value === "failuresOnly" ? "failures_only" : value;
}

function _preferenceFromCore(value: string): NotificationPreferenceValue {
  return value === "failures_only" ? "failuresOnly" : (value as NotificationPreferenceValue);
}

type NotificationsMethods = Pick<
  ItemClient,
  | "listNotifications"
  | "getUnreadNotificationCount"
  | "subscribeNotifications"
  | "markNotificationRead"
  | "markAllNotificationsRead"
  | "getNotificationPreference"
  | "updateNotificationPreference"
>;

export function createNotificationsMethods(base: ItemClientBase): NotificationsMethods {
  const { request } = base;
  return {
    async listNotifications(params: {
      page: number;
      pageSize: number;
    }): Promise<{ notifications: NotificationSummary[]; total: number }> {
      const query = new URLSearchParams({
        page: String(params.page),
        pageSize: String(params.pageSize),
      });
      return request<{ notifications: NotificationSummary[]; total: number }>(
        "GET",
        `/notifications?${query.toString()}`,
      );
    },

    async getUnreadNotificationCount(): Promise<number> {
      const { count } = await request<{ count: number }>("GET", "/notifications/unread-count");
      return count;
    },

    async markNotificationRead(id: string): Promise<NotificationSummary> {
      return request<NotificationSummary>("POST", `/notifications/${id}/read`);
    },

    async markAllNotificationsRead(): Promise<void> {
      await request<void>("POST", "/notifications/read-all");
    },

    // L13/D7 : flux SSE (le cœur le ferme après ~55 s ; l'appelant se reconnecte).
    // fetch + en-tête Authorization (EventSource ne peut pas en porter un).
    async subscribeNotifications(
      onUnread: (count: number) => void,
      signal: AbortSignal,
    ): Promise<void> {
      const res = await base.authFetch(
        `${base.coreUrl}/notifications/stream`,
        { signal, headers: { Accept: "text/event-stream" } },
        70_000,
      );
      await ensureOk(res);
      if (!res.body) return;
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) return;
        buffer += value;
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const data = /^data: (.*)$/m.exec(frame);
          if (!data || !frame.includes("event: notifications")) continue;
          const { unread } = JSON.parse(data[1]) as { unread: number };
          onUnread(unread);
        }
      }
    },

    async getNotificationPreference(): Promise<NotificationPreferenceValue> {
      const { value } = await request<{ value: string }>("GET", "/notifications/preference");
      return _preferenceFromCore(value);
    },

    async updateNotificationPreference(
      value: NotificationPreferenceValue,
    ): Promise<NotificationPreferenceValue> {
      const { value: updated } = await request<{ value: string }>(
        "PATCH",
        "/notifications/preference",
        { value: _preferenceToCore(value) },
      );
      return _preferenceFromCore(updated);
    },
  };
}
