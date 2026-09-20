// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useItemClient } from "../api/ItemClientProvider";
import { encodeAnalyticsContext } from "../lib/analyticsContextUrl";
import type { ResourceType } from "../api/types";

// Shared by CatalogRoute (general catalog) and BookmarksRoute ("Mes vues"):
// a bookmark has no editor (SP-14m — no edit flow for this kind), so opening
// one fetches its saved app/page/context and replays it via ?ctx=, instead
// of navigating to an editor route like every other kind below.
//
// The fetch (getBookmarkConfig) can fail — e.g. the bookmark's config row was
// deleted while the item survived, or a transient network error — and
// CatalogPage's onOpenItem contract is a fire-and-forget callback (ItemCard
// calls it without await/.catch()), so a rejection here would otherwise be an
// unhandled promise rejection with no feedback to the user. Catch it and
// surface it the same way HarvestSourcesAdminPage surfaces a failed mutation:
// a local error flag rendered as a `role="alert"` paragraph.
export function useOpenItem() {
  const navigate = useNavigate();
  const client = useItemClient();
  const [openError, setOpenError] = useState(false);
  const openItemAsync = async (pk: string, type: ResourceType) => {
    if (type === "bookmark") {
      try {
        const bookmark = await client.getBookmarkConfig(pk);
        const ctx = encodeAnalyticsContext({
          timeRange: bookmark.timeRange,
          extent: bookmark.extent,
          crossFilter: bookmark.crossFilter,
        });
        setOpenError(false);
        navigate(
          `/apps/${encodeURIComponent(bookmark.appId)}/${encodeURIComponent(bookmark.pageId)}?ctx=${ctx}`,
        );
      } catch {
        setOpenError(true);
      }
      return;
    }
    if (type === "pipeline") {
      navigate(`/pipelines/${pk}/edit`);
      return;
    }
    if (type === "report") {
      navigate(`/reports/${pk}/edit`);
      return;
    }
    if (type === "tileset3d" || type === "terrain3d") {
      // Un item de contenu hébergé (tileset 3D, DEM) n'a pas de layout :
      // le fallback générique `/apps/{pk}/edit` ouvrirait le builder d'app
      // sur une config vide. Sa fiche d'item est la bonne destination.
      navigate(`/items/${pk}`);
      return;
    }
    if (type === "alert") {
      // Une règle d'alerte n'a pas d'écran propre : elle s'édite dans la
      // section « Alertes » de la page de son dataset. Même patron async
      // que `bookmark` ci-dessus, y compris le catch — l'appelant est un
      // `(pk, type) => void` fire-and-forget, une promesse rejetée y serait
      // une unhandled rejection sans retour utilisateur.
      try {
        const rule = await client.getAlertRuleConfig(pk);
        setOpenError(false);
        navigate(`/datasets/${encodeURIComponent(rule.datasetItemId)}/edit`);
      } catch {
        setOpenError(true);
      }
      return;
    }
    if (type === "external") {
      // Item moissonné : aucune config éditable, le repli générique
      // /apps/{pk}/edit ouvrirait le builder sur une config vide. Même
      // raison que tileset3d/terrain3d ci-dessus.
      navigate(`/items/${pk}`);
      return;
    }
    navigate(
      type === "map"
        ? `/maps/${pk}`
        : type === "dataset"
          ? `/datasets/${pk}/edit`
          : `/apps/${pk}/edit`,
    );
  };
  // Adaptateur synchrone : CatalogPage attend `(pk, type) => void`, pas une
  // Promise (les 3 call sites la passent directement comme handler).
  const onOpenItem = (pk: string, type: ResourceType) => void openItemAsync(pk, type);
  return { onOpenItem, openError };
}
