import { Routes, Route, useNavigate, useParams } from "react-router-dom";
import { CatalogPage } from "../pages/CatalogPage";
import { ItemDetailPage } from "../pages/ItemDetailPage";

function CatalogRoute() {
  const navigate = useNavigate();
  return <CatalogPage onOpenItem={(pk) => navigate(`/items/${pk}`)} />;
}

function ItemDetailRoute() {
  const { pk } = useParams();
  const navigate = useNavigate();
  return <ItemDetailPage pk={pk!} onDeleted={() => navigate("/")} />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<CatalogRoute />} />
      <Route path="/items/:pk" element={<ItemDetailRoute />} />
    </Routes>
  );
}
