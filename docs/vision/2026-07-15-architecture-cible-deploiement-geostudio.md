# Architecture cible de déploiement GeoStudio

Date : 2026-07-15

## Vision

GeoStudio doit pouvoir fonctionner comme une plateforme géospatiale moderne déployable partout :

- poste développeur ;
- serveur local ;
- appliance collectivité ;
- cloud privé ;
- Kubernetes entreprise.

Principe : même application, même configuration logique, plusieurs profils d'exécution.

---

# 1. Architecture logique

```
Utilisateur
    |
    v
Reverse Proxy HTTPS
(Traefik/Nginx)
    |
    +----------------+
    |                |
    v                v
Shell React       API Core
TypeScript        FastAPI
    |                |
    +-------+--------+
            |
            v
       PostgreSQL
       PostGIS
            |
   +--------+---------+
   |                  |
 Martin             TiTiler
 MVT                Raster

Stockage objet
MinIO / S3

Identité
Keycloak / OIDC
```

---

# 2. Profils matériels

## Profil minimal

Cible : laptop, démonstration.

Configuration :

- 4 CPU
- 8 Go RAM
- 50 Go disque

Services :

- Shell
- Core
- PostgreSQL
- Martin

Sans :

- Keycloak
- MinIO
- monitoring

---

## Profil standard appliance

Cible : PC i5, 16 Go RAM, SSD 512 Go.

Configuration recommandée :

- 4 à 8 CPU
- 16 Go RAM
- SSD

Services :

- Shell
- Core
- PostgreSQL/PostGIS
- Martin
- TiTiler
- MinIO
- Keycloak

Capacité :

- dizaines d'utilisateurs
- plusieurs centaines d'applications
- données SIG locales

---

## Profil production

Cible : serveur entreprise.

Ajouts :

- réplication PostgreSQL
- stockage S3 externe
- monitoring
- logs centralisés
- SSO entreprise
- sauvegarde externalisée

---

# 3. Volumes persistants

Les données doivent être séparées du cycle applicatif.

```
/var/lib/geostudio

├── postgres/
├── minio/
├── keycloak/
├── uploads/
├── backups/
└── logs/
```

Un upgrade applicatif ne doit jamais supprimer les données.

---

# 4. Stratégie Docker

Chaque composant applicatif possède une image versionnée.

Exemple :

```
ghcr.io/geostudio/core:0.1.0
ghcr.io/geostudio/shell:0.1.0
```

Les versions sont immuables.

Rollback possible :

```
geostudio rollback 0.1.0
```

---

# 5. Gestion des migrations

Chaque version peut contenir :

```
migrations/

001_initial.sql
002_items.sql
003_sharing.sql
```

Déploiement :

```
backup DB
 |
 migration
 |
 démarrage services
 |
 health check
```

---

# 6. Multi-environnement

## Dev

```
mock auth
SQLite possible
hot reload
```

## Demo

```
Docker Compose
Keycloak démo
jeu de données exemple
```

## Production

```
OIDC
PostGIS complet
backup
monitoring
```

## Enterprise

```
Kubernetes
Helm
HA
```

---

# 7. Séparation Community / Enterprise

## Community

Licence open source :

- builder
- cartes
- dashboards
- API
- PostGIS
- plugins

## Enterprise

Extensions possibles :

- multi-tenant avancé
- SSO entreprise
- haute disponibilité
- audit avancé
- support
- connecteurs propriétaires

---

# 8. Déploiement Kubernetes

Architecture :

```
Namespace geostudio

Deployment
├── shell
├── core
├── martin
└── titiler

StatefulSet
├── postgresql
└── minio

Ingress
└── geostudio.example.com
```

Packaging :

```
charts/geostudio
```

---

# 9. Sécurité

Obligatoire :

- secrets hors Git
- HTTPS
- rotation clés
- OIDC
- RBAC
- sauvegardes chiffrées

---

# 10. Observabilité

Stack recommandée :

- OpenTelemetry
- Prometheus
- Grafana
- Loki

Métriques :

- temps réponse API
- erreurs
- charge DB
- génération tuiles
- utilisation stockage

---

# 11. Roadmap technique

## Étape 1

- Dockerfiles production
- compose profiles
- documentation installation

## Étape 2

- images GHCR
- CLI GeoStudio
- backup/restore

## Étape 3

- CI/CD complet
- monitoring
- upgrade automatique

## Étape 4

- Helm chart
- Kubernetes
- architecture enterprise

---

# Objectif final

GeoStudio doit devenir une plateforme géospatiale installable comme une appliance :

```bash
geostudio install
```

puis évolutive jusqu'à une architecture cloud-native.
