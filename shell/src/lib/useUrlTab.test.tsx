// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { useUrlTab } from "./useUrlTab";

function Probe() {
  const { activeTabId, onActiveTabChange } = useUrlTab("canvas");
  const { search } = useLocation();
  return (
    <>
      <p data-testid="tab">{activeTabId}</p>
      <p data-testid="search">{search}</p>
      <button onClick={() => onActiveTabChange("props")}>go</button>
    </>
  );
}

test("l'onglet par défaut est celui fourni, le changement s'écrit dans l'URL", async () => {
  render(
    <MemoryRouter>
      <Probe />
    </MemoryRouter>,
  );
  expect(screen.getByTestId("tab")).toHaveTextContent("canvas");
  await userEvent.click(screen.getByText("go"));
  expect(screen.getByTestId("tab")).toHaveTextContent("props");
  expect(screen.getByTestId("search")).toHaveTextContent("?tab=props");
});

test("l'onglet est restauré depuis l'URL", () => {
  render(
    <MemoryRouter initialEntries={["/?tab=props"]}>
      <Probe />
    </MemoryRouter>,
  );
  expect(screen.getByTestId("tab")).toHaveTextContent("props");
});
