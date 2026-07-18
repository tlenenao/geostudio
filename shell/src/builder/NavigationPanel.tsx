// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import type { ActionMessage, Page, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { validateExpression } from "./expr";

const selectCls = "h-8 rounded border border-slate-300 bg-white text-xs";

function widgetLabel(items: WidgetItem[], id: string): string {
  const it = items.find((i) => i.id === id);
  return (it && getWidget(it.widget)?.label) || id;
}
function actionsOf(items: WidgetItem[], id: string): readonly string[] {
  return getWidget(items.find((i) => i.id === id)?.widget ?? "")?.actions ?? [];
}

export function NavigationPanel({
  navigationMode,
  onNavigationModeChange,
  page,
  onPageChange,
}: {
  navigationMode: "tabs" | "story";
  onNavigationModeChange: (m: "tabs" | "story") => void;
  page: Page;
  onPageChange: (page: Page) => void;
}) {
  const items = page.layout.items;
  const receivers = items.filter((i) => (getWidget(i.widget)?.actions?.length ?? 0) > 0);
  const onEnter = page.onEnter ?? [];
  const [to, setTo] = useState("");
  const [action, setAction] = useState("");
  const [lon, setLon] = useState("");
  const [lat, setLat] = useState("");

  function add() {
    const lonNum = Number(lon);
    const latNum = Number(lat);
    if (!to || !action || Number.isNaN(lonNum) || Number.isNaN(latNum)) return;
    const message: ActionMessage = {
      id: crypto.randomUUID(),
      from: page.id,
      event: "enter",
      to,
      action,
      payload: { center: [lonNum, latNum] },
    };
    onPageChange({ ...page, onEnter: [...onEnter, message] });
    setTo(""); setAction(""); setLon(""); setLat("");
  }
  function remove(id: string) {
    onPageChange({ ...page, onEnter: onEnter.filter((m) => m.id !== id) });
  }
  function updateWhen(id: string, when: string) {
    onPageChange({
      ...page,
      onEnter: onEnter.map((m) => (m.id === id ? { ...m, when: when || undefined } : m)),
    });
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <label className="flex flex-col gap-1 text-xs">
        Mode de navigation
        <select
          aria-label="Mode de navigation"
          className={selectCls}
          value={navigationMode}
          onChange={(e) => onNavigationModeChange(e.target.value as "tabs" | "story")}
        >
          <option value="tabs">Onglets</option>
          <option value="story">Story (chapitres)</option>
        </select>
      </label>

      {navigationMode === "story" && (
        <>
          <p className="text-[10px] text-slate-400">Actions à l'entrée du chapitre « {page.name} ».</p>
          <ul className="flex flex-col gap-1">
            {onEnter.map((m) => {
              const when = m.when ?? "";
              const error = when ? validateExpression(when) : null;
              const center = (m.payload?.center as [number, number] | undefined);
              return (
                <li key={m.id} className="flex flex-col gap-1 rounded border border-slate-200 p-1 text-xs">
                  <div className="flex items-center justify-between">
                    <span>
                      {widgetLabel(items, m.to)}.{m.action}
                      {center ? ` → [${center[0]}, ${center[1]}]` : ""}
                    </span>
                    <button type="button" aria-label={`Retirer l'action ${m.id}`} className="text-red-600" onClick={() => remove(m.id)}>✕</button>
                  </div>
                  <input
                    aria-label={`Condition de l'action ${m.id}`}
                    placeholder="Condition (optionnel)"
                    className="h-7 rounded border border-slate-300 px-1 font-mono"
                    value={when}
                    onChange={(e) => updateWhen(m.id, e.target.value)}
                  />
                  {error && <span role="alert" className="text-red-600">{error}</span>}
                </li>
              );
            })}
            {onEnter.length === 0 && <li className="text-xs text-slate-400">Aucune action à l'entrée.</li>}
          </ul>

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
          <div className="flex gap-1">
            <input aria-label="Longitude" placeholder="Longitude" className="h-8 w-1/2 rounded border border-slate-300 px-1 text-xs"
              value={lon} onChange={(e) => setLon(e.target.value)} />
            <input aria-label="Latitude" placeholder="Latitude" className="h-8 w-1/2 rounded border border-slate-300 px-1 text-xs"
              value={lat} onChange={(e) => setLat(e.target.value)} />
          </div>
          <button type="button" className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100" onClick={add}>
            Ajouter à ce chapitre
          </button>
        </>
      )}
    </div>
  );
}
