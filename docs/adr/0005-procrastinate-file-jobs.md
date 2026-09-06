# 0005 — procrastinate comme file de jobs

Statut: acceptée
Source : `docs/vision/2026-07-04-feuille-de-route-geostudio.md` §7, A5 — File
de jobs / workers (SP-6, anticipé si besoin en SP-3)

## Contexte

Les traitements asynchrones (ingestion, pipelines, exports, alertes,
rapports planifiés) ont besoin d'une file de jobs. Options considérées :
procrastinate (file Postgres native), Celery+Redis (standard de fait), ou
une file maison sur `SELECT ... FOR UPDATE SKIP LOCKED`.

## Décision

procrastinate : la file vit dans Postgres, pas de broker séparé.

## Conséquences

- Aucune dépendance d'infrastructure supplémentaire — cohérent avec la
  sortie de Redis (ADR-0011) : Postgres reste la seule brique d'état
  critique du cœur.
- Retries et planification (cron) inclus dans la bibliothèque, pas à
  réimplémenter.
- Débit plafonné par Postgres — sans objet à l'échelle visée par le produit.
- Tout nouveau domaine de job (pipelines, alertes, rapports, exports) suit ce
  même patron plutôt que d'introduire une deuxième file.
