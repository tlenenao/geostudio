# j01 — Visiteur anonyme (résumé)

## Périmètre couvert
- Shell anonyme en OIDC réel (aucun login) : redirection des routes protégées, /sites/:slug, /public/items/:pk, /public/datasets/:id, /embed/:token (invalide, forgé, vide), /apps/:pk, mobile 360px.
- API publique : /v1/public/{items,sites,configs,sitemap.xml,robots.txt,social-preview}, /v1/share-links/{token} (jetons pathologiques), routes privées (401), écritures anonymes refusées, collections/STAC/DCAT publiques, absence de rate limit.

## Non couvert
- Chemins nominaux avec contenu (site publié rendu, item public, embed valide, lien expiré/révoqué, facettes/tri, aperçu social réel) : la base de reset est vide (0 item publié) et en créer exige un persona authentifié, interdit pour j01 (finding j01-010).
- Lecture des lignes d'une collection publique : bloquée par j01-004 (artefact du reset : USAGE sur schéma public manquant). Tous les agents lisant des features seront touchés tant que stack-reset.sh n'est pas corrigé.
- Sitemap/robots servis par Traefik (seo-static, seo-bots) : absent sur localhost, vérifié en lecture de docker-compose.yml seulement.

## Méthode
Lecture du code (routes shell, core/app/public, items, ratelimit), sondes curl, puis 34 tests Playwright (28 passent, 6 test.fixme j01-001..006 dont l'échec a été confirmé en retirant temporairement .fixme).

## Commandes
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j01` -> 28 passed, 6 skipped
- curl divers sur localhost:8200 / 8300 ; `docker logs geostudio-core-1` ; psql `\dn+` sur postgis.
- validateur audit_findings.py.
