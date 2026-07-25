# SP-Deploy-e — Provisioning automatisé Proxmox : design

> Issu du brainstorm du 2026-07-25. S'inscrit dans la famille **SP-Deploy**
> (spec-mère `docs/superpowers/specs/2026-07-23-sp-deploy-strategies-design.md`) :
> SP-Deploy-a (stack prod), SP-Deploy-b (durabilité) et SP-Deploy-c (installeur
> guidé) livrent déjà le dogfood réel sur machine perso (D3) via
> `scripts/install.sh`. Ce chantier répond à un fait nouveau : **la machine
> personnelle du mainteneur est un hyperviseur Proxmox VE**, pas un hôte
> Docker nu — il faut automatiser le provisioning de la VM qui fera tourner
> GeoStudio, en amont de l'installeur déjà construit.

## 1. Contexte & motivation

SP-Deploy-c a livré `scripts/install.sh` : un installeur guidé interactif qui
suppose un hôte Docker déjà prêt. Il ne dit rien de **comment cet hôte est
créé**. Sur la machine réelle du mainteneur (Proxmox VE, déjà installé,
accessible en web/SSH mais sans jeton API configuré), cette étape est
aujourd'hui manuelle : créer une VM à la main dans l'interface Proxmox, puis
lancer l'installeur dedans.

Ce chantier automatise cette étape manquante, **sans toucher** à ce que
SP-Deploy-a/b/c ont déjà construit (le compose prod, les backups, l'essentiel
d'`install.sh`) — seule une extension ciblée d'`install.sh` (§4) est dans le
périmètre.

### Décisions cadrées par le brainstorm

| # | Décision |
|---|---|
| E1 | Cible : la machine personnelle réelle (D3 de la spec-mère) est un hyperviseur **Proxmox VE**, déjà installé, accès web/SSH, pas encore de jeton API. |
| E2 | Invité GeoStudio : une **VM** (pas un LXC) — isolation forte, snapshots/migration Proxmox natifs. |
| E3 | Outillage : **OpenTofu** pour l'infra (création de la VM), **Ansible** pour la configuration (Docker, dépôt, lancement de l'installeur). Split classique infra/config, pas un outil unique. |
| E4 | OpenTofu plutôt que Terraform : fork 100 % open-source (MPL-2.0), cohérent avec la fibre Apache-2.0/souveraineté du projet (`CLAUDE.md`). |
| E5 | Ansible invoque `scripts/install.sh` avec les réponses **pré-remplies** (mode non-interactif) plutôt que de s'arrêter avant et laisser la main — une seule chaîne bout-en-bout. |
| E6 | Distribution de la VM : **Debian 12** (image cloud générique). |
| E7 | Réseau : **IP statique** sur le bridge Proxmox — stabilité pour l'accès SSH répété d'Ansible et le tunnel Tailscale. |
| E8 | Aucun template cloud-init n'existe encore sur ce Proxmox : sa création fait partie du périmètre (procédure documentée, geste manuel unique, hors code versionné). |
| E9 | Premier playbook Ansible du projet — aucun existant à réutiliser ou avec lequel s'intégrer. |

## 2. Architecture d'ensemble

Trois couches séquentielles, chacune testable et rejouable isolément :

```
OpenTofu (infra)          Ansible (config)              install.sh (existant, SP-Deploy-c)
─────────────────         ─────────────────             ──────────────────────────────────
Clone template             Attend SSH prêt                Reçoit les réponses en variables
cloud-init Debian 12   →   Installe git/curl          →   d'environnement (pas de saisie
+ IP statique + clé SSH    Clone/pull le dépôt              interactive) → lance la stack,
sur le Proxmox existant    Invoque install.sh               imprime l'URL publique
                            avec les variables
```

Ce découpage est délibéré : un échec Ansible se relance sans recréer la VM ;
un échec d'`install.sh` se relance directement en SSH sans repasser par
Ansible. Chaque couche est idempotente indépendamment des deux autres.

## 3. Couche OpenTofu (infra Proxmox)

**Provider :** `bpg/proxmox` (le plus complet pour clone de template +
cloud-init, activement maintenu — préféré à `telmate/proxmox`, plus ancien et
moins bien maintenu).

