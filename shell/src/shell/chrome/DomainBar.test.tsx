// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DomainBar } from "./DomainBar";
import type { Profile } from "../../auth/capabilities";

// Privilèges d'un Créateur (cf. BUILT_IN_ROLE_PRIVILEGES, core/app/roles/privileges.py,
// dupliqué en fixture dans capabilities.test.ts) — comprend analytics.view
// (le domaine Analytique lui est visible, sans analytics.sql_lab.access —
// SQL Lab reste hors d'atteinte, cf. RequirePrivilege sur /analytics/sql) ;
// ni admin.*.
const BASE_PROFILE: Profile = {
  privileges: new Set([
    "catalog.manage",
    "maps.manage",
    "data.view",
    "data.manage",
    "apps.manage",
    "automation.manage",
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

test("affiche Analytique pour un analyste", () => {
  renderBar({
    ...BASE_PROFILE,
    privileges: new Set([...BASE_PROFILE.privileges, "analytics.view"]),
  });
  expect(screen.getByRole("link", { name: "Analytique" })).toBeInTheDocument();
});

test("marque le domaine courant actif", () => {
  renderBar(
    { ...BASE_PROFILE, privileges: new Set([...BASE_PROFILE.privileges, "analytics.view"]) },
    "/analytics/sql",
  );
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
