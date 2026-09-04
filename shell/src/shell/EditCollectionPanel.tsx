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
  const [attachmentFields, setAttachmentFields] = useState(collection.attachmentFields ?? []);
  const [draftKey, setDraftKey] = useState("");
  const [draftLabel, setDraftLabel] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateCollection.mutateAsync({
        title,
        description,
        isPublic,
        editable,
        attachmentFields,
      });
      onClose();
    } catch {
      // surfaced via updateCollection.isError
    }
  }

  function addAttachmentField() {
    const key = draftKey.trim();
    const label = draftLabel.trim();
    if (!key || !label || attachmentFields.some((f) => f.key === key)) return;
    setAttachmentFields((fields) => [...fields, { key, label }]);
    setDraftKey("");
    setDraftLabel("");
  }

  function removeAttachmentField(key: string) {
    setAttachmentFields((fields) => fields.filter((f) => f.key !== key));
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
        <div className="flex flex-col gap-1">
          <p className="text-sm font-medium text-ink">Champs de pièces jointes</p>
          <ul className="flex flex-col gap-1">
            {attachmentFields.map((f) => (
              <li key={f.key} className="flex items-center gap-2">
                <Input
                  aria-label={`Clé existante : ${f.key}`}
                  value={f.key}
                  readOnly
                  className="text-xs"
                />
                <Input
                  aria-label={`Libellé existant : ${f.key}`}
                  value={f.label}
                  readOnly
                  className="text-xs"
                />
                <button
                  type="button"
                  className="text-danger underline text-xs"
                  onClick={() => removeAttachmentField(f.key)}
                >
                  Retirer
                </button>
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <Input
              aria-label="Clé du champ"
              value={draftKey}
              onChange={(e) => setDraftKey(e.target.value)}
            />
            <Input
              aria-label="Libellé du champ"
              value={draftLabel}
              onChange={(e) => setDraftLabel(e.target.value)}
            />
            <Button type="button" variant="outline" size="sm" onClick={addAttachmentField}>
              Ajouter un champ
            </Button>
          </div>
        </div>
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
