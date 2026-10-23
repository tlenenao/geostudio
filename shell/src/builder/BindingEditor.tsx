// SPDX-License-Identifier: Apache-2.0
// REV-183 : liaison dynamique { $expr } d'une propriété de widget, avec le
// générateur CEL (surface "binding"). Le brouillon n'entre dans la config que
// sur « Lier la propriété ».
import { lazy, Suspense, useState } from "react";
import type { Variable } from "../api/types";
import { Button } from "../ui/kit/Button";
import { t } from "../i18n";
import { formatCelError } from "./celError";
import { validateExpression } from "./expr";
import "../i18n/domains/widgets";
import { NativeSelect } from "../ui/kit/NativeSelect";

const CelGenerator = lazy(() =>
  import("./copilot/VisibleWhenGenerator").then((m) => ({ default: m.CelGenerator })),
);

const exprOf = (v: unknown) =>
  typeof v === "object" && v !== null && "$expr" in v
    ? String((v as { $expr: unknown }).$expr)
    : "";

export function BindingEditor({
  props,
  variables,
  generateItemId,
  onChange,
}: {
  props: Record<string, unknown>;
  variables: Variable[];
  generateItemId?: string;
  onChange: (props: Record<string, unknown>) => void;
}) {
  // Propriétés scalaires ou déjà liées ; les objets/tableaux se lient en JSON avancé.
  const keys = Object.keys(props).filter((k) => {
    const v = props[k];
    return exprOf(v) !== "" || (typeof v !== "object" && typeof v !== "function");
  });
  const [key, setKey] = useState("");
  const [expr, setExpr] = useState<string | null>(null);
  if (keys.length === 0) return null;
  const selected = keys.includes(key) ? key : keys[0];
  const bound = exprOf(props[selected]);
  const value = expr ?? bound;
  const error = value ? validateExpression(value) : null;
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-xs text-ink-2">{t("bindingEditor.summary")}</summary>
      <div className="mt-2 flex flex-col gap-2">
        <NativeSelect
          aria-label={t("bindingEditor.propAria")}
          className="h-9 rounded border border-rule bg-surface text-xs w-auto"
          value={selected}
          onChange={(e) => {
            setKey(e.target.value);
            setExpr(null);
          }}
        >
          {keys.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </NativeSelect>
        <textarea
          aria-label={t("bindingEditor.exprAria")}
          className="rounded-md border border-rule p-2 font-mono text-xs"
          value={value}
          onChange={(e) => setExpr(e.target.value)}
        />
        {error && (
          <span role="alert" className="whitespace-pre-line text-xs text-danger">
            {formatCelError(error)}
          </span>
        )}
        <div className="flex gap-2">
          <Button
            size="sm"
            className="w-fit"
            disabled={!value.trim() || error !== null}
            onClick={() => {
              onChange({ ...props, [selected]: { $expr: value } });
              setExpr(null);
            }}
          >
            {t("bindingEditor.bind")}
          </Button>
          {bound && (
            <Button
              size="sm"
              variant="outline"
              className="w-fit"
              onClick={() => {
                onChange({ ...props, [selected]: "" });
                setExpr(null);
              }}
            >
              {t("bindingEditor.unbind")}
            </Button>
          )}
        </div>
        {generateItemId && (
          <Suspense fallback={null}>
            <CelGenerator
              itemId={generateItemId}
              context="binding"
              availableFields={[...variables.map((v) => `vars.${v.name}`), "user.name"]}
              current={value}
              onApply={setExpr}
            />
          </Suspense>
        )}
      </div>
    </details>
  );
}
