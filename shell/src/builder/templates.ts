// SPDX-License-Identifier: Apache-2.0
import type { ActionMessage, AppLayout, DataSource, Theme } from "../api/types";

export type Template = {
  id: string;
  name: string;
  kind: "app" | "dashboard";
  layout: AppLayout;
  theme?: Theme;
  dataSources?: DataSource[];
  messages?: ActionMessage[];
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

const INCIDENT_DATA_SOURCE_ID = "tpl-incident-ds";

const INCIDENT_APP_DATA_SOURCES: DataSource[] = [
  { id: INCIDENT_DATA_SOURCE_ID, type: "features", service: "core", layer: "incidents", query: {} },
];

const INCIDENT_APP_LAYOUT: AppLayout = {
  type: "grid",
  breakpoints: {},
  items: [
    {
      id: "tpl-incident-form", widget: "form", x: 0, y: 0, w: 4, h: 6,
      props: { dataSourceId: INCIDENT_DATA_SOURCE_ID, fields: [], submitLabel: "Déclarer l'incident", geometryType: null },
    },
    {
      id: "tpl-incident-map", widget: "map", x: 4, y: 0, w: 8, h: 4,
      props: { dataSourceId: INCIDENT_DATA_SOURCE_ID },
    },
    {
      id: "tpl-incident-table", widget: "table", x: 4, y: 4, w: 8, h: 2,
      props: { dataSourceId: INCIDENT_DATA_SOURCE_ID, columns: [], pageSize: 10 },
    },
  ],
};

const INCIDENT_APP_MESSAGES: ActionMessage[] = [
  { id: "tpl-incident-msg", from: "tpl-incident-table", event: "itemSelected", to: "tpl-incident-form", action: "loadRecord" },
];

export const TEMPLATES: Template[] = [
  { id: "two-column", name: "Deux colonnes", kind: "app", layout: TWO_COLUMN_LAYOUT },
  { id: "basic-dashboard", name: "Tableau de bord basique", kind: "dashboard", layout: BASIC_DASHBOARD_LAYOUT },
  {
    id: "application-de-saisie", name: "Application de saisie", kind: "app",
    layout: INCIDENT_APP_LAYOUT, dataSources: INCIDENT_APP_DATA_SOURCES, messages: INCIDENT_APP_MESSAGES,
  },
];

export function getTemplate(id: string): Template | undefined {
  return TEMPLATES.find((t) => t.id === id);
}
