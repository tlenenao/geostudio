// SPDX-License-Identifier: Apache-2.0
// ARC-21 : enregistrements liés d'une entité (maître-détail), lus sous les droits du lecteur.
import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { CollectionRelation, ItemClient, RelatedRecords } from "../../api/types";
import { t } from "../../i18n";
import { LoadingState } from "../../ui/kit/LoadingState";
import "../../i18n/domains/widgets";

function recordLabel(f: RelatedRecords["features"][number]): string {
  const text = Object.values(f.properties).find((v) => typeof v === "string" && v !== "");
  return typeof text === "string" ? text : `#${f.id}`;
}

function RelationSection({
  client,
  collectionId,
  fid,
  relation,
}: {
  client: ItemClient;
  collectionId: string;
  fid: string;
  relation: CollectionRelation;
}) {
  const load = client.listRelatedRecords;
  const query = useQuery({
    queryKey: ["related-records", collectionId, fid, relation.id],
    queryFn: () => load!.call(client, collectionId, fid, relation.id),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <p className="text-danger">{t("relatedRecords.error")}</p>;
  const data = query.data;
  if (!data) return null;
  const count = data.numberMatched ?? data.numberReturned;
  return (
    <section className="flex flex-col gap-1">
      <h4 className="font-medium">
        {t(data.direction === "children" ? "relatedRecords.children" : "relatedRecords.parents", {
          name: relation.name,
          count,
        })}
      </h4>
      {data.features.length === 0 ? (
        <p className="text-ink-3">{t("relatedRecords.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {data.features.map((f) => (
            <li key={String(f.id)} className="rounded border border-rule p-1">
              {recordLabel(f)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function RelatedRecordsPanel({
  client,
  collectionId,
  fid,
}: {
  client: ItemClient;
  collectionId: string;
  fid: string;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const listRelations = client.listCollectionRelations;
  const relations = useQuery({
    queryKey: ["collection-relations", collectionId],
    queryFn: () => listRelations!.call(client, collectionId),
    enabled: listRelations !== undefined && client.listRelatedRecords !== undefined,
  });
  if (!listRelations || !relations.data || relations.data.length === 0) return null;
  return (
    <div className="flex flex-col gap-1 text-xs">
      <button
        type="button"
        className="self-start underline"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        {t("relatedRecords.toggle")}
      </button>
      {open && (
        <div id={panelId} role="region" aria-label={t("relatedRecords.toggle")}>
          {relations.data.map((r) => (
            <RelationSection
              key={r.id}
              client={client}
              collectionId={collectionId}
              fid={fid}
              relation={r}
            />
          ))}
        </div>
      )}
    </div>
  );
}
