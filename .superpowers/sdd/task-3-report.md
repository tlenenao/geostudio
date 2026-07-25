# Task 3 report — playbook Ansible : configuration + lancement (SP-Deploy-e)

## Ce qui a été implémenté

Création de `deploy/proxmox/ansible/` avec les 4 fichiers spécifiés dans le brief, transcrits verbatim :

- `inventory.ini.example` — inventaire d'exemple (host `geostudio-vm`, IP `192.168.1.50`,
  utilisateur `geostudio`, clé SSH `~/.ssh/geostudio_proxmox`).
- `group_vars/all.yml` — variables non-secrètes (URL/dest du dépôt, host public, profils,
  seed demo), committées telles quelles.
- `group_vars/vault.yml.example` — template des 6 variables secrètes
  (`vault_ts_authkey`, `vault_geostudio_admin_email`, `vault_backup_s3_*`) ; le vrai
  `vault.yml` sera chiffré par `ansible-vault` et gitignored (Task 5, hors périmètre ici).
- `playbook.yml` — playbook à un seul play (`hosts: geostudio`) :
  1. `wait_for_connection` (timeout 300s, tolère le premier boot cloud-init) ;
  2. mise à jour du cache apt + installation de `git`/`curl` (`become: true`) ;
  3. clone/mise à jour idempotente du dépôt (`ansible.builtin.git`, branche `main`) ;
  4. 1ère passe de `./scripts/install.sh` avec le bloc `environment` (ancre YAML
     `&geostudio_install_env`) portant les 10 variables du contrat Task 1 ;
  5. `meta: reset_connection` (commentaire expliquant pourquoi : le groupe `docker`
     du nouvel utilisateur ne prend effet qu'à la session SSH suivante) ;
  6. 2e passe de `./scripts/install.sh` réutilisant le même bloc `environment` via
     l'alias YAML (`*geostudio_install_env`) — idempotente ;
  7. `debug: var=install_pass2.stdout_lines` pour afficher le résumé de l'installeur.

Les 10 variables d'environnement présentes dans `environment:` (vérifiées une à une,
aucun ajout ni omission) : `INSTALL_YES`, `GEOSTUDIO_PUBLIC_HOST`, `TS_AUTHKEY`,
`INSTALL_PROFILES`, `INSTALL_SEED_DEMO`, `INSTALL_ADMIN_EMAIL`, `BACKUP_S3_ENDPOINT`,
`BACKUP_S3_ACCESS_KEY`, `BACKUP_S3_SECRET_KEY`, `BACKUP_S3_BUCKET`.

## Ce qui a été testé et résultats

Validation statique uniquement (aucune cible Proxmox/Ansible réelle joignable depuis cet
environnement), via le conteneur officiel `ghcr.io/ansible/community-ansible-dev-tools:latest`
(jamais installé sur l'hôte ; `docker pull` effectué avec succès au préalable).

Matérialisation temporaire (étape 5 du brief) :
```
cp deploy/proxmox/ansible/inventory.ini.example deploy/proxmox/ansible/inventory.ini
cp deploy/proxmox/ansible/group_vars/vault.yml.example deploy/proxmox/ansible/group_vars/vault.yml
```

**1. `ansible-playbook --syntax-check`**
```
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/proxmox/ansible:/workspace" -w /workspace \
  ghcr.io/ansible/community-ansible-dev-tools:latest \
  ansible-playbook -i inventory.ini --syntax-check playbook.yml
```
Sortie :
```
playbook: playbook.yml
```
Exit code : `0`. Conforme à l'attendu du brief.

**2. `ansible-lint`**
```
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/proxmox/ansible:/workspace" -w /workspace \
  ghcr.io/ansible/community-ansible-dev-tools:latest \
  ansible-lint playbook.yml
```
Sortie :
```
WARNING  Project directory /.ansible cannot be used for caching as it is not writable.
WARNING  Using unique temporary directory /tmp/.ansible-0aaa for caching.
/usr/local/lib/python3.14/site-packages/ansible_compat/runtime.py:242: UserWarning: Project directory /.ansible cannot be used for caching as it is not writable.
  self.cache_dir = get_cache_dir(self.project_dir, isolated=self.isolated)
/usr/local/lib/python3.14/site-packages/ansible_compat/runtime.py:242: UserWarning: Using unique temporary directory /tmp/.ansible-0aaa for caching.
  self.cache_dir = get_cache_dir(self.project_dir, isolated=self.isolated)

Passed: 0 failure(s), 0 warning(s) in 1 files processed of 1 encountered. Last profile that met the validation criteria was 'production'.
```
Exit code : `0`. **Zéro erreur, zéro avertissement de lint** (les seuls messages sont des
`WARNING` liés au cache Ansible non-inscriptible dans le conteneur en mode `--user`, sans
rapport avec le contenu du playbook) — aucune correction nécessaire.

Nettoyage (étape 7 du brief) effectué :
```
rm deploy/proxmox/ansible/inventory.ini deploy/proxmox/ansible/group_vars/vault.yml
```
Confirmé absents du répertoire de travail après suppression et non trackés par git
(vérifié via `git status` avant le commit : seuls les 4 fichiers du brief apparaissaient
en untracked, `inventory.ini`/`vault.yml` matérialisés n'apparaissaient déjà plus).

## Fichiers modifiés

- `deploy/proxmox/ansible/inventory.ini.example` (nouveau)
- `deploy/proxmox/ansible/group_vars/all.yml` (nouveau)
- `deploy/proxmox/ansible/group_vars/vault.yml.example` (nouveau)
- `deploy/proxmox/ansible/playbook.yml` (nouveau)

Commit : `41e501f` — `feat(deploy): playbook Ansible — configuration + lancement
non-interactif (SP-Deploy-e)` (4 fichiers, 84 insertions, aucune suppression).

## Revue personnelle (self-review)

- Les 4 fichiers correspondent au contenu du brief au caractère près : vérifié par
  `diff` direct entre le bloc YAML du brief (lignes 44-114) et `playbook.yml` produit
  — diff vide (exit 0).
- Les 10 noms de variables d'environnement du contrat Task 1 sont présents exactement
  une fois chacun dans le bloc `environment:` (ancre `&geostudio_install_env`, réutilisé
  par alias `*geostudio_install_env` dans la 2e passe) — aucun typo, aucun ajout,
  aucune omission, vérifiés un par un via `grep`.
- `inventory.ini` et `group_vars/vault.yml` (copies matérialisées) ne sont ni présents
  sur le disque après nettoyage, ni stagés, ni commités — confirmé par `git status`
  avant le commit et par le `git show --stat HEAD` après (4 fichiers exactement,
  correspondant à la liste du brief).
- Validation effectuée contre un vrai daemon Docker (Docker Desktop 29.4.3), image
  officielle tirée avec succès (`docker pull` avant exécution), jamais d'installation
  système d'Ansible sur l'hôte.
- Aucune déviation par rapport au contenu verbatim du brief n'a été nécessaire : le
  syntax-check et le lint sont passés du premier coup sans aucune erreur à corriger.

## Note sur ce fichier

Ce fichier contenait auparavant le rapport d'une "Task 3" différente d'une session
antérieure (bootstrap Q&A SP-Deploy-c). Il a été remplacé intégralement par le rapport
de la Task 3 du plan SP-Deploy-e (playbook Ansible) conformément au brief courant.

## Problèmes ou préoccupations

Aucun. La tâche s'est déroulée sans imprévu : Docker était disponible, l'image officielle
a été tirée sans problème réseau, et les deux validations statiques sont passées sans
aucune erreur ni avertissement de contenu dès la première exécution.
