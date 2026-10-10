// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense } from "react";
import { HelpCircle } from "lucide-react";
import type { DataSource, Theme, Variable, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { validateExpression } from "./expr";
import { formatCelError } from "./celError";
import { IconButton } from "../ui/kit/IconButton";
import { Popover } from "../ui/kit/Popover";
import { t } from "../i18n";

// REV-183 : lazy — n'alourdit pas la charge initiale (marge de bundle).
const VisibleWhenGenerator = lazy(() =>
  import("./copilot/VisibleWhenGenerator").then((m) => ({ default: m.VisibleWhenGenerator })),
);

export function PropsPanel({
  item,
  dataSources,
  theme,
  variables,
  onChange,
  onVisibleWhenChange,
  generateItemId,
}: {
  item: WidgetItem | null;
  dataSources: DataSource[];
  theme?: Theme;
  variables?: Variable[];
  onChange: (props: Record<string, unknown>) => void;
  onVisibleWhenChange: (expr: string) => void;
  // REV-183 : id de l'item à passer au copilote ; absent = pas de bouton Générer
  // (copilote désactivé, lecture seule, ou éditeur sans item).
  generateItemId?: string;
}) {
  if (!item) {
    return <p className="text-xs text-ink-2">{t("propsPanel.noWidgetSelected")}</p>;
  }
  const def = getWidget(item.widget);
  if (!def) {
    return (
      <p className="text-xs text-ink-2">{t("propsPanel.unknownWidget", { widget: item.widget })}</p>
    );
  }
  const Panel = def.PropsPanel;
  const visibleWhen = item.visibleWhen ?? "";
  const error = visibleWhen ? validateExpression(visibleWhen) : null;
  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1">
          {t("propsPanel.visibleWhenLabel")}
          <Popover
            aria-label={t("propsPanel.visibleWhenHelpAria")}
            trigger={
              <IconButton
                icon={<HelpCircle size={14} />}
                aria-label={t("propsPanel.visibleWhenHelpAria")}
                size="sm"
              />
            }
          >
            {t("propsPanel.visibleWhenHelpBody")}
          </Popover>
        </span>
        {/* eslint-disable-next-line geostudio/label-no-aria-label -- le label englobe un bouton d'aide et une alerte : le nom accessible doit les exclure */}
        <textarea
          aria-label={t("propsPanel.visibleWhenAria")}
          className="rounded-md border border-rule p-2 font-mono text-xs"
          value={visibleWhen}
          onChange={(e) => onVisibleWhenChange(e.target.value)}
        />
        {error && (
          <span role="alert" className="whitespace-pre-line text-xs text-danger">
            {formatCelError(error)}
          </span>
        )}
      </label>
      {generateItemId && (
        <Suspense fallback={null}>
          <VisibleWhenGenerator
            itemId={generateItemId}
            availableFields={[...(variables ?? []).map((v) => `vars.${v.name}`), "user.name"]}
            current={visibleWhen}
            onApply={onVisibleWhenChange}
          />
        </Suspense>
      )}
      <Panel
        props={item.props}
        dataSources={dataSources}
        theme={theme}
        variables={variables ?? []}
        generateItemId={generateItemId}
        onChange={(p) => onChange(p)}
      />
    </div>
  );
}
