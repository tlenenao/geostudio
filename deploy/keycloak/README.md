# Realm Keycloak GeoStudio

`geostudio-realm.json` est le realm exporté que `docker compose` importe au
démarrage de Keycloak (`kc.sh start --import-realm`,
`docker-compose.yml`/`docker-compose.prod.yml`).

## `bruteForceProtected` ne se propage pas à une instance déjà déployée

`--import-realm` **n'importe le realm que s'il est absent** — c'est un
import, pas une synchronisation. Sur une instance déjà démarrée une
première fois, le realm vit dans le volume Docker persistant
`keycloak-data` (`docker-compose.yml`) : modifier `geostudio-realm.json`
dans le dépôt (par exemple activer `bruteForceProtected`, SP-42) et
redémarrer les conteneurs ne change **rien** au realm déjà importé. Seule
une installation neuve (volume `keycloak-data` pas encore créé) reçoit la
valeur à jour du fichier.

Sur une instance existante, activer la protection anti-bourrage
d'identifiants (Brute Force Detection) après coup demande une action
manuelle — l'une des deux :

1. **Console d'administration Keycloak** (le plus simple, aucun
   redémarrage) : realm `geostudio` → *Realm settings* → onglet
   *Security defenses* → sous-onglet *Brute force detection* → activer
   *Enabled*. Les seuils par défaut de ce dépôt
   (`failureFactor: 30`, `maxFailureWaitSeconds: 900`,
   `minimumQuickLoginWaitSeconds: 60`, `waitIncrementSeconds: 60`,
   `quickLoginCheckMilliSeconds: 1000`, `maxDeltaTimeSeconds: 43200`) sont
   les valeurs par défaut de Keycloak lui-même — les reproduire à la main
   si on veut retrouver exactement ce réglage plutôt qu'une politique plus
   ou moins agressive.
2. **Réimporter le realm** : `kc.sh import --file
   /opt/keycloak/data/import/geostudio-realm.json --override true` (ou
   supprimer/recréer le volume `keycloak-data` avant un premier démarrage,
   perte de tout réglage fait à la main entre-temps — clients OIDC ajoutés
   manuellement, utilisateurs Keycloak locaux, etc. — à ne faire qu'en toute
   connaissance de cause).

Cette classe d'écart (« livré + testé ≠ câblé sur une instance déjà en
production ») est documentée pour ce dépôt dans `CLAUDE.md`, piège n°2.

Voir aussi le runbook
[`docs/runbooks/2026-09-05-activer-brute-force-protection-keycloak-existant.md`](../../docs/runbooks/2026-09-05-activer-brute-force-protection-keycloak-existant.md).
