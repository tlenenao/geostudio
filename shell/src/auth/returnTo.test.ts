// SPDX-License-Identifier: Apache-2.0
import { currentReturnTo, safeReturnTo } from "./returnTo";

test("currentReturnTo garde chemin, query et hash", () => {
  expect(currentReturnTo({ pathname: "/items/3", search: "?tab=a", hash: "#x" })).toBe(
    "/items/3?tab=a#x",
  );
});
test("currentReturnTo ignore l'URL de callback OIDC", () => {
  expect(currentReturnTo({ pathname: "/", search: "?code=1&state=2", hash: "" })).toBe("/");
});
test("safeReturnTo refuse les destinations externes", () => {
  expect(safeReturnTo("/items/3")).toBe("/items/3");
  expect(safeReturnTo("//evil.com")).toBe("/");
  expect(safeReturnTo("https://evil.com")).toBe("/");
  expect(safeReturnTo(undefined)).toBe("/");
});
