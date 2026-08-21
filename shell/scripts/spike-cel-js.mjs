// shell/scripts/spike-cel-js.mjs
// Spike SP-5a (A8) : valide que cel-js couvre le vocabulaire nécessaire à
// SP-5a (vars.x, record.champ, user.name, opérateurs arithmétiques/logiques,
// ternaire) et que les erreurs d'évaluation/parse sont bien catchables en JS
// pur, sans faire planter le process.
//
// Usage : node scripts/spike-cel-js.mjs
// Sort avec le code 0 (PASS) ou 1 (FAIL, échecs listés).
import { evaluate, parse } from "cel-js";

const failures = [];
function check(name, cond) {
  console.log(`  [${cond ? "PASS" : "FAIL"}] ${name}`);
  if (!cond) failures.push(name);
}

check("arithmétique de base", evaluate("1 + 2 * 3") === 7);
check("concaténation de chaînes", evaluate("'a' + 'b'") === "ab");
check("opérateur ternaire", evaluate("1 == 1 ? 'oui' : 'non'") === "oui");

const ctx = { vars: { seuil: "haute" }, record: { gravite: "haute" }, user: { name: "tanguy" } };
check(
  "vocabulaire vars.x / record.champ / user.name",
  evaluate('vars.seuil == "haute" && record.gravite == vars.seuil && user.name != ""', ctx) ===
    true,
);

let evalThrew = false;
try {
  evaluate("record.missingField", ctx);
} catch (err) {
  evalThrew = err instanceof Error;
}
check("une évaluation invalide lève une Error JS catchable (pas de crash process)", evalThrew);

const parseOk = parse("1 + 2");
check("parse() réussit sur une expression valide", parseOk.isSuccess === true);

const parseBad = parse("vars.x ==");
check(
  "parse() échoue proprement sur une expression invalide, avec un message",
  parseBad.isSuccess === false && Array.isArray(parseBad.errors) && parseBad.errors.length > 0,
);

const verdict = failures.length === 0 ? "PASS" : `FAIL (${failures.join(", ")})`;
console.log(`\nRésultat spike : ${verdict}`);
process.exit(failures.length === 0 ? 0 : 1);
