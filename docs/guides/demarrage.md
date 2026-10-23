# Démarrer avec GeoStudio

Ce guide mène d'une installation vide à un premier résultat visible. Il suppose
la stack locale décrite dans le [README](../../README.md) (`docker compose up -d`).

## 1. Se connecter

- En local, le mode d'authentification est `mock` : vous êtes connecté en tant
  que `mockuser`, **administrateur** dès la première requête (aucun mot de passe).
- En production, la connexion passe par Keycloak (OIDC). Le premier compte
  listé dans `CORE_ADMIN_SUBS` devient administrateur ; les autres sont créés à
  la première connexion avec le rôle **Lecteur** et promus ensuite depuis
  *Administration → Utilisateurs* (voir [administration et rôles](administration-et-roles.md)).

## 2. Peupler une instance de démonstration

```bash
docker compose exec core python -m scripts.seed_demo
```

La commande est idempotente. Elle crée deux collections publiques
(« Incidents », « Points d'intérêt ») **et** des objets de démonstration prêts
à ouvrir : une carte symbolisée, une app avec tableau et carte, un dashboard
avec filtre croisé et un pipeline. Ouvrez le **Catalogue** : ils y apparaissent.

## 3. Repérer les surfaces

| Je veux… | Où |
|---|---|
| Retrouver un objet, le partager | **Catalogue** (recherche plein texte + sémantique, filtres par type) |
| Importer un fichier | Bouton **Importer un fichier** → [guide d'import](importer-et-cartographier.md) |
| Dessiner une carte | **Nouveau → Carte** |
| Construire une app, un dashboard, un site | **Nouveau → App / Dashboard / Site** → [guide du builder](applications-no-code.md) |
| Automatiser une mise à jour | **Automatisation → Pipelines** → [guide pipelines](pipelines.md) |
| Interroger en SQL (analyste) | **Analytique → SQL Lab** |
| Gérer utilisateurs, rôles, collections | **Administration** |

La palette de commandes (**Ctrl/⌘ + K**) ouvre n'importe quelle page et l'aide
contextuelle ; le lien **Aide** de la barre du haut mène à ces guides.

## 4. Aller plus loin

- Piloter la plateforme depuis un agent IA : [serveur MCP](mcp.md).
- Déployer pour de vrai : [déploiement](deploiement.md).
- Un problème ? `docker compose logs core` est le premier réflexe ; le cœur
  expose aussi `GET /health` et la documentation d'API sur `/docs`.
