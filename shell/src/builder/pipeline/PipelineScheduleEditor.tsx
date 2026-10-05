// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useState } from "react";
import { usePipelineNextRun } from "../../api/hooks";
import type { PipelineRefreshPolicy } from "../../api/types";
import { t } from "../../i18n";

export type ScheduleForm =
  | { mode: "interval"; minutes: string }
  | { mode: "daily"; time: string }
  | { mode: "weekly"; day: string; time: string }
  | { mode: "advanced"; raw: string };

function dayLabels(): string[] {
  return [
    t("pipelineSchedule.daySunday"),
    t("pipelineSchedule.dayMonday"),
    t("pipelineSchedule.dayTuesday"),
    t("pipelineSchedule.dayWednesday"),
    t("pipelineSchedule.dayThursday"),
    t("pipelineSchedule.dayFriday"),
    t("pipelineSchedule.daySaturday"),
  ];
}
const ADVANCED_CRON_RE = /^\S+\s+\S+\s+\S+\s+\S+\s+\S+$/;
const INTERVAL_RE = /^\*\/(\d+) \* \* \* \*$/;
const DAILY_RE = /^(\d{1,2}) (\d{1,2}) \* \* \*$/;
const WEEKLY_RE = /^(\d{1,2}) (\d{1,2}) \* \* (\d)$/;

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

// Presets généré/reconnus par interpolation/regex simple — aucune librairie
// cron JS ajoutée (design SP-15h §5). Un cron qui ne matche aucun des 3
// presets ouvre en mode "avancé" avec la valeur brute intacte, sans perte,
// y compris pour un cron écrit à la main via MCP/REST.
export function parseCron(cron: string): ScheduleForm {
  const interval = cron.match(INTERVAL_RE);
  if (interval) return { mode: "interval", minutes: interval[1] };
  const weekly = cron.match(WEEKLY_RE);
  if (weekly) {
    return {
      mode: "weekly",
      day: weekly[3],
      time: `${pad(Number(weekly[2]))}:${pad(Number(weekly[1]))}`,
    };
  }
  const daily = cron.match(DAILY_RE);
  if (daily) return { mode: "daily", time: `${pad(Number(daily[2]))}:${pad(Number(daily[1]))}` };
  return { mode: "advanced", raw: cron };
}

function splitTime(time: string): [string, string] {
  const [h, m] = time.split(":");
  return [String(parseInt(h, 10) || 0), String(parseInt(m, 10) || 0)];
}

export function compileCron(form: ScheduleForm): string {
  switch (form.mode) {
    case "interval": {
      const n = Math.max(1, parseInt(form.minutes, 10) || 1);
      return `*/${n} * * * *`;
    }
    case "daily": {
      const [h, m] = splitTime(form.time);
      return `${m} ${h} * * *`;
    }
    case "weekly": {
      const [h, m] = splitTime(form.time);
      return `${m} ${h} * * ${form.day}`;
    }
    case "advanced":
      return form.raw;
  }
}

