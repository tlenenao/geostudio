# Audit c02 — Correctness backend (code)

## Périmètre couvert

- **Transactions et frontières de commit** : `request_scoped_session`, la dépendance
  `get_session` de `create_app()`, les `session.commit()` explicites au milieu des
  routes (commit puis defer), l'ordre S3/DB sur les pièces jointes et les icônes.
- **Jobs procrastinate** : les 15 modules `*.jobs`/`*.tasks`, `import_paths`, les files
  déclarées comparées aux `-q` des workers du compose, les balayages de réclamation
  (`reclaim_stuck_jobs`, `list_due_pipelines`), l'idempotence des transitions de statut,
  la notification best-effort séparée (`app/jobs/common.py`), le cycle de vie des Engines.
- **Concurrence asyncio/sync** : tous les `async def` du cœur (tools MCP, copilote,
  vérificateur de jeton MCP, `create_map_icon`).
- **Parité REST/MCP** : REV-174 revérifié (fermé pour de bon : `save_app_config` exécute
  bien les 7 validateurs et les 2 gardes de capacité), les 11 tools `@write_tool`, les
  tools qui écrivent sans ce décorateur (`create_alert_rule`, `run_alert_rule`), les trois
  routes de suppression de config/item.
- **TOCTOU** : quotas (compter puis insérer), réclamation des jobs contre une fin normale.

## Périmètre NON couvert (et pourquoi)

- **Rien sur Postgres réel** : pas de `CORE_TEST_DATABASE_URL`, pas de docker (consigne).
  Tout est rejoué sur SQLite. Les effets propres à Postgres (idle-in-transaction,
  pgbouncer, `InFailedSqlTransaction`, sérialisation) sont argumentés à partir du code
  et restent `probable`.
- **Pas relu en détail** : CDC (`app/cdc/main.py`), le runtime interne des pipelines
  (`runtime.py`, `connector_runtime.py`, déjà couvert par REV-195/196/197),
  `purge_tenant`/`anonymize_user` (interdits par la consigne ; seul le câblage de la tâche
  est signalé, c02-004), le shell.
- **Pas de nouveau signalement** pour ce que citent déjà l'audit pré-release, REV-174
  (fermé, revérifié) et REV-197.

## Méthode

Relecture directe du code, en suivant l'appel réel plutôt que des noms (piège n°11).
Chaque hypothèse vérifiable a son repro exécuté dans `repro/`. Ce dossier ne contient
que des tests et des scripts : aucun fichier source n'a été modifié. Les assertions des
repros décrivent le comportement **actuel** (fautif) : un test vert confirme donc le
défaut. Pour la concurrence, on mesure le **recouvrement des intervalles** (piège n°7),
jamais une durée. Le comportement de FastAPI 0.138.1 et de procrastinate 3.9.0 a été
vérifié sur les paquets installés (`.venv`), pas d'après leur documentation.

## Commandes lancées (depuis `core/`, `SCRATCH` = dossier scratchpad de session)

```bash
PYTHONPATH=. uv run pytest ../docs/revue/audit-2026-09-29/c02/repro/ -p tests.conftest \
  -p no:cacheprovider --basetemp=$SCRATCH/pt -q -s --rootdir=. -c pyproject.toml
#   -> 6 passed (c02-001, 002, 005, 006, 007, 008)
PYTHONPATH=. uv run python ../docs/revue/audit-2026-09-29/c02/repro/queues_vs_workers.py      # c02-003, c02-004
PYTHONPATH=. uv run python ../docs/revue/audit-2026-09-29/c02/repro/mcp_blocks_event_loop.py $SCRATCH  # c02-009
PYTHONPATH=. uv run python ../docs/revue/audit-2026-09-29/c02/repro/engine_per_job.py $SCRATCH        # c02-013
uv run python ../docs/revue/audit-2026-09-29/c02/repro/commit_after_response.py               # c02-001 (FastAPI seul)
grep -n TaskNotFound .venv/lib/python3.14/site-packages/procrastinate/worker.py               # c02-004
PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/c02 --repo-root ..
```

`-p tests.conftest` charge les fixtures et l'environnement de test du cœur
(`CORE_ENV=development`, clé maître de test) pour un fichier situé hors de `core/tests/`.
`--basetemp` contourne le `/tmp/pytest-of-lenen` appartenant à root (item 4 de l'audit
pré-release).

## Points saillants

- **S1 — c02-003** : la file `harvest` n'est consommée par aucun worker. Le moissonnage,
  manuel comme planifié, ne s'est donc jamais exécuté dans la stack compose.
- **S2** :
  - c02-004 : la purge de tenant n'est pas enregistrée dans le worker (`TaskNotFound`).
  - c02-001 : un commit exécuté après l'envoi de la réponse, donc un 2xx possible sans
    persistance.
  - c02-002 : la garde de références inverses manque sur `DELETE /configs/{id}`.
  - c02-005 : un run de pipeline long est relancé en parallèle et l'ancien reste un zombie.
  - c02-009 : les tools MCP bloquent la boucle asyncio de toute l'API.
- Les défauts c02-003 et c02-004 relèvent du piège n°2 (« livré ≠ câblé »), sur l'axe des
  files et du registre de tâches. `test_deployability.py` ne couvre pas encore cet axe.
