import { test } from "@playwright/test";

// Un test qui révèle un bug connu est déclaré avec `bug(...)` : ignoré par
// défaut (test.fixme), exécuté quand AUDIT_VERIFY=1. C'est le mode « rejeu de
// la preuve » (le test doit ÉCHOUER tant que le bug existe) et, après
// correctif, le mode « non-régression » (il doit PASSER : on retire alors le
// `bug(` au profit de `test(`).
export const verifyBugs = Boolean(process.env.AUDIT_VERIFY);
export const bug = verifyBugs ? test : test.fixme;
