// SPDX-License-Identifier: Apache-2.0
// REV-183 : brouillon d'expression CEL généré par le copilote (condition
// d'affichage, colonne calculée, condition d'action ; surface correspondante →
// outil MCP generate_cel_expression → op client applyCelDraft). Validé par validateExpression ; n'est appliqué que sur
// clic « Appliquer », jamais automatiquement. Chargé par lazy() depuis
// PropsPanel (marge de bundle initial).
import { useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import { Button } from "../../ui/kit/Button";
import { t } from "../../i18n";
import { formatCelError } from "../celError";
import { validateExpression } from "../expr";
import { CEL_DRAFT_TOOL } from "./celClientTools";
import { useMcpToken } from "./useMcpToken";
import "../../i18n/domains/automation";
import "../../i18n/domains/widgets";

export type CelGeneratorContext = "visibleWhen" | "computedColumn" | "actionCondition";

const SURFACE = {
  visibleWhen: "visible_when",
  computedColumn: "computed_column",
  actionCondition: "action_condition",
} as const;
const CURRENT_KEY = { visibleWhen: "visibleWhen", computedColumn: "expr", actionCondition: "when" };

export function CelGenerator({
  itemId,
  availableFields,
  current,
  context = "visibleWhen",
  onApply,
}: {
  context?: CelGeneratorContext;
  itemId: string;
  availableFields: string[];
  current: string;
  onApply: (expr: string) => void;
}) {
  const client = useItemClient();
  const getMcpToken = useMcpToken();
  const [question, setQuestion] = useState("");
  const [draft, setDraft] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function propose() {
    setPending(true);
    setError(null);
    setDraft(null);
    try {
      const result = await client.copilotTurn(itemId, {
        message: question,
        history: [],
        mcpToken: await getMcpToken(),
        currentConfig: { availableFields, [CURRENT_KEY[context]]: current },
        clientTools: [CEL_DRAFT_TOOL],
        surface: SURFACE[context],
      });
      const op = result.clientOps.find((o) => o.op === CEL_DRAFT_TOOL.name);
      const expression = typeof op?.args.expression === "string" ? op.args.expression.trim() : "";
      if (expression) setDraft(expression);
      else setError(t("celGen.noDraft"));
    } catch {
      setError(t("copilot.requestFailed"));
    } finally {
      setPending(false);
    }
  }

  const draftError = draft ? validateExpression(draft) : null;
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-xs text-ink-2">{t("celGen.summary")}</summary>
      <div className="mt-2 flex flex-col gap-2">
        <textarea
          aria-label={t(
            context === "computedColumn" ? "celGen.questionAriaExpr" : "celGen.questionAria",
          )}
          className="rounded-md border border-rule p-2 text-xs"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button
          size="sm"
          variant="outline"
          className="w-fit"
          disabled={pending || !question.trim()}
          onClick={() => void propose()}
        >
          {t("celGen.propose")}
        </Button>
        {error && (
          <span role="alert" className="text-xs text-danger">
            {error}
          </span>
        )}
        {draft !== null && (
          <>
            <code className="rounded-md border border-rule p-2 font-mono text-xs">{draft}</code>
            {draftError && (
              <span role="alert" className="whitespace-pre-line text-xs text-danger">
                {formatCelError(draftError)}
              </span>
            )}
            <Button
              size="sm"
              className="w-fit"
              disabled={draftError !== null}
              onClick={() => onApply(draft)}
            >
              {t("celGen.apply")}
            </Button>
          </>
        )}
      </div>
    </details>
  );
}

export const VisibleWhenGenerator = CelGenerator;
