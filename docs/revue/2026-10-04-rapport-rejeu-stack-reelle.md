# Rapport du rejeu sur stack réelle (lot D, REV-164 et REV-272 à REV-286)

- Date : 2026-10-05 à 2026-10-07 — SHA de `dev` à la clôture de D8 : `b5938393` (D6/D7 sur les SHA antérieurs, cf. historique git).
- Machine : WSL2 (~12 Go), Docker 29.4.3, Node 22.22, stack Compose complète profils `export`, `appexport`, `observability`, `CORE_AUTH_MODE=oidc` (mock pour `e2e-mock`/`smoke`).
- Logs : `.replay-results/20261005-231144/` (stages), `.audit-results/<ts>/<dossier>.json` (journeys). Ces dossiers ne sont pas versionnés.

## 1. Stages (`scripts/replay/report.py`)

| Stage | RC | Log / remarque |
|---|---|---|
| preflight | 0 | `.replay-results/20261005-231144/preflight.log` |
| up | 1, 1, 0 | `up-attempt1.log`, `up-attempt2.log`, `up.log` : cœur sain après 90 s au 1er démarrage avec migrations ; Martin à relancer (`up -d martin`) |
| journeys parallèle `--verify` | 1 | `.audit-results/20261005-232446` : 466 ok / 131 ko (parcours périmés, cf. D7) |
| journeys, rejeu après alignement | tous verts hors `bug()` | `.audit-results/20261006-084558`, `20261007-010431` (voie parallèle), `20261006-192132`, `20261007-005123` (série) |
| e2e-mock | 1 puis flake | `e2e-mock-run1.log` : 238 passed / 4 skipped / 1 failed (`pipeline-builder.spec.ts:130`), vert 2 fois isolé |
| oidc | 1 puis 0 | `oidc-run1.log` : `auth-oidc` vert, `copilot-oidc` rouge (LLM éteint) ; `oidc-copilot-fake.log` vert avec `CORE_LLM_PROVIDER=fake` |
| admin-tools | 0 (oidc) | `admin-tools.log` |
| rebuild-images | 0 | Grafana `/api/health` ok (12.0.1), titiler starlette 0.52.1 |
| plans | 0 | `plans.log` (base stack < 1000 lignes : INCONCLUSIF) + `plans-populated.log` (base jetable peuplée : 6/6 INDEX) |
| measure | 0 | `measure-pk.log`, `measure-groupby.log` |
| smoke | 1 puis 0 | `smoke-run1.log` (`S3_PUBLIC_ENDPOINT_URL` manquant), `smoke.log` ok |
| restore-oidc | non exécuté | `down -v` interdit par la consigne |

## 2. Mesures (lignes `RESULT`)

```
RESULT pk_sort rows=1000000 exec_ms=58.7 explicit_sort=False
RESULT groupby card=10000 limit=2GB status=ok rss_peak_mb=147 delta_mb=95
RESULT groupby card=100000 limit=2GB status=ok rss_peak_mb=230 delta_mb=177
RESULT groupby card=1000000 limit=2GB status=ok rss_peak_mb=443 delta_mb=390
RESULT groupby card=5000000 limit=2GB status=ok rss_peak_mb=1201 delta_mb=1148
RESULT plan ... rows=20000 verdict=INDEX   (6 requêtes : audit_log, config_revisions, configs, report_runs, pipeline_runs, group_members)
```

- Décision `memory_limit`/`MAX_GROUPS` (REV-280 d) : `card=10000` consomme 95 Mo, soit 4,6 % de la limite de 2 Go (seuil de décision : 25 %). Valeurs **confirmées par mesure du 2026-10-07**, `aggregate.py` inchangé. À 5 M de groupes, 1148 Mo (56 % de la limite) : la limite tient encore.
- Plans (REV-279 c) : sur la base de la stack, les 6 tables ont moins de 1000 lignes (INCONCLUSIF, `plans.log`). Preuve retenue : base jetable `plans_scratch` créée dans le postgis de la stack (schéma réel par `pg_dump -s`, 20 000 lignes synthétiques par table, supprimée ensuite) : 6/6 `INDEX`, aucun `SEQSCAN`, y compris `group_members` sur `ix_group_members_user_id` (migration 0049).

## 3. Verdict par lettre

