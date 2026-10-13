// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useItemClient, useMe } from "../api/hooks";
import { ApiError } from "../api/ApiError";
import type { XlsFormImportResult } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Drawer } from "../ui/kit/Drawer";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";
import { t } from "../i18n";
import "../i18n/domains/admin";

// ARC-27 : importe un XLSForm (.xlsx) -> collection + App de collecte mobile, et affiche le
// rapport des éléments non portés (jamais de perte silencieuse).
export function XlsFormImportButton() {
  const client = useItemClient();
  const privileges = useMe().data?.privileges;
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<XlsFormImportResult | null>(null);
  const panel = usePanelTrigger(open);

  if (!client.importXlsForm) return null;
  if (privileges !== undefined && !privileges.includes("data.manage")) return null;
  const importXlsForm = client.importXlsForm.bind(client);

  async function submit(file: File) {
    setBusy(true);
    setError(null);
    try {
      setResult(await importXlsForm(file));
      void queryClient.invalidateQueries({ queryKey: ["items"] });
    } catch (e) {
      setError(
        e instanceof ApiError && e.detail
          ? `${t("xlsform.importError")} ${e.detail}`
          : t("xlsform.importError"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button size="sm" variant="outline" {...panel.triggerProps} onClick={() => setOpen(true)}>
        {t("xlsform.button")}
      </Button>
      <Drawer
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            setResult(null);
            setError(null);
          }
        }}
        title={t("xlsform.title")}
        id={panel.panelId}
      >
        <div className="flex flex-col gap-3 text-sm">
          <p className="text-ink-2">{t("xlsform.help")}</p>
          <input
            type="file"
            accept=".xlsx"
            aria-label={t("xlsform.fileLabel")}
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void submit(f);
            }}
          />
          {busy && <p role="status">{t("xlsform.importing")}</p>}
          {error && (
            <p role="alert" className="text-danger">
              {error}
            </p>
          )}
          {result && (
            <div className="flex flex-col gap-2">
              <p role="status">{t("xlsform.done", { title: result.title })}</p>
              <Link className="text-accent underline" to={`/apps/${result.itemId}/edit`}>
                {t("xlsform.openApp")}
              </Link>
              <h3 className="font-medium">{t("xlsform.reportTitle")}</h3>
              {result.report.length === 0 ? (
                <p className="text-ink-2">{t("xlsform.reportEmpty")}</p>
              ) : (
                <ul className="flex list-disc flex-col gap-1 pl-4">
                  {result.report.map((r, i) => (
                    <li key={i}>
                      {r.row !== null ? `${t("xlsform.row", { row: r.row })} : ` : ""}
                      {r.message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </Drawer>
    </>
  );
}
