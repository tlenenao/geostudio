// SPDX-License-Identifier: Apache-2.0
import { useAllExtensions, useInstanceInfo, useSetExtensionEnabled } from "../api/hooks";
import { AdminNav } from "../shell/chrome/AdminNav";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

export function AdminExtensionsPage() {
  const extensionsQuery = useAllExtensions();
  const setEnabled = useSetExtensionEnabled();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: <AdminNav />,
        }}
        work={{
          id: "extensions",
          label: t("extensions.title"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">{t("extensions.title")}</h1>
              {extensionsQuery.isLoading && <p role="status">{t("extensions.loading")}</p>}
              {extensionsQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("extensions.loadError")}
                </p>
              )}
              {setEnabled.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("extensions.updateError")}
                </p>
              )}
              {extensionsQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">{t("extensions.columnLabel")}</th>
                      <th className="py-2 text-ink">{t("extensions.columnTag")}</th>
                      <th className="py-2 text-ink">{t("extensions.columnModule")}</th>
                      <th className="py-2 text-ink">{t("extensions.columnActive")}</th>
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
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ),
        }}
        inspect={{ id: "detail", label: t("extensions.detail"), content: null }}
      />
    </div>
  );
}
