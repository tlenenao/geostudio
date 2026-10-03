// SPDX-License-Identifier: Apache-2.0
import { t } from "../i18n";
export class CoreUnreachableError extends Error {
  constructor(cause?: unknown) {
    super(t("errors.coreUnreachable"));
    this.name = "CoreUnreachableError";
    this.cause = cause;
  }
}
