// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { MapSymbologyEditor } from "./MapSymbologyEditor";

test("no color field selected: shows the field picker only", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={["population", "region"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("Champ couleur")).toBeInTheDocument();
  expect(screen.queryByLabelText("Méthode de classification")).not.toBeInTheDocument();
});

test("theme-primary palette option is absent without a theme", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={[]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  const select = screen.getByLabelText("Palette") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "theme-primary")).toBe(false);
});

test("theme-primary palette option is present with a theme", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={[]}
      themeColors={{ primary: "#2563eb" }}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  const select = screen.getByLabelText("Palette") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "theme-primary")).toBe(true);
});

test("classification method selector is hidden in categorical mode and shown in numeric mode", async () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "region",
          mode: "categorical",
          palette: "categorical-a",
          domain: { kind: "categorical", values: [] },
          computedAt: "",
        },
      }}
      availableFields={["region"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );
  expect(screen.queryByLabelText("Méthode de classification")).not.toBeInTheDocument();

  rerender(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          palette: "sequential-blue",
          domain: { kind: "numeric", min: 0, max: 1 },
          computedAt: "",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );
  expect(screen.getByLabelText("Méthode de classification")).toBeInTheDocument();
});

test("class count selector is hidden when the method is continuous", () => {
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          palette: "sequential-blue",
          domain: { kind: "numeric", min: 0, max: 1 },
          computedAt: "",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.queryByLabelText("Nombre de classes")).not.toBeInTheDocument();
});

test("recompute button calls runStatistics and writes domain + computedAt via onChange", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]);
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          palette: "sequential-blue",
          domain: { kind: "numeric", min: 0, max: 0 },
          computedAt: "",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));

  expect(runStatistics).toHaveBeenCalled();
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({
      color: expect.objectContaining({
        domain: { kind: "numeric", min: 0, max: 100 },
        computedAt: expect.any(String),
      }),
    }),
  );
});

test("recompute button for the size field calls runStatistics and writes size domain", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 1, max: 9 } }]);
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      value={{ size: { field: "montant", domain: { min: 0, max: 0 }, computedAt: "" } }}
      availableFields={["montant"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Recalculer la taille" }));

  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({
      size: expect.objectContaining({ domain: { min: 1, max: 9 }, computedAt: expect.any(String) }),
    }),
  );
});

test("a failing recompute surfaces an error instead of hanging silently", async () => {
  const runStatistics = vi.fn().mockRejectedValue(new Error("boom"));
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          palette: "sequential-blue",
          domain: { kind: "numeric", min: 0, max: 0 },
          computedAt: "",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
});

// I2 de la revue finale SP-25 : un id de datalist global cassait
// l'autocomplete dès qu'une 2e couche stylée était montée sur la même
// carte — le navigateur résolvait toujours `list=` contre la 1re instance.
test("two MapSymbologyEditor instances render distinct datalist ids", () => {
  render(
    <>
      <MapSymbologyEditor
        value={undefined}
        availableFields={["a"]}
        themeColors={undefined}
        runStatistics={vi.fn()}
        sampleField={vi.fn()}
        onChange={vi.fn()}
      />
      <MapSymbologyEditor
        value={undefined}
        availableFields={["b"]}
        themeColors={undefined}
        runStatistics={vi.fn()}
        sampleField={vi.fn()}
        onChange={vi.fn()}
      />
    </>,
  );
  const inputs = screen.getAllByLabelText("Champ couleur") as HTMLInputElement[];
  expect(inputs).toHaveLength(2);
  const listIds = inputs.map((i) => i.getAttribute("list"));
  expect(listIds[0]).not.toBe(listIds[1]);
  expect(document.getElementById(listIds[0]!)).not.toBeNull();
  expect(document.getElementById(listIds[1]!)).not.toBeNull();
});

