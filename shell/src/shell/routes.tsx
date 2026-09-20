// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense } from "react";
import { Routes, Route, Outlet, useNavigate, useParams, useLocation } from "react-router-dom";
import { RequireAuth } from "../auth/RequireAuth";
import { RequirePrivilege } from "../auth/RequirePrivilege";
import { AppLayout } from "./AppLayout";
import { t } from "../i18n";
import { useOpenItem } from "./useOpenItem";

// Découpage par route (Task 8, SP-60/GAP-68) : chaque page lourde part dans
// son propre chunk, chargé seulement quand sa route est visitée — le chunk
// d'entrée ne porte plus que le socle partagé (routeur, chrome, kit UI).
// Patron identique à MapView (Task 7) : lazy() + import().then(pick export
// nommé) — aucune page de shell/src/pages/ n'a d'export default (vérifié par
// grep). <Suspense> unique autour de <Outlet/> dans ProtectedLayout (routes
// protégées) et un second autour du retour de AppRoutes() pour les 4 routes
// hors layout protégé (cf. plus bas) : React affiche le fallback pour
// n'importe quel enfant suspendu, pas seulement le premier rendu.
const CatalogPage = lazy(() =>
  import("../pages/CatalogPage").then((m) => ({ default: m.CatalogPage })),
);
const ItemDetailPage = lazy(() =>
  import("../pages/ItemDetailPage").then((m) => ({ default: m.ItemDetailPage })),
);
const MapEditorPage = lazy(() =>
  import("../pages/MapEditorPage").then((m) => ({ default: m.MapEditorPage })),
);
const AppBuilderPage = lazy(() =>
  import("../pages/AppBuilderPage").then((m) => ({ default: m.AppBuilderPage })),
);
const AppRuntimePage = lazy(() =>
  import("../pages/AppRuntimePage").then((m) => ({ default: m.AppRuntimePage })),
);
const SitePublicPage = lazy(() =>
  import("../pages/SitePublicPage").then((m) => ({ default: m.SitePublicPage })),
);
const PublicItemPage = lazy(() =>
  import("../pages/PublicItemPage").then((m) => ({ default: m.PublicItemPage })),
);
const DatasetPage = lazy(() =>
  import("../pages/DatasetPage").then((m) => ({ default: m.DatasetPage })),
);
const DatasetEditPage = lazy(() =>
  import("../pages/DatasetEditPage").then((m) => ({ default: m.DatasetEditPage })),
);
const PipelineBuilderPage = lazy(() =>
  import("../pages/PipelineBuilderPage").then((m) => ({ default: m.PipelineBuilderPage })),
);
const VisualQueryWizardPage = lazy(() =>
  import("../pages/VisualQueryWizardPage").then((m) => ({ default: m.VisualQueryWizardPage })),
);
const ReportEditPage = lazy(() =>
  import("../pages/ReportEditPage").then((m) => ({ default: m.ReportEditPage })),
);
const SqlLabPage = lazy(() =>
  import("../pages/SqlLabPage").then((m) => ({ default: m.SqlLabPage })),
);
const AdminExtensionsPage = lazy(() =>
  import("../pages/AdminExtensionsPage").then((m) => ({ default: m.AdminExtensionsPage })),
);
const AdminInfrastructurePage = lazy(() =>
  import("../pages/AdminInfrastructurePage").then((m) => ({ default: m.AdminInfrastructurePage })),
);
const CollectionsAdminPage = lazy(() =>
  import("../pages/CollectionsAdminPage").then((m) => ({ default: m.CollectionsAdminPage })),
);
const HarvestSourcesAdminPage = lazy(() =>
  import("../pages/HarvestSourcesAdminPage").then((m) => ({ default: m.HarvestSourcesAdminPage })),
);
const RolesAdminPage = lazy(() =>
  import("../pages/RolesAdminPage").then((m) => ({ default: m.RolesAdminPage })),
);
const ComplianceAdminPage = lazy(() =>
  import("../pages/ComplianceAdminPage").then((m) => ({ default: m.ComplianceAdminPage })),
);
const UsersAdminPage = lazy(() =>
  import("../pages/UsersAdminPage").then((m) => ({ default: m.UsersAdminPage })),
);
const KitGalleryPage = lazy(() =>
  import("../pages/KitGalleryPage").then((m) => ({ default: m.KitGalleryPage })),
);
const UsagePage = lazy(() => import("../pages/UsagePage").then((m) => ({ default: m.UsagePage })));
const SettingsComingSoonPage = lazy(() =>
  import("../pages/SettingsComingSoonPage").then((m) => ({ default: m.SettingsComingSoonPage })),
);
const EmbedPage = lazy(() => import("../pages/EmbedPage").then((m) => ({ default: m.EmbedPage })));

function CatalogRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <CatalogPage
      onOpenItem={onOpenItem}
      openError={openError ? t("routes.openItemError") : undefined}
    />
  );
}

function BookmarksRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <CatalogPage
      onOpenItem={onOpenItem}
      fixedType="bookmark"
      openError={openError ? t("routes.openBookmarkError") : undefined}
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
    <CatalogPage
      onOpenItem={onOpenItem}
      fixedType="report"
      openError={openError ? t("routes.openReportError") : undefined}
    />
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

function EmbedRoute() {
  const { token } = useParams();
  return <EmbedPage token={token!} />;
}

function ProtectedLayout() {
  return (
    <RequireAuth>
      <AppLayout>
        <Suspense fallback={<p role="status">Chargement…</p>}>
          <Outlet />
        </Suspense>
      </AppLayout>
    </RequireAuth>
  );
}

export function AppRoutes() {
  return (
    <Suspense fallback={<p role="status">Chargement…</p>}>
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
          <Route
            path="/analytics/sql"
            element={
              <RequirePrivilege
                privilege="analytics.sql_lab.access"
                deniedMessage={t("routes.analystOnly")}
              >
                <SqlLabPage />
              </RequirePrivilege>
            }
          />
          <Route
            path="/admin/extensions"
            element={
              <RequirePrivilege
                privilege="admin.extensions.manage"
                deniedMessage={t("routes.adminOnly")}
              >
                <AdminExtensionsPage />
              </RequirePrivilege>
            }
          />
          <Route
            path="/admin/collections"
            element={
              <RequirePrivilege
                privilege="admin.collections.manage"
                deniedMessage={t("routes.adminOnly")}
              >
                <CollectionsAdminPage />
              </RequirePrivilege>
            }
          />
          <Route
            path="/admin/harvest"
            element={
              <RequirePrivilege
                privilege="admin.harvest.manage"
                deniedMessage={t("routes.adminOnly")}
              >
                <HarvestSourcesAdminPage />
              </RequirePrivilege>
            }
          />
          <Route
            path="/admin/roles"
            element={
              <RequirePrivilege
                privilege="admin.roles.manage"
                deniedMessage={t("routes.rolesOnly")}
              >
                <RolesAdminPage />
              </RequirePrivilege>
            }
          />
          <Route
            path="/admin/users"
            element={
              <RequirePrivilege
                privilege="admin.users.manage"
                deniedMessage={t("routes.usersOnly")}
              >
                <UsersAdminPage />
              </RequirePrivilege>
            }
          />
          <Route
            path="/admin/compliance"
            element={
              <RequirePrivilege
                privilege="compliance.manage"
                deniedMessage={t("routes.complianceOnly")}
              >
                <ComplianceAdminPage />
              </RequirePrivilege>
            }
          />
          <Route
            path="/admin/infrastructure"
            element={
              <RequirePrivilege
                privilege="settings.instance.manage"
                deniedMessage={t("routes.adminOnly")}
              >
                <AdminInfrastructurePage />
              </RequirePrivilege>
            }
          />
          <Route path="/internal/kit-gallery" element={<KitGalleryPage />} />
          <Route
            path="/tasks"
            element={
              <RequirePrivilege privilege="tasks.view" deniedMessage={t("routes.tasksOnly")}>
                <UsagePage />
              </RequirePrivilege>
            }
          />
          <Route path="/settings" element={<SettingsComingSoonPage />} />
        </Route>
        <Route path="/apps/:pk/:pageId?" element={<AppRuntimeRoute />} />
        <Route path="/embed/:token" element={<EmbedRoute />} />
        <Route path="/sites/:slug" element={<SitePublicRoute />} />
        <Route path="/public/items/:pk" element={<PublicItemRoute />} />
        <Route path="/public/datasets/:collectionId" element={<DatasetRoute />} />
      </Routes>
    </Suspense>
  );
}
