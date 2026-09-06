# 0010 — Client TS du shell : types générés depuis l'OpenAPI du cœur

Statut: acceptée
Source : `docs/vision/2026-07-04-feuille-de-route-geostudio.md` §7, A11 —
Client API TypeScript du shell (SP-1d)

## Contexte

Le shell React a besoin d'un client typé pour parler au cœur. Options
considérées : générer les types TS depuis la spec OpenAPI du cœur
(`openapi-typescript`), avec `CoreItemClient` écrit à la main par-dessus ; ou
un client entièrement manuel (statu quo hérité).

## Décision

Types générés depuis l'OpenAPI du cœur (`shell/src/api/generated/
core-schema.d.ts`) ; l'interface `ItemClient`/`CoreItemClient` reste écrite à
la main par-dessus, comme façade (cf. Règle d'architecture non négociable
n°1 de `CLAUDE.md`).

## Conséquences

- Toute dérive front/back sur la forme des réponses est détectée à la
  compilation TypeScript, pas seulement à l'exécution.
- Une étape de génération obligatoire dans le flux de travail dès qu'une
  route ou un modèle change côté cœur (piège CLAUDE.md n°1 : classe d'oubli
  la plus fréquente du dépôt — diff vide légitime uniquement si la surface
  est derrière un flag éteint).
- L'OpenAPI devient un contrat de premier ordre, consommé aussi par le MCP
  (schéma JSON `AppConfig`, SP-2/SP-54) et potentiellement par des tiers.
- Le préfixe `/v1` (SP-57b) est un exemple direct de changement qui force
  une régénération à diff non vide (chaque chemin de route change).
