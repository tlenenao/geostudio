# Bilan de fonctionnalités — GeoStudio

**Généré le 2026-09-06** par `uv run python scripts/feature_health_cli.py --repo .. --write`. **Ne pas éditer à la main** : ce fichier est regénéré à chaque clôture de SP.

306 fonctionnalités — santé médiane 97.2 sur 306 mesurables.

La **santé** est calculée (quatre sous-scores, spec §3) ; la **priorité** est déclarée (spec §4). Les deux ne sont jamais moyennées. Le tri est `priorité × (100 − santé)`.

## Par domaine

| Fonctionnalités | Domaine | Santé médiane |
|---|---|---|
| 4 | **Administration** | 92.6 |
| 4 | **Analytique** | 94.1 |
| 3 | **Apps & sites** | 98.2 |
| 31 | **Automatisation** | 93.6 |
| 3 | **Builder — Actions composees** | 100.0 |
| 3 | **Builder — Analytique globale** | 97.5 |
| 5 | **Builder — Automatisation (pipelines)** | 96.0 |
| 5 | **Builder — CEL & expressions** | 100.0 |
| 2 | **Builder — Copilote IA** | 100.0 |
| 1 | **Builder — Cross-filter** | 89.4 |
| 3 | **Builder — Donnees** | 89.7 |
| 2 | **Builder — Export d'app** | 92.1 |
| 1 | **Builder — Modeles** | 100.0 |
| 1 | **Builder — Pages** | 98.6 |
| 3 | **Builder — Requete visuelle** | 100.0 |
| 9 | **Builder — Runtime** | 92.8 |
| 4 | **Builder — SDK & extensions** | 100.0 |
| 1 | **Builder — Theme** | 100.0 |
| 2 | **Builder — Variables** | 90.4 |
| 32 | **Builder — Widgets** | 91.6 |
| 12 | **CI/Qualité** | 100.0 |
| 27 | **Carte** | 98.9 |
| 2 | **Cartes** | 98.6 |
| 5 | **Cartographie** | 96.4 |
| 5 | **Catalogue** | 90.6 |
| 10 | **Catalogue/Items** | 97.4 |
| 1 | **Catalogue/Métadonnées** | 87.5 |
| 3 | **Catalogue/Portails publics** | 99.5 |
| 12 | **Collections** | 96.9 |
| 2 | **Configs/Alerte** | 98.8 |
| 2 | **Configs/AppConfig** | 96.5 |
| 2 | **Configs/Bookmark** | 99.8 |
| 3 | **Configs/Dataset** | 100.0 |
| 1 | **Configs/Impression** | 92.8 |
| 2 | **Configs/MapConfig** | 97.7 |
| 1 | **Configs/Pipeline** | 100.0 |
| 1 | **Configs/Rapport** | 100.0 |
| 1 | **Configs/Schéma** | 100.0 |
| 3 | **Conformité** | 98.7 |
| 4 | **Données** | 92.8 |
| 6 | **Déploiement** | 92.0 |
| 3 | **Export statique** | 100.0 |
| 3 | **Extensibilité** | 98.5 |
| 10 | **Features (OGC API)** | 93.3 |
| 11 | **Fédération des données** | 94.5 |
| 1 | **Gouvernance/Licences** | 40.0 |
| 1 | **Interne** | 39.4 |
| 4 | **Navigation** | 100.0 |
| 1 | **Paramètres** | 100.0 |
| 5 | **Plateforme IA** | 97.6 |
| 1 | **Provisioning** | 40.0 |
| 1 | **Recherche** | 100.0 |
| 3 | **Release** | 100.0 |
| 5 | **Réseau/Sécurité** | 100.0 |
| 5 | **Sauvegarde** | 100.0 |
| 3 | **Supervision** | 100.0 |
| 1 | **Sécurité** | 100.0 |
| 1 | **Tâches** | 98.8 |
| 1 | **audit** | 100.0 |
| 8 | **auth** | 99.4 |
| 1 | **i18n** | 100.0 |
| 1 | **instance** | 100.0 |
| 5 | **roles** | 99.0 |
| 3 | **sharing** | 93.8 |
| 1 | **tenants** | 100.0 |
| 3 | **users** | 95.8 |

## Toutes les fonctionnalités

