// SPDX-License-Identifier: Apache-2.0
import { Link, useLocation, useNavigate } from "react-router-dom";
import { navigableDomains, type Profile } from "../../auth/capabilities";
import { DOMAIN_PATHS, isDomainActive } from "./domainRoutes";
import { Popover } from "../../ui/kit/Popover";
import { t } from "../../i18n";

const FIXED_IDS = ["catalog", "maps", "tasks"] as const;

export function BottomNav({ profile }: { profile: Profile }) {
  const navigate = useNavigate();
  const location = useLocation();
  const domains = navigableDomains(profile).filter((d) => d.state === "visible");
  const fixed = domains.filter((d) => (FIXED_IDS as readonly string[]).includes(d.domain.id));
  const rest = domains.filter((d) => !(FIXED_IDS as readonly string[]).includes(d.domain.id));

  return (
    <nav aria-label={t("bottomNav.label")} className="flex items-center border-t border-rule">
      {fixed.map(({ domain }) => {
        const path = DOMAIN_PATHS[domain.id];
        // Même calcul d'actif que DomainBar (cf. isDomainActive) : plusieurs
        // domaines partagent le pathname "/" et ne diffèrent que par
        // ?type=, donc comparer aussi la recherche.
        const isActive = isDomainActive(path, location);
        return (
          <button
            key={domain.id}
            type="button"
            onClick={() => navigate(path)}
            aria-current={isActive ? "page" : undefined}
            className={
              isActive
                ? "flex flex-1 flex-col items-center border-t-2 border-accent py-2 text-xs font-semibold text-ink"
                : "flex flex-1 flex-col items-center py-2 text-xs text-ink-2"
            }
          >
            {t(domain.labelKey)}
          </button>
        );
      })}
      <Popover
        aria-label={t("bottomNav.more")}
        side="top"
        trigger={
          <button
            type="button"
            className="flex flex-1 flex-col items-center py-2 text-xs text-ink-2"
          >
            {t("bottomNav.more")}
          </button>
        }
      >
        <div className="flex flex-col gap-1">
          {rest.map(({ domain }) => {
            const path = DOMAIN_PATHS[domain.id];
            // Même raison que pour `fixed` ci-dessus et que DomainBar :
            // `NavLink` réintroduirait plusieurs entrées actives à la fois
            // sur "/" (cf. isDomainActive).
            const isActive = isDomainActive(path, location);
            return (
              <Link
                key={domain.id}
                to={path}
                aria-current={isActive ? "page" : undefined}
                className="px-2 py-1 text-sm"
              >
                {t(domain.labelKey)}
              </Link>
            );
          })}
        </div>
      </Popover>
    </nav>
  );
}
