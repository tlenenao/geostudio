// SPDX-License-Identifier: Apache-2.0
// Schémas d'outils "client" pour le copilote (SP-20) — générés depuis le
// registre de widgets plutôt que maintenus à la main : un nouveau widget
// (builtin ou WC/extension — configSchema et WcWidgetManifest.props ont la
// même forme, cf. widgetPropSchema.ts) devient automatiquement éditable
// sans code copilote supplémentaire. Reconstruits à chaque tour (jamais mis
// en cache) pour capter les extensions chargées dynamiquement après le
// montage du builder (useActiveExtensions).
import { listWidgets } from "../registry";
import type { WidgetPropDescriptor } from "../widgetPropSchema";

type ClientToolSchema = { name: string; description: string; inputSchema: Record<string, unknown> };

function jsonSchemaForProp(p: WidgetPropDescriptor): Record<string, unknown> {
  if (p.type === "boolean") return { type: "boolean", description: p.label };
  if (p.type === "number") return { type: "number", description: p.label };
  return { type: "string", description: p.label }; // "string" | "dataSource"
}

export function buildClientToolSchemas(): ClientToolSchema[] {
  const widgets = listWidgets();
  const widgetTypes = widgets.map((w) => w.type);

  const updateProperties: Record<string, unknown> = {};
  for (const w of widgets) {
    for (const p of w.configSchema ?? []) {
      updateProperties[p.name] = jsonSchemaForProp(p);
    }
  }

  return [
    {
      name: "addWidget",
      description: "Ajoute un widget sur la page en cours d'édition, avec ses props par défaut.",
      inputSchema: {
        type: "object",
        properties: {
          type: { type: "string", enum: widgetTypes, description: "Type de widget à ajouter" },
        },
        required: ["type"],
      },
    },
    {
      name: "updateWidgetProps",
      description:
        "Modifie les props d'un widget déjà présent sur le canevas, identifié par son id.",
      inputSchema: {
        type: "object",
        properties: {
          widgetId: { type: "string", description: "Identifiant du widget (item.id)" },
          props: {
            type: "object",
            description: "Propriétés à fusionner sur le widget",
            properties: updateProperties,
          },
        },
        required: ["widgetId", "props"],
      },
    },
    {
      name: "removeWidget",
      description: "Retire un widget de la page en cours d'édition.",
      inputSchema: {
        type: "object",
        properties: {
          widgetId: { type: "string", description: "Identifiant du widget (item.id)" },
        },
        required: ["widgetId"],
      },
    },
    {
      name: "addDataSource",
      description: "Ajoute une source de données à la config.",
      inputSchema: {
        type: "object",
        properties: {
          id: { type: "string" },
          type: { type: "string", enum: ["features", "static", "statistics"] },
          service: { type: "string" },
          layer: { type: "string", description: "Identifiant de la collection ou du dataset" },
        },
        required: ["id", "type", "service", "layer"],
      },
    },
    {
      name: "setFilter",
      description: "Modifie la requête (filtre) d'une source de données existante.",
      inputSchema: {
        type: "object",
        properties: {
          dataSourceId: { type: "string" },
          query: { type: "object", description: "Objet de requête/filtre appliqué à la source" },
        },
        required: ["dataSourceId", "query"],
      },
    },
  ];
}
