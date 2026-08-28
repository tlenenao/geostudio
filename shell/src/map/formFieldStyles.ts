// SPDX-License-Identifier: Apache-2.0
// Classes Tailwind partagées par les éditeurs de carte qui composent un
// formulaire label+input simple. Centralisées ici plutôt que copiées : avant
// ce fichier, MapSymbologyEditor.tsx et FieldClassificationPicker.tsx en
// avaient chacun leur propre copie identique (constat de revue Task 5,
// SP-27) — et les tâches 12/14 allaient propager cette copie si on la
// laissait. Un petit module de constantes plutôt qu'un export de l'un vers
// l'autre : ni fichier n'a besoin d'importer l'autre pour ces deux chaînes.
export const labelCls = "flex flex-col gap-1";
export const inputCls = "h-8 rounded-md border border-slate-300 px-2 text-sm";
