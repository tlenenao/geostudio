// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useInstanceInfo, useUpdateCollection } from "../api/hooks";
import type { CollectionAdmin } from "../api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { Input } from "../ui/input";

export function EditCollectionDialog({
  collection,
  open,
  onClose,
}: {
  collection: CollectionAdmin;
  open: boolean;
  onClose: () => void;
}) {
  const updateCollection = useUpdateCollection(collection.id);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [title, setTitle] = useState(collection.title);
  const [description, setDescription] = useState(collection.description);
  const [isPublic, setIsPublic] = useState(collection.isPublic);
  const [editable, setEditable] = useState(collection.editable);

  useEffect(() => {
    if (!open) return;
    setTitle(collection.title);
    setDescription(collection.description);
    setIsPublic(collection.isPublic);
    setEditable(collection.editable);
    updateCollection.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, collection]);

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
    <Dialog open={open} onClose={onClose} title={`Éditer ${collection.title}`}>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Titre
          <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Description
          <Input
            aria-label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            aria-label="Public"
            checked={isPublic}
            onChange={(e) => setIsPublic(e.target.checked)}
          />
          Public
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            aria-label="Éditable"
            checked={editable}
            onChange={(e) => setEditable(e.target.checked)}
          />
          Éditable
        </label>
        {updateCollection.isError && (
          <p role="alert" className="text-sm text-red-600">
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
    </Dialog>
  );
}
