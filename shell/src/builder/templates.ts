// SPDX-License-Identifier: Apache-2.0
import type { ActionMessage, AppLayout, DataSource, Page, Theme } from "../api/types";

export type Template = {
  id: string;
  name: string;
  kind: "app" | "dashboard" | "site";
  layout: AppLayout;
  theme?: Theme;
  dataSources?: DataSource[];
  messages?: ActionMessage[];
  pages?: Page[];
  navigationMode?: "tabs" | "story";
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

function storyChapter(idx: number, title: string, center: [number, number]): Page {
  const mapId = `tpl-story-map-${idx}`;
  return {
    id: `tpl-story-page-${idx}`,
    name: title,
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: `tpl-story-text-${idx}`, widget: "text", x: 0, y: 0, w: 4, h: 6,
          props: { text: `## ${title}\n\nRacontez ce chapitre ici.` } },
        { id: mapId, widget: "map", x: 4, y: 0, w: 8, h: 6, props: {} },
      ],
    },
    onEnter: [
      { id: `tpl-story-onenter-${idx}`, from: `tpl-story-page-${idx}`, event: "enter",
        to: mapId, action: "flyTo", payload: { center } },
    ],
  };
}

const STORY_PAGES: Page[] = [
  storyChapter(1, "Introduction", [2.35, 48.85]),
  storyChapter(2, "Développement", [4.83, 45.76]),
  storyChapter(3, "Conclusion", [-1.55, 47.22]),
];

const PORTAL_DATA_SOURCE_ID = "tpl-portal-ds";

const PORTAL_DATA_SOURCES: DataSource[] = [
  { id: PORTAL_DATA_SOURCE_ID, type: "features", service: "core", layer: "incidents", query: {} },
];

const PORTAL_LAYOUT: AppLayout = {
  type: "grid",
  breakpoints: {},
  items: [
    {
      id: "tpl-portal-hero", widget: "hero", x: 0, y: 0, w: 12, h: 3,
      props: {
        title: "Portail de données", subtitle: "Explorez et téléchargez nos jeux de données ouverts.",
        backgroundImageUrl: "", ctaLabel: "", ctaHref: "", align: "left",
      },
    },
    {
      id: "tpl-portal-gallery", widget: "gallery", x: 0, y: 3, w: 12, h: 4,
      props: { type: "", tag: "", limit: 12, columns: 3 },
    },
    {
      id: "tpl-portal-dataset-card", widget: "datasetCard", x: 0, y: 7, w: 4, h: 4,
      props: { dataSourceId: PORTAL_DATA_SOURCE_ID, showDownload: true, title: "" },
    },
    {
      id: "tpl-portal-map", widget: "map", x: 4, y: 7, w: 4, h: 4,
      props: { dataSourceId: PORTAL_DATA_SOURCE_ID },
    },
    {
      id: "tpl-portal-table", widget: "table", x: 8, y: 7, w: 4, h: 4,
      props: { dataSourceId: PORTAL_DATA_SOURCE_ID, columns: [], pageSize: 10 },
    },
  ],
};

export const TEMPLATES: Template[] = [
  { id: "two-column", name: "Deux colonnes", kind: "app", layout: TWO_COLUMN_LAYOUT },
  { id: "basic-dashboard", name: "Tableau de bord basique", kind: "dashboard", layout: BASIC_DASHBOARD_LAYOUT },
  {
    id: "application-de-saisie", name: "Application de saisie", kind: "app",
    layout: INCIDENT_APP_LAYOUT, dataSources: INCIDENT_APP_DATA_SOURCES, messages: INCIDENT_APP_MESSAGES,
  },
  {
    id: "story-cartographique", name: "Story cartographique", kind: "app",
    layout: STORY_PAGES[0].layout, pages: STORY_PAGES, navigationMode: "story",
  },
  {
    id: "portail-de-donnees", name: "Portail de données", kind: "site",
    layout: PORTAL_LAYOUT, dataSources: PORTAL_DATA_SOURCES,
  },
];

export function getTemplate(id: string): Template | undefined {
  return TEMPLATES.find((t) => t.id === id);
}
