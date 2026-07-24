### Task 4 : documentation — prérequis, template cloud-init, guide de bout en bout

**Files:**
- Create: `deploy/proxmox/README.md`

**Interfaces:**
- Consumes: rien (document terminal).
- Produces: rien consommé par du code — référence humaine pour exécuter réellement Task 2/3 sur le vrai Proxmox.

- [ ] **Step 1: Écrire `deploy/proxmox/README.md`**

```markdown
# Provisioning automatisé Proxmox (SP-Deploy-e)

> Spec : `docs/superpowers/specs/2026-07-25-sp-deploy-e-provisioning-proxmox-design.md`.
> Automatise la création de la VM qui fait tourner GeoStudio en dogfood réel
> (SP-Deploy-a/b/c) sur un hyperviseur Proxmox VE déjà installé. Trois étapes
> séquentielles : template cloud-init (une fois, manuel) → OpenTofu (VM) →
> Ansible (configuration + lancement de `scripts/install.sh`).

## 0. Prérequis, une fois par Proxmox

### Jeton API Proxmox

Interface web Proxmox → Datacenter → Permissions → API Tokens → créer un
jeton (ex. `root@pam!geostudio`, décocher « Privilege Separation » pour un
usage solo simple, ou créer un rôle dédié si vous préférez restreindre).
Notez l'ID complet et le secret (affiché une seule fois) — ils vont dans
`terraform.tfvars` (jamais commité, cf. `.gitignore` du module).

### Template cloud-init Debian 12

Sur le Proxmox, en SSH :

```bash
cd /var/lib/vz/template/iso  # ou tout datastore avec le contenu "iso"
wget https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2

qm create 9000 --name debian-12-cloudinit-template --memory 2048 --cores 2 --net0 virtio,bridge=vmbr0
qm importdisk 9000 debian-12-genericcloud-amd64.qcow2 local-lvm
qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0
qm set 9000 --ide2 local-lvm:cloudinit
qm set 9000 --boot c --bootdisk scsi0
qm set 9000 --serial0 socket --vga serial0
qm template 9000
```

VMID `9000` est la convention attendue par défaut par `variables.tf`
(`template_vmid`). Adaptez `local-lvm` au nom réel de votre datastore si
différent.

**Vérification du sudo passwordless** (le déploiement en dépend, cf. §2) :
Proxmox accorde par défaut un accès `sudo` sans mot de passe à l'utilisateur
créé via son cloud-init natif (`ciuser`, exposé par le bloc `initialization`
d'OpenTofu). Après la première création de VM (§1), vérifiez :

```bash
ssh -i ~/.ssh/geostudio_proxmox geostudio@<ip> 'sudo -n true && echo OK'
```

Si ce n'est **pas** le cas sur votre version de Proxmox/image cloud, ajoutez
manuellement, une fois, dans la VM :
```bash
echo 'geostudio ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/geostudio
```

### Outils sur votre poste (pas sur le Proxmox, pas dans ce dépôt)

Installez OpenTofu (https://opentofu.org/docs/intro/install/) et Ansible
(`pipx install ansible-core` ou le paquet de votre distribution) sur la
machine depuis laquelle vous lancez le déploiement — généralement votre poste
de travail, pas le Proxmox lui-même.

## 1. Créer la VM (OpenTofu)

```bash
cd deploy/proxmox/terraform
cp terraform.tfvars.example terraform.tfvars
# éditez terraform.tfvars : pm_api_url, pm_api_token_id, pm_api_token_secret,
# target_node, ip_address, gateway, ssh_public_key (contenu de votre clé
# publique SSH, ex. cat ~/.ssh/geostudio_proxmox.pub)
tofu init
tofu apply
```

Notez l'`output vm_ip` — reportez-le dans `inventory.ini` (§2).

## 2. Configurer et lancer GeoStudio (Ansible)

```bash
cd ../ansible
cp inventory.ini.example inventory.ini
# éditez inventory.ini : ansible_host = vm_ip de l'étape 1

cp group_vars/vault.yml.example group_vars/vault.yml
ansible-vault encrypt group_vars/vault.yml
# éditez les valeurs AVANT de chiffrer, ou : ansible-vault edit group_vars/vault.yml
# — vault_ts_authkey (https://login.tailscale.com/admin/settings/keys)
# — vault_geostudio_admin_email
# — vault_backup_s3_* (optionnel — laissez vide pour aucune sauvegarde hors-site)

# éditez éventuellement group_vars/all.yml : geostudio_public_host (vide =
# découverte auto *.ts.net), geostudio_profiles (ex. "observability"),
# geostudio_seed_demo

ansible-playbook -i inventory.ini --ask-vault-pass playbook.yml
```

À la fin, le résumé imprimé par `scripts/install.sh` (URL publique, compte
admin) s'affiche dans la sortie Ansible (tâche « Afficher le résumé »).

## 3. Vérifications réelles (critères §8 de la spec)

Une fois la stack en ligne :
1. `curl -I https://<GEOSTUDIO_PUBLIC_HOST>/` → répond en HTTPS.
2. `ssh geostudio@<vm_ip> 'cd geostudio && docker compose -f docker-compose.yml -f docker-compose.prod.yml restart'` → tous les services remontent (`worker` ne boucle pas — bloqueur corrigé en SP-Deploy-a).
3. Connexion réelle sur l'URL publique avec le compte admin, écriture d'une donnée, relecture.
4. `tofu destroy` puis `tofu apply` + re-run Ansible → cycle rejouable de bout en bout sans intervention manuelle au-delà de ce README.

Ces vérifications se font sur le vrai Proxmox du mainteneur — aucun outil
de ce dépôt ne peut les exécuter à votre place (pas d'accès réseau à votre
Proxmox depuis un environnement de développement générique).
```

- [ ] **Step 2: Vérifier les références de chemins**

```bash
test -f deploy/proxmox/terraform/terraform.tfvars.example && \
test -f deploy/proxmox/ansible/inventory.ini.example && \
test -f deploy/proxmox/ansible/group_vars/vault.yml.example && \
test -f deploy/proxmox/ansible/group_vars/all.yml && \
test -f deploy/proxmox/ansible/playbook.yml && \
echo "OK — tous les fichiers référencés par le README existent"
```
Expected: `OK — tous les fichiers référencés par le README existent`.

- [ ] **Step 3: Commit**

```bash
git add deploy/proxmox/README.md
git commit -m "docs(deploy): guide provisioning Proxmox — prérequis, template cloud-init, bout en bout (SP-Deploy-e)"
```

---

