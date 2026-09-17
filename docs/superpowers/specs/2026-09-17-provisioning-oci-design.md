# Provisioning OCI (Oracle Cloud Infrastructure) + découplage ETL/QGIS — design

## 0. Cadrage

Déclencheur : le portage arm64 multi-arch (`docs/superpowers/specs/2026-09-15-portage-arm64-multiarch-design.md`)
a levé le préalable générique (images `postgis`/`titiler`/`shell`/`core`/… publiées
en `linux/amd64,linux/arm64`, porte CI `test-gate-arm64`) mais excluait
explicitement le provisioning Oracle lui-même : « un chantier séparé qui
consomme le résultat de celui-ci ». C'est ce chantier.

Seule l'offre « always free » Oracle Cloud avec assez de RAM pour la pile par
défaut (11 services) est **Ampere A1 Flex, arm64** (jusqu'à 4 OCPU/24 Go). Ce
document couvre :

1. Un module OpenTofu + Ansible pour provisionner une instance Ampere A1 et y
   lancer GeoStudio, calqué sur `deploy/proxmox/` (déjà en place, dogfoodé).
2. Un découplage, dans `scripts/install.sh`, entre la capacité générale de
   pipelines no-code (`CORE_ETL_ENABLED`) et le sidecar QGIS (`qgis-worker`,
   profil compose `etl`, mono-arch amd64) — pour pouvoir activer la première
   sans jamais démarrer le second, quelle que soit l'architecture de l'hôte.

Hors périmètre (assumé, cf. §6) : portage arm64 de `qgis-worker` lui-même,
retry automatique sur pénurie de capacité Ampere A1, abstraction Terraform
partagée entre providers, vérification réelle sur un tenancy Oracle (à faire
par l'opérateur, aucun outil de cet environnement n'y a accès).

## 1. Constat vérifié

- `deploy/proxmox/ansible/playbook.yml` ne contient **aucune** référence à
  Proxmox : SSH (`wait_for_connection`), prérequis apt (`git`, `curl`),
  `git clone`, deux passes de `scripts/install.sh` séparées par
  `meta: reset_connection` (le groupe `docker` créé par la 1ʳᵉ passe n'est
  actif qu'à la reconnexion SSH suivante — correctif déjà trouvé une fois en
  session). 100% réutilisable tel quel pour n'importe quelle VM Debian/Ubuntu
  joignable en SSH.
- `docker-compose.yml` : le profil compose `etl` (ligne ~566) ne démarre
  **que** `qgis-worker`. La capacité générale de pipelines (`CORE_ETL_ENABLED`,
  lignes ~284/458 — reader.connector.rest/postgres, moteur DuckDB, file
  procrastinate `etl`) est un env var totalement indépendant, lu par `core`
  et `worker`. `worker` reçoit `QGIS_WORKER_URL: http://qgis-worker:8000`
  inconditionnellement ; si `qgis-worker` n'est pas démarré, seule
  l'opération `transform.qgis` échoue proprement (connexion refusée) — le
  reste du moteur de pipelines fonctionne normalement. Ce découplage existe
  déjà dans le code ; il manque seulement un moyen de régler
  `CORE_ETL_ENABLED` depuis l'installeur (`scripts/install.sh` n'expose
  aujourd'hui aucun prompt pour cette variable, seulement pour le profil
  compose `etl`, ce qui la confond avec le sidecar QGIS dans l'UI d'install).
- `docker-compose.prod.yml` ne publie aucun port hôte et route tout le trafic
  applicatif par un tunnel Tailscale (service `tunnel`, TLS terminé au bord
  du tunnel, hostname `*.ts.net`) — déjà le modèle du module Proxmox
  existant, directement réutilisable pour OCI (pas de Traefik/ACME/DNS à
  gérer côté OCI).
- Aucun fichier OCI n'existe dans le dépôt à ce jour (`deploy/proxmox/` est
  le seul module de provisioning cloud/hyperviseur).

## 2. Restructuration Ansible (préalable)

