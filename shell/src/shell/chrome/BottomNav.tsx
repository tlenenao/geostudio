// SPDX-License-Identifier: Apache-2.0
import { NavLink, useNavigate } from "react-router-dom";
import { navigableDomains, type Profile } from "../../auth/capabilities";
import { DOMAIN_PATHS } from "./domainRoutes";
import { Popover } from "../../ui/kit/Popover";
import { t } from "../../i18n";

const FIXED_IDS = ["catalog", "maps", "tasks"] as const;

export function BottomNav({ profile }: { profile: Profile }) {
  const navigate = useNavigate();
  const domains = navigableDomains(profile).filter((d) => d.state === "visible");
  const fixed = domains.filter((d) => (FIXED_IDS as readonly string[]).includes(d.domain.id));
  const rest = domains.filter((d) => !(FIXED_IDS as readonly string[]).includes(d.domain.id));

  return (
    <nav aria-label={t("bottomNav.label")} className="flex items-center border-t border-rule">
      {fixed.map(({ domain }) => (
        <button
          key={domain.id}
          type="button"
          onClick={() => navigate(DOMAIN_PATHS[domain.id])}
          className="flex flex-1 flex-col items-center py-2 text-xs text-ink-2"
        >
          {t(domain.labelKey)}
        </button>
      ))}
      <Popover
        aria-label={t("bottomNav.more")}
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
          {rest.map(({ domain }) => (
            <NavLink key={domain.id} to={DOMAIN_PATHS[domain.id]} className="px-2 py-1 text-sm">
              {t(domain.labelKey)}
            </NavLink>
          ))}
        </div>
      </Popover>
    </nav>
  );
}
