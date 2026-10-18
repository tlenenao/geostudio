// SPDX-License-Identifier: Apache-2.0
import type { ItemClient, SavedSqlQuery } from "../types";
import type { ItemClientBase } from "../base";

type SavedQueriesMethods = Pick<
  ItemClient,
  "listSavedSqlQueries" | "createSavedSqlQuery" | "updateSavedSqlQuery" | "deleteSavedSqlQuery"
>;

// AUD-062 : requêtes SQL Lab enregistrées (privées à leur auteur, côté cœur).
export function createSavedQueriesMethods(base: ItemClientBase): SavedQueriesMethods {
  const { request } = base;
  return {
    async listSavedSqlQueries(): Promise<SavedSqlQuery[]> {
      return request<SavedSqlQuery[]>("GET", "/analytics/sql/saved");
    },
    async createSavedSqlQuery(body: { name: string; sql: string }): Promise<SavedSqlQuery> {
      return request<SavedSqlQuery>("POST", "/analytics/sql/saved", body);
    },
    async updateSavedSqlQuery(
      id: string,
      body: { name: string; sql: string },
    ): Promise<SavedSqlQuery> {
      return request<SavedSqlQuery>("PUT", `/analytics/sql/saved/${encodeURIComponent(id)}`, body);
    },
    async deleteSavedSqlQuery(id: string): Promise<void> {
      await request<void>("DELETE", `/analytics/sql/saved/${encodeURIComponent(id)}`);
    },
  };
}
