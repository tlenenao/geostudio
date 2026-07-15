# Plan d'implémentation — Déploiement et industrialisation GeoStudio

Date : 2026-07-15

## Objectif

Transformer GeoStudio d'une stack de développement Docker Compose en une plateforme déployable facilement sur plusieurs environnements : poste local, serveur autonome, démonstrateur, collectivité et infrastructure entreprise.

Le principe directeur : **"One command install, reproducible anywhere"**.

---

# 1. Cibles de déploiement

## Profil Local / Développeur

Objectif : développement et tests.

Environnement :
- Docker Desktop ou Docker Engine
- docker compose
- volumes locaux
- authentification mock possible

Commande cible :

```bash
git clone geostudio
docker compose up -d
```

---

## Profil Appliance

Cible : PC serveur i5/16 Go RAM, mini serveur, VM.

Objectif : installation autonome.

Composants :

- GeoStudio Shell
- GeoStudio Core
- PostgreSQL/PostGIS
- Martin
- TiTiler
- MinIO optionnel
- Keycloak

Commande cible :

```bash
curl -fsSL https://install.geostudio.io | bash
```

---

## Profil Production

Cible : organisation, collectivité, entreprise.

Composants supplémentaires :

- reverse proxy HTTPS
- sauvegardes automatisées
- monitoring
- logs centralisés
- certificats
- SSO entreprise

---

## Profil Kubernetes

Objectif : cloud et grandes infrastructures.

Déploiement :

```bash
helm install geostudio ./charts/geostudio
```

---

# 2. Nouvelle organisation deploy/

Créer une couche d'installation indépendante du code applicatif.

```
deploy/
├── compose/
│   ├── minimal.yml
│   ├── demo.yml
│   └── production.yml
│
├── env/
│   ├── dev.env
│   ├── demo.env
│   └── prod.env
│
├── scripts/
│   ├── install.sh
│   ├── upgrade.sh
│   ├── backup.sh
│   └── doctor.sh
│
├── ansible/
│
└── helm/
```

---

# 3. Containerisation complète

## Images officielles

Créer :

- geostudio-shell
- geostudio-core
- geostudio-worker éventuel

Publication :

```
ghcr.io/geostudio/shell:v0.1
ghcr.io/geostudio/core:v0.1
```

Chaque release doit produire :

- images Docker versionnées
- changelog
- migration DB associée

---

# 4. Gestion configuration

Mettre toute la configuration dans des variables d'environnement.

Exemples :

```
DATABASE_URL
AUTH_PROVIDER
KEYCLOAK_URL
STORAGE_BACKEND
TILE_SERVER_URL
```

Créer des profils :

- minimal
- standard
- enterprise

---

# 5. CLI GeoStudio

Créer un outil de gestion :

```bash
geostudio install
geostudio start
geostudio stop
geostudio upgrade
geostudio backup
geostudio doctor
```

Fonctions :

- validation prérequis
- génération secrets
- création volumes
- migrations
- diagnostic
- restauration

---

# 6. CI/CD GitHub Actions

Pipeline cible :

```
commit
 |
 v
Tests frontend/backend
 |
 v
Build Docker
 |
 v
Scan sécurité
 |
 v
Publication GHCR
 |
 v
Déploiement staging
 |
 v
Validation
 |
 v
Production
```

Workflows :

```
.github/workflows/
├── test.yml
├── build.yml
├── release.yml
└── deploy.yml
```

---

# 7. Infrastructure as Code

## Serveur simple

Docker Compose + scripts.

## Infrastructure avancée

Ansible :

- installation OS
- Docker
- firewall
- certificats
- déploiement GeoStudio

Terraform :

- VM
- réseau
- stockage

---

# 8. Monitoring et exploitation

Ajouter progressivement :

- OpenTelemetry
- Prometheus
- Grafana
- Loki

Créer un pack de supervision :

- santé API
- état DB
- nombre utilisateurs
- erreurs frontend
- performances tuiles

---

# 9. Sauvegarde et maintenance

Automatiser :

- dump PostgreSQL
- sauvegarde MinIO
- export Keycloak
- restauration testée

Commandes :

```bash
geostudio backup
geostudio restore backup.tar.gz
```

---

# 10. Roadmap d'implémentation

## Phase 1 — Fondations (M6)

- Dockerfiles officiels
- compose minimal/demo/prod
- documentation installation
- GitHub Actions build

## Phase 2 — Appliance (M6-M7)

- installateur automatique
- CLI GeoStudio
- doctor command
- backup automatique

## Phase 3 — Production (M7)

- monitoring
- logs
- SSO
- upgrade sans interruption

## Phase 4 — Enterprise (M8+)

- Helm chart
- Kubernetes
- multi-instance
- haute disponibilité

---

# Critère de réussite

Un utilisateur doit pouvoir passer de zéro à une instance GeoStudio fonctionnelle avec :

```bash
geostudio install
```

sur un PC local, un serveur Linux ou un cluster Kubernetes sans modifier le code applicatif.
