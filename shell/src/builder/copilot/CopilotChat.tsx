// SPDX-License-Identifier: Apache-2.0
// Mécanique de conversation générique du copilote (GAP-17) — extrait de
// CopilotPanel.tsx (SP-20), neutre vis-à-vis du type de contexte
// (AppConfig, SQL brut, état de requête visuelle...). Chaque appelant
// fournit son propre contextPayload/clientTools/onClientOps.
import { useContext, useEffect, useRef, useState } from "react";
import { QueryClientContext } from "@tanstack/react-query";
import { ApiError } from "../../api/ApiError";
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
import "../../i18n/domains/automation";

// Bornes du cœur (core/app/copilot/routes.py : MAX_MESSAGE_CHARS,
// MAX_HISTORY_MESSAGES, MAX_HISTORY_MESSAGE_CHARS) — au-delà, 422 (P07.04).
export const MAX_MESSAGE_CHARS = 4_000;
export const MAX_HISTORY_MESSAGES = 40;
const MAX_HISTORY_MESSAGE_CHARS = 8_000;

/** Fenêtre glissante de l'historique envoyé au cœur. */
export function boundHistory(history: CopilotMessage[]): CopilotMessage[] {
  return history
    .slice(-MAX_HISTORY_MESSAGES)
    .map((m) => ({ ...m, content: m.content.slice(0, MAX_HISTORY_MESSAGE_CHARS) }));
}

export function CopilotChat({
  itemId,
  surface,
  contextPayload,
  clientTools,
  opLabels,
  onClientOps,
  onExchange,
  disabled = false,
}: {
  disabled?: boolean;
  itemId?: string;
  surface: CopilotSurface;
  contextPayload: Record<string, unknown>;
  clientTools: CopilotToolSchema[];
  opLabels: Record<string, string>;
  // Retour optionnel (M1, revue finale de branche GAP-17) : un tableau
  // aligné sur `ops`, `true` quand l'op a réellement été appliquée, une
  // CHAÎNE quand elle ne l'a été qu'en partie (REV-184(1) : libellé affiché
  // tel quel). Un appelant qui ne renvoie rien (CopilotPanel, qui édite via
  // setDraft et n'a rien à abandonner) garde le comportement historique —
  // tout est annoncé comme appliqué.
  onClientOps: (ops: CopilotClientOp[]) => (boolean | string)[] | void;
  // Callback optionnel (D56, historique persistant) : un appelant qui ne
  // le passe pas garde son comportement actuel inchangé.
  onExchange?: (entry: { message: string; opsCount: number; status: "ok" | "error" }) => void;
}) {
  const client = useItemClient();
  const getMcpToken = useMcpToken();
  // REV-287(a) : contexte lu sans exiger de provider (plusieurs montages de
  // test n'en ont pas) — useQueryClient() lèverait.
  const queryClient = useContext(QueryClientContext);
  const contextPayloadRef = useRef(contextPayload);
  useEffect(() => {
    contextPayloadRef.current = contextPayload;
  }, [contextPayload]);
  const [history, setHistory] = useState<CopilotMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastOpsSummary, setLastOpsSummary] = useState<string[]>([]);
  // j11-012 : écriture proposée par le copilote, en attente d'un clic humain.
  const [pendingWrite, setPendingWrite] = useState<{
    name: string;
    arguments: Record<string, unknown>;
  } | null>(null);

  async function confirmWrite(write: { name: string; arguments: Record<string, unknown> }) {
    setPendingWrite(null);
    setSending(true);
    setError(null);
    try {
      const result = await client.copilotTurn(itemId, {
        message: t("copilot.confirmWriteMessage"),
        history: [],
        mcpToken: await getMcpToken(),
        currentConfig: contextPayloadRef.current,
        clientTools: [],
        surface,
        confirmWrite: write,
      });
      setHistory((h) => [...h, { role: "assistant", content: result.reply }]);
      // Les écritures confirmables (create_item, create_form_app) CRÉENT un
      // item : la liste du catalogue est périmée.
      void queryClient?.invalidateQueries({ queryKey: ["items"] });
    } catch {
      setError(t("copilot.requestFailed"));
    } finally {
      setSending(false);
    }
  }

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
        history: boundHistory(priorHistory),
        mcpToken,
        currentConfig: contextPayloadRef.current,
        clientTools,
        surface,
      });
      setHistory([...nextHistory, { role: "assistant", content: result.reply }]);
      const writeOp = result.clientOps.find((o) => o.op === "confirmWrite");
      if (writeOp)
        setPendingWrite(writeOp.args as { name: string; arguments: Record<string, unknown> });
      result.clientOps = result.clientOps.filter((o) => o.op !== "confirmWrite");
      if (result.clientOps.length > 0) {
        // Appliquer D'ABORD, étiqueter ENSUITE (M1) : l'ordre inverse
        // annonçait « Brouillon SQL inséré. » pour une op que l'applier
        // venait d'abandonner silencieusement (SQL vide, filtres tous
        // invalides, métrique non conforme au schéma).
        const applied = onClientOps(result.clientOps);
        setLastOpsSummary(
          result.clientOps.map((o, i) => {
            const outcome = Array.isArray(applied) ? applied[i] : true;
            if (typeof outcome === "string") return outcome;
            if (outcome !== true) return t("copilot.opDropped", { op: o.op });
            return opLabels[o.op] ?? t("copilot.opUnknownIgnored", { op: o.op });
          }),
        );
      } else {
        setLastOpsSummary([]);
      }
      onExchange?.({ message, opsCount: result.clientOps.length, status: "ok" });
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 422 && /trop volumineuse/.test(e.detail ?? "")
          ? t("copilot.contextTooLarge")
          : t("copilot.requestFailed"),
      );
      onExchange?.({ message, opsCount: 0, status: "error" });
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
      <div className="flex flex-col gap-1">
        <textarea
          aria-label={t("copilot.messageAria")}
          className="min-h-16 rounded-md border border-rule bg-surface p-2 text-sm text-ink"
          value={input}
          disabled={disabled}
          maxLength={MAX_MESSAGE_CHARS}
          onChange={(e) => setInput(e.target.value)}
        />
      </div>
      <Button size="sm" disabled={disabled || sending || !input.trim()} onClick={() => void send()}>
        {t("copilot.send")}
      </Button>
      {disabled && <p className="text-xs text-ink-2">{t("copilot.readOnly")}</p>}
      {pendingWrite && (
        <div role="alert" className="flex flex-col gap-1 rounded-md border border-rule p-2 text-xs">
          <p>{t("copilot.confirmWritePrompt", { name: pendingWrite.name })}</p>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => void confirmWrite(pendingWrite)}>
              {t("copilot.confirmWriteYes")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPendingWrite(null)}>
              {t("copilot.confirmWriteNo")}
            </Button>
          </div>
        </div>
      )}
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
