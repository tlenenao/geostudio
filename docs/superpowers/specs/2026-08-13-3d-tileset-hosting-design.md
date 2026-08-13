# Hébergement de tilesets 3D Tiles uploadés (design)

> **Date : 2026-08-13 · Statut : validé (brainstorm)**
> Reste de la vision post-v0.1 (feuille de route §SP-17, arbitrage **A24**).
> **Non planifié, non numéroté** : le rendu 3D (deck.gl `Tile3DLayer` +
> terrain `raster-dem`) a été livré hors numéro de SP
> (`docs/superpowers/specs/2026-08-13-3d-tiles-terrain-design.md`) mais a
> explicitement mis hors périmètre l'hébergement de tilesets uploadés —
> jusqu'ici un tileset 3D Tiles ne peut être qu'une URL externe. Ce document
> couvre uniquement ce chantier (le premier des 4 listés dans `CLAUDE.md` §
> « Reste de la vision post-v0.1, 3D »), pas le terrain via notre TiTiler, ni
> l'encodage `mapbox`, ni la conversion 3D.
>
> Références : feuille de route
> (`docs/vision/2026-07-04-feuille-de-route-geostudio.md` §SP-17 « Contenu
> 3D », arbitrage A24 — « Hébergement de tilesets 3D Tiles *existants* :
> upload (zip) → S3 → item ; la conversion […] est différée ») ·
> `docs/superpowers/specs/2026-08-13-3d-tiles-terrain-design.md` (§1, non-but
> explicite « hébergement de tilesets uploadés ») · `CLAUDE.md` (règle
> d'architecture #2 « tout objet de plateforme est un document déclaratif
> schématisé », règle non négociable « une seule porte `can(user, action,
> object)` », « `tenant_id` et `audit_log` sur toute table/écriture ») ·
> `core/app/ingestion/` (patron presigned-upload + job procrastinate +
> item+config, réutilisé ici) · `core/app/export/jobs.py` (patron S3 pour
> blob opaque) · `core/app/harvest/service.py` (patron item référençant une
> ressource externe, écarté au profit du patron `BuilderConfig` — cf. §2).

## 1. Objectif & non-buts

**Objectif.** Un auteur uploade un zip contenant un tileset 3D Tiles
(`tileset.json` + tuiles binaires, potentiellement plusieurs Go et des
dizaines de milliers de fichiers pour un tileset ville entière).
GeoStudio le stocke sur S3/MinIO (déjà provisionné), l'expose comme **item
catalogue** cherchable/partageable/publiable comme n'importe quel autre
item, et permet de le sélectionner depuis `LayerPicker` — au lieu de taper
une URL externe — pour l'ajouter à une couche `tiles3d` d'une carte.

**Non-buts explicites** (tranchés en brainstorm 2026-08-13) :

- **Conversion 3D** (py3dtiles, nuages de points) — différée par
  l'arbitrage A24 lui-même, non concernée par ce document.
- **Terrain servi par notre propre TiTiler** — chantier séparé, risque
  technique distinct (encodage terrain-RGB depuis un DEM brut), non traité
  ici.
- **Édition/mise à jour incrémentale** d'un tileset déjà uploadé — un
  nouvel upload crée un nouvel item ; pas de remplacement in-place en v1.
- **CDN / cache de tuiles en périphérie** — chaque tuile est servie via un
  proxy authentifié sur core (§4) ; pas de CDN devant, décision assumée
  pour respecter la porte d'autorisation unique (cf. §3 « approches
  écartées »). Optimisation différée si le besoin réel apparaît — même
  logique de renoncement pragmatique que l'A25 (« print pro » différé).
- **Prévisualisation 3D à l'upload** — validation structurelle seulement
  (présence + JSON valide de `tileset.json`), pas de rendu de vignette.
- **Quotas de stockage par tenant** — au-delà des gardes-fous anti-abus de
  base (§5), la gestion de quota est un sujet transverse, pas propre à ce
  chantier.
- **Extraction serveur en objets S3 individuels** — écartée au profit d'un
  service par lecture-par-plage directement dans le zip (cf. §3).

## 2. Modèle de données

