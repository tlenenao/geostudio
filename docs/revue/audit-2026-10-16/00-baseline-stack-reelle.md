# Baseline — rejeu sur stack réelle (2026-10-16, HEAD c0251b66)

Sources lues : `docs/runbooks/2026-10-04-rejeu-stack-reelle.md` (§3 séquence, §4 table), `scripts/replay/run.sh` (stages, l.10 et suivantes), `shell/playwright.oidc.config.ts`, `shell/e2e-oidc/*.spec.ts`, `docker-compose.yml:994` (`VITE_AUTH_MODE` défaut `mock`) et `:275` (`CORE_LLM_PROVIDER` défaut vide).
Aucun fichier source édité, rien commité. Aucun `down -v`.

## 1. Etat initial de la stack (constat)

`docker ps` au départ : `postgis`, `pgbouncer`, `minio`, `keycloak`, `titiler` en `Exited (255)` depuis 3 jours ; `core` et `worker` et `martin` en boucle de redémarrage. Preuve (`docker logs`) : `failed to resolve host 'pgbouncer'` (core), `could not translate host name "pgbouncer"` (worker), `Unable to get a Postgres connection ... Name does not resolve` (martin). Cause : conteneurs de base arrêtés (probablement redémarrage de WSL/Docker), pas un défaut de code.

Remédiation non destructive : `docker compose up -d` (sans `--build`, volumes conservés). Résultat : 14 services `healthy` (core, worker, cdc-worker, export-worker, keycloak, minio, pgbouncer, postgis, titiler, shell, traefik, otel-lgtm, postgres-exporter ; martin en `starting` puis stable).

## 2. Bilan de santé

`cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check` (sans `--write`) : **RC=0**, sortie `Santé médiane : 98.8 (plancher 96.0)`. Pas d'avertissement de surface non inventoriée.

## 3. Suite `shell/e2e-oidc/` (`npm run e2e:oidc`)

Piège de câblage trouvé (piège n°2) : le conteneur `shell` tournait avec `VITE_AUTH_MODE=mock` (défaut `docker-compose.yml:994`, `.env` ne le définit pas ; `curl localhost:8300/env-config.js` donnait `mock`) alors que `CORE_AUTH_MODE=oidc` dans `.env`. Premier run : 3 échecs, `page.waitForURL(/realms/geostudio/.../auth)` en timeout (`auth-oidc.spec.ts:9` et `:22`, `copilot-oidc.spec.ts:43`), snapshot Playwright « Connexion au serveur perdue » (cœur alors instable). Le runbook ne dit pas que `run.sh oidc` seul ne suffit pas : c'est `run.sh up` -> `enable-flags.sh` / `stack-reset.sh:102-106` qui exporte `VITE_AUTH_MODE`. A consigner dans le runbook (reliquat doc, non édité ici).

Après `VITE_AUTH_MODE=oidc docker compose up -d shell` (env-config.js -> `oidc`, Keycloak `.well-known` 200) :
- `auth-oidc.spec.ts` (connexion redirige vers Keycloak puis revient ; déconnexion efface la session) : **2 passed**.
- `copilot-oidc.spec.ts:63` : **échec** en timeout 240 s (`getByLabel("Message au copilote")` introuvable, `copilot-oidc.spec.ts:58`) car `CORE_LLM_PROVIDER` vide dans `.env` ; le runbook §3.5 exige `fake`. Rejoué avec `CORE_LLM_PROVIDER=fake docker compose up -d core` : **1 passed (7,6 s)** (brouillon intact, jeton d'audience MCP, 25 tours sans 422).
- `restore-reconnect.spec.ts` : **2 skipped** par conception (`test.skip(PHASE !== "before"/"after")`, l.62 et l.84) ; ne s'exécute qu'avec `restore-oidc.sh`.

Bilan : 3/3 tests exécutables verts une fois la stack correctement configurée ; aucun défaut produit, deux défauts de configuration d'environnement.

Etat final : `core` et `shell` recréés avec leurs valeurs `.env` d'origine (sans `fake`, shell revenu au défaut `mock`), `healthy`. Les 5 services de base relancés restent démarrés.

## 4. Non rejoué, et pourquoi

| Stage / lettre | Statut | Raison |
|---|---|---|
| `restore-oidc` (REV-164 b, phase before/after de `restore-reconnect`) | non rejoué | destructif (`down -v`) ; la stack contient des volumes (`pg-data`, minio) de plus de 5 semaines. Consigne : pas de `down -v` sur données de valeur. |
| `up` (`--build`, `enable-flags.sh`, `seed-personas.sh`, `stack-reset.sh snapshot`) | non rejoué | reconstruit les images et écrase l'état de référence ; non nécessaire, la stack a été relevée à l'identique. |
| `journeys --lane all --verify` (REV-272 c, 273 a, 275, 276, 277, 278 d, 280 b, 282 a, 283 f, 284 a, 285 i, 286 c auto) | non rejoué | suite longue et lourde (WSL2 ~12 Go, runbook §2 : une seule session lourde), dépend des flags d'audit et de personas semés par `up` ; collisions possibles avec d'autres agents sur Postgres partagé. |
| `e2e-mock` (`npm run e2e`) | non rejoué | suite complète interdite par la consigne ; nécessite aussi un shell en mock géré par Playwright. |
| `admin-tools` (REV-274 a) | non rejoué | exige `CORE_ADMIN_TOOLS_ENABLED=true` et le mode journeys (`AUDIT_AUTH=oidc`), absents de `.env` courant. |
| `plans`, `measure` (REV-279 c, 280 d, 283 f 10^6) | non rejoué | écrivent/peuplent une base Postgres ; consigne de ne pas toucher aux bases partagées. |
| `rebuild-images` (REV-274 b) | non rejoué | rebuild lourd ; titiler (`healthy`) et otel-lgtm (`healthy`, up 2 jours) répondent déjà, sans preuve de reconstruction. |
| `smoke` (REV-281 d) | non rejoué | `stack-smoke.sh` exige `CORE_AUTH_MODE=mock` ; stack en `oidc`. Le job GitHub `stack-smoke` reste `externe`. |
| REV-284 d / 286 c manuels | externe | humain (lecteur d'écran, appareil tactile réels). |

## 5. Recommandations

1. Documenter dans le runbook §3.5 que `VITE_AUTH_MODE=oidc` et `CORE_LLM_PROVIDER=fake` doivent être posés avant `run.sh oidc` si la stack n'a pas été montée par `run.sh up`.
2. Après tout redémarrage de WSL, `docker compose up -d` suffit (volumes intacts) ; la boucle de redémarrage de core/worker/martin était uniquement due à pgbouncer arrêté.
3. Le rejeu complet (journeys, plans, mesures, restore) reste à planifier dans une session dédiée, seul sur la machine.
