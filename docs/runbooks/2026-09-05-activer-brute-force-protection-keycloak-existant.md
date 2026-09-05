# Runbook — activer Brute Force Detection sur un Keycloak déjà déployé

Note opérationnelle courte, pas un runbook complet. Concerne uniquement une
instance **déjà en production** dont Keycloak a été démarré une première
fois avant que `deploy/keycloak/geostudio-realm.json` n'active
`bruteForceProtected` (SP-42, revue globale F-infra-ci-02).

## Pourquoi c'est nécessaire

`docker-compose.yml`/`docker-compose.prod.yml` lancent Keycloak avec
`kc.sh start --import-realm`. Cette commande **n'importe le realm que s'il
est absent** — ce n'est pas une synchronisation à chaque démarrage. Le
realm d'une instance déjà initialisée vit dans le volume Docker persistant
`keycloak-data` ; mettre à jour l'image/le dépôt et relancer
`docker compose up -d` ne touche pas ce realm déjà importé.

Conséquence concrète : une instance mise à jour vers une version qui
active `bruteForceProtected` dans le realm exporté du dépôt **reste sans
protection anti-bourrage d'identifiants** tant que personne n'intervient
manuellement — l'écart n'est visible par aucun test automatisé de ce dépôt
(`core/tests/test_deployability.py::test_keycloak_realm_enables_brute_force_protection`
lit le JSON source, pas un realm Keycloak réel en train de tourner — piège
n°2 de `CLAUDE.md`, « livré + testé ≠ câblé »).

## Procédure

Choisir l'une des deux options, selon ce qui est acceptable pour
l'instance :

### Option 1 — console d'administration Keycloak (recommandée, aucun redémarrage)

1. Se connecter à la console d'administration Keycloak de l'instance.
2. Sélectionner le realm `geostudio`.
3. *Realm settings* → onglet *Security defenses* → sous-onglet
   *Brute force detection*.
4. Activer *Enabled*.
5. Reproduire, si on veut retrouver exactement le réglage par défaut de ce
   dépôt (plutôt qu'une politique plus ou moins agressive) :
   - Max login failures : `30`
   - Wait time increment : `60` secondes
   - Max wait time : `900` secondes
   - Quick login check in ms : `1000`
   - Minimum quick login wait : `60` secondes
   - Max delta time : `12` heures (`43200` secondes)
   - Lockout permanent (*Permanent lockout*) : **désactivé** — un
     verrouillage permanent (nécessitant une intervention admin pour
     débloquer un compte) est une décision produit distincte, non prise
     par ce correctif.
6. Enregistrer.

### Option 2 — réimporter le realm

Dans le conteneur `keycloak` en cours d'exécution (ou en montant le
fichier à jour) :

```bash
docker compose exec keycloak /opt/keycloak/bin/kc.sh import \
  --file /opt/keycloak/data/import/geostudio-realm.json \
  --override true
```

Attention : `--override true` réécrit la configuration du realm depuis le
fichier — tout réglage fait à la main dans la console depuis le premier
import (clients OIDC ajoutés manuellement, utilisateurs Keycloak locaux,
etc.) est perdu. À ne faire qu'après vérification qu'aucun réglage manuel
distinct du fichier source n'existe, ou après en avoir fait l'inventaire.

## Vérifier après coup

Console d'administration → realm `geostudio` → *Realm settings* →
*Security defenses* → *Brute force detection* → *Enabled* doit être coché.
