// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { FieldClassificationPicker, formatDomain } from "./FieldClassificationPicker";

const labels = {
  field: "Champ test",
  palette: "Palette test",
  mode: "Type test",
  method: "Méthode test",
  classes: "Classes test",
  recompute: "Recalculer test",
};

function renderPicker(over: Partial<Parameters<typeof FieldClassificationPicker>[0]> = {}) {
  const props = {
    labels,
    listId: "l1",
    themeColors: undefined,
    jenksAvailable: true,
    busy: false,
    error: null as string | null,
    value: undefined,
    onChange: vi.fn(),
    onRecompute: vi.fn(),
    ...over,
  };
  render(<FieldClassificationPicker {...props} />);
  return props;
}

test("sans champ choisi, seuls le champ et la palette sont rendus", () => {
  renderPicker();
  expect(screen.getByLabelText("Champ test")).toBeInTheDocument();
  expect(screen.getByLabelText("Palette test")).toBeInTheDocument();
  expect(screen.queryByLabelText("Type test")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Méthode test")).not.toBeInTheDocument();
});

// Le picker ne construit jamais l'encodage lui-même : il émet un patch et
// laisse l'hôte matérialiser les valeurs par défaut, exactement comme le
// faisait `setColorField` avant l'extraction.
test("le champ et la palette émettent un patch même sans encodage existant", () => {
  const { onChange } = renderPicker();
  fireEvent.change(screen.getByLabelText("Champ test"), { target: { value: "population" } });
  expect(onChange).toHaveBeenLastCalledWith({ field: "population" });
  fireEvent.change(screen.getByLabelText("Palette test"), {
    target: { value: "sequential-warm" },
  });
  expect(onChange).toHaveBeenLastCalledWith({ palette: "sequential-warm" });
});

// L'ÉLÉMENT <datalist> appartient à l'hôte (un seul par éditeur, partagé par
// les deux pickers et par le champ « taille ») : le picker ne fait que le
// référencer. Cf. constat I4 du brief de Task 5.
test("le champ référence le datalist de l'hôte sans le rendre lui-même", () => {
  renderPicker();
  expect(screen.getByLabelText("Champ test")).toHaveAttribute("list", "l1-fields");
  expect(document.querySelector("datalist")).toBeNull();
});

test("le sélecteur de méthode n'apparaît qu'en mode numérique", () => {
  const { onChange } = renderPicker({
    value: {
      field: "population",
      mode: "categorical",
      palette: "categorical-a",
      domain: { kind: "categorical", values: [] },
      computedAt: "",
    },
  });
  expect(screen.queryByLabelText("Méthode test")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Type test"), { target: { value: "numeric" } });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ mode: "numeric", classification: undefined }),
  );
});

test("le nombre de classes est borné à 2-9", () => {
  const { onChange } = renderPicker({
    value: {
      field: "population",
      mode: "numeric",
      palette: "sequential-blue",
      classification: { method: "quantile", classes: 5 },
      domain: { kind: "numeric-classed", breaks: [0, 1, 2] },
      computedAt: "",
    },
  });
  fireEvent.change(screen.getByLabelText("Classes test"), { target: { value: "42" } });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ classification: { method: "quantile", classes: 9 } }),
  );
  fireEvent.change(screen.getByLabelText("Classes test"), { target: { value: "1" } });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ classification: { method: "quantile", classes: 2 } }),
  );
});

test("l'option theme-primary suit la présence d'un thème", () => {
  renderPicker({ themeColors: { primary: "#123456" } });
  const select = screen.getByLabelText("Palette test") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "theme-primary")).toBe(true);
});

test("l'option Jenks disparaît quand jenksAvailable est faux", () => {
  renderPicker({
    jenksAvailable: false,
    value: {
      field: "population",
      mode: "numeric",
      palette: "sequential-blue",
      domain: { kind: "numeric", min: 0, max: 1 },
      computedAt: "",
    },
  });
  const select = screen.getByLabelText("Méthode test") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "jenks")).toBe(false);
});

