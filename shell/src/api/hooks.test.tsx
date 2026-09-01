// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "./itemClient";
import { ItemClientProvider } from "./ItemClientProvider";
import type { ItemClient } from "./types";
import {
  useAppConfig,
  useCandidateTables,
  useCollectionSharing,
  useCollectionsAdmin,
  useCreateBookmark,
  useCreateHarvestSource,
  useCreateItem,
  useCreateMap,
  useDeleteItem,
  useGroups,
  useHarvestSources,
  useInstanceInfo,
  useItem,
  useItems,
  useMapConfig,
  useMe,
  useRunHarvestSource,
  useSaveApp,
  useSaveMap,
  useSharing,
  useUpdateItem,
} from "./hooks";

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "test-token",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("useItems returns the mapped page", async () => {
  server.use(
    http.get("https://core.test/items", () =>
      HttpResponse.json({
        items: [
          {
            pk: "1",
            resourceType: "app",
            title: "Alpha",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "",
            configId: null,
            isPublished: false,
          },
          {
            pk: "2",
            resourceType: "dashboard",
            title: "Beta",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "",
            configId: null,
            isPublished: false,
          },
        ],
        total: 2,
        page: 1,
        pageSize: 12,
      }),
    ),
  );
  const { result } = renderHook(() => useItems({}), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.total).toBe(2);
});

test("useMe returns the current user", async () => {
  const { result } = renderHook(() => useMe(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.username).toBe("alice");
});

test("useInstanceInfo returns readOnly from the core", async () => {
  server.use(http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })));
  const { result } = renderHook(() => useInstanceInfo(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.readOnly).toBe(true);
});

test("useInstanceInfo degrades fail-open (data stays undefined, never a false positive) on network failure", async () => {
  server.use(http.get("https://core.test/instance", () => HttpResponse.error()));
  const { result } = renderHook(() => useInstanceInfo(), { wrapper });
  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(result.current.data?.readOnly).not.toBe(true);
});

test("useInstanceInfo returns exportEnabled from the core", async () => {
  server.use(
    http.get("https://core.test/instance", () =>
      HttpResponse.json({ readOnly: false, etlEnabled: false, exportEnabled: true }),
    ),
  );
  const { result } = renderHook(() => useInstanceInfo(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.exportEnabled).toBe(true);
});

test("useInstanceInfo falls back to exportEnabled: false when the client doesn't implement getInstanceInfo", async () => {
  const client = {} as unknown as ItemClient;
  const { result } = renderHook(() => useInstanceInfo(), { wrapper: makeWrapper(client) });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toEqual({ readOnly: false, etlEnabled: false, exportEnabled: false });
});

test("useCreateItem creates an item and returns it", async () => {
  const { result } = renderHook(() => useCreateItem(), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ kind: "app", title: "X", owner: "alice" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.pk).toBe("99");
});

test("useDeleteItem optimistically removes the item from the list", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "t",
  });
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
  queryClient.setQueryData(["items", {}], {
    items: [
      {
        pk: "1",
        resourceType: "app",
        title: "A",
        abstract: "",
        owner: "x",
        thumbnailUrl: null,
        date: "",
        configId: null,
        isPublished: false,
      },
      {
        pk: "2",
        resourceType: "app",
        title: "B",
        abstract: "",
        owner: "x",
        thumbnailUrl: null,
        date: "",
        configId: null,
        isPublished: false,
      },
    ],
    total: 2,
    page: 1,
    pageSize: 12,
  });

  const { result } = renderHook(() => useDeleteItem(), { wrapper: wrap });
  await act(async () => {
    await result.current.mutateAsync("1");
  });
  const page = queryClient.getQueryData(["items", {}]) as { items: { pk: string }[] };
  expect(page.items.map((i) => i.pk)).toEqual(["2"]);
});

test("useUpdateItem updates the cached item title", async () => {
  const { result } = renderHook(() => useUpdateItem("7"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ title: "Renamed" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.title).toBe("Renamed");
});

test("useGroups returns the mapped groups", async () => {
  const { result } = renderHook(() => useGroups(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.[0]).toEqual({ id: "10", title: "Équipe A" });
});

test("useSharing returns the item sharing", async () => {
  const { result } = renderHook(() => useSharing("7"), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.public).toBe(true);
});

function makeWrapper(client: ItemClient) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>{children}</ItemClientProvider>
      </QueryClientProvider>
    );
  };
}

test("useCreateMap creates a map and invalidates items", async () => {
  const client = {
    createMapItem: vi.fn().mockResolvedValue({ pk: "77", resourceType: "map", title: "C" }),
  } as unknown as ItemClient;
  const { result } = renderHook(() => useCreateMap(), { wrapper: makeWrapper(client) });
  await result.current.mutateAsync({ title: "C", owner: "alice" });
  expect(client.createMapItem).toHaveBeenCalledWith({ title: "C", owner: "alice" });
});

test("useCreateBookmark creates a bookmark and invalidates items", async () => {
  const client = {
    createBookmarkItem: vi
      .fn()
      .mockResolvedValue({ pk: "bookmark-1", resourceType: "bookmark", title: "Ma vue" }),
  } as unknown as ItemClient;
  const { result } = renderHook(() => useCreateBookmark(), { wrapper: makeWrapper(client) });
  await result.current.mutateAsync({
    title: "Ma vue",
    owner: "alice",
    appId: "app-1",
    pageId: "page-1",
    timeRange: null,
    extent: null,
    crossFilter: {},
  });
  expect(client.createBookmarkItem).toHaveBeenCalledWith({
    title: "Ma vue",
    owner: "alice",
    appId: "app-1",
    pageId: "page-1",
    timeRange: null,
    extent: null,
    crossFilter: {},
  });
});

