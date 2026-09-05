// SPDX-License-Identifier: Apache-2.0
import { Link, useLocation } from "react-router-dom";
import { navigableDomains, type Profile } from "../../auth/capabilities";
import { getDomainPath, isDomainActive } from "./domainRoutes";
import { t } from "../../i18n";

export function DomainBar({ profile }: { profile: Profile }) {
  const location = useLocation();
  const domains = navigableDomains(profile);

  return (
    <nav
      aria-label={t("domainBar.label")}
      className="flex items-center gap-1 border-b border-rule px-4"
    >
      {domains.map(({ domain, state }) => {
        const path = getDomainPath(domain.id, profile);
        // Cf. isDomainActive (domainRoutes.ts) pour le détail : plusieurs
        // domaines partagent le pathname "/" et ne diffèrent que par ?type=,
        // d'où l'usage de `Link` plutôt que `NavLink`.
        const isActive = isDomainActive(path, location);
        if (state === "locked") {
          return (
            <span
              key={domain.id}
              aria-disabled="true"
              title={t("locked.capabilityOff")}
              className="px-3 py-2 text-sm text-ink-3 opacity-45"
            >
              {t(domain.labelKey)}
            </span>
          );
        }
        return (
          <Link
            key={domain.id}
            to={path}
            aria-current={isActive ? "page" : undefined}
            className={
              isActive
                ? "border-b-2 border-accent px-3 py-2 text-sm font-semibold text-ink"
                : "px-3 py-2 text-sm text-ink-2 hover:text-ink"
            }
          >
            {t(domain.labelKey)}
          </Link>
        );
      })}
    </nav>
  );
}
