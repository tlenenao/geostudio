import { Routes, Route, useNavigate, useParams } from "react-router-dom";
import { CatalogPage } from "../pages/CatalogPage";
import { ItemDetailPage } from "../pages/ItemDetailPage";
import { MapEditorPage } from "../pages/MapEditorPage";

function CatalogRoute() {
  const navigate = useNavigate();
  return (
    <CatalogPage
      onOpenItem={(pk, type) => navigate(type === "map" ? `/maps/${pk}` : `/items/${pk}`)}
    />
  );
}

function ItemDetailRoute() {
  const { pk } = useParams();
  const navigate = useNavigate();
  return <ItemDetailPage pk={pk!} onDeleted={() => navigate("/")} onOpenEditor={() => navigate(`/maps/${pk}`)} />;
}

function MapEditorRoute() {
  const { pk } = useParams();
  return <MapEditorPage pk={pk!} />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<CatalogRoute />} />
      <Route path="/items/:pk" element={<ItemDetailRoute />} />
      <Route path="/maps/:pk" element={<MapEditorRoute />} />
    </Routes>
  );
}
