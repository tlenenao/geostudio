// SPDX-License-Identifier: Apache-2.0
// Parcourt aussi les widgets imbriqués (tabs/modal/drawer : leur contenu vit
// dans LayoutItem.props) — miroir de core/app/appexport/guard.py (j10b-004).
import type { AppConfig } from "../../api/types";

function nested(value: unknown, types: Set<string>): void {
  if (Array.isArray(value)) {
    for (const v of value) nested(v, types);
  } else if (value && typeof value === "object") {
    const rec = value as Record<string, unknown>;
    if (typeof rec.widget === "string") types.add(rec.widget);
    for (const v of Object.values(rec)) nested(v, types);
  }
}

export function collectWidgetTypes(config: AppConfig): Set<string> {
  const types = new Set<string>();
  // A config always has at least one page (shell/src/builder/pages.ts:6-7,23).
  // If `pages` is absent/empty (legacy/implicit single-page shape), the
  // widgets live in the top-level `layout` — scan both so a single-page app
  // (the common case) isn't invisible to this scan.
  for (const item of config.layout?.items ?? []) {
    types.add(item.widget);
    nested(item.props, types);
  }
  for (const page of config.pages ?? []) {
    for (const item of page.layout.items) {
      types.add(item.widget);
      nested(item.props, types);
    }
  }
  return types;
}

export const WRITE_CAPABLE_WIDGET_TYPES = new Set(["form"]);
