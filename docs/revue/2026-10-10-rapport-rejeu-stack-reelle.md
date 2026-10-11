# Rapport du rejeu destructif sur stack réelle (REV-164, 266, 267, 281, 284, 286, 292, 318, 319)

- Date : 2026-10-10 à 2026-10-11 — `dev` au départ `a333d2ff`, commits de ce rejeu listés en §4 (aucun push).
- Machine : WSL2 (~12 Go, mémoire disponible toujours > 5 Go pendant le rejeu), stack Compose complète (profils `export`, `appexport`, `observability`), OIDC réel Keycloak ; `mock` pour `e2e-mock`/`smoke`.
- Autorisation : rejeu destructif de la stack **locale** (`down -v`, `restore-oidc`) donné explicitement par Tanguy ; rien hors du projet compose n'a été touché.
- Logs : `.replay-results/20261010-184933/` (stages, `summary.txt`), `.audit-results/<ts>/<dossier>.json` (parcours). Non versionnés.

## 1. Stages (`scripts/replay/run.sh`)

| Stage | RC | Preuve / remarque |
|---|---|---|
| preflight | 0 | `preflight.log` |
| up | 1 puis 0 | `up.log` : 1er démarrage à froid, healthcheck du cœur dépassé ; relancé une fois le cœur sain (cf. REV-320, à re-mesurer avec le `start_period` 180 s) |
| journeys `--verify` (voies parallèle + série) | 0 (le stage rend 0 même avec des échecs) | `.audit-results/20261010-185843`, `214444`, `221839` : tous les `bug()` rejoués comme `test()` |
| e2e-mock | 0 | `e2e-mock.log` : 247 passed / 4 skipped / 0 failed |
| oidc | 0 | `oidc.log` : 3 passed / 2 skipped (LLM `fake` pour `copilot-oidc`) |
| admin-tools | 0 | `admin-tools.log` (stack OIDC) |
| plans | 1 puis 0 | RC 1 : `CORE_TEST_DATABASE_URL` absent de l'hôte ; relancé dans le conteneur cœur. Base de la stack < 1000 lignes (INCONCLUSIF) ; base jetable peuplée : 6/6 `INDEX` (`plans-populated.log`) |
| measure | 1 puis 0 | même cause, relancé dans le conteneur cœur : `measure-pk.log`, `measure-groupby.log` |
| rebuild-images | 0 | `rebuild-images.log` |
| smoke | 1 puis 0 | RC 1 : `S3_PUBLIC_ENDPOINT_URL` absent de `.env` local (REV-315, environnement) ; ajouté, `smoke.log` vert |
| restore-oidc | 1, 1, 1, 1, 1 puis 0 | cf. §3 (REV-164) et §4 : 2 défauts produit trouvés et corrigés ; `restore-oidc.log` (RC 0 final), spec `e2e-oidc/restore-reconnect.spec.ts` : phase *before* puis phase *after* vertes |
| journeys (rejeux sans `--verify`, après correction) | 0 | cf. §5 |

## 2. Mesures

```
RESULT pk_sort rows=1000000 exec_ms=58.0 explicit_sort=False
RESULT groupby card=10000 limit=2GB status=ok rss_peak_mb=152 delta_mb=101
RESULT groupby card=100000 limit=2GB status=ok rss_peak_mb=234 delta_mb=183
RESULT groupby card=1000000 limit=2GB status=ok rss_peak_mb=430 delta_mb=379
RESULT groupby card=5000000 limit=2GB status=ok rss_peak_mb=1405 delta_mb=1353
plans : 6/6 INDEX sur base peuplée (20 000 lignes/table)
```

**LCP du catalogue (REV-267, Lighthouse 12, profil mobile, throttling par défaut, Chromium Playwright, build de la stack)** : `.replay-results/20261010-184933/lh/catalog_.json` et `catalog_public.json`.

| URL | LCP | FCP | CLS | TBT | Score perf |
|---|---|---|---|---|---|
| `/` | **3,8 s** | 2,9 s | 0,068 | 50 ms | 0,82 |
| `/public` | **3,1 s** | 2,7 s | 0,026 | 0 ms | 0,90 |

