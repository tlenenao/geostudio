# Audit j02 — Lecteur connecté

## Périmètre couvert
- Connexion OIDC (audit-reader), rôle Lecteur (0 privilège), navigation sans entrées d'administration.
- Visibilité : items privés/partagés, 404 sur objets privés (items, collections, tuiles, STAC), écritures et routes d'admin en 403.
- Recherche du catalogue (titre, accents, caractères spéciaux, aucun résultat), filtre de portée, état vide « Mes éléments ».
- Fiche dataset, éditeur de carte en lecture seule, ouverture d'app/bookmark par ?ctx=, bookmark sur app privée.
- Pièces jointes (liste, présigné), notifications (badge, échappement, marquage lu, préférence).

## Périmètre NON couvert
- Popups de carte et rendu des tuiles vectorielles : aucune requête de tuile z>0 observée en headless, cause non établie.
- Qualité de la recherche sémantique : fournisseur d'embeddings factice (CORE_EMBEDDING_PROVIDER=fake) ; j02-012 reste « probable ».
- Envoi d'une pièce jointe : bloqué par j02-002.
- Course de première connexion (get_or_create_user) : non observée, les utilisateurs existaient déjà.
- Données de test insérées en SQL (docker exec psql) à cause de j02-002 et j02-003.

## Méthode
Seed via API en tant que creator (groupe contenant le lecteur, collections, dataset, carte, apps, bookmarks), puis tests API (jeton Keycloak, mot de passe grant) et UI Playwright OIDC, un worker. Lecture du code pour localiser chaque finding. 30 tests : 17 passent, 13 `test.fixme` (un par finding vérifié, sauf j02-015 couvert par un test passant).

## Commandes lancées
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j02`
- `docker logs geostudio-core-1`, requêtes psql (information_schema, insertion de lignes)
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j02 --repo-root ..`
