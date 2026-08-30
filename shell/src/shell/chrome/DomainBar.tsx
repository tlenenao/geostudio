// SPDX-License-Identifier: Apache-2.0
import { Link, useLocation } from "react-router-dom";
import { navigableDomains, type Profile } from "../../auth/capabilities";
import { DOMAIN_PATHS } from "./domainRoutes";
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
        const path = DOMAIN_PATHS[domain.id];
        // Plusieurs domaines (Cartes/Données/Apps & sites/Automatisation)
        // pointent tous vers "/" avec un ?type= différent (Task 6) : comparer
        // seulement le pathname les ferait paraître actifs tous en même
        // temps. Comparer aussi la recherche pour ceux dont le chemin en
        // porte une ; pour les autres (dont Catalogue, "/" sans ?type=),
        // comparer le pathname ET exiger une recherche vide — sinon
        // Catalogue ("/") paraîtrait actif même sur "/?type=map", qui
        // partage le même pathname.
        //
        // On utilise `Link`, pas `NavLink` : `NavLink` calcule sa PROPRE
        // notion d'« actif » à partir du seul pathname de `to` (la query
        // est perdue par `useResolvedPath`), et sa déstructuration par
        // défaut réinjecte "page" dès qu'on lui passe `aria-current:
        // undefined` — impossible d'annuler son `aria-current`/`className`
        // internes depuis l'extérieur. Vérifié empiriquement : `NavLink` ici
        // marquait Catalogue actif sur "/?type=map" malgré un `aria-current`
        // explicite à `undefined`.
        const currentHref = location.pathname + location.search;
        const isActive = path.includes("?")
          ? currentHref === path
          : location.pathname === path && location.search === "";
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