**Template cloud-init (prérequis manuel, une fois, hors code versionné — E8) :**
Procédure documentée dans `deploy/proxmox/README.md` : télécharger l'image
cloud officielle `debian-12-genericcloud-amd64.qcow2`, puis sur le Proxmox
`qm create` + `qm importdisk` + `qm template`, avec un VMID conventionnel
(ex. `9000`). C'est un état du serveur Proxmox, pas du dépôt : créer un
template est un geste d'admin ponctuel, cloner un template existant est le
rôle d'OpenTofu (idempotence : OpenTofu ne recrée jamais le template
lui-même).

**Module OpenTofu (`deploy/proxmox/terraform/`) :**
- Ressource `proxmox_virtual_environment_vm` : clone du template `9000` ;
  CPU/RAM/disque paramétrés par variables (`.tfvars`, valeurs par défaut
  dogfood : 4 vCPU / 8 Go RAM / 40 Go disque, ajustables) ; IP statique +
  passerelle + clé SSH publique injectées via le bloc `initialization`
  (cloud-init).
- **Credentials Proxmox** : jeton API (`PM_API_TOKEN_ID` /
  `PM_API_TOKEN_SECRET`), créé une fois via Datacenter → Permissions → API
  Tokens sur le Proxmox. Jamais commité — variables d'environnement ou
  `terraform.tfvars` **gitignored**.
- **State** : local (`terraform.tfstate`, gitignored) — un seul mainteneur,
  une seule machine, pas de backend distant. Choix explicite, pas un oubli.
- **Output** : l'IP statique de la VM, exposée en `output` pour qu'Ansible
  n'ait pas à la relire dans les `.tfvars`.

## 4. Couche Ansible (config + lancement)