// I3 de la revue finale SP-25 : recomputeSize n'avait aucun catch —
// contrairement à recomputeColor, un échec y devenait une rejection non
// gérée, sans aucun signal visible.
test("a failing size recompute surfaces an error instead of an unhandled rejection", async () => {
  const runStatistics = vi.fn().mockRejectedValue(new Error("boom-size"));
  render(
    <MapSymbologyEditor
      value={{ size: { field: "montant", domain: { min: 0, max: 0 }, computedAt: "" } }}
      availableFields={["montant"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Recalculer la taille" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("boom-size");
});

// C1 de la revue finale SP-25 : un champ configuré mais jamais recalculé
// (computedAt === "") doit être visiblement signalé, pas silencieusement
// enregistré tel quel.
test("shows a hint when a configured color field has never been computed", () => {
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "categorical",
          palette: "categorical-a",
          domain: { kind: "categorical", values: [] },
          computedAt: "",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByText(/Classes non calculées/)).toBeInTheDocument();
});

test("shows a hint when a configured size field has never been computed", () => {
  render(
    <MapSymbologyEditor
      value={{ size: { field: "montant", domain: { min: 0, max: 0 }, computedAt: "" } }}
      availableFields={["montant"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByText(/Taille non calculée/)).toBeInTheDocument();
});

// C1 de la revue finale SP-25 : il n'existait avant ce fix aucun chemin
// appelant onChange avec `color`/`size` retiré — un auteur ne pouvait pas
// revenir en arrière une fois un champ choisi.
test("clearing the color encoding removes only color, keeping size, via onChange", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "categorical",
          palette: "categorical-a",
          domain: { kind: "categorical", values: [] },
          computedAt: "",
        },
        size: { field: "montant", domain: { min: 0, max: 10 }, computedAt: "2026-08-23T00:00:00Z" },
      }}
      availableFields={["pop", "montant"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer la couleur" }));
  expect(onChange).toHaveBeenCalledWith({
    size: { field: "montant", domain: { min: 0, max: 10 }, computedAt: "2026-08-23T00:00:00Z" },
  });
});

test("clearing the only active encoding calls onChange with undefined", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "categorical",
          palette: "categorical-a",
          domain: { kind: "categorical", values: [] },
          computedAt: "",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer la couleur" }));
  expect(onChange).toHaveBeenCalledWith(undefined);
});

// I5 de la revue finale SP-25 : Jenks ne peut pas fonctionner sur un hôte
// sans collectionId résolu (mapWidget.tsx) — l'option ne doit pas être
// offerte, même précédent que "theme-primary".
test("Jenks option is present by default and hidden when jenksAvailable is false", () => {
  const numericValue = {
    color: {
      field: "pop",
      mode: "numeric" as const,
      palette: "sequential-blue" as const,
      domain: { kind: "numeric" as const, min: 0, max: 1 },
      computedAt: "",
    },
  };
  const { rerender } = render(
    <MapSymbologyEditor
      value={numericValue}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  const select = screen.getByLabelText("Méthode de classification") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "jenks")).toBe(true);

  rerender(
    <MapSymbologyEditor
      value={numericValue}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      jenksAvailable={false}
      onChange={vi.fn()}
    />,
  );
  const select2 = screen.getByLabelText("Méthode de classification") as HTMLSelectElement;
  expect(Array.from(select2.options).some((o) => o.value === "jenks")).toBe(false);
});

test("computed breaks are shown as text", () => {
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          classification: { method: "quantile", classes: 2 },
          palette: "sequential-blue",
          domain: { kind: "numeric-classed", breaks: [0, 50, 100] },
          computedAt: "2026-08-23T10:00:00Z",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByText(/0.*50.*100/)).toBeInTheDocument();
});

const baseProps = {
  availableFields: ["population", "region"],
  themeColors: undefined,
  runStatistics: vi.fn(),
  sampleField: vi.fn(),
};

test("l'opacité écrit une valeur fixe 0-100", () => {
  const onChange = vi.fn();
  render(<MapSymbologyEditor {...baseProps} value={undefined} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Opacité"), { target: { value: "60" } });
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ opacity: 60 }));
});

test("« Ajouter un contour » crée un contour fixe par défaut", async () => {
  const onChange = vi.fn();
  render(<MapSymbologyEditor {...baseProps} value={undefined} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter un contour" }));
  expect(onChange).toHaveBeenLastCalledWith({
    stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
  });
});

test("changer la couleur, l'épaisseur et le style du contour écrit stroke", () => {
  const onChange = vi.fn();
  const value = {
    stroke: { color: { fixed: "#000000" as const }, width: { fixed: 1 }, style: "solid" as const },
  };
  render(<MapSymbologyEditor {...baseProps} value={value} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Couleur de contour"), {
    target: { value: "#123456" },
  });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ stroke: expect.objectContaining({ color: { fixed: "#123456" } }) }),
  );
  fireEvent.change(screen.getByLabelText("Épaisseur de contour (px)"), { target: { value: "3" } });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ stroke: expect.objectContaining({ width: { fixed: 3 } }) }),
  );
  fireEvent.change(screen.getByLabelText("Style de contour"), { target: { value: "dashed" } });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ stroke: expect.objectContaining({ style: "dashed" }) }),
  );
});

