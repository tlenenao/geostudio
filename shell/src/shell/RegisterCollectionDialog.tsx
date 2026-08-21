// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCandidateTables, useCreateCollection, useInstanceInfo } from "../api/hooks";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { Input } from "../ui/input";

export function RegisterCollectionDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const candidatesQuery = useCandidateTables({ enabled: open });
  const createCollection = useCreateCollection();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [tableName, setTableName] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [isPublic, setIsPublic] = useState(false);

  function close() {
    setTableName("");
    setTitle("");
    setDescription("");
    setIsPublic(false);
    createCollection.reset();
    onClose();
  }

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
      close();
    } catch {
      // surfaced via createCollection.isError
    }
  }

  return (
    <Dialog open={open} onClose={close} title="Enregistrer une table">
      {candidatesQuery.isLoading && <p role="status">Chargement…</p>}
      {candidatesQuery.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec du chargement des tables candidates.
        </p>
      )}
      {candidatesQuery.data && candidatesQuery.data.length === 0 && (
        <p className="text-sm text-slate-600">
          Aucune table à enregistrer — toutes les tables éligibles du schéma public sont déjà des
          collections, ou importez un fichier depuis le catalogue.
        </p>
      )}
      {candidatesQuery.data && candidatesQuery.data.length > 0 && (
        <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Table
            <select
              aria-label="Table"
              className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
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
          {createCollection.isError && (
            <p role="alert" className="text-sm text-red-600">
              Échec de l'enregistrement.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Annuler
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={!tableName || createCollection.isPending || readOnly}
            >
              Enregistrer
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
