import { useState } from "react";
import { useItems } from "../api/hooks";
import type { ResourceType } from "../api/types";
import { ItemCard } from "../ui/ItemCard";
import { ItemActions } from "../shell/ItemActions";
import { Input } from "../ui/input";
import { Button } from "../ui/button";

const PAGE_SIZE = 12;

export function CatalogPage({ onOpenItem }: { onOpenItem: (pk: string) => void }) {
  const [q, setQ] = useState("");
  const [type, setType] = useState<ResourceType | "">("");
  const [page, setPage] = useState(1);

  const query = useItems({
    q: q || undefined,
    type: type || undefined,
    page,
    pageSize: PAGE_SIZE,
  });

  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-sm">
          Rechercher
          <Input
            aria-label="Rechercher"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Type
          <select
            aria-label="Type"
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
            value={type}
            onChange={(e) => {
              setType(e.target.value as ResourceType | "");
              setPage(1);
            }}
          >
            <option value="">Tous</option>
            <option value="app">App</option>
            <option value="dashboard">Dashboard</option>
            <option value="map">Map</option>
          </select>
        </label>
      </div>

      {query.isLoading && <p role="status">Chargement…</p>}
      {query.isError && (
        <div role="alert" className="text-sm text-red-600">
          Erreur de chargement.{" "}
          <Button size="sm" variant="outline" onClick={() => query.refetch()}>
            Réessayer
          </Button>
        </div>
      )}
      {query.isSuccess && query.data.items.length === 0 && (
        <p className="text-sm text-slate-500">Aucun élément.</p>
      )}

      {query.isSuccess && query.data.items.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {query.data.items.map((item) => (
            <ItemCard
              key={item.pk}
              item={item}
              onOpen={onOpenItem}
              actions={<ItemActions item={item} />}
            />
          ))}
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button
          size="sm"
          variant="outline"
          disabled={page <= 1}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
        >
          Précédent
        </Button>
        <span className="text-sm text-slate-500">
          Page {page} / {totalPages}
        </span>
        <Button
          size="sm"
          variant="outline"
          disabled={page >= totalPages}
          onClick={() => setPage((p) => p + 1)}
        >
          Suivant
        </Button>
      </div>
    </div>
  );
}
