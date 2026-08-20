// SPDX-License-Identifier: Apache-2.0
// Forme partagée par WidgetDefinition.configSchema (builtin widgets, ce
// fichier) et WcWidgetManifest.props (widgets WC/extension, SP-8,
// shell/src/builder/wc/manifest.ts) — même shape, délibérément non
// unifiées par un import commun pour ne pas toucher le module SP-8 : le
// typage structurel de TypeScript suffit à rendre les deux compatibles
// partout où clientTools.ts (Task 9) les consomme ensemble.
export type WidgetPropDescriptor = {
  name: string;
  type: "string" | "number" | "boolean" | "dataSource";
  label: string;
  default: unknown;
};
