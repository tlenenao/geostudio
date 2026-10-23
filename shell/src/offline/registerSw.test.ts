// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, test, vi } from "vitest";
import { registerServiceWorker } from "./registerSw";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function fakeSw(opts: { controller: boolean; waiting?: boolean }) {
  const waiting = { postMessage: vi.fn() };
  const reg = {
    waiting: opts.waiting ? waiting : null,
    installing: null as unknown,
    listeners: {} as Record<string, () => void>,
    addEventListener(n: string, h: () => void) {
      this.listeners[n] = h;
    },
  };
  const swListeners: Record<string, () => void> = {};
  const container = {
    controller: opts.controller ? {} : null,
    register: vi.fn().mockResolvedValue(reg),
    addEventListener: (n: string, h: () => void) => void (swListeners[n] = h),
  };
  vi.stubGlobal("navigator", { serviceWorker: container });
  return { container, reg, waiting, swListeners };
}
const flush = () => new Promise((r) => setTimeout(r, 0));

test("hors build de production : rien n'est enregistré", () => {
  const { container } = fakeSw({ controller: false });
  vi.stubEnv("PROD", false);
  registerServiceWorker(vi.fn());
  expect(container.register).not.toHaveBeenCalled();
});

test("1re installation (pas de contrôleur) : enregistré, aucune annonce de mise à jour", async () => {
  const { container, reg } = fakeSw({ controller: false, waiting: true });
  vi.stubEnv("PROD", true);
  const onUpdate = vi.fn();
  registerServiceWorker(onUpdate);
  await flush();
  expect(container.register).toHaveBeenCalledWith("/sw.js");
  expect(reg.waiting).toBeTruthy();
  expect(onUpdate).not.toHaveBeenCalled();
});

test("mise à jour en attente : annoncée ; apply() demande SKIP_WAITING et recharge au changement de contrôleur", async () => {
  const { waiting, swListeners } = fakeSw({ controller: true, waiting: true });
  vi.stubEnv("PROD", true);
  const reload = vi.fn();
  vi.stubGlobal("window", { location: { reload }, addEventListener: vi.fn() });
  let apply!: () => void;
  registerServiceWorker((fn) => (apply = fn));
  await flush();
  expect(apply).toBeTypeOf("function");
  expect(waiting.postMessage).not.toHaveBeenCalled(); // jamais automatique
  apply();
  expect(waiting.postMessage).toHaveBeenCalledWith({ type: "SKIP_WAITING" });
  swListeners.controllerchange();
  expect(reload).toHaveBeenCalled();
});
