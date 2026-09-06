# 0001 — Moteur d'autorisation maison + `can()` unique

Statut: acceptée
Source : `docs/vision/2026-07-04-feuille-de-route-geostudio.md` §7, A1 — Moteur
d'autorisation v0 (SP-1c)

## Contexte

Le cœur doit décider, à chaque requête, si un utilisateur peut agir sur un
objet (item, collection, feature). Le modèle de partage v0 est simple :
privé/groupe/public, sans hiérarchie. Les options considérées allaient d'un
moteur ReBAC externe (OpenFGA) à une RLS Postgres généralisée sur les tables
du cœur.

## Décision

Tables maison (`item_shares`, rôles) + une fonction unique `can(user, action,
object)` comme seul point d'entrée d'autorisation — pas de service d'état
externe, pas de RLS sur les tables du cœur lui-même.

## Conséquences

- Toute nouvelle route protégée passe par `can()` (ou `decide()`/
  `require_privilege` depuis SP-29a/SP-31) — jamais une vérification ad hoc
  de `is_admin`/rôle inline.
- Le point d'entrée unique permet de brancher un moteur ReBAC (OpenFGA) plus
  tard sans toucher les routes, si le partage devient hiérarchique.
- La RLS PostGIS reste réservée aux données métier (voir ADR-0003), pas aux
  tables internes du cœur.
