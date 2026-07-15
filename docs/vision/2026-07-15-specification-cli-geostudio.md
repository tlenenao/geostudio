# Spécification CLI GeoStudio

Date : 2026-07-15

## Objectif

Créer un outil en ligne de commande permettant d'installer, administrer et maintenir une instance GeoStudio quel que soit son environnement : poste local, serveur, appliance ou infrastructure entreprise.

Principe :

```bash
geostudio <commande>
```

L'utilisateur ne doit pas avoir besoin de manipuler directement Docker Compose, Kubernetes ou les fichiers de configuration.

---

# 1. Architecture du CLI

Technologie recommandée : Python.

Stack :

- Typer ou Click pour les commandes
- Pydantic pour la configuration
- Rich pour l'interface terminal
- Docker SDK Python
- Ansible API optionnel

Structure :

```
geostudio-cli/

├── commands/
│   ├── install.py
│   ├── upgrade.py
│   ├── backup.py
│   └── doctor.py
│
├── config/
├── templates/
├── docker/
└── main.py
```

---

# 2. Commandes principales

## Installation

```bash
geostudio install
```

Actions :

1. Vérification système
2. Détection CPU/RAM/disque
3. Choix profil
4. Génération secrets
5. Création configuration
6. Déploiement services
7. Migration base
8. Création compte admin

---

# 3. Détection automatique matériel

Commande :

```bash
geostudio detect
```

Retour :

```
CPU: 6 cores
RAM: 16 GB
Disk: 450 GB

Recommended profile:
appliance
```

Profils :

## Laptop

- moins de 8 Go RAM
- services réduits

## Appliance

- 8-32 Go RAM
- installation complète

## Enterprise

- plus de 32 Go RAM
- Kubernetes possible

---

# 4. Profils d'installation

## Minimal

```bash
geostudio install --profile minimal
```

Services :

- shell
- core
- postgres
- martin


## Standard

```bash
geostudio install --profile standard
```

Ajoute :

- Keycloak
- MinIO
- TiTiler


## Enterprise

```bash
geostudio install --profile enterprise
```

Prépare :

- Kubernetes
- Helm
- SSO

---

# 5. Gestion configuration

Commande :

```bash
geostudio config
```

Fonctions :

- afficher configuration
- modifier paramètres
- valider variables

Exemple :

```bash
geostudio config set domain geo.example.com
```

---

# 6. Cycle de vie

## Démarrage

```bash
geostudio start
```

## Arrêt

```bash
geostudio stop
```

## Statut

```bash
geostudio status
```

Retour :

```
API        OK
Database   OK
Tiles      OK
Storage    OK
Auth       OK
```

---

# 7. Upgrade

Commande :

```bash
geostudio upgrade
```

Processus :

```
backup
 |
 téléchargement nouvelle version
 |
 migration DB
 |
 redémarrage services
 |
 health checks
```

Rollback :

```bash
geostudio rollback 0.2.0
```

---

# 8. Sauvegarde

Commande :

```bash
geostudio backup
```

Sauvegarde :

- PostgreSQL
- fichiers utilisateurs
- configuration
- Keycloak
- MinIO

Restauration :

```bash
geostudio restore backup.tar.gz
```

---

# 9. Diagnostic

Commande :

```bash
geostudio doctor
```

Contrôles :

- Docker installé
- ports disponibles
- espace disque
- mémoire
- connexions DB
- certificats
- migrations
- santé services

Exemple :

```
✓ Docker
✓ PostgreSQL
✓ Storage
✗ Certificate expired
```

---

# 10. Gestion multi-instance

Permettre plusieurs instances :

```
/opt/geostudio/

├── demo/
├── prod/
└── test/
```

Commandes :

```bash
geostudio instance create demo
geostudio instance list
geostudio instance remove demo
```

---

# 11. Intégration CI/CD

Le CLI doit pouvoir être utilisé par :

- GitHub Actions
- Ansible
- scripts d'exploitation

Mode non interactif :

```bash
geostudio install \
 --profile production \
 --config prod.yaml \
 --yes
```

---

# 12. Roadmap

## Version 0.1

- install
- start
- stop
- status

## Version 0.2

- upgrade
- backup
- doctor

## Version 0.3

- multi-instance
- plugins
- marketplace

## Version 1.0

- appliance complète
- Kubernetes
- gestion entreprise

---

# Vision finale

Le CLI devient la porte d'entrée officielle de GeoStudio :

```bash
geostudio install
```

doit suffire pour transformer une machine vierge en plateforme SIG/DataViz/IA opérationnelle.
