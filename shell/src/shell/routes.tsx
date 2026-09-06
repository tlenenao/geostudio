// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useState } from "react";
import { Routes, Route, Outlet, useNavigate, useParams, useLocation } from "react-router-dom";
import { RequireAuth } from "../auth/RequireAuth";
import { RequirePrivilege } from "../auth/RequirePrivilege";
import { AppLayout } from "./AppLayout";
import { useItemClient } from "../api/ItemClientProvider";
import { encodeAnalyticsContext } from "../lib/analyticsContextUrl";
import type { ResourceType } from "../api/types";

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

function CatalogRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <CatalogPage
      onOpenItem={onOpenItem}
      openError={openError ? "Échec de l'ouverture de l'élément." : undefined}
    />
  );
}

function BookmarksRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <CatalogPage
      onOpenItem={onOpenItem}
      fixedType="bookmark"
      openError={openError ? "Échec de l'ouverture du signet." : undefined}
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
      openError={openError ? "Échec de l'ouverture du rapport." : undefined}
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
                deniedMessage="Accès réservé aux analystes."
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
                deniedMessage="Accès réservé aux administrateurs."
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
                deniedMessage="Accès réservé aux administrateurs."
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
                deniedMessage="Accès réservé aux administrateurs."
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
                deniedMessage="Accès réservé à la gestion des rôles."
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
                deniedMessage="Accès réservé à la gestion des utilisateurs."
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
                deniedMessage="Accès réservé à la conformité (RGPD)."
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
                deniedMessage="Accès réservé aux administrateurs."
              >
                <AdminInfrastructurePage />
              </RequirePrivilege>
            }
          />
          <Route path="/internal/kit-gallery" element={<KitGalleryPage />} />
          <Route
            path="/tasks"
            element={
              <RequirePrivilege
                privilege="tasks.view"
                deniedMessage="Accès réservé — privilège tasks.view requis."
              >
                <UsagePage />
              </RequirePrivilege>
            }
          />
          <Route path="/settings" element={<SettingsComingSoonPage />} />
        </Route>
        <Route path="/apps/:pk/:pageId?" element={<AppRuntimeRoute />} />
        <Route path="/sites/:slug" element={<SitePublicRoute />} />
        <Route path="/public/items/:pk" element={<PublicItemRoute />} />
        <Route path="/public/datasets/:collectionId" element={<DatasetRoute />} />
      </Routes>
    </Suspense>
  );
}
