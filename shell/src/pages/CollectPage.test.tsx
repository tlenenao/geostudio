// SPDX-License-Identifier: Apache-2.0
import "fake-indexeddb/auto";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ApiError } from "../api/ApiError";
import type { CollectKit } from "../api/types";
import { DB_NAME, closeDb } from "../offline/db";

vi.mock("../config", () => ({ loadRuntimeConfig: () => ({ coreUrl: "http://core" }) }));
const fetchPublicKit = vi.fn();
const submitPublic = vi.fn();
vi.mock("../api/domains/publicSubmit", () => ({
  fetchPublicKit: (...a: unknown[]) => fetchPublicKit(...a),
  submitPublic: (...a: unknown[]) => submitPublic(...a),
}));

import { CollectPage } from "./CollectPage";

const kit = (over: Partial<CollectKit> = {}): CollectKit => ({
  version: 1,
  title: "Relevé de terrain",
  schema: {
    geometry: { column: "geom", type: "Point", srid: 4326 },
    fields: [
      { name: "nom", type: "string", required: true, label: "Nom" },
      { name: "age", type: "integer", required: false, label: "Âge" },
    ],
  },
  rules: [
    { id: "r1", kind: "constraint", field: "age", expression: "age >= 18", message: "Majeur" },
  ],
  geometryRequired: false,
  updatedAt: null,
  etag: "abc",
  ...over,
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CollectPage token="tok" />
    </QueryClientProvider>,
  );
}

beforeEach(async () => {
  fetchPublicKit.mockReset();
  submitPublic.mockReset();
  await closeDb();
  await new Promise<void>((res) => {
    const r = indexedDB.deleteDatabase(DB_NAME);
    r.onsuccess = () => res();
  });
});
afterEach(cleanup);

test("affiche le titre du kit dans un <h1> et envoie la saisie avec un clientOpId", async () => {
  fetchPublicKit.mockResolvedValue(kit());
  submitPublic.mockResolvedValue(undefined);
  const user = userEvent.setup();
  renderPage();
  expect(await screen.findByRole("heading", { level: 1, name: "Relevé de terrain" })).toBeTruthy();
  await user.type(screen.getByLabelText(/^Nom/), "Marie");
  await user.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(submitPublic).toHaveBeenCalledTimes(1));
  const [, token, sub] = submitPublic.mock.calls[0];
  expect(token).toBe("tok");
  expect(sub.feature.properties).toEqual({ nom: "Marie" });
  expect(sub.clientOpId).toMatch(/^[0-9a-f-]{36}$/);
  expect(sub.honeypot).toBe("");
  expect(await screen.findByText(/votre saisie a bien été envoyée/)).toBeTruthy();
});

test("un champ requis vide ou une règle du kit violée bloque l'envoi", async () => {
  fetchPublicKit.mockResolvedValue(kit());
  const user = userEvent.setup();
  renderPage();
  await screen.findByLabelText(/^Nom/);
  await user.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(submitPublic).not.toHaveBeenCalled();
  await user.type(screen.getByLabelText(/^Nom/), "Marie");
  await user.type(screen.getByLabelText(/^Âge/), "12");
  await user.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(await screen.findByText("Majeur")).toBeTruthy();
  expect(submitPublic).not.toHaveBeenCalled();
});

test("géométrie requise : refus sans position, envoi avec", async () => {
  fetchPublicKit.mockResolvedValue(kit({ geometryRequired: true }));
  submitPublic.mockResolvedValue(undefined);
  const user = userEvent.setup();
  renderPage();
  await screen.findByLabelText(/^Nom/);
  await user.type(screen.getByLabelText(/^Nom/), "Marie");
  await user.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(submitPublic).not.toHaveBeenCalled();
  await user.type(screen.getByLabelText("Longitude"), "2.35");
  await user.type(screen.getByLabelText("Latitude"), "48.85");
  await user.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(submitPublic).toHaveBeenCalled());
  expect(submitPublic.mock.calls[0][2].feature.geometry).toEqual({
    type: "Point",
    coordinates: [2.35, 48.85],
  });
});

