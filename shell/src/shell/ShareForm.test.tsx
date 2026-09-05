// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
import type { ReactNode } from "react";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { Item } from "../api/types";
import { ShareForm } from "./ShareForm";
import { OWNER_PERMISSIONS } from "../auth/permissions";

const item: Item = {
  pk: "7",
  resourceType: "app",
  title: "Mon app",
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

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "t",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("saves the sharing payload for a checked group", async () => {
  let body: any = null;
  server.use(
    http.put("https://core.test/items/:pk/sharing", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 204 });
    }),
  );
  const onDone = vi.fn();
  render(
    <Harness>
      <ShareForm item={item} onDone={onDone} />
    </Harness>,
  );
  await userEvent.click(await screen.findByRole("checkbox", { name: "Groupe Équipe B" }));
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  await waitFor(() => expect(onDone).toHaveBeenCalled());
  expect(body).toEqual({
    public: true,
    groups: expect.arrayContaining([
      { groupId: "10", role: "editor" },
      { groupId: "11", role: "viewer" },
    ]),
  });
});

test("shows an alert and does not call onDone when saving fails", async () => {
  server.use(
    http.put("https://core.test/items/:pk/sharing", () => new HttpResponse(null, { status: 500 })),
  );
  const onDone = vi.fn();
  render(
    <Harness>
      <ShareForm item={item} onDone={onDone} />
    </Harness>,
  );
  await userEvent.click(await screen.findByRole("button", { name: /enregistrer/i }));
  expect(await screen.findByText(/échec du partage/i)).toBeInTheDocument();
  expect(onDone).not.toHaveBeenCalled();
});

test("annuler appelle onDone sans enregistrer", async () => {
  const onDone = vi.fn();
  render(
    <Harness>
      <ShareForm item={item} onDone={onDone} />
    </Harness>,
  );
  await screen.findByRole("checkbox", { name: "Groupe Équipe B" });
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  expect(onDone).toHaveBeenCalled();
});
