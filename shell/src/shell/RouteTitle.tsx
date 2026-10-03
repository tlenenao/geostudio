// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";
import { matchPath, useLocation } from "react-router-dom";
import { t, type MessageKey } from "../i18n";

// WCAG 2.4.2 (P33.01) : un titre de document distinct par vue, « Vue — GeoStudio ».
// Ordre significatif : la première correspondance gagne (`/apps/:pk/edit`
// avant la route publique `/apps/:pk/:pageId?`).
const ROUTE_TITLES: [path: string, key: MessageKey][] = [
  ["/", "docTitle.catalog"],
  ["/items/:pk", "docTitle.item"],
  ["/bookmarks", "docTitle.bookmarks"],
  ["/maps/:pk", "docTitle.map"],
  ["/apps/:pk/edit", "docTitle.appEdit"],
  ["/datasets/:pk/edit", "docTitle.datasetEdit"],
  ["/pipelines/new", "docTitle.pipelineNew"],
  ["/pipelines/:pk/edit", "docTitle.pipelineEdit"],
  ["/datasets/visual-query/new", "docTitle.visualQueryNew"],
  ["/datasets/visual-query/:pipelinePk/edit", "docTitle.visualQueryEdit"],
  ["/reports", "docTitle.reports"],
  ["/reports/new", "docTitle.reportNew"],
  ["/reports/:pk/edit", "docTitle.reportEdit"],
  ["/analytics/sql", "docTitle.sqlLab"],
  ["/admin/extensions", "docTitle.adminExtensions"],
  ["/admin/collections", "docTitle.adminCollections"],
  ["/admin/harvest", "docTitle.adminHarvest"],
  ["/admin/roles", "docTitle.adminRoles"],
  ["/admin/users", "docTitle.adminUsers"],
  ["/admin/compliance", "docTitle.adminCompliance"],
  ["/admin/infrastructure", "docTitle.adminInfrastructure"],
  ["/internal/kit-gallery", "docTitle.kitGallery"],
  ["/tasks", "docTitle.tasks"],
  ["/settings", "docTitle.settings"],
  ["/apps/:pk/:pageId?", "docTitle.app"],
  ["/embed/:token", "docTitle.embed"],
  ["/sites/:slug", "docTitle.site"],
  ["/public", "docTitle.publicCatalog"],
  ["/public/items/:pk", "docTitle.publicItem"],
  ["/public/datasets/:collectionId", "docTitle.publicDataset"],
];

export function routeTitle(pathname: string): string {
  const hit = ROUTE_TITLES.find(([path]) => matchPath({ path, end: true }, pathname));
  return hit ? t("docTitle.format", { view: t(hit[1]) }) : t("docTitle.appName");
}

/** Pose `document.title` à chaque navigation. Les pages qui fixent leur propre
 * titre (`useDocumentMeta`, sites publics) s'exécutent après et l'emportent. */
export function RouteTitle(): null {
  const { pathname } = useLocation();
  useEffect(() => {
    document.title = routeTitle(pathname);
  }, [pathname]);
  return null;
}
