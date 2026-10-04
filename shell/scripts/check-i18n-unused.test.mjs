// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { catalogKeys, dynamicPrefixes, findUnusedKeys } from "./check-i18n-unused.mjs";

describe("check-i18n-unused", () => {
  it("lit les clés du catalogue, valeur sur la même ligne ou la suivante", () => {
    const src = [
      "export const fr = {",
      '  "a.one": "Un",',
      '  "a.two":',
      '    "Deux",',
      "} as const;",
    ].join("\n");
    expect(catalogKeys(src)).toEqual(["a.one", "a.two"]);
  });

  it("extrait les préfixes de gabarit dynamique pointés, pas les gabarits sans point", () => {
    const src = "t(`extensions.field${name}`); t(`alertRule.state${s}`); `q${x}`; `joined_${f}`";
    expect(dynamicPrefixes(src)).toEqual(["extensions.field", "alertRule.state"]);
  });

  it("une clé citée entre guillemets, apostrophes ou backticks est utilisée", () => {
    const src = `t("a.one"); t('a.two'); t(\`a.three\`);`;
    expect(findUnusedKeys(["a.one", "a.two", "a.three", "a.four"], src)).toEqual(["a.four"]);
  });

  it("une clé couverte par un préfixe dynamique ou d'allowlist est utilisée", () => {
    const src = "t(`extensions.field${k}`)";
    expect(
      findUnusedKeys(["extensions.fieldLabel", "roles.privilege.dataView", "x.y"], src, [
        "roles.privilege.",
      ]),
    ).toEqual(["x.y"]);
  });

  it("une sous-chaîne d'une autre clé ne compte pas comme citation", () => {
    expect(findUnusedKeys(["a.b"], 't("a.bc")')).toEqual(["a.b"]);
  });
});