**Structure (`deploy/proxmox/ansible/`) :**
- `inventory.ini` — un seul host statique (l'IP fixée en §3), pas d'inventaire
  dynamique nécessaire pour une VM unique.
- `playbook.yml`, trois étapes séquentielles :
  1. **Attente SSH** (`wait_for_connection`) — le premier boot cloud-init
     prend quelques dizaines de secondes.
  2. **Prérequis système minimaux** : `apt update`, `git`, `curl`. Docker et
     `jq` sont **laissés à `scripts/install.sh::ensure_docker/ensure_jq`**
     (déjà idempotents, déjà écrits en SP-Deploy-c) — pas de duplication de
     cette logique côté Ansible.
  3. **Déploiement** : clone (ou `git pull` si déjà présent — idempotent) du
     dépôt GeoStudio dans `/opt/geostudio`, puis exécution de
     `scripts/install.sh` avec les variables d'environnement injectées
     (module `ansible.builtin.command`/`shell`, bloc `environment:`).

**Variables d'entrée** (`group_vars/all.yml` ou `--extra-vars`, secrets via
**Ansible Vault** — cf. §5) :
`geostudio_public_host` (optionnel, vide = découverte auto Tailscale, déjà le
comportement d'`install.sh`), `geostudio_admin_email`, `ts_authkey`,
`geostudio_profiles` (liste), `geostudio_seed_demo` (bool), `backup_s3_*`
(optionnels).

Un run réussi doit être **rejouable sans casse** : Ansible ne doit ni
écraser des modifications locales sur `/opt/geostudio` (pull, pas de reset
forcé) ni ré-exécuter des étapes système déjà faites.

## 5. Extension d'`install.sh` — mode non-interactif

Généralisation du mécanisme déjà existant pour `TS_AUTHKEY`
(`prompt_public_host` saute déjà son `read` si `TS_AUTHKEY` est exporté) à
**tous** les prompts qui capturent une valeur : **si la variable
d'environnement correspondante est déjà exportée, sauter le `read` et
l'utiliser directement ; sinon, comportement interactif inchangé** (aucune
régression pour l'usage manuel SP-Deploy-c).

| Prompt actuel | Variable d'environnement à ajouter |
|---|---|
| `PUBLIC_HOST_INPUT` | `GEOSTUDIO_PUBLIC_HOST` (étendre le `if` déjà là pour `TS_AUTHKEY` au même test) |
| `TS_AUTHKEY` | déjà géré, aucun changement |
| profils activés (boucle `confirm` par profil) | `INSTALL_PROFILES` (liste séparée par virgules ; si définie, remplace la boucle de confirmation par un filtrage direct) |
| seed démo | `INSTALL_SEED_DEMO` (`0`/`1`) |
| `s3_endpoint` / `access` / `secret` / `bucket` | `BACKUP_S3_ENDPOINT` / `BACKUP_S3_ACCESS_KEY` / `BACKUP_S3_SECRET_KEY` / `BACKUP_S3_BUCKET` |
| `ADMIN_EMAIL` | `INSTALL_ADMIN_EMAIL` |

Note technique : `confirm()` gère déjà `INSTALL_YES=1` pour les questions
oui/non, mais c'est un mécanisme distinct des `read -r -p` qui capturent une
*valeur* — les deux doivent être unifiés selon le même patron que
`TS_AUTHKEY` (`VAR="${ENV_OVERRIDE:-$(lecture interactive)}"`).

Risque explicitement accepté : ceci modifie le script SP-Deploy-c déjà
livré. Validé par les mêmes moyens que l'existant — exécution réelle, pas de
nouvelle suite Playwright/pytest (patron déjà utilisé pour SP-Deploy-a/b/c).

## 6. Secrets & credentials

Trois familles, à ne jamais mélanger dans le même mécanisme :

| Secret | Où il vit | Comment il y arrive |
|---|---|---|
| Jeton API Proxmox (OpenTofu) | `terraform.tfvars` gitignored ou `TF_VAR_*` | Créé une fois à la main sur le Proxmox |
| Clé SSH privée (Ansible → VM) | Trousseau local du mainteneur, jamais dans le dépôt | Clé publique injectée par cloud-init (OpenTofu) ; clé privée déjà existante côté opérateur |
| Secrets applicatifs (`TS_AUTHKEY`, email admin, S3 backup...) | Ansible Vault (fichier chiffré, commitable) | Déchiffrés au run (`--ask-vault-pass` ou fichier de mot de passe local gitignored), injectés en variables d'environnement pour `install.sh` |

Ansible Vault est le seul des trois commitable (chiffré) — state Terraform et
clé SSH restent strictement locaux à la machine du mainteneur, même logique
que `.env` produit par `bootstrap-env.sh`.

## 7. Emplacement dans le dépôt & nommage

- Nouveau répertoire `deploy/proxmox/` (`terraform/`, `ansible/`,
  `README.md`) à la racine, à côté de `scripts/` — pas dans `core/` ni
  `shell/`, aucune frontière de module concernée (infra pure).
- Ce chantier est **SP-Deploy-e — provisioning Proxmox**, dans la même
  famille que SP-Deploy-a/b/c/d, avec son propre plan d'implémentation
  suivant le même patron (TDD là où c'est pertinent — §5 —, vérification par
  exécution réelle ailleurs — §3/§4).

## 8. Validation & critères d'acceptation

Exécutée réellement sur le Proxmox du mainteneur, pas assérée :

1. `tofu apply` → VM créée, IP statique jointe en SSH.
2. `ansible-playbook` → Docker installé, dépôt cloné,
   `scripts/install.sh` exécuté **sans aucune saisie manuelle** → stack up,
   URL Tailscale répondant en HTTPS (mêmes critères que spec-mère §7-1 à
   §7-3, rejoués ici bout-en-bout depuis Proxmox).
3. **Idempotence des trois couches** : re-run `tofu apply` (aucun changement,
   ou changement attendu seulement) ; re-run Ansible (pas de casse) ; re-run
   `install.sh` (déjà garanti par SP-Deploy-c).
4. **Destruction propre** : `tofu destroy` supprime la VM sans résidu sur le
   Proxmox, pour retester tout le cycle à froid.

## 9. Hors périmètre (explicite)

- Automatiser la **création du template cloud-init** lui-même (procédure
  documentée, geste manuel unique — E8).
- Haute disponibilité, cluster Proxmox, migration live — une seule VM, un
  seul nœud, cohérent avec D3 de la spec-mère (machine personnelle).
- Tout ce qui est déjà hors périmètre de la spec-mère SP-Deploy (§9) :
  inscription publique, YunoHost/Coolify/CasaOS/boutons cloud/managé, code
  ETL SP-15.
- Modifier le comportement interactif **par défaut** d'`install.sh` — seule
  une extension rétrocompatible (§5), jamais un changement de comportement
  quand aucune variable d'environnement n'est fournie.
- LXC (E2 tranche pour la VM ; un chantier LXC serait une piste distincte, non
  retenue ici).
