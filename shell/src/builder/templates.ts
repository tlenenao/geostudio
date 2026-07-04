import type { AppLayout, Theme } from "../api/types";

export type Template = {
  id: string;
  name: string;
  kind: "app" | "dashboard";
  layout: AppLayout;
  theme?: Theme;
};

const TWO_COLUMN_LAYOUT: AppLayout = {
  type: "grid",
  breakpoints: {},
  items: [
    { id: "tpl-two-col-a", widget: "text", x: 0, y: 0, w: 3, h: 3, props: { text: "Colonne gauche" } },
    { id: "tpl-two-col-b", widget: "text", x: 3, y: 0, w: 3, h: 3, props: { text: "Colonne droite" } },
  ],
};

const BASIC_DASHBOARD_LAYOUT: AppLayout = {
  type: "grid",
  breakpoints: {},
  items: [
    { id: "tpl-dash-title", widget: "text", x: 0, y: 0, w: 6, h: 2, props: { text: "Bienvenue sur votre tableau de bord" } },
    { id: "tpl-dash-cta", widget: "button", x: 0, y: 2, w: 2, h: 1, props: { label: "En savoir plus", href: "" } },
  ],
};

export const TEMPLATES: Template[] = [
  { id: "two-column", name: "Deux colonnes", kind: "app", layout: TWO_COLUMN_LAYOUT },
  { id: "basic-dashboard", name: "Tableau de bord basique", kind: "dashboard", layout: BASIC_DASHBOARD_LAYOUT },
];

export function getTemplate(id: string): Template | undefined {
  return TEMPLATES.find((t) => t.id === id);
}
