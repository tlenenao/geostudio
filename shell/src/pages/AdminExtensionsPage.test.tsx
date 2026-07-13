import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AdminExtensionsPage } from "./AdminExtensionsPage";

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <AdminExtensionsPage />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("shows an access-denied message and never calls /extensions when the user is not admin", async () => {
  let extensionsCalled = false;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false }),
    ),
    http.get("https://core.test/extensions", () => {
      extensionsCalled = true;
      return HttpResponse.json({ extensions: [] });
    }),
  );
  render(<Harness />);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux administrateurs."),
  );
  expect(extensionsCalled).toBe(false);
});

test("lists extensions (including disabled) and toggles enabled via PATCH", async () => {
  let patchedBody: unknown;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
    http.get("https://core.test/extensions", ({ request }) => {
      expect(new URL(request.url).searchParams.get("all")).toBe("true");
      return HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js", props: [], events: [], actions: [],
            defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" }, enabled: false,
          },
        ],
      });
    }),
    http.patch("https://core.test/extensions/acme.gauge", async ({ request }) => {
      patchedBody = await request.json();
      return HttpResponse.json({ id: "acme.gauge", enabled: true });
    }),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  expect(toggle).not.toBeChecked();
  await userEvent.click(toggle);
  await waitFor(() => expect(patchedBody).toEqual({ enabled: true }));
});
