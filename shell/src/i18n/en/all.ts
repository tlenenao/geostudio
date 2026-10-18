// SPDX-License-Identifier: Apache-2.0
// Chunk anglais, chargé par `activateLocale("en")` uniquement (import dynamique).
import { adminEn } from "./admin";
import { automationEn } from "./automation";
import { coreEn } from "./core";
import { mapEn } from "./map";
import { miscEn } from "./misc";
import { widgetsEn } from "./widgets";

export const enMessages: Record<string, string> = {
  ...coreEn,
  ...adminEn,
  ...automationEn,
  ...mapEn,
  ...miscEn,
  ...widgetsEn,
};
