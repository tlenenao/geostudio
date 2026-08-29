// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { t } from "./index";
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

describe("catalogue français", () => {
  it("n'a aucune valeur vide", () => {
    for (const [key, value] of Object.entries(fr)) {
      expect(value.trim(), `message vide pour ${key}`).not.toBe("");
    }
  });

  it("nomme ses clés en <domaine>.<intention>", () => {
    for (const key of Object.keys(fr)) {
      expect(key, `clé mal formée : ${key}`).toMatch(/^[a-z][a-zA-Z0-9]*\.[a-zA-Z0-9]+$/);
    }
  });
});
