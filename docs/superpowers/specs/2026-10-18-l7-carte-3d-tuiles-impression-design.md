# Lot L7 « Carte, 3D, tuiles, impression » — spec

Périmètre : AUD-049, 051, 052, 053, 054, 055, 056, 057, 058, 059, 060, 061, 099
(`docs/revue/audit-2026-10-16/99-synthese.md`, fiches `d01`–`d05`, `d18`). Ordre :
corrections de rendu, puis capacités. Chaque constat est revérifié dans le code avant
traitement (piège n°12).

## Décisions

- **AUD-049** : le fond de carte change sans rechargement (remontage de l'éditeur sur
  `basemap.style`) ; la fenêtre temporelle filtre aussi effets (`__fx_*`), étiquettes et points
  de densité ; le clic lit `pkColumn` (`promoteId`) ; les fonds `xyz:` portent des `glyphs`. Le fond
  vierge reste sans glyphs (choix hors-ligne) : reliquat.
- **AUD-053** : le jeton (OIDC ou lien de partage) est relu à chaque requête du `Tile3DLayer`
  (`loadOptions.fetch`), `X-Share-Link-Token` pour un invité.
- **AUD-054** : le proxy tileset3d garde le zip ouvert (LRU 16) et résout le dossier racine du zip ;
  la validation borne `tileset.json` (64 Mio), exige `asset.version` 1.0/1.1 et `root.boundingVolume`.
- **AUD-055** : au-delà de 5000 entités par tuile, l'échantillon est un hachage de la PK
  (`hashtextextended`), déterministe et sans biais spatial, au lieu des plus petites PK. Pas de
  clustering z8-14 (reliquat).
- **AUD-056** : groupe de budget `tiles` (3000/min) au limiteur ; le proxy TiTiler et terrain3d
  libèrent la connexion DB avant l'appel sortant (timeout 10 s). Cache serveur de tuiles : reliquat.
- **AUD-099** : `statement_timeout` 15 s et `offset` plafonné à 100 000 sur `GET /items` (503 sur
  timeout). Reste : pré-agrégation des tuiles, cache d'`/aggregate`, backfill CDC en flux.
- **AUD-057** : atlas plafonné et trié côté cœur (`limit` + `sortby` poussés, `AtlasConfig.sortBy`),
  bandeau de troncature « N pages sur M » ; séries de cartes et mise en page composable : reliquats.
- **AUD-058** : `ReportSchedulePayload.format` (`pdf`|`png`) et `retry {maxAttempts, delayMinutes}` ;
  un rendu en erreur est rejoué (nouveau run) avant le cron suivant, la panne n'est notifiée
  qu'après le dernier essai ; `PrintLayout.dpi` (96/150/300/600, défaut 150) devient
  `device_scale_factor` plafonné à 8192 px de côté long. Aucune migration.
- **AUD-059** : totaux de pivot non additifs masqués (min/max recomposés), cellule absente vide ;
  fenêtre de référence « période précédente » sans jour commun ; widget Période dérivé du contexte.
  Reliquats : comparaison qui perd les filtres de la source, cross-filter à entrée unique.
- **AUD-060** : `BookmarkCrossFilterEntry.geometry` (borné à 100 000 caractères JSON), reporté dans
  le contexte des rapports planifiés.
- **AUD-051** : `MapLayer.minZoom/maxZoom` (validés, appliqués à toutes les sous-couches) et
  éditeur dans `LayersPanel`. Le filtre par couche (CEL → MapLibre/WHERE ST_AsMVT) reste à faire.
- **AUD-061** : `queryPage` remonte `asOf`/`pending` du lac jusqu'à `DataSourceState.lake` ; le
  `WidgetHost` affiche un avis quand la réplication est en cours ou en retard de plus de 5 minutes.
- **AUD-052** : différé (nécessite le contexte d'expression de l'app jusqu'à `MapView`).
