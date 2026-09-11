// SPDX-License-Identifier: Apache-2.0
import type { CollectionSchema } from "../../api/types";
import type { FilterOperator, FilterRow } from "../visualQuery/compileFilter";
import type {
  JoinConfig,
  MetricConfig,
  MetricFunction,
  SummaryConfig,
} from "../visualQuery/inferSchema";
import type { RawClientOp } from "./applyClientOp";

const FILTER_OPERATORS = new Set<FilterOperator>([
  "eq",
  "neq",
  "gt",
  "gte",
  "lt",
  "lte",
  "contains",
]);
const METRIC_FUNCTIONS = new Set<MetricFunction>([
  "count",
  "countDistinct",
  "sum",
  "avg",
  "median",
  "percentile",
  "stddev",
  "min",
  "max",
]);

// Ce que le wizard sait réellement au moment où le brouillon arrive (I2/I3,
// revue finale de branche GAP-17). Les deux schémas sont déjà chargés par
// VisualQueryWizardPage, la liste de collections aussi — rien de nouveau
// n'est requêté ici.
export type VisualQueryKnownContext = {
  baseSchema: CollectionSchema;
  joinedSchema: CollectionSchema | null;
  collectionIds: string[];
};

// Miroir exact de `_known_field_names` (core/app/mcp/tools/query_generation.py) :
// les champs de la collection jointe gardent leur nom, sauf collision avec un
// champ de base, auquel cas ils sont préfixés `joined_` (même règle que
// inferOutputColumns/compileVisualQueryToPipeline côté shell).
//
// Nuance assumée : un filtre est compilé AVANT la jointure
// (compileVisualQueryToPipeline) et donc contre `baseSchema` seul — accepter
// ici un nom de colonne jointe reste plus permissif que ce que le pipeline
// saura exécuter. On reste volontairement aligné sur la validation serveur
// plutôt que plus strict qu'elle : le rôle de ce module est de ne jamais
// laisser passer une colonne INEXISTANTE, pas de re-trancher le périmètre de
// chaque étage du compilateur.
function knownColumnNames(ctx: VisualQueryKnownContext): Set<string> {
  const names = new Set(ctx.baseSchema.fields.map((f) => f.name));
  if (ctx.joinedSchema) {
    const baseNames = new Set(names);
    for (const f of ctx.joinedSchema.fields) {
      names.add(baseNames.has(f.name) ? `joined_${f.name}` : f.name);
    }
  }
  return names;
}

function isValidGeneratedFilterRow(row: unknown, known: Set<string>): row is FilterRow {
  if (typeof row !== "object" || row === null) return false;
  const r = row as Record<string, unknown>;
  return (
    typeof r.column === "string" &&
    known.has(r.column) &&
    typeof r.operator === "string" &&
    FILTER_OPERATORS.has(r.operator as FilterOperator) &&
    typeof r.value === "string"
  );
}

function isValidGeneratedJoin(join: unknown, ctx: VisualQueryKnownContext): join is JoinConfig {
  if (typeof join !== "object" || join === null) return false;
  const j = join as Record<string, unknown>;
  return (
    typeof j.collectionId === "string" &&
    // I3 : sans ce contrôle, une collection hallucinée produisait un
    // formulaire affichant une jointure « posée » (joinValid n'exige que des
    // chaînes non vides) et un pipeline réel qui ne la porte PAS —
    // compilePipeline n'émet le SQL de jointure que sous
    // `if (state.join && joinedSchema)`, et joinedSchema reste null pour une
    // collection qui n'existe pas. Perte silencieuse de bout en bout.
    ctx.collectionIds.includes(j.collectionId) &&
    typeof j.on === "string" &&
    (j.how === "inner" || j.how === "left")
  );
}

