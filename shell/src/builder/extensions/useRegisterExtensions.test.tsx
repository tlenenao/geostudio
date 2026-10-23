// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { ExtensionManifest, ItemClient } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { _resetRegistry, getWidget } from "../registry";
import {
  _resetRegisteredExtensions,
  reconcileExtensions,
  useRegisterExtensions,
} from "./useRegisterExtensions";

const manifest = (type: string, label = type): ExtensionManifest => ({
  type,
  tag: "x-widget",
  label,
  props: [],
  defaultSize: { w: 1, h: 1 },
  moduleUrl: "https://c.example.com/w.js",
});

beforeEach(() => {
  _resetRegistry();
  _resetRegisteredExtensions();
});

test("reconcile : enregistre, met à jour sans avertissement d'écrasement, retire les disparus", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  reconcileExtensions([manifest("acme.a"), manifest("acme.b")]);
  expect(getWidget("acme.a")?.label).toBe("acme.a");

  reconcileExtensions([manifest("acme.a", "A bis")]);
  expect(getWidget("acme.a")?.label).toBe("A bis");
  expect(getWidget("acme.b")).toBeUndefined();
  expect(warn).not.toHaveBeenCalled();
  warn.mockRestore();
});

test("reconcile : un type retiré du registre est ré-enregistré même sans changement de manifeste", () => {
  reconcileExtensions([manifest("acme.a")]);
  _resetRegistry();
  reconcileExtensions([manifest("acme.a")]);
  expect(getWidget("acme.a")).toBeDefined();
});

function wrapper(client: Partial<ItemClient>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client as ItemClient}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("useRegisterExtensions : true une fois les extensions enregistrées", async () => {
  const { result } = renderHook(() => useRegisterExtensions(), {
    wrapper: wrapper({ listActiveExtensions: async () => [manifest("acme.pub")] }),
  });
  expect(result.current).toBe(false);
  await waitFor(() => expect(result.current).toBe(true));
  expect(getWidget("acme.pub")).toBeDefined();
});

test("useRegisterExtensions : fail-open quand /extensions échoue", async () => {
  const { result } = renderHook(() => useRegisterExtensions(), {
    wrapper: wrapper({
      listActiveExtensions: async () => {
        throw new Error("down");
      },
    }),
  });
  await waitFor(() => expect(result.current).toBe(true));
});
