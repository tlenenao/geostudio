# Fixtures d'ingestion — provenance et licence

Chaque fichier de ce répertoire est un téléchargement réel (pas un fichier
synthétique), conservé pour test uniquement (GAP-29).

- `archsites.gml` — OSGeo/gdal, `autotest/ogr/data/gml/archsites.gml`,
  licence MIT (`LICENSE.TXT` racine du dépôt).
- `TwoSheetsNoneHidden.xlsx` — apache/poi,
  `test-data/spreadsheet/TwoSheetsNoneHidden.xlsx`, licence Apache-2.0
  (`legal/LICENSE`).
- `scifact_claims_sample.jsonl` — openai/openai-cookbook,
  `examples/data/scifact_claims.jsonl`, licence MIT — tronqué aux N
  premières lignes (fichier source : 65 007 octets, bien plus volumineux
  qu'un fixture de test n'a besoin de l'être).
- `books.xml` — microsoft/aspire,
  `playground/Stress/Stress.ApiService/content/books.xml`, licence MIT.

Si un remplacement a eu lieu pendant l'exécution du plan (source
indisponible), la ligne correspondante ci-dessus doit être mise à jour avec
le chemin/dépôt/licence réels utilisés.
