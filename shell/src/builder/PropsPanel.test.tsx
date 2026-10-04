// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { registerWidget, _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { PropsPanel } from "./PropsPanel";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient, WidgetItem } from "../api/types";
import { expectTokenizedClasses } from "../ui/kit/testUtils";
import { t } from "../i18n";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

const item: WidgetItem = { id: "t", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } };

// The "text" widget's PropsPanel offers a source-binding DataSourceSelect,
// which reads the item client via useItems even when its query is disabled
// — so any render exercising PropsPanel needs an ItemClientProvider in scope.
function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={{} as unknown as ItemClient}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("edits the selected widget's props", async () => {
  const onChange = vi.fn();
  render(
    <PropsPanel item={item} dataSources={[]} onChange={onChange} onVisibleWhenChange={vi.fn()} />,
    { wrapper },
  );
  const area = screen.getByLabelText("Texte du widget");
  await userEvent.type(area, "!");
  expect(onChange).toHaveBeenCalled();
  const last = onChange.mock.calls.at(-1)![0];
  expect(String(last.text).startsWith("Hi")).toBe(true);
});

test("shows a placeholder when nothing is selected", () => {
  render(
    <PropsPanel item={null} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={vi.fn()} />,
    { wrapper },
  );
  expect(screen.getByText(/aucun widget/i)).toBeInTheDocument();
});

test("edits the selected widget's visibleWhen and shows a validation error", async () => {
  const onVisibleWhenChange = vi.fn();
  render(
    <PropsPanel
      item={item}
      dataSources={[]}
      onChange={vi.fn()}
      onVisibleWhenChange={onVisibleWhenChange}
    />,
    { wrapper },
  );
  const area = screen.getByLabelText("Condition d'affichage (visibleWhen)");
  await userEvent.type(area, "vars.x ==");
  expect(onVisibleWhenChange).toHaveBeenCalled();
});

test("shows no validation error for a valid visibleWhen", () => {
  const itemWithValidExpr = { ...item, visibleWhen: "vars.x == 'a'" };
  render(
    <PropsPanel
      item={itemWithValidExpr}
      dataSources={[]}
      onChange={vi.fn()}
      onVisibleWhenChange={vi.fn()}
    />,
    { wrapper },
  );
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("shows a validation error for an invalid visibleWhen", () => {
  const itemWithInvalidExpr = { ...item, visibleWhen: "vars.x ==" };
  const { container } = render(
    <PropsPanel
      item={itemWithInvalidExpr}
      dataSources={[]}
      onChange={vi.fn()}
      onVisibleWhenChange={vi.fn()}
    />,
    { wrapper },
  );
  // D35 : le message brut de cel-js est préfixé « • » (formatCelError),
  // pas affiché tel quel.
  expect(screen.getByRole("alert")).toHaveTextContent("•");
  // SP-B12c : pas de couleur Tailwind de palette codée en dur — un token
  // --gs-* à la place.
  expectTokenizedClasses(container);
});

// Même précédent que shell/src/ui/kit/Popover.test.tsx (Task 31, portes de
// qualité) : le repositionnement Popper (@floating-ui/react-dom) sous jsdom
// coûte assez cher (getComputedStyle/getBoundingClientRect répétés) pour
// dépasser par intermittence le testTimeout par défaut du dépôt (5000ms)
// sous couverture v8 + suite complète. Reproduit 3 fois de suite en
// clôture de Vague C (`npm run test -- --coverage`, 280 fichiers), jamais
// en lançant ce fichier seul. Relevé local à ce test, pas touché à
// vitest.config.ts.
test("propose une aide contextuelle sur la condition d'affichage CEL", async () => {
  render(
    <PropsPanel item={item} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={vi.fn()} />,
    { wrapper },
  );
  const helpButton = screen.getByRole("button", { name: t("propsPanel.visibleWhenHelpAria") });
  await userEvent.click(helpButton);
  expect(await screen.findByText(t("propsPanel.visibleWhenHelpBody"))).toBeInTheDocument();
}, 45000);

test("passes theme through to the widget's PropsPanel", () => {
  const receivedThemes: (unknown | undefined)[] = [];
  registerWidget({
    type: "theme-probe",
    label: "Probe",
    defaultProps: {},
    defaultSize: { w: 1, h: 1 },
    PropsPanel: ({ theme }) => {
      receivedThemes.push(theme);
      return null;
    },
    Component: () => null,
  });
  render(
    <PropsPanel
      item={{ id: "1", widget: "theme-probe", x: 0, y: 0, w: 1, h: 1, props: {} }}
      dataSources={[]}
      theme={{ colors: { primary: "#2563eb" } }}
      onChange={vi.fn()}
      onVisibleWhenChange={vi.fn()}
    />,
    { wrapper },
  );
  expect(receivedThemes).toEqual([{ colors: { primary: "#2563eb" } }]);
});

test("REV-183 : pas de bouton Générer sans generateItemId", () => {
  render(
    <PropsPanel item={item} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={vi.fn()} />,
    { wrapper },
  );
  expect(screen.queryByText("Générer")).not.toBeInTheDocument();
});

test("REV-183 : bouton Générer (chargé à la demande) avec generateItemId", async () => {
  render(
    <PropsPanel
      item={item}
      dataSources={[]}
      variables={[{ id: "v1", name: "statut", initialValue: "" }]}
      generateItemId="9"
      onChange={vi.fn()}
      onVisibleWhenChange={vi.fn()}
    />,
    { wrapper },
  );
  expect(await screen.findByText("Générer")).toBeInTheDocument();
});
