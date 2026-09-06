# 0002 — Groupes gérés par le cœur, pas par Keycloak

Statut: acceptée
Source : `docs/vision/2026-07-04-feuille-de-route-geostudio.md` §7, A2 —
Source de vérité des groupes (SP-1c)

## Contexte

Le partage par groupe (`ShareDialog`) a besoin d'une source de vérité pour
les groupes d'utilisateurs. L'identité est déléguée à Keycloak (OIDC), mais
les groupes de partage pouvaient soit vivre côté IdP (claims du token,
admin API Keycloak), soit être une notion propre au produit.

## Décision

Les groupes de partage sont gérés par le cœur (tables + UI d'admin minimale),
indépendamment des groupes éventuels de l'IdP.

## Conséquences

- Un déployeur peut fédérer son annuaire (AD, autre IdP) sans que ses
  groupes SIG en dépendent — l'identité (OIDC) et l'autorisation (groupes,
  partages) restent deux couches séparées.
- Pas d'appel à l'admin API Keycloak dans le chemin de partage.
- Deux notions de groupe coexistent (IdP vs produit) — assumé, cohérent avec
  le modèle déjà en place côté GeoNode dont ce produit hérite l'UX.
