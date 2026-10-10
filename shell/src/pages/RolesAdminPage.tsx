// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import { useDeleteRole, useRoles } from "../api/hooks";
import { ApiError } from "../api/ApiError";
import type { Role } from "../api/types";
import { Button } from "../ui/kit/Button";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { DataTable } from "../ui/kit/DataTable";
import { EmptyState } from "../ui/kit/EmptyState";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";
import { CreateRolePanel } from "../shell/CreateRolePanel";
import { EditRolePanel } from "../shell/EditRolePanel";
import { SettingsNav } from "../shell/chrome/SettingsNav";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { plural, t } from "../i18n";
import { LoadingState } from "../ui/kit/LoadingState";
import { Banner } from "../ui/kit/Banner";
import { PageTitle } from "../ui/kit/PageTitle";
import "../i18n/domains/admin";
import "../i18n/domains/misc";

export function RolesAdminPage() {
  const rolesQuery = useRoles();
  const deleteRole = useDeleteRole();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Role | null>(null);
  const [deleting, setDeleting] = useState<Role | null>(null);
  const editPanel = usePanelTrigger(editing !== null);
  const createPanel = usePanelTrigger(creating);
  const [sortKey, setSortKey] = useState<string | undefined>(undefined);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");

  function handleSortChange(key: string) {
    if (key === sortKey) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  }

  const sortedRoles = useMemo(() => {
    const rows = rolesQuery.data ?? [];
    if (!sortKey) return rows;
    return [...rows].sort((a, b) => {
      const cmp =
        sortKey === "privilegeCount"
          ? a.privileges.length - b.privileges.length
          : a.name.localeCompare(b.name);
      return sortDirection === "asc" ? cmp : -cmp;
    });
  }, [rolesQuery.data, sortKey, sortDirection]);

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await deleteRole.mutateAsync(deleting.id);
      if (editing?.id === deleting.id) setEditing(null);
      setDeleting(null);
    } catch {
      // Ferme la boîte (modale) pour laisser voir l'alerte ci-dessous.
      setDeleting(null);
    }
  }

  // j08-011 : 409 « N user(s) still have this role » → message avec le compte.
  const blockedCount =
    deleteRole.error instanceof ApiError && deleteRole.error.status === 409
      ? Number.parseInt(deleteRole.error.detail ?? "", 10)
      : Number.NaN;
  const deleteErrorMessage = Number.isNaN(blockedCount)
    ? t("roles.deleteError")
    : t(plural(blockedCount, "roles.deleteBlockedByUsageOne", "roles.deleteBlockedByUsageMany"), {
        count: blockedCount,
      });

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: <SettingsNav />,
        }}
        work={{
          id: "roles",
          label: t("roles.title"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <PageTitle>{t("roles.title")}</PageTitle>
                <Button
                  size="sm"
                  {...createPanel.triggerProps}
                  onClick={() => {
                    setEditing(null);
                    setCreating(true);
                  }}
                >
                  {t("roles.addRole")}
                </Button>
              </div>
              {rolesQuery.isLoading && <LoadingState />}
              {rolesQuery.isError && (
                <Banner variant="danger" onRetry={() => void rolesQuery.refetch()}>
                  {t("roles.loadError")}
                </Banner>
              )}
              {deleteRole.isError && (
                <p role="alert" className="text-sm text-danger">
                  {deleteErrorMessage}
                </p>
              )}
              {rolesQuery.data && rolesQuery.data.length === 0 && (
                <EmptyState title={t("roles.empty")} />
              )}
              {rolesQuery.data && rolesQuery.data.length > 0 && (
                <DataTable
                  columns={[
                    {
                      key: "name",
                      label: t("roles.columnName"),
                      render: (role: Role) => (
                        <>
                          {role.name}
                          {role.isBuiltIn && (
                            <span className="ml-2 text-xs text-ink-2">
                              ({t("roles.builtInBadge")})
                            </span>
                          )}
                        </>
                      ),
                    },
                    {
                      key: "privilegeCount",
                      label: t("roles.columnPrivileges"),
                      render: (role: Role) => (
                        <span className="text-xs text-ink-2">{role.privileges.length}</span>
                      ),
                    },
                    {
                      key: "actions",
                      label: t("collectionsAdmin.columnActions"),
                      render: (role: Role) =>
                        !role.isBuiltIn && (
                          <div className="flex gap-2">
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
                          </div>
                        ),
                    },
                  ]}
                  rows={sortedRoles}
                  getRowId={(role) => role.id}
                  sortKey={sortKey}
                  sortDirection={sortDirection}
                  onSortChange={handleSortChange}
                />
              )}
            </div>
          ),
        }}
        inspect={{
          id: "detail",
          label: t("roles.detail"),
          content: (
            <div className="flex flex-col gap-3 p-3">
              {creating && (
                <div id={createPanel.panelId}>
                  <CreateRolePanel onClose={() => setCreating(false)} />
                </div>
              )}
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
