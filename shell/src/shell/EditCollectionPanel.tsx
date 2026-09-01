// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useInstanceInfo, useUpdateCollection } from "../api/hooks";
import type { CollectionAdmin } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";

export function EditCollectionPanel({
  collection,
  onClose,
}: {
  collection: CollectionAdmin;
  onClose: () => void;
}) {
  const updateCollection = useUpdateCollection(collection.id);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [title, setTitle] = useState(collection.title);
  const [description, setDescription] = useState(collection.description);
  const [isPublic, setIsPublic] = useState(collection.isPublic);
  const [editable, setEditable] = useState(collection.editable);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateCollection.mutateAsync({ title, description, isPublic, editable });
      onClose();
    } catch {
      // surfaced via updateCollection.isError
    }
  }

  return (
    <section aria-label={`Éditer ${collection.title}`} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">Éditer {collection.title}</h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          Titre
          <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          Description
          <Input
            aria-label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            aria-label="Public"
            checked={isPublic}
            onChange={(e) => setIsPublic(e.target.checked)}
          />
          Public
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            aria-label="Éditable"
            checked={editable}
            onChange={(e) => setEditable(e.target.checked)}
          />
          Éditable
        </label>
        {updateCollection.isError && (
          <p role="alert" className="text-sm text-danger">
            Échec de la mise à jour.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={updateCollection.isPending || readOnly}>
            Enregistrer
          </Button>
        </div>
      </form>
    </section>
  );
}