export function PipelineScheduleEditor({
  value,
  onChange,
  readOnly = false,
}: {
  value: PipelineRefreshPolicy | null;
  onChange: (next: PipelineRefreshPolicy | null) => void;
  // Revue finale Vague C (point 2, D55) : sans ce prop, la planification
  // restait entièrement éditable pour un utilisateur en lecture seule —
  // PipelineBuilderPage.tsx garde déjà son propre `setRefreshPolicy`
  // (seconde ligne de défense), mais les contrôles eux-mêmes doivent aussi
  // refléter l'état verrouillé.
  readOnly?: boolean;
}) {
  const enabled = value?.enabled ?? false;
  const cron = value?.cron ?? "*/15 * * * *";
  const [form, setForm] = useState<ScheduleForm>(() => parseCron(cron));
  const nextRunQuery = usePipelineNextRun(cron, enabled);
  const cronErrorId = useId();

  useEffect(() => {
    setForm(parseCron(cron));
  }, [cron]);

  function setEnabled(next: boolean) {
    if (readOnly) return;
    onChange({ enabled: next, cron });
  }
  function handleSetForm(next: ScheduleForm) {
    if (readOnly) return;
    setForm(next);
    onChange({ enabled, cron: compileCron(next) });
  }

  return (
    <div className="flex flex-col gap-2 border-t border-rule pt-2">
      <label className="flex items-center gap-2 text-xs font-medium text-ink-2">
        <input
          type="checkbox"
          className="h-6 w-6"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          disabled={readOnly}
        />
        {t("pipelineSchedule.autoSchedulingLabel")}
      </label>
      {enabled && (
        <div className="flex flex-col gap-2 text-xs">
          <label className="flex flex-col gap-1">
            {t("pipelineSchedule.modeAria")}
            <select
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={form.mode}
              onChange={(e) => {
                const mode = e.target.value as ScheduleForm["mode"];
                if (mode === "interval") handleSetForm({ mode: "interval", minutes: "15" });
                else if (mode === "daily") handleSetForm({ mode: "daily", time: "02:00" });
                else if (mode === "weekly")
                  handleSetForm({ mode: "weekly", day: "1", time: "02:00" });
                else handleSetForm({ mode: "advanced", raw: cron });
              }}
              disabled={readOnly}
            >
              <option value="interval">{t("pipelineSchedule.modeInterval")}</option>
              <option value="daily">{t("pipelineSchedule.modeDaily")}</option>
              <option value="weekly">{t("pipelineSchedule.modeWeekly")}</option>
              <option value="advanced">{t("pipelineSchedule.modeAdvanced")}</option>
            </select>
          </label>
          {enabled && nextRunQuery.data && (
            <p className="text-xs text-ink-2">
              {t("pipelineSchedule.nextRun", {
                when: new Date(nextRunQuery.data.nextRun).toLocaleString("fr-FR"),
              })}
            </p>
          )}
          {form.mode === "interval" && (
            <label className="flex flex-col gap-1">
              {t("pipelineSchedule.intervalLabel")}
              <input
                type="number"
                min={1}
                className="h-8 rounded border border-control bg-surface px-2 text-ink"
                value={form.minutes}
                onChange={(e) => handleSetForm({ mode: "interval", minutes: e.target.value })}
                disabled={readOnly}
              />
            </label>
          )}
          {form.mode === "daily" && (
            <label className="flex flex-col gap-1">
              {t("pipelineSchedule.executionTimeLabel")}
              <input
                type="time"
                className="h-8 rounded border border-control bg-surface px-2 text-ink"
                value={form.time}
                onChange={(e) => handleSetForm({ mode: "daily", time: e.target.value })}
                disabled={readOnly}
              />
            </label>
          )}
          {form.mode === "weekly" && (
            <>
              <label className="flex flex-col gap-1">
                {t("pipelineSchedule.dayAria")}
                <select
                  className="h-8 rounded border border-control bg-surface px-2 text-ink"
                  value={form.day}
                  onChange={(e) =>
                    handleSetForm({ mode: "weekly", day: e.target.value, time: form.time })
                  }
                  disabled={readOnly}
                >
                  {dayLabels().map((label, i) => (
                    <option key={label} value={i}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                {t("pipelineSchedule.executionTimeLabel")}
                <input
                  type="time"
                  className="h-8 rounded border border-control bg-surface px-2 text-ink"
                  value={form.time}
                  onChange={(e) =>
                    handleSetForm({ mode: "weekly", day: form.day, time: e.target.value })
                  }
                  disabled={readOnly}
                />
              </label>
            </>
          )}
          {form.mode === "advanced" && (
            <label className="flex flex-col gap-1">
              {t("pipelineSchedule.cronExpressionLabel")}
              <input
                aria-invalid={!ADVANCED_CRON_RE.test(form.raw)}
                aria-describedby={!ADVANCED_CRON_RE.test(form.raw) ? `${cronErrorId}` : undefined}
                className="h-8 rounded border border-control bg-surface px-2 font-mono text-ink"
                value={form.raw}
                onChange={(e) => handleSetForm({ mode: "advanced", raw: e.target.value })}
                disabled={readOnly}
              />
              {!ADVANCED_CRON_RE.test(form.raw) && (
                <p id={cronErrorId} role="alert" className="text-danger">
                  {t("pipelineSchedule.invalidCronFormat")}
                </p>
              )}
            </label>
          )}
        </div>
      )}
    </div>
  );
}
