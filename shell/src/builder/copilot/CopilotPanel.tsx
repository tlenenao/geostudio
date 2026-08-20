// SPDX-License-Identifier: Apache-2.0
// Panneau copilote du builder (SP-20) — propose des micro-actions
// (ajouter/modifier/retirer un widget, source de données, filtre) sur la
// config en cours d'édition. Chaque action passée par clientOps traverse
// setDraft (SP-19 undo) en un seul appel par tour : annulable via le
// bouton "Annuler" existant de la barre d'outils (AppBuilderPage.tsx),
// pas de bouton Annuler dédié ici — un seul et même undo stack.
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import type { AppConfig, CopilotMessage } from "../../api/types";
import { Button } from "../../ui/button";
import { applyClientOp, type RawClientOp } from "./applyClientOp";
import { buildClientToolSchemas } from "./clientTools";
import { useMcpToken } from "./useMcpToken";

const OP_LABELS: Record<string, string> = {
  addWidget: "Widget ajouté",
  updateWidgetProps: "Widget modifié",
  removeWidget: "Widget supprimé",
  addDataSource: "Source de données ajoutée",
  setFilter: "Filtre modifié",
};

export function CopilotPanel({
  itemId, config, activePageId, setDraft,
}: {
  itemId: string;
  config: AppConfig;
  activePageId: string;
  setDraft: (update: (prev: AppConfig | null) => AppConfig | null) => void;
}) {
  const client = useItemClient();
  const getMcpToken = useMcpToken();
  // Un tour peut durer plusieurs secondes : si l'utilisateur change de page
  // pendant ce temps, les clientOps doivent viser la page réellement active
  // à l'arrivée de la réponse, pas celle capturée à l'envoi (la config,
  // elle, est déjà lue au plus tard via le paramètre `d` de setDraft).
  const activePageIdRef = useRef(activePageId);
  useEffect(() => {
    activePageIdRef.current = activePageId;
  }, [activePageId]);
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
        message, history: priorHistory, mcpToken, currentConfig: config,
        clientTools: buildClientToolSchemas(),
      });
      setHistory([...nextHistory, { role: "assistant", content: result.reply }]);
      if (result.clientOps.length > 0) {
        setLastOpsSummary(result.clientOps.map((o) => OP_LABELS[o.op] ?? `Action inconnue ignorée : ${o.op}`));
        setDraft((d) => {
          if (!d) return d;
          return (result.clientOps as RawClientOp[]).reduce(
            (acc, op) => applyClientOp(op, acc, activePageIdRef.current), d,
          );
        });
      } else {
        setLastOpsSummary([]);
      }
    } catch {
      setError("Échec de la requête au copilote.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex max-h-64 flex-col gap-2 overflow-auto">
        {history.map((m, i) => (
          <p key={i} className={m.role === "user" ? "font-medium" : "text-slate-600"}>
            {m.content}
          </p>
        ))}
      </div>
      <label className="flex flex-col gap-1">
        <textarea
          aria-label="Message au copilote"
          className="min-h-16 rounded-md border border-slate-300 p-2 text-sm"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
      </label>
      <Button size="sm" disabled={sending || !input.trim()} onClick={send}>
        Envoyer
      </Button>
      {lastOpsSummary.length > 0 && (
        <ul className="text-xs text-slate-500">
          {lastOpsSummary.map((s, i) => <li key={i}>{s}</li>)}
        </ul>
      )}
      {error && <p role="alert" className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
