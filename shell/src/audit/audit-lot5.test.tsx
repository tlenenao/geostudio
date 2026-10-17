// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ComplianceAdminPage } from "../pages/ComplianceAdminPage";
import { ShareForm } from "../shell/ShareForm";
import { OWNER_PERMISSIONS } from "../auth/permissions";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ItemClientProvider client={client}>{ui}</ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function stubMM() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: false, addEventListener() {}, removeEventListener() {} }),
  );
}

// Anonymisation RGPD : un clic ne doit pas suffire (ComplianceAdminPage.tsx:57).
it("REV-360 : erase user demande une confirmation avant l'appel", async () => {
  stubMM();
  server.use(
    http.get("https://core.test/v1/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "me",
        firstName: "M",
        lastName: "M",
        email: "m@e.x",
        tenantId: "t1",
        tenantSlug: "demo",
        role: { id: "r", name: "X", slug: "x" },
        privileges: ["admin.users.manage", "compliance.manage"],
        version: "0.1.0",
      }),
    ),
  );
  let called = false;
  server.use(
    http.all("https://core.test/v1/compliance/users/*", () => {
      called = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  wrap(<ComplianceAdminPage />);
  const [input, confirm] = await screen.findAllByRole("textbox");
  await userEvent.type(input, "u42");
  await userEvent.type(confirm, "u42-name"); // AUD-094 : nom d'utilisateur de confirmation
  await userEvent.click(screen.getByRole("button", { name: /anonymiser ce compte/i }));
  await new Promise((r) => setTimeout(r, 100));
  expect(called).toBe(false);
  // la confirmation (dialogue d'alerte) déclenche bien l'appel
  const dialog = await screen.findByRole("alertdialog");
  await userEvent.click(within(dialog).getByRole("button", { name: /anonymiser ce compte/i }));
  await vi.waitFor(() => expect(called).toBe(true));
});

// Révocation de lien : doit afficher une erreur sur 500 (ShareForm.tsx:105).
it("REV-361 : revoke link affiche une erreur sur échec 500", async () => {
  const item: any = {
    pk: "7",
    resourceType: "app",
    title: "A",
    abstract: "",
    owner: "alice",
    thumbnailUrl: null,
    date: "",
    configId: null,
    isPublished: false,
    permissions: OWNER_PERMISSIONS,
    license: "",
    language: "fr",
  };
  server.use(
    http.get("https://core.test/v1/items/7/share-links", () =>
      HttpResponse.json([
        {
          id: "l1",
          token: "tok",
          revoked: false,
          expiresAt: new Date(Date.now() + 1e9).toISOString(),
          createdAt: new Date().toISOString(),
          scope: "view",
        },
      ]),
    ),
    http.delete(
      "https://core.test/v1/items/7/share-links/l1",
      () => new HttpResponse(null, { status: 500 }),
    ),
    http.post(
      "https://core.test/v1/items/7/share-links/l1/revoke",
      () => new HttpResponse(null, { status: 500 }),
    ),
  );
  wrap(<ShareForm item={item} onDone={() => {}} />);
  const btns = await screen.findAllByRole("button", { name: /révoquer/i });
  await userEvent.click(btns[0]);
  // Une confirmation éventuelle est acceptée, puis on attend un message d'erreur.
  const confirm = screen.queryAllByRole("button", { name: /confirmer|révoquer/i }).pop();
  if (confirm && confirm !== btns[0]) await userEvent.click(confirm);
  expect(await screen.findByRole("alert", {}, { timeout: 800 })).toBeTruthy();
});
