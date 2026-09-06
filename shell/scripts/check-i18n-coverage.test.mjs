// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { detectViolations } from "./check-i18n-coverage.mjs";

describe("detectViolations", () => {
  it("détecte un texte JSX accentué", () => {
    const content = `export function X() {\n  return <p>Élément supprimé</p>;\n}\n`;
    const violations = detectViolations(content);
    expect(violations.some((v) => v.snippet.includes("Élément supprimé"))).toBe(true);
  });

  it('ne détecte pas un appel t("clé")', () => {
    // La clé contient délibérément un mot de la liste courte ("supprimer")
    // pour que ce test prouve vraiment que le filtre t() neutralise
    // l'argument — une clé neutre (ex. "items.deleted") ne prouverait rien,
    // elle ne serait de toute façon jamais détectée (piège CLAUDE.md n°10 :
    // vérifié par falsification, cf. Task 1 Step 3 du plan).
    const content = `import { t } from "@/i18n";\nexport function X() {\n  return <p>{t("actions.supprimer")}</p>;\n}\n`;
    const violations = detectViolations(content);
    expect(violations).toHaveLength(0);
  });

  it("ne détecte pas une chaîne française dans un commentaire", () => {
    // La chaîne entre guillemets, à l'intérieur du commentaire, doit être
    // neutralisée par le retrait des commentaires *avant* le scan des
    // chaînes littérales — sinon ce test ne prouverait rien (STRING_RE ne
    // verrait jamais un simple texte de commentaire sans guillemets).
    const content = `// TODO: revoir "Élément supprimé" avant la clôture\nexport function X() {\n  return <p>ok</p>;\n}\n`;
    const violations = detectViolations(content);
    expect(violations).toHaveLength(0);
  });

  it("détecte un attribut aria-label avec un mot de la liste courte, sans accent", () => {
    const content = `export function X() {\n  return <button aria-label="Fermer">x</button>;\n}\n`;
    const violations = detectViolations(content);
    expect(violations.some((v) => v.snippet.includes("Fermer"))).toBe(true);
  });

  it("ignore les lignes import", () => {
    const content = `import { Fermer } from "./annuler-supprimer-module";\nexport function X() {\n  return <p>ok</p>;\n}\n`;
    const violations = detectViolations(content);
    expect(violations).toHaveLength(0);
  });
});
