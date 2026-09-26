// SPDX-License-Identifier: Apache-2.0
import { listWidgets } from "./registry";

export function WidgetPalette({
  onAdd,
  exclude = [],
}: {
  onAdd: (type: string) => void;
  exclude?: string[];
}) {
  return (
    <ul className="flex flex-col gap-1">
      {listWidgets()
        .filter((def) => !exclude.includes(def.type))
        .map((def) => (
          <li key={def.type}>
            <button
              type="button"
              className="w-full rounded-md border border-rule px-2 py-1.5 text-left text-sm hover:bg-sunken"
              onClick={() => onAdd(def.type)}
            >
              {def.label}
            </button>
          </li>
        ))}
    </ul>
  );
}
