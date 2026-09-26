// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { ConnectivityBanner } from "./ConnectivityBanner";
import { CoreUnreachableError } from "../api/CoreUnreachableError";

test("affiche une bannière quand le cœur est injoignable, la masque au succès suivant", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ConnectivityBanner />
    </QueryClientProvider>,
  );

  expect(screen.queryByRole("alert")).not.toBeInTheDocument();

  await queryClient
    .fetchQuery({
      queryKey: ["connectivity-probe-fail"],
      queryFn: () => Promise.reject(new CoreUnreachableError()),
    })
    .catch(() => {});

  await waitFor(() => {
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Connexion au serveur perdue — nouvelle tentative en cours…",
    );
  });

  await queryClient.fetchQuery({
    queryKey: ["connectivity-probe-ok"],
    queryFn: () => Promise.resolve("ok"),
  });

  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
});
