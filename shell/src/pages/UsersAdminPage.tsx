// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import { useEraseUser, useRoles, useUpdateUserRole, useUsers } from "../api/hooks";
import type { UserSummary } from "../api/types";
import { Button } from "../ui/kit/Button";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { eraseErrorMessage } from "./eraseErrorMessage";
import { DataTable } from "../ui/kit/DataTable";
import { EmptyState } from "../ui/kit/EmptyState";
import { Input } from "../ui/kit/Input";
import { SettingsNav } from "../shell/chrome/SettingsNav";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

const PAGE_SIZE = 50;

export function UsersAdminPage() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [rowError, setRowError] = useState<{ userId: string; message: string } | null>(null);
  const [pendingUserId, setPendingUserId] = useState<string | null>(null);

  const usersQuery = useUsers({ page, pageSize: PAGE_SIZE, q: q || undefined });
  const rolesQuery = useRoles();
  const updateUserRole = useUpdateUserRole();
  const eraseUser = useEraseUser();
  const [erasing, setErasing] = useState<UserSummary | null>(null);
  const [sortKey, setSortKey] = useState<string | undefined>(undefined);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");

  const totalPages = usersQuery.data
    ? Math.max(1, Math.ceil(usersQuery.data.total / PAGE_SIZE))
    : 1;

  function handleSortChange(key: string) {
    if (key === sortKey) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  }

  const sortedUsers = useMemo(() => {
    const rows = usersQuery.data?.users ?? [];
    if (!sortKey) return rows;
    const roles = rolesQuery.data ?? [];
    const roleNameFor = (user: UserSummary) =>
      roles.find((r) => r.slug === user.roleSlug)?.name ?? "";
    return [...rows].sort((a, b) => {
      const cmp =
        sortKey === "role"
          ? roleNameFor(a).localeCompare(roleNameFor(b))
          : a.username.localeCompare(b.username);
      return sortDirection === "asc" ? cmp : -cmp;
    });
  }, [usersQuery.data, rolesQuery.data, sortKey, sortDirection]);

  async function handleRoleChange(userId: string, roleId: string) {
    // Ne touche que l'erreur de CETTE ligne : changer le rôle de la ligne B
    // ne doit jamais effacer un message d'erreur encore affiché sur la ligne A.
    setRowError((prev) => (prev?.userId === userId ? null : prev));
    setPendingUserId(userId);
    try {
      await updateUserRole.mutateAsync({ id: userId, roleId });
    } catch {
      setRowError({ userId, message: t("usersAdmin.roleUpdateError") });
    } finally {
      setPendingUserId(null);
    }
  }

  async function confirmErase() {
    if (!erasing) return;
    const target = erasing;
    setRowError((prev) => (prev?.userId === target.id ? null : prev));
    try {
      await eraseUser.mutateAsync(target.id);
    } catch (error) {
      setRowError({ userId: target.id, message: eraseErrorMessage(error) });
    } finally {
      setErasing(null);
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: <SettingsNav />,
        }}
        work={{
          id: "users",
          label: t("usersAdmin.title"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">{t("usersAdmin.title")}</h1>
              <label className="flex flex-col gap-1 text-sm text-ink">
                {t("catalog.searchLabel")}
                <Input
                  aria-label={t("catalog.searchLabel")}
                  value={q}
                  onChange={(e) => {
                    setQ(e.target.value);
                    setPage(1);
                    setRowError(null);
                  }}
                />
              </label>
              {usersQuery.isLoading && <p role="status">{t("common.loading")}</p>}
              {usersQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("usersAdmin.loadError")}
                </p>
              )}
              {rolesQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("usersAdmin.rolesLoadError")}
                </p>
              )}
              {usersQuery.data && rolesQuery.data && usersQuery.data.users.length === 0 && (
                <EmptyState title={t("usersAdmin.empty")} />
              )}
              {usersQuery.data && rolesQuery.data && usersQuery.data.users.length > 0 && (
                <DataTable
                  columns={[
                    {
                      key: "username",
                      label: t("usersAdmin.usernameColumn"),
                      render: (u: UserSummary) => u.username,
                    },
                    {
                      key: "role",
                      label: t("usersAdmin.roleColumn"),
                      render: (u: UserSummary) => {
                        const currentRole = rolesQuery.data!.find((r) => r.slug === u.roleSlug);
                        const pending = pendingUserId === u.id;
                        return (
                          <>
                            <select
                              aria-label={t("usersAdmin.roleAria", { username: u.username })}
                              className="h-9 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
                              value={currentRole?.id ?? ""}
                              disabled={pending || !!u.erasedAt}
                              onChange={(e) => void handleRoleChange(u.id, e.target.value)}
                            >
                              {rolesQuery.data!.map((role) => (
                                <option key={role.id} value={role.id}>
                                  {role.name}
                                </option>
                              ))}
                            </select>
                            {rowError?.userId === u.id && (
                              <p role="alert" className="mt-1 text-xs text-danger">
                                {rowError.message}
                              </p>
                            )}
                          </>
                        );
                      },
                    },
                    {
                      key: "actions",
                      label: t("usersAdmin.actionsColumn"),
                      render: (u: UserSummary) =>
                        u.erasedAt ? (
                          <span className="text-xs text-ink-2">{t("usersAdmin.erasedBadge")}</span>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            aria-label={t("usersAdmin.eraseAria", { username: u.username })}
                            onClick={() => setErasing(u)}
                          >
                            {t("usersAdmin.eraseButton")}
                          </Button>
                        ),
                    },
                  ]}
                  rows={sortedUsers}
                  getRowId={(u) => u.id}
                  sortKey={sortKey}
                  sortDirection={sortDirection}
                  onSortChange={handleSortChange}
                />
              )}
              <div className="mt-auto flex items-center gap-3">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page <= 1}
                  onClick={() => {
                    setPage((p) => Math.max(1, p - 1));
                    setRowError(null);
                  }}
                >
                  {t("usage.previous")}
                </Button>
                <span className="text-sm text-ink-2">
                  {t("usage.pageOf", { page, totalPages })}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page >= totalPages}
                  onClick={() => {
                    setPage((p) => p + 1);
                    setRowError(null);
                  }}
                >
                  {t("usage.next")}
                </Button>
              </div>
            </div>
          ),
        }}
        inspect={{
          id: "help",
          label: t("usersAdmin.detail"),
          content: (
            <div className="flex flex-col gap-2 p-3 text-sm text-ink-2">
              <p>{t("usersAdmin.demotionProtectionText")}</p>
            </div>
          ),
        }}
      />
      <ConfirmDialog
        open={!!erasing}
        title={t("usersAdmin.eraseConfirmTitle")}
        message={erasing ? t("usersAdmin.eraseConfirmMessage", { username: erasing.username }) : ""}
        confirmLabel={t("usersAdmin.eraseButton")}
        pending={eraseUser.isPending}
        onCancel={() => setErasing(null)}
        onConfirm={() => void confirmErase()}
      />
    </div>
  );
}
