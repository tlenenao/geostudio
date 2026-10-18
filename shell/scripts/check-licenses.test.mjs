// SPDX-License-Identifier: Apache-2.0
import { test } from "node:test";
import assert from "node:assert/strict";
import { violations } from "./check-licenses.mjs";

test("GPL seule refusée, double licence avec branche permissive acceptée, exception honorée", () => {
  const pkgs = [
    { name: "a", license: "MIT" },
    { name: "b", license: "GPL-3.0-only" },
    { name: "c", license: "(MIT OR GPL-3.0-or-later)" },
    { name: "d", license: "LGPL-2.1" },
  ];
  assert.deepEqual(violations(pkgs, {}), ["b: GPL-3.0-only", "d: LGPL-2.1"]);
  assert.deepEqual(violations(pkgs, { b: "x" }), ["d: LGPL-2.1"]);
});
