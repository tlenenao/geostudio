# Rejouer la suite de parcours d'audit

~770 tests Playwright (`shell/e2e/journeys/`, 96 fichiers) écrits pendant l'audit du
2026-09-29/30, sur **stack réelle** (oidc, flags d'audit allumés, LLM éteint).
Ils ne font pas partie de `npm run e2e` ni de la CI : lancement dédié.

## Pré-requis (une fois par poste)

```bash
scripts/audit/enable-flags.sh          # écrit les flags + secrets dans .env (non versionné), idempotent
docker compose up -d                   # profils export, appexport, observability
scripts/audit/seed-personas.sh         # 4 personas Keycloak (cf. ORCHESTRATION.md pour l'ordre complet
scripts/audit/stack-reset.sh snapshot  #  de bootstrap : personas → snapshot → reset → 1er login → set-roles → snapshot)
```

Grafana est exposé sur l'hôte en `:3011` (`GRAFANA_HOST_PORT`), car `:3001` est refusé par
WSL2/Windows sur certains postes.

## Lancer

```bash
scripts/audit/run-suite.sh                       # les deux voies
scripts/audit/run-suite.sh --lane parallel       # 1 reset, 3 workers
scripts/audit/run-suite.sh --lane serial         # 1 reset par dossier, 1 worker
scripts/audit/run-suite.sh --only "j01 j05"      # sous-ensemble
scripts/audit/run-suite.sh --verify              # exécute aussi les tests bug()
```

Résultats : `.audit-results/<horodatage>/summary.md` (+ un JSON et un log par dossier).

## Les deux voies

- **parallel** : dossiers qui ne lisent que ce qu'ils créent (`stamp()`).
- **serial** : rôles/anonymisation/quotas (j08*), alertes/rapports (j09*), copilote (j11),
  groupes/partages (j13), arrêt de `worker`/`martin` (t02), mesures de temps (t03*).
  Un reset `--auth oidc` précède chaque dossier.

Un test qui change de verdict entre la voie parallèle et la référence en série dépend de l'état
global : le déplacer dans `SERIAL` (variable en tête de `run-suite.sh`).

## `bug(...)` et `AUDIT_VERIFY`

Un test qui révèle un bug connu est déclaré `bug("idfinding : …", …)` (`_fixtures/verify.ts`) :
ignoré par défaut, exécuté avec `AUDIT_VERIFY=1` (`--verify`).

- **Avant correctif** : `--verify` doit les faire **échouer** (preuve du bug).
- **Après correctif** : les faire **passer**, puis remplacer `bug(` par `test(` dans le test :
  il rejoint la suite de non-régression. La variable historique par dossier (`J04_VERIFY`,
  `T01_VERIFY`…) reste acceptée.

## Contournements à retirer après les correctifs

Ils masquent un bug et feraient passer (ou casser) un test pour une mauvaise raison :
`stubMap` (worker MapLibre servi en octet-stream, j12-001) ; second cœur `:8201` pour les quotas (j08b, à remplacer une fois les limites réglables).
