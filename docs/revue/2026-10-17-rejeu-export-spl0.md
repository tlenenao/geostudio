# Rejeu sur stack réelle des correctifs export SP-L0 (AUD-133 / AUD-001 / AUD-003)

Date : 2026-10-17, branche `dev` @ `0a6a747c`, stack locale docker compose (`CORE_AUTH_MODE=oidc`, profils export+appexport+observability).
Aucun source modifié, rien commité. Seuls core, worker, export-worker, shell reconstruits (`docker compose up -d --build core worker export-worker shell`, ~6 min, tous `healthy`).

## Préparation
- Piège n°2 : `docker compose config` et `docker exec geostudio-export-worker-1 env` montrent `EXPORT_CORE_INTERNAL_URL=http://core:8200` (compose l.772, défaut `http://core:8200`). Câblé.
- Authentification : utilisateur Keycloak jetable `replay-spl0` (supprimé à la fin), jeton par grant `password` sur le client `geostudio-shell`, appelé sur `http://localhost:8200/v1/...`.
- Données (préfixe `replay-spl0-`) : collection vide Point (`nom` text, `pop` integer, 3 entités `Zorglub-Alpha/Bravo/Charlie`), dataset `source=collection`, app avec un widget `table` lié par `datasetId` (`layer=""`), app avec mesure `{"metric": "total_pop"}`.
- Bruit d'environnement : un `ReportSchedule` d'audit antérieur (item `ceb7ce37…`, `aud-j09-…-rep-app`, utilisateur `audit-creator`) rejoue toutes les 5 min un export qui expire à 120 s (`wait_for_selector`), et le worker d'export est sériel : mes jobs ont attendu 2 à 4 min dans la file. Sans lien avec SP-L0 (l'avant-correctif échouait déjà sur « cœur non joignable », cf. jobs `6f73c950…` 07:30).

## AUD-133 — pont Chromium + ctx : VÉRIFIÉ
- `POST /v1/export {itemId, format:"pdf", ctx:<base64url crossFilter>}`.
  - Sans filtre : PDF 16 921 o, 1 page, texte extrait (PyMuPDF) `nom pop Zorglub-Alpha 10 Zorglub-Bravo 20 Zorglub-Charlie 30` (job `e3ce2215…`, 1,8 s de rendu).
  - Avec `ctx` cross-filter (`{<datasetId>: {field:"nom", value:"Zorglub-Bravo", originSourceId:"other"}}`) : PDF 15 870 o, texte `nom pop Zorglub-Bravo 20` seulement : le ctx est bien transmis et appliqué (job `a2defa1a…`).
  - PNG avec ctx : 8 387 o, 794x1123, rendu visuel lu (tableau « nom/pop » avec la seule ligne Bravo), non blanc (job `937fbbe3…`).
