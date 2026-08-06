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
import { SqlLabPage } from "../pages/SqlLabPage";
import { AdminExtensionsPage } from "../pages/AdminExtensionsPage";
import { CollectionsAdminPage } from "../pages/CollectionsAdminPage";
import { HarvestSourcesAdminPage } from "../pages/HarvestSourcesAdminPage";
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
  const onOpenItem = async (pk: string, type: ResourceType) => {
    if (type === "bookmark") {
      try {
        const bookmark = await client.getBookmarkConfig(pk);
        const ctx = encodeAnalyticsContext({
          timeRange: bookmark.timeRange, extent: bookmark.extent, crossFilter: bookmark.crossFilter,
        });
        setOpenError(false);
        navigate(`/apps/${encodeURIComponent(bookmark.appId)}/${encodeURIComponent(bookmark.pageId)}?ctx=${ctx}`);
      } catch {
        setOpenError(true);
      }
      return;
    }
    if (type === "pipeline") {
      navigate(`/pipelines/${pk}/edit`);
      return;
    }
    navigate(type === "map" ? `/maps/${pk}` : type === "dataset" ? `/datasets/${pk}/edit` : `/apps/${pk}/edit`);
  };
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
      onOpenEditor={(type) => navigate(
        type === "map" ? `/maps/${pk}` :
        type === "dataset" ? `/datasets/${pk}/edit` :
        type === "pipeline" ? `/pipelines/${pk}/edit` :
        `/apps/${pk}/edit`
      )}
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
        <Route path="/analytics/sql" element={<SqlLabPage />} />
        <Route path="/admin/extensions" element={<AdminExtensionsPage />} />
        <Route path="/admin/collections" element={<CollectionsAdminPage />} />
        <Route path="/admin/harvest" element={<HarvestSourcesAdminPage />} />
      </Route>
      <Route path="/apps/:pk/:pageId?" element={<AppRuntimeRoute />} />
      <Route path="/sites/:slug" element={<SitePublicRoute />} />
      <Route path="/public/items/:pk" element={<PublicItemRoute />} />
      <Route path="/public/datasets/:collectionId" element={<DatasetRoute />} />
    </Routes>
  );
}
