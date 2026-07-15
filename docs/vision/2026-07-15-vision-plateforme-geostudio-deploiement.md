# Vision unifiée — GeoStudio plateforme déployable

Date : 2026-07-15

## Ambition

GeoStudio doit devenir une plateforme complète SIG + DataViz + Analytics + IA, déployable partout avec une expérience proche d'une appliance logicielle.

Principe :

> Une seule plateforme, plusieurs modes de déploiement.

---

# Architecture cible

```
Utilisateur
 |
 HTTPS
 |
 Reverse Proxy
 |
 +----------------+
 |                |
Shell React     Core API
 |                |
 +-------+--------+
         |
      PostGIS
         |
 +-------+-------+
 |       |       |
Martin TiTiler MinIO

Keycloak / OIDC
```

---

# Déploiements supportés

## Développeur

Docker Compose, hot reload.

## Appliance

PC serveur :

- i5
- 16 Go RAM
- SSD 512 Go

Installation :

```bash
geostudio install
```

## Production

Serveur entreprise :

- HTTPS
- SSO
- monitoring
- sauvegardes

## Enterprise

Kubernetes + Helm.

---

# Philosophie d'installation

L'utilisateur ne doit pas gérer :

- Docker Compose ;
- variables complexes ;
- migrations ;
- certificats.

Le CLI automatise tout.

---

# GeoStudio CLI

Commandes principales :

```bash
geostudio install
geostudio status
geostudio upgrade
geostudio backup
geostudio restore
geostudio doctor
```

---

# Industrialisation

## Conteneurs

Images versionnées :

```
core:v1
shell:v1
```

## Configuration

Profils :

- minimal
- standard
- enterprise

## CI/CD

Pipeline :

```
Code
 ↓
Tests
 ↓
Build Docker
 ↓
Release
 ↓
Déploiement
```

---

# Données et exploitation

Les données sont séparées du logiciel :

```
postgres/
minio/
backups/
config/
```

Les mises à jour doivent être réversibles.

---

# Roadmap

## Court terme

- Docker production
- profils compose
- documentation déploiement

## Moyen terme

- CLI
- CI/CD
- backup
- monitoring

## Long terme

- Kubernetes
- multi-tenant
- marketplace plugins

---

# Backlog GitHub et milestones

## Milestone v0.1 — Deployment Foundation

Objectif : rendre le déploiement reproductible.

Issues :

- Create production Docker images
- Add Docker Compose profiles (minimal/demo/production)
- Add environment configuration templates
- Add service health checks
- Document installation architecture

---

## Milestone v0.2 — GeoStudio Appliance

Objectif : installer GeoStudio sur un serveur autonome.

Issues :

- Create installation wizard
- Add hardware detection
- Generate configuration automatically
- Initialize PostGIS database
- Create demo dataset installation

---

## Milestone v0.3 — GeoStudio CLI

Objectif : fournir une interface d'administration officielle.

Issues :

- Implement geostudio-cli Python package
- Add install command
- Add status command
- Add doctor command
- Add upgrade workflow
- Add backup/restore commands

---

## Milestone v0.4 — Production Ready

Objectif : exploitation professionnelle.

Issues :

- Add GitHub Actions release pipeline
- Publish Docker images to registry
- Add monitoring stack
- Add centralized logs
- Add database migration system
- Add rollback mechanism

---

## Milestone v1.0 — Enterprise Platform

Objectif : déploiement organisationnel.

Issues :

- Create Helm charts
- Kubernetes deployment
- Multi-tenant architecture
- Enterprise authentication
- Audit logging
- Plugin marketplace

---

# Processus de développement recommandé

Chaque fonctionnalité suit le cycle :

```
Issue GitHub
    ↓
Développement
    ↓
Tests automatiques
    ↓
Pull Request
    ↓
Release
    ↓
Déploiement
```

---

# Positionnement

GeoStudio vise une approche entre :

- ArcGIS Experience Builder pour le builder ;
- Grafana/PowerBI pour la datavisualisation ;
- GeoNode/MapStore pour le SIG ;
- plateformes IA modernes pour les agents et assistants.

La différenciation : une plateforme ouverte, géospatiale et automatisable.
