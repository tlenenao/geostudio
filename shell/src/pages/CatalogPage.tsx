// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useItemFacets, useItems, useMe } from "../api/hooks";
import type { ItemScope, ItemSort, ResourceType } from "../api/types";
import { RESOURCE_TYPE_LABELS, RESOURCE_TYPE_ORDER } from "../api/resourceTypes";
import { ItemCard } from "../ui/ItemCard";
import { ItemActions } from "../shell/ItemActions";
import { Input } from "../ui/kit/Input";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";
import { CatalogSpatialFilter, type Bbox } from "./CatalogSpatialFilter";

const PAGE_SIZE = 12;
const SCOPE_LABELS: Record<ItemScope, string> = {
  all: "Tous",
  mine: "Mes éléments",
  shared: "Partagés avec moi",
  public: "Publics",
};
const SORT_LABELS: Record<ItemSort, string> = {
  date_desc: "Date de création (récent d'abord)",
  date_asc: "Date de création (ancien d'abord)",
  updated_desc: "Date de modification (récent d'abord)",
  title_asc: "Titre (A→Z)",
  title_desc: "Titre (Z→A)",
};
const SORT_ORDER: ItemSort[] = ["date_desc", "date_asc", "updated_desc", "title_asc", "title_desc"];

export function CatalogPage({
  onOpenItem,
  fixedType,
  openError,
}: {
  onOpenItem: (pk: string, type: ResourceType) => void;
  fixedType?: ResourceType;
  openError?: string;
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
    // replace: true — SP-30a review finale : une entrée d'historique par
    // changement de filtre rendait le retour arrière du navigateur inutile.
    setSearchParams(params, { replace: true });
  };
  const [scope, setScope] = useState<ItemScope>("all");
  const [sort, setSort] = useState<ItemSort>("date_desc");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [selectedKeywords, setSelectedKeywords] = useState<string[]>([]);
  const [spatialBbox, setSpatialBbox] = useState<Bbox | null>(null);
  const [page, setPage] = useState(1);
  // SP-30a review finale : la page n'était pas réinitialisée en changeant de
  // domaine via DomainBar (?type= change sans démontage de CatalogPage) —
  // "Page 3 / 1" restait affiché sur une grille vide.
  useEffect(() => {
    setPage(1);
  }, [type, fixedType]);
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
      sort,
      owner: ownerFilter || undefined,
      keywords: selectedKeywords.length > 0 ? selectedKeywords : undefined,
      bbox: spatialBbox ? spatialBbox.join(",") : undefined,
      me: requiresMe ? me.data?.username : undefined,
    },
    { enabled: !requiresMe || !!me.data },
  );
  const facetsQuery = useItemFacets(
    { q: q || undefined, type: type || undefined, scope },
    { enabled: !requiresMe || !!me.data },
  );

  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1;

  function toggleKeyword(keyword: string) {
    setSelectedKeywords((prev) =>
      prev.includes(keyword) ? prev.filter((k) => k !== keyword) : [...prev, keyword],
    );
    setPage(1);
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="catalog"
        browse={{
          id: "filter",
          label: "Filtrer",
          content: (
            <div className="flex flex-col gap-4 p-3">
              <label className="flex flex-col gap-1 text-sm text-ink">
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
                <label className="flex flex-col gap-1 text-sm text-ink">
                  Type
                  <select
                    aria-label="Type"
                    className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                    value={type}
                    onChange={(e) => setType(e.target.value as ResourceType | "")}
                  >
                    <option value="">Tous</option>
                    {RESOURCE_TYPE_ORDER.map((rt) => (
                      <option key={rt} value={rt}>
                        {RESOURCE_TYPE_LABELS[rt]}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {type === "pipeline" && !fixedType && (
                <Link to="/reports" className="text-accent hover:underline">
                  Rapports planifiés →
                </Link>
              )}
              <label className="flex flex-col gap-1 text-sm text-ink">
                Portée
                <select
                  aria-label="Portée"
                  className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                  value={scope}
                  onChange={(e) => {
                    setScope(e.target.value as ItemScope);
                    setPage(1);
                  }}
                >
                  {(Object.keys(SCOPE_LABELS) as ItemScope[]).map((s) => (
                    <option key={s} value={s}>
                      {SCOPE_LABELS[s]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm text-ink">
                Trier par
                <select
                  aria-label="Trier par"
                  className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                  value={sort}
                  onChange={(e) => {
                    setSort(e.target.value as ItemSort);
                    setPage(1);
                  }}
                >
                  {SORT_ORDER.map((s) => (
                    <option key={s} value={s}>
                      {SORT_LABELS[s]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm text-ink">
                Propriétaire
                <select
                  aria-label="Propriétaire"
                  className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                  value={ownerFilter}
                  onChange={(e) => {
                    setOwnerFilter(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">Tous</option>
                  {(facetsQuery.data?.owners ?? []).map((o) => (
                    <option key={o.username} value={o.username}>
                      {o.username} ({o.count})
                    </option>
                  ))}
                </select>
              </label>
              {(facetsQuery.data?.keywords.length ?? 0) > 0 && (
                <div className="flex flex-col gap-1 text-sm text-ink">
                  Mots-clés
                  <div className="flex flex-wrap gap-2">
                    {(facetsQuery.data?.keywords ?? []).map((k) => (
                      <button
                        key={k.keyword}
                        type="button"
                        aria-pressed={selectedKeywords.includes(k.keyword)}
                        onClick={() => toggleKeyword(k.keyword)}
                        className="rounded-full border border-rule bg-surface px-3 py-1 text-xs text-ink aria-pressed:border-accent aria-pressed:bg-accent aria-pressed:text-surface"
                      >
                        {k.keyword} ({k.count})
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex flex-col gap-1 text-sm text-ink">
                Recherche spatiale
                <CatalogSpatialFilter
                  onChange={(bbox) => {
                    setSpatialBbox(bbox);
                    setPage(1);
                  }}
                />
              </div>
            </div>
          ),
        }}
        work={{
          id: "catalog",
          label: "Catalogue",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-6">
              {openError && (
                <p role="alert" className="text-sm text-danger">
                  {openError}
                </p>
              )}
              {query.isLoading && <p role="status">Chargement…</p>}
              {query.isError && (
                <div role="alert" className="text-sm text-danger">
                  Erreur de chargement.{" "}
                  <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
                    Réessayer
                  </Button>
                </div>
              )}
              {query.isSuccess && query.data.items.length === 0 && (
                <p className="text-sm text-ink-3">Aucun élément.</p>
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
              <div className="mt-auto flex items-center gap-3">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Précédent
                </Button>
                <span className="text-sm text-ink-2">
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
          ),
        }}
        inspect={{
          id: "summary",
          label: "Résumé",
          content: (
            <Panel className="m-3 flex flex-col gap-2 text-sm">
              <p className="font-medium text-ink">
                {t("catalog.count", { n: query.data?.total ?? 0 })}
              </p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs text-ink-2">
                <dt>Recherche</dt>
                <dd>{q || "—"}</dd>
                <dt>Type</dt>
                <dd>{type ? RESOURCE_TYPE_LABELS[type] : "Tous"}</dd>
                <dt>Portée</dt>
                <dd>{SCOPE_LABELS[scope]}</dd>
                <dt>Trier par</dt>
                <dd>{SORT_LABELS[sort]}</dd>
                <dt>Propriétaire</dt>
                <dd>{ownerFilter || "Tous"}</dd>
                <dt>Mots-clés</dt>
                <dd>{selectedKeywords.length > 0 ? selectedKeywords.join(", ") : "—"}</dd>
                <dt>Emprise spatiale</dt>
                <dd>{spatialBbox ? spatialBbox.map((n) => n.toFixed(2)).join(", ") : "—"}</dd>
              </dl>
            </Panel>
          ),
        }}
      />
    </div>
  );
}
