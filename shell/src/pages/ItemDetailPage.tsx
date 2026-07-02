import { useItem } from "../api/hooks";
import { Button } from "../ui/button";
import { ItemActions } from "../shell/ItemActions";

export function ItemDetailPage({ pk, onDeleted, onOpenEditor }: { pk: string; onDeleted?: () => void; onOpenEditor?: (type: string) => void }) {
  const query = useItem(pk);

  if (query.isLoading) return <p role="status">Chargement…</p>;
  if (query.isError || !query.data)
    return (
      <p role="alert" className="text-sm text-red-600">
        Élément introuvable.
      </p>
    );

  const item = query.data;
  return (
    <article className="flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <span className="w-fit rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
          {item.resourceType}
        </span>
        <ItemActions item={item} onDeleted={onDeleted} />
      </div>
      <h2 className="text-xl font-semibold">{item.title}</h2>
      <p className="text-sm text-slate-500">Propriétaire : {item.owner}</p>
      <p className="text-sm">{item.abstract}</p>
      {["map", "app", "dashboard"].includes(item.resourceType) ? (
        <Button className="w-fit" onClick={() => onOpenEditor?.(item.resourceType)}>Ouvrir dans l'éditeur</Button>
      ) : (
        <Button className="w-fit" disabled title="Éditeur indisponible pour ce type">
          Ouvrir dans l'éditeur
        </Button>
      )}
    </article>
  );
}
