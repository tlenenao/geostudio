// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { GroupClaimMappingsSection } from "./GroupClaimMappingsSection";

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <GroupClaimMappingsSection />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("liste, ajoute et retire un mapping claim vers groupe", async () => {
  let mappings = [{ id: "m1", groupId: "g1", claimValue: "SIG" }];
  let posted: unknown = null;
  server.use(
    http.get("https://core.test/v1/groups", () =>
      HttpResponse.json([{ id: "g1", name: "Équipe SIG", createdBy: "u", canManage: true }]),
    ),
    http.get("https://core.test/v1/groups/claim-mappings", () => HttpResponse.json(mappings)),
    http.post("https://core.test/v1/groups/claim-mappings", async ({ request }) => {
      posted = await request.json();
      mappings = [...mappings, { id: "m2", groupId: "g1", claimValue: "RH" }];
      return HttpResponse.json(mappings[1], { status: 201 });
    }),
    http.delete("https://core.test/v1/groups/claim-mappings/m1", () => {
      mappings = mappings.filter((m) => m.id !== "m1");
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(<Harness />);
  expect(await screen.findByText("SIG")).toBeInTheDocument();

  await userEvent.type(screen.getByLabelText("Valeur du claim"), "RH");
  await userEvent.selectOptions(await screen.findByLabelText("Groupe"), "g1");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le mapping" }));
  await waitFor(() => expect(posted).toEqual({ groupId: "g1", claimValue: "RH" }));
  expect(await screen.findByText("RH")).toBeInTheDocument();

  await userEvent.click(
    screen.getByRole("button", { name: "Retirer le mapping SIG vers Équipe SIG" }),
  );
  await waitFor(() => expect(screen.queryByText("SIG")).not.toBeInTheDocument());
});

test("un échec d'enregistrement affiche une alerte", async () => {
  server.use(
    http.get("https://core.test/v1/groups", () =>
      HttpResponse.json([{ id: "g1", name: "G", createdBy: "u", canManage: true }]),
    ),
    http.get("https://core.test/v1/groups/claim-mappings", () => HttpResponse.json([])),
    http.post(
      "https://core.test/v1/groups/claim-mappings",
      () => new HttpResponse(null, { status: 409 }),
    ),
  );
  render(<Harness />);
  await screen.findByText(/Aucun mapping/);
  await userEvent.type(screen.getByLabelText("Valeur du claim"), "X");
  await userEvent.selectOptions(await screen.findByLabelText("Groupe"), "g1");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le mapping" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Échec de l'enregistrement");
});
