import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRoutes } from "./routes";

function wrap(children: ReactNode, initial = "/") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "t",
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("navigates from catalog to item detail on open", async () => {
  wrap(<AppRoutes />);
  await userEvent.click((await screen.findAllByRole("button", { name: /ouvrir/i }))[0]);
  expect(await screen.findByRole("heading", { name: /item 1/i })).toBeInTheDocument();
});
