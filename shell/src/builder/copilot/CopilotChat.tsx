// SPDX-License-Identifier: Apache-2.0
// Mécanique de conversation générique du copilote (GAP-17) — extrait de
// CopilotPanel.tsx (SP-20), neutre vis-à-vis du type de contexte
// (AppConfig, SQL brut, état de requête visuelle...). Chaque appelant
// fournit son propre contextPayload/clientTools/onClientOps.
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import type {
  CopilotClientOp,
  CopilotMessage,
  CopilotSurface,
  CopilotToolSchema,
} from "../../api/types";
import { t } from "../../i18n";
import { Button } from "../../ui/kit/Button";
import { useMcpToken } from "./useMcpToken";

export function CopilotChat({
  itemId,
  surface,
  contextPayload,
  clientTools,
  opLabels,
  onClientOps,
}: {
  itemId?: string;
  surface: CopilotSurface;
  contextPayload: Record<string, unknown>;
  clientTools: CopilotToolSchema[];
  opLabels: Record<string, string>;
  // Retour optionnel (M1, revue finale de branche GAP-17) : un tableau
  // aligné sur `ops`, `true` quand l'op a réellement été appliquée. Un
  // appelant qui ne renvoie rien (CopilotPanel, qui édite via setDraft et
  // n'a rien à abandonner) garde le comportement historique — tout est
  // annoncé comme appliqué.
  onClientOps: (ops: CopilotClientOp[]) => boolean[] | void;
}) {
  const client = useItemClient();
  const getMcpToken = useMcpToken();
  const contextPayloadRef = useRef(contextPayload);
  useEffect(() => {
    contextPayloadRef.current = contextPayload;
  }, [contextPayload]);
  const [history, setHistory] = useState<CopilotMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastOpsSummary, setLastOpsSummary] = useState<string[]>([]);

  async function send() {
    const message = input.trim();
    if (!message || sending) return;
    setInput("");
    setSending(true);
    setError(null);
    const priorHistory = history;
    const nextHistory: CopilotMessage[] = [...priorHistory, { role: "user", content: message }];
    setHistory(nextHistory);
    try {
      const mcpToken = await getMcpToken();
      const result = await client.copilotTurn(itemId, {
        message,
        history: priorHistory,
        mcpToken,
        currentConfig: contextPayloadRef.current,
        clientTools,
        surface,
      });
      setHistory([...nextHistory, { role: "assistant", content: result.reply }]);
      if (result.clientOps.length > 0) {
        // Appliquer D'ABORD, étiqueter ENSUITE (M1) : l'ordre inverse
        // annonçait « Brouillon SQL inséré. » pour une op que l'applier
        // venait d'abandonner silencieusement (SQL vide, filtres tous
        // invalides, métrique non conforme au schéma).
        const applied = onClientOps(result.clientOps);
        setLastOpsSummary(
          result.clientOps.map((o, i) => {
            if (Array.isArray(applied) && applied[i] !== true)
              return t("copilot.opDropped", { op: o.op });
            return opLabels[o.op] ?? t("copilot.opUnknownIgnored", { op: o.op });
          }),
        );
      } else {
        setLastOpsSummary([]);
      }
    } catch {
      setError(t("copilot.requestFailed"));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex max-h-64 flex-col gap-2 overflow-auto">
        {history.map((m, i) => (
          <p key={i} className={m.role === "user" ? "font-medium" : "text-ink-2"}>
            {m.content}
          </p>
        ))}
      </div>
      <label className="flex flex-col gap-1">
        <textarea
          aria-label={t("copilot.messageAria")}
          className="min-h-16 rounded-md border border-rule bg-surface p-2 text-sm text-ink"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
      </label>
      <Button size="sm" disabled={sending || !input.trim()} onClick={() => void send()}>
        {t("copilot.send")}
      </Button>
      {lastOpsSummary.length > 0 && (
        <ul className="text-xs text-ink-2">
          {lastOpsSummary.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
