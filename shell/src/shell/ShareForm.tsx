// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import {
  useAddGroupMember,
  useCollectionSharing,
  useCreateGroup,
  useCreateShareLink,
  useDeleteGroup,
  useGroupMembers,
  useGroups,
  useRemoveGroupMember,
  useRenameGroup,
  useRevokeShareLink,
  useSetCollectionSharing,
  useSetSharing,
  useShareLinks,
  useSharing,
  useUserDirectory,
} from "../api/hooks";
import type { Group, Item, ShareLinkInfo, ShareRole } from "../api/types";
import { Button } from "../ui/kit/Button";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";
import { plural, t } from "../i18n";
import { useReferencedCollectionIds } from "./referencedCollections";
import { LoadingState } from "../ui/kit/LoadingState";
import { formatDateTime } from "../lib/format";
import "../i18n/domains/admin";
import "../i18n/domains/misc";

const MAX_SHARE_LINK_TTL_DAYS = 30;

// D52 : copie dans le presse-papiers pour le lien de partage et le snippet
// embed. `navigator.clipboard.writeText` requiert un contexte sécurisé
// (HTTPS ou localhost) — repli sur `execCommand("copy")` (dépréciée mais
// toujours fonctionnelle) sinon.
export async function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const el = document.createElement("textarea");
  el.value = text;
  el.style.position = "fixed";
  el.style.opacity = "0";
  document.body.appendChild(el);
  el.select();
  document.execCommand("copy");
  document.body.removeChild(el);
}

// Le cœur sérialise des datetimes UTC naïfs (sans fuseau) : sans « Z », le
// navigateur les lirait en heure locale.
function parseUtc(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
}

