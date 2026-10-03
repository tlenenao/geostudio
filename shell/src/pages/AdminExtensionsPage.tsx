// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import {
  useAllExtensions,
  useCreateExtension,
  useDeleteExtension,
  useInstanceInfo,
  useSetExtensionEnabled,
} from "../api/hooks";
import type { AdminExtension } from "../api/types";
import { SettingsNav } from "../shell/chrome/SettingsNav";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";
import { Banner } from "../ui/kit/Banner";
import { Button } from "../ui/kit/Button";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { EmptyState } from "../ui/kit/EmptyState";
import { Input } from "../ui/kit/Input";
import { LoadingState } from "../ui/kit/LoadingState";
import { PageTitle } from "../ui/kit/PageTitle";

function RegisterForm({ disabled }: { disabled: boolean }) {
  const create = useCreateExtension();
  const [form, setForm] = useState({ id: "", tag: "", label: "", moduleUrl: "" });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });
  const valid = Object.values(form).every((v) => v.trim() !== "");
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate(
          { ...form, defaultSize: { w: 2, h: 2 } },
          { onSuccess: () => setForm({ id: "", tag: "", label: "", moduleUrl: "" }) },
        );
      }}
    >
      <h2 className="text-base font-semibold text-ink">{t("extensions.registerTitle")}</h2>
      {(["id", "tag", "label", "moduleUrl"] as const).map((k) => (
        <label key={k} className="flex flex-col gap-1 text-sm text-ink">
          {t(`extensions.field${k[0].toUpperCase()}${k.slice(1)}` as "extensions.fieldId")}
          <Input value={form[k]} onChange={set(k)} disabled={disabled} />
        </label>
      ))}
      {create.isError && (
        <p role="alert" className="text-sm text-danger">
          {t("extensions.registerError")}
        </p>
      )}
      <Button type="submit" size="sm" disabled={!valid || disabled || create.isPending}>
        {t("extensions.registerButton")}
      </Button>
    </form>
  );
}

export function AdminExtensionsPage() {
  const extensionsQuery = useAllExtensions();
  const setEnabled = useSetExtensionEnabled();
  const deleteExt = useDeleteExtension();
  const [toDelete, setToDelete] = useState<AdminExtension | null>(null);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: <SettingsNav />,
        }}
        work={{
          id: "extensions",
          label: t("extensions.title"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <PageTitle>{t("extensions.title")}</PageTitle>
              {extensionsQuery.isLoading && <LoadingState />}
              {extensionsQuery.isError && (
                <Banner variant="danger" onRetry={() => void extensionsQuery.refetch()}>
                  {t("extensions.loadError")}
                </Banner>
              )}
              {setEnabled.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("extensions.updateError")}
                </p>
              )}
              {deleteExt.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("extensions.deleteError")}
                </p>
              )}
              {extensionsQuery.data && extensionsQuery.data.length === 0 && (
                <EmptyState
                  title={t("extensions.emptyTitle")}
                  description={t("extensions.emptyDescription")}
                />
              )}
              {extensionsQuery.data && extensionsQuery.data.length > 0 && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">{t("extensions.columnLabel")}</th>
                      <th className="py-2 text-ink">{t("extensions.columnTag")}</th>
                      <th className="py-2 text-ink">{t("extensions.columnModule")}</th>
                      <th className="py-2 text-ink">{t("extensions.columnActive")}</th>
                      <th className="py-2 text-ink">{t("extensions.columnActions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {extensionsQuery.data.map((ext) => (
                      <tr key={ext.type} className="border-b border-rule-2">
                        <td className="py-2 text-ink">{ext.label}</td>
                        <td className="py-2 text-ink">{ext.tag}</td>
                        <td className="py-2 text-xs text-ink-2">{ext.moduleUrl}</td>
                        <td className="py-2">
                          <input
                            type="checkbox"
                            aria-label={t("extensions.activeAria", { label: ext.label })}
                            checked={ext.enabled}
                            disabled={setEnabled.isPending || readOnly}
                            onChange={(e) =>
                              setEnabled.mutate({ id: ext.type, enabled: e.target.checked })
                            }
                          />
                        </td>
                        <td className="py-2">
                          <Button
                            size="sm"
                            variant="outline"
                            aria-label={t("extensions.deleteAria", { label: ext.label })}
                            disabled={readOnly}
                            onClick={() => setToDelete(ext)}
                          >
                            {t("extensions.deleteButton")}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <RegisterForm disabled={readOnly} />
              <ConfirmDialog
                open={toDelete !== null}
                title={t("extensions.deleteTitle")}
                message={toDelete ? t("extensions.deleteMessage", { label: toDelete.label }) : ""}
                confirmLabel={t("extensions.deleteButton")}
                pending={deleteExt.isPending}
                onCancel={() => setToDelete(null)}
                onConfirm={() => {
                  if (toDelete)
                    deleteExt.mutate(toDelete.type, { onSettled: () => setToDelete(null) });
                }}
              />
            </div>
          ),
        }}
        inspect={{ id: "detail", label: t("extensions.detail"), content: null }}
      />
    </div>
  );
}
