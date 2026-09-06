// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCandidateTables, useCreateCollection, useInstanceInfo } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { t } from "../i18n";

export function RegisterCollectionPanel({ onClose }: { onClose: () => void }) {
  const candidatesQuery = useCandidateTables();
  const createCollection = useCreateCollection();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [tableName, setTableName] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [isPublic, setIsPublic] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!tableName) return;
    try {
      await createCollection.mutateAsync({
        tableName,
        title: title.trim() || undefined,
        description: description.trim() || undefined,
        isPublic,
      });
      onClose();
    } catch {
      // surfaced via createCollection.isError
    }
  }

  return (
    <section aria-label={t("registerCollection.title")} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">{t("registerCollection.title")}</h2>
      {candidatesQuery.isLoading && <p role="status">{t("common.loading")}</p>}
      {candidatesQuery.isError && (
        <p role="alert" className="text-sm text-danger">
          {t("registerCollection.candidatesLoadFailed")}
        </p>
      )}
      {candidatesQuery.data && candidatesQuery.data.length === 0 && (
        <p className="text-sm text-ink-2">{t("registerCollection.noCandidates")}</p>
      )}
      {candidatesQuery.data && candidatesQuery.data.length > 0 && (
        <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm text-ink">
            {t("registerCollection.tableLabel")}
            <select
              aria-label={t("registerCollection.tableLabel")}
              className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
              value={tableName}
              onChange={(e) => setTableName(e.target.value)}
            >
              <option value="" />
              {candidatesQuery.data.map((c) => (
                <option key={c.tableName} value={c.tableName} disabled={!c.registrable}>
                  {c.registrable ? c.tableName : `${c.tableName} (${c.reason})`}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink">
            {t("collectionsAdmin.columnTitle")}
            <Input
              aria-label={t("collectionsAdmin.columnTitle")}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink">
            {t("kitGallery.descriptionFieldLabel")}
            <Input
              aria-label={t("kitGallery.descriptionFieldLabel")}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              aria-label={t("collectionsAdmin.columnPublic")}
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            {t("collectionsAdmin.columnPublic")}
          </label>
          {createCollection.isError && (
            <p role="alert" className="text-sm text-danger">
              {t("registerCollection.registerFailed")}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              {t("confirmDialog.cancel")}
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={!tableName || createCollection.isPending || readOnly}
            >
              {t("common.save")}
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
