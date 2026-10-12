// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ApiKeysSection } from "./ApiKeysSection";

const KEY = {
  id: "k1",
  name: "CI",
  prefix: "gsk_0123456789ab",
  createdAt: "2026-10-11T08:00:00Z",
  expiresAt: "2027-01-01T00:00:00Z",
  revokedAt: null,
  lastUsedAt: null,
};

function renderSection() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <ApiKeysSection />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("liste les clés sans jamais montrer de secret", async () => {
  server.use(http.get("https://core.test/v1/api-keys", () => HttpResponse.json([KEY])));
  renderSection();
  expect(await screen.findByText("CI")).toBeInTheDocument();
  expect(screen.getByText("gsk_0123456789ab…")).toBeInTheDocument();
  expect(screen.getByText("Jamais utilisée")).toBeInTheDocument();
});

test("crée une clé, affiche le secret une seule fois puis le masque", async () => {
  server.use(http.get("https://core.test/v1/api-keys", () => HttpResponse.json([])));
  let body: unknown = null;
  server.use(
    http.post("https://core.test/v1/api-keys", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ ...KEY, token: "gsk_0123456789ab_SECRET" }, { status: 201 });
    }),
  );
  renderSection();
  await userEvent.type(await screen.findByLabelText("Nom de la clé"), "CI");
  await userEvent.click(screen.getByRole("button", { name: "Créer la clé" }));
  expect(await screen.findByText("gsk_0123456789ab_SECRET")).toBeInTheDocument();
  expect(body).toEqual({ name: "CI", expiresInDays: 90 });
  await userEvent.click(screen.getByRole("button", { name: "J'ai copié la clé" }));
  expect(screen.queryByText("gsk_0123456789ab_SECRET")).not.toBeInTheDocument();
});

test("refuse une durée supérieure à un an (bouton désactivé)", async () => {
  server.use(http.get("https://core.test/v1/api-keys", () => HttpResponse.json([])));
  renderSection();
  await userEvent.type(await screen.findByLabelText("Nom de la clé"), "CI");
  const days = screen.getByLabelText("Durée de validité (jours, 365 max)");
  await userEvent.clear(days);
  await userEvent.type(days, "366");
  expect(screen.getByRole("button", { name: "Créer la clé" })).toBeDisabled();
});

test("révoque après confirmation", async () => {
  server.use(http.get("https://core.test/v1/api-keys", () => HttpResponse.json([KEY])));
  let revoked = false;
  server.use(
    http.delete("https://core.test/v1/api-keys/k1", () => {
      revoked = true;
      return HttpResponse.json({ ...KEY, revokedAt: "2026-10-11T09:00:00Z" });
    }),
  );
  renderSection();
  await userEvent.click(await screen.findByRole("button", { name: "Révoquer" }));
  const dialog = await screen.findByRole("alertdialog");
  expect(dialog).toHaveTextContent("gsk_0123456789ab");
  expect(revoked).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "Révoquer", hidden: false }));
  await waitFor(() => expect(revoked).toBe(true));
});
