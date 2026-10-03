// SPDX-License-Identifier: Apache-2.0
import {
  QueryClient,
  QueryClientProvider,
  QueryObserver,
  onlineManager,
} from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { ConnectivityBanner, CONNECTIVITY_POLL_MS } from "./ConnectivityBanner";
import { CoreUnreachableError } from "../api/CoreUnreachableError";

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <ConnectivityBanner />
    </QueryClientProvider>,
  );
  return { queryClient, ...utils };
}

const fail = (qc: QueryClient, key: string) =>
  qc
    .fetchQuery({ queryKey: [key], queryFn: () => Promise.reject(new CoreUnreachableError()) })
    .catch(() => {});

afterEach(() => {
  vi.useRealTimers();
  onlineManager.setOnline(true);
});

test("affiche une bannière quand le cœur est injoignable, la masque quand la requête échouée réussit", async () => {
  const { queryClient } = setup();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();

  await fail(queryClient, "probe");
  await waitFor(() => {
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Connexion au serveur perdue — nouvelle tentative en cours…",
    );
  });

  await queryClient.fetchQuery({ queryKey: ["probe"], queryFn: () => Promise.resolve("ok") });
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
});

test("t02-012 : le succès d'une AUTRE requête ne lève pas la bannière", async () => {
  const { queryClient } = setup();
  await fail(queryClient, "list");
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

  await queryClient.fetchQuery({ queryKey: ["notifs"], queryFn: () => Promise.resolve("ok") });
  expect(screen.getByRole("alert")).toBeInTheDocument();

  await queryClient.fetchQuery({ queryKey: ["list"], queryFn: () => Promise.resolve("ok") });
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
});

test("t02-006 : un sondage relance les requêtes en échec et lève la bannière au retour du cœur", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const { queryClient } = setup();
  let up = false;
  const queryFn = () => (up ? Promise.resolve("ok") : Promise.reject(new CoreUnreachableError()));
  // Requête « active » (observée) comme dans une page réelle.
  const obs = new QueryObserver(queryClient, { queryKey: ["list"], queryFn, retry: false });
  const unsub = obs.subscribe(() => {});
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

  up = true;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(CONNECTIVITY_POLL_MS + 50);
  });
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  unsub();
});

test("le sondage est arrêté au démontage (aucun timer résiduel)", async () => {
  const { queryClient, unmount } = setup();
  await fail(queryClient, "list");
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  vi.useFakeTimers();
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});

test("t02-007 : hors ligne, une bannière dédiée est affichée", async () => {
  setup();
  act(() => onlineManager.setOnline(false));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/hors ligne/));
  act(() => onlineManager.setOnline(true));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
});
