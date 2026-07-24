### Task 1 : squelette + détection/installation des prérequis Docker

**Files:**
- Create: `scripts/install.sh`

**Interfaces:**
- Consumes: `scripts/bootstrap-env.sh` (existant, inchangé) ; `docker-compose.prod.yml` (SP-Deploy-a/b, existant).
- Produces: fonctions bash `confirm()`, `ensure_docker()` — réutilisées par toutes les tâches suivantes du même fichier.

**Contexte vérifié :** `docker compose version` (sous-commande, pas `docker-compose` legacy) est la façon correcte de tester la présence du plugin Compose v2 — vérifié sur cet environnement (`Docker Compose version v5.1.3`). `get.docker.com` est le script d'installation officiel documenté par Docker, auto-détecte apt/dnf/pacman/zypper en interne.

- [ ] **Step 1: Squelette + helpers**

Créer `scripts/install.sh` :

```bash
#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

# Confirmation interactive — jamais d'action destructive/installante sans
# accord explicite (spec SP-Deploy §5.1). INSTALL_YES=1 permet un mode
# non-interactif pour les Steps de vérification de ce plan (jamais utilisé
# pour un vrai déploiement humain).
confirm() {
  if [ "${INSTALL_YES:-0}" = "1" ]; then
    echo "$1 [y/N] → y (INSTALL_YES=1)"
    return 0
  fi
  read -r -p "$1 [y/N] " reply
  case "$reply" in
    [yY]|[yY][eE][sS]) return 0 ;;
    *) return 1 ;;
  esac
}

echo "═══ GeoStudio — installeur guidé ═══"
```

- [ ] **Step 2: Détection/installation de Docker**

Ajouter à `scripts/install.sh` :

```bash
ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "✓ Docker + Docker Compose détectés ($(docker compose version --short))."
    return 0
  fi

  echo "✗ Docker (avec le plugin Compose v2) est requis et n'a pas été détecté."
  case "$(uname -s)" in
    Linux)
      if confirm "Installer Docker maintenant via le script officiel get.docker.com ?"; then
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$USER"
        echo "Docker installé. Déconnectez-vous/reconnectez-vous (ou lancez 'newgrp docker')"
        echo "pour que l'appartenance au groupe docker prenne effet, puis relancez ce script."
        exit 0
      fi
      echo "Installation annulée — relancez ce script une fois Docker installé manuellement."
      exit 1
      ;;
    Darwin)
      echo "macOS : installez Docker Desktop manuellement : https://www.docker.com/products/docker-desktop/"
      echo "Relancez ce script une fois Docker Desktop démarré."
      exit 1
      ;;
    *)
      echo "OS non reconnu automatiquement : installez Docker manuellement"
      echo "(https://docs.docker.com/get-docker/), puis relancez ce script."
      exit 1
      ;;
  esac
}

ensure_docker
```

- [ ] **Step 3: Vérifier réellement (cas nominal — Docker déjà présent)**

Dans un clone jetable, jamais dans le dépôt de travail :

```bash
rm -rf /tmp/geostudio-install-test && git clone . /tmp/geostudio-install-test
chmod +x /tmp/geostudio-install-test/scripts/install.sh
cd /tmp/geostudio-install-test && ./scripts/install.sh
```

Expected : `✓ Docker + Docker Compose détectés (...)` (l'environnement d'exécution de ce plan a déjà Docker), puis le script se termine normalement (rien après `ensure_docker` pour l'instant — Task 2 continue).

```bash
cd /home/lenen/projets/geostudio && rm -rf /tmp/geostudio-install-test
```

- [ ] **Step 4: Commit**

```bash
git add scripts/install.sh
git commit -m "feat(deploy): installeur guidé — squelette + détection Docker"
```

---

