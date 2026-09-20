// SPDX-License-Identifier: Apache-2.0
import { Link, useLocation } from "react-router-dom";
import { useMe } from "../../api/hooks";
import { Panel } from "../../ui/kit/Panel";
import { t, type MessageKey } from "../../i18n";

// Liens partagés par la page Paramètres et les sept pages d'administration :
// fusion des anciens domaines "admin" et "settings" (capabilities.ts) en un
// seul point d'entrée toujours visible — "Général" (vers /settings) n'exige
// aucun privilège, les sept entrées admin gardent leur filtrage inchangé.
// Même doctrine que capabilities.ts : un privilège manquant MASQUE le lien.
const SETTINGS_LINKS: readonly { to: string; labelKey: MessageKey; privilege?: string }[] = [
  { to: "/settings", labelKey: "settingsNav.linkGeneral" },
  {
    to: "/admin/extensions",
    labelKey: "extensions.linkExtensions",
    privilege: "admin.extensions.manage",
  },
  {
    to: "/admin/infrastructure",
    labelKey: "extensions.linkInfrastructure",
    privilege: "settings.instance.manage",
  },
  { to: "/admin/roles", labelKey: "extensions.linkRoles", privilege: "admin.roles.manage" },
  { to: "/admin/users", labelKey: "extensions.linkUsers", privilege: "admin.users.manage" },
  {
    to: "/admin/collections",
    labelKey: "extensions.linkCollections",
    privilege: "admin.collections.manage",
  },
  { to: "/admin/harvest", labelKey: "extensions.linkHarvest", privilege: "admin.harvest.manage" },
  {
    to: "/admin/compliance",
    labelKey: "extensions.linkCompliance",
    privilege: "compliance.manage",
  },
] as const;

export function SettingsNav() {
  const meQuery = useMe();
  const location = useLocation();
  const visibleLinks = SETTINGS_LINKS.filter(
    (link) =>
      link.privilege === undefined || meQuery.data?.privileges.includes(link.privilege) === true,
  );

  return (
    <Panel className="m-3 flex flex-col gap-1 text-sm">
      <Link to="/" className="rounded-md px-2 py-1.5 text-accent hover:bg-sunken hover:underline">
        {t("nav.backToCatalog")}
      </Link>
      <nav
        aria-label={t("settingsNav.label")}
        className="mt-1 flex flex-col gap-0.5 border-t border-rule pt-2"
      >
        {visibleLinks.map((link) => {
          const active = location.pathname === link.to;
          return (
            <Link
              key={link.to}
              to={link.to}
              aria-current={active ? "page" : undefined}
              className={
                active
                  ? "rounded-md bg-accent-soft px-2 py-1.5 font-semibold text-accent-ink"
                  : "rounded-md px-2 py-1.5 text-ink-2 hover:bg-sunken hover:text-ink"
              }
            >
              {t(link.labelKey)}
            </Link>
          );
        })}
      </nav>
    </Panel>
  );
}
