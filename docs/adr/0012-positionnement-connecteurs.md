# 0012 — Positionnement des connecteurs : entrepôts/SQL/objet d'abord, le reste à la demande

Statut: acceptée
Source : question produit Q2 (répondue le 2026-09-15 : produit horizontal,
parité de couverture de connecteurs comme différenciateur face à FME) et
`REV-123` (`docs/revue/2026-09-04-backlog.md`, GAP-29, écart de largeur face
aux 450+ connecteurs FME).

## Contexte

FME couvre plus de 450 formats et connecteurs ; GeoNode 5 propose un import
multi-formats unifié. GeoStudio en couvrait 4 à l'origine, puis a ajouté des
formats d'import (SP-56, GAP-29) et des lecteurs de pipeline (REST, PostgreSQL,
Snowflake, BigQuery, SQL Server, Oracle, stockage objet, Databricks). L'écart de
largeur restera réel : viser l'exhaustivité est inatteignable et n'est pas
l'objectif. Le « Partiel » de `REV-123` est une question de positionnement, pas
un défaut qu'un lot de code ferme.

## Décision

On ne vise pas la couverture exhaustive des connecteurs. On livre en priorité
les familles à plus forte valeur pour un produit horizontal — entrepôts de
données, bases SQL, stockage objet — chacune par le patron `OperationContract`
(registre unique `OPERATIONS` : schéma de paramètres, secret typé du coffre,
garde d'egress SSRF, plafonds de lignes et délais, dialecte SQLAlchemy résolu
par entry point quand il existe). Tout autre connecteur est traité à la demande
(besoin concret d'un utilisateur), jamais par anticipation. Le suivi chiffré de
l'écart reste la matrice `docs/revue/matrice-couverture-fme.{jsonl,md}`.

## Conséquences

- Un nouveau connecteur SQL est un clone du chemin existant (op + secret
  `*_dsn` + dépendance Apache/BSD/MIT) ; toute dépendance copyleft ou toute
  licence non vérifiée exige une note dans `docs/ops/redistribution-images.md`
  et la vérification arm64 avant fusion.
- Un connecteur non vérifiable sans compte/cluster réel (Databricks, Redshift,
  Snowflake) est livré avec la mention explicite « non vérifié sur instance
  réelle » et un test manuel skippé par défaut, jamais câblé en CI.
- Redshift n'a pas d'op dédiée : il passe par `reader.connector.postgres`, avec
  un traitement spécifique du délai d'attente (REV-110).
- `REV-123` reste « Partiel » par construction : cette décision l'assume au lieu
  de promettre une parité qu'on ne tiendra pas.
