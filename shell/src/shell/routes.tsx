// SPDX-License-Identifier: Apache-2.0
import { Routes, Route, Outlet, useNavigate, useParams } from "react-router-dom";
import { CatalogPage } from "../pages/CatalogPage";
import { ItemDetailPage } from "../pages/ItemDetailPage";
import { MapEditorPage } from "../pages/MapEditorPage";
import { AppBuilderPage } from "../pages/AppBuilderPage";
import { AppRuntimePage } from "../pages/AppRuntimePage";
import { SitePublicPage } from "../pages/SitePublicPage";
import { PublicItemPage } from "../pages/PublicItemPage";
import { DatasetPage } from "../pages/DatasetPage";
import { DatasetEditPage } from "../pages/DatasetEditPage";
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
function useOpenItem() {
  const navigate = useNavigate();
  const client = useItemClient();
  return async (pk: string, type: ResourceType) => {
    if (type === "bookmark") {
      const bookmark = await client.getBookmarkConfig(pk);
      const ctx = encodeAnalyticsContext({
        timeRange: bookmark.timeRange, extent: bookmark.extent, crossFilter: bookmark.crossFilter,
      });
      navigate(`/apps/${encodeURIComponent(bookmark.appId)}/${encodeURIComponent(bookmark.pageId)}?ctx=${ctx}`);
      return;
    }
    navigate(type === "map" ? `/maps/${pk}` : type === "dataset" ? `/datasets/${pk}/edit` : `/apps/${pk}/edit`);
  };
}

function CatalogRoute() {
  const onOpenItem = useOpenItem();
  return <CatalogPage onOpenItem={onOpenItem} />;
}

function BookmarksRoute() {
  const onOpenItem = useOpenItem();
  return <CatalogPage onOpenItem={onOpenItem} fixedType="bookmark" />;
}

function ItemDetailRoute() {
  const { pk } = useParams();
  const navigate = useNavigate();
  return (
    <ItemDetailPage
      pk={pk!}
      onDeleted={() => navigate("/")}
      onOpenEditor={(type) => navigate(type === "map" ? `/maps/${pk}` : type === "dataset" ? `/datasets/${pk}/edit` : `/apps/${pk}/edit`)}
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
