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

Architecture globale :

Utilisateur
→ HTTPS
→ Reverse Proxy
→ React Shell + FastAPI Core
→ PostgreSQL/PostGIS
→ Martin / TiTiler / MinIO
→ Keycloak / OIDC

### Frontend
- React ;
- TypeScript ;
- builder d'applications ;
- dashboards ;
- widgets et plugins.

### Backend
- FastAPI ;
- API métier ;
- services spécialisés ;
- mécanismes d'extension.

### Données
- PostgreSQL/PostGIS ;
- stockage objet S3 compatible MinIO ;
- vector tiles ;
- raster tiles.

### Sécurité
- Keycloak ;
- OIDC ;
- RBAC ;
- gestion des organisations.

## 3. Stratégie de déploiement

### Développement

Docker Compose, hot reload et environnement développeur reproductible.

### Appliance

Cible : PC serveur i5, 16 Go RAM, SSD 512 Go ou VM.

Objectif : installation autonome :

`geostudio install`

Composants : Shell, Core, PostgreSQL/PostGIS, Martin, TiTiler, MinIO optionnel et Keycloak.

### Production

Inclut :
- HTTPS ;
- SSO ;
- monitoring ;
- logs ;
- sauvegardes ;
- certificats.

### Enterprise

- Kubernetes ;
- Helm ;
- haute disponibilité ;
- architecture cloud-native.

## 4. Industrialisation

### Docker

Images versionnées :

- ghcr.io/geostudio/core:vX
- ghcr.io/geostudio/shell:vX

Profils :
- minimal ;
- standard ;
- enterprise.

Configuration par variables d'environnement, secrets et volumes persistants.

### CI/CD

Pipeline :

Commit
↓
Tests
↓
Build Docker
↓
Scan sécurité
↓
Registry
↓
Déploiement

Technologies : GitHub Actions, GHCR et releases versionnées.

## 5. GeoStudio CLI

CLI officiel :

```bash
geostudio install
geostudio detect
geostudio start
geostudio stop
geostudio status
geostudio upgrade
geostudio rollback
geostudio backup
geostudio restore
geostudio doctor
```

Fonctions :
- détection matériel ;
- sélection automatique du profil ;
- génération configuration ;
- installation ;
- migrations ;
- sauvegarde/restauration ;
- diagnostic.

## 6. Gestion des données

Répertoire :

```
/var/lib/geostudio
├── postgres/
├── minio/
├── uploads/
├── backups/
├── config/
└── logs/
```

Principes :
- séparation code/données ;
- migrations versionnées ;
- rollback ;
- restauration complète.

## 7. Roadmap produit

### v0.1 Deployment Foundation
- Docker production ;
- compose profiles ;
- documentation ;
- health checks.

### v0.2 GeoStudio Appliance
- installateur ;
- détection matériel ;
- configuration automatique ;
- dataset démo.

### v0.3 GeoStudio CLI
- CLI Python ;
- install ;
- doctor ;
- upgrade ;
- backup/restore.

### v0.4 Production Ready
- CI/CD ;
- monitoring ;
- logs ;
- sécurité ;
- migrations.

### v1.0 Enterprise Platform
- Kubernetes ;
- Helm ;
- multi-tenant ;
- SSO entreprise ;
- audit ;
- marketplace plugins.

## 8. Backlog GitHub initial

### v0.1
- Create production Docker images
- Add Docker Compose profiles
- Add environment templates
- Add health checks
- Add deployment documentation

### v0.2
- Create installation wizard
- Add hardware detection
- Generate configuration automatically
- Initialize PostGIS database
- Add demo dataset

### v0.3
- Implement geostudio-cli
- Add install command
- Add doctor command
- Add upgrade workflow
- Add backup/restore

### v0.4
- Add GitHub Actions release pipeline
- Publish Docker images
- Add monitoring stack
- Add centralized logs
- Add migration system

### v1.0
- Create Helm charts
- Kubernetes deployment
- Multi-tenant architecture
- Enterprise authentication
- Audit logging
- Plugin marketplace

## 9. Critères de réussite

Un utilisateur doit pouvoir :

1. Installer GeoStudio avec une commande.
2. Déployer sur PC, serveur ou cloud.
3. Mettre à jour sans perte de données.
4. Restaurer une instance.
5. Migrer entre environnements.
6. Exploiter la plateforme sans manipuler Docker directement.
