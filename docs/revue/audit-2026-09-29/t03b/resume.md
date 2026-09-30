# t03b — Performance perçue (passe flags allumés)

## Périmètre couvert
- Pipeline (ETL allumé) sur 50k et 500k lignes (collection sans géométrie : reader.collection ne lit pas `geom`, j06b-002) : reader -> writer.export CSV (0,9 s, pic worker 330 -> 398 Mo), filtre + agrégat -> export (0,3 s), writer.export GeoJSON (2,6 s, 299 -> 709 Mo), aperçu (0,3 s), writer.collection 50k (24,3 s) et 500k (242 s), file d'attente du worker (t03b-002).
- Exports d'entités `/v1/collections/{id}/export/items` : 10 000 exactes (CSV 0,19 s, GeoJSON 0,52 s, GPKG 0,40 s, XLSX 0,69 s, cœur 261-275 Mo), 10 001 (413 en 0,16 s), 500k (413 en 0,84 s), agrégat exporté 500k (0,22 s). Confirme et quantifie t03-008 (plafond) et t03-007 (lien GeoJSON à 1 000).
- DuckDB / lakehouse (CDC actif) : agrégat groupé 500k 0,24-0,27 s, 5 concurrents 0,6 s, SQL Lab GROUP BY 0,3 s, ORDER BY plafonné à 10 000 lignes 0,36 s, jointure explosive stoppée à 10,2 s (400 propre), fraîcheur CDC 31 s.
- Écrans nouvellement accessibles en navigation SPA : éditeur de pipeline (prêt 0,9 s, 98 Ko transférés dont 76 Ko de chunk, CLS 0,037), 8 écrans d'administration/tâches/SQL Lab (tous < 0,9 s, CLS < 0,05 ; SQL Lab 172 Ko).
- Quotas/usage (CORE_QUOTAS_ENABLED) : GET /admin/usage avec 2 500 objets (0,27 s) et exactitude du calcul de stockage.

## Non couvert (et pourquoi)
- Observability (profil absent), LLM éteint. Rendu carte sur 500k non re-mesuré (couvert par t03 ; worker MapLibre octet-stream j12-001).
- Exécution de pipeline déclenchée depuis l'interface : POST /run répond 500 (AppNotOpen) ; les runs sont déférés depuis le worker comme j06b (`runPipeline`).
- Lecture de collections à géométrie par pipeline et par SQL Lab (j05-001, j06b-002) : 500k points mesurés seulement via l'API d'agrégat (qui ne lit pas `geom`).
- Bloc LCP à froid d'une route authentifiée (j02-004) ; fuites au démontage de l'éditeur de pipeline (budget de 25 tests atteint) ; 5 M de lignes (extrapolation mémoire non mesurée, t03b-008 en `probable`) ; compression Traefik.
- `/admin/compliance` exclu : page vide pour l'admin sans privilège `compliance.manage` (conception, non perf).

## Méthode
Jeux de données : POST /v1/collections/empty puis INSERT ... generate_series dans la seule table (caches /tmp/aud-t03*, aud-t03b*). Attente du CDC avant tout reader. Durées de run lues dans startedAt/finishedAt (l'attente de `runPipeline`, ~8 s, vient du rattrapage AppNotOpen, pas du moteur). Mémoire : `docker stats` échantillonné en continu pendant le run. Chaque test `bug(...)` a été rejoué avec AUDIT_VERIFY=1 et échoue pour la raison attendue. Un premier échantillonneur synchrone gelait la boucle d'événements : remplacé par un échantillonneur asynchrone. Résultat sain majeur : le moteur DuckDB/pipeline tient 500k lignes en moins de 3 s ; les goulots sont l'écriture ligne à ligne et la concurrence du worker.

## Commandes
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/t03b` (25 tests : 18 verts, 7 `bug` ignorés hors AUDIT_VERIFY)
- `AUDIT_VERIFY=1 ... -g "t03b-00"` : les 7 échouent comme attendu
- `cd shell && npx eslint e2e/journeys/t03b && npx prettier --check e2e/journeys/t03b`
- Validateur : `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/t03b --repo-root ..`
