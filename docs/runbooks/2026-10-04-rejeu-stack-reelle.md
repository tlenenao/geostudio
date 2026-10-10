# Runbook — rejeu sur stack réelle (REV-164, 272 à 286)

Orchestrateur : `scripts/replay/run.sh` (un stage à la fois, relançable). Journeys : `scripts/audit/run-suite.sh`.
Rapport de la dernière exécution : `docs/revue/2026-10-04-rapport-rejeu-stack-reelle.md`.

## 1. Objet et règle de fermeture

Une lettre de REV se ferme dans l'un de ces trois cas, et seulement ceux-là : (1) livrée dans le code avec son test ; (2) tranchée par un ADR (`docs/adr/`) ; (3) rejouée sur stack réelle avec une preuve datée (chemin de log ou de JSON). Une lettre non rejouée est `externe` ou `non rejoué`, jamais fermée par défaut.

## 2. Pré-requis machine

- WSL2 avec ~12 Go de RAM : une seule session lourde à la fois (un second job concurrent fait tuer les conteneurs ou les tests).
- `.env` bootstrappé (`scripts/bootstrap-env.sh`), `CORE_AUTH_MODE=oidc` pour les journeys et `oidc`, `mock` pour `smoke`.
- Docker + Compose, `uv`, Node 22 (`cd shell && npm ci`).
- Ne pas poser `S3_PUBLIC_ENDPOINT_URL` vide : la CI le fixe (`http://localhost:9000`) ; sans lui les URL présignées pointent sur `minio:9000`, injoignable du navigateur.

## 3. Séquence

1. `run.sh preflight` : docker, `.env`, charge machine, SHA.
2. `run.sh up` : flags d'audit, `docker compose up -d --build`, personas, snapshot (premier démarrage : le healthcheck du cœur peut dépasser 90 s après migrations ; Martin se relance avec `docker compose up -d martin`).
3. `run.sh journeys --lane all --verify` : voies parallèle puis série, JSON dans `.audit-results/<ts>/`.
4. `run.sh e2e-mock` : `npm run e2e` complet.
5. `run.sh oidc` : `shell/e2e-oidc/` (le copilote exige `CORE_LLM_PROVIDER=fake`).
6. `run.sh admin-tools` : spec `j09c/admin-tools-traefik.spec.ts` derrière Traefik.
7. `run.sh plans` : plans d'index sur Postgres réel (sans `SEQSCAN` ni `INCONCLUSIF` ; une base < 1000 lignes est inconclusive, la peupler d'abord).
8. `run.sh measure` : tri PK 10^6 et mémoire du `GROUP BY` DuckDB.
9. `run.sh rebuild-images` : titiler et otel-lgtm reconstruits.
10. `run.sh smoke` : `scripts/ci/stack-smoke.sh`, sur une stack remontée en mock.
11. `run.sh restore-oidc` : **destructif** (`down -v`) : sauvegarde, restauration puis reconnexion OIDC (REV-164). Ne jamais le lancer sur une stack à conserver.
12. `run.sh report` : agrège `.replay-results/<ts>/summary.txt` et les lignes `RESULT` en `report.md`.

## 4. Table lettres → preuve

