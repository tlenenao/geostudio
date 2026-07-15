import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { CollectionsAdminPage } from "./CollectionsAdminPage";

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <CollectionsAdminPage />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("shows an access-denied message and never calls /collections when the user is not admin", async () => {
  let collectionsCalled = false;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false }),
    ),
    http.get("https://core.test/collections", () => {
      collectionsCalled = true;
      return HttpResponse.json({ collections: [] });
    }),
  );
  render(<Harness />);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux administrateurs."),
  );
  expect(collectionsCalled).toBe(false);
});

test("lists collections and registers a new one via the dialog", async () => {
  let posted: unknown;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents", title: "Incidents", description: "", tableName: "incidents",
            isPublic: false, editable: true, geometryType: "Point", srid: 4326,
            pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
          },
        ],
      }),
    ),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [{ tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 }],
      }),
    ),
    http.post("https://core.test/collections", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json({
        id: "points_interet", title: "points_interet", description: "", tableName: "points_interet",
        isPublic: false, editable: true, geometryType: "Point", srid: 4326,
        pkColumn: "id", canWrite: true, featureCount: 0, owner: "admin",
      });
    }),
  );
  render(<Harness />);
  await screen.findByText("Incidents");
  expect(screen.getByText("admin")).toBeInTheDocument(); // owner column

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer une table" }));
  await userEvent.selectOptions(await screen.findByLabelText("Table"), "points_interet");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  // No title typed here — isPublic is still always sent (a real `false`,
  // never dropped by JSON.stringify), only the untouched title/description
  // fields drop out (empty string → undefined via `.trim() || undefined`).
  await waitFor(() => expect(posted).toEqual({ tableName: "points_interet", isPublic: false }));
});

test("edits a collection via the row action", async () => {
  let patched: unknown;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents", title: "Incidents", description: "", tableName: "incidents",
            isPublic: false, editable: true, geometryType: "Point", srid: 4326,
            pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
          },
        ],
      }),
    ),
    http.get("https://core.test/collections/candidates", () => HttpResponse.json({ candidates: [] })),
    http.patch("https://core.test/collections/incidents", async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json({
        id: "incidents", title: "Incidents (v2)", description: "", tableName: "incidents",
        isPublic: false, editable: true, geometryType: "Point", srid: 4326,
        pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
      });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
  const titleInput = await screen.findByLabelText("Titre");
  await userEvent.clear(titleInput);
  await userEvent.type(titleInput, "Incidents (v2)");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(patched).toMatchObject({ title: "Incidents (v2)" }));
});

test("deletes a collection after confirming", async () => {
  let deleteCalled = false;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents", title: "Incidents", description: "", tableName: "incidents",
            isPublic: false, editable: true, geometryType: "Point", srid: 4326,
            pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
          },
        ],
      }),
    ),
    http.get("https://core.test/collections/candidates", () => HttpResponse.json({ candidates: [] })),
    http.delete("https://core.test/collections/incidents", () => {
      deleteCalled = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Supprimer" }));
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(deleteCalled).toBe(true));
});

test("shares a collection via the row action", async () => {
  let putBody: unknown;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents", title: "Incidents", description: "", tableName: "incidents",
            isPublic: false, editable: true, geometryType: "Point", srid: 4326,
            pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
          },
        ],
      }),
    ),
    http.get("https://core.test/collections/candidates", () => HttpResponse.json({ candidates: [] })),
    http.get("https://core.test/groups", () => HttpResponse.json([{ id: "g1", name: "Équipe terrain" }])),
    http.get("https://core.test/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.put("https://core.test/collections/incidents/sharing", async ({ request }) => {
      putBody = await request.json();
      return HttpResponse.json({ public: true, groups: [] });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Partager" }));
  await userEvent.click(await screen.findByLabelText("Public"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(putBody).toEqual({ public: true, groups: [] }));
});
