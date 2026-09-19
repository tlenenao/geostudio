// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { ItemClient, PipelineRefreshPolicy } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { PipelineScheduleEditor, compileCron, parseCron } from "./PipelineScheduleEditor";

// PipelineScheduleEditor appelle usePipelineNextRun (Tâche 22) inconditionnellement
// à chaque rendu — enabled ne fait que gater l'appel réseau côté react-query,
// pas l'exigence d'un ItemClientProvider/QueryClientProvider ancêtre. Tout
// rendu de ce composant, dans ce fichier, doit donc passer par ce helper.
function renderEditor(
  value: PipelineRefreshPolicy | null,
  onChange: (next: PipelineRefreshPolicy | null) => void,
  getPipelineNextRun = vi.fn().mockResolvedValue({ nextRun: "2026-08-07T02:00:00.000Z" }),
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { getPipelineNextRun };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineScheduleEditor value={value} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { getPipelineNextRun };
}

test("parseCron recognizes the interval preset", () => {
  expect(parseCron("*/15 * * * *")).toEqual({ mode: "interval", minutes: "15" });
});

test("parseCron recognizes the daily preset", () => {
  expect(parseCron("0 2 * * *")).toEqual({ mode: "daily", time: "02:00" });
});

test("parseCron recognizes the weekly preset", () => {
  expect(parseCron("30 9 * * 1")).toEqual({ mode: "weekly", day: "1", time: "09:30" });
});

test("parseCron falls back to advanced for an unrecognized cron", () => {
  expect(parseCron("0 0 1 * *")).toEqual({ mode: "advanced", raw: "0 0 1 * *" });
});

test("compileCron round-trips each preset", () => {
  expect(compileCron({ mode: "interval", minutes: "10" })).toBe("*/10 * * * *");
  expect(compileCron({ mode: "daily", time: "02:00" })).toBe("0 2 * * *");
  expect(compileCron({ mode: "weekly", day: "1", time: "09:30" })).toBe("30 9 * * 1");
  expect(compileCron({ mode: "advanced", raw: "0 0 1 * *" })).toBe("0 0 1 * *");
});

test("toggle off by default, no fields shown when value is null", () => {
  renderEditor(null, vi.fn());
  expect(screen.getByLabelText("Planification automatique")).not.toBeChecked();
  expect(screen.queryByLabelText("Mode de planification")).not.toBeInTheDocument();
});

test("checking the toggle for the first time enables with a default cron", async () => {
  const onChange = vi.fn();
  renderEditor(null, onChange);
  await userEvent.click(screen.getByLabelText("Planification automatique"));
  expect(onChange).toHaveBeenCalledWith({ enabled: true, cron: "*/15 * * * *" });
});

test("switching to daily mode and setting a time compiles the expected cron", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "*/15 * * * *" };
  renderEditor(value, onChange);
  await userEvent.selectOptions(screen.getByLabelText("Mode de planification"), "daily");
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "0 2 * * *" });
});

test("existing daily cron opens pre-filled in daily mode", () => {
  const value: PipelineRefreshPolicy = { enabled: true, cron: "0 2 * * *" };
  renderEditor(value, vi.fn());
  expect(screen.getByLabelText("Mode de planification")).toHaveValue("daily");
  expect(screen.getByLabelText("Heure d'exécution")).toHaveValue("02:00");
});

test("an unrecognized existing cron opens in advanced mode with the raw value intact", () => {
  const value: PipelineRefreshPolicy = { enabled: true, cron: "0 0 1 * *" };
  renderEditor(value, vi.fn());
  expect(screen.getByLabelText("Mode de planification")).toHaveValue("advanced");
  expect(screen.getByLabelText("Expression cron")).toHaveValue("0 0 1 * *");
});

test("an invalid advanced cron shows an inline error", async () => {
  const value: PipelineRefreshPolicy = { enabled: true, cron: "0 0 1 * *" };
  renderEditor(value, vi.fn());
  await userEvent.clear(screen.getByLabelText("Expression cron"));
  await userEvent.type(screen.getByLabelText("Expression cron"), "not a cron");
  expect(screen.getByRole("alert")).toHaveTextContent("Format cron invalide");
});

test("switching to weekly mode compiles a default weekly cron and lists all 7 days", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "*/15 * * * *" };
  renderEditor(value, onChange);
  await userEvent.selectOptions(screen.getByLabelText("Mode de planification"), "weekly");
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "0 2 * * 1" });
  expect(screen.getByRole("option", { name: "Dimanche" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Samedi" })).toBeInTheDocument();
});

test("changing the weekly day recompiles the cron with the new day", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "30 9 * * 1" };
  renderEditor(value, onChange);
  await userEvent.selectOptions(screen.getByLabelText("Jour"), "3");
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "30 9 * * 3" });
});

test("changing the weekly execution time recompiles the cron with the new time", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "30 9 * * 1" };
  renderEditor(value, onChange);
  fireEvent.change(screen.getByLabelText("Heure d'exécution"), { target: { value: "14:45" } });
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "45 14 * * 1" });
});

test("changing the interval minutes recompiles the cron", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "*/15 * * * *" };
  renderEditor(value, onChange);
  fireEvent.change(screen.getByLabelText("Intervalle en minutes"), { target: { value: "5" } });
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "*/5 * * * *" });
});

test("switching to advanced mode keeps the current cron as the raw value", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "*/15 * * * *" };
  renderEditor(value, onChange);
  await userEvent.selectOptions(screen.getByLabelText("Mode de planification"), "advanced");
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "*/15 * * * *" });
  expect(screen.getByLabelText("Expression cron")).toHaveValue("*/15 * * * *");
});

test("shows the next scheduled run time when scheduling is enabled", async () => {
  const value: PipelineRefreshPolicy = { enabled: true, cron: "0 2 * * *" };
  const getPipelineNextRun = vi.fn().mockResolvedValue({ nextRun: "2026-08-07T02:00:00.000Z" });
  renderEditor(value, vi.fn(), getPipelineNextRun);
  await waitFor(() =>
    expect(
      screen.getByText(new Date("2026-08-07T02:00:00.000Z").toLocaleString("fr-FR"), {
        exact: false,
      }),
    ).toBeInTheDocument(),
  );
  expect(getPipelineNextRun).toHaveBeenCalledWith("0 2 * * *");
});

test("does not show the next run hint when scheduling is disabled", () => {
  renderEditor(null, vi.fn());
  expect(screen.queryByText(/Prochaine ex.cution/)).not.toBeInTheDocument();
});
