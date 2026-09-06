# GeoStudio

**Plateforme d'applications géospatiales open-source** : cataloguer des
données, cartographier, construire des apps/dashboards/sites **sans code**,
et automatiser leur mise à jour — avec un cœur pensé pour être piloté par un
agent IA (serveur MCP natif) autant que par un humain.

[![Licence](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](LICENSE)
[![CI](https://github.com/tlenenao/geostudio/actions/workflows/ci.yml/badge.svg)](https://github.com/tlenenao/geostudio/actions/workflows/ci.yml)
[![Version](https://img.shields.io/github/v/release/tlenenao/geostudio)](https://github.com/tlenenao/geostudio/releases)

---

## Ce que fait GeoStudio

Chaque point ci-dessous est une fonctionnalité qui fonctionne réellement de
bout en bout aujourd'hui (testée, mergée) — pas une intention de feuille de
route. Le détail complet, avec sa preuve dans le code, est dans
[`docs/revue/2026-09-04-matrice-fonctionnalites.md`](docs/revue/2026-09-04-matrice-fonctionnalites.md).

- **Cataloguer et partager** ses données et ses productions : recherche
  hybride (plein texte + sémantique), filtres par type/portée, partage par
  groupe ou publication anonyme sur un site public à URL dédiée, permissions
  fines calculées par élément (lire/écrire/supprimer/partager).
- **Cartographier sans code** : couches vectorielles (tuiles servies par le
  cœur) ou GeoJSON externe, symbologie déclarative (catégorielle, continue,
  classée — quantile/intervalle égal/Jenks), contours et icônes
  data-driven, étiquettes multi-champs, popups au clic avec gabarit Markdown
  et pièces jointes, terrain 3D et tuiles 3D hébergées.
- **Construire des apps, dashboards et sites** dans un builder no-code :
  grille responsive multi-breakpoints, une trentaine de widgets (carte,
  formulaire généré depuis un schéma, tableau, graphique, KPI, filtre,
  cross-filter…), bus d'actions composées, variables typées, thèmes,
  annuler/rétablir, export en bundle Statique/Connecté/Autoporté.
- **Importer et gérer ses données** : GeoJSON, CSV, GeoPackage et Shapefile
  zippé glissés-déposés deviennent une collection PostGIS avec RLS
  multi-tenant automatique ; une table existante s'enregistre aussi comme
  collection ; formulaires avec pièces jointes (photos, documents) par
  entité.
- **Automatiser sans code** : pipelines ETL en graphe (lecteurs REST/
  Postgres, transformations spatiales via QGIS Processing, écritures),
  exécution à la demande ou planifiée (cron), alertes de seuil notifiées par
  email/webhook au changement d'état, rapports PDF planifiés d'une vue
  enregistrée, cloche de notifications in-app.
- **Analyser** : agrégations (regroupement, neuf mesures dont médiane et
  percentile, filtres spatiaux/temporels) sur les collections ou sur un
  service ArcGIS moissonné en direct, assistant de requête visuelle
  (Filtrer → Joindre → Résumer) pour bâtir un nouveau dataset sans SQL, et
  un SQL Lab en lecture seule sandboxé pour les utilisateurs analystes.
- **Fédérer des sources externes** : moissonner STAC, ArcGIS Feature
  Service, WMS/WMTS/WFS, CSW et CKAN (couches ajoutables directement à une
  carte) ; exposer son propre catalogue via une API STAC native et un export
  DCAT-AP, pour l'interopérabilité avec d'autres infrastructures de
  données.
- **Se piloter par un agent IA** : serveur MCP authentifié (OAuth 2.1 +
  PKCE) exposant le catalogue, le partage et la création d'items à un agent
  externe, et un copilote intégré au builder qui orchestre ces mêmes outils
  en direct pour modifier une app pendant qu'on la regarde.

## Aperçu

Ce dépôt ne contient pas encore de capture d'écran ou de GIF à publier ici —
l'interface se découvre en lançant la stack locale ci-dessous (catalogue,
éditeur de carte, builder d'app). Un mode démo en lecture seule existe
(`CORE_READ_ONLY_MODE=true`) pour montrer une instance sans risquer
d'écriture ; voir la variable dans `.env.example`.

## Essayer en cinq minutes

Prérequis : Docker 24+, Node 20+, [uv](https://docs.astral.sh/uv/) (pour
contribuer côté cœur — pas nécessaire pour seulement lancer la stack).

```bash
./scripts/bootstrap-env.sh   # génère .env avec des secrets forts (no-op si .env existe déjà)
docker compose up -d         # stack complète — migrations du cœur appliquées automatiquement
```

`bootstrap-env.sh` génère aussi `CORE_SECRETS_MASTER_KEY` (clé AES-GCM du
coffre de secrets du cœur) — sans elle, le cœur refuse de démarrer.

| Service | URL |
|---|---|
| Shell (front) | http://localhost:8300 |
| Cœur (API) | http://localhost:8200 |
| Martin (tuiles MVT, accès dev uniquement) | http://localhost:3010 |
| Keycloak | http://localhost:8180 |
| MinIO console | http://localhost:9001 |

Par défaut, le mode d'authentification est `mock` (`mockuser` promu
administrateur dès la première requête, aucun accès réseau à Keycloak
nécessaire). Pour peupler des données de démonstration (collections
publiques éditables, utiles pour explorer le catalogue et le builder sans
importer ses propres données) :

```bash
docker compose exec core python -m scripts.seed_demo
```

Pour déployer en production (images publiées, pas de build sur l'hôte,
sauvegardes chiffrées planifiées, tunnel Tailscale Funnel en option), voir
l'installeur guidé (`scripts/install.sh`) et
[`CONTRIBUTING.md`](CONTRIBUTING.md) pour la marche à suivre complète côté
développement. Pour une instance Keycloak déjà déployée, voir
[`deploy/keycloak/README.md`](deploy/keycloak/README.md) et les runbooks
sous [`docs/runbooks/`](docs/runbooks/).

## Architecture en bref

Un **shell React** (TypeScript, Vite, MapLibre GL + deck.gl, ECharts) parle
exclusivement à un **cœur Python/FastAPI** (monolithe modulaire) via une
seule interface côté client (`ItemClient`) ; le cœur expose la même logique
en REST, en API OGC Features, et en outils MCP pour un agent — jamais de
logique dupliquée entre ces trois surfaces. Les données métier vivent dans
PostGIS avec RLS par tenant ; les fichiers dans S3 (MinIO en dev) ; les jobs
asynchrones (ingestion, pipelines, exports, alertes, rapports) tournent sur
une file Postgres (`procrastinate`, pas de broker séparé) ; une réplication
logique Postgres alimente un lakehouse GeoParquet pour l'analytique.

```
                     ┌──────────────┐
   Navigateur ──────▶│    shell     │  (React, builder no-code)
                     └──────┬───────┘
                            │ REST / OGC API Features / MCP
                     ┌──────▼───────┐        ┌─────────────┐
                     │     core     │───────▶│   worker    │ (jobs procrastinate)
                     │  (FastAPI)   │        │ cdc-worker  │ (CDC → GeoParquet)
                     └──┬────┬───┬──┘        └─────────────┘
                        │    │   │
             ┌──────────┘    │   └──────────┐
        ┌────▼────┐   ┌──────▼─────┐  ┌──────▼──────┐
        │ postgis  │   │   minio    │  │  keycloak   │
        │(pgbouncer)│  │   (S3)     │  │   (OIDC)    │
        └──────────┘   └────────────┘  └─────────────┘
```

Martin (tuiles vectorielles) et TiTiler (raster/COG) sont utilisés en
interne par le cœur, derrière Traefik. Cinq services supplémentaires
n'existent que derrière un profil compose optionnel : `etl` (sidecar QGIS
pour les transformations spatiales), `export` (rendu Playwright des
exports/rapports), `appexport` (construction du bundle Autoporté),
`observability` (Grafana/Prometheus/Loki/Tempo).

## État du projet

**Version publiée : `v0.1.0`** — huit images `ghcr.io/tlenenao/geostudio-*`
publiées sur le registre, anonymement téléchargeables, épinglées par tag
(jamais `latest` en production). Le [`CHANGELOG.md`](CHANGELOG.md) suit le
format Keep a Changelog.

**Ce qui est stable** : le catalogue et le partage, l'éditeur de carte et sa
symbologie, le builder d'apps/dashboards et son runtime, l'ingestion de
fichiers géospatiaux, l'authentification OIDC, le modèle de rôles à
privilèges, la CI (lint, types, tests, couverture, E2E, scan de
vulnérabilités) et la release taguée. Ces surfaces ont chacune une suite de
tests qui les couvre et sont vérifiées à chaque évolution du dépôt.

**Ce qui ne l'est pas encore** : plusieurs fonctionnalités livrées et
testées ne sont accessibles que par une URL directe faute de lien de
navigation câblé (l'inventaire exact, avec sa preuve, est dans la matrice
de fonctionnalités) ; la restauration d'une sauvegarde n'a jamais été
rejouée de bout en bout ; la Content-Security-Policy tourne en mode
« report-only », pas encore bloquant ; les transformations spatiales QGIS
n'ont pas été exécutées contre un vrai sidecar dans un environnement de
test. Ce dépôt documente ces manques explicitement plutôt que de les
taire — voir la matrice et [`docs/revue/2026-09-04-backlog.md`](docs/revue/2026-09-04-backlog.md)
pour le détail et le suivi.

Ce projet est développé par une seule personne assistée d'agents Claude ; il
n'y a pas d'équipe ni de support commercial derrière ce dépôt aujourd'hui.

## Aller plus loin

| Document | Rôle |
|---|---|
| [`docs/revue/2026-09-04-matrice-fonctionnalites.md`](docs/revue/2026-09-04-matrice-fonctionnalites.md) | L'inventaire complet des fonctionnalités, avec preuve dans le code |
| [`docs/vision/2026-07-04-feuille-de-route-geostudio.md`](docs/vision/2026-07-04-feuille-de-route-geostudio.md) | La feuille de route et les arbitrages produit |
| [`docs/`](docs/) | Specs, plans et revues datés de chaque chantier |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Lancer les tests, convention de commits, process de pull request |
| [`SECURITY.md`](SECURITY.md) | Politique et canal de signalement des vulnérabilités |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records — décisions d'architecture qui contraignent durablement le code |
| [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) | Code de conduite du projet |
| [`CHANGELOG.md`](CHANGELOG.md) | Historique des versions |
| [`CLAUDE.md`](CLAUDE.md) | Guide de travail pour les sessions de développement (Claude) |

## Licence

[Apache-2.0](LICENSE).
