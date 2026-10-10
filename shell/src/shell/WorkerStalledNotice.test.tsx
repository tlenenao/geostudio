// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient } from "../api/types";
import { WorkerStalledNotice } from "./WorkerStalledNotice";

function renderWith(backlog: unknown, active = true) {
  const getJobsBacklog = vi.fn().mockResolvedValue(backlog);
  render(
    <ItemClientProvider client={{ getJobsBacklog } as unknown as ItemClient}>
      <WorkerStalledNotice active={active} />
    </ItemClientProvider>,
  );
  return getJobsBacklog;
}

test("t02-013 : une file ancienne signale un traitement indisponible", async () => {
  renderWith({ todo: 2, oldestTodoAgeSeconds: 300 });
  expect(await screen.findByRole("status")).toHaveTextContent(/traitement en arrière-plan/i);
});

test("une file récente ou vide ne dit rien", async () => {
  const probe = renderWith({ todo: 1, oldestTodoAgeSeconds: 3 });
  await waitFor(() => expect(probe).toHaveBeenCalled());
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("inactif : aucune sonde", () => {
  const probe = renderWith({ todo: 2, oldestTodoAgeSeconds: 300 }, false);
  expect(probe).not.toHaveBeenCalled();
});
