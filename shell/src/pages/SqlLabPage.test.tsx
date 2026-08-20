// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { SqlLabPage } from "./SqlLabPage";

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <SqlLabPage />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

function mockMe(isAnalyst: boolean) {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        isAdmin: false,
        isAnalyst,
      }),
    ),
  );
}

beforeEach(() => localStorage.clear());

test("shows an access-denied message for a non-analyst user", async () => {
  mockMe(false);
  render(<Harness />);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux analystes."),
  );
});

test("executes a query and renders the result table", async () => {
  mockMe(true);
  let posted: unknown;
  server.use(
    http.post("https://core.test/analytics/sql", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json({
        columns: ["nom", "surface"],
        rows: [
          ["Parc A", 12],
          ["Parc B", 30],
        ],
        truncated: false,
      });
    }),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select nom, surface from parcs");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByRole("columnheader", { name: "nom" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "Parc A" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "30" })).toBeInTheDocument();
  await waitFor(() => expect(posted).toEqual({ sql: "select nom, surface from parcs" }));
});

test("shows the truncation notice when the result was capped", async () => {
  mockMe(true);
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json({ columns: ["id"], rows: [["1"]], truncated: true }),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select id from x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByText("Résultat tronqué aux 1 premières lignes.")).toBeInTheDocument();
});

test("shows the server error message and keeps the SQL text on failure", async () => {
  mockMe(true);
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json(
        {
          detail: {
            errors: [{ field: "sql", code: "sql_error", message: "Parser Error: syntax error" }],
          },
        },
        { status: 400 },
      ),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select * fro x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Parser Error: syntax error");
  expect(textarea).toHaveValue("select * fro x");
});

test("records history on success and reloads a past query when clicked", async () => {
  mockMe(true);
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json({ columns: ["id"], rows: [["1"]], truncated: false }),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select id from x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  await screen.findByRole("columnheader", { name: "id" });
  await userEvent.clear(textarea);
  const historyButton = await screen.findByRole("button", {
    name: "Recharger la requête : select id from x",
  });
  await userEvent.click(historyButton);
  expect(textarea).toHaveValue("select id from x");
});