Seuil « bon » = 2,5 s : les deux pages sont au-dessus. Le chemin critique est dominé par le chargement de `index.js` (le FCP est déjà à 2,7-2,9 s).

## 3. Verdict par REV

| REV | Verdict | Preuve / raison |
|---|---|---|
| **164** | **fermable** | Sauvegarde puis restauration sur stack vidée (`down -v`), reconnexion OIDC complète avec le même compte, carte visible : `restore-oidc.log` RC 0, `restore-reconnect.spec.ts` 2 passed. Deux défauts produit trouvés et corrigés (§4) : `restore.sh` ne recréait pas les rôles `gis_rls`/`gis_rls_masked` (globaux au cluster, absents des dumps) avant `pg_restore` ; `restore-oidc.sh` remontait le shell en `mock`. |
| **266** | **fermable** | Les parcours `shell/e2e/journeys/` et `e2e-oidc/` ont tourné sur la stack réelle OIDC avec les flags d'audit allumés (ETL compris) : `.audit-results/20261010-185843/`, `214444`, `221839`, puis rejeux verts dossier par dossier (§5). Les écarts trouvés sont qualifiés un par un (§4, §6) : 0 échec de `test()` restant hors flake de charge identifié. Réserve : `j09`/`j09b` voir §5. |
| **292** | **fermable** | `t01b`, `t02`, `t03`, `t04`, `j06b`, `j11` rejoués sur stack OIDC réelle : `t02` 37/0 échec, `t03b` 24/0, `j11` 23/0 (`.audit-results/20261010-232953/`) ; `t04`/`j06b` verts (`20261010-221839`, sous `--verify`, après alignement). `t03` : 1 échec de perf marginal (2 050 ms pour un seuil de 2 000 ms, machine chargée), cf. §6. |
| **267** | **reste partielle** | LCP **mesuré** : 3,8 s (`/`) et 3,1 s (`/public`), > 2,5 s. Reste : alléger `index.js` selon cette mesure, filet E2E du rendu canvas. La partie « mesurer » est close. |
| **318** | **reste partielle** | 12 `bug()` basculés en `test()` (§5), 3 parcours périmés réécrits (t02-003, t02-013, j13), 2 bugs de harnais (sonde copilote, `run_export.py`). Les `bug()` restants sont triés au §6 : défauts produit à ouvrir en REV, un problème d'environnement (`unzip`), le reste à décider. Le lot n'est pas fermable tant que ces défauts persistent. |
| **319** | **reste partielle** | `j10`/`j10b`/`j11`/`j13` rejoués : `j10` 47/0 échec, `j10b` 22/0, `j11` 23/0, `j13` 23/0 ; 11 `bug()` basculés. Persistent : `j10-004/006/007`, `j10b-004/005/007`, `j11-007` (UI copilote), `j13-005/007/008/009` : triés au §6. |
| **281 (d)** | **reste partielle (externe)** | `smoke.log` vert en local ; le job GitHub `stack-smoke` exige un push / une PR, non fait. |
| **284 (d)** | **reste partielle (externe)** | Lecteur d'écran réel : non exécutable ici. |
| **286 (c)** | **reste partielle (externe)** | Appareil tactile réel : non exécutable ici. |

## 4. Défauts produit trouvés par le rejeu, et leurs commits

