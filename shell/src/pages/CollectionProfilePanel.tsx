// SPDX-License-Identifier: Apache-2.0
import { useCollectionProfile } from "../api/domains/datasets.hooks";
import type { CollectionColumnProfile } from "../api/types";
import { t } from "../i18n";
import { formatDateTime, formatNumber } from "../lib/format";
import { Banner } from "../ui/kit/Banner";
import { LoadingState } from "../ui/kit/LoadingState";
import { QueryErrorState } from "../ui/kit/QueryErrorState";

function formatBound(v: number | string | null | undefined): string {
  if (typeof v === "number") return formatNumber(v);
  if (typeof v === "string") return formatDateTime(v);
  return "—";
}

function Histogram({ column }: { column: CollectionColumnProfile }) {
  const bins = column.histogram ?? [];
  const max = Math.max(1, ...bins.map((b) => b.count));
  if (bins.length === 0) return null;
  return (
    <div
      role="img"
      aria-label={t("datasetProfile.histogram", { name: column.name })}
      className="mt-1 flex h-8 items-end gap-px"
    >
      {bins.map((b) => (
        <span
          key={b.bucketIndex}
          className="w-3 bg-accent"
          style={{ height: `${Math.max(4, (b.count / max) * 100)}%` }}
          title={`${formatNumber(b.bucketStart)} – ${formatNumber(b.bucketEnd)} : ${b.count}`}
        />
      ))}
    </div>
  );
}

function Summary({ column }: { column: CollectionColumnProfile }) {
  return (
    <>
      {column.min !== undefined && column.min !== null ? (
        <p>
          {t("datasetProfile.range", {
            min: formatBound(column.min),
            max: formatBound(column.max),
          })}
          {typeof column.median === "number"
            ? ` · ${t("datasetProfile.median", { n: formatNumber(column.median) })}`
            : ""}
        </p>
      ) : null}
      {column.topValues && column.topValues.length > 0 ? (
        <p>{column.topValues.map((v) => `${v.value} (${formatNumber(v.count)})`).join(", ")}</p>
      ) : null}
      <Histogram column={column} />
    </>
  );
}

export function CollectionProfilePanel({ collectionId, id }: { collectionId: string; id: string }) {
  const query = useCollectionProfile(collectionId);
  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data) {
    return (
      <div id={id}>
        <QueryErrorState queries={[query]} notFoundMessage={t("datasetPage.notFound")} />
      </div>
    );
  }
  const p = query.data;
  if (p.pending || p.rowCount === 0) {
    return (
      <div id={id}>
        <Banner variant="info">
          {t(p.pending ? "datasetProfile.pending" : "datasetProfile.empty")}
        </Banner>
      </div>
    );
  }
  return (
    <section id={id} aria-label={t("datasetProfile.title")} className="flex flex-col gap-3">
      <p className="text-xs text-ink-3">
        {t("datasetProfile.rows", { n: formatNumber(p.rowCount) })}
        {p.asOf ? ` · ${t("datasetProfile.asOf", { date: formatDateTime(p.asOf) })}` : ""}
        {p.sampled ? ` · ${t("datasetProfile.sampled")}` : ""}
        {p.truncatedColumns ? ` · ${t("datasetProfile.truncatedColumns")}` : ""}
      </p>
      {p.geometry ? (
        <p className="text-sm text-ink-2">
          {t("datasetProfile.geometry", { column: p.geometry.column })} :{" "}
          {p.geometry.types.map((g) => `${g.type} (${formatNumber(g.count)})`).join(", ")}
          {p.geometry.bbox
            ? ` — ${t("datasetProfile.extent", {
                bbox: p.geometry.bbox.map((v) => formatNumber(v, 4)).join(" ; "),
              })}`
            : ""}
        </p>
      ) : null}
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-ink-3">
          <tr>
            <th scope="col">{t("datasetProfile.colName")}</th>
            <th scope="col">{t("datasetProfile.colType")}</th>
            <th scope="col">{t("datasetProfile.colFill")}</th>
            <th scope="col">{t("datasetProfile.colDistinct")}</th>
            <th scope="col">{t("datasetProfile.colSummary")}</th>
          </tr>
        </thead>
        <tbody>
          {p.columns.map((c) => {
            const total = c.nonNull + c.nulls;
            return (
              <tr key={c.name} className="border-t border-rule align-top">
                <th scope="row" className="py-1 pr-2 font-medium text-ink">
                  {c.name}
                </th>
                <td className="pr-2 text-ink-2">{c.type}</td>
                <td className="pr-2 text-ink-2">
                  {formatNumber(total === 0 ? 0 : (c.nonNull / total) * 100, 0)} %
                </td>
                <td className="pr-2 text-ink-2">
                  {c.distinct === null || c.distinct === undefined ? "—" : formatNumber(c.distinct)}
                </td>
                <td className="py-1 text-ink-2">
                  <Summary column={c} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
