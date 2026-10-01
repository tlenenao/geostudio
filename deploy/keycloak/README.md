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

## Enregistrement dynamique de clients (DCR) : surface d'onboarding MCP

`POST /realms/geostudio/clients-registrations/openid-connect` est ouvert
**volontairement** : c'est ce qui permet à un client MCP (Claude, un client
OAuth 2.1 + PKCE) de s'enregistrer seul. Un client ainsi créé reçoit
l'audience `geostudio-mcp` (jeton accepté par `/mcp`, refusé par l'API REST).

Il est cadré par la politique **Trusted Hosts** (anonyme) du realm :
`client-uris-must-match=true`, les `redirect_uris` demandées doivent pointer
un hôte de la liste (`localhost`, `127.0.0.1`, `claude.ai`) — vérifié contre
Keycloak 24.0.5 : `localhost` et `claude.ai` donnent 201, un hôte tiers 403.
S'ajoutent *Max Clients* (200) et *Consent Required*. Pour autoriser un autre
client MCP : *Realm settings → Client registration → Client registration
policies → Anonymous access policies → Trusted Hosts* (ou modifier
`geostudio-realm.json`). Comme pour tout réglage du realm, ce fichier ne
s'applique qu'à une installation neuve (cf. section précédente) : sur une
instance existante, ajouter la politique à la main dans la console.
