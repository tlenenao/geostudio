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

const admin: Profile = { isAdmin: true, isAnalyst: true, capabilities: ALL_ON };
const creator: Profile = { isAdmin: false, isAnalyst: false, capabilities: ALL_ON };

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

  it("masque un domaine dont le rôle manque", () => {
    expect(stateOf("admin", creator)).toBe("hidden");
    expect(stateOf("admin", admin)).toBe("visible");
  });

  it("verrouille — sans masquer — un domaine dont la capacité est coupée", () => {
    const etlOff: Profile = {
      ...creator,
      capabilities: { ...ALL_ON, etlEnabled: false },
    };
    expect(stateOf("automation", etlOff)).toBe("locked");
    expect(stateOf("automation", creator)).toBe("visible");
  });

  it("le rôle l'emporte sur la capacité : un domaine masqué le reste", () => {
    // Sinon un non-admin apprendrait l'existence d'un domaine par son verrou.
    const both: Profile = {
      isAdmin: false,
      isAnalyst: false,
      capabilities: { ...ALL_ON, etlEnabled: false },
    };
    expect(stateOf("admin", both)).toBe("hidden");
  });

  it("masque le domaine analytique à un non-analyste, le montre à un analyste", () => {
    // Régression (Finding 7) : SqlLabPage refuse l'accès à qui n'est pas
    // analyste — le domaine ne doit donc pas apparaître dans le chrome pour
    // ce profil, sous peine de proposer un point d'entrée mort.
    expect(stateOf("analytics", creator)).toBe("hidden");
    expect(stateOf("analytics", admin)).toBe("visible");
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
    // isAnalyst: true ici pour que "analytics" reste dans la liste attendue
    // ci-dessous — ce test porte sur le verrouillage par capacité
    // (etlEnabled), pas sur le masquage par rôle (couvert séparément).
    const etlOff: Profile = {
      ...creator,
      isAnalyst: true,
      capabilities: { ...ALL_ON, etlEnabled: false },
    };
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
