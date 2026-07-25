# SP-Deploy — Stratégies de déploiement : planifiée, facilitée, idéale

> Spec issue du brainstorm du 2026-07-23. Trois paliers : (1) un déploiement
> dogfood réel sur machine perso via tunnel, avec sauvegardes et restauration
> testée ; (2) un installeur guidé universel + une étude comparée des modalités
> grand public ; (3) les cibles long terme (app-stores, PaaS, appliances,
> managé). Le plan d'implémentation ne **construit** que les paliers 1 et 2
> (installeur) ; le reste est **étudié/documenté** pour trancher plus tard.

## 1. Contexte & motivation

GeoStudio dispose déjà de la brique de release (`.github/workflows/release.yml`
pousse les images `core`/`shell`/`postgis` vers `ghcr.io/tlenenao/geostudio-*`
sur tag `vX.Y.Z`, validé par un dry-run rc1 en SP-9), d'un ingress Traefik
câblé (SP-9 « sécurité minimale » : `Host()`, HSTS, rate-limit, dashboard
fermé), d'un bootstrap de secrets (`scripts/bootstrap-env.sh`) et d'un mode
démo lecture seule (`CORE_READ_ONLY_MODE`, SP-9). **Mais aucune cible de
déploiement réelle n'a jamais été décidée ni documentée** : le seul document
existant (`docs/archive/stacks-production.md`) est périmé (parle encore de
GeoNode, retiré au jalon M1). La question produit Q2 (« premiers utilisateurs
réels ») reste ouverte dans le comparatif.

Ce chantier tranche : **de vrais premiers utilisateurs vont écrire de la
donnée** (objectif dogfooding), sur la **machine personnelle** du mainteneur,
exposée à un **cercle de confiance** via un **tunnel sortant**. Priorité n°1
absolue : **ne rien perdre** (sauvegardes + restauration réellement testée).

### Décisions cadrées par le brainstorm

| # | Décision |
|---|---|
| D1 | Objectif : vrais utilisateurs **écrivant** de la donnée (durabilité critique). |
| D2 | Public initial : **soi / cercle de confiance** (dogfooding), pas d'inscription ouverte. |
| D3 | Substrat : **machine personnelle** auto-hébergée. |
| D4 | Accès : **tunnel sortant** (aucun port ouvert, IP maison cachée). |
| D5 | Nom d'hôte : démarrer sur `*.ts.net` (tunnel), **migrer vers domaine propre** ensuite → doit être une **source de vérité unique**. |
| D6 | Calendrier : **après clôture de SP-12**, en **chantier dédié** (« SP-Deploy »). |
| D7 | Grand public : **installeur guidé construit** ; toutes les autres modalités **étudiées/comparées**, non construites. |

## 2. Structure en trois paliers

| Palier | Contenu | Statut d'exécution |
|---|---|---|
| **1. Planifiée** | Déploiement dogfood réel : stack prod + tunnel + sauvegardes + restauration testée. | **Construit & exécuté** (jour J, après SP-12). |
| **2. Facilitée** | **Installeur guidé universel** + **étude comparée** des modalités grand public. | Installeur **construit** ; comparaison **documentée**. |
| **3. Idéale** | Cibles long terme (YunoHost, PaaS 1-clic, appliances, managé). | **Étudié/comparé** seulement (matrice de décision). |

Le plan d'implémentation ne construit que : *déploiement dogfood* +
*installeur guidé* + *correction des 2 bloqueurs connus*.

## 3. Palier 1 — Architecture du déploiement dogfood

### 3.1 Principe cardinal : nom d'hôte public = source de vérité unique

Une variable **`GEOSTUDIO_PUBLIC_HOST`** (dans `.env`) irrigue **tous** les
points qui dépendent de l'URL publique :

- l'`issuer` et les `redirect_uri` du realm Keycloak ;
- la configuration OIDC du cœur (audience, issuer attendu) ;
- la base d'API du shell ;
- la configuration du service tunnel ;
- les règles de routage Traefik (`Host(...)`).

Conséquence : passer de `machine.tailnet.ts.net` à `geostudio.tondomaine.fr`
= **éditer une ligne** de `.env` + redémarrer, **jamais** reconstruire une
image ni éditer plusieurs fichiers. C'est un critère d'acceptation testé (§7,
critère 4).

### 3.2 Stack prod : `docker-compose.prod.yml` en surcouche

