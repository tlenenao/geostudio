# Rapport de rejeu REV-27 (Z3) — partiel, interrompu

Date : 2026-10-11, HEAD 826988b6, stack rebuild via `scripts/replay/run.sh up` (log `.replay-results/20261011-115905/up.log`).
File du worker vérifiée par valeur (`docker compose config`) : `-q ingestion,search,cdc,etl,tileset3d,terrain3d,appexport,harvest,dataexport` — OK.

## Exécuté : `run.sh journeys --lane all --verify` (arrêté pendant j05b)

Résultats : `.audit-results/20261011-120419/` (`j01..j05.json`, `*.log`).

| Dossier | Résultat | Classement |
|---|---|---|
| j01 | 36 passed, 1 failed (« GET /v1/public/items : catalogue vide valide ») | env : base de référence polluée (items publiés datant de sessions antérieures) |
| j02 | 30 passed | OK |
| j03 | 39 passed, 1 failed (menu ⋯ publie la carte, j03-012) | à rejouer seul, non classé |
| j04 | 40 passed | OK |
| j05 | 45 passed, 14 failed, 1 skipped (j05-009 reste `bug(`, skipped) | env probable : liste « Collection de base » sans la collection de seed (185 collections / 493 items en base) |
| j05b | tous les tests d'exécution en timeout 4-5 min | même cause probable, non conclu |

## Cause de l'arrêt

`run.sh up` a re-snapshoté (`stack-reset.sh snapshot`) une base déjà polluée par des rejeux antérieurs (185 collections, 493 items, ~230 tables `ingest_*`/`query_*`, dont ~60 000 à 500 000 lignes). Chaque `reset` restaure donc cette base polluée : parcours sensibles à l'état vide ou à la pagination (j01, j05, j05b) non fiables. L'assainissement (TRUNCATE ciblé des tables de contenu + DROP des tables `ingest_*`/`query_*`) a été refusé par le classificateur de permissions ; le rebuild sur le nouveau `dev` (25e33cb1, demandé en cours de session) l'a également été. Rien n'a été modifié en base ni dans le code.

## Non rejoué (à faire après décision de Tanguy)

- t03 (t03-009, t03b-002, REV-283), j05b-006, j10-006, j05-009, REV-321 (`--workers=2`), `bug()` REV-275/318/319, parcours G2, j06/j06b/j09b, tileset3d, e2e-oidc/LCP (REV-267) : « non mesuré ».
- Aucun `bug(` basculé en `test(`.
- Rejeu après les correctifs 25e33cb1 (tileset3d /complete, budget share-link, restore.sh, GroupShare.name) : non fait.

## Pour reprendre

1. Autoriser (ou exécuter soi-même) l'assainissement de la base de référence, ou accepter `down`/recréation de la base `gis` + `seed-personas.sh` + `stack-reset.sh snapshot`.
2. `docker compose up -d --build core worker shell`.
3. `scripts/replay/run.sh journeys --lane all --verify`, puis rejeu sans `--verify` des bascules.