test("useMapConfig loads a map config", async () => {
  const cfg = { basemap: { style: "s" }, view: { center: [0, 0], zoom: 1 }, layers: [] };
  const client = { getMapConfig: vi.fn().mockResolvedValue(cfg) } as unknown as ItemClient;
  const { result } = renderHook(() => useMapConfig("77"), { wrapper: makeWrapper(client) });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toEqual(cfg);
  expect(client.getMapConfig).toHaveBeenCalledWith("77");
});

test("useSaveMap saves a map config", async () => {
  const client = { saveMapConfig: vi.fn().mockResolvedValue(undefined) } as unknown as ItemClient;
  const { result } = renderHook(() => useSaveMap("77"), { wrapper: makeWrapper(client) });
  const cfg = {
    basemap: { style: "s" },
    view: { center: [0, 0] as [number, number], zoom: 1 },
    layers: [],
  };
  await result.current.mutateAsync(cfg);
  expect(client.saveMapConfig).toHaveBeenCalledWith("77", cfg);
});

test("useAppConfig loads an app config", async () => {
  const cfg = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
  const client = { getAppConfig: vi.fn().mockResolvedValue(cfg) } as unknown as ItemClient;
  const { result } = renderHook(() => useAppConfig("5"), { wrapper: makeWrapper(client) });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toEqual(cfg);
});

test("useAppConfig forwards mode to the client", async () => {
  const cfg = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
  const client = { getAppConfig: vi.fn().mockResolvedValue(cfg) } as unknown as ItemClient;
  const { result } = renderHook(() => useAppConfig("5", { mode: "runtime" }), {
    wrapper: makeWrapper(client),
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(client.getAppConfig).toHaveBeenCalledWith("5", "runtime");
});

test("useSaveApp saves an app config", async () => {
  const client = { saveAppConfig: vi.fn().mockResolvedValue(undefined) } as unknown as ItemClient;
  const { result } = renderHook(() => useSaveApp("5"), { wrapper: makeWrapper(client) });
  const cfg = {
    kind: "app" as const,
    theme: {},
    dataSources: [],
    messages: [],
    layout: { type: "grid" as const, breakpoints: {}, items: [] },
  };
  await result.current.mutateAsync(cfg);
  expect(client.saveAppConfig).toHaveBeenCalledWith("5", cfg);
});

test("useCollectionsAdmin returns the mapped collections", async () => {
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents",
            title: "Incidents",
            description: "",
            tableName: "incidents",
            isPublic: false,
            editable: true,
            geometryType: "Point",
            srid: 4326,
            pkColumn: "id",
            canWrite: true,
            featureCount: 3,
            owner: "admin",
          },
        ],
      }),
    ),
  );
  const { result } = renderHook(() => useCollectionsAdmin(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.[0]?.owner).toBe("admin");
});

test("useCandidateTables returns the candidates list", async () => {
  server.use(
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          { tableName: "widgets", registrable: false, reason: "table has no primary key" },
        ],
      }),
    ),
  );
  const { result } = renderHook(() => useCandidateTables(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toEqual([
    { tableName: "widgets", registrable: false, reason: "table has no primary key" },
  ]);
});

test("useCollectionSharing returns the collection's sharing", async () => {
  server.use(
    http.get("https://core.test/collections/incidents/sharing", () =>
      HttpResponse.json({ public: true, groups: [] }),
    ),
  );
  const { result } = renderHook(() => useCollectionSharing("incidents"), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toEqual({ public: true, groups: [] });
});

test("useHarvestSources returns the mapped sources", async () => {
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: [
          {
            id: "src-1",
            type: "stac",
            url: "https://stac.example.com/collections",
            mode: "reference",
            enabled: true,
            intervalMinutes: 60,
            lastRunAt: null,
            lastStatus: null,
            lastError: null,
          },
        ],
      }),
    ),
  );
  const { result } = renderHook(() => useHarvestSources(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.[0]?.url).toBe("https://stac.example.com/collections");
});

test("useCreateHarvestSource posts the input and invalidates the list", async () => {
  let posted: unknown;
  server.use(
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json(
        {
          id: "src-2",
          type: "stac",
          url: "https://a",
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );
  const { result } = renderHook(() => useCreateHarvestSource(), { wrapper });
  await result.current.mutateAsync({
    type: "stac",
    url: "https://a",
    mode: "reference",
    enabled: true,
  });
  expect(posted).toEqual({ type: "stac", url: "https://a", mode: "reference", enabled: true });
});

test("useRunHarvestSource posts to the run endpoint", async () => {
  let called = false;
  server.use(
    http.post("https://core.test/harvest/sources/src-1/run", () => {
      called = true;
      return HttpResponse.json({ status: "queued" }, { status: 202 });
    }),
  );
  const { result } = renderHook(() => useRunHarvestSource(), { wrapper });
  await result.current.mutateAsync("src-1");
  expect(called).toBe(true);
});

test("useItem: enabled false ne déclenche aucune requête", () => {
  // Aucun handler MSW enregistré pour GET /items/x : si enabled n'est pas
  // câblé, la requête réelle échouerait bruyamment (onUnhandledRequest:
  // "error", shell/src/test/setup.ts) — mais on la détecte plus tôt, de
  // façon synchrone, via fetchStatus : "fetching" démarre immédiatement si
  // la requête part, "idle" si elle est bien désactivée.
  const { result } = renderHook(() => useItem("x", { enabled: false }), { wrapper });
  expect(result.current.fetchStatus).toBe("idle");
  expect(result.current.data).toBeUndefined();
});
