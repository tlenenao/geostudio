# Cadrage des reliquats L (AUD-057, 099, 014, 115)

Une page par item : périmètre, tâches, risques, effort. Aucun n'est implémenté dans le
couloir C. Les points de départ sont ceux de `99-synthese.md` ; une relecture du code précède
toute exécution (piège n°12).

## AUD-057 — séries cartographiques, mise en page composable, pied de page PDF

- **Périmètre** : (1) pied de page/en-tête PDF (pagination, titre, date, licence) ; (2) mise
  en page composable : `printLayout` passe de gabarit fixe à une liste de blocs (carte,
  légende, texte CEL, tableau, échelle) positionnés sur la page ; (3) série cartographique :
  une page par entité d'un atlas, carte recadrée sur l'emprise de l'entité (l'atlas actuel est
  borné/trié côté serveur, sans carte par fiche).
- **Tâches** : schéma `PrintLayout` v2 (+ migration de lecture des configs v1, sans migration
  SQL) ; éditeur `PrintLayoutPanel` à blocs ; le worker Playwright rend N pages (une navigation
  par entité, réutilisation du contexte navigateur) ; plafond et reprise du job (le plafond de
  fiches existant devient un paramètre de tenant) ; E2E d'un PDF multi-pages.
- **Risques** : délai de rendu (120 s par rendu, cf. minuterie d'export) : il faut un budget
  par page et une annulation ; compatibilité des configs `printLayout` existantes ; mémoire du
  Chromium sur 100 pages ; vérification impossible sans stack réelle (rejeu export, section C
  de `100`).
- **Effort** : L (4 à 6 j). Dépend du rejeu d'export réel.

## AUD-099 — pré-agrégation, cache, backfill, index

- **Périmètre** : (1) tuiles agrégées au-delà de z 7 (pré-agrégation ou cache) ; (2) cache et
  limite de concurrence sur `/aggregate` ; (3) backfill CDC en flux (aujourd'hui en mémoire) ;
  (4) aperçu de pipeline sans matérialiser toute la collection (échantillon + `LIMIT` poussé) ;
  (5) index d'attribut déclaratifs par collection et `statement_timeout` sur `GET /items`.
- **Tâches** : cache de tuiles clé `(collection, z/x/y, version du lac)` invalidé par
  compaction (Redis exclu : cache Postgres ou fichier local borné) ; sémaphore par tenant sur
  `/aggregate` ; backfill par lots de lignes avec curseur ; `CollectionIndex` (champ + type)
  avec DDL `CREATE INDEX CONCURRENTLY` en job ; `SET LOCAL statement_timeout` dans `rls_scope`
  des lectures.
- **Risques** : invalidation de cache (données périmées après écriture, RLS : une tuile mise
  en cache ne doit jamais traverser un `rls_scope` ni une limite géographique, donc clé par
  rôle effectif) ; `CREATE INDEX CONCURRENTLY` hors transaction Alembic ; migration
  (plage 0180-0189) pour `CollectionIndex` ; mesures de charge exigeant des volumes réels.
- **Effort** : L (5 à 8 j), séparable en 3 lots (tuiles/cache, backfill, index/timeout).

## AUD-014 — lecture en flux OGR/GeoParquet/XML

- **Périmètre** : l'import charge le fichier entier en mémoire (pic 2,9 Go pour 281 Mo, worker
  limité à 2 Go). Les lecteurs CSV/JSONL sont déjà bornés ; restent OGR (GPKG/SHP/GDB/KML),
  GeoParquet, GML/XML.
- **Tâches** : OGR : itérer `layer` par fenêtres (`SetNextByIndex`/`GetNextFeature`) et
  insérer par lots de N lignes ; GeoParquet : `pyarrow.parquet.ParquetFile.iter_batches` ;
  XML/GML : `iterparse` avec purge des éléments ; `_load_rows` devient un générateur de lots ;
  le rapport (rejets, `ignoredColumns`) s'agrège en flux ; mesure de pic mémoire en test
  (`tracemalloc`/`resource`) sur un fichier synthétique de 200 Mo.
- **Risques** : `_load_rows` est le point unique de plusieurs correctifs (paramètres liés,
  clés réservées, `force_2d`, `ST_MakeValid`) : le passage en lots ne doit pas les diviser ;
  atomicité de l'import (une seule transaction vs lots commités : reprise partielle à
  décider) ; quotas de comptage déjà posés dès `POST /v1/uploads` ; schéma inféré sur les
  premières lignes seulement (types tardifs).
- **Effort** : L (4 à 6 j). Décision à prendre : import atomique ou par lots reprenables.

## AUD-115 — i18n du cœur et fuseaux

- **Périmètre** : le shell a un mécanisme fr/en (lot L11). Restent côté cœur : erreurs RFC
  7807, copilote, e-mails (alertes, rapports, invitations), métadonnées DCAT localisées ;
  `users.locale`/`users.timezone` ; `timeZone` des alertes, rapports planifiés et exports ;
  traductions XLSForm ignorées ; RTL.
- **Tâches** : migration (0180) `users.locale`, `users.timezone` (+ `tenants` par défaut) et
  lecture du claim `locale` à la création JIT ; catalogue de messages du cœur (`gettext` ou
  dictionnaire par domaine, clé stable dans `type`/`code` RFC 7807, texte localisé dans
  `detail`) négocié par `Accept-Language` puis `users.locale` ; gabarits d'e-mail par langue ;
  `timeZone` propagé aux `AlertRule`/`ReportSchedule`/export (déjà accepté par l'agrégat) ;
  XLSForm : libellés `label::en` conservés dans le schéma de formulaire.
- **Risques** : centaines de messages `detail` en français dont des tests assertent le texte ;
  contrat d'API (`detail` devient variable : les clients doivent lire `code`) ; DCAT multilingue
  (`dct:title@en`) à arbitrer avec D8 (contenu utilisateur traduisible, décision de Tanguy) ;
  RTL = chantier CSS propre, à découper ; test de migration sur base non vide.
- **Effort** : L (6 à 10 j), séparable : (a) `locale`/`timezone` + e-mails, (b) erreurs et
  copilote, (c) DCAT/XLSForm/RTL (dépend de D8).
