// SPDX-License-Identifier: Apache-2.0
import { Routes, Route, Outlet, useNavigate, useParams } from "react-router-dom";
import { CatalogPage } from "../pages/CatalogPage";
import { ItemDetailPage } from "../pages/ItemDetailPage";
import { MapEditorPage } from "../pages/MapEditorPage";
import { AppBuilderPage } from "../pages/AppBuilderPage";
import { AppRuntimePage } from "../pages/AppRuntimePage";
import { SitePublicPage } from "../pages/SitePublicPage";
import { AdminExtensionsPage } from "../pages/AdminExtensionsPage";
import { CollectionsAdminPage } from "../pages/CollectionsAdminPage";
import { RequireAuth } from "../auth/RequireAuth";
import { AppLayout } from "./AppLayout";

function CatalogRoute() {
  const navigate = useNavigate();
  return (
    <CatalogPage
      onOpenItem={(pk, type) =>
        navigate(type === "map" ? `/maps/${pk}` : `/apps/${pk}/edit`)
      }
    />
  );
}

function ItemDetailRoute() {
  const { pk } = useParams();
  const navigate = useNavigate();
  return (
    <ItemDetailPage
      pk={pk!}
      onDeleted={() => navigate("/")}
      onOpenEditor={(type) => navigate(type === "map" ? `/maps/${pk}` : `/apps/${pk}/edit`)}
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

function AppRuntimeRoute() {
  const { pk, pageId } = useParams();
  return <AppRuntimePage pk={pk!} pageId={pageId} />;
}

function SitePublicRoute() {
  const { slug } = useParams();
  return <SitePublicPage slug={slug!} />;
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
        <Route path="/maps/:pk" element={<MapEditorRoute />} />
        <Route path="/apps/:pk/edit" element={<AppBuilderRoute />} />
        <Route path="/admin/extensions" element={<AdminExtensionsPage />} />
        <Route path="/admin/collections" element={<CollectionsAdminPage />} />
      </Route>
      <Route path="/apps/:pk/:pageId?" element={<AppRuntimeRoute />} />
      <Route path="/sites/:slug" element={<SitePublicRoute />} />
    </Routes>
  );
}
