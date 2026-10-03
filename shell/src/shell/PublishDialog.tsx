// SPDX-License-Identifier: Apache-2.0
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useItemClient } from "../api/ItemClientProvider";
import type { Item } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Dialog } from "../ui/kit/Dialog";
import { t } from "../i18n";
import { useReferencedCollectionIds } from "./referencedCollections";
import { LoadingState } from "../ui/kit/LoadingState";

// j03-012 : publier une carte/app ne publie pas les collections qu'elle lit —
// un anonyme verrait la config mais des données vides. Le dialogue liste les
// collections encore non publiques et propose de les publier avec l'item.
export function PublishDialog({
  item,
  open,
  pending,
  onPublish,
  onCancel,
  returnFocusRef,
}: {
  item: Item;
  open: boolean;
  pending: boolean;
  onPublish: () => void;
  onCancel: () => void;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  const ids = useReferencedCollectionIds(item, open);
  const [failed, setFailed] = useState(false);
  const check = useQuery({
    queryKey: ["publish-check", item.pk, ids],
    enabled: open && ids.length > 0,
    queryFn: async () => {
      const rows = await Promise.all(
        ids.map((id) =>
          client
            .getCollectionSharing(id)
            .then((sharing) => ({ id, sharing }))
            .catch(() => null),
        ),
      );
      return rows.filter((r) => r !== null && !r.sharing.public);
    },
  });
  const privates = check.data ?? [];

  async function publishWithCollections() {
    setFailed(false);
    try {
      await Promise.all(
        privates.map((row) =>
          client.setCollectionSharing(row!.id, { ...row!.sharing, public: true }),
        ),
      );
      void queryClient.invalidateQueries({ queryKey: ["collection-sharing"] });
      onPublish();
    } catch {
      setFailed(true);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !next && onCancel()}
      title={t("publish.title")}
      returnFocusRef={returnFocusRef}
    >
      {check.isLoading && <LoadingState />}
      {privates.length > 0 && (
        <div className="mb-4 text-sm text-ink-2">
          <p>{t("publish.privateCollections")}</p>
          <ul className="list-disc pl-5">
            {privates.map((row) => (
              <li key={row!.id}>{row!.id}</li>
            ))}
          </ul>
        </div>
      )}
      {failed && (
        <p role="alert" className="mb-2 text-sm text-danger">
          {t("publish.collectionsFailed")}
        </p>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          {t("confirmDialog.cancel")}
        </Button>
        <Button
          type="button"
          variant={privates.length > 0 ? "outline" : "default"}
          size="sm"
          disabled={pending || check.isLoading}
          onClick={onPublish}
        >
          {privates.length > 0 ? t("publish.itemOnly") : t("actions.publish")}
        </Button>
        {privates.length > 0 && (
          <Button
            type="button"
            size="sm"
            disabled={pending}
            onClick={() => void publishWithCollections()}
          >
            {t("publish.withCollections")}
          </Button>
        )}
      </div>
    </Dialog>
  );
}
