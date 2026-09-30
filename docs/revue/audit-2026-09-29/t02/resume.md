# t02 — Résilience et erreurs (résumé)

Stack réelle, auth OIDC (Keycloak), personas `audit-*`. 14 findings (S2 : 4, S3 : 8, S4 : 2), 37 tests Playwright
(22 passent tels quels + 1 test de session de 6 min, 14 `test.fixme` renvoyant aux findings).

## Périmètre couvert

- 401 (absence, jeton corrompu/tronqué, schéma non Bearer) sur 7 familles ; 404 sur identifiants inconnus ; 403 du Lecteur sur les écritures ; 409 (slug) ; 422 ; 429 (budget `collections_empty`, `Retry-After`, problem+json). Balayage OpenAPI : ~140 GET avec identifiants inexistants, aucun 5xx.
- Réseau : coupure (`route.abort`) puis retour, bannière de connectivité, « Réessayer », timeout 15 s + rejeu, hors ligne (`setOffline`), 401 injecté, 429/409(quota) injectés sur la création, coupure pendant création / enregistrement.
- Double soumission (Créer, Enregistrer, avec un écart humain de 60 ms entre clics), retour/avance après création, deux onglets (écriture périmée), écritures concurrentes de l'API (10 PUT).
- Renouvellement silencieux du jeton après 5 min (`session survit…`, passe, 0 réponse 401 après expiration).
- `docker stop`/`start` de `worker` puis `martin` (exception à la règle 6, `healthy` confirmé avant de continuer ; état final `Up (healthy)` pour les deux) : le cœur, le shell et les tuiles (servies par le cœur) restent utilisables ; un job d'ingestion mis en file pendant l'arrêt reste `pending`/`todo` puis passe `done` au redémarrage ; aucun signal côté health/instance/shell (t02-013). Martin n'est consommé par aucune route du produit (seule la passerelle `/admin/martin`, désactivée ici).

## Non couvert (et pourquoi)

- Quotas (items, collections, stockage), ETL/pipelines, export, admin-tools, copilote LLM : capacités éteintes sur la stack ; seul l'affichage d'un 409/429 simulé a été exercé (t02-014 en hypothèse).
- Ingestion réelle de bout en bout via l'UI : `POST /uploads` et `/uploads/presign` répondent 500 (j03-001/j03-002) ; le pipeline d'upload est simulé par `page.route` (t02-010/011), le job réel est mis en file depuis le conteneur core.
- Rate limit : seul le groupe `collections_empty` (5/min) a été franchi ; le fait que la plupart des routes (uploads, public, écritures d'items) n'aient aucun budget est lu dans `core/app/ratelimit/limiter.py`, pas mesuré.
- Enregistrement effectif d'une table Keycloak comme collection (t02-005) : non exécuté, il altérerait les tables d'authentification ; seule la liste des candidats est prouvée.
- Perte de la base ou de S3 (la sonde `/health` statique n'a donc pas pu être contredite autrement que par lecture de code) ; arrêt de tout service autre que `worker`/`martin`.
- Le test 429 (`@audit-flaky`) échoue s'il est rejoué dans les 60 s (le budget du jeton `reader` n'est pas encore remis à zéro).

## Méthode

Sondes `curl`/python (jetons Keycloak par mot de passe) pour cadrer, puis specs Playwright (`api-errors`, `connectivity`, `session-import`, `services-down`) ; chaque `fixme` a été rejoué avec `T02_VERIFY=1` pour prouver qu'il échoue sur l'assertion visée. Les objets créés portent le préfixe `aud-t02-` (`stamp("t02")`) ; un item de 40 Mo et trois items de sonde ont été supprimés après usage.

## Commandes lancées

- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/t02 --grep-invert "session survit"` : 22 passed, 14 skipped (fixme).
- `T02_VERIFY=1 npx playwright test … e2e/journeys/t02/<fichier> -g "t02-0"` : les 14 fixme échouent sur l'assertion visée.
- `npx playwright test … e2e/journeys/t02/session-import -g "session survit"` : 1 passed (5,9 min).
- `npx eslint e2e/journeys/t02` et `npx prettier --check e2e/journeys/t02` : verts.
- `docker stop|start geostudio-worker-1` puis `geostudio-martin-1` (via `withServiceStopped`), `docker compose ps` de contrôle.
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/t02 --repo-root ..`

## Findings notables déjà connus, non re-signalés

j03-001/j03-002 (uploads 500), j03-003/j03-019 (job pending, catch générique), j12-001 (worker MapLibre octet-stream, contourné par `fixWorkerMime`), t04-010/t04-011 (500 en lecture), c08 (404 text/plain, 422 non 7807), j04-003 (garde de brouillon), j08-005 (noms de rôles dupliqués).
