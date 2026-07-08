# GeoStudio SP-1d — Bascule et démolition

> Design / spec. Quatrième et dernière sous-phase de SP-1. Le shell bascule sur
> le cœur pour tout ce qui était servi par GeoNode ; GeoNode, Superset et Redis
> sortent du compose (jalon M1). C'est la sous-phase qui rend SP-1a/b/c
> observables : rien n'était visible avant celle-ci.
>
> Date : 2026-07-05.
> Statut : design proposé.
> Prérequis : SP-1a/b/c livrés (auth, items, partage/publication tous
> fonctionnels côté cœur, testés en isolation).

---

## 1. Contexte et périmètre

Aujourd'hui `itemClient.ts` parle à **deux services** : GeoNode
(`VITE_GEONODE_URL`, items/groupes/partage/vignettes) et le cœur
(`VITE_BUILDER_URL`, configs). SP-1d fait du cœur l'unique interlocuteur :
`VITE_CORE_URL` remplace les deux variables.

**Contenu.**
- `CoreItemClient` dans le shell — même interface `ItemClient`, mêmes types TS
  (arbitrage A11 : types générés depuis l'OpenAPI du cœur, `CoreItemClient`
  écrit à la main par-dessus, câblé dès SP-1a).
- Variables d'environnement : `VITE_CORE_URL` remplace `VITE_GEONODE_URL` (et
  fusionne l'usage de `VITE_BUILDER_URL`, qui disparaît).
- Migration des données selon A15 : repartir propre, re-seed de démo — pas de
  script de migration GeoNode → cœur (aucun déploiement de prod identifié).
