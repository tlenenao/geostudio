// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PrintLayoutPanel } from "./PrintLayoutPanel";

describe("PrintLayoutPanel", () => {
  it("renders defaults when value is null", () => {
    render(<PrintLayoutPanel value={null} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Format")).toHaveValue("a4");
    expect(screen.getByLabelText("Orientation")).toHaveValue("portrait");
  });

  it("calls onChange with an updated title, preserving other fields", () => {
    // fireEvent.change (une seule valeur complète), pas userEvent.type
    // (frappe caractère par caractère) : le composant est entièrement
    // contrôlé et `onChange` ici est un mock qui ne réinjecte jamais la
    // nouvelle valeur dans `value` — avec userEvent.type, React réafficherait
    // `value=""` entre chaque frappe (le prop ne change jamais), et seul le
    // DERNIER caractère tapé survivrait dans le dernier appel à onChange.
    const onChange = vi.fn();
    render(<PrintLayoutPanel value={{ pageSize: "a3", orientation: "landscape", showLegend: false }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Titre"), { target: { value: "Rapport" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: "a3", orientation: "landscape", showLegend: false, title: "Rapport" }));
  });

  it("toggles showLegend", async () => {
    const onChange = vi.fn();
    render(<PrintLayoutPanel value={{ showLegend: true }} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText("Légende"));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ showLegend: false }));
  });

  it("changing page size to a3 landscape calls onChange with both fields", async () => {
    const onChange = vi.fn();
    render(<PrintLayoutPanel value={null} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText("Format"), "a3");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: "a3" }));
  });
});
