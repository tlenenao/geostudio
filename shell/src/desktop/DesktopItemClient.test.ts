// SPDX-License-Identifier: Apache-2.0
// shell/src/desktop/DesktopItemClient.test.ts
import { describe, expect, it, vi, beforeEach } from "vitest";
import { createDesktopItemClient } from "./DesktopItemClient";

const CONNECTION = { baseUrl: "http://127.0.0.1:9999", token: "s3cr3t" };

describe("createDesktopItemClient", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("sends the bearer token on every sidecar request", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ "reader.file": { kind: "reader", paramsSchema: {} } }), {
        status: 200,
      }),
    );
    const client = createDesktopItemClient(CONNECTION);
    await client.getPipelineOps();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:9999/pipelines/ops");
    expect((init?.headers as Record<string, string>)["Authorization"]).toBe("Bearer s3cr3t");
  });

  it("createPipelineItem builds a local Item and PUTs the payload to the sidecar", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = createDesktopItemClient(CONNECTION);
    const payload = { nodes: [], edges: [] };
    const item = await client.createPipelineItem({
      title: "Mon pipeline",
      owner: "local",
      pipeline: payload,
    });
    expect(item.resourceType).toBe("pipeline");
    expect(item.title).toBe("Mon pipeline");
    expect(item.pk).toBeTruthy();
    // Correction par rapport au brief (piège n°3, CLAUDE.md) : ItemPermissions
    // (shell/src/auth/permissions.ts) n'a pas de champ `canWrite` — c'est
    // `write` (Record<"read"|"write"|"delete"|"share", boolean>).
    // OWNER_PERMISSIONS = {read,write,delete,share}: true, donc `write: true`
    // est l'assertion réelle équivalente à l'intention du brief.
    expect(item.permissions).toEqual(expect.objectContaining({ write: true }));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`http://127.0.0.1:9999/pipelines/${item.pk}`);
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual(payload);
  });

  it("getPipelineConfig fetches the last PUT payload back from the sidecar's own store", async () => {
    // Le sidecar n'a pas de GET /pipelines/{id} dédié (contrat §3.1 du
    // roadmap) — getPipelineConfig doit donc garder le payload en mémoire
    // côté client desktop lui-même (jamais relu depuis le sidecar).
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = createDesktopItemClient(CONNECTION);
    const payload = { nodes: [], edges: [] };
    const item = await client.createPipelineItem({ title: "t", owner: "o", pipeline: payload });
    const roundtripped = await client.getPipelineConfig(item.pk);
    expect(roundtripped).toEqual(payload);
  });

  it("listConfigRevisions resolves to an empty list instead of rejecting", async () => {
    const client = createDesktopItemClient(CONNECTION);
    await expect(client.listConfigRevisions("any-pk")).resolves.toEqual([]);
  });

  it("rollbackConfig rejects (no version history in desktop mode)", async () => {
    const client = createDesktopItemClient(CONNECTION);
    await expect(client.rollbackConfig("any-pk", 1)).rejects.toThrow();
  });

  it("listPipelineWebhookTokens rejects (webhooks are server-only, out of scope for v1)", async () => {
    const client = createDesktopItemClient(CONNECTION);
    await expect(client.listPipelineWebhookTokens("any-pk")).rejects.toThrow();
  });

  it("a method with no desktop meaning at all rejects with a clear message", async () => {
    const client = createDesktopItemClient(CONNECTION);
    await expect(client.listCollections()).rejects.toThrow(/desktop/i);
  });
});
