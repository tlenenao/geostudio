// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useItemClient } from "../api/ItemClientProvider";
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
import type { Item, ResourceType } from "../api/types";
import { t } from "../i18n";
import { publicThumbnailSrc } from "../lib/publicThumbnail";
import { useDocumentMeta } from "../shell/useDocumentMeta";
import { Banner } from "../ui/kit/Banner";
import { Button } from "../ui/kit/Button";
import { EmptyState } from "../ui/kit/EmptyState";
import { Input } from "../ui/kit/Input";
import { ItemCard } from "../ui/kit/ItemCard";
import { LoadingState } from "../ui/kit/LoadingState";
import { PageTitle } from "../ui/kit/PageTitle";

// Types servis par GET /public/items (core/app/items/repository.py::PUBLIC_KINDS).
const PUBLIC_TYPES: ResourceType[] = ["site", "app", "dashboard", "map", "dataset"];
const PAGE_SIZE = 12;

/** Catalogue consultable sans connexion (P35.01) : items publiés, filtre
 * type/mot-clé, pagination — état dans l'URL. */
export function PublicCatalogPage() {
  const client = useItemClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const rawType = params.get("type");
  const type = PUBLIC_TYPES.find((p) => p === rawType);
  const tag = params.get("tag") ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);

  useDocumentMeta({
    title: t("publicCatalog.title"),
    description: t("publicCatalog.description"),
    canonicalUrl: `${window.location.origin}/public`,
  });

  const query = useQuery({
    queryKey: ["public-catalog", type, tag, page],
    queryFn: () =>
      client.listPublicItems({ type, tag: tag || undefined, page, pageSize: PAGE_SIZE }),
    retry: false,
  });

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  }

  function open(pk: string, resourceType: ResourceType) {
    const item = query.data?.items.find((i) => i.pk === pk);
    navigate(
      resourceType === "site" && item?.slug
        ? `/sites/${encodeURIComponent(item.slug)}`
        : `/public/items/${encodeURIComponent(pk)}`,
    );
  }

  const pages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PAGE_SIZE));
  const items: Item[] = (query.data?.items ?? []).map((i) => ({
    ...i,
    thumbnailUrl: publicThumbnailSrc(i.thumbnailUrl),
  }));

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <PageTitle>{t("publicCatalog.title")}</PageTitle>
        <p className="text-sm text-ink-2">{t("publicCatalog.description")}</p>
      </header>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("publicCatalog.typeLabel")}
          <select
            className="h-9 rounded-md border border-control bg-surface px-2 text-sm text-ink"
            value={type ?? ""}
            onChange={(e) => setParam("type", e.target.value)}
          >
            <option value="">{t("publicCatalog.allTypes")}</option>
            {PUBLIC_TYPES.map((p) => (
              <option key={p} value={p}>
                {RESOURCE_TYPE_LABELS[p]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("publicCatalog.tagLabel")}
          <Input value={tag} onChange={(e) => setParam("tag", e.target.value)} />
        </label>
      </div>
      {query.isLoading && <LoadingState />}
      {query.isError && <Banner variant="danger">{t("publicCatalog.loadError")}</Banner>}
      {query.isSuccess && items.length === 0 && <EmptyState title={t("publicCatalog.empty")} />}
      {items.length > 0 && (
        <ul className="grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <li key={item.pk}>
              <ItemCard item={item} onOpen={open} />
            </li>
          ))}
        </ul>
      )}
      {pages > 1 && (
        <nav className="flex items-center justify-between" aria-label={t("publicCatalog.title")}>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setParam("page", String(page - 1))}
          >
            {t("publicCatalog.previous")}
          </Button>
          <span className="text-sm text-ink-2">{t("publicCatalog.pageOf", { page, pages })}</span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pages}
            onClick={() => setParam("page", String(page + 1))}
          >
            {t("publicCatalog.next")}
          </Button>
        </nav>
      )}
    </main>
  );
}
