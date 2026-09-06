// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { resolveMessageKey, t } from "./index";
import { fr } from "./catalog.fr";

describe("t", () => {
  it("rend le message du catalogue", () => {
    expect(t("actions.edit")).toBe("Modifier");
  });

  it("interpole les paramètres nommés", () => {
    expect(t("actions.deleteMessage", { title: "Réseau d'eau potable" })).toBe(
      "Supprimer « Réseau d'eau potable » ? Cette action est irréversible.",
    );
  });

  it("laisse le gabarit en place quand un paramètre manque", () => {
    // Visible plutôt que silencieux : un « {title} » à l'écran se remarque,
    // une chaîne vide non.
    expect(t("actions.deleteMessage", {})).toContain("{title}");
  });

  it("accepte un nombre comme paramètre", () => {
    expect(t("catalog.count", { n: 68 })).toBe("68 éléments");
  });

  it("rejette une clé inconnue à la compilation", () => {
    // @ts-expect-error clé absente du catalogue
    expect(() => t("cle.inexistante")).toBeDefined();
  });
});

describe("resolveMessageKey", () => {
  it("garde une clé qui existe réellement dans le catalogue", () => {
    expect(resolveMessageKey("actions.edit", "roles.privilege.unknown")).toBe("actions.edit");
  });

  it("retombe sur le repli quand la clé est absente du catalogue (REV-064)", () => {
    // Cas réel : `GET /roles/catalog` renvoie une labelKey que le shell ne
    // connaît pas encore (dérive cœur/shell). Un cast non sûr laissait
    // passer cette clé telle quelle jusqu'à `t()`, qui rendait `undefined`
    // — case à cocher sans libellé ni aria-label, silencieusement.
    expect(resolveMessageKey("roles.privilege.doesNotExist", "roles.privilege.unknown")).toBe(
      "roles.privilege.unknown",
    );
  });
});

describe("catalogue français", () => {
  it("n'a aucune valeur vide", () => {
    for (const [key, value] of Object.entries(fr)) {
      expect(value.trim(), `message vide pour ${key}`).not.toBe("");
    }
  });

  it("nomme ses clés en <domaine>.<intention> (ou <domaine>.privilege.<intention> pour les libellés de privilège, dont la clé est un contrat de données avec le cœur — cf. PRIVILEGE_METADATA, core/app/roles/privileges.py)", () => {
    for (const key of Object.keys(fr)) {
      expect(key, `clé mal formée : ${key}`).toMatch(
        /^[a-z][a-zA-Z0-9]*\.([a-zA-Z0-9]+|privilege\.[a-zA-Z0-9]+)$/,
      );
    }
  });
});
