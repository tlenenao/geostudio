# Construire une app, un dashboard ou un site sans code

Apps et dashboards partagent **un seul moteur** : une configuration déclarative
(JSON schématisé) rendue en mode édition, aperçu ou exécution. Rien n'est caché
hors de cette configuration — c'est ce qui permet aussi de la générer par un
agent ([MCP](mcp.md)) ou le copilote du builder.

## Créer

**Nouveau → App** (ou Dashboard, Site). Le builder s'ouvre sur un canevas en
grille responsive (réglage par point de rupture).

## Les briques

- **Sources de données** : collection, jeu de données partagé (*dataset*),
  GeoJSON statique, enregistrements saisis à la main. Un dataset est un objet du
  catalogue réutilisable : **Promouvoir en jeu de données partagé** depuis une
  source, avec colonnes calculées et métriques nommées.
- **Widgets** : carte, tableau, graphique, indicateur (KPI), filtre, formulaire
  généré depuis le schéma de la collection, fiche d'entité, texte, image, onglets,
  lecteur temporel… Chaque widget se lie à une source.
- **Variables typées** et **bus d'actions** : cliquer une ligne du tableau peut
  filtrer le graphique (`setFilter`), ouvrir un formulaire, naviguer.
- **Expressions (CEL)** : conditions d'affichage (`visibleWhen`), colonnes
  calculées, liaisons dynamiques. Le copilote peut proposer l'expression à partir
  d'une phrase.
- **Filtre croisé** : un clic sur un widget filtre les autres, y compris entre
  datasets liés (lien spatial ou clé).
- **Thèmes**, annuler/rétablir (50 niveaux), historique de versions.

## Prévisualiser, publier, exporter

- **Aperçu** : même rendu que l'exécution, sans enregistrer.
- **Enregistrer** puis partager/publier depuis le catalogue (garde anti-écrasement
  `If-Match` : un conflit de versions est signalé, jamais écrasé).
- **Intégrer** dans un autre site : lien d'intégration `/embed/<jeton>` (les droits
  du lien sont recoupés avec ceux de son créateur).
- **Exporter** un bundle : Statique, Connecté ou Autoporté (conteneur + snapshot).

## Sites

Un **Site** assemble des pages (widgets de contenu, fiches de jeux de données,
téléchargement) servies sous `/sites/<slug>`.
