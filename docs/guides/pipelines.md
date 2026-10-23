# Automatiser avec les pipelines

Un pipeline est un **graphe d'opérations** (lecteurs, transformations, écritures)
exécuté par le moteur DuckDB du cœur, en tâche de fond. Il est activé par
`CORE_ETL_ENABLED=true` (déjà vrai dans la stack packagée) et requiert le privilège
`automation.manage`.

## Construire

1. **Automatisation → Pipelines → Nouveau**, ou l'assistant (wizard) qui génère un
   premier graphe.
2. Glisser des nœuds depuis la **palette** (recherche, récents) et relier les
   ports au clic ou au clavier.
3. **Lecteurs** : collection, fichier S3, REST, Postgres, entrepôts et bases
   externes. Les identifiants vivent dans le **coffre de secrets** (AES-GCM,
   jamais en clair dans la configuration) ; un secret est lié à une URL/portée.
4. **Transformations** : filtrer, joindre, regrouper, reprojeter, géométrie,
   texte, dates, appel HTTP par ligne, géocodage… Le catalogue réel de votre
   instance est `GET /v1/pipelines/ops` — c'est la référence, pas une liste figée.
5. **Écritures** : `writer.collection` (insertion, mise à jour, *upsert*,
   suppression ; les lignes rejetées vont dans une table `<cible>__rejected`).

> Certaines opérations parlant à un service tiers jamais rejoué en réel sont
> **expérimentales** : masquées tant que `CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED`
> vaut `false`.

## Exécuter

- **Aperçu** d'un nœud (échantillon, tri, pagination) avant d'exécuter ; l'aperçu
  est limité aux lectures sans effet de bord.
- **Exécuter** à la demande, avec des **paramètres de run** ; le détail de chaque
  run (nœuds, durées, rejets, tentatives) est consultable.
- **Planifier** (cron) ou déclencher par **webhook entrant** (jeton dédié) ou par
  dépôt de fichier S3. Un run peut être annulé ; les échecs sont repris par nœud.

## Brancher le reste

- **Alertes** : une règle de seuil notifie (email/webhook) au changement d'état.
- **Rapports** : une vue enregistrée (bookmark) rendue en PDF/PNG sur cron.
- **Lineage** : *Impact* montre ce qui dépend d'un jeu de données avant de le
  modifier (aussi via l'outil MCP `get_item_impact`).
