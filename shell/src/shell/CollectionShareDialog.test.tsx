// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { CollectionShareDialog } from "./CollectionShareDialog";

function Harness({ onClose = () => {} }: { onClose?: () => void }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <CollectionShareDialog collectionId="incidents" open={true} onClose={onClose} />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("pre-fills sharing state and PUTs the chosen roles on submit", async () => {
  let body: unknown;
  server.use(
    http.get("https://core.test/groups", () =>
      HttpResponse.json([{ id: "g1", name: "Équipe terrain" }]),
    ),
    http.get("https://core.test/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.put("https://core.test/collections/incidents/sharing", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ public: false, groups: [{ groupId: "g1", role: "editor" }] });
    }),
  );
  const onClose = vi.fn();
  render(<Harness onClose={onClose} />);
  await userEvent.click(await screen.findByLabelText("Groupe Équipe terrain"));
  await userEvent.selectOptions(screen.getByLabelText("Rôle Équipe terrain"), "editor");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  expect(body).toEqual({ public: false, groups: [{ groupId: "g1", role: "editor" }] });
});

test("disables the submit button when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/groups", () =>
      HttpResponse.json([{ id: "g1", name: "Équipe terrain" }]),
    ),
    http.get("https://core.test/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});
