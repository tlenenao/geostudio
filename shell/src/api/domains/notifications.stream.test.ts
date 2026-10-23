// SPDX-License-Identifier: Apache-2.0
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { runNotificationStream } from "./notifications.hooks";
import { createNotificationsMethods } from "./notifications";
import type { ItemClientBase } from "../base";

describe("subscribeNotifications", () => {
  it("décode les trames SSE découpées n'importe où et ignore les battements", async () => {
    const enc = new TextEncoder();
    const chunks = [
      "retry: 5000\n\nevent: notif",
      'ications\ndata: {"unread": 3}\n\n: ping\n\n',
      'event: notifications\ndata: {"unread": 0}\n\n',
    ];
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        chunks.forEach((s) => {
          c.enqueue(enc.encode(s));
        });
        c.close();
      },
    });
    const base = {
      coreUrl: "http://core/v1",
      authFetch: vi.fn().mockResolvedValue(new Response(body, { status: 200 })),
    } as unknown as ItemClientBase;
    const seen: number[] = [];
    await createNotificationsMethods(base).subscribeNotifications(
      (n) => seen.push(n),
      new AbortController().signal,
    );
    expect(seen).toEqual([3, 0]);
  });
});

describe("runNotificationStream", () => {
  it("met à jour le compte, invalide la liste, se reconnecte et s'arrête sur abort", async () => {
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, "invalidateQueries").mockResolvedValue();
    const ac = new AbortController();
    let calls = 0;
    const client = {
      subscribeNotifications: vi.fn((onUnread: (n: number) => void) => {
        calls += 1;
        if (calls === 1) onUnread(2);
        if (calls === 2) onUnread(2); // inchangé : pas de refetch
        if (calls === 3) return Promise.reject(new Error("coupé"));
        if (calls === 4) ac.abort();
        return Promise.resolve();
      }),
    };
    const waits: number[] = [];
    await runNotificationStream(client, qc, ac.signal, (ms) => {
      waits.push(ms);
      return Promise.resolve();
    });
    expect(qc.getQueryData(["notifications", "unread-count"])).toBe(2);
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(waits).toEqual([1_000, 1_000, 10_000, 1_000]);
    expect(client.subscribeNotifications).toHaveBeenCalledTimes(4);
  });
});
