// SPDX-License-Identifier: Apache-2.0
import { HelpCircle } from "lucide-react";
import type { DataSource, Theme, Variable, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { validateExpression } from "./expr";
import { formatCelError } from "./celError";
import { IconButton } from "../ui/kit/IconButton";
import { Popover } from "../ui/kit/Popover";
import { t } from "../i18n";

export function PropsPanel({
  item,
  dataSources,
  theme,
  variables,
  onChange,
  onVisibleWhenChange,
}: {
  item: WidgetItem | null;
  dataSources: DataSource[];
  theme?: Theme;
  variables?: Variable[];
  onChange: (props: Record<string, unknown>) => void;
  onVisibleWhenChange: (expr: string) => void;
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
      <Panel
        props={item.props}
        dataSources={dataSources}
        theme={theme}
        variables={variables ?? []}
        onChange={(p) => onChange(p)}
      />
    </div>
  );
}
