import { useState } from "react";
import type { ActionMessage, WidgetItem } from "../api/types";
import { getWidget } from "./registry";

function widgetLabel(items: WidgetItem[], id: string): string {
  const it = items.find((i) => i.id === id);
  return (it && getWidget(it.widget)?.label) || id;
}
function eventsOf(items: WidgetItem[], id: string): readonly string[] {
  return getWidget(items.find((i) => i.id === id)?.widget ?? "")?.events ?? [];
}
function actionsOf(items: WidgetItem[], id: string): readonly string[] {
  return getWidget(items.find((i) => i.id === id)?.widget ?? "")?.actions ?? [];
}

const selectCls = "h-8 rounded border border-slate-300 bg-white text-xs";

export function ActionsPanel({
  items,
  messages,
  onChange,
}: {
  items: WidgetItem[];
  messages: ActionMessage[];
  onChange: (messages: ActionMessage[]) => void;
}) {
  const emitters = items.filter((i) => (getWidget(i.widget)?.events?.length ?? 0) > 0);
  const receivers = items.filter((i) => (getWidget(i.widget)?.actions?.length ?? 0) > 0);
  const [from, setFrom] = useState("");
  const [event, setEvent] = useState("");
  const [to, setTo] = useState("");
  const [action, setAction] = useState("");

  function add() {
    if (!from || !event || !to || !action) return;
    onChange([...messages, { id: crypto.randomUUID(), from, event, to, action }]);
    setFrom(""); setEvent(""); setTo(""); setAction("");
  }
  function remove(id: string) {
    onChange(messages.filter((m) => m.id !== id));
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <ul className="flex flex-col gap-1">
        {messages.map((m) => (
          <li key={m.id} className="flex items-center justify-between rounded border border-slate-200 p-1 text-xs">
            <span>{widgetLabel(items, m.from)}.{m.event} → {widgetLabel(items, m.to)}.{m.action}</span>
            <button type="button" aria-label={`Retirer l'action ${m.id}`} className="text-red-600" onClick={() => remove(m.id)}>✕</button>
          </li>
        ))}
        {messages.length === 0 && <li className="text-xs text-slate-400">Aucune action.</li>}
      </ul>
      <select aria-label="Widget émetteur" className={selectCls} value={from}
        onChange={(e) => { setFrom(e.target.value); setEvent(""); }}>
        <option value="">Widget émetteur…</option>
        {emitters.map((i) => <option key={i.id} value={i.id}>{widgetLabel(items, i.id)}</option>)}
      </select>
      <select aria-label="Événement" className={selectCls} value={event} disabled={!from}
        onChange={(e) => setEvent(e.target.value)}>
        <option value="">Événement…</option>
        {eventsOf(items, from).map((ev) => <option key={ev} value={ev}>{ev}</option>)}
      </select>
      <select aria-label="Widget cible" className={selectCls} value={to}
        onChange={(e) => { setTo(e.target.value); setAction(""); }}>
        <option value="">Widget cible…</option>
        {receivers.map((i) => <option key={i.id} value={i.id}>{widgetLabel(items, i.id)}</option>)}
      </select>
      <select aria-label="Action" className={selectCls} value={action} disabled={!to}
        onChange={(e) => setAction(e.target.value)}>
        <option value="">Action…</option>
        {actionsOf(items, to).map((a) => <option key={a} value={a}>{a}</option>)}
      </select>
      <button type="button" className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100" onClick={add}>
        Ajouter une action
      </button>
    </div>
  );
}
