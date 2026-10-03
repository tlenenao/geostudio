// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { editorPath } from "./editorPath";

const writer = { permissions: { read: true, write: true, delete: false, share: false } };
const reader = { permissions: { read: true, write: false, delete: false, share: false } };

test("un lecteur ouvre une app en usage, un éditeur dans le builder (P35.02)", () => {
  expect(editorPath("1", "app", reader)).toBe("/apps/1");
  expect(editorPath("1", "dashboard", reader)).toBe("/apps/1");
  expect(editorPath("1", "app", writer)).toBe("/apps/1/edit");
  expect(editorPath("1", "app")).toBe("/apps/1/edit");
  expect(editorPath("1", "map", reader)).toBe("/maps/1");
  expect(editorPath("1", "dataset", reader)).toBe("/datasets/1/edit");
});
