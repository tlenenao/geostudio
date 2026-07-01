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
import { ShareDialog } from "./ShareDialog";

const item: Item = {
  pk: "7",
  resourceType: "app",
  title: "Mon app",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "",
  configId: null,
};

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
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
    http.put("https://geonode.test/api/v2/resources/:pk/permissions", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 200 });
    }),
  );
  const onClose = vi.fn();
  render(
    <Harness>
      <ShareDialog item={item} open onClose={onClose} />
    </Harness>,
  );
  await userEvent.click(await screen.findByRole("checkbox", { name: "Groupe Équipe B" }));
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  expect(body.groups).toEqual(
    expect.arrayContaining([
      { id: "anonymous", permissions: "view" },
      { id: "10", permissions: "edit" },
      { id: "11", permissions: "view" },
    ]),
  );
});

test("keeps the dialog open and shows an alert when saving fails", async () => {
  server.use(
    http.put("https://geonode.test/api/v2/resources/:pk/permissions", () =>
      new HttpResponse(null, { status: 500 }),
    ),
  );
  const onClose = vi.fn();
  render(
    <Harness>
      <ShareDialog item={item} open onClose={onClose} />
    </Harness>,
  );
  await userEvent.click(await screen.findByRole("button", { name: /enregistrer/i }));
  expect(await screen.findByText(/échec du partage/i)).toBeInTheDocument();
  expect(onClose).not.toHaveBeenCalled();
});
