// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { PipelineRefreshPolicy } from "../../api/types";
import { PipelineScheduleEditor, compileCron, parseCron } from "./PipelineScheduleEditor";

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
  render(<PipelineScheduleEditor value={null} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Planification automatique")).not.toBeChecked();
  expect(screen.queryByLabelText("Mode de planification")).not.toBeInTheDocument();
});

test("checking the toggle for the first time enables with a default cron", async () => {
  const onChange = vi.fn();
  render(<PipelineScheduleEditor value={null} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("Planification automatique"));
  expect(onChange).toHaveBeenCalledWith({ enabled: true, cron: "*/15 * * * *" });
});

test("switching to daily mode and setting a time compiles the expected cron", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "*/15 * * * *" };
  render(<PipelineScheduleEditor value={value} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Mode de planification"), "daily");
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "0 2 * * *" });
});

test("existing daily cron opens pre-filled in daily mode", () => {
  const value: PipelineRefreshPolicy = { enabled: true, cron: "0 2 * * *" };
  render(<PipelineScheduleEditor value={value} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Mode de planification")).toHaveValue("daily");
  expect(screen.getByLabelText("Heure d'exécution")).toHaveValue("02:00");
});

test("an unrecognized existing cron opens in advanced mode with the raw value intact", () => {
  const value: PipelineRefreshPolicy = { enabled: true, cron: "0 0 1 * *" };
  render(<PipelineScheduleEditor value={value} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Mode de planification")).toHaveValue("advanced");
  expect(screen.getByLabelText("Expression cron")).toHaveValue("0 0 1 * *");
});

test("an invalid advanced cron shows an inline error", async () => {
  const value: PipelineRefreshPolicy = { enabled: true, cron: "0 0 1 * *" };
  render(<PipelineScheduleEditor value={value} onChange={vi.fn()} />);
  await userEvent.clear(screen.getByLabelText("Expression cron"));
  await userEvent.type(screen.getByLabelText("Expression cron"), "not a cron");
  expect(screen.getByRole("alert")).toHaveTextContent("Format cron invalide");
});
