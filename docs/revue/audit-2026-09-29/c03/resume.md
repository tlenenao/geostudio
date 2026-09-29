# c03 — Migrations et données (code) : résumé

## Périmètre couvert

- Relecture de `core/alembic/versions/0028` à `0042` en entier, et relecture ciblée des migrations
  antérieures (0001, 0004, 0006, 0007, 0008, 0016, 0018, 0020, 0021, 0023, 0027) : sens upgrade
  **et** downgrade sur base non vide, colonnes NOT NULL ajoutées sans défaut, gestion des rôles
  Postgres.
- Clés étrangères et cascades : inventaire mécanique de toutes les FK de `Base.metadata`
  (identique au schéma Alembic d'après `tests/test_model_alembic_parity.py`), puis le vrai chemin de
  suppression d'item (`DELETE /v1/items/{id}` → `_delete_config_and_item`).
- Index : inventaire mécanique des index par table + plans de requête des chemins les plus
  fréquents (usage/audit, configs, runs).
- `tenant_id` / `audit_log` : comptage par module des routes d'écriture et des `write_audit`, puis
  lecture des chemins d'écriture en arrière-plan (balayages cron pipelines/moissonnage/alertes/
  rapports, runtime `writer.collection`).

## Déjà connu, non re-signalé

- Migrations sans test round-trip (0029/0030/0031/0034/0037/0038/0039/0041) et le faux test de
  0028 : items 5 et 6 de `docs/revue/2026-09-29-audit-pre-release.md`. c03-002 ajoute un **défaut
  réel** à 0030, pas le seul manque de test.
- Downgrade 0024, index alert/pipeline runs, dérive de `server_default` : GAP-63 (fermé).
  c03-007 est la jumelle oubliée de ce correctif (report_runs).
- `audit_log` en lecture : GAP-71 (fermé par SP-47). c03-004 porte sur l'index absent.

## Périmètre non couvert (et pourquoi)

- **Pas d'exécution réelle upgrade/downgrade sur Postgres** : aucun `CORE_TEST_DATABASE_URL`
  dans cet environnement, aucun Postgres joignable sur 5432-5434, et le prompt interdit docker.
  Les preuves exécutées tournent donc sur SQLite (`PRAGMA foreign_keys=ON`, cf. `app/db.py`) ou
  appellent directement les fonctions de données de 0030. Les plans de requête viennent de SQLite
  `EXPLAIN QUERY PLAN` : ils prouvent qu'aucun index n'existe, pas un temps mesuré sur Postgres.
- `alembic upgrade --sql` (mode hors ligne) échoue dès 0011 (migration de données) : pas de
  génération de SQL possible hors base.
- `purge_tenant` : exclu par la règle 6.
- Le CDC et les tables physiques des collections (RLS, GRANT), hors RLS de base de 0042, ne sont pas
  audités ici.

## Méthode

Lecture directe du code (jamais de conclusion tirée d'un seul `grep`), puis sondes exécutées,
conservées dans `probes/` pour pouvoir les rejouer :

- `probes/test_c03_probe.py` : suppression d'un pipeline qui a un run ou un jeton webhook
  (IntegrityError → 500), aller-retour downgrade/upgrade de 0030 pour un Lecteur (→ Créateur).
- `probes/index_plans.py` : inventaire index/FK de `Base.metadata` et plans de requête.

## Commandes lancées

```bash
cd core && CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8= CORE_ENV=development \
  PYTHONPATH=. uv run pytest ../docs/revue/audit-2026-09-29/c03/probes/test_c03_probe.py -s -q \
  -p no:cacheprovider --rootdir=. -o addopts=""        # 3 failed = 3 défauts reproduits
cd core && PYTHONPATH=. uv run python ../docs/revue/audit-2026-09-29/c03/probes/index_plans.py
cd core && DATABASE_URL=postgresql+psycopg://x:x@localhost/x PYTHONPATH=. uv run alembic upgrade 0029 --sql   # échoue en 0011
cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/c03 --repo-root ..
```

## Bilan

10 findings : S2 × 5 (suppression d'item en 500, élévation Lecteur→Créateur au downgrade de 0030,
écritures de pipelines planifiés absentes de l'audit, `audit_log` sans index, configs/révisions
sans index) ; S3 × 4 ; S4 × 1.
