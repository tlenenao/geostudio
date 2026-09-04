// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Button } from "./kit/Button";
import { Input } from "./kit/Input";
import { Select } from "./kit/Select";

const UNSET = "unset";

export function MetadataForm({
  initial,
  licenses,
  languages,
  onSubmit,
  onCancel,
  pending,
}: {
  initial: {
    title: string;
    abstract: string;
    keywords: string[];
    license: string;
    language: string;
  };
  licenses: { id: string; label: string }[];
  languages: { id: string; label: string }[];
  onSubmit: (v: {
    title: string;
    abstract: string;
    keywords: string[];
    license: string;
    language: string;
  }) => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  const [title, setTitle] = useState(initial.title);
  const [abstract, setAbstract] = useState(initial.abstract);
  const [keywords, setKeywords] = useState(initial.keywords.join(", "));
  const [license, setLicense] = useState(initial.license || UNSET);
  const [language, setLanguage] = useState(initial.language);

  const licenseOptions = [
    { value: UNSET, label: "Aucune licence déclarée" },
    ...licenses.map((l) => ({ value: l.id, label: l.label })),
  ];
  const languageOptions = languages.map((l) => ({ value: l.id, label: l.label }));

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) return;
    onSubmit({
      title: clean,
      abstract,
      keywords: keywords
        .split(",")
        .map((k) => k.trim())
        .filter((k) => k.length > 0),
      license: license === UNSET ? "" : license,
      language,
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm text-ink">
        Titre
        <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm text-ink">
        Résumé
        <textarea
          aria-label="Résumé"
          className="min-h-20 rounded-md border border-rule bg-surface px-3 py-2 text-sm text-ink"
          value={abstract}
          onChange={(e) => setAbstract(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm text-ink">
        Mots-clés
        <Input
          aria-label="Mots-clés"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm text-ink">
        Licence
        <Select
          aria-label="Licence"
          value={license}
          onValueChange={setLicense}
          options={licenseOptions}
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
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Annuler
        </Button>
        <Button type="submit" size="sm" disabled={pending || !title.trim()}>
          Enregistrer
        </Button>
      </div>
    </form>
  );
}
