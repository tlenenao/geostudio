// SPDX-License-Identifier: Apache-2.0
import type { ItemClient, NotificationPreferenceValue, NotificationSummary } from "../types";
import type { ItemClientBase } from "../base";

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