function formatUtc(iso: string): string {
  return formatDateTime(parseUtc(iso));
}

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
  const [lastCreatedToken, setLastCreatedToken] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<"link" | "embed" | null>(null);

  const links = linksQuery.data ?? [];
  const isInactive = (link: ShareLinkInfo) =>
    link.revoked || parseUtc(link.expiresAt).getTime() < Date.now();
  const active = links.filter((l) => !isInactive(l));
  const inactive = links.filter(isInactive);

  function renderLink(link: ShareLinkInfo) {
    const status = link.revoked
      ? t("shareForm.linkStatusRevoked")
      : isInactive(link)
        ? t("shareForm.linkStatusExpired")
        : t("shareForm.linkStatusActive");
    return (
      <li key={link.id} className="flex items-center justify-between gap-2">
        <span>
          {t("shareForm.linkSummaryTemplate", {
            createdAt: link.createdAt ? formatUtc(link.createdAt) : "—",
            createdBy: link.createdBy || "—",
            status,
            expiresAt: formatUtc(link.expiresAt),
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
  }

  function handleCopy(field: "link" | "embed", text: string) {
    void copyToClipboard(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  }

  async function handleCreate() {
    createLink.reset();
    setLastCreatedUrl(null);
    setLastCreatedToken(null);
    try {
      const link = await createLink.mutateAsync(ttlDays);
      setLastCreatedUrl(link.url);
      setLastCreatedToken(link.token);
    } catch {
      /* surfaced via createLink.isError */
    }
  }

  return (
    <div className="flex flex-col gap-2 border-t border-rule pt-2">
      <p className="text-xs font-medium text-ink-2">{t("shareForm.linksTitle")}</p>
      {linksQuery.isLoading && <LoadingState />}
      {linksQuery.isError && (
        <p role="alert" className="text-xs text-danger">
          {t("shareForm.linksLoadError")}
        </p>
      )}
      {active.length > 0 && (
        <ul className="flex flex-col gap-1 text-xs">{active.map(renderLink)}</ul>
      )}
      {inactive.length > 0 && (
        <details className="text-xs text-ink-2">
          <summary>{t("shareForm.inactiveLinks", { count: inactive.length })}</summary>
          <ul className="flex flex-col gap-1">{inactive.map(renderLink)}</ul>
        </details>
      )}
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1 text-xs text-ink">
          {/* eslint-disable-next-line geostudio/label-no-aria-label -- le texte visible n'est que l'unité (jours) ; le nom accessible la contient */}
          <input
            type="number"
            aria-label={t("shareForm.ttlAria")}
            min={1}
            max={MAX_SHARE_LINK_TTL_DAYS}
            className="h-9 w-16 rounded-md border border-control bg-surface px-2 text-xs text-ink"
            value={ttlDays}
            onChange={(e) => setTtlDays(Number(e.target.value))}
          />
          {t(plural(ttlDays, "shareForm.ttlUnitOne", "shareForm.ttlUnitMany"))}
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
        <p className="flex items-center gap-1 text-xs text-ink">
          {t("shareForm.linkCreatedPrefix")}
          <span className="break-all">{lastCreatedUrl}</span>
          <button
            type="button"
            aria-label={t("shareForm.copyLinkAria")}
            className="text-ink-2 hover:text-ink"
            onClick={() => handleCopy("link", lastCreatedUrl)}
          >
            {copiedField === "link" ? <Check size={14} /> : <Copy size={14} />}
          </button>
          {copiedField === "link" && (
            <span aria-live="polite" className="text-ink-2">
              {t("shareForm.copiedFeedback")}
            </span>
          )}
        </p>
      )}
      {lastCreatedToken &&
        (() => {
          const embedSnippet = `<iframe src="${window.location.origin}/embed/${lastCreatedToken}" width="100%" height="600" style="border:0" loading="lazy"></iframe>`;
          return (
            <div className="flex flex-col gap-1 border-t border-rule pt-2">
              <p className="flex items-center gap-1 text-xs font-medium text-ink-2">
                {t("shareForm.embedTitle")}
                <button
                  type="button"
                  aria-label={t("shareForm.copyEmbedAria")}
                  className="text-ink-2 hover:text-ink"
                  onClick={() => handleCopy("embed", embedSnippet)}
                >
                  {copiedField === "embed" ? <Check size={14} /> : <Copy size={14} />}
                </button>
                {copiedField === "embed" && (
                  <span aria-live="polite" className="font-normal">
                    {t("shareForm.copiedFeedback")}
                  </span>
                )}
              </p>
              <textarea
                readOnly
                aria-label={t("shareForm.embedSnippetAria")}
                className="h-20 w-full rounded-md border border-rule bg-surface p-2 font-mono text-xs text-ink"
                value={embedSnippet}
              />
            </div>
          );
        })()}
    </div>
  );
}

// j13-005 : ajout de membre par recherche dans l'annuaire restreint du tenant
// (GET /users/directory, catalog.manage) — plus d'UUID à connaître.
function AddGroupMemberControl({ groupId, groupTitle }: { groupId: string; groupTitle: string }) {
  const [q, setQ] = useState("");
  const directory = useUserDirectory(q.trim());
  const addGroupMember = useAddGroupMember();

  async function handleAdd(userId: string) {
    addGroupMember.reset();
    try {
      await addGroupMember.mutateAsync({ groupId, userId });
      setQ("");
    } catch {
      /* surfaced via addGroupMember.isError/error */
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <input
        type="search"
        aria-label={t("shareForm.memberSearchAria", { group: groupTitle })}
        placeholder={t("shareForm.memberSearchPlaceholder")}
        className="h-9 rounded-md border border-control bg-surface px-2 text-xs text-ink"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {directory.data && directory.data.length === 0 && (
        <p className="text-xs text-ink-2">{t("shareForm.memberSearchEmpty")}</p>
      )}
      {directory.data && directory.data.length > 0 && (
        <ul className="flex flex-col gap-1">
          {directory.data.map((u) => (
            <li key={u.id}>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={addGroupMember.isPending}
                aria-label={t("shareForm.addMemberButton", {
                  group: `${u.username} → ${groupTitle}`,
                })}
                onClick={() => void handleAdd(u.id)}
              >
                {u.username}
                {u.email ? ` (${u.email})` : ""}
              </Button>
            </li>
          ))}
        </ul>
      )}
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

// j13-004 : membres (retrait), renommage et suppression d'un groupe — réservés
// à son créateur ou à un administrateur (Group.canManage, calculé par le cœur).
function GroupManageControl({ group }: { group: Group }) {
  const members = useGroupMembers(group.id);
  const removeMember = useRemoveGroupMember(group.id);
  const rename = useRenameGroup(group.id);
  const remove = useDeleteGroup(group.id);
  const [name, setName] = useState(group.title);
  const [confirming, setConfirming] = useState(false);
  const { triggerProps } = usePanelTrigger(confirming);
  const failed = removeMember.isError || rename.isError || remove.isError;

  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs font-medium text-ink-2">
        {t("shareForm.membersTitle", { group: group.title })}
      </p>
      {members.data && members.data.length === 0 && (
        <p className="text-xs text-ink-2">{t("shareForm.membersEmpty")}</p>
      )}
      <ul className="flex flex-col gap-1">
        {members.data?.map((m) => (
          <li key={m.userId} className="flex items-center justify-between gap-2 text-xs">
            <span>{m.username}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={removeMember.isPending}
              aria-label={t("shareForm.removeMemberButton", {
                user: m.username,
                group: group.title,
              })}
              onClick={() => removeMember.mutate(m.userId)}
            >
              {t("shareForm.revokeButton")}
            </Button>
          </li>
        ))}
      </ul>
      <div className="flex items-center gap-2">
        <input
          type="text"
          aria-label={t("shareForm.renameGroupAria", { group: group.title })}
          className="h-9 flex-1 rounded-md border border-control bg-surface px-2 text-xs text-ink"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!name.trim() || name.trim() === group.title || rename.isPending}
          aria-label={t("shareForm.renameGroupButton", { group: group.title })}
          onClick={() => rename.mutate(name.trim())}
        >
          {t("shareForm.renameGroupButton", { group: "" }).trim()}
        </Button>
        <Button
          type="button"
          variant="danger"
          size="sm"
          {...triggerProps}
          aria-label={t("shareForm.deleteGroupButton", { group: group.title })}
          onClick={() => setConfirming(true)}
        >
          {t("actions.delete")}
        </Button>
      </div>
      {failed && (
        <p role="alert" className="text-xs text-danger">
          {t("shareForm.groupActionFailed")}
        </p>
      )}
      <ConfirmDialog
        open={confirming}
        title={t("shareForm.deleteGroupTitle")}
        message={t("shareForm.deleteGroupMessage", { group: group.title })}
        confirmLabel={t("actions.delete")}
        pending={remove.isPending}
        onConfirm={() => remove.mutate(undefined, { onSuccess: () => setConfirming(false) })}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}

// j13-008 : partager une carte/app avec un groupe ne partage pas les données
// qu'elle lit — la collection reste illisible au membre (carte vide). Signale
// chaque collection lue non partagée avec les groupes cochés et propose de la
// partager (lecture) avec eux, si l'appelant en a le droit (sinon : rien).
function UnsharedSource({
  collectionId,
  selectedGroups,
  groups,
}: {
  collectionId: string;
  selectedGroups: string[];
  groups: Group[];
}) {
  const sharing = useCollectionSharing(collectionId);
  const setSharing = useSetCollectionSharing(collectionId);
  if (!sharing.data) return null;
  const shared = new Set(sharing.data.groups.map((g) => g.groupId));
  const missing = selectedGroups.filter((id) => !shared.has(id));
  if (missing.length === 0) return null;
  const names = missing.map((id) => groups.find((g) => g.id === id)?.title ?? id).join(", ");
  const current = sharing.data;
  return (
    <div className="flex flex-col gap-1 text-xs text-ink-2">
      <p role="status">
        {t("shareForm.unsharedSource", { collection: collectionId, groups: names })}
      </p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={setSharing.isPending}
        onClick={() =>
          setSharing.mutate({
            ...current,
            groups: [
              ...current.groups,
              ...missing.map((groupId) => ({ groupId, role: "viewer" as ShareRole })),
            ],
          })
        }
      >
        {t("shareForm.shareSourceButton", { collection: collectionId })}
      </Button>
      {setSharing.isError && (
        <p role="alert" className="text-danger">
          {t("shareForm.shareSourceFailed")}
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
  const referencedCollections = useReferencedCollectionIds(item);

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
      {loading && <LoadingState />}
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
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            {t("sharePanel.publicLabel")}
          </label>
          <p className="text-xs text-ink-2">
            {item.isPublished ? t("shareForm.publishedYes") : t("shareForm.publishedNo")}
          </p>

          <div className="flex flex-col gap-3">
            {groupsQuery.data.map((g) => (
              <div key={g.id} className="flex flex-col gap-1 border-b border-rule pb-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <label className="flex items-center gap-2 text-ink">
                    {/* eslint-disable-next-line geostudio/label-no-aria-label -- le nom accessible contient le texte visible et ajoute le contexte dynamique (champ/ligne) */}
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
                    className="h-9 rounded-md border border-control bg-surface px-2 text-sm text-ink"
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
                {g.canManage && (
                  <>
                    <GroupManageControl group={g} />
                    <AddGroupMemberControl groupId={g.id} groupTitle={g.title} />
                  </>
                )}
              </div>
            ))}
          </div>

          {referencedCollections.map((id) => (
            <UnsharedSource
              key={id}
              collectionId={id}
              groups={groupsQuery.data}
              selectedGroups={Object.entries(roles)
                .filter(([, role]) => role)
                .map(([groupId]) => groupId)}
            />
          ))}

          <div className="flex flex-col gap-1 border-t border-rule pt-2">
            <p className="text-xs font-medium text-ink-2">{t("shareForm.createGroupHelp")}</p>
            <div className="flex items-center gap-2">
              <input
                type="text"
                aria-label={t("shareForm.newGroupNameLabel")}
                placeholder={t("shareForm.newGroupNameLabel")}
                className="h-9 flex-1 rounded-md border border-control bg-surface px-2 text-sm text-ink"
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
