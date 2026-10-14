# 0019 — Haute disponibilité : borne de la Vague 1, puis HA multi-réplicas (ARC-32)

Statut: acceptée (mise à jour : ARC-32 livré)
Source : ARC-18/ARC-19 (comparatif FME/ArcGIS Enterprise 2026-10-11 §6.1.2) ; ARC-32 (HA réelle multi-réplicas) ; SP-49, SP-59, REV-164/354/355/345.

## Contexte

Esri documente une HA bornée à un datacenter (2 portails + LB). GeoStudio est un monolithe `core` ; la Vague 1 avait un limiteur de débit en mémoire par process et un `cdc-worker` mono-writer.

## Décision

- Vague 1 : un **runbook** (2 instances `core` derrière Traefik, Postgres primaire/standby en streaming, MinIO distribué, RPO/RTO annoncés), un **test de bascule scripté**, et la vérification des invariants à 2 réplicas (jobs procrastinate, CSP, limiteur).
- **ARC-32 (livré)** : limiteur de débit **partagé Postgres** (`rate_limit_counters`, repli mémoire thread-safe si la base est injoignable) ; **élection du `cdc-worker`** par verrou consultatif de session sur connexion directe (la fente de réplication reste la seconde garde) ; MCP **sans état** (`CORE_MCP_STATELESS`) ; **verrou consultatif de migration** dans `alembic/env.py` (N réplicas lançant `alembic upgrade head`), qui exige une connexion directe (`CORE_MIGRATION_DATABASE_URL`) derrière PgBouncer. Mesures et limites : `docs/runbooks/2026-10-14-haute-disponibilite-reelle.md`.
- **Exception à la règle « `tenant_id` et `audit_log` dès la première migration »** : `rate_limit_counters` est une table d'**infrastructure**, pas une donnée métier. Elle est `UNLOGGED` (perdue au crash, sans conséquence : fenêtres de 60 s), sa clé est un **hachage SHA-256** de l'en-tête `Authorization` (aucun jeton ni identité en clair), et elle n'est jamais lue par un utilisateur. Un `tenant_id` n'aurait pas de sens (le budget est par appelant) et un `audit_log` par incrément serait un coût de latence sans valeur.
- Le **drill de restauration** (ARC-19) ne tourne que sur une stack jetable, jamais sur la base de référence partagée.

## Conséquences

- Promesse commerciale : HA multi-réplicas du cœur, dans les bornes mesurées du runbook ; le support contractuel reste hors périmètre.
- Reliquat : le pacer de `geocoding/batch` reste par process (budget non partagé entre réplicas).
