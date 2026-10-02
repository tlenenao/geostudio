// SPDX-License-Identifier: Apache-2.0
import { ApiError } from "../api/ApiError";
import { t } from "../i18n";

/** Message distinct par cause d'échec de POST /compliance/users/{id}/erase (j08-006). */
export function eraseErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return t("compliance.eraseNotFound");
    if (error.status === 403) return t("compliance.eraseForbidden");
    if (error.status === 409) {
      return /already erased/i.test(error.detail ?? "")
        ? t("compliance.eraseAlreadyErased")
        : t("compliance.eraseLastHolder");
    }
  }
  return t("compliance.eraseError");
}
