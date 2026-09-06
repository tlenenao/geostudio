// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DomainBar } from "./DomainBar";
import type { Profile } from "../../auth/capabilities";

// Privilèges d'un Créateur (cf. BUILT_IN_ROLE_PRIVILEGES, core/app/roles/privileges.py,
// dupliqué en fixture dans capabilities.test.ts) — comprend analytics.view
// (le domaine Analytique lui est visible, sans analytics.sql_lab.access —
// SQL Lab reste hors d'atteinte, cf. RequirePrivilege sur /analytics/sql ;
// DOMAIN_PATHS.analytics pointe désormais vers /?type=bookmark, une
// destination que le Créateur peut réellement ouvrir — SP-42, revue de la
// dernière passe de correctifs, points 7/8) ; ni admin.*.
const BASE_PROFILE: Profile = {
  privileges: new Set([
    "catalog.manage",
    "maps.manage",
    "data.view",
    "data.manage",
    "apps.manage",
    "automation.manage",
    "automation.secrets.manage",
    "analytics.view",
    "tasks.view",
  ]),
  capabilities: {
    readOnly: false,
    etlEnabled: true,
    exportEnabled: false,
    appExportEnabled: false,
    tileset3dEnabled: false,
    terrain3dEnabled: false,
    copilotEnabled: false,
    quotasEnabled: false,
  },
};

function renderBar(profile: Profile, initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <DomainBar profile={profile} />
    </MemoryRouter>,
  );
}

test("affiche les huit domaines accessibles à un créateur, avec Analytique mais sans Administration", () => {
  renderBar(BASE_PROFILE);
  for (const label of [
    "Catalogue",
    "Cartes",
    "Données",
    "Apps & sites",
    "Automatisation",
    "Analytique",
    "Tâches",
    "Paramètres",
  ]) {
    expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
  }
  expect(screen.queryByRole("link", { name: "Administration" })).not.toBeInTheDocument();
});

test("affiche Administration pour un administrateur", () => {
  renderBar({
    ...BASE_PROFILE,
    privileges: new Set([...BASE_PROFILE.privileges, "admin.users.manage"]),
  });
  expect(screen.getByRole("link", { name: "Administration" })).toBeInTheDocument();
});

test("Analytique pointe vers le catalogue filtré (bookmark), pas vers SQL Lab, pour un créateur", () => {
  // SP-42, revue de la dernière passe de correctifs (points 7/8) :
  // DOMAIN_PATHS.analytics est statique (contrairement à "admin", qui varie
  // par profil via getDomainPath) — un Créateur (analytics.view seul)
  // atterrit sur cette destination ; seul un lien direct vers
  // /analytics/sql (hors de ce domaine de navigation) ouvre SQL Lab.
  renderBar(BASE_PROFILE);
  expect(screen.getByRole("link", { name: "Analytique" })).toHaveAttribute(
    "href",
    "/?type=bookmark",
  );
});

test("Analytique pointe vers la même destination pour un analyste (analytics.sql_lab.access ne change pas le lien)", () => {
  renderBar({
    ...BASE_PROFILE,
    privileges: new Set([...BASE_PROFILE.privileges, "analytics.sql_lab.access"]),
  });
  expect(screen.getByRole("link", { name: "Analytique" })).toHaveAttribute(
    "href",
    "/?type=bookmark",
  );
});

test("marque le domaine courant actif", () => {
  renderBar(BASE_PROFILE, "/?type=bookmark");
  expect(screen.getByRole("link", { name: "Analytique" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Catalogue" })).not.toHaveAttribute("aria-current");
});

test("distingue Cartes de Catalogue même si les deux mènent à /", () => {
  // Cartes/Données/Apps & sites/Automatisation pointent tous vers le
  // Catalogue pré-filtré par ?type= (Task 6) — sans comparer aussi la
  // recherche d'URL, les cinq domaines qui partagent le chemin "/"
  // paraîtraient actifs en même temps dès qu'on est sur "/".
  renderBar(BASE_PROFILE, "/?type=map");
  expect(screen.getByRole("link", { name: "Cartes" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Catalogue" })).not.toHaveAttribute("aria-current");
});

test("Automatisation verrouillée quand la capacité etlEnabled est coupée", () => {
  renderBar({ ...BASE_PROFILE, capabilities: { ...BASE_PROFILE.capabilities, etlEnabled: false } });
  const automation = screen.getByText("Automatisation");
  expect(automation.closest("[aria-disabled]")).toHaveAttribute("aria-disabled", "true");
});

test("SP-42/F-securite-autorisation-08(b) : Administration pointe vers la route accessible au privilège réellement détenu", () => {
  renderBar({
    ...BASE_PROFILE,
    // Ni admin.extensions.manage (destination par défaut de DOMAIN_PATHS)
    // ni aucun autre privilège admin que admin.users.manage.
    privileges: new Set([...BASE_PROFILE.privileges, "admin.users.manage"]),
  });
  expect(screen.getByRole("link", { name: "Administration" })).toHaveAttribute(
    "href",
    "/admin/users",
  );
});
