// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useInstanceInfo, useMetadataCatalog, useUpdateCollection } from "../api/hooks";
import type { CollectionAdmin } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Select } from "../ui/kit/Select";
import { Tabs } from "../ui/kit/Tabs";
import { Textarea } from "../ui/kit/Textarea";

const UNSET = "unset";

export function EditCollectionPanel({
  collection,
  onClose,
}: {
  collection: CollectionAdmin;
  onClose: () => void;
}) {
  const updateCollection = useUpdateCollection(collection.id);
  const instanceQuery = useInstanceInfo();
  const catalogQuery = useMetadataCatalog();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [title, setTitle] = useState(collection.title);
  const [description, setDescription] = useState(collection.description);
  const [isPublic, setIsPublic] = useState(collection.isPublic);
  const [editable, setEditable] = useState(collection.editable);
  const [attachmentFields, setAttachmentFields] = useState(collection.attachmentFields ?? []);
  const [draftKey, setDraftKey] = useState("");
  const [draftLabel, setDraftLabel] = useState("");
  const [license, setLicense] = useState(collection.license || UNSET);
  const [licenseUri, setLicenseUri] = useState(collection.licenseUri);
  const [producer, setProducer] = useState(collection.producer);
  const [contact, setContact] = useState(collection.contact);
  const [updateFrequency, setUpdateFrequency] = useState(collection.updateFrequency || UNSET);
  const [lineage, setLineage] = useState(collection.lineage);
  const [language, setLanguage] = useState(collection.language);
  const [version, setVersion] = useState(collection.version);
  const [temporalStart, setTemporalStart] = useState(collection.temporalStart ?? "");
  const [temporalEnd, setTemporalEnd] = useState(collection.temporalEnd ?? "");

  const licenseOptions = [
    { value: UNSET, label: "Aucune licence déclarée" },
    ...(catalogQuery.data?.licenses.map((l) => ({ value: l.id, label: l.label })) ?? []),
  ];
  const frequencyOptions = [
    { value: UNSET, label: "Non renseignée" },
    ...(catalogQuery.data?.frequencies.map((f) => ({ value: f.id, label: f.label })) ?? []),
  ];
  const languageOptions =
    catalogQuery.data?.languages.map((l) => ({ value: l.id, label: l.label })) ?? [];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateCollection.mutateAsync({
        title,
        description,
        isPublic,
        editable,
        attachmentFields,
        license: license === UNSET ? "" : license,
        licenseUri,
        producer,
        contact,
        updateFrequency: updateFrequency === UNSET ? "" : updateFrequency,
        lineage,
        language,
        version,
        temporalStart: temporalStart || null,
        temporalEnd: temporalEnd || null,
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
        <Tabs
          aria-label="Sections d'édition"
          defaultValue="general"
          tabs={[
            {
              value: "general",
              label: "Général",
              content: (
                <div className="flex flex-col gap-3 pt-3">
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Titre
                    <Input
                      aria-label="Titre"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
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
                </div>
              ),
            },
            {
              value: "metadata",
              label: "Métadonnées ouvertes",
              content: (
                <div className="flex flex-col gap-3 pt-3">
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Licence
                    <Select
                      aria-label="Licence"
                      value={license}
                      onValueChange={setLicense}
                      options={licenseOptions}
                    />
                  </label>
                  {license === "other" && (
                    <label className="flex flex-col gap-1 text-sm text-ink">
                      URI de la licence
                      <Input
                        aria-label="URI de la licence"
                        value={licenseUri}
                        onChange={(e) => setLicenseUri(e.target.value)}
                      />
                    </label>
                  )}
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Producteur
                    <Input
                      aria-label="Producteur"
                      value={producer}
                      onChange={(e) => setProducer(e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Contact
                    <Input
                      aria-label="Contact"
                      value={contact}
                      onChange={(e) => setContact(e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Fréquence de mise à jour
                    <Select
                      aria-label="Fréquence de mise à jour"
                      value={updateFrequency}
                      onValueChange={setUpdateFrequency}
                      options={frequencyOptions}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Généalogie
                    <Textarea
                      aria-label="Généalogie"
                      value={lineage}
                      onChange={(e) => setLineage(e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Langue
                    <Select
                      aria-label="Langue"
                      value={language}
                      onValueChange={setLanguage}
                      options={languageOptions}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    Version
                    <Input
                      aria-label="Version"
                      value={version}
                      onChange={(e) => setVersion(e.target.value)}
                    />
                  </label>
                  <div className="flex gap-2">
                    <label className="flex flex-1 flex-col gap-1 text-sm text-ink">
                      Début
                      <Input
                        type="date"
                        aria-label="Début de l'emprise temporelle"
                        value={temporalStart}
                        onChange={(e) => setTemporalStart(e.target.value)}
                      />
                    </label>
                    <label className="flex flex-1 flex-col gap-1 text-sm text-ink">
                      Fin
                      <Input
                        type="date"
                        aria-label="Fin de l'emprise temporelle"
                        value={temporalEnd}
                        onChange={(e) => setTemporalEnd(e.target.value)}
                      />
                    </label>
                  </div>
                </div>
              ),
            },
            {
              value: "attachments",
              label: "Pièces jointes",
              content: (
                <div className="flex flex-col gap-1 pt-3">
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
              ),
            },
          ]}
        />
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