- Le pont est actif : `core_bridge_target` renvoie `('http://localhost:8200', 'http://core:8200')` dans le conteneur (le cœur publié `localhost:8200` est injoignable du worker). Aucune erreur CORS/preflight en console Chromium, aucun souci de gzip/`content-encoding` observé (le tableau se rend avec ses données, via `route.fetch` + `route.fulfill(response=…)`). Les requêtes `GET /v1/collections/<id>/items` et `/schema` passent par le pont.
- Configuration cassée (relance de export-worker avec `EXPORT_CORE_INTERNAL_URL=http://nowhere.invalid:1`, puis remise à l'état normal, vérifié `http://core:8200`) : job en `error` avec le message utilisateur « L'export n'est pas disponible pour le moment (configuration du serveur). Contactez l'administrateur. » ; le détail (`localhost:8200`, `VITE_CORE_URL`, `EXPORT_CORE_INTERNAL_URL`) reste dans le journal du worker uniquement.

## AUD-001 — attente de disponibilité : PARTIEL
- Vérifié : harnais Playwright exécuté dans le conteneur export-worker (même pont, jeton d'export frappé avec le secret du worker), requêtes `/v1/collections/*` retardées de 6 s. `data-export-ready` ne se lève qu'à 13,6 s (deux requêtes sérielles `items` puis `schema`), contenu complet à ce moment ; pas de capture à moitié rendue.
- Non démontré : `data-export-incomplete`. Une requête qui ne se résout jamais n'atteint pas la garde de 90 s : le timeout de requête du shell (15 s, SP-B4) la convertit en erreur de données, la page devient « prête » à 32,6 s avec `exportIncomplete = undefined` et le texte « Connexion au serveur perdue… | Erreur de données ». Donc un export dont une source est en échec réseau serait livré en succès avec un widget « Erreur de données » (à confirmer côté job réel ; non rejoué en job, seulement dans le harnais). Le chemin `data-export-incomplete` → `USER_EXPORT_INCOMPLETE` reste couvert par tests unitaires seulement, non rejouable sans modifier le source.
- Observation (hors périmètre SP-L0, préexistante) : quand la page n'atteint jamais `baseReady` (app d'audit `ceb7ce37…`), le minuteur de 90 s ne démarre pas (`if (!baseReady) return`, `shell/src/shell/exportReady.ts`) ; le worker échoue au bout de 120 s et le message stocké/notifié est le texte brut Playwright (`Page.wait_for_selector: Timeout 119839ms exceeded. Call log: …`, `core/app/export/jobs.py:421-425`, `str(exc)`), pas un message français convivial.

## AUD-003 — appexport avec source `datasetId` : VÉRIFIÉ (3 modes), refus partiellement vérifié
- Collection non publique : les 3 modes refusent avec `source 's1' : collection 'query_…' n'est pas partagée publiquement` (la source `datasetId` est donc bien résolue vers la collection avant la garde). Collection passée `isPublic=true` ensuite.
- Statique (`app-aa72d1-static.zip`, 2 603 354 o) : `geostudio-app-config.json` avec `dataSources[0]` = `type:"static"`, `layer=<collectionId>`, `datasetId:null`, 3 enregistrements `Zorglub-*` embarqués.
- Connecté (`…-connected.zip`, 2 603 407 o) : config `type:"features"`, `layer=<collectionId>`, `datasetId:null` + `geostudio-connection.json`.
- Autoporté (`…-standalone.zip`, 5 444 o) : `data/geostudio-app-config.json` identique (`layer=<collectionId>`), `data/manifest.json`, `data/snapshot/tenant_id=default/collection_id=<id>/dt=snapshot/data.parquet` (10 953 o, contient `Zorglub`), `docker-compose.yml`, `README.md`. (Contenu parquet non lu au-delà de la présence des valeurs.)
- Refus mesure nommée : job `error`, « source 's1' : l'export ne supporte pas les métriques nommées du dataset — remplacez-les par des mesures explicites (champ + agrégat); source 's1' : l'export statique ne supporte pas encore les sources de type agrégat (statistics) » (testé en mode statique seulement).
- Non testé sur stack : dataset ArcGIS (`POST /v1/configs` refuse un `arcgisItemId` fictif : « arcgis layer not found ») ; le schéma `DatasetPayload` n'a que `collection|arcgis` (pas de dataset SQL/pipeline à ce stade). Message correspondant couvert seulement par `core/tests/test_appexport_datasets.py`.

## Verdicts
| AUD | Verdict |
|---|---|
| AUD-133 | vérifié |
| AUD-001 | partiel (attente de disponibilité vérifiée ; `data-export-incomplete` non rejoué) |
| AUD-003 | vérifié (static/connected/standalone) ; refus métrique vérifié, refus ArcGIS non testé |

Aucune régression SP-L0 trouvée. Deux observations à trier : (1) un échec réseau de source est livré en export « réussi » avec « Erreur de données » (timeout de requête 15 s < garde 90 s) ; (2) message brut Playwright exposé à l'utilisateur sur timeout de rendu quand `baseReady` n'arrive jamais.

## Nettoyage
- Supprimés via l'API : items `replay-spl0-app`, `replay-spl0-app-metric`, `replay-spl0-dataset`. Utilisateur Keycloak `replay-spl0` supprimé.
- Reste : collection `replay-spl0-col` (`query_b7b01a186efd`, **publique**, 3 entités) : `DELETE /v1/collections/{id}` renvoie 403 pour un utilisateur non admin ; à supprimer par un admin. Artefacts d'export dans MinIO (`renders/*`, appexports) laissés. Fichiers de travail dans le scratchpad de session (`/tmp/claude-1000/.../scratchpad/dl/`).