Un fichier d'**override** appliqué par-dessus le `docker-compose.yml` existant
(`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`).
Différences avec le compose de dev :

- **Images depuis GHCR** (`ghcr.io/tlenenao/geostudio-{core,shell,postgis}:vX.Y.Z`)
  au lieu de `build:`, pour `core`/`shell`/`worker`/`cdc-worker`/`postgis`.
  Le tag est piloté par une variable (ex. `GEOSTUDIO_VERSION`).
- **Service `tunnel`** (`cloudflared` ou `tailscale`, cf. §3.3) exposant l'URL
  publique HTTPS sans port ouvert. Traefik reste **routeur interne** + en-têtes
  de sécurité, **sans ACME/Let's Encrypt** (le TLS est terminé au bord du
  tunnel).
- **Service `backup`** (cf. §4).
- Retrait des commodités de dev (montages de code source, ports de debug).
- `restart: unless-stopped` sur tous les services d'état.
- Observabilité (`--profile observability`) **optionnelle**, éteinte par défaut
  sur la machine perso.

### 3.3 Choix du connecteur de tunnel

Le déploiement démarre en `*.ts.net` (D5). Deux implémentations possibles,
tranchées à l'exécution (les deux satisfont « aucun port ouvert, IP cachée ») :

- **`tailscale funnel`** : URL publique `*.ts.net` gratuite, **sans domaine ni
  compte tiers**, la plus directe pour le point de départ D5-A.
- **`cloudflared` (Cloudflare Tunnel)** : nécessite un domaine sur Cloudflare
  (palier D5-B), meilleur quand la migration vers domaine propre est faite.

Le design **n'impose pas** l'un ou l'autre : la config du tunnel est un service
compose isolé, paramétré par `GEOSTUDIO_PUBLIC_HOST`. Le plan choisira
`tailscale funnel` pour le démarrage (aligné D5-A), en gardant `cloudflared`
documenté comme le chemin de migration.

### 3.4 Correction des 2 bloqueurs connus (dans le périmètre)

Documentés dans CLAUDE.md, ils empêchent un démarrage réel propre :

1. **`worker` en boucle de redémarrage** (SP-10b, suivi hors-périmètre) :
   le service `worker` (`schema --apply && worker`) redémarre en boucle après
   le premier succès, car `schema --apply` n'est **pas idempotent** une fois
   les types procrastinate créés. Correction : rendre l'application du schéma
   procrastinate **idempotente** ou la **séparer** du lancement du worker
   (étape one-shot au boot vs boucle de travail), pour que la stack survive à
   tout redémarrage. Test de non-régression dédié.
2. **Volume `pg-data` par défaut cassé** (SP-11a, suivi) : `alembic_version`
   jamais estampillé sur certains chemins → migrations en échec sur un volume
   pré-existant. Le service `core` enchaîne déjà `alembic upgrade head` depuis
   SP-9-install ; vérifier et garantir un premier boot **propre sur volume
   vierge** (§7 critère 1) et le rattrapage d'un volume non estampillé.

Ces deux fixes touchent du code applicatif/compose et ont leurs **propres
tests** ; le reste du chantier ne touche pas le code applicatif.

## 4. Palier 1 — Durabilité (cœur du scénario)

Trois volumes portent tout l'état : `pg-data` (Postgres : configs, items,
collections, données métier OGC Features), `minio-data` (objets S3, GeoParquet
CDC), `keycloak-data` (comptes, realm OIDC).

### 4.1 Service `backup`

Conteneur avec cron interne effectuant, selon une planification (ex. quotidien) :

- **Postgres** : `pg_dump` compressé (dump logique, portable entre versions
  mineures).
- **MinIO** : `mc mirror` du/des buckets vers la cible hors-site.
- **Keycloak** : export du realm (comptes + config OIDC). **Indispensable** :
  sans lui, une restauration perd tous les utilisateurs.
- **Chiffrement au repos** avant envoi (restic natif, ou `age`/`gpg`) — l'hôte
  hors-site ne doit jamais lire en clair.
- **Cible hors-site** : stockage objet bon marché **hors de la machine**
  (Cloudflare R2 free ≤10 Go par défaut ; Backblaze B2 / Scaleway en
  alternative). Un backup sur le même disque ne protège ni de l'incendie ni du
  vol ni de la panne disque.
