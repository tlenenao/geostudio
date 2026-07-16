// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCollectionsAdmin, useDeleteCollection, useMe } from "../api/hooks";
import type { CollectionAdmin } from "../api/types";
import { Button } from "../ui/button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { CollectionShareDialog } from "../shell/CollectionShareDialog";
import { EditCollectionDialog } from "../shell/EditCollectionDialog";
import { RegisterCollectionDialog } from "../shell/RegisterCollectionDialog";

export function CollectionsAdminPage() {
  const meQuery = useMe();
  const collectionsQuery = useCollectionsAdmin({ enabled: meQuery.data?.isAdmin === true });
  const deleteCollection = useDeleteCollection();
  const [registerOpen, setRegisterOpen] = useState(false);
  const [editing, setEditing] = useState<CollectionAdmin | null>(null);
  const [deleting, setDeleting] = useState<CollectionAdmin | null>(null);
  const [sharing, setSharing] = useState<CollectionAdmin | null>(null);

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

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await deleteCollection.mutateAsync(deleting.id);
      setDeleting(null);
    } catch {
      // surfaced via deleteCollection.isError
    }
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
      {deleteCollection.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec de la suppression.
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
              <th className="py-2">Actions</th>
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
                <td className="py-2 flex gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={() => setEditing(col)}>
                    Éditer
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setSharing(col)}>
                    Partager
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setDeleting(col)}>
                    Supprimer
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <RegisterCollectionDialog open={registerOpen} onClose={() => setRegisterOpen(false)} />
      {editing && (
        <EditCollectionDialog collection={editing} open={true} onClose={() => setEditing(null)} />
      )}
      {sharing && (
        <CollectionShareDialog collectionId={sharing.id} open={true} onClose={() => setSharing(null)} />
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Supprimer la collection"
        message={deleting ? `Désenregistrer « ${deleting.title} » ? La table PostGIS ne sera pas supprimée.` : ""}
        confirmLabel="Supprimer"
        pending={deleteCollection.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={confirmDelete}
      />
    </div>
  );
}
