// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { createItemClient } from "../../api/itemClient";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { StatusBar } from "./StatusBar";

function renderBar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <StatusBar />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("affiche la version et le tenant depuis /me", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "",
        lastName: "",
        isAdmin: false,
        isAnalyst: false,
        hasAnyEditorRole: false,
        version: "0.1.0",
        tenantSlug: "correze",
      }),
    ),
  );
  renderBar();
  expect(await screen.findByText("v0.1.0 · correze")).toBeInTheDocument();
});
