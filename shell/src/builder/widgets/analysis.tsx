// SPDX-License-Identifier: Apache-2.0
// ARC-25 : widget « Analyse » — exécute un outil d'analyse spatiale (op de pipeline) sur une
// collection via POST /v1/collections/{id}/analysis (mêmes portes que /aggregate : droits,
// champs masqués, limites géographiques). Résultat éphémère en lecture, ou collection créée.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { useItemClient } from "../../api/ItemClientProvider";
import type { AnalysisResult, AnalysisTool } from "../../api/types";
import { Button } from "../../ui/kit/Button";
import { Input } from "../../ui/kit/Input";
import { NativeSelect } from "../../ui/kit/NativeSelect";
import { Field } from "../../ui/kit/Field";
import { t } from "../../i18n";
import "../../i18n/domains/widgets";

type ParamSpec = NonNullable<AnalysisTool["paramsSchema"]["properties"]>[string];

function paramType(spec: ParamSpec): string {
  if (spec.type) return spec.type;
  return spec.anyOf?.find((a) => a.type && a.type !== "null")?.type ?? "string";
}

// Convertit la saisie texte d'un paramètre vers la valeur typée attendue par le schéma.
function coerce(spec: ParamSpec, raw: string): unknown {
  const type = paramType(spec);
  if (type === "number" || type === "integer") return raw === "" ? undefined : Number(raw);
  if (type === "boolean") return raw === "true";
  if (type === "array")
    return raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  return raw === "" ? undefined : raw;
}

function AnalysisPanel() {
  const client = useItemClient();
  const tools = useQuery({
    queryKey: ["analysis-tools"],
    queryFn: () => client.listAnalysisTools(),
  });
  const collections = useQuery({
    queryKey: ["analysis-collections"],
    queryFn: () => client.listCollections({ limit: 200 }),
  });
  const [toolName, setToolName] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [otherId, setOtherId] = useState("");
  const [raw, setRaw] = useState<Record<string, string>>({});
  const [title, setTitle] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const tool = tools.data?.find((x) => x.name === toolName);
  const props = tool?.paramsSchema.properties ?? {};
  const required = new Set(tool?.paramsSchema.required ?? []);
  const ready =
    Boolean(tool && sourceId) && (!tool?.needsOtherCollection || Boolean(otherId)) && !busy;

  async function run(output: "ephemeral" | "collection") {
    if (!tool) return;
    const params: Record<string, unknown> = {};
    for (const [name, spec] of Object.entries(props)) {
      const v = coerce(spec, raw[name] ?? "");
      if (v !== undefined) params[name] = v;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(
        await client.runAnalysis(sourceId, {
          tool: tool.name,
          params,
          otherCollectionId: tool.needsOtherCollection ? otherId : undefined,
          output,
          title: output === "collection" ? title.trim() : undefined,
        }),
      );
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : t("widgetAnalysis.failed"));
    } finally {
      setBusy(false);
    }
  }

  const collectionOptions = (collections.data ?? []).map((c) => (
    <option key={c.id} value={c.id}>
      {c.title}
    </option>
  ));

  return (
    <form
      className="flex flex-col gap-2 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        void run("ephemeral");
      }}
    >
      <Field label={t("widgetAnalysis.tool")} htmlFor="analysis-tool" hint={tool?.help}>
        <NativeSelect
          id="analysis-tool"
          value={toolName}
          onChange={(e) => {
            setToolName(e.target.value);
            setRaw({});
            setResult(null);
          }}
        >
          <option value="">{t("widgetAnalysis.choose")}</option>
          {(tools.data ?? []).map((x) => (
            <option key={x.name} value={x.name}>
              {x.label}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <Field label={t("widgetAnalysis.source")} htmlFor="analysis-source">
        <NativeSelect
          id="analysis-source"
          value={sourceId}
          onChange={(e) => setSourceId(e.target.value)}
        >
          <option value="">{t("widgetAnalysis.choose")}</option>
          {collectionOptions}
        </NativeSelect>
      </Field>
      {tool?.needsOtherCollection && (
        <Field label={t("widgetAnalysis.other")} htmlFor="analysis-other">
          <NativeSelect
            id="analysis-other"
            value={otherId}
            onChange={(e) => setOtherId(e.target.value)}
          >
            <option value="">{t("widgetAnalysis.choose")}</option>
            {collectionOptions}
          </NativeSelect>
        </Field>
      )}
      {Object.entries(props).map(([name, spec]) => {
        const id = `analysis-param-${name}`;
        const label = `${spec.title ?? name}${required.has(name) ? " *" : ""}`;
        const type = paramType(spec);
        return (
          <Field key={name} label={label} htmlFor={id} hint={spec.description}>
            {spec.enum || type === "boolean" ? (
              <NativeSelect
                id={id}
                value={raw[name] ?? ""}
                onChange={(e) => setRaw({ ...raw, [name]: e.target.value })}
              >
                <option value="">{t("widgetAnalysis.default")}</option>
                {(spec.enum ?? ["true", "false"]).map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </NativeSelect>
            ) : (
              <Input
                id={id}
                type={type === "number" || type === "integer" ? "number" : "text"}
                value={raw[name] ?? ""}
                onChange={(e) => setRaw({ ...raw, [name]: e.target.value })}
              />
            )}
          </Field>
        );
      })}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={!ready}>
          {t("widgetAnalysis.run")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
      {result?.output === "ephemeral" && (
        <div role="status" className="flex flex-col gap-2">
          <p>
            {t("widgetAnalysis.resultCount", {
              count: String(result.featureCollection?.features.length ?? 0),
            })}
            {result.truncated ? ` ${t("widgetAnalysis.truncated")}` : ""}
          </p>
          <div className="flex items-end gap-2">
            <Field label={t("widgetAnalysis.saveTitle")} htmlFor="analysis-title">
              <Input id="analysis-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!ready || title.trim() === ""}
              onClick={() => void run("collection")}
            >
              {t("widgetAnalysis.save")}
            </Button>
          </div>
        </div>
      )}
      {result?.output === "collection" && (
        <p role="status">{t("widgetAnalysis.saved", { count: String(result.rowCount ?? 0) })}</p>
      )}
    </form>
  );
}

export function registerAnalysisWidget(): void {
  registerWidget({
    type: "analysis",
    label: t("widgetAnalysis.paletteLabel"),
    defaultProps: {},
    defaultSize: { w: 6, h: 6 },
    events: [],
    actions: [],
    configSchema: [],
    PropsPanel: () => <p className="text-xs">{t("widgetAnalysis.propsHint")}</p>,
    Component: ({ ctx }) =>
      // En édition, aucun appel réseau : simple repère visuel.
      ctx.mode === "edit" ? (
        <p className="text-sm text-[var(--gs-color-text)]">{t("widgetAnalysis.editHint")}</p>
      ) : (
        <AnalysisPanel />
      ),
  });
}
