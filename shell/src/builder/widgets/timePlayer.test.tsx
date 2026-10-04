// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import type { WidgetContext } from "../registry";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { registerTimePlayerWidget, windowAt } from "./timePlayer";
import { expectTokenizedClasses } from "../../ui/kit/testUtils";

beforeEach(() => {
  _resetRegistry();
  registerTimePlayerWidget();
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

function TimeRangeProbe() {
  const ctx = useAnalyticsContext();
  return <p>timeRange:{ctx.timeRange ? `${ctx.timeRange.from}..${ctx.timeRange.to}` : "none"}</p>;
}

const PROPS = {
  from: "2026-06-01",
  to: "2026-06-03",
  stepDays: 1,
  windowDays: 1,
  intervalMs: 1000,
};

function renderPlayer(props: Record<string, unknown> = PROPS) {
  const TimePlayer = getWidget("timePlayer")!.Component;
  return render(
    <AnalyticsContextProvider interactions="auto">
      <TimePlayer props={props} ctx={{ mode: "runtime" } as WidgetContext} />
      <TimeRangeProbe />
    </AnalyticsContextProvider>,
  );
}

test("windowAt : fenêtre glissante UTC, bornée par la fin, null au-delà", () => {
  expect(windowAt("2026-06-01", "2026-06-10", 1, 7, 0)).toEqual({
    from: "2026-06-01",
    to: "2026-06-07",
  });
  expect(windowAt("2026-06-01", "2026-06-10", 1, 7, 5)).toEqual({
    from: "2026-06-06",
    to: "2026-06-10",
  });
  expect(windowAt("2026-06-01", "2026-06-10", 3, 1, 3)).toEqual({
    from: "2026-06-10",
    to: "2026-06-10",
  });
  expect(windowAt("2026-06-01", "2026-06-10", 1, 7, 10)).toBeNull();
  expect(windowAt("pas une date", "2026-06-10", 1, 7, 0)).toBeNull();
});

test("Lecture pousse la 1re fenêtre tout de suite, avance à chaque intervalle et s'arrête à la fin", () => {
  renderPlayer();
  fireEvent.click(screen.getByRole("button", { name: "Lecture" }));
  expect(screen.getByText("timeRange:2026-06-01..2026-06-01")).toBeInTheDocument();
  act(() => {
    vi.advanceTimersByTime(1000);
  });
  expect(screen.getByText("timeRange:2026-06-02..2026-06-02")).toBeInTheDocument();
  act(() => {
    vi.advanceTimersByTime(1000);
  });
  expect(screen.getByText("timeRange:2026-06-03..2026-06-03")).toBeInTheDocument();
  act(() => {
    vi.advanceTimersByTime(1000);
  });
  // Fin dépassée : arrêt, dernière fenêtre conservée, prêt à rejouer.
  expect(screen.getByRole("button", { name: "Lecture" })).toBeInTheDocument();
  expect(screen.getByText("timeRange:2026-06-03..2026-06-03")).toBeInTheDocument();
  expect(vi.getTimerCount()).toBe(0);
});

test("Pause fige la fenêtre ; la vitesse ×2 divise l'intervalle", () => {
  renderPlayer();
  fireEvent.change(screen.getByLabelText("Vitesse"), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "Lecture" }));
  act(() => {
    vi.advanceTimersByTime(500);
  });
  expect(screen.getByText("timeRange:2026-06-02..2026-06-02")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Pause" }));
  act(() => {
    vi.advanceTimersByTime(5000);
  });
  expect(screen.getByText("timeRange:2026-06-02..2026-06-02")).toBeInTheDocument();
});

test("le minuteur est nettoyé au démontage", () => {
  const { unmount } = renderPlayer();
  fireEvent.click(screen.getByRole("button", { name: "Lecture" }));
  expect(vi.getTimerCount()).toBe(1);
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});

test("sans début ni fin : message de configuration, pas de bouton Lecture", () => {
  renderPlayer({ stepDays: 1, windowDays: 7, intervalMs: 1000 });
  expect(
    screen.getByText("Lecteur temporel non configuré : renseignez le début et la fin."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Lecture" })).not.toBeInTheDocument();
});

test("PropsPanel : champs bornés, sans couleur brute, vide = prop retirée", () => {
  const Panel = getWidget("timePlayer")!.PropsPanel;
  const onChange = vi.fn();
  const { container } = render(<Panel props={{ ...PROPS }} dataSources={[]} onChange={onChange} />);
  expect(screen.getByLabelText("Pas (jours)")).toHaveAttribute("min", "1");
  expect(screen.getByLabelText("Intervalle (ms)")).toHaveAttribute("min", "500");
  fireEvent.change(screen.getByLabelText("Fenêtre (jours)"), { target: { value: "" } });
  expect(onChange.mock.calls.at(-1)![0].windowDays).toBeUndefined();
  fireEvent.change(screen.getByLabelText("Début de l'animation"), {
    target: { value: "2026-05-01" },
  });
  expect(onChange.mock.calls.at(-1)![0].from).toBe("2026-05-01");
  expectTokenizedClasses(container);
});