Extraction de `deploy/proxmox/ansible/playbook.yml` vers
**`deploy/ansible/playbook.yml`**, partagé entre providers — aucune logique
spécifique à Proxmox ou OCI n'y vit, donc aucune duplication de contenu
(en particulier la paire `command install.sh` / `reset_connection`, dont un
bug futur ne devrait être corrigé qu'à un seul endroit).

- `deploy/proxmox/ansible/` garde `inventory.ini.example` +
  `group_vars/{all.yml,vault.yml.example}` (valeurs réellement spécifiques :
  IP statique, bridge, etc. — déjà dans `terraform/`, pas dans `ansible/`,
  donc rien à changer côté `group_vars` sauf le chemin du playbook).
- `deploy/proxmox/README.md` : commande mise à jour
  (`ansible-playbook -i inventory.ini --ask-vault-pass ../../ansible/playbook.yml`).
- Terraform **reste séparé par provider** : `proxmox_virtual_environment_vm`
  et `oci_core_instance`+VCN n'ont aucune ressource en commun ; une
  abstraction ici serait artificielle (cf. §6, et le postmortem
  `2026-09-08-app-builder-package-extraction-postmortem.md` sur l'extraction
  prématurée).

## 3. Module OpenTofu (`deploy/oci/terraform/`)

Même découpage de fichiers que `deploy/proxmox/terraform/`
(`main.tf`/`variables.tf`/`outputs.tf`/`versions.tf`/`terraform.tfvars.example`).

- **Provider** : `oracle/oci`, authentification par clé API utilisateur
  (`tenancy_ocid`, `user_ocid`, `fingerprint`, `private_key_path`, `region`)
  — modèle standard pour un compte personnel, pas de principal d'instance
  (aucune instance existante pour bootstrapper).
- **Réseau créé par ce module** (contrairement à Proxmox, qui suppose un
  bridge/datastore déjà là) : VCN dédiée, subnet public, Internet Gateway,
  route table (route par défaut via l'IGW), **security list** attachée au
  subnet :
  - ingress TCP/22 depuis `var.admin_ssh_cidr` (variable **obligatoire**,
    pas de défaut ouvert à `0.0.0.0/0` — cohérent avec la discipline
    sécurité du dépôt, ex. `admin_auth`/rate-limit/CSP sur les autres
    surfaces d'admin) ;
  - egress tout (mises à jour apt, pull d'images GHCR, Tailscale) ;
  - aucun autre port ouvert : 80/443 applicatifs passent exclusivement par
    le tunnel Tailscale, comme documenté dans `docker-compose.prod.yml`.
- **Instance** : shape `VM.Standard.A1.Flex`, `ocpus`/`memory_in_gbs`
  variables (défaut 4/24 — plafond « always free »). Image résolue via
  `data "oci_core_images"` (dernière image Canonical Ubuntu 22.04 arm64
  compatible avec le shape, filtrée par `operating_system`/
  `operating_system_version`/`shape`, triée par `time_created` décroissant)
  — pas d'OCID en dur (varie par région). Utilisateur par défaut `ubuntu`
  (sudo NOPASSWD déjà présent sur l'image officielle Canonical — contrairement
  au template Proxmox, pas de vérification manuelle nécessaire) ; clé SSH
  publique injectée via les métadonnées d'instance (`ssh_authorized_keys`).
- **Stockage** : boot volume dédié, taille variable (défaut 100 Go — dans
  l'enveloppe gratuite totale de 200 Go boot+block volumes).
- **Sorties** (`outputs.tf`) : IP publique de l'instance, user SSH — à
  reporter dans `deploy/oci/ansible/inventory.ini` (même patron que
  `vm_ip`/`vm_ssh_username` côté Proxmox).

## 4. Ansible (`deploy/oci/ansible/`)

- `inventory.ini.example` : `ansible_host=<IP sortie de Tofu>`,
  `ansible_user=ubuntu`, `ansible_ssh_private_key_file=~/.ssh/geostudio_oci`.
- `group_vars/all.yml` :
  - `geostudio_profiles: ""` **en dur, jamais `etl`** — pas une détection
    d'architecture, une décision de déploiement : ce chantier ne fait jamais
    tourner `qgis-worker` sur cette cible (image mono-arch amd64).
  - nouvelle variable `geostudio_core_etl_enabled: true` — active le moteur
    de pipelines (indépendant du sidecar QGIS, cf. §2) via le nouveau toggle
    d'installeur (§5).
- `group_vars/vault.yml.example` : identique au modèle Proxmox
  (`vault_ts_authkey`, `vault_geostudio_admin_email`, `vault_backup_s3_*`).
- Référence le playbook commun : `ansible-playbook -i inventory.ini
  --ask-vault-pass ../../ansible/playbook.yml`.
- `playbook.yml` (commun, §2) gagne une ligne dans le bloc `environment:`
  partagé entre les deux passes d'installation :
  `INSTALL_CORE_ETL_ENABLED: "{{ '1' if geostudio_core_etl_enabled else '0' }}"`
  — absente par défaut pour Proxmox (`group_vars/all.yml` n'y définit pas
  cette variable ; Ansible Jinja sur une variable absente échoue, donc
  `deploy/proxmox/ansible/group_vars/all.yml` gagne aussi
  `geostudio_core_etl_enabled: false` pour ne pas casser le provisioning
  existant).

## 5. `scripts/install.sh` — toggle `CORE_ETL_ENABLED` découplé de QGIS

Nouvelle fonction `prompt_etl_engine` (même patron que `prompt_backup_target`,
appelée juste après `prompt_profiles`) :

```
Activer le moteur de pipelines no-code (CORE_ETL_ENABLED — reader.connector,
DuckDB ; indépendant du sidecar QGIS ci-dessus) ? [y/N]
```

- Interactif : `confirm` classique.
- Non-interactif : `INSTALL_CORE_ETL_ENABLED=1|0` (même convention que
  `INSTALL_SEED_DEMO`) → `set_env_var CORE_ETL_ENABLED true|false`.
- Si non renseigné en mode non-interactif (`INSTALL_YES=1` sans
  `INSTALL_CORE_ETL_ENABLED`), défaut `false` — pas de changement de
  comportement pour les installs existantes qui ne connaissent pas cette
  variable.

`profile_label("etl")` reformulé pour ne plus dire « ETL no-code (SP-17) »
(qui laissait croire que ce profil couvre tout le moteur de pipelines) mais
nommer explicitement ce qu'il démarre réellement :

```
etl) echo "Sidecar QGIS (transform.qgis, isolé, image mono-arch amd64)" ;;
```

Sans ce changement, les deux prompts (« ETL no-code » pour le profil compose,
puis un nouveau « CORE_ETL_ENABLED ») porteraient le même nom pour deux
capacités différentes — exactement la confusion que ce chantier existe pour
éliminer.

## 6. `deploy/oci/README.md`

Même structure que `deploy/proxmox/README.md` :

0. Prérequis : clé API OCI (Console → Identité → Utilisateurs → Clés API),
   OCID tenancy/user/compartment, OpenTofu + Ansible sur le poste opérateur.
1. `tofu init && tofu apply` (module §3) → noter `vm_ip`.
2. Reporter dans `inventory.ini` (§4), `ansible-vault encrypt group_vars/vault.yml`,
   `ansible-playbook -i inventory.ini --ask-vault-pass ../../ansible/playbook.yml`.
3. Vérifications réelles (même check-list que Proxmox §3 : HTTPS répond,
   `docker compose restart` ne boucle pas, connexion admin réelle
   écriture/relecture, cycle `tofu destroy` + `tofu apply` rejouable).
4. **Note capacité** : Ampere A1 Flex sur le tier gratuit connaît des
   pénuries de capacité fréquentes selon la région (`Out of host capacity`
   sur `tofu apply`) — documenté comme un aléa à réessayer manuellement,
   **pas** de boucle de retry automatisée dans ce chantier (cf. §0).

## 7. Hors périmètre (assumé)

- Portage arm64 de `qgis-worker` (chantier séparé, déjà noté dans le suivi
  CLAUDE.md — base QGIS elle-même mono-arch).
- Script de retry automatique sur pénurie de capacité Ampere A1.
- Abstraction Terraform partagée entre Proxmox et OCI (§2 : aucune ressource
  commune entre les deux providers).
- Vérification finale sur un vrai tenancy OCI : à faire par l'opérateur,
  aucun outil de cet environnement n'y a accès (même limitation que
  Proxmox §3 de son README).
- Support d'une autre distribution que Ubuntu arm64 (Oracle Linux
  nécessiterait de forker le playbook Ansible, `apt` → `dnf`).
