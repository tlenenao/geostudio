// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useDeleteHarvestSource, useHarvestSources, useMe, useRunHarvestSource } from "../api/hooks";
import type { HarvestSource } from "../api/types";
import { Button } from "../ui/button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { CreateHarvestSourceDialog } from "../shell/CreateHarvestSourceDialog";
import { EditHarvestSourceDialog } from "../shell/EditHarvestSourceDialog";

export function HarvestSourcesAdminPage() {
  const meQuery = useMe();
  const sourcesQuery = useHarvestSources({ enabled: meQuery.data?.isAdmin === true });
  const deleteSource = useDeleteHarvestSource();
  const runSource = useRunHarvestSource();
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<HarvestSource | null>(null);
  const [deleting, setDeleting] = useState<HarvestSource | null>(null);

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
      await deleteSource.mutateAsync(deleting.id);
      setDeleting(null);
    } catch {
      // surfaced via deleteSource.isError
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">Moissonnage</h1>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          Ajouter une source
        </Button>
      </div>
      {sourcesQuery.isLoading && <p role="status">Chargement…</p>}
      {sourcesQuery.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec du chargement des sources.
        </p>
      )}
      {deleteSource.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec de la suppression.
        </p>
      )}
      {sourcesQuery.data && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="py-2">Type</th>
              <th className="py-2">URL</th>
              <th className="py-2">Mode</th>
              <th className="py-2">Actif</th>
              <th className="py-2">Dernier statut</th>
              <th className="py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sourcesQuery.data.map((source) => (
              <tr key={source.id} className="border-b border-slate-100">
                <td className="py-2">{source.type}</td>
                <td className="py-2 text-xs text-slate-500">{source.url}</td>
                <td className="py-2">{source.mode}</td>
                <td className="py-2">{source.enabled ? "Oui" : "Non"}</td>
                <td className="py-2">{source.lastStatus ?? "—"}</td>
                <td className="py-2 flex gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={() => runSource.mutate(source.id)}>
                    Moissonner maintenant
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setEditing(source)}>
                    Éditer
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setDeleting(source)}>
                    Supprimer
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <CreateHarvestSourceDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      {editing && (
        <EditHarvestSourceDialog source={editing} open={true} onClose={() => setEditing(null)} />
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Supprimer la source"
        message={deleting ? `Supprimer la source « ${deleting.url} » ? Les items/collections déjà produits survivent.` : ""}
        confirmLabel="Supprimer"
        pending={deleteSource.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={confirmDelete}
      />
    </div>
  );
}
