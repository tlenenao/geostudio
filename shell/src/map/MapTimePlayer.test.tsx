// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { MapTimePlayerConfig } from "../api/types";
import { MapTimePlayer } from "./MapTimePlayer";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

const VALUE: MapTimePlayerConfig = {
  start: "2026-06-01",
  end: "2026-06-03",
  stepDays: 1,
  windowDays: 1,
  intervalMs: 1000,
  windowIndex: 1,
};

test("sans configuration : deux dates créent l'état du lecteur, aucune plage poussée", () => {
  const onChange = vi.fn();
  const onRange = vi.fn();
  render(<MapTimePlayer value={null} onChange={onChange} onRange={onRange} />);
  expect(onRange).toHaveBeenLastCalledWith(null);
  fireEvent.change(screen.getByLabelText("Début de l'animation"), {
    target: { value: "2026-06-01" },
  });
  expect(onChange).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Fin de l'animation"), {
    target: { value: "2026-06-03" },
  });
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({ start: "2026-06-01", end: "2026-06-03", windowIndex: 0 }),
  );
});

test("configuré : pousse la fenêtre persistée, la lecture avance, la pause persiste l'index", () => {
  const onChange = vi.fn();
  const onRange = vi.fn();
  render(<MapTimePlayer value={VALUE} onChange={onChange} onRange={onRange} />);
  expect(onRange).toHaveBeenLastCalledWith({ from: "2026-06-02", to: "2026-06-02" });
  fireEvent.click(screen.getByRole("button", { name: "Lecture" }));
  act(() => {
    vi.advanceTimersByTime(1000);
  });
  expect(onRange).toHaveBeenLastCalledWith({ from: "2026-06-03", to: "2026-06-03" });
  fireEvent.click(screen.getByRole("button", { name: "Pause" }));
  expect(onChange).toHaveBeenLastCalledWith({ ...VALUE, windowIndex: 2 });
});

test("Retirer le lecteur : état null et filtre levé", () => {
  const onChange = vi.fn();
  const onRange = vi.fn();
  render(<MapTimePlayer value={VALUE} onChange={onChange} onRange={onRange} />);
  fireEvent.click(screen.getByRole("button", { name: "Retirer le lecteur temps" }));
  expect(onChange).toHaveBeenCalledWith(null);
});
