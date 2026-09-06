# 0006 — CEL comme langage d'expressions no-code

Statut: acceptée
Source : `docs/vision/2026-07-04-feuille-de-route-geostudio.md` §7, A8 —
Langage d'expressions (SP-5)

## Contexte

Le builder no-code a besoin d'un langage d'expressions pour `visibleWhen`,
les colonnes calculées, les actions composées et les bindings — évalué à la
fois côté serveur (Python) et côté client (JS), sandboxable, et si possible
bien généré par des LLM (le copilote). Options considérées : CEL, JSONLogic,
JS sandboxé (QuickJS-wasm/SES).

## Décision

CEL (cel-python côté serveur, cel-js côté client), validé par un spike
cel-js en ouverture de SP-5 ; JSONLogic en repli si le spike avait échoué.

## Conséquences

- Même sémantique d'expression des deux côtés (serveur/client), condition du
  spike réussi avant SP-5 (confirmé — pas de repli JSONLogic nécessaire).
- Sandboxable par construction, analysable statiquement — pas de JS
  sandboxé côté serveur (risque d'évasion, coût d'audit).
- Deux implémentations (Python/JS) à garder alignées à chaque évolution du
  langage d'expressions.
- Les bindings CEL généralisés et les variables typées (périmètre SP-5)
  s'appuient sur ce même moteur, pas un second langage parallèle.