| REV | Lettre | Verdict | Preuve / raison |
|---|---|---|---|
| 164 | (b) | externe — non rejoué : `docker compose down -v` interdit pendant ce lot | `run.sh restore-oidc` à lancer sur une stack jetable |
| 272 | (c) | fermé | `.audit-results/20261006-084428/j01.json` (37/37) ; rejeu `20261007-013526/j01.json` vert |
| 273 | (a) | fermé | `j06-004` retiré (`fcd5282f`) : l'egress DSN est contrôlé à l'exécution (`connector_runtime`), preuve `j06b-010` verte (`20261007-010431/j06.json`) |
| 274 | (a) | fermé | `admin-tools.log` RC 0 sur stack OIDC |
| 274 | (b) | fermé | `rebuild-images.log` : Grafana 12.0.1 `/api/health` ok, titiler starlette 0.52.1 |
| 275 | (a) | partiel | `j06b` vert hors `j06b-006`/`008`/`013` ; `t03b` vert hors `t03b-002` (`20261007-010431/j06.json`, `20261007-005123/t03.json`) |
| 275 | (b) | fermé | `j06b-001/014/015/016` basculés en `test()` (commits `3c78ac3d`), rejeu sans verify vert (`.audit-results/20261007-013526/j06b.json`). `j06-012` : introuvable dans `shell/e2e/journeys` (`grep` vide), rien à basculer |
| 276 | (a) | partiel | `j07` vert hors `j07-016` (`20261007-010431/j07.json`) |
| 277 | (a) | partiel | `j02`, `j09`, `j09b` verts hors `j02-001`/`005`, `j09b-001`/`009`/`011` |
| 278 | (d) | partiel | `j01 j03 j04 j08 j09` verts hors `bug()` persistants (`j03-002/003/012`, `j04-008/010`, `j08-009/012`) ; `npm run e2e` : 238 passed / 4 skipped / 1 flake isolé vert |
| 279 | (c) | fermé | `plans-populated.log` (base peuplée synthétique, schéma réel) ; la base réelle seule reste INCONCLUSIF |
| 280 | (b) | partiel | `j05`, `j05b`, `t03b` verts hors `j05-009/016/018`, `j05b-001/004/006`, `t03b-002` |
| 280 | (d) | fermé | mesure `groupby` ci-dessus, valeurs confirmées sans changement de code |
| 281 | (d) | externe — non rejoué : le job GitHub `stack-smoke` exige un push/PR | `smoke.log` vert en local seulement |
| 282 | (a) | partiel | `j03`, `t02` verts hors `t02-003` (API 409)/`008`/`013`, `j03-002/003/012` |
| 283 | (f) | partiel | tri PK 58,7 ms sans tri explicite (fermé) ; `j03 j09 t03 t03b` verts hors `t03-006`, `t03-009`, `t03b-002` |
| 284 | (a) | fermé | `t01`, `t01b` verts (`20261006-084558/t01*.json`), `j03` vert hors `bug()` |
| 284 | (d) | externe — non exécutée : lecteur d'écran réel | `docs/revue/2026-10-04-rejeu-procedures-manuelles.md` §B |
| 285 | (i) | fermé | `t04`, `j06` verts ; `oidc-run1.log` (`auth-oidc`) et `oidc-copilot-fake.log` (`copilot-oidc`) verts |
| 286 | (c) | externe — partie manuelle (appareil tactile réel) non exécutée | `j02`, `j03`, `j12` verts hors `bug()` ; procédure §A du fichier manuel |

## 4. Défauts révélés par le rejeu et leurs commits

- `group_members(user_id)` sans index (Seq Scan) : migration 0049 `CONCURRENTLY` + test, commit `8459743e`.
- Semis `sensitiveFields` par un Créateur : 403 voulu (P13), harnais corrigé `1058a411`.
- Alignements de parcours périmés (aucun défaut produit) : `06abda36` (j05b), `c82f6fa8` (j06b-015/001), `3b57c956` (j09b alertes), `154f566b` (j08/j08b), `177513de` (j09/j09b), `ad64de75` (t02), `4b9b037d` (t03/t03b), `cbd9531b` (j05b analyste).

## 5. Bascule `bug(` vers `test(` (D8)

