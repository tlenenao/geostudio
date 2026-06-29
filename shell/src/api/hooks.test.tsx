import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { createItemClient } from "./itemClient";
import { ItemClientProvider } from "./ItemClientProvider";
import { useItems, useMe } from "./hooks";

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