- **Rétention** : rotation simple (ex. 7 quotidiens + 4 hebdomadaires).

La cible et la planification sont paramétrées par `.env` (variables dédiées,
optionnelles — un déploiement sans cible hors-site configurée émet un
avertissement clair plutôt que d'échouer en silence).

### 4.2 Restauration testée — livrable, pas intention

Un backup jamais restauré est présumé mort. Le plan inclut une **procédure de
restauration réellement exécutée** (§7 critère 5) : sur une machine/volumes
**vierges**, restaurer les 3 stores (Postgres, MinIO, realm Keycloak),
redémarrer la stack, **se reconnecter** et **relire une donnée écrite avant le
backup**. Documentée pas-à-pas dans le repo (runbook), pour être rejouable par
le mainteneur en situation réelle de perte.

## 5. Palier 2 — Installeur guidé universel (construit)

Un script unique **interactif et idempotent** (`scripts/install.sh`, ou cible
`make deploy`), surcouche de `bootstrap-env.sh`. **Orchestrateur de profils**,
pas liste figée : il reflète les capacités réellement présentes dans le repo
au moment où il tourne.

### 5.1 Détection & installation des prérequis

- Détecte `docker` + `docker compose`. Si absent : propose l'installation
  **avec consentement explicite**, jamais en silence, jamais d'élévation de
  privilège furtive.
  - **Linux** : détection de distro (apt/dnf/pacman) → script officiel
    `get.docker.com` après confirmation ; ajoute l'utilisateur au groupe
    `docker`.
  - **macOS/Windows** : pas d'auto-install propre possible (Docker Desktop) →
    **détecte et guide** (lien + instructions), puis reprend une fois installé.
- Vérifie de même le binaire du tunnel choisi (`tailscale`/`cloudflared`) et
  propose son installation selon le même protocole de consentement.

### 5.2 Menu d'options (profils compose)

Le script propose d'activer/désactiver des **profils** :

- **Observabilité** (`--profile observability` : Grafana/Loki/Tempo/Prometheus
  + postgres-exporter) — **existe déjà**.
- **ETL no-code** — **piste future (SP-15, non encore construit)** : l'entrée
  figure au menu mais **marquée « à venir » / désactivée** tant que le profil
  n'existe pas dans le repo, plutôt que de mentir à l'utilisateur.
- **Seed de démo** optionnel (lecture seule) pour un premier tour.

Le menu est **extensible** : une capacité future livrée = une ligne de plus,
sans réécrire l'installeur. Le script découvre les profils disponibles plutôt
que de les coder en dur là où c'est raisonnable.

### 5.3 Bootstrap & lancement

1. Demande **2-3 réponses** : nom d'hôte public (ou « génère-moi un `*.ts.net` »),
   identité admin (email / `sub` OIDC), cible de backup (optionnelle).
2. Génère `.env` (secrets forts, mécanisme `bootstrap-env.sh` existant) **et
   propage `GEOSTUDIO_PUBLIC_HOST`** dans le realm Keycloak et la config.
3. Lance le tunnel + `docker compose -f docker-compose.yml -f
   docker-compose.prod.yml --profile <choisis> up -d`.
4. Attend la santé des services, applique les migrations, **imprime l'URL
   publique + les prochaines étapes** (créer l'admin, seed démo optionnel).

Objectif : **`git clone` → `./install.sh` → répondre à 3 questions → URL en
main**, pour le mainteneur comme pour un tiers. **Idempotent** (re-run sans
casse). Faible dette de maintenance.

## 6. Paliers 2/3 — Étude comparée des modalités grand public (étudiées)

Le spec fournit une **matrice de décision** notée, argumentée, avec une
**séquence d'adoption** recommandée. Aucune de ces modalités n'est construite
dans le plan — ce sont les paliers « possibles/idéaux ».

| Modalité | Public | Dette solo | Alignement projet | Verdict pressenti |
|---|---|---|---|---|
| **Installeur guidé** (§5) | Tous auto-hébergeurs | Faible | ★★★ | **Construit maintenant** |
| **YunoHost** | Non-technique, FR/souverain | Moyenne (format de packaging propre) | ★★★ | Piste **prioritaire** post-déploiement |
| **Coolify / Dokploy / CapRover** | Hobbyiste self-host | Faible (template compose réutilisé) | ★★ | Piste **facile** (quasi gratuite) |
| **CasaOS / Umbrel** | Home-server clé en main | Moyenne (2 app-stores distincts) | ★★ | Possible, à la demande |
| **Bouton « Deploy to » (Railway/Render/Fly)** | Développeurs | Moyenne (par plateforme) | ★ (s'éloigne du self-host souverain) | Différé |
| **Offre managée / SaaS** | Non-hébergeurs | **Élevée** (ops continue) | — (modèle d'affaires) | Hors périmètre solo |

### Critères de notation (argumentés dans le doc final)

- **Public visé** : à qui s'adresse la modalité.
- **Dette de maintenance solo** : coût récurrent pour un seul mainteneur
  (format de packaging à suivre, releases à répercuter, cassures upstream).
- **Alignement souveraineté** : cohérence avec la fibre Apache-2.0 / RGPD /
  self-host du projet.
- **Effort de packaging initial** et **portée d'adoption**.

### Séquence d'adoption recommandée

1. **Installeur guidé** (construit ici) — socle universel.
2. **Template Coolify/Dokploy** — quasi gratuit (réutilise le compose), premier
   levier hobbyiste.
3. **YunoHost** — si traction dans l'écosystème FR/souverain (public
   non-technique, fort alignement).
4. **CasaOS/Umbrel, boutons cloud** — à la demande, si un besoin réel émerge.
5. **Managé/SaaS** — hors périmètre d'un mainteneur solo (modèle d'affaires,
   ops continue), mentionné pour complétude.

## 7. Validation & critères d'acceptation

Chaque critère est **exécuté réellement**, pas asséré :

1. **Démarrage à froid** : sur un volume `pg-data` **vierge**, `./install.sh` →
   stack saine, migrations appliquées (`GET /me` anonyme = 401, pas 500), URL
   publique répondant en HTTPS.
2. **Survie au redémarrage** : `docker compose restart` (et reboot machine) →
   tous les services remontent, **`worker` ne boucle pas** (bloqueur 1
   corrigé).
3. **OIDC bout-en-bout** : connexion réelle via Keycloak sur le nom d'hôte
   public, écriture d'une donnée, relecture.
4. **Bascule d'hôte** : changer `GEOSTUDIO_PUBLIC_HOST` (`*.ts.net` → domaine)
   + redémarrer → OIDC re-fonctionne **sans reconstruction** (preuve du
   principe source-unique, §3.1).
5. **Cycle sauvegarde → restauration** : écrire une donnée → backup → **détruire
   les volumes** → restaurer → **relire la donnée** + reconnexion utilisateur.
   Critère central du scénario B (§4.2).
6. **Installeur idempotent** : re-run sans casse ; menu de profils
   (observabilité on/off) effectif ; détection Docker correcte (présent /
   absent).
7. **Non-régression** : suites cœur/shell/E2E existantes restent vertes (le
   déploiement ne touche pas le code applicatif, sauf les 2 fixes de bloqueurs
   qui ont leurs propres tests).

## 8. Calendrier & découpage

- **Déclenchement** : **après clôture de SP-12** (fédération finie, `main`
  synchronisé) — D6.
- **Forme** : chantier dédié **« SP-Deploy »** (à inscrire dans la feuille de
  route), exécuté en **subagent-driven-development** comme le reste du projet.
- **Sous-phases probables** (découpage fin dans le plan) :
  1. **Stack prod** : `docker-compose.prod.yml`, images GHCR, service tunnel,
     hostname source-unique + **correction des 2 bloqueurs**.
  2. **Durabilité** : service `backup` + **restauration testée** sur volumes
     vierges (runbook).
  3. **Installeur guidé** : détection/install des prérequis, menu de profils,
     bootstrap/lancement idempotents.
  4. **Étude grand public** : matrice comparée + séquence d'adoption + mise à
     jour feuille de route / README.

## 9. Hors périmètre (explicite)

- Inscription publique ouverte, multi-tenant à l'échelle, quotas/abus,
  modération (relèvent de D2, non retenu).
- Construction effective de YunoHost / Coolify / CasaOS / boutons cloud /
  managé (étudiés en §6, non construits).
- Haute disponibilité, réplication multi-nœuds, PITR (pgBackRest / archivage
  WAL) — surdimensionné pour un cercle fermé sur une machine unique.
- SP-15 (ETL) : seule une entrée « à venir » désactivée dans le menu de
  l'installeur, aucun code ETL ici.
