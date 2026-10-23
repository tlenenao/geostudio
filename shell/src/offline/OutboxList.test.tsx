// SPDX-License-Identifier: Apache-2.0
import "fake-indexeddb/auto";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { DB_NAME, closeDb, type OutboxEntry } from "./db";
import { enqueue, listEntries } from "./outbox";
import { OutboxList } from "./OutboxList";
import { SyncStatusPill } from "./SyncStatusPill";
import { OutboxContext, useOutboxEngine } from "./useOutbox";
import type { SyncTransport } from "./sync";

const OWNER = "t1:alice";
let transport: SyncTransport;

function Harness({ onEdit }: { onEdit?: (e: OutboxEntry) => void }) {
  const api = useOutboxEngine(OWNER, transport);
  return (
    <OutboxContext.Provider value={api}>
      <SyncStatusPill />
      {api && <OutboxList api={api} onEdit={onEdit ?? (() => {})} />}
    </OutboxContext.Provider>
  );
}

beforeEach(async () => {
  await closeDb();
  await new Promise<void>((res) => {
    const r = indexedDB.deleteDatabase(DB_NAME);
    r.onsuccess = () => res();
  });
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false); // pas de synchro automatique
  transport = { mode: "separate", create: vi.fn(async () => ({ fid: "1" })), uploadBlob: vi.fn() };
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const add = (n: number) =>
  enqueue(OWNER, {
    opId: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    collectionId: "c",
    payload: { properties: { n }, geometry: null },
  });

test("la pastille annonce le nombre de saisies en attente (aria-live) et la liste montre leur état", async () => {
  await add(1);
  await add(2);
  render(<Harness />);
  const pill = await screen.findByRole("button", { name: /2 saisies à envoyer/ });
  expect(pill.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
  expect(screen.getAllByText("En attente d'envoi")).toHaveLength(2);
});

test("abandon : confirmation puis suppression de la saisie", async () => {
  const e = await add(1);
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Abandonner" }));
  await userEvent.click(await screen.findByRole("button", { name: "Abandonner", hidden: false }));
  await waitFor(async () => expect(await listEntries(OWNER)).toEqual([]));
  expect(e.opId).toBeTruthy();
});

test("conflit : détails d'erreur, export JSON et modification proposés", async () => {
  const e = await add(1);
  const { updateEntry } = await import("./outbox");
  await updateEntry(OWNER, e.opId, {
    state: "conflict",
    lastError: "invalid",
    lastDetail: "boom",
    fieldErrors: [{ field: "nom", code: "required", message: "obligatoire" }],
  });
  const onEdit = vi.fn();
  render(<Harness onEdit={onEdit} />);
  expect(await screen.findByText("À corriger")).toBeInTheDocument();
  expect(screen.getByText("nom : obligatoire")).toBeInTheDocument();
  expect(screen.getByText("Détails de l'erreur")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Exporter en JSON" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Modifier" }));
  expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ opId: e.opId }));
});
