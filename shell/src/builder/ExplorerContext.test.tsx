// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import {
  ExplorerProvider,
  useCloseExplorer,
  useExplorerEnabled,
  useExplorerTarget,
  useOpenExplorer,
} from "./ExplorerContext";

function Probe() {
  const target = useExplorerTarget();
  const enabled = useExplorerEnabled();
  const open = useOpenExplorer();
  const close = useCloseExplorer();
  return (
    <div>
      <p>enabled:{String(enabled)}</p>
      <p>target:{target ? `${target.datasetId}/${target.dataSourceId}` : "none"}</p>
      <button onClick={() => open({ datasetId: "ds1", dataSourceId: "src1" })}>open</button>
      <button onClick={() => open({ datasetId: "ds2", dataSourceId: "src2" })}>open-other</button>
      <button onClick={close}>close</button>
    </div>
  );
}

test("openExplorer is a silent no-op when the provider is disabled", async () => {
  render(
    <ExplorerProvider enabled={false}>
      <Probe />
    </ExplorerProvider>,
  );
  expect(screen.getByText("enabled:false")).toBeInTheDocument();
  await userEvent.click(screen.getByText("open"));
  expect(screen.getByText("target:none")).toBeInTheDocument();
});

test("openExplorer sets the target when enabled", async () => {
  render(
    <ExplorerProvider enabled>
      <Probe />
    </ExplorerProvider>,
  );
  expect(screen.getByText("enabled:true")).toBeInTheDocument();
  await userEvent.click(screen.getByText("open"));
  expect(screen.getByText("target:ds1/src1")).toBeInTheDocument();
});

test("opening a second target while one is open replaces it (last one wins)", async () => {
  render(
    <ExplorerProvider enabled>
      <Probe />
    </ExplorerProvider>,
  );
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(screen.getByText("open-other"));
  expect(screen.getByText("target:ds2/src2")).toBeInTheDocument();
});

test("closeExplorer clears the target", async () => {
  render(
    <ExplorerProvider enabled>
      <Probe />
    </ExplorerProvider>,
  );
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(screen.getByText("close"));
  expect(screen.getByText("target:none")).toBeInTheDocument();
});

test("hooks work with no provider mounted at all (default disabled, no-op)", async () => {
  render(<Probe />);
  expect(screen.getByText("enabled:false")).toBeInTheDocument();
  await userEvent.click(screen.getByText("open"));
  expect(screen.getByText("target:none")).toBeInTheDocument();
});
