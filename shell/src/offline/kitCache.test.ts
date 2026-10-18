// @vitest-environment node
// SPDX-License-Identifier: Apache-2.0
import "fake-indexeddb/auto";
import { beforeEach, expect, test, vi } from "vitest";
import { ApiError } from "../api/ApiError";
import { CoreUnreachableError } from "../api/CoreUnreachableError";
import type { CollectKit } from "../api/types";
import { DB_NAME, closeDb } from "./db";
import { KitUnavailableError, loadKit } from "./kitCache";
import { KIT_MAX_AGE_MS, getKit } from "./outbox";

const A = "t1:alice";
const KEY = "t1:alice:c1";
const kit = (etag: string): CollectKit => ({
  version: 1,
  title: `K-${etag}`,
  schema: { geometry: null, fields: [] },
  rules: [],
  geometryRequired: false,
  updatedAt: null,
  etag,
});

beforeEach(async () => {
  await closeDb();
  await new Promise<void>((res) => {
    const r = indexedDB.deleteDatabase(DB_NAME);
    r.onsuccess = () => res();
  });
});

test("en ligne : premier chargement sans ETag, puis revalidation If-None-Match", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(kit("e1")).mockResolvedValueOnce(null);
  const first = await loadKit(A, KEY, fetcher, 1000);
  expect(fetcher).toHaveBeenLastCalledWith(undefined);
  expect(first).toMatchObject({ fromCache: false, expired: false });
  expect(first.kit.etag).toBe("e1");
  const second = await loadKit(A, KEY, fetcher, 2000);
  expect(fetcher).toHaveBeenLastCalledWith("e1");
  expect(second.kit.title).toBe("K-e1");
});

test("304 : le contenu n'est pas réécrit mais la fraîcheur avance (le kit n'expire pas à tort)", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(kit("e1")).mockResolvedValue(null);
  await loadKit(A, KEY, fetcher, 1000);
  const before = (await getKit(A, KEY, 1000))!;
  const later = 1000 + KIT_MAX_AGE_MS - 5;
  await loadKit(A, KEY, fetcher, later);
  const after = (await getKit(A, KEY, later + 10))!;
  expect(after.kit).toEqual(before.kit);
  expect(after.fetchedAt).toBe(later);
  expect(after.expired).toBe(false);
});

test("kit modifié côté serveur : le nouveau remplace l'ancien", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(kit("e1")).mockResolvedValueOnce(kit("e2"));
  await loadKit(A, KEY, fetcher, 1000);
  const r = await loadKit(A, KEY, fetcher, 2000);
  expect(r.kit.etag).toBe("e2");
  expect((await getKit(A, KEY, 2000))?.kit.title).toBe("K-e2");
});

test("hors ligne : le kit du cache est servi, signalé comme tel", async () => {
  await loadKit(A, KEY, vi.fn().mockResolvedValue(kit("e1")), 1000);
  const r = await loadKit(A, KEY, vi.fn().mockRejectedValue(new CoreUnreachableError()), 2000);
  expect(r).toMatchObject({ fromCache: true, expired: false });
  expect(r.kit.etag).toBe("e1");
});

test("hors ligne et jamais chargé : erreur explicite", async () => {
  await expect(
    loadKit(A, KEY, vi.fn().mockRejectedValue(new CoreUnreachableError()), 1000),
  ).rejects.toBeInstanceOf(KitUnavailableError);
});

test("hors ligne avec un kit de plus de 14 jours : servi mais marqué périmé", async () => {
  await loadKit(A, KEY, vi.fn().mockResolvedValue(kit("e1")), 1000);
  const r = await loadKit(
    A,
    KEY,
    vi.fn().mockRejectedValue(new CoreUnreachableError()),
    1000 + KIT_MAX_AGE_MS + 1,
  );
  expect(r).toMatchObject({ fromCache: true, expired: true });
});

test("une vraie réponse d'erreur du serveur (410, 403) n'est jamais masquée par le cache", async () => {
  await loadKit(A, KEY, vi.fn().mockResolvedValue(kit("e1")), 1000);
  await expect(
    loadKit(A, KEY, vi.fn().mockRejectedValue(new ApiError(410)), 2000),
  ).rejects.toMatchObject({ status: 410 });
});

test("un autre propriétaire ne reçoit pas le kit en cache d'autrui", async () => {
  await loadKit(A, KEY, vi.fn().mockResolvedValue(kit("e1")), 1000);
  await expect(
    loadKit("t1:bob", KEY, vi.fn().mockRejectedValue(new CoreUnreachableError()), 2000),
  ).rejects.toBeInstanceOf(KitUnavailableError);
});

test("IndexedDB indisponible : le kit en ligne est servi quand même", async () => {
  const spy = vi.spyOn(indexedDB, "open").mockImplementation(() => {
    throw new Error("storage blocked");
  });
  await closeDb();
  const r = await loadKit(A, KEY, vi.fn().mockResolvedValue(kit("e1")), 1000);
  expect(r.kit.etag).toBe("e1");
  spy.mockRestore();
});