| Commit | Défaut | Test |
|---|---|---|
| `4313a3b5` | `deploy/backup/restore.sh` : `pg_restore` échouait (`role "gis_rls" does not exist`) sur une stack vidée : les rôles globaux ne sont pas dans les dumps. Le script les recrée avant la restauration. | `core/tests/test_restore_script.py` (+1 test, 5 verts) |
| `53611986` | `scripts/replay/restore-oidc.sh` : l'`up -d` final remettait le shell en `mock` (`VITE_AUTH_MODE` non exporté) : la reconnexion OIDC ne pouvait pas être vérifiée. | rejeu `restore-oidc` RC 0 |
| `2d122104` | `ensure_geo_limit_policy` : installation concurrente de la fonction partagée `app_geo_limit_fn` (`CREATE OR REPLACE`) → 500 à la création simultanée de deux collections (parcours `j02`/`j04`, « col 500 »). Verrou consultatif transactionnel. | `core/tests/test_geo_limits_postgis.py::test_concurrent_policy_install_does_not_race_on_the_shared_function` (falsifié : échoue sans le verrou) ; 11 verts |
| `fed64f6a` | `SessionExpiredBanner` s'affichait à un visiteur anonyme (REV-318). Ne s'affiche plus que si la session a été authentifiée. | `SessionExpiredBanner.test.tsx` (+1 test anonyme, falsifié) |

