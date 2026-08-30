// SPDX-License-Identifier: Apache-2.0
import type { Item, ResourceType } from "../api/types";
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
import { Button } from "./kit/Button";
import { Panel } from "./kit/Panel";

export function ItemCard({
  item,
  onOpen,
  actions,
}: {
  item: Item;
  onOpen: (pk: string, type: ResourceType) => void;
  actions?: React.ReactNode;
}) {
  return (
    <Panel className="flex flex-col gap-2">
      <div className="flex items-start justify-between">
        <span className="w-fit rounded bg-sunken px-2 py-0.5 text-xs uppercase text-ink-2">
          {RESOURCE_TYPE_LABELS[item.resourceType]}
        </span>
        {actions}
      </div>
      {item.thumbnailUrl && (
        <img
          src={item.thumbnailUrl}
          alt={item.title}
          className="h-24 w-full rounded object-cover"
        />
      )}
      <h3 className="text-base font-semibold text-ink">{item.title}</h3>
      <p className="line-clamp-2 text-sm text-ink-2">{item.abstract}</p>
      <Button size="sm" className="mt-2 w-fit" onClick={() => onOpen(item.pk, item.resourceType)}>
        Ouvrir
      </Button>
    </Panel>
  );
}
