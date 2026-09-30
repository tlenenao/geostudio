# c09 — Performance backend (code)

## Périmètre couvert
N+1 et index (configs, audit_log, items, reports), listes sans pagination (catalogue public, facettes, /items count), DuckDB (open_connection, aggregate, SQL Lab, pipelines, alertes), tuiles MVT (plafond 5000, introspection), balayages cron (pipelines/alertes/rapports/appexport/CSP), worker procrastinate, CDC (compaction, dédup, consumer), ingestion.

## Non couvert
Mesures sur PostGIS réel (aucune stack ni CORE_TEST_DATABASE_URL : pas de EXPLAIN ni de temps mesurés, findings d'index/N+1 en code-read/probable) ; harvest et connecteurs (déjà traités GAP-57/59/64) ; recherche hybride RRF/pgvector en détail ; shell.

## Méthode
Lecture directe du code, puis 4 vérifications exécutées : concurrence procrastinate par défaut (1), défauts DuckDB (12.4 GiB / 8 threads), SQL compilé de select(Item) incluant embedding, select_files_to_merge re-fusionnant le fichier compacté.

## Commandes lancées
`uv run python -c` (procrastinate.worker.WORKER_CONCURRENCY ; duckdb settings ; compile select(Item) ; select_files_to_merge), `uv run python -m procrastinate ... worker --help`, greps de repro listés dans findings.jsonl, validateur audit_findings.py.
