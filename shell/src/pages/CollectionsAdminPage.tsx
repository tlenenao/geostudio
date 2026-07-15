import { useState } from "react";
import { useCollectionsAdmin, useMe } from "../api/hooks";
import { Button } from "../ui/button";
import { RegisterCollectionDialog } from "../shell/RegisterCollectionDialog";

export function CollectionsAdminPage() {
  const meQuery = useMe();
  const collectionsQuery = useCollectionsAdmin({ enabled: meQuery.data?.isAdmin === true });
  const [registerOpen, setRegisterOpen] = useState(false);

  if (meQuery.isLoading) {
    return <p role="status">Chargement…</p>;
  }
  if (meQuery.data?.isAdmin !== true) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Accès réservé aux administrateurs.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">Collections</h1>
        <Button size="sm" onClick={() => setRegisterOpen(true)}>
          Enregistrer une table
        </Button>
      </div>
      {collectionsQuery.isLoading && <p role="status">Chargement…</p>}
      {collectionsQuery.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec du chargement des collections.
        </p>
      )}
      {collectionsQuery.data && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="py-2">Titre</th>
              <th className="py-2">Table</th>
              <th className="py-2">Public</th>
              <th className="py-2">Éditable</th>
              <th className="py-2">Entités</th>
              <th className="py-2">Propriétaire</th>
            </tr>
          </thead>
          <tbody>
            {collectionsQuery.data.map((col) => (
              <tr key={col.id} className="border-b border-slate-100">
                <td className="py-2">{col.title}</td>
                <td className="py-2 text-xs text-slate-500">{col.tableName}</td>
                <td className="py-2">{col.isPublic ? "Oui" : "Non"}</td>
                <td className="py-2">{col.editable ? "Oui" : "Non"}</td>
                <td className="py-2">{col.featureCount ?? "—"}</td>
                <td className="py-2">{col.owner ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <RegisterCollectionDialog open={registerOpen} onClose={() => setRegisterOpen(false)} />
    </div>
  );
}
