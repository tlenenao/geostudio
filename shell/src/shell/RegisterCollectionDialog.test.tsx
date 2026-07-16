// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { RegisterCollectionDialog } from "./RegisterCollectionDialog";

function Harness({ open = true, onClose = () => {} }: { open?: boolean; onClose?: () => void }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <RegisterCollectionDialog open={open} onClose={onClose} />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("shows an empty-state message when there are no candidate tables", async () => {
  server.use(
    http.get("https://core.test/collections/candidates", () => HttpResponse.json({ candidates: [] })),
  );
  render(<Harness />);
  await waitFor(() =>
    expect(screen.getByText(/Aucune table à enregistrer/)).toBeInTheDocument(),
  );
});

test("disables a non-registrable candidate and shows its reason", async () => {
  server.use(
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          { tableName: "widgets", registrable: false, reason: "table has no primary key" },
          { tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 },
        ],
      }),
    ),
  );
  render(<Harness />);
  // findByLabelText itself polls until the <select> mounts, which only
  // happens once candidatesQuery.data is populated with both options — by
  // the time this resolves, both <option> elements are already rendered.
  await screen.findByLabelText("Table");
  const widgetsOption = screen.getByRole("option", { name: /widgets.*table has no primary key/ });
  expect(widgetsOption).toBeDisabled();
  const poiOption = screen.getByRole("option", { name: "points_interet" });
  expect(poiOption).not.toBeDisabled();
});

test("submits the chosen table and closes on success", async () => {
  let body: unknown;
  server.use(
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [{ tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 }],
      }),
    ),
    http.post("https://core.test/collections", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "points_interet", title: "Points d'intérêt", description: "", tableName: "points_interet",
        isPublic: false, editable: true, geometryType: "Point", srid: 4326,
        pkColumn: "id", canWrite: true, featureCount: 0, owner: "admin",
      });
    }),
  );
  const onClose = vi.fn();
  render(<Harness onClose={onClose} />);
  await userEvent.selectOptions(await screen.findByLabelText("Table"), "points_interet");
  await userEvent.type(screen.getByLabelText("Titre"), "Points d'intérêt");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  // isPublic is always sent (a real `false`, not `undefined`, so
  // JSON.stringify keeps the key) — only title/description drop out when
  // left blank, since `"".trim() || undefined` turns an empty string into
  // an actually-undefined value.
  expect(body).toEqual({ tableName: "points_interet", title: "Points d'intérêt", isPublic: false });
});

test("disables the submit button when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [{ tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 }],
      }),
    ),
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  await userEvent.selectOptions(await screen.findByLabelText("Table"), "points_interet");
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});
