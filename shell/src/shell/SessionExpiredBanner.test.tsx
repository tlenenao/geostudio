// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/ApiError";
import { SessionExpiredBanner } from "./SessionExpiredBanner";

const signIn = vi.fn();
vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ signIn }) }));

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <SessionExpiredBanner />
    </QueryClientProvider>,
  );
  return qc;
}

test("t02-008 : un 401 invite à se reconnecter, un succès ultérieur lève l'invite", async () => {
  const qc = setup();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await act(async () => {
    await qc
      .fetchQuery({ queryKey: ["a"], queryFn: () => Promise.reject(new ApiError(401)) })
      .catch(() => {});
  });
  expect(await screen.findByRole("alert")).toHaveTextContent(/session a expiré/i);
  await userEvent.click(screen.getByRole("button", { name: "Se reconnecter" }));
  expect(signIn).toHaveBeenCalledTimes(1);
  await act(async () => {
    await qc.fetchQuery({ queryKey: ["b"], queryFn: () => Promise.resolve(1) });
  });
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
});

test("une erreur non 401 n'affiche rien", async () => {
  const qc = setup();
  await act(async () => {
    await qc
      .fetchQuery({ queryKey: ["c"], queryFn: () => Promise.reject(new ApiError(500)) })
      .catch(() => {});
  });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
