// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useRoles, useUpdateUserRole, useUsers } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

const PAGE_SIZE = 50;

export function UsersAdminPage() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [rowError, setRowError] = useState<{ userId: string; message: string } | null>(null);

  const usersQuery = useUsers({ page, pageSize: PAGE_SIZE, q: q || undefined });
  const rolesQuery = useRoles();
  const updateUserRole = useUpdateUserRole();

  const totalPages = usersQuery.data
    ? Math.max(1, Math.ceil(usersQuery.data.total / PAGE_SIZE))
    : 1;

  async function handleRoleChange(userId: string, roleId: string) {
    setRowError(null);
    try {
      await updateUserRole.mutateAsync({ id: userId, roleId });
    } catch {
      setRowError({ userId, message: "Échec de la mise à jour du rôle." });
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
            </Panel>
          ),
        }}
        work={{
          id: "users",
          label: "Utilisateurs",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">Utilisateurs</h1>
              <label className="flex flex-col gap-1 text-sm text-ink">
                Rechercher
                <Input
                  aria-label="Rechercher"
                  value={q}
                  onChange={(e) => {
                    setQ(e.target.value);
                    setPage(1);
                  }}
                />
              </label>
              {usersQuery.isLoading && <p role="status">Chargement…</p>}
              {usersQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec du chargement des utilisateurs.
                </p>
              )}
              {usersQuery.data && rolesQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">Nom d&apos;utilisateur</th>
                      <th className="py-2 text-ink">Rôle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usersQuery.data.users.map((u) => {
                      const currentRole = rolesQuery.data.find((r) => r.slug === u.roleSlug);
                      const pending =
                        updateUserRole.isPending && updateUserRole.variables?.id === u.id;
                      return (
                        <tr key={u.id} className="border-b border-rule-2">
                          <td className="py-2 text-ink">{u.username}</td>
                          <td className="py-2">
                            <select
                              aria-label={`Rôle de ${u.username}`}
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
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Précédent
                </Button>
                <span className="text-sm text-ink-2">
                  Page {page} / {totalPages}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Suivant
                </Button>
              </div>
            </div>
          ),
        }}
        inspect={{
          id: "help",
          label: "Détail",
          content: (
            <div className="flex flex-col gap-2 p-3 text-sm text-ink-2">
              <p>
                Le dernier titulaire de la gestion des rôles et des utilisateurs ne peut pas être
                rétrogradé : la tentative échoue pour préserver au moins un compte capable
                d&apos;administrer le tenant.
              </p>
            </div>
          ),
        }}
      />
    </div>
  );
}