test("« Retirer le contour » n'efface que le contour", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        opacity: 80,
        stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer le contour" }));
  expect(onChange).toHaveBeenLastCalledWith({ opacity: 80 });
});

// C1 de la revue finale SP-25, réintroduit par SP-27 : clearColor/clearSize
// ne regardaient que l'AUTRE des deux encodages historiques.
test("retirer la couleur préserve tous les autres encodages", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        color: {
          field: "region",
          mode: "categorical",
          palette: "categorical-a",
          domain: { kind: "categorical", values: ["A"] },
          computedAt: "2026-08-27T00:00:00Z",
        },
        opacity: 70,
        stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer la couleur" }));
  expect(onChange).toHaveBeenLastCalledWith({
    opacity: 70,
    stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
  });
});

test("retirer le dernier encodage repasse la symbologie à undefined", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer le contour" }));
  expect(onChange).toHaveBeenLastCalledWith(undefined);
});

test("basculer le contour en data-driven écrit un champ, une palette et un domaine vide", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Couleur de contour par attribut" }));
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      stroke: expect.objectContaining({
        color: {
          field: "",
          mode: "categorical",
          palette: "categorical-a",
          domain: { kind: "categorical", values: [] },
          computedAt: "",
        },
      }),
    }),
  );
});

test("les libellés du contour ne collident pas avec ceux de la couleur", () => {
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        color: {
          field: "region",
          mode: "categorical",
          palette: "categorical-a",
          domain: { kind: "categorical", values: ["A"] },
          computedAt: "2026-08-27T00:00:00Z",
        },
        stroke: {
          color: {
            field: "pop",
            mode: "numeric",
            palette: "sequential-blue",
            domain: { kind: "numeric", min: 0, max: 1 },
            computedAt: "",
          },
          width: { fixed: 1 },
          style: "solid",
        },
      }}
      onChange={vi.fn()}
    />,
  );
  // Les deux pickers coexistent : chaque nom accessible reste unique.
  expect(screen.getByLabelText("Champ couleur")).toBeInTheDocument();
  expect(screen.getByLabelText("Champ du contour")).toBeInTheDocument();
  expect(screen.getByLabelText("Palette")).toBeInTheDocument();
  expect(screen.getByLabelText("Couleurs du contour")).toBeInTheDocument();
  expect(screen.getByLabelText("Type de valeurs du contour")).toBeInTheDocument();
  expect(screen.getByLabelText("Méthode de répartition du contour")).toBeInTheDocument();
  // Un SEUL <datalist> pour les deux pickers et le champ taille : rendre
  // l'élément dans le picker dupliquerait son id DOM (constat I4).
  expect(document.querySelectorAll("datalist")).toHaveLength(1);

  // Constat A de la revue finale Task 5 (SP-27) : `getByLabelText` de Testing
  // Library matche EXACT, ce qui laissait passer des libellés de contour
  // sur-chaînes stricts de ceux de la couleur (« Champ couleur de contour »
  // ⊃ « Champ couleur ») — invisible ici, mais une violation de mode strict
  // pour `getByLabel`/`getByRole({ name })` de Playwright, qui matchent en
  // sous-chaîne insensible à la casse par défaut. On vérifie donc la relation
  // mécaniquement, dans les deux sens, plutôt que par lecture visuelle des
  // libellés.
  const colorLabels = [
    "Champ couleur",
    "Palette",
    "Type de couleur",
    "Méthode de classification",
    "Nombre de classes",
    "Recalculer les classes",
  ];
  const strokeLabels = [
    "Champ du contour",
    "Couleurs du contour",
    "Type de valeurs du contour",
    "Méthode de répartition du contour",
    "Nombre de tranches du contour",
    "Recalculer le contour",
  ];
  for (const c of colorLabels) {
    for (const s of strokeLabels) {
      const cLower = c.toLowerCase();
      const sLower = s.toLowerCase();
      expect(sLower.includes(cLower)).toBe(false);
      expect(cLower.includes(sLower)).toBe(false);
    }
  }
});

