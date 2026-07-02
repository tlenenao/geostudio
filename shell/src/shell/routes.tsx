import { Routes, Route, useNavigate, useParams } from "react-router-dom";
import { CatalogPage } from "../pages/CatalogPage";
import { ItemDetailPage } from "../pages/ItemDetailPage";
import { MapEditorPage } from "../pages/MapEditorPage";
import { AppBuilderPage } from "../pages/AppBuilderPage";
import { AppRuntimePage } from "../pages/AppRuntimePage";

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
  const { pk } = useParams();
  return <AppRuntimePage pk={pk!} />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<CatalogRoute />} />
      <Route path="/items/:pk" element={<ItemDetailRoute />} />
      <Route path="/maps/:pk" element={<MapEditorRoute />} />
      <Route path="/apps/:pk/edit" element={<AppBuilderRoute />} />
      <Route path="/apps/:pk" element={<AppRuntimeRoute />} />
    </Routes>
  );
}
