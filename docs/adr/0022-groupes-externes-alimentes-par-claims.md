# 0022 — Groupes externes : appartenance alimentée par les claims, groupes gérés par le cœur

Statut: acceptée
Source : ARC-24 (comparatif §6.1.2) ; ADR 0002 (groupes gérés par le cœur), A2, SP-31.

## Contexte

Les groupes de partage sont gérés par le cœur (ADR 0002) ; les claims OIDC ne sont pas utilisés pour les alimenter, d'où une double saisie en collectivité.

## Décision

- L'ADR 0002 est **précisé, pas amendé** : les groupes restent créés, nommés et portés par le cœur ; seule l'**appartenance** peut être alimentée par un mapping administré `claim de groupe IdP → groupe du cœur`.
- Application **additive** à la connexion : ajout des appartenances mappées présentes dans le claim, retrait de celles issues d'un mapping dont le claim a disparu. Les appartenances ajoutées manuellement ne sont jamais retirées (marquage de l'origine : `manual` vs `claim`).
- Le mapping est une table admin (privilège existant de gestion des groupes), auditée. Un claim inconnu ou mal formé est ignoré, jamais une erreur de connexion.
- Aucune élévation de privilèges par ce canal : un groupe donne des droits de partage, pas de rôle.

## Conséquences

- Un IdP compromis peut ajouter des appartenances aux groupes mappés : le mapping est donc opt-in par groupe.
