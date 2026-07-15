// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useCollectionSharing, useGroups, useSetCollectionSharing } from "../api/hooks";
import type { ShareRole } from "../api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";

export function CollectionShareDialog({
  collectionId,
  open,
  onClose,
}: {
  collectionId: string;
  open: boolean;
  onClose: () => void;
}) {
  const groupsQuery = useGroups({ enabled: open });
  const sharingQuery = useCollectionSharing(collectionId, { enabled: open });
  const setSharing = useSetCollectionSharing(collectionId);

  const [isPublic, setIsPublic] = useState(false);
  const [roles, setRoles] = useState<Record<string, ShareRole | undefined>>({});

  useEffect(() => {
    if (!open || !sharingQuery.data) return;
    setIsPublic(sharingQuery.data.public);
    const map: Record<string, ShareRole> = {};
    sharingQuery.data.groups.forEach((g) => {
      map[g.groupId] = g.role;
    });
    setRoles(map);
  }, [open, sharingQuery.data]);

  async function submit() {
    setSharing.reset();
    const groups = Object.entries(roles)
      .filter(([, role]) => role)
      .map(([groupId, role]) => ({ groupId, role: role as ShareRole }));
    try {
      await setSharing.mutateAsync({ public: isPublic, groups });
      onClose();
    } catch {
      /* surfaced via setSharing.isError */
    }
  }

  const loading = groupsQuery.isLoading || sharingQuery.isLoading;
  const failed = groupsQuery.isError || sharingQuery.isError;
  const ready = groupsQuery.isSuccess && sharingQuery.isSuccess;

  return (
    <Dialog open={open} onClose={onClose} title="Partager la collection">
      {loading && <p role="status">Chargement…</p>}
      {failed && (
        <p role="alert" className="text-sm text-red-600">
          Erreur de chargement.
        </p>
      )}
      {ready && (
        <div className="flex flex-col gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              aria-label="Public"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            Public (visible par tous)
          </label>

          <div className="flex flex-col gap-2">
            {groupsQuery.data.map((g) => (
              <div key={g.id} className="flex items-center justify-between gap-2 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={`Groupe ${g.title}`}
                    checked={!!roles[g.id]}
                    onChange={(e) =>
                      setRoles((r) => ({
                        ...r,
                        [g.id]: e.target.checked ? (r[g.id] ?? "viewer") : undefined,
                      }))
                    }
                  />
                  {g.title}
                </label>
                <select
                  aria-label={`Rôle ${g.title}`}
                  className="h-8 rounded-md border border-slate-300 bg-white px-2 text-sm"
                  disabled={!roles[g.id]}
                  value={roles[g.id] ?? "viewer"}
                  onChange={(e) =>
                    setRoles((r) => ({ ...r, [g.id]: e.target.value as ShareRole }))
                  }
                >
                  <option value="viewer">Lecteur</option>
                  <option value="editor">Éditeur</option>
                </select>
              </div>
            ))}
          </div>

          {setSharing.isError && (
            <p role="alert" className="text-sm text-red-600">
              Échec du partage.
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Annuler
            </Button>
            <Button type="button" size="sm" disabled={setSharing.isPending} onClick={submit}>
              Enregistrer
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
