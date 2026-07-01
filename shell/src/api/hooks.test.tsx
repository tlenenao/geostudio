import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { createItemClient } from "./itemClient";
import { ItemClientProvider } from "./ItemClientProvider";
import { useCreateItem, useDeleteItem, useGroups, useItems, useMe, useSharing, useUpdateItem } from "./hooks";

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "test-token",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("useItems returns the mapped page", async () => {
  const { result } = renderHook(() => useItems({}), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.total).toBe(2);
});

test("useMe returns the current user", async () => {
  const { result } = renderHook(() => useMe(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.username).toBe("alice");
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
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "t",
  });
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
  queryClient.setQueryData(["items", {}], {
    items: [
      { pk: "1", resourceType: "app", title: "A", abstract: "", owner: "x", thumbnailUrl: null, date: "", configId: null },
      { pk: "2", resourceType: "app", title: "B", abstract: "", owner: "x", thumbnailUrl: null, date: "", configId: null },
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
