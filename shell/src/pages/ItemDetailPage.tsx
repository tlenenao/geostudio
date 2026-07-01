import { useItem } from "../api/hooks";
import { Button } from "../ui/button";
import { ItemActions } from "../shell/ItemActions";

export function ItemDetailPage({ pk }: { pk: string }) {
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
        <ItemActions item={item} />
      </div>
      <h2 className="text-xl font-semibold">{item.title}</h2>
      <p className="text-sm text-slate-500">Propriétaire : {item.owner}</p>
      <p className="text-sm">{item.abstract}</p>
      <Button className="w-fit" disabled title="Disponible avec l'éditeur (SP-0d)">
        Ouvrir dans l'éditeur
      </Button>
    </article>
  );
}
