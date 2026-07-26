// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { ExplorerMenu } from "./ExplorerMenu";
import { ExplorerProvider, useExplorerTarget } from "../ExplorerContext";

function TargetProbe() {
  const target = useExplorerTarget();
  return <p>target:{target ? `${target.datasetId}/${target.dataSourceId}` : "none"}</p>;
}

test("renders nothing when the explorer is disabled", () => {
  render(
    <ExplorerProvider enabled={false}>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();
});

test("renders nothing when there is no datasetId", () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId={undefined} dataSourceId="src1" />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();
});

test("clicking the button then the menu item opens the explorer with the right target", async () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
      <TargetProbe />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Voir les entités")).not.toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Voir les entités"));
  expect(screen.getByText("target:ds1/src1")).toBeInTheDocument();
});

test("the menu closes again after selecting the item", async () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
    </ExplorerProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Voir les entités"));
  expect(screen.queryByLabelText("Voir les entités")).not.toBeInTheDocument();
});
