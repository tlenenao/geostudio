// SPDX-License-Identifier: Apache-2.0
// i18n-ok-file: identifiants de gabarit (slugs), pas des libellés ; les noms passent par le catalogue.
// Gabarits d'app/dashboard/site : des DONNÉES déclaratives (règle d'architecture n°2),
// dans `templates.data.json`. Ce fichier est copié à l'identique dans
// `core/app/configs/builder_templates.json` (outil MCP `create_item` avec `template`) ;
// `templates.test.ts` casse si les deux dérivent. Seul le nom passe par le catalogue i18n.
import { t, type MessageKey } from "../i18n";
import type {
  ActionMessage,
  AppLayout,
  DataSource,
  Page,
  PrintLayoutConfig,
  Theme,
} from "../api/types";
import data from "./templates.data.json";

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
  printLayout?: PrintLayoutConfig;
};

const NAME_KEYS: Record<string, MessageKey> = {
  "two-column": "template.two",
  "basic-dashboard": "template.basicDashboard",
  "application-de-saisie": "template.incidentApp",
  "story-cartographique": "template.story",
  "portail-de-donnees": "template.portal",
  "tableau-de-bord-territorial": "template.territorialDashboard",
  "suivi-de-chantier": "template.worksite",
  "enquete-citoyenne": "template.survey",
  "observatoire-donnees-ouvertes": "template.openDataObservatory",
  "comparateur-de-cartes": "template.mapCompare",
  "galerie-de-fonds-de-carte": "template.basemapGallery",
  "fiches-d-entites": "template.entitySheet",
  "atlas-par-entite": "template.atlas",
};

// Le JSON n'est pas vérifié par tsc contre `Template` (littéraux élargis) : la
// conformité au schéma AppConfig est testée dans templates.test.ts et côté cœur.
export const TEMPLATES: Template[] = (data as unknown as Omit<Template, "name">[]).map((tpl) => ({
  ...tpl,
  name: t(NAME_KEYS[tpl.id]),
}));

export function getTemplate(id: string): Template | undefined {
  return TEMPLATES.find((tpl) => tpl.id === id);
}
