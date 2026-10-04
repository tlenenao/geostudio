import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, expect, test } from "vitest";
import { _resetRegistry, listWidgets } from "../registry";
import { registerBuiltinWidgets } from "./index";

// REV-278a : la liste des types natifs du cœur (validation à l'écriture) doit
// rester identique au registre du shell — ce test casse si l'un dérive.
// vitest tourne avec cwd = shell/ (import.meta.url n'est pas un file: sous jsdom).
const JSON_PATH = resolve(process.cwd(), "../core/app/configs/builtin_widget_types.json");

beforeEach(() => _resetRegistry());

test("les types natifs du cœur égalent le registre du shell", () => {
  registerBuiltinWidgets();
  const shellTypes = listWidgets()
    .map((w) => w.type)
    .sort();
  const coreTypes = (JSON.parse(readFileSync(JSON_PATH, "utf-8")) as string[]).slice().sort();
  expect(coreTypes).toEqual(shellTypes);
});
