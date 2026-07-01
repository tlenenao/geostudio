import type { Item } from "../api/types";
import { Button } from "./button";
import { Card } from "./card";

export function ItemCard({
  item,
  onOpen,
  actions,
}: {
  item: Item;
  onOpen: (pk: string) => void;
  actions?: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col gap-2 p-4">
      <div className="flex items-start justify-between">
        <span className="w-fit rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
          {item.resourceType}
        </span>
        {actions}
      </div>
      <h3 className="text-base font-semibold">{item.title}</h3>
      <p className="line-clamp-2 text-sm text-slate-500">{item.abstract}</p>
      <Button size="sm" className="mt-2 w-fit" onClick={() => onOpen(item.pk)}>
        Ouvrir
      </Button>
    </Card>
  );
}
