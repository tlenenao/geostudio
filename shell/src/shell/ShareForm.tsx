// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import {
  useAddGroupMember,
  useCreateGroup,
  useCreateShareLink,
  useGroups,
  useRevokeShareLink,
  useSetSharing,
  useShareLinks,
  useSharing,
} from "../api/hooks";
import type { Item, ShareRole } from "../api/types";
import { Button } from "../ui/kit/Button";
import { t } from "../i18n";

const MAX_SHARE_LINK_TTL_DAYS = 30;

// GAP-12 (chantier 4.23) : section distincte du partage groupe/rôle plat
// ci-dessus — un lien de partage est présenté à un tiers externe, révocable
// à tout moment. La consommation anonyme du lien (côté visiteur sans
// compte) reste hors périmètre (spec §9) : ce panneau ne fait que
// créer/lister/révoquer, il ne rend aucune page publique.
function ShareLinksPanel({ itemId }: { itemId: string }) {
  const linksQuery = useShareLinks(itemId);
  const createLink = useCreateShareLink(itemId);
  const revokeLink = useRevokeShareLink(itemId);
  const [ttlDays, setTtlDays] = useState(7);
  const [lastCreatedUrl, setLastCreatedUrl] = useState<string | null>(null);

  async function handleCreate() {
    createLink.reset();
    setLastCreatedUrl(null);
    try {
      const link = await createLink.mutateAsync(ttlDays);
      setLastCreatedUrl(link.url);
    } catch {
      /* surfaced via createLink.isError */
    }
  }

  return (
    <div className="flex flex-col gap-2 border-t border-rule pt-2">
      <p className="text-xs font-medium text-ink-2">{t("shareForm.linksTitle")}</p>
      {linksQuery.isLoading && <p role="status">{t("common.loading")}</p>}
      {linksQuery.isError && (
        <p role="alert" className="text-xs text-danger">
          {t("shareForm.linksLoadError")}
        </p>
      )}
      {linksQuery.data && linksQuery.data.length > 0 && (
        <ul className="flex flex-col gap-1 text-xs">
          {linksQuery.data.map((link) => {
            const expired = new Date(link.expiresAt).getTime() < Date.now();
            const status = link.revoked
              ? t("shareForm.linkStatusRevoked")
              : expired
                ? t("shareForm.linkStatusExpired")
                : t("shareForm.linkStatusActive");
            return (
              <li key={link.id} className="flex items-center justify-between gap-2">
                <span>
                  {t("shareForm.linkSummaryTemplate", {
                    id: link.id,
                    status,
                    expiresAt: link.expiresAt,
                  })}
                </span>
                {!link.revoked && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={revokeLink.isPending}
                    onClick={() => revokeLink.mutate(link.id)}
                  >
                    {t("shareForm.revokeButton")}
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1 text-xs text-ink">
          <input
            type="number"
            aria-label={t("shareForm.ttlAria")}
            min={1}
            max={MAX_SHARE_LINK_TTL_DAYS}
            className="h-8 w-16 rounded-md border border-rule bg-surface px-2 text-xs text-ink"
            value={ttlDays}
            onChange={(e) => setTtlDays(Number(e.target.value))}
          />
          {t("shareForm.ttlUnit")}
        </label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={createLink.isPending || ttlDays < 1 || ttlDays > MAX_SHARE_LINK_TTL_DAYS}
          onClick={() => void handleCreate()}
        >
          {t("shareForm.createLinkButton")}
        </Button>
      </div>
      {createLink.isError && (
        <p role="alert" className="text-xs text-danger">
          {t("shareForm.createLinkFailed")}
        </p>
      )}
      {lastCreatedUrl && (
        <p className="text-xs text-ink">
          {t("shareForm.linkCreatedPrefix")}
          <span className="break-all">{lastCreatedUrl}</span>
        </p>
      )}
    </div>
  );
}

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
          aria-label={t("shareForm.memberIdAria", { group: groupTitle })}
          placeholder={t("shareForm.memberIdPlaceholder")}
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
          {t("shareForm.addMemberButton", { group: groupTitle })}
        </Button>
      </div>
      {addGroupMember.isError && (
        <p role="alert" className="text-xs text-danger">
          {addGroupMember.error instanceof Error
            ? addGroupMember.error.message
            : t("shareForm.addMemberFailedGeneric")}
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
      <h3 className="text-sm font-semibold text-ink">{t("shareForm.heading")}</h3>
      {loading && <p role="status">{t("common.loading")}</p>}
      {failed && (
        <p role="alert" className="text-sm text-danger">
          {t("sharePanel.loadError")}
        </p>
      )}
      {ready && (
        <>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              aria-label={t("collectionsAdmin.columnPublic")}
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            {t("sharePanel.publicLabel")}
          </label>

          <div className="flex flex-col gap-3">
            {groupsQuery.data.map((g) => (
              <div key={g.id} className="flex flex-col gap-1 border-b border-rule pb-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <label className="flex items-center gap-2 text-ink">
                    <input
                      type="checkbox"
                      aria-label={t("sharePanel.groupAria", { group: g.title })}
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
                    aria-label={t("sharePanel.roleAria", { group: g.title })}
                    className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
                    disabled={!roles[g.id]}
                    value={roles[g.id] ?? "viewer"}
                    onChange={(e) =>
                      setRoles((r) => ({ ...r, [g.id]: e.target.value as ShareRole }))
                    }
                  >
                    <option value="viewer">{t("sharePanel.roleViewer")}</option>
                    <option value="editor">{t("sharePanel.roleEditor")}</option>
                  </select>
                </div>
                <AddGroupMemberControl groupId={g.id} groupTitle={g.title} />
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-1 border-t border-rule pt-2">
            <p className="text-xs font-medium text-ink-2">{t("shareForm.createGroupHelp")}</p>
            <div className="flex items-center gap-2">
              <input
                type="text"
                aria-label={t("shareForm.newGroupNameLabel")}
                placeholder={t("shareForm.newGroupNameLabel")}
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
                {t("shareForm.createGroupButton")}
              </Button>
            </div>
            {createGroup.isError && (
              <p role="alert" className="text-xs text-danger">
                {t("shareForm.createGroupFailed")}
              </p>
            )}
          </div>

          <ShareLinksPanel itemId={item.pk} />

          {setSharing.isError && (
            <p role="alert" className="text-sm text-danger">
              {t("sharePanel.shareFailed")}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onDone}>
              {t("confirmDialog.cancel")}
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={setSharing.isPending}
              onClick={() => void submit()}
            >
              {t("common.save")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
