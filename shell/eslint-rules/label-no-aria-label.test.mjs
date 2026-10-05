// SPDX-License-Identifier: Apache-2.0
import { RuleTester } from "eslint";
import { describe, it } from "vitest";
import rule from "./label-no-aria-label.mjs";

RuleTester.describe = describe;
RuleTester.it = it;
RuleTester.itOnly = it.only;

const tester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: "module",
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
});

tester.run("label-no-aria-label", rule, {
  valid: [
    "const a = <label>Nom <input /></label>;",
    'const a = <label htmlFor="x">Nom</label>;',
    'const a = <input aria-label="Rechercher" />;',
    // Select du kit : aria-label imposé par son type (déclencheur Radix)
    'const a = <label>Taille <Select aria-label="Taille" /></label>;',
  ],
  invalid: [
    {
      code: 'const a = <label>Nom <input aria-label="Nom du champ" /></label>;',
      errors: [{ messageId: "dup" }],
    },
    {
      code: 'const a = <label><span>Taille</span><Input aria-label="Taille" /></label>;',
      errors: [{ messageId: "dup" }],
    },
    {
      code: 'const a = <label>Nom <div><textarea aria-labelledby="z" /></div></label>;',
      errors: [{ messageId: "dup" }],
    },
  ],
});
