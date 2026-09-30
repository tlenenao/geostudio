# j09b — Ops / instance (passe flags allumés)

## Couvert
- Passerelle /admin/grafana réellement en fonctionnement (Grafana otel-lgtm sur l'hôte :3011) : santé, dashboards GeoStudio provisionnés, sources Prometheus/Loki, 403 sans cookie, dashboard dans un navigateur sous le sous-chemin, expiration du jeton de lancement à 60 s (gateway-grafana.spec.ts). Findings 007 et 008.
- Alertes : livraison webhook réelle (payload, pas de renotification sans transition, retour à « ok », redirection vers 169.254.169.254 bloquée, cible muette abandonnée à 10 s), e-mail réel vers un SMTP jetable (authentifié, identifiants refusés sans fuite du mot de passe), STARTTLS, usage de secret SMTP par un Créateur, balayage */5 réel du worker (alerts-delivery.spec.ts). Findings 002 à 006.
- Rapports planifiés : balayage réel du worker, chaîne complète déclenchement -> rendu -> notification exécutée avec l'environnement du cœur, livraison webhook/e-mail/notification in-app, API des runs, validations (reports.spec.ts). Findings 001, 011, 013.
- Reprise de jobs : lignes périmées (2 h) plantées pour export, appexport, ingestion, pipeline, alerte ; observation des balayages réels (recovery.spec.ts). Findings 009, 010.
- Parité compose core/worker (finding 012, par lecture du compose).

## Non couvert, et pourquoi
- Jobs procrastinate orphelins à l'état « doing » (tué en vol) : exigeait de tuer le worker, interdit (stack non modifiable).
- Métriques du cœur dans Grafana : OTEL_EXPORTER_OTLP_ENDPOINT est vide sur cette stack (le profil n'a pas été choisi par install.sh), seuls les dashboards et sources sont vérifiés, pas les séries du cœur.
- Succès d'un rendu PDF Playwright par l'export-worker (en boucle de redémarrage, j05b-008) : le rendu abouti est simulé en base.
- Webhook livré par le worker réel : la garde d'egress SSRF bloque toute cible loopback/privée ; un conteneur jetable (réseau 11.77.0.0/24, env du cœur) exécute donc l'évaluation, le worker réel n'est observé que par ses balayages.
- E-mail : aucun SMTP dans la stack ; récepteur SMTP jetable (plain 2525, STARTTLS 2526) lancé et supprimé par les specs.
- Page infrastructure / état d'instance et passerelles Martin/Titiler : déjà couverts par j08b, non rejoués.

## Méthode
Récepteur jetable (`recv.py`) dans un conteneur sur un réseau docker dédié, démarré/arrêté par `helpers.ts`. Lignes de reprise insérées en SQL (horodatage -2 h) puis attente des balayages réels du worker (*/5, */15). Chaque test bug est `test.fixme` ; vérifié en le dé-fixmeant, il échoue pour la raison énoncée. 25 tests : 9 alertes, 5 passerelle, 6 rapports, 5 reprise.

## Commandes
```
cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j09b/gateway-grafana.spec.ts
cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j09b/alerts-delivery.spec.ts
cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j09b/reports.spec.ts
cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j09b/recovery.spec.ts
cd shell && npx eslint e2e/journeys/j09b && npx prettier --check e2e/journeys/j09b
```
