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

  it("masque le domaine analytique au lecteur et au créateur (pas de SQL Lab), le montre à l'analyste", () => {
    // SP-42/F-securite-autorisation-08(a) : gaté sur analytics.sql_lab.access,
    // pas analytics.view. /analytics/sql (RequirePrivilege du même nom,
    // routes.tsx) est aujourd'hui l'unique destination de ce domaine — un
    // Créateur (analytics.view sans sql_lab.access) voyait auparavant un
    // domaine qui refusait systématiquement sa seule destination
    // (falsifié : domainState === "visible" mais la route refuse). Revient
    // sur le changement assumé par SP-30a (masquer sur analytics.view
    // seul) une fois la divergence domaine/route constatée.
    expect(stateOf("analytics", reader)).toBe("hidden");
    expect(stateOf("analytics", creator)).toBe("hidden");
    expect(stateOf("analytics", analyst)).toBe("visible");
  });

  it("masque le domaine Cartes au lecteur, le montre au créateur", () => {
    // SP-42/F-shell-pages-03 : maps.manage distingue déjà Créateur de
    // Lecteur côté catalogue de privilèges (core/app/roles/privileges.py) —
    // seul ce domaine n'en tenait pas compte jusqu'ici.
    expect(stateOf("maps", reader)).toBe("hidden");
    expect(stateOf("maps", creator)).toBe("visible");
  });

  it("un domaine visible doit toujours pouvoir atteindre le privilège réellement gardé par sa destination (F-securite-autorisation-08)", () => {
    // Cf. shell/src/shell/routes.tsx pour la garde RequirePrivilege réelle de
    // chaque destination de DOMAIN_PATHS (domainRoutes.ts) — dupliqué ici
    // faute de pouvoir importer routes.tsx (React Router) dans un test de
    // logique pure. admin est délibérément absent : sa destination varie
    // par profil (getDomainPath), déjà couvert par domainRoutes.test.ts.
    const destinationPrivilege: Partial<Record<string, string>> = {
      analytics: "analytics.sql_lab.access",
    };
    for (const profile of [admin, creator, analyst, reader]) {
      for (const domain of DOMAINS) {
        if (domain.id === "admin") continue;
        const required = destinationPrivilege[domain.id];
        if (!required) continue;
        if (domainState(domain, profile) === "visible") {
          expect(profile.privileges.has(required)).toBe(true);
        }
      }
    }
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
    // "analytics" absent : `creator` n'a pas analytics.sql_lab.access
    // (SP-42/F-securite-autorisation-08(a) ci-dessus), pas un effet de
    // etlOff.
    expect(rendered.map((r) => r.domain.id)).not.toContain("analytics");
    expect(rendered.find((r) => r.domain.id === "automation")?.state).toBe("locked");
    expect(rendered.map((r) => r.domain.id)).toEqual([
      "catalog",
      "maps",
      "data",
      "apps",
      "automation",
      "tasks",
      "settings",
    ]);
  });
});
