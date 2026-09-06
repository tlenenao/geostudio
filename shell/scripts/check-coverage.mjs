#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
//
// Porte de couverture (REV-078) : vérifie les quatre métriques d'Istanbul
// (lines, branches, functions, statements) contre quatre seuils indépendants,
// au lieu de ne lire que `lines.pct` — une régression réelle sur les trois
// autres métriques ne déclenchait jamais cette porte auparavant.
import { readFileSync } from "node:fs";

export const METRICS = ["lines", "branches", "functions", "statements"];

/**
 * Seuils au format historique (un nombre nu, ex. "88") : rétrocompatible,
 * appliqué identiquement aux quatre métriques. Format étendu (REV-078) :
 * un objet JSON `{lines, branches, functions, statements}`, un seuil propre
 * par métrique.
 */
export function parseThresholds(raw) {
  const parsed = JSON.parse(raw.trim());
  if (typeof parsed === "number") {
    return Object.fromEntries(METRICS.map((metric) => [metric, parsed]));
  }
  return parsed;
}

/**
 * Compare les quatre métriques mesurées (coverage-summary.json `total`) aux
 * seuils fournis. Retourne la liste des métriques en échec (vide si tout
 * passe) — fonction pure, sans I/O, pour être testée directement.
 */
export function checkCoverage(summary, thresholds) {
  return METRICS.filter((metric) => {
    const measured = summary.total[metric].pct;
    const threshold = thresholds[metric];
    return measured < threshold;
  }).map((metric) => ({
    metric,
    measured: summary.total[metric].pct,
    threshold: thresholds[metric],
  }));
}

function main(summaryPath, thresholdPath) {
  const summary = JSON.parse(readFileSync(summaryPath, "utf-8"));
  const thresholds = parseThresholds(readFileSync(thresholdPath, "utf-8"));
  const failures = checkCoverage(summary, thresholds);

  for (const metric of METRICS) {
    const measured = summary.total[metric].pct;
    const threshold = thresholds[metric];
    console.log(
      `Couverture ${metric} : ${measured.toFixed(2)}% (seuil : ${threshold.toFixed(2)}%)`,
    );
  }

  if (failures.length > 0) {
    for (const f of failures) {
      console.error(
        `ÉCHEC : couverture ${f.metric} ${f.measured.toFixed(2)}% < seuil ${f.threshold.toFixed(2)}%`,
      );
    }
    process.exit(1);
  }
}

const isMain = process.argv[1] && import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  main(process.argv[2], process.argv[3]);
}