| Domaine | Fonctionnalité | id | Santé | Δ | Priorité | tests | atteignabilité | garde | dette |
|---|---|---|---|---|---|---|---|---|---|
| Déploiement | Créer le premier compte administrateur pendant l'installation | `deploiement-creer-le-premier-compte-administrateur-pendant-l-installation` | 40.0 | = | haute | 0.0 | — | — | 100.0 |
| Déploiement | Installeur guidé interactif (Docker, jq, profils, .env, Tailscale, sauvegarde, premier admin) | `deploiement-installeur-guide-interactif-docker-jq-profils-env-tailscale-sauvegar` | 40.0 | = | haute | 0.0 | — | — | 100.0 |
| Sauvegarde | Restaurer une sauvegarde | `sauvegarde-restaurer-une-sauvegarde` | 40.0 | = | haute | 0.0 | — | — | 100.0 |
| CI/Qualité | Analyser statiquement le code à la recherche de vulnérabilités (CodeQL) | `ci-qualite-analyser-statiquement-le-code-a-la-recherche-de-vulnerabilites-codeql` | 40.0 | = | moyenne | 0.0 | — | — | 100.0 |
| CI/Qualité | Bloquer un push/PR contenant un secret détecté dans l'arbre de travail | `ci-qualite-bloquer-un-push-pr-contenant-un-secret-detecte-dans-l-arbre-de-travai` | 40.0 | = | moyenne | 0.0 | — | — | 100.0 |
| Provisioning | Provisionner automatiquement une VM et y déployer GeoStudio sur un hyperviseur Proxmox | `provisioning-provisionner-automatiquement-une-vm-et-y-deployer-geostudio-sur-un-` | 40.0 | = | moyenne | 0.0 | — | — | 100.0 |
| Réseau/Sécurité | Exécuter les conteneurs applicatifs en utilisateur non-root | `reseau-securite-executer-les-conteneurs-applicatifs-en-utilisateur-non-root` | 40.0 | = | moyenne | 0.0 | — | — | 100.0 |
| Sauvegarde | Rotation automatique des sauvegardes (7 quotidiennes + 4 hebdomadaires, locale et hors-site) | `sauvegarde-rotation-automatique-des-sauvegardes-7-quotidiennes-4-hebdomadaires-l` | 40.0 | = | moyenne | 0.0 | — | — | 100.0 |
| Supervision | Recevoir une alerte SLO par webhook (latence API/tuiles, backlog de jobs, taux de 5xx) | `supervision-recevoir-une-alerte-slo-par-webhook-latence-api-tuiles-backlog-de-jo` | 40.0 | = | moyenne | 0.0 | — | — | 100.0 |
| Export statique | Client zero-backend pour le mode Statique (donnees gelees) | `export-statique-client-zero-backend-pour-le-mode-statique-donnees-gelees` | 46.2 | = | moyenne | 10.3 | — | — | 100.0 |
| Fédération des données | Fraîcheur quasi temps réel des données pour l'analytique (capture de réplication logique Postgres → GeoParquet) | `federation-des-donnees-fraicheur-quasi-temps-reel-des-donnees-pour-l-analytique-` | 66.6 | = | haute | 44.3 | — | — | 100.0 |
| auth | Déconnexion | `auth-deconnexion` | 61.8 | = | moyenne | 36.4 | — | — | 100.0 |
| Interne | Galerie interne de composants du kit UI | `interne-galerie-interne-de-composants-du-kit-ui` | 39.4 | = | basse | 31.8 | 0.0 | — | 100.0 |
| Automatisation | Transformer spatialement des données via QGIS Processing (buffer, dissolve, etc.) dans un pipeline | `automatisation-transformer-spatialement-des-donnees-via-qgis-processing-buffer-d` | 70.0 | = | moyenne | 50.0 | — | — | 100.0 |
| Gouvernance/Licences | Distribuer les notices de licences tierces (GPL/AGPL) avec les images qui embarquent du code sous ces licences | `gouvernance-licences-distribuer-les-notices-de-licences-tierces-gpl-agpl-avec-le` | 40.0 | = | basse | 0.0 | — | — | 100.0 |
| Builder — Widgets | Widget Hero (bandeau) avec validation de schema d'URL anti-injection | `builder-widgets-widget-hero-bandeau-avec-validation-de-schema-d-url-anti-injecti` | 75.5 | = | moyenne | 59.1 | — | — | 100.0 |
| Fédération des données | Compaction périodique des petits fichiers GeoParquet du lakehouse | `federation-des-donnees-compaction-periodique-des-petits-fichiers-geoparquet-du-l` | 76.9 | = | moyenne | 61.5 | — | — | 100.0 |
| Catalogue | Mes vues (signets) | `catalogue-mes-vues-signets` | 78.2 | = | moyenne | 63.6 | — | — | 100.0 |
| Builder — Runtime | Deplacement d'un widget par boutons flechés (canevas) | `builder-runtime-deplacement-d-un-widget-par-boutons-fleches-canevas` | 78.8 | = | moyenne | 64.7 | — | — | 100.0 |
| Features (OGC API) | Tuiles vectorielles MVT servies par le cœur (avec RLS) | `features-ogc-api-tuiles-vectorielles-mvt-servies-par-le-cur-avec-rls` | 87.0 | = | haute | 98.5 | 100.0 | 50.0 | 100.0 |
| Automatisation | Lancer l'exécution d'un pipeline à la demande | `automatisation-lancer-l-execution-d-un-pipeline-a-la-demande` | 88.7 | = | haute | 90.2 | 100.0 | 66.7 | 100.0 |
| Builder — Widgets | Widget Fiche jeu de donnees (datasetCard) | `builder-widgets-widget-fiche-jeu-de-donnees-datasetcard` | 84.2 | = | moyenne | 73.7 | — | — | 100.0 |
| Builder — Donnees | Panneau des sources de donnees (features/statistics/static) | `builder-donnees-panneau-des-sources-de-donnees-features-statistics-static` | 89.7 | = | haute | 82.8 | — | — | 100.0 |
| Builder — Widgets | Widget Galerie (catalogue public filtrable) | `builder-widgets-widget-galerie-catalogue-public-filtrable` | 85.0 | = | moyenne | 75.0 | — | — | 100.0 |
| Builder — Widgets | Widget Section riche (markdown assaini) | `builder-widgets-widget-section-riche-markdown-assaini` | 85.0 | = | moyenne | 75.0 | — | — | 100.0 |
| users | Liste des utilisateurs du tenant, avec recherche et pagination | `users-liste-des-utilisateurs-du-tenant-avec-recherche-et-pagination` | 85.1 | +2.0 | moyenne | 64.3 | 100.0 | 83.3 | 100.0 |
| Builder — Widgets | Comparaison de periode sur le widget Graphique (lignes/aires) | `builder-widgets-comparaison-de-periode-sur-le-widget-graphique-lignes-aires` | 85.2 | = | moyenne | 75.3 | — | — | 100.0 |
| roles | Créer, éditer, supprimer un rôle sur mesure avec privilèges cochés par domaine | `roles-creer-editer-supprimer-un-role-sur-mesure-avec-privileges-coches-par-domai` | 85.3 | +2.0 | moyenne | 50.9 | 100.0 | 100.0 | 100.0 |
| Fédération des données | Garde d'egress SSRF sur toute requête sortante du moteur de moissonnage | `federation-des-donnees-garde-d-egress-ssrf-sur-toute-requete-sortante-du-moteur-` | 90.2 | = | haute | 83.7 | — | — | 100.0 |
| Automatisation | Assistant de requête visuelle (Filtrer/Joindre/Résumer) | `automatisation-assistant-de-requete-visuelle-filtrer-joindre-resumer` | 85.5 | = | moyenne | 63.7 | 100.0 | — | 100.0 |
| Builder — Widgets | Widget Table (tri, pagination, cross-filter, action setFilter) | `builder-widgets-widget-table-tri-pagination-cross-filter-action-setfilter` | 90.5 | = | haute | 84.2 | — | — | 100.0 |
| Catalogue | Catalogue (recherche, filtre type, filtre portée, pagination) | `catalogue-catalogue-recherche-filtre-type-filtre-portee-pagination` | 90.6 | = | haute | 97.2 | 75.0 | — | 100.0 |
| Automatisation | Marquer une ou toutes les notifications comme lues | `automatisation-marquer-une-ou-toutes-les-notifications-comme-lues` | 86.1 | = | moyenne | 95.2 | 100.0 | 50.0 | 100.0 |
| Cartographie | Uploader une icône SVG personnalisée dans une bibliothèque d'icônes du tenant | `cartographie-uploader-une-icone-svg-personnalisee-dans-une-bibliotheque-d-icones` | 86.2 | +2.0 | moyenne | 95.5 | 100.0 | 50.0 | 100.0 |
| Administration | Copilote IA dans le builder d'app orchestrant des outils MCP réels en loopback | `administration-copilote-ia-dans-le-builder-d-app-orchestrant-des-outils-mcp-reel` | 86.2 | = | moyenne | 95.8 | 100.0 | 50.0 | 100.0 |
| Builder — Requete visuelle | Jointure entre collections dans l'assistant de requete visuelle | `builder-requete-visuelle-jointure-entre-collections-dans-l-assistant-de-requete-` | 86.7 | = | moyenne | 77.8 | — | — | 100.0 |
| Automatisation | Choisir sa préférence de notification (toutes / échecs seulement / aucune) | `automatisation-choisir-sa-preference-de-notification-toutes-echecs-seulement-auc` | 86.8 | = | moyenne | 97.6 | 100.0 | 50.0 | 100.0 |
| Automatisation | Être notifié dans une cloche persistante du shell des jobs en échec/succès (ingestion, pipeline, export, export d'app, rapport) | `automatisation-etre-notifie-dans-une-cloche-persistante-du-shell-des-jobs-en-ech` | 86.8 | = | moyenne | 97.6 | 100.0 | 50.0 | 100.0 |
| Builder — Widgets | Widget Onglets (conteneur, layout imbrique par onglet) | `builder-widgets-widget-onglets-conteneur-layout-imbrique-par-onglet` | 86.8 | = | moyenne | 78.0 | — | — | 100.0 |
| Automatisation | Importer un fichier géospatial (GeoJSON/CSV/GeoPackage/Shapefile zippé) comme nouvelle collection | `automatisation-importer-un-fichier-geospatial-geojson-csv-geopackage-shapefile-z` | 91.3 | +9.1 | haute | 91.7 | 100.0 | 75.0 | 100.0 |
| Données | Configuration des champs de pièces jointes d'une collection | `donnees-configuration-des-champs-de-pieces-jointes-d-une-collection` | 86.9 | = | moyenne | 78.2 | — | — | 100.0 |
| Données | Édition des métadonnées ouvertes (DCAT) d'une collection | `donnees-edition-des-metadonnees-ouvertes-dcat-d-une-collection` | 86.9 | = | moyenne | 78.2 | — | — | 100.0 |
| Builder — Widgets | Widget Carte (symbologie, popup, cross-filter, actions flyTo/highlight) | `builder-widgets-widget-carte-symbologie-popup-cross-filter-actions-flyto-highlig` | 91.4 | +8.0 | haute | 85.7 | — | — | 100.0 |
| Automatisation | Recevoir un rapport PDF périodique d'un Bookmark, envoyé par email/webhook | `automatisation-recevoir-un-rapport-pdf-periodique-d-un-bookmark-envoye-par-email` | 87.3 | = | moyenne | 61.7 | 100.0 | 95.0 | 100.0 |
| Catalogue/Métadonnées | Catalogue curaté de licences/fréquences/langues | `catalogue-metadonnees-catalogue-curate-de-licences-frequences-langues` | 87.5 | = | moyenne | 100.0 | 100.0 | 50.0 | 100.0 |
| Automatisation | Consulter l'historique des exécutions d'un pipeline | `automatisation-consulter-l-historique-des-executions-d-un-pipeline` | 87.9 | = | moyenne | 87.3 | 100.0 | 66.7 | 100.0 |
| Automatisation | Prévisualiser un pipeline jusqu'à un nœud donné, avant exécution complète | `automatisation-previsualiser-un-pipeline-jusqu-a-un-nud-donne-avant-execution-co` | 87.9 | = | moyenne | 87.3 | 100.0 | 66.7 | 100.0 |
| Builder — Widgets | Widget Graphique (15 types ECharts, clic -> cross-filter) | `builder-widgets-widget-graphique-15-types-echarts-clic-cross-filter` | 91.9 | = | haute | 86.6 | — | — | 100.0 |
| Automatisation | Attacher un fichier (photo, document) à une entité depuis le widget Formulaire | `automatisation-attacher-un-fichier-photo-document-a-une-entite-depuis-le-widget-` | 91.9 | +2.0 | haute | 89.8 | 100.0 | 80.0 | 100.0 |
| Builder — Export d'app | Detection des widgets consommateurs d'ecriture pour l'avertissement d'export | `builder-export-d-app-detection-des-widgets-consommateurs-d-ecriture-pour-l-avert` | 88.0 | = | moyenne | 80.0 | — | — | 100.0 |
| Builder — Variables | Variables typees d'app (string/number/bool/date/record/list) | `builder-variables-variables-typees-d-app-string-number-bool-date-record-list` | 88.0 | = | moyenne | 80.0 | — | — | 100.0 |
| Builder — Widgets | Widget Navigation (menu de pages automatique) | `builder-widgets-widget-navigation-menu-de-pages-automatique` | 88.0 | = | moyenne | 80.0 | — | — | 100.0 |
| Déploiement | Déployer en production avec des images pré-construites publiées (aucun build sur l'hôte), hôte public piloté par une seule variable | `deploiement-deployer-en-production-avec-des-images-pre-construites-publiees-aucu` | 92.0 | +4.0 | haute | 100.0 | — | — | 80.0 |
| Builder — Widgets | Widget Indicateur (KPI) avec comparaison de periode et sparkline | `builder-widgets-widget-indicateur-kpi-avec-comparaison-de-periode-et-sparkline` | 92.1 | = | haute | 86.8 | — | — | 100.0 |
| Catalogue/Portails publics | Lister/lire les items publiés, anonymement | `catalogue-portails-publics-lister-lire-les-items-publies-anonymement` | 92.1 | = | haute | 73.8 | 100.0 | 100.0 | 100.0 |
| Builder — Automatisation (pipelines) | Planification cron partagee (pipelines, rapports, alertes) | `builder-automatisation-pipelines-planification-cron-partagee-pipelines-rapports-` | 88.3 | = | moyenne | 80.4 | — | — | 100.0 |
| Builder — Widgets | Formulaire en lecture seule si permission insuffisante ou instance en mode demo | `builder-widgets-formulaire-en-lecture-seule-si-permission-insuffisante-ou-instan` | 92.5 | = | haute | 87.5 | — | — | 100.0 |
| Builder — Widgets | Widget Formulaire genere depuis le schema de collection | `builder-widgets-widget-formulaire-genere-depuis-le-schema-de-collection` | 92.5 | = | haute | 87.5 | — | — | 100.0 |
| Features (OGC API) | Créer/modifier/supprimer une entité (OGC Part 4) | `features-ogc-api-creer-modifier-supprimer-une-entite-ogc-part-4` | 92.6 | +2.0 | haute | 94.2 | 100.0 | 77.3 | 100.0 |
| Administration | Administration des collections | `administration-administration-des-collections` | 92.7 | = | haute | 81.8 | 100.0 | — | 100.0 |
| Automatisation | Catalogue des rapports planifiés (/reports) | `automatisation-catalogue-des-rapports-planifies-reports` | 78.2 | = | basse | 63.6 | — | — | 100.0 |
| Automatisation | Construire un pipeline ETL no-code (graphe reader/transform/writer) | `automatisation-construire-un-pipeline-etl-no-code-graphe-reader-transform-writer` | 92.7 | = | haute | 91.2 | 100.0 | 81.6 | 100.0 |
| Builder — Runtime | Runtime d'app a trois modes (edition/apercu/execution) | `builder-runtime-runtime-d-app-a-trois-modes-edition-apercu-execution` | 92.8 | = | haute | 88.0 | — | — | 100.0 |
| Builder — Cross-filter | Lien de cross-filter entre deux datasets (attribut ou spatial) | `builder-cross-filter-lien-de-cross-filter-entre-deux-datasets-attribut-ou-spatia` | 89.4 | = | moyenne | 82.3 | — | — | 100.0 |
| Catalogue/Items | Publier / dépublier un item | `catalogue-items-publier-depublier-un-item` | 93.1 | = | haute | 94.2 | 100.0 | 79.2 | 100.0 |
| Builder — Donnees | Six grains temporels pour une source statistics | `builder-donnees-six-grains-temporels-pour-une-source-statistics` | 89.7 | = | moyenne | 82.8 | — | — | 100.0 |
| Builder — Widgets | Widget Selecteur (valeurs distinctes -> cross-filter multi-valeur) | `builder-widgets-widget-selecteur-valeurs-distinctes-cross-filter-multi-valeur` | 89.7 | = | moyenne | 82.8 | — | — | 100.0 |
| Builder — Widgets | Widget Plage de dates (pilote le contexte temporel global) | `builder-widgets-widget-plage-de-dates-pilote-le-contexte-temporel-global` | 90.0 | = | moyenne | 83.3 | — | — | 100.0 |
| Features (OGC API) | Lister/lire les entités d'une collection (bbox, filtres d'attribut, pagination) | `features-ogc-api-lister-lire-les-entites-d-une-collection-bbox-filtres-d-attribu` | 93.3 | +2.0 | haute | 96.8 | 100.0 | 77.3 | 100.0 |
| Carte | Gestion des couches (réordonnancement, visibilité, suppression) | `carte-gestion-des-couches-reordonnancement-visibilite-suppression` | 93.5 | = | haute | 89.2 | — | — | 100.0 |
| Catalogue | Menu d'actions sur un item (modifier/publier/miniature/partager/supprimer/programmer un rapport) | `catalogue-menu-d-actions-sur-un-item-modifier-publier-miniature-partager-supprim` | 90.4 | = | moyenne | 84.0 | — | — | 100.0 |
| Automatisation | Planifier l'exécution récurrente d'un pipeline (cron) | `automatisation-planifier-l-execution-recurrente-d-un-pipeline-cron` | 90.5 | = | moyenne | 84.2 | — | — | 100.0 |
| Analytique | Agrégation de données d'une collection (groupBy multi-champs, mesures count/sum/avg/min/max/countDistinct/median/percentile/stddev, filtres, bbox/geomIntersects, bucket temporel, histogramme bins, échantillon) | `analytique-agregation-de-donnees-d-une-collection-groupby-multi-champs-mesures-c` | 93.7 | +4.0 | haute | 97.8 | 100.0 | 77.3 | 100.0 |
| Builder — CEL & expressions | Colonne calculee CEL sur le widget Table | `builder-cel-expressions-colonne-calculee-cel-sur-le-widget-table` | 90.5 | = | moyenne | 84.2 | — | — | 100.0 |
| Builder — Widgets | Widget Liste (selection -> cross-filter) | `builder-widgets-widget-liste-selection-cross-filter` | 90.5 | = | moyenne | 84.2 | — | — | 100.0 |
| Builder — Widgets | Widget Curseur (plage numerique -> cross-filter) | `builder-widgets-widget-curseur-plage-numerique-cross-filter` | 90.6 | = | moyenne | 84.4 | — | — | 100.0 |
| sharing | Partager un item avec des groupes (rôle lecteur/éditeur) et basculer sa visibilité publique | `sharing-partager-un-item-avec-des-groupes-role-lecteur-editeur-et-basculer-sa-vi` | 93.8 | +2.0 | haute | 96.5 | 100.0 | 79.2 | 100.0 |
| Catalogue | Fiche détail d'un item (panneaux édition/miniature/partage via URL) | `catalogue-fiche-detail-d-un-item-panneaux-edition-miniature-partage-via-url` | 91.2 | = | moyenne | 78.0 | 100.0 | — | 100.0 |
| Automatisation | Inspecter les couches d'un GeoPackage/Shapefile avant de choisir laquelle importer | `automatisation-inspecter-les-couches-d-un-geopackage-shapefile-avant-de-choisir-` | 91.3 | +5.1 | moyenne | 91.9 | 100.0 | 75.0 | 100.0 |
| Builder — Widgets | Outils de mesure/croquis sur le widget Carte, actifs seulement hors edition | `builder-widgets-outils-de-mesure-croquis-sur-le-widget-carte-actifs-seulement-ho` | 91.4 | +8.0 | moyenne | 85.7 | — | — | 100.0 |
| Carte | Légende de symbologie (couleurs par classe/catégorie) affichée sur la carte | `carte-legende-de-symbologie-couleurs-par-classe-categorie-affichee-sur-la-carte` | 91.4 | +8.0 | moyenne | 85.7 | — | — | 100.0 |
| Features (OGC API) | SQL Lab : requête SQL en lecture seule sandboxée sur les collections visibles | `features-ogc-api-sql-lab-requete-sql-en-lecture-seule-sandboxee-sur-les-collecti` | 91.5 | +2.0 | moyenne | 97.5 | 91.7 | 77.3 | 100.0 |
| Builder — Widgets | Widget Bouton (action composee + lien externe) | `builder-widgets-widget-bouton-action-composee-lien-externe` | 91.6 | = | moyenne | 86.0 | — | — | 100.0 |
| Builder — Widgets | Widget Image | `builder-widgets-widget-image` | 91.6 | = | moyenne | 86.0 | — | — | 100.0 |
| Builder — Widgets | Widget Texte avec interpolation {{champ}}/{{var:nom}} | `builder-widgets-widget-texte-avec-interpolation-champ-var-nom` | 91.6 | = | moyenne | 86.0 | — | — | 100.0 |
| sharing | Créer un groupe de partage et y ajouter des membres | `sharing-creer-un-groupe-de-partage-et-y-ajouter-des-membres` | 91.7 | = | moyenne | 100.0 | 100.0 | 66.7 | 100.0 |
| Analytique | Agrégation live sur un dataset ArcGIS Feature Service moissonné, sans copie locale | `analytique-agregation-live-sur-un-dataset-arcgis-feature-service-moissonne-sans-` | 92.0 | = | moyenne | 100.0 | — | — | 80.0 |
| Déploiement | Publier l'instance sur Internet sans ouvrir de port (tunnel Tailscale Funnel) | `deploiement-publier-l-instance-sur-internet-sans-ouvrir-de-port-tunnel-tailscale` | 92.0 | +4.0 | moyenne | 100.0 | — | — | 80.0 |
| Réseau/Sécurité | Bloquer les scripts/ressources non autorisés via une Content-Security-Policy | `reseau-securite-bloquer-les-scripts-ressources-non-autorises-via-une-content-sec` | 92.0 | +4.0 | moyenne | 100.0 | — | — | 80.0 |
| Builder — CEL & expressions | Seuils critique/alerte CEL sur l'indicateur | `builder-cel-expressions-seuils-critique-alerte-cel-sur-l-indicateur` | 92.1 | = | moyenne | 86.8 | — | — | 100.0 |
| Builder — Widgets | Widget Modale (conteneur, ouverture/fermeture par action) | `builder-widgets-widget-modale-conteneur-ouverture-fermeture-par-action` | 92.2 | = | moyenne | 93.8 | — | — | 90.0 |
| Builder — Automatisation (pipelines) | Canevas DAG de pipeline avec branchements et fusion | `builder-automatisation-pipelines-canevas-dag-de-pipeline-avec-branchements-et-fu` | 92.3 | = | moyenne | 87.2 | — | — | 100.0 |
| Administration | Lancer Martin/Titiler/Grafana depuis le shell derrière un gate cookie de courte durée | `administration-lancer-martin-titiler-grafana-depuis-le-shell-derriere-un-gate-co` | 92.5 | = | moyenne | 75.0 | 100.0 | 100.0 | 100.0 |
| Builder — Widgets | Actions composees du Formulaire (reset/loadRecord) et evenements (submitted/failed) | `builder-widgets-actions-composees-du-formulaire-reset-loadrecord-et-evenements-s` | 92.5 | = | moyenne | 87.5 | — | — | 100.0 |
| Builder — Widgets | Champ pieces jointes dans le widget Formulaire (upload/telechargement/suppression) | `builder-widgets-champ-pieces-jointes-dans-le-widget-formulaire-upload-telecharge` | 92.5 | = | moyenne | 87.5 | — | — | 100.0 |
| Builder — Widgets | Edition de geometrie Point dans le widget Formulaire | `builder-widgets-edition-de-geometrie-point-dans-le-widget-formulaire` | 92.5 | = | moyenne | 87.5 | — | — | 100.0 |
| Builder — Widgets | Erreurs de validation serveur par champ sur le Formulaire | `builder-widgets-erreurs-de-validation-serveur-par-champ-sur-le-formulaire` | 92.5 | = | moyenne | 87.5 | — | — | 100.0 |
| Builder — Widgets | Overrides de champ (ordre par glisser-deposer, masquage, requis, contraintes) | `builder-widgets-overrides-de-champ-ordre-par-glisser-deposer-masquage-requis-con` | 92.5 | = | moyenne | 87.5 | — | — | 100.0 |
| Builder — Widgets | Widget Filtre (texte libre, evenement changed) | `builder-widgets-widget-filtre-texte-libre-evenement-changed` | 92.5 | = | moyenne | 87.5 | — | — | 100.0 |
| Builder — Widgets | Widget Tiroir (conteneur lateral, ouverture/fermeture par action) | `builder-widgets-widget-tiroir-conteneur-lateral-ouverture-fermeture-par-action` | 92.5 | = | moyenne | 87.5 | — | — | 100.0 |
| Carte | Contour de couche (fixe ou par attribut classé), épaisseur, style | `carte-contour-de-couche-fixe-ou-par-attribut-classe-epaisseur-style` | 92.6 | = | moyenne | 87.6 | — | — | 100.0 |
| Carte | Opacité globale d'une couche vector/feature (symbologie) | `carte-opacite-globale-d-une-couche-vector-feature-symbologie` | 92.6 | = | moyenne | 87.6 | — | — | 100.0 |
| Carte | Symbologie taille (bulles proportionnelles à un champ numérique) | `carte-symbologie-taille-bulles-proportionnelles-a-un-champ-numerique` | 92.6 | = | moyenne | 87.6 | — | — | 100.0 |
| Plateforme IA | Décrire les champs interrogeables d'un dataset avant une requête analytique (agent MCP) | `plateforme-ia-decrire-les-champs-interrogeables-d-un-dataset-avant-une-requete-a` | 92.7 | = | moyenne | 81.8 | 100.0 | — | 100.0 |
| Builder — Runtime | Actions declenchees a l'entree d'un chapitre (onEnter) | `builder-runtime-actions-declenchees-a-l-entree-d-un-chapitre-onenter` | 92.8 | = | moyenne | 88.0 | — | — | 100.0 |
| Builder — Runtime | Detection automatique du breakpoint courant | `builder-runtime-detection-automatique-du-breakpoint-courant` | 92.8 | = | moyenne | 88.0 | — | — | 100.0 |
| Builder — Runtime | Mode narratif (story) avec navigation par chapitres | `builder-runtime-mode-narratif-story-avec-navigation-par-chapitres` | 92.8 | = | moyenne | 88.0 | — | — | 100.0 |
| Builder — Variables | Ecriture d'une variable par une action composee (var:id.set) | `builder-variables-ecriture-d-une-variable-par-une-action-composee-var-id-set` | 92.8 | = | moyenne | 88.0 | — | — | 100.0 |
| Configs/Impression | Mise en page d'impression déclarative (PrintLayout) | `configs-impression-mise-en-page-d-impression-declarative-printlayout` | 92.8 | = | moyenne | 88.1 | — | — | 100.0 |
| Builder — Widgets | Widget Pivot (tableau croise dynamique) | `builder-widgets-widget-pivot-tableau-croise-dynamique` | 93.0 | = | moyenne | 88.4 | — | — | 100.0 |
| Catalogue/Items | Miniature d'un item (upload/lecture) | `catalogue-items-miniature-d-un-item-upload-lecture` | 93.1 | = | moyenne | 94.2 | 100.0 | 79.2 | 100.0 |
| Carte | Popup au clic sur une entité (liste de champs configurable) | `carte-popup-au-clic-sur-une-entite-liste-de-champs-configurable` | 95.4 | +8.0 | haute | 92.4 | — | — | 100.0 |
| Features (OGC API) | Exporter les entités brutes d'une collection (CSV/XLSX/GeoJSON/GPKG) | `features-ogc-api-exporter-les-entites-brutes-d-une-collection-csv-xlsx-geojson-g` | 93.1 | +2.0 | moyenne | 96.1 | 100.0 | 77.3 | 100.0 |
| Fédération des données | Moissonnage : créer/lister/éditer/supprimer une source externe (STAC, ArcGIS FS, WMS, WFS, WMTS, CSW, OGC API - Records, CKAN) | `federation-des-donnees-moissonnage-creer-lister-editer-supprimer-une-source-exte` | 93.2 | = | moyenne | 84.1 | 100.0 | 91.7 | 100.0 |
| Features (OGC API) | Cascade de suppression des pièces jointes à la suppression d'une entité | `features-ogc-api-cascade-de-suppression-des-pieces-jointes-a-la-suppression-d-un` | 93.3 | +2.0 | moyenne | 96.8 | 100.0 | 77.3 | 100.0 |
| Features (OGC API) | Exporter un agrégat en CSV/XLSX | `features-ogc-api-exporter-un-agregat-en-csv-xlsx` | 93.3 | +2.0 | moyenne | 96.8 | 100.0 | 77.3 | 100.0 |
| Features (OGC API) | Landing page et déclaration de conformité OGC API Features | `features-ogc-api-landing-page-et-declaration-de-conformite-ogc-api-features` | 93.3 | +2.0 | moyenne | 96.8 | 100.0 | 77.3 | 100.0 |
| Catalogue/Items | Slug d'URL unique pour un site publié (attribution + renommage) | `catalogue-items-slug-d-url-unique-pour-un-site-publie-attribution-renommage` | 93.4 | = | moyenne | 95.5 | 100.0 | 79.2 | 100.0 |
| Fédération des données | API STAC native (landing, conformance, collections, items, recherche cross-collection) | `federation-des-donnees-api-stac-native-landing-conformance-collections-items-rec` | 93.5 | = | moyenne | 88.7 | 100.0 | 87.5 | 100.0 |
| Automatisation | Voir les pièces jointes d'une entité dans le popup de la carte | `automatisation-voir-les-pieces-jointes-d-une-entite-dans-le-popup-de-la-carte` | 93.6 | +2.0 | moyenne | 95.4 | 100.0 | 80.0 | 100.0 |
| auth | Consultation du profil courant (identité, rôle, privilèges, capacités) | `auth-consultation-du-profil-courant-identite-role-privileges-capacites` | 95.8 | +2.0 | haute | 100.0 | 100.0 | 83.3 | 100.0 |
| users | Changer le rôle d'un utilisateur | `users-changer-le-role-d-un-utilisateur` | 95.8 | +2.0 | haute | 100.0 | 100.0 | 83.3 | 100.0 |
| users | Garde anti-lockout sur le changement de rôle d'un utilisateur (dernier titulaire admin.users.manage+admin.roles.manage) | `users-garde-anti-lockout-sur-le-changement-de-role-d-un-utilisateur-dernier-titu` | 95.8 | +2.0 | haute | 100.0 | 100.0 | 83.3 | 100.0 |
| Carte | Sélection d'un DEM hébergé existant comme source de terrain | `carte-selection-d-un-dem-heberge-existant-comme-source-de-terrain` | 93.8 | = | moyenne | 89.7 | — | — | 100.0 |
| Automatisation | Être notifié en in-app quand un rapport a été déclenché avec succès ou en échec | `automatisation-etre-notifie-en-in-app-quand-un-rapport-a-ete-declenche-avec-succ` | 93.9 | = | moyenne | 89.8 | — | — | 100.0 |
| Features (OGC API) | Exécution SQL sous rôle non-propriétaire borné au tenant (RLS transactionnelle) | `features-ogc-api-execution-sql-sous-role-non-proprietaire-borne-au-tenant-rls-tr` | 96.0 | = | haute | 93.3 | — | — | 100.0 |
| Carte | Étiquettes de carte multi-champs (gabarit CEL) | `carte-etiquettes-de-carte-multi-champs-gabarit-cel` | 94.1 | = | moyenne | 90.1 | — | — | 100.0 |
| Builder — Export d'app | Export d'app en trois modes (Statique/Connecte/Autoporte) | `builder-export-d-app-export-d-app-en-trois-modes-statique-connecte-autoporte` | 96.2 | = | haute | 90.4 | 100.0 | — | 100.0 |
| Configs/AppConfig | Restreindre les widgets d'extension aux collections déclarées | `configs-appconfig-restreindre-les-widgets-d-extension-aux-collections-declarees` | 94.4 | = | moyenne | 90.7 | — | — | 100.0 |
| Analytique | Export (agrégat CSV/XLSX et entités GeoJSON/CSV/XLSX) d'un dataset ArcGIS Feature Service live | `analytique-export-agregat-csv-xlsx-et-entites-geojson-csv-xlsx-d-un-dataset-arcg` | 94.5 | = | moyenne | 88.7 | 100.0 | 91.7 | 100.0 |
| Analytique | Lecture live paginée/filtrée des entités d'un dataset ArcGIS Feature Service (pour rendu carte) | `analytique-lecture-live-paginee-filtree-des-entites-d-un-dataset-arcgis-feature-` | 94.5 | = | moyenne | 88.7 | 100.0 | 91.7 | 100.0 |
| Fédération des données | Exécution manuelle immédiate d'un moissonnage (bouton « Lancer ») | `federation-des-donnees-execution-manuelle-immediate-d-un-moissonnage-bouton-lanc` | 94.5 | = | moyenne | 88.7 | 100.0 | 91.7 | 100.0 |
| Apps & sites | Runtime d'une app (navigation par page, contexte analytique dans l'URL, enregistrer une vue) | `apps-sites-runtime-d-une-app-navigation-par-page-contexte-analytique-dans-l-url-` | 96.4 | = | haute | 97.6 | 100.0 | — | 90.0 |
| Automatisation | Recevoir une alerte par email ou webhook uniquement au changement d'état (pas à chaque évaluation) | `automatisation-recevoir-une-alerte-par-email-ou-webhook-uniquement-au-changement` | 95.0 | = | moyenne | 91.6 | — | — | 100.0 |
| Builder — Runtime | Editeur d'actions a l'entree de chapitre limite a un payload de centrage carte | `builder-runtime-editeur-d-actions-a-l-entree-de-chapitre-limite-a-un-payload-de-` | 95.6 | = | moyenne | 92.7 | — | — | 100.0 |
| Cartographie | Uploader un DEM et le convertir en terrain 3D affichable sur la carte | `cartographie-uploader-un-dem-et-le-convertir-en-terrain-3d-affichable-sur-la-car` | 95.6 | = | moyenne | 95.9 | 100.0 | 87.5 | 100.0 |
| Catalogue/Items | Lire/mettre à jour un config par id ou par item | `catalogue-items-lire-mettre-a-jour-un-config-par-id-ou-par-item` | 97.1 | = | haute | 94.6 | 100.0 | 95.0 | 100.0 |
| Cartes | Éditeur de carte (couches, fond de carte, terrain, caméra, impression, historique) | `cartes-editeur-de-carte-couches-fond-de-carte-terrain-camera-impression-historiq` | 97.1 | = | haute | 92.9 | 100.0 | — | 100.0 |
| Collections | Lire le détail d'une collection (avec emprise spatiale) | `collections-lire-le-detail-d-une-collection-avec-emprise-spatiale` | 97.2 | = | haute | 97.3 | 100.0 | 100.0 | 90.0 |
| Collections | Lire le schéma d'une collection (champs + pièces jointes) | `collections-lire-le-schema-d-une-collection-champs-pieces-jointes` | 97.2 | = | haute | 97.3 | 100.0 | 100.0 | 90.0 |
| Collections | Inscrire/retirer une table de la publication logique CDC | `collections-inscrire-retirer-une-table-de-la-publication-logique-cdc` | 95.9 | = | moyenne | 93.1 | — | — | 100.0 |
| Builder — Automatisation (pipelines) | Apercu des donnees d'un noeud de pipeline (table/carte) | `builder-automatisation-pipelines-apercu-des-donnees-d-un-noeud-de-pipeline-table` | 96.0 | = | moyenne | 93.3 | — | — | 100.0 |
| Catalogue/Items | Créer un objet de plateforme versionné (AppConfig/MapConfig/Dataset/...) | `catalogue-items-creer-un-objet-de-plateforme-versionne-appconfig-mapconfig-datas` | 97.4 | = | haute | 95.3 | 100.0 | 95.0 | 100.0 |
| Builder — Automatisation (pipelines) | Inspecteur de noeud genere depuis un schema JSON serveur | `builder-automatisation-pipelines-inspecteur-de-noeud-genere-depuis-un-schema-jso` | 96.2 | = | moyenne | 93.6 | — | — | 100.0 |
| Collections | Enregistrer une table PostGIS existante comme collection | `collections-enregistrer-une-table-postgis-existante-comme-collection` | 96.4 | = | moyenne | 94.6 | 100.0 | 100.0 | 90.0 |
| Collections | Lister les tables PostGIS candidates à l'enregistrement | `collections-lister-les-tables-postgis-candidates-a-l-enregistrement` | 96.4 | = | moyenne | 94.6 | 100.0 | 100.0 | 90.0 |
| Collections | Modifier une collection (titre, publication, métadonnées ouvertes, champs pièces jointes) | `collections-modifier-une-collection-titre-publication-metadonnees-ouvertes-champ` | 96.4 | = | moyenne | 94.6 | 100.0 | 100.0 | 90.0 |
| Collections | Supprimer une collection | `collections-supprimer-une-collection` | 96.4 | = | moyenne | 94.6 | 100.0 | 100.0 | 90.0 |
| Configs/MapConfig | Terrain 3D raster-dem sur une carte | `configs-mapconfig-terrain-3d-raster-dem-sur-une-carte` | 96.4 | = | moyenne | 94.0 | — | — | 100.0 |
| Carte | Options de gabarit d'impression : barre d'échelle et flèche du nord | `carte-options-de-gabarit-d-impression-barre-d-echelle-et-fleche-du-nord` | 92.8 | = | basse | 88.1 | — | — | 100.0 |
| Fédération des données | Mode « copie » du moissonnage : matérialise le contenu distant en une collection propre au tenant (RLS, édition, etc.) | `federation-des-donnees-mode-copie-du-moissonnage-materialise-le-contenu-distant-` | 96.4 | = | moyenne | 94.0 | — | — | 100.0 |
| Cartographie | Héberger un tileset 3D (zip, ex. Cesium 3D Tiles) sans jamais l'extraire sur disque | `cartographie-heberger-un-tileset-3d-zip-ex-cesium-3d-tiles-sans-jamais-l-extrair` | 96.4 | = | moyenne | 96.5 | 100.0 | 90.0 | 100.0 |
| Plateforme IA | Serveur MCP authentifié (OAuth 2.1 + PKCE) exposant des outils au catalogue/aux items/au partage | `plateforme-ia-serveur-mcp-authentifie-oauth-2-1-pkce-exposant-des-outils-au-cata` | 97.7 | = | haute | 94.2 | 100.0 | — | 100.0 |
| Collections | Lister/rechercher les collections (recherche hybride) | `collections-lister-rechercher-les-collections-recherche-hybride` | 96.6 | = | moyenne | 91.6 | 100.0 | — | 100.0 |
| sharing | Partager une collection avec des groupes, avec court-circuit admin | `sharing-partager-une-collection-avec-des-groupes-avec-court-circuit-admin` | 96.7 | +2.0 | moyenne | 95.7 | 100.0 | 100.0 | 90.0 |
| Automatisation | Créer/expliquer une règle d'alerte via un agent MCP | `automatisation-creer-expliquer-une-regle-d-alerte-via-un-agent-mcp` | 97.0 | = | moyenne | 92.5 | 100.0 | — | 100.0 |
| Plateforme IA | Décrire un rapport planifié sans le déclencher (agent MCP) | `plateforme-ia-decrire-un-rapport-planifie-sans-le-declencher-agent-mcp` | 97.0 | = | moyenne | 92.6 | 100.0 | — | 100.0 |
| Collections | Créer une collection vide à schéma explicite | `collections-creer-une-collection-vide-a-schema-explicite` | 97.2 | = | moyenne | 97.3 | 100.0 | 100.0 | 90.0 |
| Features (OGC API) | Filtrer les features par intersection géométrique exacte (ST_Intersects) | `features-ogc-api-filtrer-les-features-par-intersection-geometrique-exacte-st-int` | 97.2 | = | moyenne | 93.0 | 100.0 | — | 100.0 |
| Catalogue/Items | Supprimer un item (cascade config + révisions + partages) | `catalogue-items-supprimer-un-item-cascade-config-revisions-partages` | 97.4 | = | moyenne | 95.3 | 100.0 | 95.0 | 100.0 |
| Builder — Analytique globale | Bandeau des filtres de contexte actifs avec effacement individuel/global | `builder-analytique-globale-bandeau-des-filtres-de-contexte-actifs-avec-effacemen` | 97.5 | = | moyenne | 95.8 | — | — | 100.0 |
| Builder — Analytique globale | Panneau Explorer (table + mini-carte) sur une source de donnees | `builder-analytique-globale-panneau-explorer-table-mini-carte-sur-une-source-de-d` | 97.5 | = | moyenne | 95.8 | — | — | 100.0 |
| Collections | Ré-embedding sémantique automatique d'une collection modifiée | `collections-re-embedding-semantique-automatique-d-une-collection-modifiee` | 97.5 | = | moyenne | 95.8 | — | — | 100.0 |
| Cartographie | Choisir une icône Lucide curatée pour la symbologie catégorielle d'une couche | `cartographie-choisir-une-icone-lucide-curatee-pour-la-symbologie-categorielle-d-` | 97.5 | = | moyenne | 95.9 | — | — | 100.0 |
| Plateforme IA | Générer une application de saisie complète sur une collection depuis un agent MCP | `plateforme-ia-generer-une-application-de-saisie-complete-sur-une-collection-depu` | 97.6 | = | moyenne | 93.9 | 100.0 | — | 100.0 |
| Automatisation | Exporter une App en bundle Statique (données gelées, sans backend) | `automatisation-exporter-une-app-en-bundle-statique-donnees-gelees-sans-backend` | 97.6 | = | moyenne | 92.0 | 100.0 | 100.0 | 100.0 |
| Automatisation | Exporter une App en mode Connecté (CORS restreint au domaine cible) | `automatisation-exporter-une-app-en-mode-connecte-cors-restreint-au-domaine-cible` | 97.6 | = | moyenne | 92.0 | 100.0 | 100.0 | 100.0 |
| Configs/Alerte | Évaluer une expression de condition d'alerte en SQL borné (sandboxé) | `configs-alerte-evaluer-une-expression-de-condition-d-alerte-en-sql-borne-sandbox` | 97.7 | = | moyenne | 96.2 | — | — | 100.0 |
| Carte | Téléchargement d'une pièce jointe depuis le popup de carte | `carte-telechargement-d-une-piece-jointe-depuis-le-popup-de-carte` | 97.9 | = | moyenne | 96.5 | — | — | 100.0 |
| Cartographie | Afficher un tileset 3D hébergé directement sur la carte (deck.gl) | `cartographie-afficher-un-tileset-3d-heberge-directement-sur-la-carte-deck-gl` | 97.9 | = | moyenne | 96.5 | — | — | 100.0 |
| Données | Éditeur de dataset partagé (métadonnées, colonnes, champ temporel, cross-filter) | `donnees-editeur-de-dataset-partage-metadonnees-colonnes-champ-temporel-cross-fil` | 98.6 | = | haute | 96.5 | 100.0 | — | 100.0 |
| Configs/AppConfig | Bâtir une app/dashboard/site no-code (pages, layout en grille, messages) | `configs-appconfig-batir-une-app-dashboard-site-no-code-pages-layout-en-grille-me` | 98.6 | = | haute | 96.5 | 100.0 | — | 100.0 |
| Catalogue/Items | Lister et rechercher les items du catalogue (recherche hybride) | `catalogue-items-lister-et-rechercher-les-items-du-catalogue-recherche-hybride` | 98.7 | = | haute | 96.7 | 100.0 | — | 100.0 |
| Apps & sites | Capturer une miniature depuis le canevas de l'app | `apps-sites-capturer-une-miniature-depuis-le-canevas-de-l-app` | 98.2 | = | moyenne | 95.6 | 100.0 | — | 100.0 |
| Catalogue/Items | Historique de versions et rollback d'une config | `catalogue-items-historique-de-versions-et-rollback-d-une-config` | 98.3 | +2.0 | moyenne | 98.4 | 100.0 | 95.0 | 100.0 |
| Carte | Ajout d'une couche par URL GeoJSON externe | `carte-ajout-d-une-couche-par-url-geojson-externe` | 98.9 | = | haute | 98.2 | — | — | 100.0 |
| Automatisation | Consulter l'historique des évaluations d'une règle d'alerte | `automatisation-consulter-l-historique-des-evaluations-d-une-regle-d-alerte` | 98.4 | = | moyenne | 94.6 | 100.0 | 100.0 | 100.0 |
| Catalogue/Items | Permissions calculées par item (une seule porte, read/write/delete/share) | `catalogue-items-permissions-calculees-par-item-une-seule-porte-read-write-delete` | 99.0 | = | haute | 98.4 | — | — | 100.0 |
| roles | Quatre rôles prédéfinis immuables par tenant (Administrateur, Créateur, Analyste, Lecteur) | `roles-quatre-roles-predefinis-immuables-par-tenant-administrateur-createur-analy` | 99.0 | = | haute | 98.4 | — | — | 100.0 |
| Configs/MapConfig | Couche de carte liée à une collection (tuiles/symbologie/pk) | `configs-mapconfig-couche-de-carte-liee-a-une-collection-tuiles-symbologie-pk` | 99.0 | = | haute | 98.4 | — | — | 100.0 |
| Extensibilité | Activer/désactiver une extension enregistrée sans la supprimer | `extensibilite-activer-desactiver-une-extension-enregistree-sans-la-supprimer` | 98.5 | = | moyenne | 95.1 | 100.0 | 100.0 | 100.0 |
| Extensibilité | Enregistrer un widget externe (Web Component) dans le registre d'extensions du tenant | `extensibilite-enregistrer-un-widget-externe-web-component-dans-le-registre-d-ext` | 98.5 | = | moyenne | 95.1 | 100.0 | 100.0 | 100.0 |
| Builder — Pages | Gestion multi-pages d'une app (PageManager) | `builder-pages-gestion-multi-pages-d-une-app-pagemanager` | 98.6 | = | moyenne | 97.6 | — | — | 100.0 |
| Automatisation | Lire une source REST ou Postgres externe dans un pipeline (connecteurs) | `automatisation-lire-une-source-rest-ou-postgres-externe-dans-un-pipeline-connect` | 98.7 | = | moyenne | 96.7 | 100.0 | — | 100.0 |
| Conformité | Anonymiser un utilisateur (droit à l'effacement RGPD) | `conformite-anonymiser-un-utilisateur-droit-a-l-effacement-rgpd` | 98.7 | = | moyenne | 95.8 | 100.0 | 100.0 | 100.0 |
| Conformité | Purger un tenant (suppression complète et irréversible) | `conformite-purger-un-tenant-suppression-complete-et-irreversible` | 98.7 | = | moyenne | 95.8 | 100.0 | 100.0 | 100.0 |
| Carte | Outil de croquis éphémère (formes libres, couleur) | `carte-outil-de-croquis-ephemere-formes-libres-couleur` | 98.7 | = | moyenne | 97.9 | — | — | 100.0 |
| Tâches | Centre de tâches | `taches-centre-de-taches` | 98.8 | = | moyenne | 95.8 | 100.0 | 100.0 | 100.0 |
| Automatisation | Créer et lancer un pipeline par l'IA (agent MCP) | `automatisation-creer-et-lancer-un-pipeline-par-l-ia-agent-mcp` | 98.8 | = | moyenne | 96.9 | 100.0 | — | 100.0 |
| Automatisation | Exporter une carte enregistrée (Bookmark) en image PNG ou PDF | `automatisation-exporter-une-carte-enregistree-bookmark-en-image-png-ou-pdf` | 98.8 | = | moyenne | 95.9 | 100.0 | 100.0 | 100.0 |
| Automatisation | Définir une règle d'alerte de seuil sur un dataset | `automatisation-definir-une-regle-d-alerte-de-seuil-sur-un-dataset` | 98.8 | = | moyenne | 95.9 | 100.0 | 100.0 | 100.0 |
| Automatisation | Exporter une App en conteneur Autoporté (mini-serveur embarqué) | `automatisation-exporter-une-app-en-conteneur-autoporte-mini-serveur-embarque` | 98.8 | = | moyenne | 96.0 | 100.0 | 100.0 | 100.0 |
| auth | Accès anonyme en lecture aux items/collections publics | `auth-acces-anonyme-en-lecture-aux-items-collections-publics` | 99.2 | +4.0 | haute | 98.7 | — | — | 100.0 |
| auth | Authentification OIDC (Keycloak) avec provisioning JIT du compte, et mode mock réservé au développement | `auth-authentification-oidc-keycloak-avec-provisioning-jit-du-compte-et-mode-mock` | 99.2 | +4.0 | haute | 98.7 | — | — | 100.0 |
| Catalogue | Créer un nouvel élément (App/Dashboard/Map/Site/Dataset/Pipeline/Requête visuelle) | `catalogue-creer-un-nouvel-element-app-dashboard-map-site-dataset-pipeline-requet` | 99.3 | +8.0 | haute | 98.8 | — | — | 100.0 |
| Carte | Légende simple des couches visibles | `carte-legende-simple-des-couches-visibles` | 98.9 | = | moyenne | 98.2 | — | — | 100.0 |
| Carte | Peinture MapLibre brute personnalisée sur une couche (paint), en repli sans symbologie déclarative | `carte-peinture-maplibre-brute-personnalisee-sur-une-couche-paint-en-repli-sans-s` | 97.9 | = | basse | 96.5 | — | — | 100.0 |
| Carte | Réglage de l'opacité d'une couche raster | `carte-reglage-de-l-opacite-d-une-couche-raster` | 97.9 | = | basse | 96.5 | — | — | 100.0 |
| Carte | Visualisations deck.gl agrégées (heatmap/hexbin/column) | `carte-visualisations-deck-gl-agregees-heatmap-hexbin-column` | 98.9 | +4.0 | moyenne | 98.2 | — | — | 100.0 |
| roles | Catalogue des privilèges pour construire l'UI de gestion des rôles | `roles-catalogue-des-privileges-pour-construire-l-ui-de-gestion-des-roles` | 99.0 | = | moyenne | 98.4 | — | — | 100.0 |
| roles | Garde anti-lockout sur la modification ou suppression d'un rôle | `roles-garde-anti-lockout-sur-la-modification-ou-suppression-d-un-role` | 99.0 | = | moyenne | 98.4 | — | — | 100.0 |
| Apps & sites | Annuler/Rétablir dans le builder d'app | `apps-sites-annuler-retablir-dans-le-builder-d-app` | 99.1 | = | moyenne | 97.8 | 100.0 | — | 100.0 |
| Fédération des données | Créer un Dataset de plateforme à partir d'un Feature Service ArcGIS déjà moissonné (source live, sans copie) | `federation-des-donnees-creer-un-dataset-de-plateforme-a-partir-d-un-feature-serv` | 99.3 | +8.0 | moyenne | 98.8 | — | — | 100.0 |
| auth | Garde : refus de démarrer en mode mock d'authentification hors développement | `auth-garde-refus-de-demarrer-en-mode-mock-d-authentification-hors-developpement` | 99.6 | +4.0 | haute | 99.4 | — | — | 100.0 |
| Conformité | Mesurer l'usage de stockage et de ressources d'un tenant | `conformite-mesurer-l-usage-de-stockage-et-de-ressources-d-un-tenant` | 98.9 | = | basse | 96.4 | 100.0 | 100.0 | 100.0 |
| Configs/Dataset | Définir un dataset comme objet de plateforme (source collection ou ArcGIS) | `configs-dataset-definir-un-dataset-comme-objet-de-plateforme-source-collection-o` | 99.7 | = | haute | 99.2 | 100.0 | — | 100.0 |
| Catalogue/Portails publics | Lire la config d'un item publié (anonyme) | `catalogue-portails-publics-lire-la-config-d-un-item-publie-anonyme` | 99.5 | = | moyenne | 98.4 | 100.0 | 100.0 | 100.0 |
| Automatisation | Consulter l'historique des exécutions d'un rapport planifié | `automatisation-consulter-l-historique-des-executions-d-un-rapport-planifie` | 99.6 | = | moyenne | 98.7 | 100.0 | 100.0 | 100.0 |
| Catalogue/Portails publics | Résoudre un site publié par son slug | `catalogue-portails-publics-resoudre-un-site-publie-par-son-slug` | 99.6 | = | moyenne | 98.8 | 100.0 | 100.0 | 100.0 |
| Configs/Bookmark | Enregistrer un signet d'état analytique (temps, emprise, cross-filter) | `configs-bookmark-enregistrer-un-signet-d-etat-analytique-temps-emprise-cross-fil` | 99.7 | = | moyenne | 99.2 | 100.0 | — | 100.0 |
| Administration | Accéder à la console MinIO depuis la page d'infrastructure admin | `administration-acceder-a-la-console-minio-depuis-la-page-d-infrastructure-admin` | 100.0 | = | basse | 100.0 | — | — | 100.0 |
| audit | Consulter le journal d'audit des actions sensibles | `audit-consulter-le-journal-d-audit-des-actions-sensibles` | 100.0 | = | haute | 100.0 | — | — | 100.0 |
| auth | Capacités de déploiement dupliquées sur GET /me pour éviter deux requêtes par écran | `auth-capacites-de-deploiement-dupliquees-sur-get-me-pour-eviter-deux-requetes-pa` | 100.0 | = | basse | 100.0 | — | — | 100.0 |
| auth | Jeton d'export à usage interne pour le rendu authentifié du worker Playwright | `auth-jeton-d-export-a-usage-interne-pour-le-rendu-authentifie-du-worker-playwrig` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| auth | Promotion automatique en Administrateur ou Analyste par sub OIDC (CORE_ADMIN_SUBS / CORE_ANALYST_SUBS) | `auth-promotion-automatique-en-administrateur-ou-analyste-par-sub-oidc-core-admin` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Automatisation | Lister les pièces jointes d'une entité via un agent MCP | `automatisation-lister-les-pieces-jointes-d-une-entite-via-un-agent-mcp` | 100.0 | = | moyenne | 100.0 | 100.0 | — | 100.0 |
| Automatisation | Stocker un secret chiffré (clé API, DSN Postgres) pour un connecteur de pipeline | `automatisation-stocker-un-secret-chiffre-cle-api-dsn-postgres-pour-un-connecteur` | 100.0 | = | moyenne | 100.0 | 100.0 | 100.0 | 100.0 |
| Automatisation | Écrire le résultat d'un pipeline dans une collection existante ou en créer une nouvelle | `automatisation-ecrire-le-resultat-d-un-pipeline-dans-une-collection-existante-ou` | 100.0 | = | haute | 100.0 | — | — | 100.0 |
| Builder — Actions composees | Bus d'evenements/actions par app (ActionBus) | `builder-actions-composees-bus-d-evenements-actions-par-app-actionbus` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Actions composees | Compositeur d'actions widget-a-widget (ActionsPanel) | `builder-actions-composees-compositeur-d-actions-widget-a-widget-actionspanel` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Actions composees | Liste des actions filtree par page (mais config globale) | `builder-actions-composees-liste-des-actions-filtree-par-page-mais-config-globale` | 100.0 | = | basse | 100.0 | — | — | 100.0 |
| Builder — Analytique globale | Contexte analytique global (periode x emprise x cross-filter) | `builder-analytique-globale-contexte-analytique-global-periode-x-emprise-x-cross-` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Automatisation (pipelines) | Validation locale du graphe de pipeline (miroir du serveur) | `builder-automatisation-pipelines-validation-locale-du-graphe-de-pipeline-miroir-` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — CEL & expressions | Bindings CEL generalises sur n'importe quelle prop de widget | `builder-cel-expressions-bindings-cel-generalises-sur-n-importe-quelle-prop-de-wi` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — CEL & expressions | Diagnostic centralise des erreurs d'expression CEL avant sauvegarde | `builder-cel-expressions-diagnostic-centralise-des-erreurs-d-expression-cel-avant` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — CEL & expressions | Visibilite conditionnelle d'un widget (visibleWhen, CEL) | `builder-cel-expressions-visibilite-conditionnelle-d-un-widget-visiblewhen-cel` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Copilote IA | Cinq operations client allowlistees pour le copilote | `builder-copilote-ia-cinq-operations-client-allowlistees-pour-le-copilote` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Copilote IA | Jeton MCP scope obtenu par signinSilent iframe pour le copilote | `builder-copilote-ia-jeton-mcp-scope-obtenu-par-signinsilent-iframe-pour-le-copil` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Donnees | Neuf agregats analytiques dont countDistinct/median/percentile/stddev | `builder-donnees-neuf-agregats-analytiques-dont-countdistinct-median-percentile-s` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Modeles | Cinq modeles de demarrage (app/tableau de bord/site) | `builder-modeles-cinq-modeles-de-demarrage-app-tableau-de-bord-site` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Requete visuelle | Constructeur de filtres visuel compile en SQL parametrable | `builder-requete-visuelle-constructeur-de-filtres-visuel-compile-en-sql-parametra` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Requete visuelle | Inference du schema de sortie d'une requete visuelle (colonnes/types) | `builder-requete-visuelle-inference-du-schema-de-sortie-d-une-requete-visuelle-co` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Runtime | Grille responsive multi-breakpoints (sm/md/lg) | `builder-runtime-grille-responsive-multi-breakpoints-sm-md-lg` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Runtime | Isolation des crashs de widget (error boundary) | `builder-runtime-isolation-des-crashs-de-widget-error-boundary` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Runtime | Redimensionnement d'un widget sur le canevas | `builder-runtime-redimensionnement-d-un-widget-sur-le-canevas` | 100.0 | = | haute | 100.0 | — | — | 100.0 |
| Builder — SDK & extensions | Pont Web Components pour widgets tiers (props/evenements/actions) | `builder-sdk-extensions-pont-web-components-pour-widgets-tiers-props-evenements-a` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — SDK & extensions | SDK public re-exporte pour les auteurs de widgets tiers | `builder-sdk-extensions-sdk-public-re-exporte-pour-les-auteurs-de-widgets-tiers` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — SDK & extensions | Widget de demonstration 'Compteur (WC)' toujours present dans la palette de production | `builder-sdk-extensions-widget-de-demonstration-compteur-wc-toujours-present-dans` | 100.0 | = | basse | 100.0 | — | — | 100.0 |
| Builder — SDK & extensions | Widgets d'extension charges dynamiquement (modules ES tiers) | `builder-sdk-extensions-widgets-d-extension-charges-dynamiquement-modules-es-tier` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Theme | Theme d'app (couleurs/police/arrondi/espacement) | `builder-theme-theme-d-app-couleurs-police-arrondi-espacement` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Widgets | Rattachement direct a un dataset partage depuis le PropsPanel d'un widget | `builder-widgets-rattachement-direct-a-un-dataset-partage-depuis-le-propspanel-d-` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Builder — Widgets | Telechargement direct GeoJSON/CSV d'un jeu de donnees | `builder-widgets-telechargement-direct-geojson-csv-d-un-jeu-de-donnees` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Carte | Catalogue de sources de couches (collections du cœur, couches raster moissonnées, tuiles 3D hébergées) | `carte-catalogue-de-sources-de-couches-collections-du-cur-couches-raster-moissonn` | 100.0 | +4.0 | haute | 100.0 | — | — | 100.0 |
| Carte | Classification par seuils naturels (Jenks) | `carte-classification-par-seuils-naturels-jenks` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Carte | Contrôle de la caméra 3D (inclinaison/orientation) | `carte-controle-de-la-camera-3d-inclinaison-orientation` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Carte | Introspection d'une couche GeoJSON externe (champs, statistiques calculés côté client) | `carte-introspection-d-une-couche-geojson-externe-champs-statistiques-calcules-co` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Carte | Outil de mesure de distance et de surface | `carte-outil-de-mesure-de-distance-et-de-surface` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Carte | Palette de couleur reprenant le thème du site (theme-primary) | `carte-palette-de-couleur-reprenant-le-theme-du-site-theme-primary` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Carte | Persistance de collectionId/pkColumn sur une couche 'feature' (URL GeoJSON) | `carte-persistance-de-collectionid-pkcolumn-sur-une-couche-feature-url-geojson` | 100.0 | +4.0 | moyenne | 100.0 | — | — | 100.0 |
| Carte | Persistance de la configuration de carte (basemap, vue, couches, terrain, mise en page d'impression) | `carte-persistance-de-la-configuration-de-carte-basemap-vue-couches-terrain-mise-` | 100.0 | +4.0 | haute | 100.0 | — | — | 100.0 |
| Carte | Popup avancé : gabarit Markdown avec expressions CEL | `carte-popup-avance-gabarit-markdown-avec-expressions-cel` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Carte | Symbologie couleur catégorielle/continue/classée | `carte-symbologie-couleur-categorielle-continue-classee` | 100.0 | = | haute | 100.0 | — | — | 100.0 |
| Carte | Sélection du fond de carte (basemap) | `carte-selection-du-fond-de-carte-basemap` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Cartes | Rendu export headless (chrome masqué pour capture Playwright) | `cartes-rendu-export-headless-chrome-masque-pour-capture-playwright` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Catalogue/Items | Métadonnées ouvertes d'un item (licence, langue) | `catalogue-items-metadonnees-ouvertes-d-un-item-licence-langue` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| CI/Qualité | Auditer les dépendances npm à la recherche de vulnérabilités connues, avec allowlist | `ci-qualite-auditer-les-dependances-npm-a-la-recherche-de-vulnerabilites-connues-` | 100.0 | +4.0 | moyenne | 100.0 | — | — | 100.0 |
| CI/Qualité | Auditer les dépendances Python à la recherche de vulnérabilités connues | `ci-qualite-auditer-les-dependances-python-a-la-recherche-de-vulnerabilites-connu` | 100.0 | +4.0 | moyenne | 100.0 | — | — | 100.0 |
| CI/Qualité | Empêcher qu'un nom documenté dans .env.example comme réglable ne soit en réalité substitué nulle part | `ci-qualite-empecher-qu-un-nom-documente-dans-env-example-comme-reglable-ne-soit-` | 100.0 | = | moyenne | — | — | — | 100.0 |
| CI/Qualité | Empêcher qu'une variable d'environnement lue par le cœur reste non câblée dans la stack packagée | `ci-qualite-empecher-qu-une-variable-d-environnement-lue-par-le-cur-reste-non-cab` | 100.0 | = | haute | — | — | — | 100.0 |
| CI/Qualité | Empêcher toute dérive entre le schéma OpenAPI du cœur et les types TS générés côté shell | `ci-qualite-empecher-toute-derive-entre-le-schema-openapi-du-cur-et-les-types-ts-` | 100.0 | +4.0 | haute | 100.0 | — | — | 100.0 |
| CI/Qualité | Exécuter la suite E2E shell contre un vrai serveur Keycloak (OIDC réel, pas le mode mock) | `ci-qualite-executer-la-suite-e2e-shell-contre-un-vrai-serveur-keycloak-oidc-reel` | 100.0 | +4.0 | moyenne | 100.0 | — | — | 100.0 |
| CI/Qualité | Garantir qu'aucune image (propre ou tierce) n'utilise un tag flottant (latest, mineur/majeur nu, mot-clé mouvant) | `ci-qualite-garantir-qu-aucune-image-propre-ou-tierce-n-utilise-un-tag-flottant-l` | 100.0 | = | moyenne | — | — | — | 100.0 |
| CI/Qualité | Garantir que la porte de release démarre Postgres avec les mêmes réglages que la CI | `ci-qualite-garantir-que-la-porte-de-release-demarre-postgres-avec-les-memes-regl` | 100.0 | = | moyenne | — | — | — | 100.0 |
| CI/Qualité | Vérifier automatiquement lint/format/tests/couverture/E2E/build du shell à chaque push/PR | `ci-qualite-verifier-automatiquement-lint-format-tests-couverture-e2e-build-du-sh` | 100.0 | +4.0 | haute | 100.0 | — | — | 100.0 |
| CI/Qualité | Vérifier automatiquement lint/format/types/tests/couverture du cœur à chaque push/PR | `ci-qualite-verifier-automatiquement-lint-format-types-tests-couverture-du-cur-a-` | 100.0 | +4.0 | haute | 100.0 | — | — | 100.0 |
| Collections | Permissions calculées par collection, avec bypass admin.collections.manage sur GET/PATCH/DELETE/schema/sharing | `collections-permissions-calculees-par-collection-avec-bypass-admin-collections-m` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Collections | RLS multi-tenant appliquée automatiquement à toute nouvelle collection | `collections-rls-multi-tenant-appliquee-automatiquement-a-toute-nouvelle-collecti` | 100.0 | = | haute | 100.0 | — | — | 100.0 |
| Configs/Alerte | Valider qu'une règle d'alerte référence un dataset lisible | `configs-alerte-valider-qu-une-regle-d-alerte-reference-un-dataset-lisible` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Configs/Bookmark | Valider qu'un bookmark référence une app/dashboard lisible | `configs-bookmark-valider-qu-un-bookmark-reference-une-app-dashboard-lisible` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Configs/Dataset | Rattacher un dataset à son pipeline source (créé via la requête visuelle) | `configs-dataset-rattacher-un-dataset-a-son-pipeline-source-cree-via-la-requete-v` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Configs/Dataset | Valider qu'un dataset référence une collection lisible du même tenant | `configs-dataset-valider-qu-un-dataset-reference-une-collection-lisible-du-meme-t` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Configs/Pipeline | Valider la topologie et les opérations d'un pipeline (acyclique, un seul reader/writer par nœud, ops connus) | `configs-pipeline-valider-la-topologie-et-les-operations-d-un-pipeline-acyclique-` | 100.0 | = | haute | 100.0 | — | — | 100.0 |
| Configs/Rapport | Valider qu'un rapport référence un bookmark lisible | `configs-rapport-valider-qu-un-rapport-reference-un-bookmark-lisible` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Configs/Schéma | Publier le schéma JSON d'AppConfig en HTTP | `configs-schema-publier-le-schema-json-d-appconfig-en-http` | 100.0 | = | basse | 100.0 | 100.0 | 100.0 | 100.0 |
| Données | Fiche dataset publique (/public/datasets/:collectionId) | `donnees-fiche-dataset-publique-public-datasets-collectionid` | 100.0 | = | haute | 100.0 | 100.0 | — | 100.0 |
| Déploiement | Démarrer une stack de développement complète en une commande | `deploiement-demarrer-une-stack-de-developpement-complete-en-une-commande` | 100.0 | = | haute | 100.0 | — | — | 100.0 |
| Déploiement | Générer automatiquement un .env avec des secrets forts au premier démarrage | `deploiement-generer-automatiquement-un-env-avec-des-secrets-forts-au-premier-dem` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Export statique | Chargement des extensions tierces en mode Connecte uniquement | `export-statique-chargement-des-extensions-tierces-en-mode-connecte-uniquement` | 100.0 | = | moyenne | — | — | — | 100.0 |
| Export statique | Runtime autonome pour bundle d'app exporte (Statique + Connecte) | `export-statique-runtime-autonome-pour-bundle-d-app-exporte-statique-connecte` | 100.0 | = | haute | — | — | — | 100.0 |
| Extensibilité | Découvrir les extensions actives et les capacités de l'instance depuis une page d'admin | `extensibilite-decouvrir-les-extensions-actives-et-les-capacites-de-l-instance-de` | 100.0 | = | moyenne | 100.0 | 100.0 | — | 100.0 |
| Fédération des données | Couches raster externes moissonnées (WMS/WMTS) proposées dans le sélecteur de couches de la carte | `federation-des-donnees-couches-raster-externes-moissonnees-wms-wmts-proposees-da` | 100.0 | +4.0 | moyenne | 100.0 | — | — | 100.0 |
| Fédération des données | Export DCAT-AP du catalogue (catalogue complet + fiche dataset, JSON-LD) | `federation-des-donnees-export-dcat-ap-du-catalogue-catalogue-complet-fiche-datas` | 100.0 | = | moyenne | 100.0 | 100.0 | 100.0 | 100.0 |
| Fédération des données | Planification périodique du moissonnage d'une source (intervalle en minutes) | `federation-des-donnees-planification-periodique-du-moissonnage-d-une-source-inte` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| i18n | Catalogue de messages français (t()) | `i18n-catalogue-de-messages-francais-t` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| instance | Statut des capacités du déploiement, visible sans authentification | `instance-statut-des-capacites-du-deploiement-visible-sans-authentification` | 100.0 | = | haute | 100.0 | 100.0 | 100.0 | 100.0 |
| Navigation | Bandeau lecture seule (mode démo) | `navigation-bandeau-lecture-seule-mode-demo` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Navigation | Barre de statut (version + tenant) | `navigation-barre-de-statut-version-tenant` | 100.0 | = | basse | 100.0 | — | — | 100.0 |
| Navigation | Layout triptyque adaptatif (3 colonnes desktop / onglets mobile) | `navigation-layout-triptyque-adaptatif-3-colonnes-desktop-onglets-mobile` | 100.0 | = | haute | 100.0 | — | — | 100.0 |
| Navigation | Menu compte (rôle affiché + déconnexion) | `navigation-menu-compte-role-affiche-deconnexion` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Paramètres | Paramètres d'instance et de tenant | `parametres-parametres-d-instance-et-de-tenant` | 100.0 | = | moyenne | 100.0 | 100.0 | — | 100.0 |
| Plateforme IA | Modifier le partage d'un item depuis un agent MCP | `plateforme-ia-modifier-le-partage-d-un-item-depuis-un-agent-mcp` | 100.0 | = | moyenne | 100.0 | 100.0 | — | 100.0 |
| Recherche | Recherche hybride des collections (même mécanisme RRF que les items) | `recherche-recherche-hybride-des-collections-meme-mecanisme-rrf-que-les-items` | 100.0 | = | moyenne | 100.0 | 100.0 | — | 100.0 |
| Release | Générer et publier un SBOM par image de release | `release-generer-et-publier-un-sbom-par-image-de-release` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Release | Publier une release taguée : porte de tests puis construction/publication de 8 images sur un registre public | `release-publier-une-release-taguee-porte-de-tests-puis-construction-publication-` | 100.0 | = | haute | 100.0 | — | — | 100.0 |
| Release | Scanner les images publiées à la recherche de vulnérabilités (Trivy, report-only) | `release-scanner-les-images-publiees-a-la-recherche-de-vulnerabilites-trivy-repor` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| roles | Navigation dérivée du profil : un domaine sans privilège est masqué, un domaine sans capacité est verrouillé et expliqué | `roles-navigation-derivee-du-profil-un-domaine-sans-privilege-est-masque-un-domai` | 100.0 | = | haute | 100.0 | — | — | 100.0 |
| Réseau/Sécurité | Ajouter des en-têtes de sécurité HTTP (HSTS, nosniff, frame-deny, referrer-policy) sur les routes exposées | `reseau-securite-ajouter-des-en-tetes-de-securite-http-hsts-nosniff-frame-deny-re` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Réseau/Sécurité | Limiter le débit de requêtes contre le cœur et le shell exposés | `reseau-securite-limiter-le-debit-de-requetes-contre-le-cur-et-le-shell-exposes` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Réseau/Sécurité | Protéger l'accès direct à Martin par un secret dédié | `reseau-securite-proteger-l-acces-direct-a-martin-par-un-secret-dedie` | 100.0 | = | basse | 100.0 | — | — | 100.0 |
| Sauvegarde | Garantir que chaque bucket S3 utilisé par le cœur est couvert par la sauvegarde | `sauvegarde-garantir-que-chaque-bucket-s3-utilise-par-le-cur-est-couvert-par-la-s` | 100.0 | = | moyenne | — | — | — | 100.0 |
| Sauvegarde | Répliquer les sauvegardes vers une cible hors-site S3-compatible | `sauvegarde-repliquer-les-sauvegardes-vers-une-cible-hors-site-s3-compatible` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Sauvegarde | Sauvegarde quotidienne chiffrée de Postgres, des buckets MinIO et du realm Keycloak | `sauvegarde-sauvegarde-quotidienne-chiffree-de-postgres-des-buckets-minio-et-du-r` | 100.0 | = | haute | 100.0 | — | — | 100.0 |
| Supervision | Détecter automatiquement un service en panne avant de router du trafic vers lui | `supervision-detecter-automatiquement-un-service-en-panne-avant-de-router-du-traf` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Supervision | Observabilité packagée (Grafana + Prometheus + Loki + Tempo, dashboards pré-provisionnés) | `supervision-observabilite-packagee-grafana-prometheus-loki-tempo-dashboards-pre-` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| Sécurité | Limiter le débit des routes sensibles (SQL Lab, LLM/copilote, jobs d'export/appexport, écritures harvest) par jeton appelant | `securite-limiter-le-debit-des-routes-sensibles-sql-lab-llm-copilote-jobs-d-expor` | 100.0 | = | moyenne | 100.0 | — | — | 100.0 |
| tenants | Provisionnement d'un tenant unique par défaut (multi-tenant non exposé à l'utilisateur) | `tenants-provisionnement-d-un-tenant-unique-par-defaut-multi-tenant-non-expose-a-` | 100.0 | = | basse | 100.0 | — | — | 100.0 |
