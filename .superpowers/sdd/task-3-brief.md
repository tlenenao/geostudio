### Task 3 : playbook Ansible — configuration + lancement

**Files:**
- Create: `deploy/proxmox/ansible/inventory.ini.example`
- Create: `deploy/proxmox/ansible/group_vars/all.yml`
- Create: `deploy/proxmox/ansible/group_vars/vault.yml.example`
- Create: `deploy/proxmox/ansible/playbook.yml`

**Interfaces:**
- Consumes: le contrat de variables d'environnement défini en Task 1 (`INSTALL_YES`, `GEOSTUDIO_PUBLIC_HOST`, `TS_AUTHKEY`, `INSTALL_PROFILES`, `INSTALL_SEED_DEMO`, `INSTALL_ADMIN_EMAIL`, `BACKUP_S3_*`) ; l'IP/utilisateur produits par Task 2 (`vm_ip`/`vm_ssh_username`, reportés à la main dans `inventory.ini`).
- Produces: rien consommé par un autre fichier de ce plan — nœud terminal de la chaîne.

- [ ] **Step 1: `inventory.ini.example`**

```ini
[geostudio]
geostudio-vm ansible_host=192.168.1.50 ansible_user=geostudio ansible_ssh_private_key_file=~/.ssh/geostudio_proxmox
```

- [ ] **Step 2: `group_vars/all.yml`** (non-secret, committé tel quel)

```yaml
geostudio_repo_url: "https://github.com/tlenenao/geostudio.git"
geostudio_repo_dest: "/home/geostudio/geostudio"
geostudio_public_host: ""
geostudio_profiles: ""
geostudio_seed_demo: false
```

- [ ] **Step 3: `group_vars/vault.yml.example`** (template — le vrai `vault.yml` est chiffré par `ansible-vault` et gitignored, cf. Task 5)

```yaml
vault_ts_authkey: "tskey-auth-CHANGEME"
vault_geostudio_admin_email: "admin@example.com"
vault_backup_s3_endpoint: ""
vault_backup_s3_access_key: ""
vault_backup_s3_secret_key: ""
vault_backup_s3_bucket: "geostudio-backups"
```

- [ ] **Step 4: `playbook.yml`**

```yaml
---
- name: Provisionner GeoStudio sur la VM Proxmox
  hosts: geostudio
  vars_files:
    - group_vars/all.yml
    - group_vars/vault.yml

  tasks:
    - name: Attendre que SSH soit disponible (premier boot cloud-init)
      ansible.builtin.wait_for_connection:
        timeout: 300

    - name: Mettre à jour le cache apt
      become: true
      ansible.builtin.apt:
        update_cache: true
        cache_valid_time: 3600

    - name: Installer les prérequis système (git, curl)
      become: true
      ansible.builtin.apt:
        name:
          - git
          - curl
        state: present

    - name: Cloner ou mettre à jour le dépôt GeoStudio
      ansible.builtin.git:
        repo: "{{ geostudio_repo_url }}"
        dest: "{{ geostudio_repo_dest }}"
        version: main
        force: false

    - name: Lancer l'installeur GeoStudio (1ère passe — installe Docker si absent, peut s'arrêter là)
      ansible.builtin.command:
        cmd: ./scripts/install.sh
        chdir: "{{ geostudio_repo_dest }}"
      environment: &geostudio_install_env
        INSTALL_YES: "1"
        GEOSTUDIO_PUBLIC_HOST: "{{ geostudio_public_host }}"
        TS_AUTHKEY: "{{ vault_ts_authkey }}"
        INSTALL_PROFILES: "{{ geostudio_profiles }}"
        INSTALL_SEED_DEMO: "{{ '1' if geostudio_seed_demo else '0' }}"
        INSTALL_ADMIN_EMAIL: "{{ vault_geostudio_admin_email }}"
        BACKUP_S3_ENDPOINT: "{{ vault_backup_s3_endpoint }}"
        BACKUP_S3_ACCESS_KEY: "{{ vault_backup_s3_access_key }}"
        BACKUP_S3_SECRET_KEY: "{{ vault_backup_s3_secret_key }}"
        BACKUP_S3_BUCKET: "{{ vault_backup_s3_bucket }}"
      register: install_pass1
      changed_when: true

    # Si ensure_docker (scripts/install.sh) vient d'installer Docker, le
    # script s'arrête volontairement après (exit 0) : l'appartenance au
    # groupe docker du nouvel utilisateur ne prend effet qu'à la prochaine
    # session. reset_connection force Ansible à rouvrir une session SSH
    # neuve avant la 2e passe plutôt que de réutiliser la connexion
    # persistante existante, qui ignorerait ce changement.
    - name: Réinitialiser la connexion SSH (prise en compte du groupe docker)
      ansible.builtin.meta: reset_connection

    - name: Lancer l'installeur GeoStudio (2e passe — idempotente, termine le déploiement)
      ansible.builtin.command:
        cmd: ./scripts/install.sh
        chdir: "{{ geostudio_repo_dest }}"
      environment: *geostudio_install_env
      register: install_pass2
      changed_when: true

    - name: Afficher le résumé de l'installeur
      ansible.builtin.debug:
        var: install_pass2.stdout_lines
```

- [ ] **Step 5: Matérialiser temporairement les fichiers `.example` pour la vérification**

```bash
cp deploy/proxmox/ansible/inventory.ini.example deploy/proxmox/ansible/inventory.ini
cp deploy/proxmox/ansible/group_vars/vault.yml.example deploy/proxmox/ansible/group_vars/vault.yml
```

- [ ] **Step 6: Vérifier la syntaxe et lint (conteneur officiel, aucune installation système)**

Run:
```bash
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/proxmox/ansible:/workspace" -w /workspace \
  ghcr.io/ansible/community-ansible-dev-tools:latest \
  ansible-playbook -i inventory.ini --syntax-check playbook.yml
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/proxmox/ansible:/workspace" -w /workspace \
  ghcr.io/ansible/community-ansible-dev-tools:latest \
  ansible-lint playbook.yml
```
Expected : `--syntax-check` répond `playbook: playbook.yml` sans erreur (code `0`) ; `ansible-lint` ne remonte aucune erreur bloquante (des avertissements de style sont acceptables, à corriger seulement s'ils sont triviaux).

- [ ] **Step 7: Nettoyer les fichiers matérialisés (ne pas les laisser trackés — ils contiennent des valeurs d'exemple, pas les vraies)**

```bash
rm deploy/proxmox/ansible/inventory.ini deploy/proxmox/ansible/group_vars/vault.yml
```

- [ ] **Step 8: Commit**

```bash
git add deploy/proxmox/ansible/
git commit -m "feat(deploy): playbook Ansible — configuration + lancement non-interactif (SP-Deploy-e)"
```

---

