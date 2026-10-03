// SPDX-License-Identifier: Apache-2.0
import { t } from "../i18n";
import { formatBytes } from "../lib/format";
import { ApiError } from "./ApiError";

// Message affichable d'une erreur de mutation : le `detail` RFC 7807 du cœur, avec
// « Réessayez dans N s » sur un 429 ; `fallback` pour toute autre erreur.
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  if (error.problemType === "quota-exceeded" && error.quota) {
    const { kind, current, limit } = error.quota;
    const fmt = kind === "storage" ? formatBytes : (n: number) => String(n);
    const vars = { current: fmt(current), limit: fmt(limit) };
    if (kind === "items") return t("quota.exceeded.items", vars);
    if (kind === "collections") return t("quota.exceeded.collections", vars);
    if (kind === "storage") return t("quota.exceeded.storage", vars);
  }
  if (error.status === 429)
    return `${error.detail ?? fallback} ${
      error.retryAfter !== undefined ? t("errors.retryAfter", { seconds: error.retryAfter }) : ""
    }`.trim();
  return error.detail ?? fallback;
}