Un tileset hébergé est **un item catalogue de plus**, pas un mécanisme à
part — cohérent avec la règle CLAUDE.md #2. Dixième `kind` de
`BuilderConfig`, aux côtés de `map`/`dataset`/`pipeline`/`alert`/`report`/…

```python
class Tileset3DPayload(BaseModel):
    sourceKey: str          # clé S3 du zip complet, jamais extrait
    tilesetJsonPath: str    # v1 : toujours "tileset.json" (racine exigée)
    totalBytes: int
    entryCount: int

class BuilderConfig(BaseModel):
    kind: Literal[..., "tileset3d"]
    ...
    tileset3d: Tileset3DPayload | None = None
```

- **`Item.resource_type = "tileset3d"`**, créé par
  `items_repo.create_item(...)` exactement comme l'ingestion le fait déjà
  pour `resource_type="map"` — cherchable, partageable, publiable par le
  mécanisme existant, sans rien ajouter au modèle d'autorisation.
- **Pas de nouvelle table `tileset3d_assets`** : les métadonnées de
  l'artefact final vivent dans le payload du config, déjà versionné/stocké
  par l'infra `configs` existante (SP-0) — rien à dupliquer.
- **Une seule nouvelle table, `tileset3d_jobs`**, qui ne suit que le cycle
  de vie *transitoire* de l'upload multipart (mirroring `ingestion_jobs`,
  `core/app/ingestion/models.py`) :
  `id, tenant_id, created_by, status (pending|uploading|finalizing|done|error),
  source_key, upload_id, error_message, item_id (nullable jusqu'à commit),
  created_at`. `tenant_id` sur la table + `write_audit(...)` à la création
  du job et à la finalisation (item créé), conformément à la règle non
  négociable.
- **`MapLayer` (shell) ne change pas** : `kind: "tiles3d"` porte déjà un
  champ `url` générique (spec 3D précédente). Un tileset hébergé produit
  juste une URL de la forme `/tileset3d/{item_id}/tileset.json` au lieu
  d'une URL externe — zéro changement de schéma, rétrocompatible avec les
  tilesets externes existants.

## 3. Service des fichiers au navigateur — approche retenue

Un 3D Tiles ne se télécharge pas en un fichier : deck.gl fait des
centaines/milliers de requêtes individuelles (`tileset.json` puis chaque
tuile enfant) pendant la navigation. Trois approches ont été comparées :

- **(A) — retenue.** Le zip reste un **seul objet S3**, jamais extrait.
  Une route core ouvre `zipfile.ZipFile` (stdlib) sur un fichier-plage
  custom (`S3RangeFile`, lecture par `Range` GET à la demande) et sert
  chaque entrée individuellement. Respecte `can()` partout (chaque requête
  passe par une authentification standard), pas de risque de zip-bomb en
  stockage (jamais totalement décompressé côté serveur), pas d'explosion du
  nombre d'objets S3 (un tileset ville entière peut avoir des dizaines de
  milliers de fichiers). Contrepartie assumée : chaque tuile traverse core
  (latence, charge), pas de CDN en v1.
- **(B) — écartée.** Extraction complète en objets S3 individuels. Plus
  lourde (download + re-upload de tout le volume, stockage temporairement
  doublé, gardes anti-zip-bomb à construire soi-même) et n'élimine
  finalement pas le besoin d'un proxy core pour respecter `can()` — sa
  complexité s'ajoute à celle de (A) sans supprimer le proxy.
