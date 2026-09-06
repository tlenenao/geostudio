# 0008 — Structure du dépôt : monorepo, `core/` + `shell/`

Statut: acceptée
Source : `docs/vision/2026-07-04-feuille-de-route-geostudio.md` §7, A14 —
Structure du dépôt (SP-1a)

## Contexte

Le fork `gis-project` héritait d'un service nommé `builder-service` qui,
dès SP-1b, allait gérer bien plus que la construction de configs (items,
partage, catalogue...). Options considérées : garder le monorepo avec ce nom
inchangé, renommer `builder-service/` en `core/`, ou scinder en deux dépôts
séparés (core/shell).

## Décision

Monorepo unique, `builder-service/` renommé `core/` ; `shell/` inchangé.

## Conséquences

- Le nom du module dit ce qu'il est (le cœur du produit), évite le mensonge
  progressif de « builder-service » une fois les items/le partage/le
  catalogue ajoutés.
- Une seule CI, un seul historique de PR — un changement front+back cohérent
  tient dans une seule pull request.
- Pas de coordination de version croisée entre deux dépôts (overhead jugé
  injustifié pour un développement mono-committer).
- Renommage propagé une fois (compose, CI, docs) au moment du fork —
  coût ponctuel, pas récurrent.
