// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { CollectionAdmin } from "../api/types";
import { EditCollectionDialog } from "./EditCollectionDialog";

const COLLECTION: CollectionAdmin = {
  id: "incidents",
  title: "Incidents",
  description: "Signalements",
  tableName: "incidents",
  isPublic: false,
  editable: true,
  geometryType: "Point",
  srid: 4326,
  pkColumn: "id",
  canWrite: true,
  featureCount: 3,
  owner: "admin",
};

function Harness({ onClose = () => {} }: { onClose?: () => void }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <EditCollectionDialog collection={COLLECTION} open={true} onClose={onClose} />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("pre-fills the form from the collection and PATCHes the edited fields on submit", async () => {
  let body: unknown;
  server.use(
    http.patch("https://core.test/collections/incidents", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ ...COLLECTION, title: "Incidents (v2)", isPublic: true });
    }),
  );
  const onClose = vi.fn();
  render(<Harness onClose={onClose} />);
  const titleInput = screen.getByLabelText("Titre") as HTMLInputElement;
  expect(titleInput.value).toBe("Incidents");
  await userEvent.clear(titleInput);
  await userEvent.type(titleInput, "Incidents (v2)");
  await userEvent.click(screen.getByLabelText("Public"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  expect(body).toEqual({
    title: "Incidents (v2)",
    description: "Signalements",
    isPublic: true,
    editable: true,
  });
});

test("surfaces an alert when the PATCH fails", async () => {
  server.use(
    http.patch("https://core.test/collections/incidents", () =>
      HttpResponse.json({}, { status: 500 }),
    ),
  );
  render(<Harness />);
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Échec de la mise à jour."),
  );
});

test("disables the submit button when the instance is in read-only demo mode", async () => {
  server.use(http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })));
  render(<Harness />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});
