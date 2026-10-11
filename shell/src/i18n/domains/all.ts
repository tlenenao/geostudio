// SPDX-License-Identifier: Apache-2.0
// TESTS UNIQUEMENT : réunit le noyau et tous les domaines (et les enregistre).
// Ne jamais importer depuis du code de production : ce serait ramener tout le
// catalogue dans le chunk d'entrée (REV-307 b).
import { fr } from "../catalog.fr";
import { admin } from "./admin";
import { automation } from "./automation";
import { map } from "./map";
import { misc } from "./misc";
import { widgets } from "./widgets";

export const allMessages = { ...fr, ...admin, ...automation, ...map, ...misc, ...widgets };
