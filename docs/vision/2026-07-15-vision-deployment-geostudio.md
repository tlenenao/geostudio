# Vision GeoStudio

## 1. Ambition produit

GeoStudio est une plateforme SIG + DataViz + Analytics + IA conçue comme un produit logiciel professionnel ouvert, automatisable et déployable partout.

Objectifs :
- SIG Web ;
- Application Builder ;
- Dashboard Builder ;
- visualisation et analyse de données ;
- catalogue de données ;
- IA, agents et RAG ;
- connecteurs universels ;
- architecture extensible par plugins.

Positionnement : GeoStudio vise une alternative ouverte aux plateformes comme ArcGIS Experience Builder / Portal, Grafana, Power BI, GeoNode et MapStore, en combinant cartographie avancée, analytics, automatisation et intelligence artificielle.

Différenciation : une plateforme géospatiale moderne, API-first, plugin-ready et déployable du poste local au cloud entreprise.

## 2. Architecture cible

Utilisateur → HTTPS → Reverse Proxy → React Shell + FastAPI Core → PostgreSQL/PostGIS → Martin / TiTiler / MinIO → Keycloak / OIDC

Frontend : React, TypeScript, builder, dashboards, widgets et plugins.

Backend : FastAPI, API métier, services spécialisés et extensions.

Données : PostgreSQL/PostGIS, stockage objet S3 compatible MinIO, vector tiles et raster tiles.

Sécurité : Keycloak, OIDC, RBAC.

## 3. Stratégie de déploiement

### Développement
Docker Compose, hot reload et environnement reproductible.

### Appliance
Installation autonome via :

`geostudio install`

### Production
HTTPS, SSO, monitoring, logs, sauvegardes.

### Enterprise
Kubernetes, Helm, haute disponibilité, cloud-native.

## 4. Industrialisation

Images Docker versionnées :
- ghcr.io/geostudio/core:vX
- ghcr.io/geostudio/shell:vX

Pipeline : Commit → Tests → Build Docker → Scan sécurité → Registry → Déploiement

## 5. GeoStudio CLI

Commandes : install, detect, start, stop, status, upgrade, rollback, backup, restore, doctor.

## 6. Gestion des données

`/var/lib/geostudio`

- postgres/
- minio/
- uploads/
- backups/
- config/
- logs/

Séparation code/données, migrations versionnées, rollback et restauration complète.

## 7. Roadmap

v0.1 Deployment Foundation

v0.2 GeoStudio Appliance

v0.3 GeoStudio CLI

v0.4 Production Ready

v1.0 Enterprise Platform

## 8. Backlog GitHub initial

Milestones : Docker, appliance, CLI, CI/CD, monitoring, Kubernetes, multi-tenant, plugins.

## 9. Critères de réussite

Installer, déployer, mettre à jour, restaurer et migrer GeoStudio sans manipuler directement l'infrastructure.