import type { AppConfig, AppLayout, Page } from "../api/types";

const IMPLICIT_PAGE_ID = "page-1";

// A config always has at least one page. If `config.pages` is absent/empty,
// the top-level `layout` IS that single implicit page.
export function getPages(config: AppConfig): Page[] {
  if (config.pages && config.pages.length > 0) return config.pages;
  return [{ id: IMPLICIT_PAGE_ID, name: "Page 1", layout: config.layout }];
}

export function getPageLayout(config: AppConfig, pageId: string): AppLayout {
  return getPages(config).find((p) => p.id === pageId)?.layout ?? config.layout;
}

// Writes a new layout for one page. If the config has no explicit `pages` yet,
// the result stays a legacy single-page config (only `layout` changes) — an
// explicit `pages` array only appears once a second page is added (PageManager).
// Once `pages` exists, its first entry always mirrors the top-level `layout`
// (the field the backend still requires for app/dashboard configs).
export function setPageLayout(config: AppConfig, pageId: string, layout: AppLayout): AppConfig {
  if (!config.pages || config.pages.length === 0) {
    return { ...config, layout };
  }
  const pages = config.pages.map((p) => (p.id === pageId ? { ...p, layout } : p));
  return { ...config, pages, layout: pages[0].layout };
}
