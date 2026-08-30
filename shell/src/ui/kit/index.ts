// SPDX-License-Identifier: Apache-2.0
// Barrel du kit de primitives SP-29b. Chaque tâche du plan
// 2026-08-30-sp29b-kit-primitives.md ajoute sa ligne d'export ici.
// Ne pas réexporter shell/src/ui/{button,card,input,dialog,ConfirmDialog}.tsx
// (existants, intouchés) : ce sont deux systèmes distincts tant que SP-30
// n'a pas basculé les points d'appel.

export { Button, type ButtonProps } from "./Button";
export { IconButton, type IconButtonProps } from "./IconButton";
export { Gate } from "../../auth/Gate";
export { Field } from "./Field";
export { Input } from "./Input";
export { Textarea } from "./Textarea";
export { Checkbox } from "./Checkbox";
export { Radio } from "./Radio";
export { Switch } from "./Switch";
export { Slider } from "./Slider";
export { Segmented } from "./Segmented";
export { ColorField } from "./ColorField";
