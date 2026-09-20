// SPDX-License-Identifier: Apache-2.0
import type { Me } from "../api/types";
import { t, type MessageKey } from "../i18n";

const BUILT_IN_ROLE_LABEL_KEYS: Record<string, MessageKey> = {
  admin: "account.roleAdmin",
  analyst: "account.roleAnalyst",
  creator: "account.roleCreator",
  reader: "account.roleReader",
};

export function roleLabel(me: Me | undefined): string {
  if (!me) return "";
  const key = BUILT_IN_ROLE_LABEL_KEYS[me.role.slug];
  return key ? t(key) : me.role.name;
}
