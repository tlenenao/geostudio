// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { BottomNav } from "./BottomNav";
import type { Profile } from "../../auth/capabilities";

// Privilèges d'un administrateur (cf. BUILT_IN_ROLE_PRIVILEGES,
// core/app/roles/privileges.py, dupliqué en fixture dans capabilities.test.ts)
// — nécessaire pour que tous les domaines exercés par ces tests (Données,
// Apps & sites, Automatisation, Administration) soient visibles.
const PROFILE: Profile = {
  privileges: new Set([
    "catalog.manage",
    "maps.manage",
    "data.view",
    "data.manage",
    "apps.manage",
    "automation.manage",
    "automation.secrets.manage",
    "analytics.view",
    "analytics.sql_lab.access",
    "tasks.view",
    "tasks.view_all",
    "admin.users.manage",
    "admin.roles.manage",
    "admin.harvest.manage",
    "admin.collections.manage",
    "admin.extensions.manage",
    "admin.secrets.manage",
    "settings.instance.manage",
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

test("affiche toujours les quatre entrées fixes", () => {
  render(
    <MemoryRouter>
      <BottomNav profile={PROFILE} />
    </MemoryRouter>,
  );
  for (const label of ["Catalogue", "Cartes", "Tâches", "Plus"]) {
    expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
  }
});

// BottomNav rend son menu "Plus" via ui/kit/Popover (@floating-ui/react-dom) :
// même coût de repositionnement sous jsdom que Popover.test.tsx (~2-3s par
// ouverture), qui dépasse par intermittence le testTimeout par défaut du
// dépôt (5000ms) sous charge CPU, et de façon reproductible sous couverture
// v8 — précédent exact documenté dans Popover.test.tsx (Task 31, portes de
// qualité) et jamais reporté ici (piège n°4 : garde-fou non propagé à un
// consommateur du même composant).
const OPEN_TIMEOUT = 45000;

test(
  "Plus ouvre les domaines restants accessibles au profil",
  async () => {
    render(
      <MemoryRouter>
        <BottomNav profile={PROFILE} />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Plus" }));
    expect(screen.getByRole("link", { name: "Administration" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Données" })).toBeInTheDocument();
  },
  OPEN_TIMEOUT,
);

test(
  "le menu Plus ne marque qu'une seule entrée active même si plusieurs domaines partagent /",
  async () => {
    // Régression (Finding 6) : le menu "Plus" rendait ses domaines restants
    // via NavLink, dont la détection d'actif ignore la recherche d'URL —
    // Données/Apps & sites/Automatisation (tous "/") auraient tous porté
    // aria-current="page" en même temps sur "/?type=dataset".
    render(
      <MemoryRouter initialEntries={["/?type=dataset"]}>
        <BottomNav profile={PROFILE} />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Plus" }));
    expect(screen.getByRole("link", { name: "Données" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Apps & sites" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Automatisation" })).not.toHaveAttribute(
      "aria-current",
    );
    expect(screen.getByRole("link", { name: "Administration" })).not.toHaveAttribute(
      "aria-current",
    );
  },
  OPEN_TIMEOUT,
);

test("marque l'entrée fixe active via aria-current, y compris sur une route en ?type=", () => {
  render(
    <MemoryRouter initialEntries={["/?type=map"]}>
      <BottomNav profile={PROFILE} />
    </MemoryRouter>,
  );
  const cartes = screen.getByRole("button", { name: "Cartes" });
  const catalogue = screen.getByRole("button", { name: "Catalogue" });
  const taches = screen.getByRole("button", { name: "Tâches" });
  expect(cartes).toHaveAttribute("aria-current", "page");
  expect(catalogue).not.toHaveAttribute("aria-current");
  expect(taches).not.toHaveAttribute("aria-current");
});
