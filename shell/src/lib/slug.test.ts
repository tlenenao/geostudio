// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from "vitest";
import { slugify, isValidSlug } from "./slug";

describe("slugify (client)", () => {
  it.each([
    ["Mon Portail", "mon-portail"],
    ["Été à Lyon !", "ete-a-lyon"],
    ["  double   espace  ", "double-espace"],
    ["", "site"],
  ])("slugify(%s) = %s", (input, expected) => {
    expect(slugify(input)).toBe(expected);
  });
});

describe("isValidSlug", () => {
  it.each([
    ["mon-portail", true],
    ["Mon-Portail", false],
    ["-x", false],
    ["a--b", false],
    ["", false],
  ])("isValidSlug(%s) = %s", (slug, valid) => {
    expect(isValidSlug(slug)).toBe(valid);
  });
});
