# 0021 — Relations entre collections : clé étrangère logique déclarée

Statut: acceptée
Source : ARC-21 (comparatif §6.1.2) ; ADR 0004 (OGC API Features), A3 (RLS), ARC-13/15.

## Contexte

Seule une jointure de requête visuelle existe. Les cas collectivité (parcelle → propriétaires) exigent des enregistrements liés dans les popups et formulaires, et des suppressions contrôlées. Une géodatabase d'entreprise complète est hors périmètre (H1).

## Décision

- Une **relation** est déclarée entre deux collections (document déclaratif, règle d'architecture n°2) : cardinalité 1-1 / 1-N / N-N (table d'association), champ(s) clé, politique de suppression `restrict` (défaut) ou `cascade`.
- Clé étrangère **logique** par défaut (validée à l'écriture par le cœur) ; pas de contrainte SQL imposée entre collections de tenants différents (même tenant obligatoire).
- Les enregistrements liés sont lus **sous la RLS et le masquage de chaque côté** : un lecteur ne voit jamais un enfant qu'il ne peut pas lire. Chaque écriture de relation passe par `can()` des deux collections et par le journal ARC-15.
- Pas de versioning de branche, pas de relations spatiales automatiques.

## Conséquences

- Suppression `restrict` : 409 si des enfants existent ; `cascade` explicite, auditée.
- Migration testée sur base non vide, dans les deux sens.
