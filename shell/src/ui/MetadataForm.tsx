// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Button } from "./button";
import { Input } from "./input";

export function MetadataForm({
  initial,
  onSubmit,
  onCancel,
  pending,
}: {
  initial: { title: string; abstract: string; keywords: string[] };
  onSubmit: (v: { title: string; abstract: string; keywords: string[] }) => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  const [title, setTitle] = useState(initial.title);
  const [abstract, setAbstract] = useState(initial.abstract);
  const [keywords, setKeywords] = useState(initial.keywords.join(", "));

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
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        Titre
        <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Résumé
        <textarea
          aria-label="Résumé"
          className="min-h-20 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
          value={abstract}
          onChange={(e) => setAbstract(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Mots-clés
        <Input
          aria-label="Mots-clés"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
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
