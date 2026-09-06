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

test("crée un nouveau groupe depuis le formulaire de partage", async () => {
  let created = false;
  server.use(
    http.post("https://core.test/groups", async ({ request }) => {
      const body = (await request.json()) as { name: string };
      expect(body.name).toBe("Nouveau");
      created = true;
      return HttpResponse.json({ id: "g2", name: "Nouveau" }, { status: 201 });
    }),
    // Réponse dynamique : reflète la création côté serveur pour que le
    // refetch déclenché par onSuccess (invalidateQueries) voie le nouveau
    // groupe — même patron que toute mutation suivie d'un refetch dans ce
    // dépôt (ex. useCreateCollection).
    http.get("https://core.test/groups", () =>
      HttpResponse.json(
        created
          ? [
              { id: "10", name: "Équipe A" },
              { id: "11", name: "Équipe B" },
              { id: "g2", name: "Nouveau" },
            ]
          : [
              { id: "10", name: "Équipe A" },
              { id: "11", name: "Équipe B" },
            ],
      ),
    ),
  );
  const onDone = vi.fn();
  render(
    <Harness>
      <ShareForm item={item} onDone={onDone} />
    </Harness>,
  );
  await screen.findByRole("checkbox", { name: "Groupe Équipe B" });
  await userEvent.type(screen.getByLabelText("Nom du nouveau groupe"), "Nouveau");
  await userEvent.click(screen.getByRole("button", { name: "Créer le groupe" }));
  await waitFor(() =>
    expect(screen.getByRole("checkbox", { name: "Groupe Nouveau" })).toBeInTheDocument(),
  );
});

test("ajoute un membre à un groupe existant, affiche l'erreur si non-créateur", async () => {
  server.use(
    http.post("https://core.test/groups/10/members", () =>
      HttpResponse.json({ detail: "group or user not found" }, { status: 404 }),
    ),
  );
  render(
    <Harness>
      <ShareForm item={item} onDone={vi.fn()} />
    </Harness>,
  );
  await screen.findByRole("checkbox", { name: "Groupe Équipe A" });
  await userEvent.type(screen.getByLabelText("Identifiant utilisateur (Équipe A)"), "u2");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter un membre (Équipe A)" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/créateur/i);
});

test("crée un lien de partage à échéance", async () => {
  server.use(
    http.get("https://core.test/items/7/share-links", () => HttpResponse.json([])),
    http.post("https://core.test/items/7/share-links", async ({ request }) => {
      const body = (await request.json()) as { ttlDays: number };
      expect(body.ttlDays).toBe(14);
      return HttpResponse.json(
        { url: "https://core.test/share-links/eyJ...", expiresAt: "2026-10-05T00:00:00" },
        { status: 201 },
      );
    }),
  );
  render(
    <Harness>
      <ShareForm item={item} onDone={vi.fn()} />
    </Harness>,
  );
  await screen.findByRole("checkbox", { name: "Groupe Équipe B" });
  await userEvent.clear(screen.getByLabelText("Durée du lien (jours)"));
  await userEvent.type(screen.getByLabelText("Durée du lien (jours)"), "14");
  await userEvent.click(screen.getByRole("button", { name: "Créer un lien" }));
  await waitFor(() => expect(screen.getByText(/eyJ\.\.\./)).toBeInTheDocument());
});

test("liste les liens de partage existants et permet de les révoquer", async () => {
  let revoked = false;
  server.use(
    http.get("https://core.test/items/7/share-links", () =>
      HttpResponse.json(
        revoked
          ? [{ id: "sl1", expiresAt: "2026-10-05T00:00:00", revoked: true }]
          : [{ id: "sl1", expiresAt: "2026-10-05T00:00:00", revoked: false }],
      ),
    ),
    http.delete("https://core.test/items/7/share-links/sl1", () => {
      revoked = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(
    <Harness>
      <ShareForm item={item} onDone={vi.fn()} />
    </Harness>,
  );
  await screen.findByRole("button", { name: "Révoquer" });
  await userEvent.click(screen.getByRole("button", { name: "Révoquer" }));
  await waitFor(() => expect(screen.getByText(/révoqué/i)).toBeInTheDocument());
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