// Constat I6 : la version précédente de ce test ne cliquait RIEN et
// assertionnait `not.toHaveBeenCalled()`, vrai par construction — il serait
// resté vert si `onRecompute` n'avait jamais été câblé au bouton. Deux
// rendus, deux propriétés distinctes, chacune réellement falsifiable.
test("le bouton de recalcul délègue à onRecompute", async () => {
  const { onRecompute } = renderPicker({
    value: {
      field: "population",
      mode: "numeric",
      palette: "sequential-blue",
      domain: { kind: "numeric", min: 0, max: 1 },
      computedAt: "",
    },
  });
  await userEvent.click(screen.getByRole("button", { name: "Recalculer test" }));
  expect(onRecompute).toHaveBeenCalledTimes(1);
});

test("le bouton de recalcul est désactivé pendant le calcul", () => {
  renderPicker({
    busy: true,
    value: {
      field: "population",
      mode: "numeric",
      palette: "sequential-blue",
      domain: { kind: "numeric", min: 0, max: 1 },
      computedAt: "",
    },
  });
  expect(screen.getByRole("button", { name: /Recalculer test|Calcul/ })).toBeDisabled();
});

test("une erreur est affichée en role=alert", () => {
  renderPicker({
    error: "champ inconnu",
    value: {
      field: "population",
      mode: "numeric",
      palette: "sequential-blue",
      domain: { kind: "numeric", min: 0, max: 1 },
      computedAt: "",
    },
  });
  expect(screen.getByRole("alert")).toHaveTextContent("champ inconnu");
});

// Constat I7 : la version précédente n'exerçait que la première moitié de son
// titre, finissait par un `userEvent.click` sans assertion, et déclarait une
// liaison inutilisée `const { onChange: _ }`. Deux rendus, les deux moitiés.
test("un domaine jamais calculé affiche l'avertissement", () => {
  renderPicker({
    value: {
      field: "population",
      mode: "categorical",
      palette: "categorical-a",
      domain: { kind: "categorical", values: ["A", "B"] },
      computedAt: "",
    },
  });
  expect(screen.getByText(/non calculées/)).toBeInTheDocument();
  expect(screen.queryByText(/Classes calculées le/)).not.toBeInTheDocument();
});

test("un domaine calculé affiche son résumé au lieu de l'avertissement", () => {
  renderPicker({
    value: {
      field: "population",
      mode: "categorical",
      palette: "categorical-a",
      domain: { kind: "categorical", values: ["A", "B"] },
      computedAt: "2026-08-27T10:00:00Z",
    },
  });
  expect(screen.queryByText(/non calculées/)).not.toBeInTheDocument();
  // `formatDomain` d'un domaine catégoriel rend la liste des valeurs jointe
  // par ", " ; on n'asserte pas la phrase entière, elle contient un
  // `toLocaleString()` dépendant du fuseau.
  expect(screen.getByText(/Classes calculées le/)).toBeInTheDocument();
  expect(screen.getByText(/A, B/)).toBeInTheDocument();
});

// L'avertissement nomme le bouton réellement rendu : pour l'usage couleur la
// chaîne est identique au caractère près à celle d'avant l'extraction, pour
// l'usage contour elle désigne « … du contour » plutôt qu'un bouton absent.
test("l'avertissement nomme le bouton de recalcul injecté", () => {
  renderPicker({
    value: {
      field: "population",
      mode: "categorical",
      palette: "categorical-a",
      domain: { kind: "categorical", values: ["A"] },
      computedAt: "",
    },
  });
  expect(
    screen.getByText("Classes non calculées — cliquez sur « Recalculer test »."),
  ).toBeInTheDocument();
});

test("formatDomain rend chaque forme de domaine", () => {
  expect(formatDomain({ kind: "categorical", values: ["A", "B"] })).toBe("A, B");
  expect(formatDomain({ kind: "numeric-classed", breaks: [0, 50, 100] })).toBe(
    "0.0 – 50.0 – 100.0",
  );
  expect(formatDomain({ kind: "numeric", min: 1, max: 9 })).toBe("1 – 9");
});