// metricExpr (compilePipeline.ts) fait `quoteIdent(metric.sourceColumn!)` pour
// toute fonction autre que "count" — un `sourceColumn` absent y jetterait un
// TypeError non rattrapé, potentiellement après création de ressources
// backend réelles (VisualQueryWizardPage, flux "create"). "percentile" a en
// plus sa propre garde runtime sur `p` (0 < p < 100, cf. metricExpr) : un `p`
// non numérique ou hors bornes y lève une Error explicite, mais tout aussi
// non rattrapée par l'appelant de ce module. Un metric invalide sur l'un ou
// l'autre point doit être traité comme un join invalide : le résumé entier
// est ignoré (jamais une application partielle groupBy-sans-metrics).
function isValidGeneratedMetric(m: unknown, known: Set<string>): m is MetricConfig {
  if (typeof m !== "object" || m === null) return false;
  const metric = m as Record<string, unknown>;
  if (typeof metric.alias !== "string") return false;
  if (
    typeof metric.function !== "string" ||
    !METRIC_FUNCTIONS.has(metric.function as MetricFunction)
  )
    return false;
  const fn = metric.function as MetricFunction;

  // Round-trip contract avec decompileMetrics (compilePipeline.ts) : seul
  // "count" produit/attend sourceColumn: null, toute autre fonction attend
  // une chaîne non nulle (c'est elle que metricExpr quote dans le SQL émis).
  if (fn === "count") {
    if (metric.sourceColumn !== null) return false;
  } else if (typeof metric.sourceColumn !== "string" || !known.has(metric.sourceColumn)) {
    // I2 : le nom de colonne est composé par le LLM, pas repris du JSON déjà
    // validé par le tool MCP — il doit exister dans le schéma réellement
    // chargé par le wizard, sinon le pipeline créé n'échoue qu'à l'exécution.
    return false;
  }

  // Idem pour p : seul "percentile" en a besoin (0 < p < 100, borne vérifiée
  // à l'exécution par metricExpr) ; toute autre fonction attend p: null.
  if (fn === "percentile") {
    if (typeof metric.p !== "number" || !(metric.p > 0 && metric.p < 100)) return false;
  } else if (metric.p !== null) {
    return false;
  }

  return true;
}

function isValidGeneratedSummary(summary: unknown, known: Set<string>): summary is SummaryConfig {
  if (typeof summary !== "object" || summary === null) return false;
  const s = summary as Record<string, unknown>;
  if (!Array.isArray(s.groupBy) || !s.groupBy.every((g) => typeof g === "string" && known.has(g)))
    return false;
  if (!Array.isArray(s.metrics)) return false;
  return s.metrics.every((m) => isValidGeneratedMetric(m, known));
}

/**
 * Applique un brouillon de requête visuelle à l'état du wizard. Retourne
 * `true` si au moins un des trois volets a réellement été appliqué (M1 :
 * CopilotChat n'annonce « Requête visuelle mise à jour. » que dans ce cas).
 *
 * Limitation assumée (I4, revue finale de branche GAP-17) : ces écritures ne
 * passent PAS par la pile d'annulation SP-19 — contrairement au copilote du
 * builder d'App, qui édite via `setDraft`/`useUndoableDraft`. Le wizard tient
 * son état en `useState` nus ; l'y brancher est une fonctionnalité à part
 * entière (VisualQueryWizardPage n'a aucun bouton Annuler à câbler), hors du
 * périmètre de cette passe de correction. Ce qui est fermé ici, c'est le seul
 * cas réellement destructeur et silencieux : un brouillon entièrement
 * invalide qui effaçait les filtres saisis à la main.
 */
export function applyVisualQueryClientOp(
  raw: RawClientOp,
  setters: {
    setFilters: (rows: FilterRow[]) => void;
    setJoin: (join: JoinConfig | null) => void;
    setSummary: (summary: SummaryConfig | null) => void;
  },
  ctx: VisualQueryKnownContext,
): boolean {
  if (raw.op !== "applyVisualQueryDraft") return false;
  const known = knownColumnNames(ctx);
  const args = raw.args as { filters?: unknown; join?: unknown; summary?: unknown };
  let applied = false;
  if (Array.isArray(args.filters)) {
    const rows = args.filters.filter((r) => isValidGeneratedFilterRow(r, known)) as FilterRow[];
    // I4 : ne jamais vider les filtres existants parce que TOUT ce que le
    // modèle a proposé était invalide. Un tableau vide envoyé explicitement
    // reste une demande légitime d'effacement, et passe.
    if (rows.length > 0 || args.filters.length === 0) {
      setters.setFilters(rows);
      applied = true;
    }
  }
  if ("join" in args) {
    if (args.join === null) {
      setters.setJoin(null);
      applied = true;
    } else if (isValidGeneratedJoin(args.join, ctx)) {
      setters.setJoin(args.join);
      applied = true;
    }
  }
  if ("summary" in args) {
    if (args.summary === null) {
      setters.setSummary(null);
      applied = true;
    } else if (isValidGeneratedSummary(args.summary, known)) {
      setters.setSummary(args.summary as SummaryConfig);
      applied = true;
    }
  }
  return applied;
}
