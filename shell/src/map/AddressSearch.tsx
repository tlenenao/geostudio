// SPDX-License-Identifier: Apache-2.0
// REV-102 : recherche d'adresse (BAN via GET /v1/geocode). Une requête par
// soumission, jamais à la frappe (budget de rate limit « geocode »). Chargé
// par lazy() depuis MapEditorPage.
import { useState, type FormEvent } from "react";
import { useItemClient } from "../api/ItemClientProvider";
import type { GeocodeResult } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { t } from "../i18n";

export function AddressSearch({ onSelect }: { onSelect: (center: [number, number]) => void }) {
  const client = useItemClient();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[] | null>(null);
  const [failed, setFailed] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setFailed(false);
    try {
      setResults(await client.geocode(query.trim()));
    } catch {
      setResults(null);
      setFailed(true);
    }
  }

  return (
    <form className="flex flex-col gap-2" onSubmit={(e) => void submit(e)}>
      <div className="flex gap-2">
        <Input
          aria-label={t("addressSearch.inputAria")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Button type="submit" size="sm" variant="outline" disabled={query.trim().length < 3}>
          {t("addressSearch.submit")}
        </Button>
      </div>
      {failed && (
        <p role="alert" className="text-xs text-danger">
          {t("addressSearch.failed")}
        </p>
      )}
      {results?.length === 0 && <p className="text-xs text-ink-2">{t("addressSearch.empty")}</p>}
      {results && results.length > 0 && (
        <ul className="flex flex-col gap-1">
          {results.map((r) => (
            <li key={`${r.lon},${r.lat},${r.label}`}>
              <button
                type="button"
                className="text-left text-xs text-ink underline"
                onClick={() => onSelect([r.lon, r.lat])}
              >
                {r.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}
