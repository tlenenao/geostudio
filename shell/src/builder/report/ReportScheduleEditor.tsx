// SPDX-License-Identifier: Apache-2.0
import type { AlertChannel, ReportSchedulePayload } from "../../api/types";
import { t } from "../../i18n";
import { PipelineScheduleEditor } from "../pipeline/PipelineScheduleEditor";
import { NativeSelect } from "../../ui/kit/NativeSelect";
import { Input } from "../../ui/kit/Input";
import "../../i18n/domains/automation";

// Composant contrôlé (reproduit la forme value/onChange de
// PipelineScheduleEditor, pas la forme autonome création-et-réinitialisation
// d'AlertRuleEditor) : ReportEditPage (SP-17b) a besoin à la fois d'un
// cycle de création ET d'édition plus un panneau d'historique des runs à
// côté, donc c'est le parent qui possède la persistance — même raison que
// PipelineBuilderPage possède l'état PipelinePayload au lieu que
// PipelineScheduleEditor le possède.
export function ReportScheduleEditor({
  value,
  onChange,
  bookmarks,
}: {
  value: ReportSchedulePayload;
  onChange: (next: ReportSchedulePayload) => void;
  bookmarks: { pk: string; title: string }[];
}) {
  function setChannel(channel: AlertChannel) {
    onChange({ ...value, channels: [channel] });
  }
  const channel: AlertChannel | undefined = value.channels[0];

  return (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm">
        {t("reportSchedule.targetedViewLabel")}
        <NativeSelect
          required
          value={value.bookmarkItemId}
          onChange={(e) => onChange({ ...value, bookmarkItemId: e.target.value })}
        >
          <option value="">{t("reportSchedule.bookmarkPlaceholder")}</option>
          {/* Un id hors liste (page tronquée, droit retiré) reste affiché plutôt que perdu. */}
          {value.bookmarkItemId && !bookmarks.some((b) => b.pk === value.bookmarkItemId) && (
            <option value={value.bookmarkItemId}>{value.bookmarkItemId}</option>
          )}
          {bookmarks.map((b) => (
            <option key={b.pk} value={b.pk}>
              {b.title}
            </option>
          ))}
        </NativeSelect>
      </label>

      <label className="flex flex-col gap-1 text-sm">
        {t("reportSchedule.channelLabel")}
        <NativeSelect
          value={channel?.kind ?? "webhook"}
          onChange={(e) => {
            if (e.target.value === "webhook") setChannel({ kind: "webhook", url: "" });
            else setChannel({ kind: "email", to: "", smtpSecretName: "" });
          }}
        >
          <option value="webhook">{t("reportSchedule.channelWebhook")}</option>
          <option value="email">{t("reportSchedule.channelEmail")}</option>
        </NativeSelect>
      </label>

      {channel?.kind === "webhook" && (
        <label className="flex flex-col gap-1 text-sm">
          {t("reportSchedule.webhookUrlLabel")}
          <Input
            value={channel.url}
            onChange={(e) => setChannel({ kind: "webhook", url: e.target.value })}
          />
        </label>
      )}

      {channel?.kind === "email" && (
        <>
          <label className="flex flex-col gap-1 text-sm">
            {t("reportSchedule.recipientLabel")}
            <Input
              value={channel.to}
              onChange={(e) =>
                setChannel({
                  kind: "email",
                  to: e.target.value,
                  smtpSecretName: channel.smtpSecretName,
                })
              }
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t("reportSchedule.smtpSecretLabel")}
            <Input
              value={channel.smtpSecretName}
              onChange={(e) =>
                setChannel({ kind: "email", to: channel.to, smtpSecretName: e.target.value })
              }
            />
          </label>
        </>
      )}

      <PipelineScheduleEditor
        value={value.refreshPolicy}
        onChange={(policy) =>
          onChange({ ...value, refreshPolicy: policy ?? { enabled: false, cron: "0 8 * * MON" } })
        }
      />
    </div>
  );
}