| REV | Lettre | Preuve à produire | Outil |
|---|---|---|---|
| REV-164 | (b) | Restauration réelle puis reconnexion OIDC du même compte, item d'avant-sinistre visible (runbook 2026-07-24 §7, étapes 1-7) | `run.sh restore-oidc` |
| REV-272 | (c) | `shell/e2e/journeys/j01/embed-share-link.spec.ts` vert sur stack OIDC | `run.sh journeys --only j01` |
| REV-272 | (a) | Pas de rejeu : tombstone = ADR statu quo, conditionnel DPO | — |
| REV-273 | (a) | `j06/secrets-api.spec.ts` « j06-004 » vert en `--verify` (garde d'egress à l'exécution, preuve `j06b-010`) | `journeys --only j06` |
| REV-274 | (a) | Spec `j09c/admin-tools-traefik.spec.ts` (lancement, cookie, Martin, révocation) avec `CORE_ADMIN_TOOLS_ENABLED=true` derrière Traefik | `run.sh admin-tools` |
| REV-274 | (b) | Images `deploy/titiler` et `otel-lgtm` reconstruites ; Grafana Viewer anonyme et titiler répondent | `run.sh rebuild-images` |
| REV-275 | (a) | `j06b` complet vert ; run de 50 000 lignes réel (`t03b/pipeline-volume.spec.ts`) | `journeys --only "j06 j06b t03b"` |
| REV-275 | (b) | `j06b-001/014/015/016` et `j06-012` basculés | règle de bascule (§6) |
| REV-276 | (a) | `j07/*` vert | `journeys --only j07` |
| REV-277 | (a) | `j09`, `j09b`, `j02` verts | `journeys --only "j02 j09 j09b"` |
| REV-278 | (d) | `j01 j03 j04 j08 j09` verts + `npm run e2e` complet | `journeys` + `run.sh e2e-mock` |
| REV-279 | (c) | Plans d'index sur Postgres réel (`scripts/replay/index_plans_pg.py`) | `run.sh plans` |
| REV-280 | (b) | `j05`, `j05b`, `t03b` verts | `journeys --only "j05 j05b t03b"` |
| REV-280 | (d) | Mesure mémoire du `GROUP BY` DuckDB ; `memory_limit`/`MAX_GROUPS` (`core/app/analytics/aggregate.py`) fixés d'après la mesure | `run.sh measure` |
| REV-281 | (d) | `scripts/ci/stack-smoke.sh` en local et job `stack-smoke` vu vert sur GitHub (exige un push/PR : sinon `externe`) | `run.sh smoke` |
| REV-282 | (a) | Import réel (sans semis SQL) + `j03`, `t02` verts | `journeys --only "j03 t02"` |
| REV-283 | (f) | `j03`, `j09`, `t03`, `t03b` verts ; `EXPLAIN` du tri PK sur 10^6 entités | `journeys` + `run.sh measure` |
| REV-284 | (a) | `t01`, `t01b`, `j03` verts | `journeys --only "t01 t01b j03"` |
| REV-284 | (d) | Manuel : audit lecteur d'écran réel (procédure du §7) | humain |
| REV-285 | (i) | `t04`, `j06` verts + `npm run e2e:oidc` | `journeys` + `run.sh oidc` |
| REV-286 | (c) | `j02`, `j03`, `j12` verts ; manuel : appareil tactile réel (procédure du §7) | `journeys` + humain |

## 5. Lire un échec

Sous `--verify`, un test `bug(...)` dont le défaut est corrigé doit passer. Un rouge se classe : (i) régression produit réelle : REV neuve ; (ii) flake de charge : rejouer le dossier seul (`--only <dossier>`) avant de conclure, deux sessions concurrentes sur le même Postgres produisent des collisions sans rapport (piège SP-49) ; (iii) parcours périmé face à un changement produit (libellé, état vide, plafond de privilège) : corriger le parcours et le consigner.

## 6. Règle de bascule `bug(` vers `test(`

Seul un test dont le JSON `.audit-results/<ts>/<dossier>.json`, produit sous `--verify`, montre `passed` bascule. Rejouer ensuite le dossier SANS `AUDIT_VERIFY` (0 failed attendu), et falsifier au moins une bascule (injecter le défaut, constater l'échec, restaurer). Un `bug(` encore rouge reste `bug(` et devient une REV.

## 7. Lettres manuelles

REV-284 (d) et REV-286 (c) : voir `docs/revue/2026-10-04-rejeu-procedures-manuelles.md`. Non exécutées = `externe`.

## 8. Nettoyage

Ne pas laisser la stack tourner : `docker compose down` (jamais `-v` hors `run.sh restore-oidc` voulu), `scripts/audit/stack-reset.sh` pour revenir à l'état de référence, supprimer les bases/conteneurs jetables (`audit-*`).
