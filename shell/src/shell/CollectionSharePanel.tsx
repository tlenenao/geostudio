// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import {
  useCollectionSharing,
  useGroups,
  useInstanceInfo,
  useSetCollectionSharing,
} from "../api/hooks";
import type { ShareRole } from "../api/types";
import { Button } from "../ui/kit/Button";

export function CollectionSharePanel({
  collectionId,
  onClose,
}: {
  collectionId: string;
  onClose: () => void;
}) {
  const groupsQuery = useGroups();
  const sharingQuery = useCollectionSharing(collectionId);
  const setSharing = useSetCollectionSharing(collectionId);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;

  const [isPublic, setIsPublic] = useState(false);
  const [roles, setRoles] = useState<Record<string, ShareRole | undefined>>({});

  useEffect(() => {
    if (!sharingQuery.data) return;
    setIsPublic(sharingQuery.data.public);
    const map: Record<string, ShareRole> = {};
    sharingQuery.data.groups.forEach((g) => {
      map[g.groupId] = g.role;
    });
    setRoles(map);
  }, [sharingQuery.data]);

  async function submit() {
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
    <section aria-label="Partager la collection" className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">Partager la collection</h2>
      {loading && <p role="status">Chargement…</p>}
      {failed && (
        <p role="alert" className="text-sm text-danger">
          Erreur de chargement.
        </p>
      )}
      {ready && (
        <div className="flex flex-col gap-3">
          <label className="flex items-center gap-2 text-sm text-ink">
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
              <div key={g.id} className="flex items-center justify-between gap-2 text-sm text-ink">
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
                  className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
                  disabled={!roles[g.id]}
                  value={roles[g.id] ?? "viewer"}
                  onChange={(e) => setRoles((r) => ({ ...r, [g.id]: e.target.value as ShareRole }))}
                >
                  <option value="viewer">Lecteur</option>
                  <option value="editor">Éditeur</option>
                </select>
              </div>
            ))}
          </div>

          {setSharing.isError && (
            <p role="alert" className="text-sm text-danger">
              Échec du partage.
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Annuler
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={setSharing.isPending || readOnly}
              onClick={() => void submit()}
            >
              Enregistrer
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
