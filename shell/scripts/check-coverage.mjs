#!/usr/bin/env node
import { readFileSync } from "node:fs";

function main(summaryPath, thresholdPath) {
  const summary = JSON.parse(readFileSync(summaryPath, "utf-8"));
  const measured = summary.total.lines.pct;
  const threshold = Number(readFileSync(thresholdPath, "utf-8").trim());
  console.log(`Couverture mesurée : ${measured.toFixed(2)}% (seuil : ${threshold.toFixed(2)}%)`);
  if (measured < threshold) {
    console.error(`ÉCHEC : couverture ${measured.toFixed(2)}% < seuil ${threshold.toFixed(2)}%`);
    process.exit(1);
  }
}

main(process.argv[2], process.argv[3]);
