// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import * as sdk from "./sdk";

test("re-exports the widget registry functions and types", () => {
  expect(typeof sdk.registerWidget).toBe("function");
  expect(typeof sdk.getWidget).toBe("function");
  expect(typeof sdk.listWidgets).toBe("function");
});

test("re-exports the action/data/variables hooks", () => {
  expect(typeof sdk.useBusAction).toBe("function");
  expect(typeof sdk.useSetFilter).toBe("function");
  expect(typeof sdk.useVariables).toBe("function");
  expect(typeof sdk.useSetVariable).toBe("function");
});