// `computeColorDomain` en mode catégoriel fait `rows.map((r) => String(r.id))` :
// le mock doit avoir la forme réelle d'un `DataRecord` (`{ id, properties }`),
// pas `{ region: … }` — sinon le domaine vaudrait `["undefined", …]`.
test("« Recalculer le contour » fige le domaine et l'horodatage", async () => {
  const onChange = vi.fn();
  const runStatistics = vi.fn().mockResolvedValue([
    { id: "Nord", properties: {} },
    { id: "Sud", properties: {} },
  ]);
  render(
    <MapSymbologyEditor
      {...baseProps}
      runStatistics={runStatistics}
      value={{
        stroke: {
          color: {
            field: "region",
            mode: "categorical",
            palette: "categorical-a",
            domain: { kind: "categorical", values: [] },
            computedAt: "",
          },
          width: { fixed: 1 },
          style: "solid",
        },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Recalculer le contour" }));
  await vi.waitFor(() => {
    const last = onChange.mock.calls.at(-1)![0];
    expect(last.stroke.color.domain).toEqual({ kind: "categorical", values: ["Nord", "Sud"] });
    // Invariant SP-25 : le domaine est FIGÉ, avec la date de son calcul.
    expect(last.stroke.color.computedAt).not.toBe("");
  });
});

test("un recalcul de contour en échec affiche une erreur au lieu d'une rejection", async () => {
  const runStatistics = vi.fn().mockRejectedValue(new Error("champ inconnu"));
  render(
    <MapSymbologyEditor
      {...baseProps}
      runStatistics={runStatistics}
      value={{
        stroke: {
          color: {
            field: "region",
            mode: "categorical",
            palette: "categorical-a",
            domain: { kind: "categorical", values: [] },
            computedAt: "",
          },
          width: { fixed: 1 },
          style: "solid",
        },
      }}
      onChange={vi.fn()}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Recalculer le contour" }));
  await vi.waitFor(() =>
    expect(screen.getAllByRole("alert").some((n) => n.textContent?.includes("champ inconnu"))).toBe(
      true,
    ),
  );
});

test("revenir à une couleur de contour fixe efface le champ et le domaine", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        stroke: {
          color: {
            field: "region",
            mode: "categorical",
            palette: "categorical-a",
            domain: { kind: "categorical", values: ["A"] },
            computedAt: "2026-08-27T00:00:00Z",
          },
          width: { fixed: 1 },
          style: "solid",
        },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Couleur de contour fixe" }));
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      stroke: expect.objectContaining({ color: { fixed: "#000000" } }),
    }),
  );
});

// Cohérence avec Task 4 : « plus rien ne reste » vaut aussi pour un contour
// CLASSÉ, pas seulement pour un contour fixe. `clearEncoding` reste générique.
test("retirer un contour classé, seul encodage actif, rend undefined", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        stroke: {
          color: {
            field: "region",
            mode: "categorical",
            palette: "categorical-a",
            domain: { kind: "categorical", values: ["A"] },
            computedAt: "2026-08-27T00:00:00Z",
          },
          width: { fixed: 2 },
          style: "dashed",
        },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer le contour" }));
  expect(onChange).toHaveBeenLastCalledWith(undefined);
});

// Important de la revue finale Task 5, SP-27 : les deux boutons de mode du
// contour étaient inconditionnels — un reclic sur le mode déjà actif
// écrasait une couleur fixe choisie par l'utilisateur, ou un champ/palette/
// domaine déjà calculés, par la valeur par défaut.
test("recliquer « Couleur de contour fixe » alors qu'elle est déjà active est un no-op", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        stroke: { color: { fixed: "#ff0000" }, width: { fixed: 1 }, style: "solid" },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Couleur de contour fixe" }));
  expect(onChange).not.toHaveBeenCalled();
});

test("recliquer « Couleur de contour par attribut » alors qu'elle est déjà active est un no-op", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        stroke: {
          color: {
            field: "region",
            mode: "categorical",
            palette: "categorical-a",
            domain: { kind: "categorical", values: ["A"] },
            computedAt: "2026-08-27T00:00:00Z",
          },
          width: { fixed: 1 },
          style: "solid",
        },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Couleur de contour par attribut" }));
  expect(onChange).not.toHaveBeenCalled();
});

// Constat 4 de la revue finale Task 5 : seul recomputeStrokeDomain était
// couvert côté hôte. Une inversion de cible dans setStrokeColorPatch
// (écrire dans value.color au lieu de value.stroke.color) sur un changement
// de palette du contour serait passée inaperçue.
test("changer la palette du contour écrit stroke.color.palette, jamais color.palette", () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        stroke: {
          color: {
            field: "region",
            mode: "categorical",
            palette: "categorical-a",
            domain: { kind: "categorical", values: ["A"] },
            computedAt: "2026-08-27T00:00:00Z",
          },
          width: { fixed: 1 },
          style: "solid",
        },
      }}
      onChange={onChange}
    />,
  );
  fireEvent.change(screen.getByLabelText("Couleurs du contour"), {
    target: { value: "sequential-warm" },
  });
  const call = onChange.mock.calls.at(-1)![0];
  expect(call.stroke.color.palette).toBe("sequential-warm");
  expect(call.color).toBeUndefined();
});

