// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { GeoLimitsSection } from "./GeoLimitsSection";

const SQUARE = {
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 0],
    ],
  ],
};

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

function mockGroups() {
  server.use(
    http.get("https://core.test/v1/groups", () =>
      HttpResponse.json([{ id: "g1", name: "Équipe", title: "Équipe" }]),
    ),
  );
}

test("renders nothing without the admin privilege (403)", async () => {
  mockGroups();
  server.use(
    http.get(
      "https://core.test/v1/collections/c1/geo-limits",
      () => new HttpResponse(JSON.stringify({ detail: "forbidden" }), { status: 403 }),
    ),
  );
  const { container } = render(
    <Harness>
      <GeoLimitsSection collectionId="c1" />
    </Harness>,
  );
  await new Promise((r) => setTimeout(r, 50));
  expect(container).toBeEmptyDOMElement();
});

test("lists, saves and removes a limit", async () => {
  mockGroups();
  let put: unknown = null;
  let deleted = false;
  const row = { targetType: "group", targetId: "g1", geometry: SQUARE, updatedAt: "x" };
  server.use(
    http.get("https://core.test/v1/collections/c1/geo-limits", () =>
      HttpResponse.json({ limits: [row] }),
    ),
    http.put("https://core.test/v1/collections/c1/geo-limits/group/g1", async ({ request }) => {
      put = await request.json();
      return HttpResponse.json(row);
    }),
    http.delete("https://core.test/v1/collections/c1/geo-limits/group/g1", () => {
      deleted = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  const user = userEvent.setup();
  render(
    <Harness>
      <GeoLimitsSection collectionId="c1" />
    </Harness>,
  );
  await screen.findByRole("button", { name: /Retirer la limite de Équipe/ });
  await user.selectOptions(screen.getByLabelText("Groupe"), "g1");
  await user.click(screen.getByLabelText(/Polygone GeoJSON/));
  await user.paste(JSON.stringify(SQUARE));
  await user.click(screen.getByRole("button", { name: "Enregistrer la limite" }));
  await waitFor(() => expect(put).toEqual({ geometry: SQUARE }));
  await user.click(screen.getByRole("button", { name: /Retirer la limite de Équipe/ }));
  await waitFor(() => expect(deleted).toBe(true));
});

test("rejects an invalid JSON polygon client-side", async () => {
  mockGroups();
  server.use(
    http.get("https://core.test/v1/collections/c1/geo-limits", () =>
      HttpResponse.json({ limits: [] }),
    ),
  );
  const user = userEvent.setup();
  render(
    <Harness>
      <GeoLimitsSection collectionId="c1" />
    </Harness>,
  );
  await screen.findByText("Aucune limite définie.");
  await user.selectOptions(screen.getByLabelText("Groupe"), "g1");
  await user.click(screen.getByLabelText(/Polygone GeoJSON/));
  await user.paste("{pas du json");
  await user.click(screen.getByRole("button", { name: "Enregistrer la limite" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("JSON valide");
});