- **(C) — écartée.** Bucket/préfixe public en lecture. Le plus simple et
  performant, mais contourne frontalement la porte unique `can()` (règle
  d'architecture non négociable) : un tileset au partage restreint
  fuiterait dès que son URL est connue. Rejetée pour ne pas créer une
  exception de sécurité au modèle d'autorisation pour cette seule
  ressource.

**Pourquoi (A) reste pratique malgré la ré-ouverture du zip par requête** :
`zipfile.ZipFile` ne lit que l'EOCD + la table centrale à l'ouverture — un
coût constant indépendant de la taille des données (pas du volume total du
tileset), pas un scan de tout l'objet. Documenté comme limite v1 assumée
(pas de cache en mémoire du process worker) — à optimiser seulement si la
mesure réelle le justifie (même discipline de scope que l'A25).

## 4. Flux d'upload et de lecture

**Upload (multipart, jusqu'à plusieurs Go) :**

1. `POST /tileset3d/uploads` → crée la ligne `tileset3d_jobs` (`pending`),
   appelle `S3.create_multipart_upload`, renvoie `job_id` + `upload_id` +
   `key`. Garde tenant sur le job identique au garde confused-deputy de
   l'ingestion (`core/app/ingestion/routes.py:99-105`).
2. Le shell découpe le fichier en parts (ex. 100 Mo) et demande une URL
   présignée par part : `POST /tileset3d/uploads/{job_id}/parts/{n}/presign`
   → upload direct navigateur→S3, core ne voit jamais les octets (même
   principe que l'ingestion). L'API S3 multipart autorise nativement un
   part unique de taille libre : le même chemin de code sert aussi bien un
   fixture de test de 50 Ko qu'un tileset ville entière de plusieurs Go —
   pas de branchement séparé « petit fichier ».
3. `POST /tileset3d/uploads/{job_id}/complete` avec `{part_number, etag}[]`
   → `S3.complete_multipart_upload`, status `finalizing`, **commit
   explicite avant defer** (même garde anti-zombie que l'ingestion,
   `core/app/ingestion/routes.py:116-122`), puis
   `finalize_tileset3d_task.defer(...)` sur une file procrastinate dédiée
   `tileset3d`.
4. Le worker (`finalize_tileset3d_task`) ouvre le zip complété via
   `S3RangeFile` + `zipfile.ZipFile` et valide (§5) : nombre d'entrées,
   taille totale décompressée, taille par entrée, noms d'entrée sûrs,
   exactement un `tileset.json` à la racine, JSON valide avec
   `asset.version`. Succès → crée l'item (`resource_type="tileset3d"`) + le
   `BuilderConfig` (`kind="tileset3d"`), écrit `audit_log`, status `done`.
   Échec → status `error` + message, **aucun item créé** (jamais d'état
   partiel, même discipline que l'ingestion,
   `core/app/ingestion/tasks.py:66-71`).
5. Le shell attend via un panneau de poll générique (réutilise le patron
   `PipelineRunPanel`/`ReportRunPanel`), puis ouvre le nouvel item une fois
   `done`.

**Lecture (à chaque requête de tuile pendant la navigation) :**

- Route `GET /tileset3d/{item_id}/{path:path}` sur core. Auth : bearer
  token standard + `can(user, "read", item)` — la même porte que pour tout
  autre item (fonctionne aussi en mode démo public si l'item est publié).
- Charge `sourceKey`/`tilesetJsonPath` depuis le config de l'item, résout
  `path` contre les noms d'entrée du zip (404 si absent), stream les octets
  décompressés avec `Content-Type` déduit de l'extension (`.json` ;
  `.b3dm`/`.i3dm`/`.pnts`/`.cmpt`/`.glb` → `application/octet-stream`) et
  `Cache-Control: private, max-age=3600`.
- `MapView.tsx` (shell) attache le token de session courant via
  `loadOptions.fetch.headers.Authorization` du `Tile3DLayer` deck.gl
  **uniquement quand l'URL de la couche pointe vers le préfixe
  `/tileset3d/`** — les tilesets externes existants ne sont pas affectés,
  aucun changement pour eux.

## 5. UI shell

- `LayerPicker.tsx` gagne une quatrième source dans sa liste cherchable
  existante (à côté de vector/feature/raster,
  `shell/src/api/itemClient.ts::listLayerSources`) :
  `fetchHostedTileset3dSources()`, qui liste les items
  `resource_type="tileset3d"` accessibles et retourne
  `{id, title, kind: "tiles3d", url: "/tileset3d/{id}/tileset.json"}`. Le
  formulaire d'URL manuelle existant (spec 3D précédente) reste valide pour
  les tilesets externes — la liste catalogue devient le chemin préféré pour
  un tileset hébergé, sans rien retirer.
- Point d'entrée de création : une option « Nouveau tileset 3D » dans
  `NewItemButton` (même patron que « Dataset par requête visuelle » de
  SP-14o), ouvrant un flux upload (sélection fichier zip → barre de
  progression multipart → panneau de poll de finalisation) qui atterrit sur
  la fiche du nouvel item une fois prêt.

## 6. Gardes-fous de sécurité

- **Caps configurables** (env) : nombre d'entrées max, taille décompressée
  totale max, taille décompressée max par entrée (anti zip-bomb sur une
  seule entrée — une petite entrée compressée qui se déplierait en une
  taille énorme lors d'une seule requête de lecture) — rejet propre en
  `error` côté job de finalisation, jamais un crash worker.
- **Noms d'entrée non sûrs rejetés** à la finalisation (`..`, chemin
  absolu) — défensif même si (A) ne les extrait jamais sur disque, pour
  éviter toute ambiguïté de résolution de `path` côté route de lecture.
- **Garde tenant sur `tileset3d_jobs`** identique au garde confused-deputy
  de l'ingestion — un job ne peut être piloté que par le tenant qui l'a
  créé.
- **Pas de surface SSRF** : aucune récupération d'URL externe (tout vient
  des octets uploadés par l'utilisateur) — pas besoin de la garde egress
  harvest ici.
- **`CORE_TILESET3D_ENABLED`** (défaut désactivé), même précédent que
  `CORE_ETL_ENABLED`/`CORE_EXPORT_ENABLED` — coupe route + bouton d'upload
  tant que l'opérateur n'a pas explicitement provisionné le bucket S3
  dédié.

## 7. Tests

- **pytest** : garde tenant sur les jobs ; presign/complete (succès +
  erreurs) ; `finalize_tileset3d_task` (caps dépassés, zip sans
  `tileset.json` racine, `tileset.json` invalide, noms d'entrée avec
  traversée de chemin — tous rejetés proprement, jamais un item créé) ;
  route de lecture (`can()` refuse un item privé d'un autre tenant,
  autorise un item partagé/publié, 404 sur un `path` absent du zip) ;
  `S3RangeFile` contre un fixture zip réel de test (un seul part multipart
  suffit pour un petit fixture, cf. §4).
- **Vitest** : nouvelle branche `LayerPicker`/`itemClient`
  (`fetchHostedTileset3dSources`), flux d'upload (progression, erreurs
  presign/complete).
- **E2E Playwright** (nouvelle spec ou extension de `map-editor` — décidé à
  l'implémentation selon la taille du flux d'upload) : upload d'un petit
  tileset 3D Tiles synthétique (fixture à créer), apparition dans
  `LayerPicker`, ajout à une carte, sauvegarde, rechargement → la couche
  hébergée est restituée et ses requêtes de tuiles aboutissent (200, pas de
  couche vide).
- **Explicitement hors CI** : performance réelle du proxy core sous charge
  (nombreuses tuiles simultanées d'un vrai tileset ville entière) —
  vérification manuelle ponctuelle avant de considérer l'incrément livré,
  non mesurable de façon fiable en CI. Ne bloque pas la CI ; bloque la
  clôture manuelle de l'incrément dans `CLAUDE.md`.

## 8. Risques

| Risque | Garde-fou |
|---|---|
| Charge core proportionnelle au nombre de tuiles vues (pas de CDN, cf. §1/§3) | Décision assumée pour respecter `can()` ; à réévaluer (cache process, voire bascule vers une architecture à jeton signé façon export SP-17a) seulement si la mesure réelle sur un tileset ville entière le justifie |
| Réouverture de `zipfile.ZipFile` à chaque requête de tuile (§3) | Coût constant (EOCD + table centrale seulement, pas le volume de données) ; documenté comme limite v1, pas un défaut caché |
| Multipart abandonné (job jamais complété) laissant un upload S3 orphelin | Politique de lifecycle S3 sur le bucket dédié (purge des multipart incomplets après N jours) — point opérationnel, pas applicatif |
| Zip valide mais `tileset.json` absent de la racine (nesté dans un sous-dossier, cas réel de certains exports d'outils tiers) | Rejeté explicitement avec message d'erreur clair plutôt qu'une résolution ambiguë « premier trouvé » — periomètre v1 assumé, extension possible plus tard sans changement de modèle |
| Confusion avec le chantier terrain-TiTiler (autre item du même bullet CLAUDE.md, non traité ici) | Non-but explicite §1, aucun chevauchement de code entre les deux (l'un est un module `tileset3d` nouveau, l'autre toucherait le module `titiler`/DEM existant) |