Règle : dernier statut `passed` sous `--verify` dans les JSON de `.audit-results/`, puis rejeu sans `AUDIT_VERIFY` (514 passed, 3 failed, aucun test basculé en échec ; les 3 échecs sont des `test()` préexistants, `j02 reader-ui:41`, `j03 map-ui:233`, `j09b alerts-delivery:273`, tous verts isolés : flakes de charge). 56 tests basculés, un commit par dossier : j01 `2fa3ba66`, j02 `cc59a946`, j03 `1dc2ce28`, j05 `48c87200`, j05b `4d4b9233`, j06b `3c78ac3d`, j07 `ba8cc64d`, j08 `2b7ac6eb`, j08b `677c3ba6`, j09 `e2654218`, j09b `35f4c079`, t02 `3df22858`, t03 `54bc2f08`, t03b `b5938393`. Dont les candidats annoncés : `j06b-001`, `j08-002`, `j08-011`, `j08b-010`, `j09b-010`, `j09b-013`, `t03-004`. Non basculés car non vus passer au dernier rejeu : `j08b-002` (rouge), `j09b-001` (rouge). `j06b-002` laissé en `bug()` (flake d'état vu une fois).

Falsification (piège n°10) : `t03-004` (`j06-004` n'existe plus). Défaut injecté : un serveur local sur le port 8399 servant `/fixtures/gauge-extension-widget.js` et `/.vite/manifest.json` en 200, visé par `SHELL_URL=http://localhost:8399` : le test échoue (statuts reçus 200 au lieu de 404). Retour au shell réel : il repasse. Une première tentative (fichier déposé dans le conteneur `shell`) n'avait pas mordu car nginx refuse `/fixtures/` et `/.vite/` explicitement (`default.conf`) ; le conteneur est resté intact.

## 6. Défauts persistants triés en candidats REV (numéros provisoires, dernier REV existant : REV-307)

| N° provisoire | Défaut | Tests `bug()` | Nature |
|---|---|---|---|
| REV-308 | Colonnes entières nullables écrites en double dans le GeoParquet du lac : `writer.collection` refuse la ligne (`montant expected integer`) | j05b-004 | défaut produit, cause racine probable `parquet_writer.build_geodataframe` |
| REV-309 | L'assistant de requête visuelle liste `GET /collections` (100 par défaut, sans recherche) : un tenant > 100 collections ne peut pas choisir sa base | j05b-001/006 (à confirmer) | défaut produit |
| REV-310 | Second `POST /run` accepté pendant un run en cours (pas de 409) | j06b-006 | défaut produit |
| REV-311 | Colonne ajoutée après l'écriture du GeoParquet : `Binder Error` au run | j06b-008 | défaut produit |
| REV-312 | Cron « 1er janvier 3h » exécuté au premier balayage | j06b-013 | défaut produit |
| REV-313 | Filtre `__in` découpé sur la virgule | j05-018 | défaut produit |
| REV-314 | Rapport planifié / évaluation `pending` et run `running` périmés non repris | j09b-001/009 | défaut produit à qualifier |
| REV-315 | `S3_PUBLIC_ENDPOINT_URL` vide par défaut : URL présignées en hôte `minio`, injoignables du navigateur (la CI le fixe) | j03-002, j09b-011 | configuration par défaut |
| REV-316 | Marge de 5 % sous le seuil de bundle non tenue (734 Ko) | t03-006 | perf |
| REV-317 | `t02-003` (409 sur version périmée), `t02-008` (401 invite à se reconnecter), `t02-013` (arrêt du worker observable) | t02 | résilience |
| REV-318 | Lot de `bug()` non triés au rejeu : j02-001/005, j03-003/012, j05-009 (environnement `unzip`)/016, j05b-006, j07-016, j08-009/012, j08b-002/004, t03-009, t03b-002, j04-008/010 | divers | à re-trier un par un |
| REV-319 | `j10`, `j10b`, `j11`, `j13` : `bug()` non rejoués depuis D6 (statut d'avant les alignements), à rejouer | j10-004/006/007, j10b-004/005/007/008/011, j11-007, j13-005/007/008/009 | non rejoué |
| REV-320 | Le healthcheck du cœur est trop court au premier démarrage avec migrations (`up` RC=1 deux fois) ; Martin sans redémarrage sur échec de login pgbouncer | — | exploitation |
| REV-321 | Parcours à rafraîchir en masse pour tenir sous charge (3 flakes `test()` en voie `--workers=2`) | j02 reader-ui:41, j03 map-ui:233, j09b:273 | tests |

## 7. Limites assumées

Les lettres 164 (`down -v`), 281 (d) (push), 284 (d) et 286 (c) (humain) ne sont pas fermées. Aucune lettre n'est marquée fermée sur la foi d'un récit : chaque verdict `fermé` cite un chemin de log ou de JSON.
