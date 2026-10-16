# Activer les op de pipeline expérimentales

Une trentaine d'op de pipeline (messagerie, bases et entrepôts externes, fichiers cloud, OGC,
routage, géocodage) n'ont jamais été rejouées contre le vrai service. Elles sont masquées par
défaut. Liste, critère et preuves : [`docs/revue/2026-10-16-ops-experimentales.md`](../revue/2026-10-16-ops-experimentales.md).

## Activer

1. Dans `.env` : `CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED=true` (docker compose, Proxmox) ou
   `config.CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED: "true"` dans les `values` du chart Helm.
2. Recréer **`core` et `worker`** (le premier filtre le catalogue et valide l'écriture, le second
   refuse l'exécution) : `docker compose up -d core worker`.
3. Vérifier : `GET /v1/pipelines/ops` expose par exemple `writer.slack` avec `"experimental": true`,
   et la palette du builder affiche le badge « Expérimental ».

`scripts/install.sh` ne propose pas ce flag : l'activer est un choix explicite, jamais un défaut.

## Éteindre

Remettre `false` et recréer `core` et `worker`. Les pipelines déjà enregistrés qui contiennent
une op expérimentale ne sont pas supprimés : leur exécution (manuelle, planifiée, webhook) échoue
avec « Opération expérimentale désactivée : … » et leur enregistrement est refusé.

## Avant de s'y fier

Rejouer le pipeline sur un environnement de test du service visé (compte sandbox, file jetable)
avant tout usage en production : ces op peuvent diverger du comportement réel de l'API. Les
writers à effet externe (messagerie, FTP) ne sont jamais rejoués automatiquement.
