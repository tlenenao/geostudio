# 0007 — Web Components (Lit) comme technique de SDK widgets

Statut: acceptée
Source : `docs/vision/2026-07-04-feuille-de-route-geostudio.md` §7, A10 —
Technique Web Components (SP-8)

## Contexte

Le SDK public de widgets (destiné à des développeurs tiers) doit choisir une
technique d'implémentation. Options considérées : un contrat Web Components
natif (Lit ou vanilla) avec un pont vers les widgets internes React, un
wrapper automatique React→WC (`@r2wc`) pour tout, ou une réécriture complète
des widgets internes en WC.

## Décision

Contrat Web Components natif (Lit) pour la surface publique ; les widgets
internes restent React, connectés via un pont `WidgetHost` ↔ WC. Pas
d'ouverture aux tiers avant ce pont ; le registre React actuel reste interne.

## Conséquences

- Le contrat public n'expose jamais React (pas de fuite de bundle/version) —
  un tiers peut écrire un widget en Lit, vanilla JS, ou tout autre framework
  qui produit un Web Component conforme.
- Un pont `WidgetHost` à écrire et tester (props/events/slots) ; deux façons
  d'écrire un widget coexistent en interne (React historique, WC pour le
  SDK public).
- Pas de réécriture des widgets internes existants — coût nul sur l'acquis
  déjà testé.
