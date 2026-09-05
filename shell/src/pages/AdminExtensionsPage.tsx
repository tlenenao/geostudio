// SPDX-License-Identifier: Apache-2.0
import { Link } from "react-router-dom";
import { useAllExtensions, useInstanceInfo, useMe, useSetExtensionEnabled } from "../api/hooks";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

// SP-46 (GAP-67) : un privilège manquant MASQUE le lien plutôt que de le
// laisser mener à un refus de RequirePrivilege sur la route cible — même
// doctrine que capabilities.ts pour la barre de domaines. Pas de hook
// usePrivilege() partagé : un seul consommateur (cette page), cf. spec SP-46
// §2 pour la justification de ne pas extraire.
const ADMIN_LINKS: { to: string; label: string; privilege: string }[] = [
  {
    to: "/admin/infrastructure",
    label: "Outils d'infrastructure →",
    privilege: "settings.instance.manage",
  },
  { to: "/admin/roles", label: "Rôles et privilèges →", privilege: "admin.roles.manage" },
  { to: "/admin/users", label: "Utilisateurs →", privilege: "admin.users.manage" },
  { to: "/admin/collections", label: "Collections →", privilege: "admin.collections.manage" },
  { to: "/admin/harvest", label: "Moissonnage →", privilege: "admin.harvest.manage" },
];

export function AdminExtensionsPage() {
  const extensionsQuery = useAllExtensions();
  const setEnabled = useSetExtensionEnabled();
  const instanceQuery = useInstanceInfo();
  const meQuery = useMe();
  const readOnly = instanceQuery.data?.readOnly === true;
  const visibleLinks = ADMIN_LINKS.filter(
    (link) => meQuery.data?.privileges.includes(link.privilege) === true,
  );

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
              {visibleLinks.map((link) => (
                <Link key={link.to} to={link.to} className="text-accent hover:underline">
                  {link.label}
                </Link>
              ))}
            </Panel>
          ),
        }}
        work={{
          id: "extensions",
          label: "Extensions",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">Extensions</h1>
              {extensionsQuery.isLoading && <p role="status">Chargement…</p>}
              {extensionsQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec du chargement des extensions.
                </p>
              )}
              {setEnabled.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec de la mise à jour de l'extension.
                </p>
              )}
              {extensionsQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">Étiquette</th>
                      <th className="py-2 text-ink">Balise</th>
                      <th className="py-2 text-ink">Module</th>
                      <th className="py-2 text-ink">Actif</th>
                    </tr>
                  </thead>
                  <tbody>
                    {extensionsQuery.data.map((ext) => (
                      <tr key={ext.type} className="border-b border-rule-2">
                        <td className="py-2 text-ink">{ext.label}</td>
                        <td className="py-2 text-ink">{ext.tag}</td>
                        <td className="py-2 text-xs text-ink-2">{ext.moduleUrl}</td>
                        <td className="py-2">
                          <input
                            type="checkbox"
                            aria-label={`Actif : ${ext.label}`}
                            checked={ext.enabled}
                            disabled={setEnabled.isPending || readOnly}
                            onChange={(e) =>
                              setEnabled.mutate({ id: ext.type, enabled: e.target.checked })
                            }
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ),
        }}
        inspect={{ id: "detail", label: "Détail", content: null }}
      />
    </div>
  );
}
