// SPDX-License-Identifier: Apache-2.0
// i18n-ok-file: description de schéma d'outil envoyée au LLM (invite), pas de l'interface.
// Outil CLIENT du copilote sur la condition d'affichage (REV-183) : propose un
// brouillon CEL, jamais appliqué sans clic « Appliquer ». Même patron que
// sqlLabClientTools.ts.
import type { CopilotToolSchema } from "../../api/types";

export const CEL_DRAFT_TOOL: CopilotToolSchema = {
  name: "applyCelDraft",
  description:
    "Propose une expression CEL comme brouillon de condition d'affichage (visibleWhen). " +
    "Ne l'applique jamais — l'utilisateur doit cliquer sur Appliquer.",
  inputSchema: {
    type: "object",
    properties: { expression: { type: "string", description: "Expression CEL brouillon" } },
    required: ["expression"],
  },
};
