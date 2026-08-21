// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { collectWidgetTypes } from "./collectWidgetTypes";
import type { AppConfig } from "../../api/types";

function config(itemsByPage: string[][]): AppConfig {
  return {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    navigationMode: "tabs",
    variables: [],
    pages: itemsByPage.map((types, pi) => ({
      id: `p${pi}`,
      name: `P${pi}`,
      onEnter: [],
      layout: {
        type: "grid",
        breakpoints: {},
        items: types.map((t, i) => ({
          id: `w${pi}-${i}`,
          widget: t,
          x: 0,
          y: i,
          w: 4,
          h: 2,
          props: {},
        })),
      },
    })),
  } as unknown as AppConfig;
}

describe("collectWidgetTypes", () => {
  it("collects distinct widget types across all pages", () => {
    const types = collectWidgetTypes(
      config([
        ["text", "map"],
        ["text", "form"],
      ]),
    );
    expect([...types].sort()).toEqual(["form", "map", "text"]);
  });

  it("returns an empty set for a config with no widgets", () => {
    expect(collectWidgetTypes(config([[]]))).toEqual(new Set());
  });

  it("collects widget types from the top-level layout when pages is empty (legacy/implicit single-page shape)", () => {
    const legacyConfig = {
      kind: "app",
      theme: {},
      dataSources: [],
      messages: [],
      navigationMode: "tabs",
      variables: [],
      pages: [],
      layout: {
        type: "grid",
        breakpoints: {},
        items: [{ id: "w0", widget: "form", x: 0, y: 0, w: 4, h: 2, props: {} }],
      },
    } as unknown as AppConfig;
    expect(collectWidgetTypes(legacyConfig)).toEqual(new Set(["form"]));
  });
});
