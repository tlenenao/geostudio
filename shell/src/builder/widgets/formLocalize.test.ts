// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, test } from "vitest";
import { activateLocale } from "../../i18n";
import { localizeField, type FormField } from "./form";

const base: FormField = {
  name: "nom",
  type: "string",
  label: "Nom",
  order: 0,
  hidden: false,
  required: false,
  hint: "Votre nom",
  labels: { en: "Name" },
};

afterEach(() => activateLocale("fr"));

test("AUD-115 c : libellé traduit selon la langue active, repli sur le texte source", async () => {
  expect(localizeField(base).label).toBe("Nom");
  await activateLocale("en");
  const en = localizeField(base);
  expect(en.label).toBe("Name");
  expect(en.hint).toBe("Votre nom"); // pas de `hints.en` : repli
});
