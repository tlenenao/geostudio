// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import {
  useAddGroupMember,
  useCreateGroup,
  useGroups,
  useSetSharing,
  useSharing,
} from "../api/hooks";
import type { Item, ShareRole } from "../api/types";
import { Button } from "../ui/kit/Button";

// GAP-42/65 : formulaire d'ajout de groupe + contrôle d'ajout de membre par
// groupe. L'API AddMemberRequest attend un userId exact (un UUID), pas un
// nom — GET /users est admin-only (ADMIN_USERS_MANAGE), indisponible à un
// partageur ordinaire (spec §1.2) : pas de recherche par nom possible ici,
// l'aide contextuelle le dit explicitement plutôt que de le masquer.
function AddGroupMemberControl({ groupId, groupTitle }: { groupId: string; groupTitle: string }) {
  const [userId, setUserId] = useState("");
  const addGroupMember = useAddGroupMember();

  async function handleAdd() {
    addGroupMember.reset();
    if (!userId.trim()) return;
    try {
      await addGroupMember.mutateAsync({ groupId, userId: userId.trim() });
      setUserId("");
    } catch {
      /* surfaced via addGroupMember.isError/error */
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <input
          type="text"
          aria-label={`Identifiant utilisateur (${groupTitle})`}
          placeholder="Identifiant utilisateur (UUID)"
          className="h-8 flex-1 rounded-md border border-rule bg-surface px-2 text-xs text-ink"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!userId.trim() || addGroupMember.isPending}
          onClick={() => void handleAdd()}
        >
          {`Ajouter un membre (${groupTitle})`}
        </Button>
      </div>
      {addGroupMember.isError && (
        <p role="alert" className="text-xs text-danger">
          {addGroupMember.error instanceof Error
            ? addGroupMember.error.message
            : "Échec de l'ajout du membre."}
        </p>
      )}
    </div>
  );
}

export function ShareForm({ item, onDone }: { item: Item; onDone: () => void }) {
  const groupsQuery = useGroups();
  const sharingQuery = useSharing(item.pk);
  const setSharing = useSetSharing(item.pk);
  const createGroup = useCreateGroup();

  const [isPublic, setIsPublic] = useState(false);
  const [roles, setRoles] = useState<Record<string, ShareRole | undefined>>({});
  const [newGroupName, setNewGroupName] = useState("");

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
    setSharing.reset();
    const groups = Object.entries(roles)
      .filter(([, role]) => role)
      .map(([groupId, role]) => ({ groupId, role: role as ShareRole }));
    try {
      await setSharing.mutateAsync({ public: isPublic, groups });
      onDone();
    } catch {
      /* surfaced via setSharing.isError */
    }
  }

  async function submitNewGroup() {
    createGroup.reset();
    const name = newGroupName.trim();
    if (!name) return;
    try {
      await createGroup.mutateAsync(name);
      setNewGroupName("");
    } catch {
      /* surfaced via createGroup.isError */
    }
  }

  const loading = groupsQuery.isLoading || sharingQuery.isLoading;
  const failed = groupsQuery.isError || sharingQuery.isError;
  const ready = groupsQuery.isSuccess && sharingQuery.isSuccess;

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-ink">Partager l'élément</h3>
      {loading && <p role="status">Chargement…</p>}
      {failed && (
        <p role="alert" className="text-sm text-danger">
          Erreur de chargement.
        </p>
      )}
      {ready && (
        <>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              aria-label="Public"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            Public (visible par tous)
          </label>

          <div className="flex flex-col gap-3">
            {groupsQuery.data.map((g) => (
              <div key={g.id} className="flex flex-col gap-1 border-b border-rule pb-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <label className="flex items-center gap-2 text-ink">
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
                    onChange={(e) =>
                      setRoles((r) => ({ ...r, [g.id]: e.target.value as ShareRole }))
                    }
                  >
                    <option value="viewer">Lecteur</option>
                    <option value="editor">Éditeur</option>
                  </select>
                </div>
                <AddGroupMemberControl groupId={g.id} groupTitle={g.title} />
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-1 border-t border-rule pt-2">
            <p className="text-xs font-medium text-ink-2">
              Créer un groupe — seul son créateur pourra ensuite y ajouter des membres.
            </p>
            <div className="flex items-center gap-2">
              <input
                type="text"
                aria-label="Nom du nouveau groupe"
                placeholder="Nom du nouveau groupe"
                className="h-8 flex-1 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!newGroupName.trim() || createGroup.isPending}
                onClick={() => void submitNewGroup()}
              >
                Créer le groupe
              </Button>
            </div>
            {createGroup.isError && (
              <p role="alert" className="text-xs text-danger">
                Échec de la création du groupe.
              </p>
            )}
          </div>

          {setSharing.isError && (
            <p role="alert" className="text-sm text-danger">
              Échec du partage.
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onDone}>
              Annuler
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={setSharing.isPending}
              onClick={() => void submit()}
            >
              Enregistrer
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
