// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import type { ActionMessage, Page, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { validateExpression } from "./expr";
import { t } from "../i18n";

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
    const lonTrimmed = lon.trim();
    const latTrimmed = lat.trim();
    const lonNum = Number(lonTrimmed);
    const latNum = Number(latTrimmed);
    if (
      !to ||
      !action ||
      !lonTrimmed ||
      !latTrimmed ||
      Number.isNaN(lonNum) ||
      Number.isNaN(latNum)
    )
      return;
    const message: ActionMessage = {
      id: crypto.randomUUID(),
      from: page.id,
      event: "enter",
      to,
      action,
      payload: { center: [lonNum, latNum] },
    };
    onPageChange({ ...page, onEnter: [...onEnter, message] });
    setTo("");
    setAction("");
    setLon("");
    setLat("");
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
        {t("navigationPanel.modeLabel")}
        <select
          aria-label={t("navigationPanel.modeLabel")}
          className={selectCls}
          value={navigationMode}
          onChange={(e) => onNavigationModeChange(e.target.value as "tabs" | "story")}
        >
          <option value="tabs">{t("navigationPanel.tabsOption")}</option>
          <option value="story">{t("navigationPanel.storyOption")}</option>
        </select>
      </label>

      {navigationMode === "story" && (
        <>
          <p className="text-[10px] text-ink-2">
            {t("navigationPanel.enterActionsHeading", { name: page.name })}
          </p>
          <ul className="flex flex-col gap-1">
            {onEnter.map((m) => {
              const when = m.when ?? "";
              const error = when ? validateExpression(when) : null;
              const center = m.payload?.center as [number, number] | undefined;
              return (
                <li
                  key={m.id}
                  className="flex flex-col gap-1 rounded border border-slate-200 p-1 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span>
                      {widgetLabel(items, m.to)}.{m.action}
                      {center ? ` → [${center[0]}, ${center[1]}]` : ""}
                    </span>
                    <button
                      type="button"
                      aria-label={t("navigationPanel.removeActionAria", { id: m.id })}
                      className="text-red-600"
                      onClick={() => remove(m.id)}
                    >
                      ✕
                    </button>
                  </div>
                  <input
                    aria-label={t("navigationPanel.conditionAria", { id: m.id })}
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
            {onEnter.length === 0 && (
              <li className="text-xs text-ink-2">{t("navigationPanel.emptyEnterActions")}</li>
            )}
          </ul>

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
            {receivers.map((i) => (
              <option key={i.id} value={i.id}>
                {widgetLabel(items, i.id)}
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
          <div className="flex gap-1">
            <input
              aria-label={t("widgetForm.longitude")}
              placeholder={t("widgetForm.longitude")}
              className="h-8 w-1/2 rounded border border-slate-300 px-1 text-xs"
              value={lon}
              onChange={(e) => setLon(e.target.value)}
            />
            <input
              aria-label={t("widgetForm.latitude")}
              placeholder={t("widgetForm.latitude")}
              className="h-8 w-1/2 rounded border border-slate-300 px-1 text-xs"
              value={lat}
              onChange={(e) => setLat(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100"
            onClick={add}
          >
            {t("navigationPanel.addToChapterButton")}
          </button>
        </>
      )}
    </div>
  );
}