test("une panne à l'envoi garde la saisie, et le renvoi réutilise le même clientOpId", async () => {
  fetchPublicKit.mockResolvedValue(kit());
  submitPublic.mockRejectedValueOnce(new ApiError(429, { detail: "too many submissions" }));
  submitPublic.mockResolvedValueOnce(undefined);
  const user = userEvent.setup();
  renderPage();
  await screen.findByLabelText(/^Nom/);
  await user.type(screen.getByLabelText(/^Nom/), "Marie");
  await user.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(await screen.findByText(/Trop d'envois/)).toBeTruthy();
  expect((screen.getByLabelText(/^Nom/) as HTMLInputElement).value).toBe("Marie");
  await user.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(submitPublic).toHaveBeenCalledTimes(2));
  expect(submitPublic.mock.calls[1][2].clientOpId).toBe(submitPublic.mock.calls[0][2].clientOpId);
});

test("lien révoqué (410) et inconnu (404) : message dédié, aucun formulaire", async () => {
  fetchPublicKit.mockRejectedValueOnce(new ApiError(410));
  renderPage();
  expect(await screen.findByText(/expiré ou a été révoqué/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Envoyer" })).toBeNull();
  cleanup();
  fetchPublicKit.mockRejectedValueOnce(new ApiError(404));
  renderPage();
  expect(await screen.findByText(/introuvable/)).toBeTruthy();
});

test("le champ piège est rempli : transmis tel quel, le cœur l'écarte en silence", async () => {
  fetchPublicKit.mockResolvedValue(kit());
  submitPublic.mockResolvedValue(undefined);
  const user = userEvent.setup();
  renderPage();
  await screen.findByLabelText(/^Nom/);
  await user.type(screen.getByLabelText(/^Nom/), "Bot");
  await user.type(screen.getByLabelText("Ne pas remplir ce champ", { selector: "input" }), "x");
  await user.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(submitPublic).toHaveBeenCalled());
  expect(submitPublic.mock.calls[0][2].honeypot).toBe("x");
});

test("hors réseau : la saisie est mise en file locale (même opId), puis envoyée au retour du réseau", async () => {
  fetchPublicKit.mockResolvedValue(kit());
  const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
  const user = userEvent.setup();
  renderPage();
  await screen.findByLabelText(/^Nom/);
  await user.type(screen.getByLabelText(/^Nom/), "Marie");
  await user.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(await screen.findAllByText(/Hors-ligne : saisie enregistrée/)).toBeTruthy();
  expect(submitPublic).not.toHaveBeenCalled();
  expect(await screen.findByText("En attente d'envoi")).toBeTruthy();
  online.mockReturnValue(true);
  submitPublic.mockResolvedValue(undefined);
  window.dispatchEvent(new Event("online"));
  await waitFor(() => expect(submitPublic).toHaveBeenCalledTimes(1));
  expect(submitPublic.mock.calls[0][2].feature.properties).toEqual({ nom: "Marie" });
  expect(await screen.findByText("Envoyée")).toBeTruthy();
  online.mockRestore();
});

test("cœur injoignable pendant l'envoi : mise en file avec le même clientOpId", async () => {
  fetchPublicKit.mockResolvedValue(kit());
  const { CoreUnreachableError } = await import("../api/CoreUnreachableError");
  // Le passage de synchro qui suit échoue aussi (réseau toujours coupé) : la saisie reste en file.
  submitPublic.mockRejectedValue(new CoreUnreachableError());
  const user = userEvent.setup();
  renderPage();
  await screen.findByLabelText(/^Nom/);
  await user.type(screen.getByLabelText(/^Nom/), "Marie");
  await user.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(await screen.findAllByText(/Hors-ligne : saisie enregistrée/)).toBeTruthy();
  await waitFor(() => expect(submitPublic.mock.calls.length).toBeGreaterThanOrEqual(2));
  expect(submitPublic.mock.calls[1][2].clientOpId).toBe(submitPublic.mock.calls[0][2].clientOpId);
});