const iconValue = {
  icon: {
    field: "categorie",
    domain: { kind: "categorical" as const, values: ["ecole", "commerce"] },
    mapping: {},
  },
};

test("« Ajouter des icônes » ouvre le bloc, qui est fermé par défaut", async () => {
  render(<MapSymbologyEditor {...baseProps} value={undefined} onChange={vi.fn()} />);
  expect(screen.queryByLabelText("Champ icône")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Ajouter des icônes" }));
  expect(screen.getByLabelText("Champ icône")).toBeInTheDocument();
});

test("la grille d'icônes n'apparaît que pour la valeur en cours d'édition", async () => {
  render(<MapSymbologyEditor {...baseProps} value={iconValue} onChange={vi.fn()} />);
  // Aucune grille au départ : seulement un bouton par valeur du domaine.
  expect(screen.queryByRole("img", { name: "school" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Choisir l'icône de ecole" }));
  // Une seule grille, donc un seul bouton nommé "school".
  expect(screen.getByRole("img", { name: "school" })).toBeInTheDocument();
});

test("choisir une icône Lucide écrit icon.mapping pour cette valeur", async () => {
  const onChange = vi.fn();
  render(<MapSymbologyEditor {...baseProps} value={iconValue} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Choisir l'icône de commerce" }));
  await userEvent.click(screen.getByRole("img", { name: "shopping-cart" }));
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      icon: expect.objectContaining({
        mapping: { commerce: { source: "lucide", name: "shopping-cart" } },
      }),
    }),
  );
});

// Constat 11 du rapport cœur (Important) : le mock de la version précédente
// était `[{ categorie: "ecole" }, { categorie: "commerce" }]`. FAUX, et
// mesuré : `computeColorDomain` en mode catégoriel fait
// `rows.map((r) => String(r.id))` (`mapSymbology.ts:194-197`) — il lit `r.id`,
// jamais `r.categorie`, donc le domaine valait `["undefined","undefined"]` et
// l'assertion échouait. La forme réelle est `DataRecord` = `{ id, properties }`
// (`types.ts:593-597`). Le garde-fou de la version précédente (« read the
// file's existing categorical-color test and copy its mock verbatim »)
// renvoyait dans le vide : `MapSymbologyEditor.test.tsx` ne contient que DEUX
// `mockResolvedValue`, tous deux numériques (lignes 118 et 153) — il n'existe
// aucun test catégoriel dont copier un mock.
test("« Recalculer les valeurs » remplit le domaine depuis runStatistics", async () => {
  const onChange = vi.fn();
  const runStatistics = vi.fn().mockResolvedValue([
    { id: "ecole", properties: {} },
    { id: "commerce", properties: {} },
  ]);
  render(
    <MapSymbologyEditor
      {...baseProps}
      runStatistics={runStatistics}
      value={undefined}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Ajouter des icônes" }));
  await userEvent.type(screen.getByLabelText("Champ icône"), "categorie");
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les valeurs" }));
  expect(runStatistics).toHaveBeenCalled();
  await vi.waitFor(() =>
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        icon: expect.objectContaining({
          field: "categorie",
          domain: { kind: "categorical", values: ["ecole", "commerce"] },
        }),
      }),
    ),
  );
});

test("l'effet de chargement des icônes personnalisées ne boucle pas", async () => {
  const listCustomIcons = vi.fn().mockResolvedValue([]);
  const { rerender } = render(
    <MapSymbologyEditor
      {...baseProps}
      value={undefined}
      onChange={vi.fn()}
      listCustomIcons={listCustomIcons}
    />,
  );
  // Une nouvelle identité de callback à chaque rendu, comme un `() =>
  // client.listMapIcons()` inline chez l'hôte : l'effet ne doit PAS repartir.
  rerender(
    <MapSymbologyEditor
      {...baseProps}
      value={undefined}
      onChange={vi.fn()}
      listCustomIcons={vi.fn().mockResolvedValue([])}
    />,
  );
  rerender(
    <MapSymbologyEditor
      {...baseProps}
      value={undefined}
      onChange={vi.fn()}
      listCustomIcons={vi.fn().mockResolvedValue([])}
    />,
  );
  await vi.waitFor(() => expect(listCustomIcons).toHaveBeenCalledTimes(1));
});

test("« Retirer les icônes » n'efface que l'encodage icône", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor {...baseProps} value={{ ...iconValue, opacity: 60 }} onChange={onChange} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer les icônes" }));
  expect(onChange).toHaveBeenLastCalledWith({ opacity: 60 });
});
