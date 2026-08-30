// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Routes, Route, Outlet, useNavigate, useParams, useLocation } from "react-router-dom";
import { CatalogPage } from "../pages/CatalogPage";
import { ItemDetailPage } from "../pages/ItemDetailPage";
import { MapEditorPage } from "../pages/MapEditorPage";
import { AppBuilderPage } from "../pages/AppBuilderPage";
import { AppRuntimePage } from "../pages/AppRuntimePage";
import { SitePublicPage } from "../pages/SitePublicPage";
import { PublicItemPage } from "../pages/PublicItemPage";
import { DatasetPage } from "../pages/DatasetPage";
import { DatasetEditPage } from "../pages/DatasetEditPage";
import { PipelineBuilderPage } from "../pages/PipelineBuilderPage";
import { VisualQueryWizardPage } from "../pages/VisualQueryWizardPage";
import { ReportEditPage } from "../pages/ReportEditPage";
import { SqlLabPage } from "../pages/SqlLabPage";
import { AdminExtensionsPage } from "../pages/AdminExtensionsPage";
import { CollectionsAdminPage } from "../pages/CollectionsAdminPage";
import { HarvestSourcesAdminPage } from "../pages/HarvestSourcesAdminPage";
import { KitGalleryPage } from "../pages/KitGalleryPage";
import { RequireAuth } from "../auth/RequireAuth";
import { AppLayout } from "./AppLayout";
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
function useOpenItem() {
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

function CatalogRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <>
      {openError && (
        <p role="alert" className="text-sm text-red-600">
          Échec de l'ouverture de l'élément.
        </p>
      )}
      <CatalogPage onOpenItem={onOpenItem} />
    </>
  );
}

function BookmarksRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <>
      {openError && (
        <p role="alert" className="text-sm text-red-600">
          Échec de l'ouverture du signet.
        </p>
      )}
      <CatalogPage onOpenItem={onOpenItem} fixedType="bookmark" />
    </>
  );
}

function ItemDetailRoute() {
  const { pk } = useParams();
  const navigate = useNavigate();
  return (
    <ItemDetailPage
      pk={pk!}
      onDeleted={() => navigate("/")}
      onOpenEditor={(type) =>
        navigate(
          type === "map"
            ? `/maps/${pk}`
            : type === "dataset"
              ? `/datasets/${pk}/edit`
              : type === "pipeline"
                ? `/pipelines/${pk}/edit`
                : `/apps/${pk}/edit`,
        )
      }
    />
  );
}

function MapEditorRoute() {
  const { pk } = useParams();
  return <MapEditorPage pk={pk!} />;
}

function AppBuilderRoute() {
  const { pk } = useParams();
  return <AppBuilderPage pk={pk!} />;
}

function DatasetEditRoute() {
  const { pk } = useParams();
  return <DatasetEditPage pk={pk!} />;
}

function PipelineNewRoute() {
  const location = useLocation();
  const title = (location.state as { title?: string } | null)?.title;
  return <PipelineBuilderPage pk={null} initialTitle={title} />;
}

function PipelineEditRoute() {
  const { pk } = useParams();
  return <PipelineBuilderPage pk={pk!} />;
}

function VisualQueryWizardNewRoute() {
  const location = useLocation();
  const title = (location.state as { title?: string } | null)?.title;
  return <VisualQueryWizardPage pipelinePk={null} initialTitle={title} />;
}

function VisualQueryWizardEditRoute() {
  const { pipelinePk } = useParams();
  return <VisualQueryWizardPage pipelinePk={pipelinePk!} />;
}

function ReportNewRoute() {
  const location = useLocation();
  const bookmarkItemId = (location.state as { bookmarkItemId?: string } | null)?.bookmarkItemId;
  return <ReportEditPage pk={null} initialBookmarkItemId={bookmarkItemId} />;
}

function ReportEditRoute() {
  const { pk } = useParams();
  return <ReportEditPage pk={pk!} />;
}

function ReportsRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <>
      {openError && (
        <p role="alert" className="text-sm text-red-600">
          Échec de l'ouverture du rapport.
        </p>
      )}
      <CatalogPage onOpenItem={onOpenItem} fixedType="report" />
    </>
  );
}

function AppRuntimeRoute() {
  const { pk, pageId } = useParams();
  return <AppRuntimePage pk={pk!} pageId={pageId} />;
}

function SitePublicRoute() {
  const { slug } = useParams();
  return <SitePublicPage slug={slug!} />;
}

function PublicItemRoute() {
  const { pk } = useParams();
  return <PublicItemPage pk={pk!} />;
}

function DatasetRoute() {
  const { collectionId } = useParams();
  return <DatasetPage collectionId={collectionId!} />;
}

function ProtectedLayout() {
  return (
    <RequireAuth>
      <AppLayout>
        <Outlet />
      </AppLayout>
    </RequireAuth>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<CatalogRoute />} />
        <Route path="/items/:pk" element={<ItemDetailRoute />} />
        <Route path="/bookmarks" element={<BookmarksRoute />} />
        <Route path="/maps/:pk" element={<MapEditorRoute />} />
        <Route path="/apps/:pk/edit" element={<AppBuilderRoute />} />
        <Route path="/datasets/:pk/edit" element={<DatasetEditRoute />} />
        <Route path="/pipelines/new" element={<PipelineNewRoute />} />
        <Route path="/pipelines/:pk/edit" element={<PipelineEditRoute />} />
        <Route path="/datasets/visual-query/new" element={<VisualQueryWizardNewRoute />} />
        <Route
          path="/datasets/visual-query/:pipelinePk/edit"
          element={<VisualQueryWizardEditRoute />}
        />
        <Route path="/reports" element={<ReportsRoute />} />
        <Route path="/reports/new" element={<ReportNewRoute />} />
        <Route path="/reports/:pk/edit" element={<ReportEditRoute />} />
        <Route path="/analytics/sql" element={<SqlLabPage />} />
        <Route path="/admin/extensions" element={<AdminExtensionsPage />} />
        <Route path="/admin/collections" element={<CollectionsAdminPage />} />
        <Route path="/admin/harvest" element={<HarvestSourcesAdminPage />} />
        <Route path="/internal/kit-gallery" element={<KitGalleryPage />} />
      </Route>
      <Route path="/apps/:pk/:pageId?" element={<AppRuntimeRoute />} />
      <Route path="/sites/:slug" element={<SitePublicRoute />} />
      <Route path="/public/items/:pk" element={<PublicItemRoute />} />
      <Route path="/public/datasets/:collectionId" element={<DatasetRoute />} />
    </Routes>
  );
}
