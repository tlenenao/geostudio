// SPDX-License-Identifier: Apache-2.0
import { roleLabel } from "./roleLabel";
import type { Me } from "../api/types";

function meWith(slug: string, name: string): Me {
  return {
    id: "u1",
    tenantId: "t1",
    tenantSlug: "demo",
    username: "alice",
    email: null,
    firstName: "",
    lastName: "",
    role: { id: "r1", name, slug },
    privileges: [],
    version: "0.1.0",
    capabilities: {
      readOnly: false,
      etlEnabled: false,
      exportEnabled: false,
      appExportEnabled: false,
      tileset3dEnabled: false,
      terrain3dEnabled: false,
      copilotEnabled: false,
      adminToolsEnabled: false,
      quotasEnabled: false,
    },
  };
}

test("traduit le libellé d'un rôle intégré", () => {
  expect(roleLabel(meWith("admin", "Administrateur"))).toBe("Administrateur");
});

test("retombe sur le nom du rôle pour un rôle sur mesure", () => {
  expect(roleLabel(meWith("role-abc123", "Cartographe"))).toBe("Cartographe");
});

test("retourne une chaîne vide sans profil", () => {
  expect(roleLabel(undefined)).toBe("");
});