- Retrait de GeoNode, Superset, Redis du compose.
- Realm Keycloak exporté et provisionné au démarrage (fin du `start-dev` nu) —
  premier branchement réel du mode `oidc` (le mode `mock` seul suffisait
  jusqu'ici, y compris pour tous les e2e).
- Mise à jour README/docs.

**Hors périmètre.** Toute nouvelle fonctionnalité produit — cette sous-phase
est un remplacement à comportement observable identique, garanti par les 13
specs e2e existantes. Pas de gestion multi-royaume Keycloak (un seul realm
`geostudio`, cohérent avec le tenant unique de SP-1a).

## 2. Décisions de cadrage

| Sujet | Décision |
|---|---|
| Bascule | **Coupure nette, pas de double-implémentation.** `CoreItemClient` remplace l'implémentation GeoNode dans le même commit/PR qui retire GeoNode du compose — pas de flag `VITE_ITEM_BACKEND=geonode\|core` à maintenir en parallèle. Cohérent avec la philosophie du dépôt (pas de compat shim pour une bascule à sens unique). |
| Filet de sécurité | Les 13 specs e2e Playwright, inchangées dans leur intention (elles testent des comportements produit, pas une implémentation), doivent rester vertes. C'est le critère de bascule réussie, pas une relecture manuelle exhaustive. |
| Types TS | Générés par `openapi-typescript` depuis `core-schema.d.ts` (pipeline posé dès SP-1a). `CoreItemClient` mappe ces types générés vers l'interface `ItemClient` existante — la façade `ItemClient` elle-même ne change pas (elle est le sas, cf. règle d'architecture n°1). |
| Données existantes (A15) | Repartir propre : le compose de dev redémarre avec une base vide + un script de seed (quelques items de démo créés via l'API du cœur) plutôt qu'un migrateur GeoNode→cœur. |
| Retrait des services | `geonode`, `superset`, `redis` retirés de `docker-compose.yml` (services, volumes, variables d'env associées dans `.env.example`) ; `core/app/geonode.py` supprimé (mort depuis SP-1b, plus aucun appelant). |
| Keycloak | Réalm `geostudio` exporté en JSON, committé (`deploy/keycloak/geostudio-realm.json`), monté et importé via `start-dev --import-realm`. Deux clients : `geostudio-shell` (public, PKCE, redirect URIs de dev) et `geostudio-core` (bearer-only, audience validée par le middleware JWT de SP-1a). Quelques utilisateurs de démo pour les tests manuels en mode `oidc`. |
| Ordre d'exécution | 1) réalm Keycloak + `CoreItemClient` d'abord, testés manuellement en mode `oidc` réel ; 2) bascule des variables d'env shell ; 3) retrait GeoNode/Superset/Redis ; 4) e2e complet sur le compose réduit. Dans cet ordre, chaque étape reste réversible individuellement si un problème surgit. |

## 3. `CoreItemClient` — mapping

`CoreItemClient(coreUrl: string): ItemClient` — un seul client HTTP, un seul
`Authorization: Bearer <token>` (le même déjà porté par `useAuth().getAccessToken()`,
qu'il vienne du mode `oidc` ou `mock`). Mapping direct endpoint par endpoint
vers ceux posés en SP-1b/1c :

| Méthode `ItemClient` | Endpoint cœur |
|---|---|
| `listItems` | `GET /items` |
| `getItem` | `GET /items/{id}` |
| `getMe` | `GET /me` |
| `createConfigItem` | `POST /configs` |
| `updateItem` | `PATCH /items/{id}` |
| `uploadThumbnail` | `POST /items/{id}/thumbnail` |
| `deleteItem` | `DELETE /configs/by-item/{id}` |
| `listGroups` | `GET /groups` |
| `getSharing`/`setSharing` | `GET`/`PUT /items/{id}/sharing` |
| `getMapConfig`/`saveMapConfig`/`getAppConfig`/`saveAppConfig` | `GET`/`PUT /configs/by-item/{id}` (inchangé depuis SP-0) |

`listLayerSources`, `queryDataSource`, `featuresUrl` : inchangés, ils parlent
déjà à Martin/pg_featureserv directement, pas à GeoNode ni au cœur.

`Me.username`/`firstName`/`lastName` (type existant) mappés depuis la réponse
`GET /me` du cœur (`username`, `firstName`, `lastName` — champ `email`/`id`/
`tenantId` du cœur non exposés dans `Me`, le type shell ne change pas).

## 4. Flux de bascule (config & compose)

- `shell/src/config.ts` : `VITE_GEONODE_URL` + `VITE_BUILDER_URL` → une seule
  `VITE_CORE_URL`. Validation d'env mise à jour (variable requise unique).
- `.env.example` : retrait des sections GeoNode/Superset/Redis/Martin-JWT liées
  à GeoNode ; ajout des variables Keycloak realm-import si besoin (aucune
  nouvelle en pratique, `KC_PASSWORD` existe déjà).
- `docker-compose.yml` : suppression des blocs `geonode`, `superset`, `redis`
  (services + volumes `redis-data` associés) ; `keycloak.command` devient
  `start-dev --import-realm` avec un volume supplémentaire montant
  `deploy/keycloak/geostudio-realm.json` dans
  `/opt/keycloak/data/import/`.
- README : liste des services mise à jour, variables d'env mises à jour,
  mention explicite que GeoNode/Superset/Redis ne sont plus utilisés.

## 5. Gestion d'erreurs

- Pendant la bascule, si `CoreItemClient` échoue sur un endpoint non encore
  couvert par SP-1b/1c (régression de scope), l'erreur doit être détectée par
  les e2e existants plutôt que découverte en usage — aucune tolérance
  "ça marchera en prod" sur ce chantier.
- Import du realm Keycloak échoue au démarrage (JSON invalide, conflit
  d'import) → le conteneur `keycloak` ne doit pas démarrer silencieusement en
  état incohérent ; healthcheck du compose doit le détecter.

## 6. Stratégie de tests

- **Les 13 specs e2e Playwright existantes** tournent sur le compose réduit
  (sans GeoNode/Superset/Redis), en mode `VITE_AUTH_MODE=mock` comme
  aujourd'hui — c'est le critère de non-régression principal.
- Un test manuel (pas e2e automatisé, documenté dans le README) vérifie le
  mode `oidc` réel de bout en bout : login via le realm importé, token validé
  par le cœur, `GET /me` cohérent.
- Vérification que `docker compose up` ne démarre plus que : shell, core,
  postgis, minio, martin, titiler, keycloak, traefik, pgbouncer (liste exacte
  du critère d'acceptation SP-1 de la feuille de route).

## 7. Critères d'acceptation

- Les 13 specs e2e passent sur le compose sans GeoNode/Superset/Redis.
- `docker compose up` démarre exactement les 9 services listés ci-dessus,
  rien de plus.
- Un utilisateur peut se connecter en mode `oidc` réel via le realm importé et
  obtenir un `/me` cohérent côté cœur.
- Aucune référence à `VITE_GEONODE_URL`/`VITE_BUILDER_URL`/GeoNode ne subsiste
  dans le code, les docs ou le compose (grep de contrôle avant merge).

## 8. Risques

C'est la sous-phase où une régression devient visible pour la première fois
(les trois précédentes ne changeaient rien d'observable). Mitigé par l'ordre
d'exécution en §2 (chaque étape réversible isolément) et par le filet des 13
e2e. Le point le plus susceptible de surprise est le mode `oidc` réel : c'est
la première fois qu'il tourne de bout en bout (jusqu'ici seul le mode `mock`
était exercé), donc des problèmes de configuration Keycloak (redirect URI,
audience du token) sont probables et doivent être budgétés dans l'estimation.
