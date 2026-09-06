// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import type { ActionMessage, Variable, WidgetItem } from "../api/types";
import { t } from "../i18n";
import { getWidget } from "./registry";
import { validateExpression } from "./expr";

function widgetLabel(items: WidgetItem[], variables: Variable[], id: string): string {
  if (id.startsWith("var:")) {
    const v = variables.find((v) => `var:${v.id}` === id);
    return v ? t("actionsPanel.variableLabel", { name: v.name }) : id;
  }
  const it = items.find((i) => i.id === id);
  return (it && getWidget(it.widget)?.label) || id;
}
function eventsOf(items: WidgetItem[], id: string): readonly string[] {
  return getWidget(items.find((i) => i.id === id)?.widget ?? "")?.events ?? [];
}
function actionsOf(items: WidgetItem[], id: string): readonly string[] {
  if (id.startsWith("var:")) return ["set"];
  return getWidget(items.find((i) => i.id === id)?.widget ?? "")?.actions ?? [];
}
function resolvesOnThisPage(items: WidgetItem[], variables: Variable[], id: string): boolean {
  if (id.startsWith("var:")) return variables.some((v) => `var:${v.id}` === id);
  return items.some((i) => i.id === id);
}

const selectCls = "h-8 rounded border border-slate-300 bg-white text-xs";

export function ActionsPanel({
  items,
  variables = [],
  messages,
  onChange,
}: {
  items: WidgetItem[];
  variables?: Variable[];
  messages: ActionMessage[];
  onChange: (messages: ActionMessage[]) => void;
}) {
  const emitters = items.filter((i) => (getWidget(i.widget)?.events?.length ?? 0) > 0);
  const widgetReceivers = items.filter((i) => (getWidget(i.widget)?.actions?.length ?? 0) > 0);
  const variableReceivers = variables.map((v) => ({
    id: `var:${v.id}`,
    label: t("actionsPanel.variableLabel", { name: v.name }),
  }));
  const [from, setFrom] = useState("");
  const [event, setEvent] = useState("");
  const [to, setTo] = useState("");
  const [action, setAction] = useState("");

  const visibleMessages = messages.filter(
    (m) =>
      resolvesOnThisPage(items, variables, m.from) && resolvesOnThisPage(items, variables, m.to),
  );

  function add() {
    if (!from || !event || !to || !action) return;
    onChange([...messages, { id: crypto.randomUUID(), from, event, to, action }]);
    setFrom("");
    setEvent("");
    setTo("");
    setAction("");
  }
  function remove(id: string) {
    onChange(messages.filter((m) => m.id !== id));
  }
  function updateWhen(id: string, when: string) {
    onChange(messages.map((m) => (m.id === id ? { ...m, when: when || undefined } : m)));
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <ul className="flex flex-col gap-1">
        {visibleMessages.map((m) => {
          const when = m.when ?? "";
          const error = when ? validateExpression(when) : null;
          return (
            <li
              key={m.id}
              className="flex flex-col gap-1 rounded border border-slate-200 p-1 text-xs"
            >
              <div className="flex items-center justify-between">
                <span>
                  {widgetLabel(items, variables, m.from)}.{m.event} →{" "}
                  {widgetLabel(items, variables, m.to)}.{m.action}
                </span>
                <button
                  type="button"
                  aria-label={t("actionsPanel.removeAria", { id: m.id })}
                  className="text-red-600"
                  onClick={() => remove(m.id)}
                >
                  ✕
                </button>
              </div>
              <input
                aria-label={t("actionsPanel.conditionAria", { id: m.id })}
                placeholder={t("actionsPanel.conditionPlaceholder")}
                className="h-7 rounded border border-slate-300 px-1 font-mono"
                value={when}
                onChange={(e) => updateWhen(m.id, e.target.value)}
              />
              {error && (
                <span role="alert" className="text-red-600">
                  {error}
                </span>
              )}
            </li>
          );
        })}
        {visibleMessages.length === 0 && (
          <li className="text-xs text-ink-2">{t("actionsPanel.empty")}</li>
        )}
      </ul>
      <select
        aria-label={t("actionsPanel.emitterAria")}
        className={selectCls}
        value={from}
        onChange={(e) => {
          setFrom(e.target.value);
          setEvent("");
        }}
      >
        <option value="">{t("actionsPanel.emitterPlaceholder")}</option>
        {emitters.map((i) => (
          <option key={i.id} value={i.id}>
            {widgetLabel(items, variables, i.id)}
          </option>
        ))}
      </select>
      <select
        aria-label={t("actionsPanel.eventAria")}
        className={selectCls}
        value={event}
        disabled={!from}
        onChange={(e) => setEvent(e.target.value)}
      >
        <option value="">{t("actionsPanel.eventPlaceholder")}</option>
        {eventsOf(items, from).map((ev) => (
          <option key={ev} value={ev}>
            {ev}
          </option>
        ))}
      </select>
      <select
        aria-label={t("actionsPanel.targetAria")}
        className={selectCls}
        value={to}
        onChange={(e) => {
          setTo(e.target.value);
          setAction("");
        }}
      >
        <option value="">{t("actionsPanel.targetPlaceholder")}</option>
        {widgetReceivers.map((i) => (
          <option key={i.id} value={i.id}>
            {widgetLabel(items, variables, i.id)}
          </option>
        ))}
        {variableReceivers.map((r) => (
          <option key={r.id} value={r.id}>
            {r.label}
          </option>
        ))}
      </select>
      <select
        aria-label={t("actionsPanel.actionAria")}
        className={selectCls}
        value={action}
        disabled={!to}
        onChange={(e) => setAction(e.target.value)}
      >
        <option value="">{t("actionsPanel.actionPlaceholder")}</option>
        {actionsOf(items, to).map((a) => (
          <option key={a} value={a}>
            {a}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100"
        onClick={add}
      >
        {t("actionsPanel.addButton")}
      </button>
    </div>
  );
}
