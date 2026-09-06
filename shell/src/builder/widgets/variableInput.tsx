// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";
import { useVariableDefs, useVariables, useSetVariable } from "../VariablesContext";
import type { Variable } from "../../api/types";
import { t } from "../../i18n";

type Props = { variableId: string; label: string };

function controlFor(
  variable: Variable,
  value: unknown,
  onChange: (v: unknown) => void,
  disabled: boolean,
) {
  const type = variable.type ?? "string";
  if (type === "number") {
    return (
      <input
        aria-label={variable.name}
        type="number"
        disabled={disabled}
        value={Number(value ?? 0)}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    );
  }
  if (type === "bool") {
    return (
      <input
        aria-label={variable.name}
        type="checkbox"
        disabled={disabled}
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  if (type === "date") {
    return (
      <input
        aria-label={variable.name}
        type="date"
        disabled={disabled}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <input
      aria-label={variable.name}
      type="text"
      disabled={disabled}
      value={String(value ?? "")}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function registerVariableInputWidget(): void {
  registerWidget({
    type: "variableInput",
    label: t("widgetVariableInput.paletteLabel"),
    defaultProps: { variableId: "", label: "" } satisfies Props,
    defaultSize: { w: 3, h: 2 },
    configSchema: [
      {
        name: "variableId",
        type: "string",
        label: t("widgetVariableInput.variableConfig"),
        default: "",
      },
      { name: "label", type: "string", label: t("widgetVariableInput.labelConfig"), default: "" },
    ],
    PropsPanel: ({ props, onChange, variables = [] }) => {
      const { variableId, label } = props as Props;
      return (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex flex-col gap-1">
            {t("widgetVariableInput.variableConfig")}
            <select
              aria-label={t("widgetVariableInput.variableAria")}
              className="h-9 rounded-md border border-slate-300 px-2"
              value={variableId}
              onChange={(e) => onChange({ variableId: e.target.value, label })}
            >
              <option value="">{t("widgetVariableInput.chooseVariable")}</option>
              {variables
                .filter((v) => (v.type ?? "string") !== "record" && (v.type ?? "string") !== "list")
                .map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            {t("widgetVariableInput.labelConfig")}
            <input
              aria-label={t("widgetVariableInput.labelAria")}
              className="h-9 rounded-md border border-slate-300 px-2"
              value={label}
              onChange={(e) => onChange({ variableId, label: e.target.value })}
            />
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const { variableId, label } = props as Props;
      const defs = useVariableDefs();
      const values = useVariables();
      const setVariable = useSetVariable();
      const variable = defs.find((v) => v.id === variableId);
      if (!variable) {
        return <p className="text-xs text-slate-400">{t("widgetVariableInput.notFound")}</p>;
      }
      const disabled = ctx.mode === "edit";
      return (
        <label className="flex flex-col gap-1 text-sm">
          {label || variable.name}
          {controlFor(
            variable,
            values[variable.name],
            (v) => setVariable(variable.name, v),
            disabled,
          )}
        </label>
      );
    },
  });
}
