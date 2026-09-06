// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useDeleteRole, useRoles } from "../api/hooks";
import type { Role } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";
import { CreateRolePanel } from "../shell/CreateRolePanel";
import { EditRolePanel } from "../shell/EditRolePanel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

export function RolesAdminPage() {
  const rolesQuery = useRoles();
  const deleteRole = useDeleteRole();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Role | null>(null);
  const [deleting, setDeleting] = useState<Role | null>(null);
  const editPanel = usePanelTrigger(editing !== null);

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await deleteRole.mutateAsync(deleting.id);
      if (editing?.id === deleting.id) setEditing(null);
      setDeleting(null);
    } catch {
      // surfaced via deleteRole.isError
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                {t("nav.backToCatalog")}
              </Link>
            </Panel>
          ),
        }}
        work={{
          id: "roles",
          label: t("roles.title"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <h1 className="text-lg font-bold text-ink">{t("roles.title")}</h1>
                <Button
                  size="sm"
                  onClick={() => {
                    setEditing(null);
                    setCreating(true);
                  }}
                >
                  {t("roles.addRole")}
                </Button>
              </div>
              {rolesQuery.isLoading && <p role="status">{t("common.loading")}</p>}
              {rolesQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("roles.loadError")}
                </p>
              )}
              {deleteRole.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("roles.deleteError")}
                </p>
              )}
              {rolesQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">{t("roles.columnName")}</th>
                      <th className="py-2 text-ink">{t("roles.columnPrivileges")}</th>
                      <th className="py-2 text-ink">{t("collectionsAdmin.columnActions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rolesQuery.data.map((role) => (
                      <tr key={role.id} className="border-b border-rule-2">
                        <td className="py-2 text-ink">
                          {role.name}
                          {role.isBuiltIn && (
                            <span className="ml-2 text-xs text-ink-2">
                              ({t("roles.builtInBadge")})
                            </span>
                          )}
                        </td>
                        <td className="py-2 text-xs text-ink-2">{role.privileges.length}</td>
                        <td className="py-2 flex gap-2">
                          {!role.isBuiltIn && (
                            <>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                aria-controls={editPanel.panelId}
                                aria-expanded={editing?.id === role.id}
                                onClick={() => {
                                  setCreating(false);
                                  setEditing(role);
                                }}
                              >
                                {t("collectionsAdmin.edit")}
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => setDeleting(role)}
                              >
                                {t("actions.delete")}
                              </Button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ),
        }}
        inspect={{
          id: "detail",
          label: t("roles.detail"),
          content: (
            <div className="flex flex-col gap-3 p-3">
              {creating && <CreateRolePanel onClose={() => setCreating(false)} />}
              {editing && (
                // id seul (pas role="region") : EditRolePanel rend déjà un
                // <section aria-label=…>, région implicite nommée — même
                // correction que CollectionsAdminPage/HarvestSourcesAdminPage.
                <div id={editPanel.panelId}>
                  <EditRolePanel key={editing.id} role={editing} onClose={() => setEditing(null)} />
                </div>
              )}
            </div>
          ),
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        title={t("roles.deleteConfirmTitle")}
        message={deleting ? t("roles.deleteConfirmMessage", { name: deleting.name }) : ""}
        confirmLabel={t("actions.delete")}
        pending={deleteRole.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
