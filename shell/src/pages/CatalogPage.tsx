// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useItems, useMe } from "../api/hooks";
import type { ItemScope, ResourceType } from "../api/types";
import { RESOURCE_TYPE_LABELS, RESOURCE_TYPE_ORDER } from "../api/resourceTypes";
import { ItemCard } from "../ui/ItemCard";
import { ItemActions } from "../shell/ItemActions";
import { Input } from "../ui/input";
import { Button } from "../ui/button";

const PAGE_SIZE = 12;

export function CatalogPage({
  onOpenItem,
  fixedType,
}: {
  onOpenItem: (pk: string, type: ResourceType) => void;
  fixedType?: ResourceType;
}) {
  const [q, setQ] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const urlType = searchParams.get("type");
  const validUrlType =
    urlType !== null && (RESOURCE_TYPE_ORDER as readonly string[]).includes(urlType)
      ? (urlType as ResourceType)
      : "";
  // L'URL est la source de vérité (DomainBar navigue en changeant ?type=) :
  // pas de useState local qui figerait la valeur au premier rendu et
  // ignorerait les navigations suivantes vers la même page montée.
  const type = fixedType ?? validUrlType;
  const setType = (next: ResourceType | "") => {
    const params = new URLSearchParams(searchParams);
    if (next) {
      params.set("type", next);
    } else {
      params.delete("type");
    }
    setSearchParams(params);
  };
  const [scope, setScope] = useState<ItemScope>("all");
  const [page, setPage] = useState(1);
  const me = useMe();

  // "mine"/"shared" need the current username; gate the query until it's known
  // so the grid never briefly shows unfiltered results under those scopes.
  const requiresMe = scope === "mine" || scope === "shared";
  const query = useItems(
    {
      q: q || undefined,
      type: type || undefined,
      page,
      pageSize: PAGE_SIZE,
      scope,
      me: requiresMe ? me.data?.username : undefined,
    },
    { enabled: !requiresMe || !!me.data },
  );

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
        {!fixedType && (
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
              {RESOURCE_TYPE_ORDER.map((t) => (
                <option key={t} value={t}>
                  {RESOURCE_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="flex flex-col gap-1 text-sm">
          Portée
          <select
            aria-label="Portée"
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
            value={scope}
            onChange={(e) => {
              setScope(e.target.value as ItemScope);
              setPage(1);
            }}
          >
            <option value="all">Tous</option>
            <option value="mine">Mes éléments</option>
            <option value="shared">Partagés avec moi</option>
            <option value="public">Publics</option>
          </select>
        </label>
      </div>

      {query.isLoading && <p role="status">Chargement…</p>}
      {query.isError && (
        <div role="alert" className="text-sm text-red-600">
          Erreur de chargement.{" "}
          <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
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
