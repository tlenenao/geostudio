// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useRoles, useUpdateUserRole, useUsers } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Panel } from "../ui/kit/Panel";
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

  const totalPages = usersQuery.data
    ? Math.max(1, Math.ceil(usersQuery.data.total / PAGE_SIZE))
    : 1;

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
              {usersQuery.data && rolesQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">{t("usersAdmin.usernameColumn")}</th>
                      <th className="py-2 text-ink">{t("usersAdmin.roleColumn")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usersQuery.data.users.map((u) => {
                      const currentRole = rolesQuery.data.find((r) => r.slug === u.roleSlug);
                      const pending = pendingUserId === u.id;
                      return (
                        <tr key={u.id} className="border-b border-rule-2">
                          <td className="py-2 text-ink">{u.username}</td>
                          <td className="py-2">
                            <select
                              aria-label={t("usersAdmin.roleAria", { username: u.username })}
                              className="h-9 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
                              value={currentRole?.id ?? ""}
                              disabled={pending}
                              onChange={(e) => void handleRoleChange(u.id, e.target.value)}
                            >
                              {rolesQuery.data.map((role) => (
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
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
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
    </div>
  );
}
