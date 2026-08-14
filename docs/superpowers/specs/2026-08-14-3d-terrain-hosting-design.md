# Terrain hébergé — DEM converti et servi par notre TiTiler (design)

> **Date : 2026-08-14 · Statut : validé (brainstorm)**
> Reste de la vision post-v0.1 (feuille de route §SP-17, arbitrage **A24**).
> **Non planifié, non numéroté** : deuxième des quatre chantiers listés dans
> `CLAUDE.md` § « Reste de la vision post-v0.1, 3D » — après le rendu 3D
> (`2026-08-13-3d-tiles-terrain-design.md`, deck.gl `Tile3DLayer` + terrain
> `raster-dem`, URL externe uniquement) et l'hébergement de tilesets 3D Tiles
> uploadés (`2026-08-13-3d-tileset-hosting-design.md`, dont ce document
> réutilise directement le patron d'architecture). Ce document couvre
> uniquement le terrain servi par notre propre TiTiler depuis un DEM que
> nous hébergeons — pas l'encodage `mapbox`, pas la conversion 3D
> (py3dtiles, nuages de points).
>
> Références : feuille de route
> (`docs/vision/2026-07-04-feuille-de-route-geostudio.md` §SP-17, arbitrage
> A24) · `CLAUDE.md` (règle d'architecture #2 « tout objet de plateforme est
> un document déclaratif schématisé », règle non négociable « une seule
> porte `can(user, action, object)` », « `tenant_id` et `audit_log` sur
> toute table/écriture », suivi « tags d'images Docker à repinner si
> dérive ») · `2026-08-13-3d-tileset-hosting-design.md` (patron
> item+proxy authentifié+capacité repris ici, cf. §3) ·
> `core/app/ingestion/` (patron presigned-upload simple + job procrastinate
> + item+config, réutilisé ici) · `core/app/tileset3d/` (patron capacité +
> validation de `kind` côté `/configs` + proxy authentifié, réutilisé ici) ·
> `shell/src/map/MapView.tsx` (`isHostedTilesetUrl`, généralisé ici) ·
> service `titiler` du compose (déjà provisionné, jamais consommé par le
> shell jusqu'ici).

## 1. Objectif & non-buts

**Objectif.** Un auteur uploade un GeoTIFF d'élévation (DEM) quelconque —
pas nécessairement déjà au format COG. GeoStudio le convertit en COG côté
serveur, le stocke sur S3/MinIO, l'expose comme **item catalogue**
cherchable/partageable/publiable comme n'importe quel autre item, et permet
de le sélectionner depuis `TerrainPanel` (éditeur de carte) au lieu de
taper une URL de tuiles terrain-RGB externe.

**Non-buts explicites** (tranchés en brainstorm 2026-08-14) :

- **Encodage `mapbox`/`terrainrgb`** — le shell ne décode que `terrarium`
  aujourd'hui ; TiTiler supporte les deux nativement (`algorithm=terrarium`
  ou `algorithm=terrainrgb`, natifs depuis TiTiler ≥ 0.8, confirmés contre
  la doc officielle), mais ce chantier encode systématiquement en
  `terrarium` — la meilleure précision des deux (3 mm vs 10 cm) et aucun
  changement client requis. Item séparé du même bullet CLAUDE.md, non
  traité ici.
- **Conversion 3D** (py3dtiles, nuages de points) — item séparé du même
  bullet CLAUDE.md, non traité ici.
- **Hébergement raster/imagerie généraliste** (NDVI, imagerie satellite,
  toute couche `raster` non-terrain) — hors périmètre ; ce chantier ne
  couvre que le DEM terrain. Le futur item pourrait réutiliser une bonne
  partie de l'infrastructure (module `terrain3d`, proxy TiTiler), mais ce
  n'est pas conçu ici.
- **Upload multipart chunké** — un DEM COG pour un terrain hébergé est
  typiquement quelques dizaines à quelques centaines de Mo, pas les
  plusieurs Go d'un tileset ville entière. Un unique PUT présigné (jusqu'à
  5 Go, patron `POST /uploads/presign` déjà utilisé par l'ingestion)
  suffit ; pas de généralisation du modèle de job multipart de
  `tileset3d`.
- **Édition/mise à jour incrémentale** d'un DEM déjà hébergé — un nouvel
  upload crée un nouvel item ; pas de remplacement in-place en v1 (même
  choix que tileset3d hosting).
- **CDN / cache de tuiles en périphérie** — chaque tuile est servie via un
  proxy authentifié sur core ; pas de CDN devant, même arbitrage assumé
  qu'en tileset3d hosting (§1 de ce document précédent), pour la même
  raison (porte d'autorisation unique).
- **Quotas de stockage par tenant** — sujet transverse, pas propre à ce
  chantier.

## 2. Modèle de données

Un DEM hébergé est **un item catalogue de plus**. Onzième `kind` de
`BuilderConfig`, aux côtés de `map`/`dataset`/`pipeline`/…/`tileset3d`.

```python
class Terrain3DPayload(BaseModel):
    sourceKey: str            # clé S3 du COG converti (jamais celle de l'upload brut)
    originalFilename: str

class BuilderConfig(BaseModel):
    kind: Literal[..., "terrain3d"]
    ...
    terrain3d: Terrain3DPayload | None = None
```

- **`Item.resource_type = "terrain3d"`**, créé exactement comme
  `core/app/tileset3d/jobs.py` le fait déjà pour `resource_type="tileset3d"`
  — cherchable, partageable, publiable sans rien ajouter au modèle
  d'autorisation.
- **Validation de payload côté `/configs`** dès la première tâche du plan
  (pas trouvée en revue a posteriori comme pour tileset3d I1) : un
  `kind="terrain3d"` soumis par un utilisateur quelconque sur les 3 routes
  d'écriture `/configs` est rejeté inconditionnellement — seul
  `finalize_terrain3d_task` produit ce `kind`, par appel direct au
  repository, jamais via la route générique.
- **Une seule nouvelle table, `terrain3d_jobs`**, cycle de vie *transitoire*
  de l'upload+conversion (mirroring `tileset3d_jobs`/`ingestion_jobs`) :
  `id, tenant_id, created_by, status (uploaded|converting|done|error),
  source_key (upload brut), converted_key (nullable jusqu'à conversion
  réussie), title, error_message, item_id (nullable jusqu'à commit),
  created_at`. `tenant_id` sur la table + `write_audit(...)` à la création
  du job et à la finalisation (item créé), conformément à la règle non
  négociable.
- **`MapTerrainConfig` (shell) ne change pas** : porte déjà
  `{ tilesUrl, encoding, exaggeration? }` (spec 3D précédente). Un DEM
  hébergé produit juste un `tilesUrl` de la forme
  `{coreUrl}/terrain3d/{item_id}/tiles/{z}/{x}/{y}.png` avec
  `encoding: "terrarium"` fixe — zéro changement de schéma, rétrocompatible
  avec les URL de terrain externes existantes.

## 3. Conversion COG et service des tuiles — approche retenue

**Pourquoi convertir plutôt que valider seulement** (contrairement à
tileset3d, qui ne fait que valider un zip déjà bien formé) : un DEM brut
téléchargé depuis une source publique (IGN, USGS, etc.) est très rarement
déjà tuilé avec overviews — l'exiger aurait rejeté la quasi-totalité des
fichiers réels et déplacé la charge de conversion sur l'auteur (GDAL en
ligne de commande). Le format COG est nécessaire pour que TiTiler serve des
tuiles à coût constant (lecture par plage HTTP, pas un scan du fichier
entier à chaque requête) — condition non négociable pour un service de
tuiles interactif.

**Chaîne de conversion** (worker, nouvelle file procrastinate `terrain3d`,
même conteneur que `ingestion`/`etl`, juste un `-q` supplémentaire — pas de
sidecar séparé, à la différence de `qgis-worker` : `rasterio`+`rio-cogeo`
sont des wheels Python standard avec GDAL embarqué, pas une application
desktop complète) :

1. Téléchargement de l'upload brut **en flux vers un fichier scratch local**
   (`client.download_file`, pas `download_object` de l'ingestion qui charge
   tout en mémoire — un DEM peut faire plusieurs centaines de Mo, risque
   mémoire réel sur le process worker partagé).
2. `rio_cogeo.cog_translate(...)` produit un COG (tuilage + overviews +
   compression par défaut) dans un second fichier scratch.
3. Validation structurelle du résultat (`rio_cogeo.cog_validate` ou
   équivalent `rasterio` direct) — driver GTiff, présence d'overviews,
   tuilage interne confirmé. Échec de conversion ou de validation → status
   `error`, message clair, **aucun item créé** (même discipline que
   tileset3d/ingestion : jamais d'état partiel observable).
4. Upload du COG validé vers S3 sous une nouvelle clé (`converted_key`),
   création de l'item (`resource_type="terrain3d"`) + `BuilderConfig`
   (`kind="terrain3d"`), écriture `audit_log`, status `done`.
5. **Nettoyage systématique des deux fichiers scratch** (upload brut +
   COG converti), y compris sur les chemins d'échec — même invariant que
   `qgis-worker`/pipelines pour les fichiers scratch GDAL.
6. Bornes configurables : `CORE_TERRAIN3D_MAX_UPLOAD_BYTES` (rejet propre
   avant même de lancer la conversion) et un timeout de conversion — même
   philosophie de garde-fou anti-abus que les tuning vars tileset3d.

**Service des tuiles** (à chaque requête pendant la navigation, comme pour
tileset3d) :

- Route `GET /terrain3d/{item_id}/tiles/{z}/{x}/{y}.png` sur core. Auth :
  bearer token standard + `can(user, "read", item)` — la même porte que
  pour tout autre item.
- Charge `sourceKey` (le COG converti, jamais l'upload brut) depuis le
  config de l'item — jamais une clé fournie par le client.
- Appelle TiTiler en interne (réseau docker, pas exposé au navigateur) :
  `GET http://titiler:8000/cog/tiles/{z}/{x}/{y}.png?url=s3://{bucket}/{key}&algorithm=terrarium`
  — TiTiler a déjà les identifiants MinIO (`AWS_ACCESS_KEY_ID`/
  `AWS_SECRET_ACCESS_KEY`/`AWS_ENDPOINT_URL`, déjà dans le compose) et
  l'algorithme `terrarium` est natif depuis TiTiler ≥ 0.8 (notre image
  épingle `0.18.4`) — aucune config TiTiler supplémentaire.
- Stream la réponse PNG de TiTiler vers le client avec
  `Cache-Control: private, max-age=3600` (même politique que tileset3d).
- **Pas de surface SSRF** : l'`url=` passé à TiTiler est toujours dérivée
  du `sourceKey` stocké côté serveur, jamais d'une entrée utilisateur —
  même raisonnement que tileset3d §6 (« pas de récupération d'URL externe »).

## 4. Flux d'upload

1. `POST /terrain3d/uploads/presign` → réutilise le presigned-PUT simple de
   l'ingestion (`core/app/ingestion/storage.py::generate_presigned_put_url`),
   pas de multipart. Renvoie `key` + URL présignée.
2. Le navigateur PUT le GeoTIFF brut directement sur S3 — core ne voit
   jamais les octets (même principe A6 que l'ingestion/tileset3d).
3. `POST /terrain3d/uploads` crée la ligne `terrain3d_jobs` (`uploaded`),
   **commit explicite avant defer** (même garde anti-zombie que
   l'ingestion/tileset3d), puis `convert_terrain3d_task.defer(...)` sur la
   file `terrain3d`.
4. `GET /terrain3d/uploads/{job_id}` pour le poll (même forme que la route
   de statut tileset3d).
5. Le shell attend via un panneau de poll générique (réutilise le patron
   `PipelineRunPanel`/`ReportRunPanel`/tileset3d upload dialog), puis
   affiche le DEM prêt dans le picker.

## 5. UI shell

- `TerrainPanel.tsx` gagne, à côté du champ URL manuelle existant (spec 3D
  précédente), un sélecteur de DEM hébergé : nouvelle fonction
  `fetchHostedTerrain3dSources` (closure interne à `createItemClient`,
  même pattern que `fetchHostedTileset3dSources`) listant les items
  `resource_type="terrain3d"` accessibles. Sélectionner une entrée pose
  `tilesUrl: "{coreUrl}/terrain3d/{itemId}/tiles/{z}/{x}/{y}.png"` et
  `encoding: "terrarium"` sur le `MapTerrainConfig` existant — le champ URL
  manuelle reste valide pour les DEM externes, rien n'est retiré.
- Un bouton d'upload (titre + sélection fichier → presign → PUT → poll,
  même forme que `Tileset3DUploadButton`) à côté du sélecteur.
- **Attachement du bearer token aux requêtes de tuiles terrain** : à la
  différence de `Tile3DLayer` (deck.gl, `loadOptions.fetch.headers` par
  couche), les sources `raster-dem` de MapLibre passent par le chargeur de
  tuiles interne de la lib — pas de point d'injection par couche. `MapView`
  ajoute `transformRequest` à la construction du `maplibregl.Map`, qui
  attache `Authorization: Bearer` uniquement quand l'URL matche l'**origine
  réelle** du core **et** un préfixe de chemin `/terrain3d/` — même vérif
  d'origine que celle qui protège déjà `/tileset3d/` (généralisée en un
  helper partagé plutôt que dupliquée, pour ne pas réintroduire la classe
  de bug corrigée en Task 11 de tileset3d hosting : un simple test de
  sous-chaîne sur l'URL laisserait fuiter le token vers un hôte externe
  forgé du type `https://attacker.example/x/terrain3d/y/tiles/…`). Les URL
  de terrain externes ne matchent jamais et ne reçoivent jamais l'en-tête.

## 6. Gardes-fous de sécurité

- **`CORE_TERRAIN3D_ENABLED`** (défaut désactivé) — coupe routes + bouton
  d'upload tant que l'opérateur n'a pas explicitement provisionné le
  bucket S3 dédié et les dépendances `rasterio`/`rio-cogeo`. **Câblé dans
  `docker-compose.yml` pour `core` ET `worker` dès la première tâche du
  plan** — 3e occurrence de l'oubli documentée dans `CLAUDE.md`
  (SP-17a/SP-17b/tileset3d-hosting), traitée ici comme une contrainte
  globale explicite du plan, pas un correctif de revue finale.
- **`CORE_TERRAIN3D_MAX_UPLOAD_BYTES`** + timeout de conversion — bornent
  la charge worker (mémoire/CPU/disque scratch) par job.
- **Garde tenant sur `terrain3d_jobs`** identique au garde confused-deputy
  de l'ingestion/tileset3d — un job ne peut être piloté que par le tenant
  qui l'a créé.
- **Validation de `kind="terrain3d"` côté `/configs`** — cf. §2, corrige
  par construction la classe de bug trouvée en revue finale sur tileset3d
  (I1) au lieu de la reproduire.
- **Pas de surface SSRF** côté upload (tout vient des octets uploadés par
  l'utilisateur) ; côté service des tuiles, l'`url=` envoyé à TiTiler est
  toujours dérivé server-side du `sourceKey` stocké, jamais d'une entrée
  utilisateur (cf. §3).

## 7. Tests

- **pytest** : garde tenant sur les jobs ; presign/complete ; conversion
  (GeoTIFF valide → COG validé + item créé ; GeoTIFF corrompu/non-raster
  rejeté proprement, aucun item créé ; upload dépassant
  `CORE_TERRAIN3D_MAX_UPLOAD_BYTES` rejeté avant conversion) ; validation
  de payload `kind="terrain3d"` refusée sur les 3 routes `/configs` pour
  un appelant quelconque ; route de lecture (`can()` refuse un item privé
  d'un autre tenant, autorise un item partagé/publié) — avec un TiTiler
  réel disponible en test (déjà dans le compose, pas de mock nécessaire
  pour ce chemin) ou un double léger si le coût CI est prohibitif, décidé
  à l'implémentation. Contrairement à `qgis-worker`, `rasterio`/
  `rio-cogeo` sont des dépendances Python normales : les tests de
  conversion tournent réellement en CI, pas de marker `@pytest.mark.*`
  skippé faute d'environnement (leçon du suivi non bloquant SP-15d).
- **Vitest** : nouvelle branche `TerrainPanel`/`itemClient`
  (`fetchHostedTerrain3dSources`), flux d'upload (progression, erreurs
  presign/complete), helper `transformRequest` (URL hébergée légitime vs
  URL externe forgée avec le même préfixe de chemin — régression directe
  du test déjà écrit pour `isHostedTilesetUrl`).
- **E2E Playwright** (extension de `map-editor` ou nouvelle spec, décidé à
  l'implémentation) : upload d'un petit GeoTIFF DEM synthétique (fixture à
  créer), apparition dans `TerrainPanel`, activation sur une carte,
  sauvegarde, rechargement → le terrain hébergé est restitué et ses
  requêtes de tuiles aboutissent (200, pas de terrain plat).
- **Explicitement hors CI** : performance réelle du proxy core sous charge
  et coût de conversion GDAL sur un DEM volumineux réel — vérification
  manuelle ponctuelle avant de considérer l'incrément livré, non mesurable
  de façon fiable en CI (même discipline que tileset3d hosting §7).

## 8. Risques

| Risque | Garde-fou |
|---|---|
| Charge core proportionnelle au nombre de tuiles vues (pas de CDN, cf. §1) | Décision assumée pour respecter `can()`, même arbitrage que tileset3d hosting ; à réévaluer seulement si la mesure réelle le justifie |
| Conversion GDAL coûteuse en CPU/mémoire sur un gros DEM, sur le worker partagé | File procrastinate dédiée `terrain3d` (isolable via un process worker séparé si besoin, sans changer de conteneur) + `CORE_TERRAIN3D_MAX_UPLOAD_BYTES` + timeout |
| Nouvelle dépendance `rasterio`/`rio-cogeo` (GDAL embarqué) alourdit l'image `core`/`worker` | Poids comparable à `pyogrio` (déjà présent) ; pas un sidecar séparé comme QGIS — pas de gonflement d'image de plusieurs Go |
| Oubli de câblage compose/env (`CORE_TERRAIN3D_ENABLED`, dépendances) — 3e occurrence de cette classe de bug sur ce dépôt | Traité comme contrainte globale explicite du plan dès la première tâche (§6), pas un correctif de revue finale |
| Confusion avec le chantier d'hébergement de tilesets 3D Tiles (autre item du même bullet CLAUDE.md) | Non-but explicite §1 ; module `terrain3d` distinct de `tileset3d`, aucun chevauchement de code, TiTiler (nouveau consommateur) vs S3RangeFile/zip (tileset3d) |
