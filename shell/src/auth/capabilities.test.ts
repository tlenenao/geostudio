// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  DOMAINS,
  domainState,
  navigableDomains,
  type InstanceCapabilities,
  type Profile,
} from "./capabilities";

const ALL_ON: InstanceCapabilities = {
  readOnly: false,
  etlEnabled: true,
  exportEnabled: true,
  appExportEnabled: true,
  tileset3dEnabled: true,
  terrain3dEnabled: true,
  copilotEnabled: true,
};

// Miroir de BUILT_IN_ROLE_PRIVILEGES (core/app/roles/privileges.py) — mêmes
// valeurs, dupliquées ici faute de source unique inter-langages (le shell ne
// consomme ce catalogue que via GET /roles/catalog à l'exécution, jamais à la
// compilation des tests).
const admin: Profile = {
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
  capabilities: ALL_ON,
};
const creator: Profile = {
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
  capabilities: ALL_ON,
};
const analyst: Profile = {
  privileges: new Set(["data.view", "analytics.view", "analytics.sql_lab.access", "tasks.view"]),
  capabilities: ALL_ON,
};
const reader: Profile = { privileges: new Set(), capabilities: ALL_ON };

function stateOf(id: string, profile: Profile) {
  const domain = DOMAINS.find((d) => d.id === id);
  if (!domain) throw new Error(`domaine inconnu dans le test : ${id}`);
  return domainState(domain, profile);
}

describe("domainState", () => {
  it("déclare les neuf domaines de la spec", () => {
    expect(DOMAINS.map((d) => d.id)).toEqual([
      "catalog",
      "maps",
      "data",
      "apps",
      "automation",
      "analytics",
      "tasks",
      "admin",
      "settings",
    ]);
  });

  it("masque le domaine admin sans aucun privilège admin.*, le montre à l'admin", () => {
    expect(stateOf("admin", reader)).toBe("hidden");
    expect(stateOf("admin", creator)).toBe("hidden");
    expect(stateOf("admin", admin)).toBe("visible");
  });

  it("verrouille — sans masquer — un domaine dont la capacité est coupée", () => {
    const etlOff: Profile = { ...creator, capabilities: { ...ALL_ON, etlEnabled: false } };
    expect(stateOf("automation", etlOff)).toBe("locked");
    expect(stateOf("automation", creator)).toBe("visible");
  });

  it("le privilège l'emporte sur la capacité : un domaine masqué le reste", () => {
    // Sinon un lecteur apprendrait l'existence d'automation par son verrou.
    const readerEtlOff: Profile = { ...reader, capabilities: { ...ALL_ON, etlEnabled: false } };
    expect(stateOf("automation", readerEtlOff)).toBe("hidden");
  });

  it("masque le domaine Données au lecteur, le montre au créateur et à l'analyste", () => {
    expect(stateOf("data", reader)).toBe("hidden");
    expect(stateOf("data", creator)).toBe("visible");
    expect(stateOf("data", analyst)).toBe("visible");
  });

  it("montre le domaine analytique au créateur (sans SQL Lab, matrice §6.7) et à l'analyste, le masque au lecteur", () => {
    // Changement de comportement assumé par cette tâche : l'ancien modèle
    // masquait tout le domaine à qui n'était pas isAnalyst=true, y compris un
    // créateur — la matrice §6.7 dit « ◐ sans SQL Lab », pas absent.
    // L'accès à SQL Lab lui-même reste gardé séparément par RequirePrivilege
    // sur la route /analytics/sql (analytics.sql_lab.access), pas ici.
    expect(stateOf("analytics", reader)).toBe("hidden");
    expect(stateOf("analytics", creator)).toBe("visible");
    expect(stateOf("analytics", analyst)).toBe("visible");
  });

  it("le mode démo ne masque ni ne verrouille aucun domaine", () => {
    // Il retire l'écriture, pas la navigation (spec §6.7).
    const demo: Profile = { ...creator, capabilities: { ...ALL_ON, readOnly: true } };
    for (const domain of DOMAINS) {
      expect(domainState(domain, demo)).toBe(domainState(domain, creator));
    }
  });
});

describe("navigableDomains", () => {
  it("ne rend que le visible et le verrouillé, dans l'ordre déclaré", () => {
    const etlOff: Profile = { ...creator, capabilities: { ...ALL_ON, etlEnabled: false } };
    const rendered = navigableDomains(etlOff);
    expect(rendered.map((r) => r.domain.id)).not.toContain("admin");
    expect(rendered.find((r) => r.domain.id === "automation")?.state).toBe("locked");
    expect(rendered.map((r) => r.domain.id)).toEqual([
      "catalog",
      "maps",
      "data",
      "apps",
      "automation",
      "analytics",
      "tasks",
      "settings",
    ]);
  });
});