Parcours périmés (aucun défaut produit) réécrits : `8be46d99` (j02 : le Lecteur crée des bookmarks, décision REV-318), `t02-003` (le contrat est `If-Match` → 412, pas 409 sans en-tête), `t02-013` (`/health` porte `jobsBacklog` en plus de `status`), j13 (matrice de création, administrateur membre de groupe via `admin.users.manage`, constats de défauts désormais corrigés retirés), j11 (la sonde `copilot_probe.py` ne neutralisait pas l'audit `copilot.turn` ni `get_session` introduits depuis : tout répondait 500 ; l'inventaire d'outils suit `etlEnabled`), j08 (`« 1 utilisateur(s) »`), t02 (`Annuler l'import` existe depuis D6, `Annuler` du tiroir reste verrouillé), j10 (sélecteur de type du tiroir, tests « capacité éteinte » qui s'auto-ignorent quand la capacité est allumée), j10b (`runExport` : le job est désormais réellement différé, le worker d'export peut l'avoir pris, on attend son état terminal ; budget `collections_empty` 5/min, attente de la fenêtre), t04/j03/j06b (cf. commit `test(shell): t04, j03, j06b, j10b rejoués…`).

## 5. Bascule `bug(` vers `test(`

Règle du runbook : seul un `passed` JSON sous `--verify` compte, puis rejeu **sans** `AUDIT_VERIFY` (0 échec attendu).

- Basculés : `j13-001` (API + UI), `j13-002`, `j13-003`, `j13-004`, `j13-006`, `j13-010` ; `t02-003`, `t02-008`, `t02-013` ; `j10-001`, `j10b-001`, `j10b-002`, `j10b-003`, `j10b-006`, `j10b-008`, `j10b-010`, `j10b-011`, `j10b-012` ; `j11-003`, `j11-007` (brouillon SQL) ; `j12-001` (×2) ; `j09b-001` (rejeu : voir ci-dessous).
- Rejeux sans verify, 0 échec : `j13` 23 passed / 4 skipped (`.audit-results/20261010-224324` verify, puis `20261010-225038`) ; `j08` 56/0, `j11` 23/0, `t02` 37/0, `t03b` 24/0 (`20261010-232953`) ; `j10b` 22/0 (`20261011-000304`) ; `j10` 47/0 (dernier rejeu) ; `j12` 30/0 (`20261010-235135`).
- Falsification : les flips reposent sur le fait que le même test échouait quand le défaut existait (verify rouge avant le correctif produit pour `j13-001/002/003/006/010`, parcours « constat » jumeaux qui assertaient l'ancien défaut et sont devenus rouges au correctif : `constat j13-001/002/003/010/006`, 5 occurrences observées). Pas de falsification par injection pour les autres.
- `j09b` rejoué seul sans `--verify` : 23 passed / 2 skipped / 0 échec (`.audit-results/20261011-*/j09b.json`, dernier dossier), `j09b-001` basculé et vert. `j09` : 46 passed / 5 skipped, 1 échec : `balayage périodique réel` (j09b) dans la passe combinée `j09 j09b j09c`, jeton Keycloak de 5 min expiré pendant l'attente de deux cycles de balayage (le corps devient une erreur, plus un tableau) ; harnais corrigé (jeton renouvelé à chaque sondage), le même test est vert dans la passe `j09b` seule.

## 6. Défauts persistants (`bug()` restants), qualifiés

Qualification faite sur le message d'échec sous `--verify` et le code ; « produit » = à ouvrir en REV, « parcours » = assertion à réécrire, « env » = environnement.

| Test | Nature | Observation |
|---|---|---|
| j02-001 | parcours probable | `GET /items?scope=<inconnu>` répond sans `items` (pas de fuite observée) ; à réécrire vers le contrat réel (422 ?) |
| j02-005 | produit / décision | un Lecteur voit les noms de tous les groupes du tenant (`GET /groups`), y compris « groupe-secret » : annuaire, à trancher (P14) |
| j03-003 | produit (compromis) | job `pending` après échec de mise en file : repris par le balayage périodique (SP-49) mais pas immédiatement |
| j03-012 | produit | carte publiée dont la collection reste privée : la collection répond 404 à l'anonyme, aucun signalement à la publication |
| j04-008 | parcours | l'écriture concurrente sans `If-Match` réussit (opt-in, REV-271) ; à réécrire avec `If-Match` |
| j04-010 | produit | un refus serveur sur un champ absent du formulaire n'est pas signalé (aucun `alert`) |
| j05-009 | env | `unzip` absent de l'hôte |
| j05-016, j05-018, j05b-001/004/006, j06b-002/006/008/013 | produit | candidats REV-308 à REV-313 du rapport du 2026-10-04, inchangés |
| j07-016 | produit / décision | le propriétaire de la collection ne lit pas ses propres champs sensibles (masquage sans exception propriétaire) |
| j08-009, j08-012 | parcours probable | écrans extensions / journal (locator introuvable après refonte UI) |
| j08b-004 | produit | dernier administrateur actif anonymisable |
| j09b-009, j09b-011 | produit | runs `running` périmés non repris (REV-314) ; lien de rapport en hôte Docker sans `S3_PUBLIC_ENDPOINT_URL` : défaut de configuration par défaut (REV-315), corrigé localement dans `.env` |
| j10-004, j10-006, j10-007 | produit / parcours | `/public/items` sans filtre ; retrait d'action de chapitre ; gel d'export statique (403 au semis par le Créateur) |
| j10b-004, j10b-005, j10b-007 | produit | widget tiers imbriqué refusé en statique (422) ; 50 001 lignes non signalées (plafond appliqué en amont) ; export d'un item non-app accepté |
| j11-007 (UI copilote) | env | exige un LLM, éteint volontairement |
| j13-005 | produit | l'identifiant utilisateur n'est pas affiché sur la page Paramètres |
| j13-007 | parcours | sélecteur ambigu (2 éléments), texte présent |
| j13-008 | produit | membre d'un groupe d'une carte partagée : sa collection répond 404 |
| j13-009 | produit | l'Administrateur ne peut pas dépublier l'item d'un autre (403) |
| t03-006, t03-009, t03b-002 | perf | marge de bundle, densité à z5, export 50k : inchangés ; `t03` « 4 repositionnements < 2 s » : 2 050 ms (limite machine) |

Observation produit hors périmètre, non modifiée : le catalogue envoie toujours `sort=date_desc` même avec une recherche `q` ; sur un tenant dont les données s'accumulent, la recherche par titre peut ne pas remonter la carte voulue sur la première page (71 correspondances floues pour une page de 12). Les parcours `j02`/`j03` de recherche y sont fragiles. Candidat REV.

## 7. Limites assumées

- `j09` : le correctif de jeton du test de balayage périodique n'a pas été rejoué en passe combinée (la passe `j09b` seule est verte).
- Les lettres 281 (d), 284 (d), 286 (c) restent externes (push GitHub, lecteur d'écran, tactile).
- `docs/revue/2026-09-04-backlog.md` et `CLAUDE.md` n'ont pas été modifiés : le changement d'état des REV ci-dessus est à reporter par Tanguy / la session suivante.
- La stack est laissée en `oidc`, flags d'audit allumés, `.env` local modifié (`S3_PUBLIC_ENDPOINT_URL`, flags d'`enable-flags.sh`).
