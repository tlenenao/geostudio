# Roadmap d'industrialisation GeoStudio

Date : 2026-07-15

## Objectif

Transformer GeoStudio en une plateforme SIG/DataViz/IA déployable comme un produit logiciel complet.

Objectif final :

```bash
geostudio install
```

permet d'obtenir une instance fonctionnelle sur un poste local, un serveur ou une infrastructure cloud.

---

# Phase 0 — Fondations

Durée indicative : 1 mois

## Objectifs

Stabiliser la base de déploiement.

Actions :

- standardiser les Dockerfiles ;
- définir les images officielles ;
- créer les profils compose ;
- documenter les prérequis.

Livrables :

```
deploy/
├── compose/
├── env/
└── scripts/
```

---

# Phase 1 — Appliance GeoStudio

Durée indicative : 2 mois

Cible : PC serveur i5/16 Go RAM.

Fonctionnalités :

- installation automatique ;
- génération configuration ;
- création administrateur ;
- initialisation base PostGIS ;
- jeu de données exemple.

Commande cible :

```bash
curl install.geostudio.io | bash
```

---

# Phase 2 — GeoStudio CLI

Créer l'outil officiel :

```bash
geostudio install
geostudio status
geostudio upgrade
geostudio backup
geostudio doctor
```

Fonctions :

- détection matériel ;
- gestion profils ;
- diagnostic ;
- maintenance.

---

# Phase 3 — CI/CD

Mettre en place :

GitHub Actions :

```
commit
 |
 tests
 |
 build images
 |
 scan sécurité
 |
 publication GHCR
 |
 déploiement
```

Livrables :

- releases versionnées ;
- changelog automatique ;
- images Docker officielles.

---

# Phase 4 — Exploitation production

Ajouter :

- monitoring Prometheus/Grafana ;
- logs Loki ;
- OpenTelemetry ;
- backups automatisés ;
- rotation secrets.

---

# Phase 5 — Enterprise

Objectif : collectivités et grandes organisations.

Fonctionnalités :

- SSO OIDC/SAML ;
- RBAC avancé ;
- multi-instance ;
- audit ;
- haute disponibilité.

---

# Phase 6 — Kubernetes

Créer :

```
charts/geostudio
```

Support :

- Helm ;
- Ingress ;
- StatefulSets ;
- stockage externe ;
- autoscaling.

---

# Backlog technique prioritaire

## P0

- Dockerfiles production
- compose profiles
- documentation installation
- health checks

## P1

- CLI Python
- backup/restore
- migrations DB
- CI/CD

## P2

- monitoring
- plugins déploiement
- marketplace

## P3

- Kubernetes
- multi-tenant
- HA

---

# Critères de réussite

Un utilisateur doit pouvoir :

1. installer GeoStudio sans connaissance technique avancée ;
2. mettre à jour sans perte de données ;
3. restaurer une instance ;
4. migrer d'un PC vers un serveur ;
5. déployer la même application en cloud.

---

# Vision produit

GeoStudio devient une plateforme ouverte combinant :

- builder SIG ;
- dashboards ;
- data analytics ;
- catalogue ;
- IA et agents ;
- déploiement automatisé.
