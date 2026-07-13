import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test } from "vitest";
import { makeLazyWcHost } from "./LazyWcHost";
import { _resetModuleCache } from "./moduleCache";
import type { ExtensionManifest } from "../../api/types";
import type { WidgetContext } from "../registry";

afterEach(cleanup);
beforeEach(() => _resetModuleCache());

const readyManifest: ExtensionManifest = {
  type: "test.lazy-ready", tag: "test-lazy-ready-widget", label: "Test prêt",
  props: [], defaultSize: { w: 2, h: 2 },
  moduleUrl: "./__fixtures__/dummyLazyWidget.ts",
};

const errorManifest: ExtensionManifest = {
  type: "test.lazy-error", tag: "test-lazy-error-widget", label: "Test en échec",
  props: [], defaultSize: { w: 2, h: 2 },
  moduleUrl: "./__fixtures__/does-not-exist.ts",
};

test("shows a loading placeholder, then delegates to WcHost once the module resolves", async () => {
  const LazyWcHost = makeLazyWcHost(readyManifest);
  const ctx = { mode: "runtime" } as WidgetContext;
  const { container } = render(<LazyWcHost props={{}} ctx={ctx} />);
  expect(screen.getByText("Chargement…")).toBeInTheDocument();
  await waitFor(() => expect(container.querySelector("test-lazy-ready-widget")).not.toBeNull());
});

test("shows an error placeholder when the module import rejects", async () => {
  const LazyWcHost = makeLazyWcHost(errorManifest);
  const ctx = { mode: "runtime" } as WidgetContext;
  render(<LazyWcHost props={{}} ctx={ctx} />);
  expect(await screen.findByText("Extension indisponible")).toBeInTheDocument();
});
