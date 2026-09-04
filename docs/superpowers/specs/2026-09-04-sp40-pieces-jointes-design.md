# Pièces jointes sur une entité (SP-40)

> Ferme le chantier 4.12 « Pièces jointes sur une entité » (C2)
> (`docs/vision/2026-08-20-revue-projet-et-plan-daction.md`, vague 4, effort
> **L**) : « upload S3 présigné (patron A6), table de liaison tenant-scopée,
> ajout et rendu depuis le widget Formulaire, respect de `can()` et de la RLS
> de collection. Preuve de sortie : une photo attachée depuis le formulaire
> est visible d'un lecteur autorisé et invisible des autres. » Spec
> brainstormée et validée avec Tanguy le 2026-09-04, à la suite de la clôture
> de SP-39 (4.19, notifications in-app).

## 1. Contexte & objectif

Vérifié par lecture directe du code (pas supposé) :

- Aucune notion de pièce jointe n'existe aujourd'hui, ni côté cœur ni côté
  shell.
- Une collection est une vraie table Postgres par collection
  (`core/app/collections/introspection.py`), **pas** une table générique
  `features` — il n'existe donc **aucun `feature_id` unique et typé** qu'une
  table de liaison pourrait référencer par FK Postgres. `_coerce_fid`
  (`features/repository.py:164-171`) coerce le `fid` de l'URL en `int`
  seulement si la colonne PK introspectée est de type `integer`, sinon le
  garde en texte. Conséquence directe pour ce chantier : la table de liaison
  doit référencer `(tenant_id, collection_id, fid)` avec `fid` **toujours
  stocké en texte**, sans FK Postgres vers la table dynamique — l'intégrité
  est gérée côté application, exactement comme `feature_count` est
  incrémenté/décrémenté à la main (`features/routes.py:559-562`,
  `627-633`) plutôt que par trigger.
- Le widget Formulaire (`shell/src/builder/widgets/form.tsx`) construit ses
  champs depuis `CollectionSchema["fields"]`
  (`shell/src/api/types.ts:246-259`, **type TS écrit à la main**, pas
  généré depuis l'OpenAPI — `GET /collections/{id}/schema` n'a pas de
  `response_model` Pydantic, `table_info_to_schema()` retourne un `dict`
  pur). Les 5 types actuels (`boolean`, `integer`/`number`, `date`,
  `datetime`, `text` en repli) sont dans `FieldInput`
  (`form.tsx:233-319`).
- Patron A6 (upload S3 présigné) déjà en place pour l'ingestion
  (`core/app/ingestion/storage.py`, `routes.py:61-146`) : le cœur choisit la
  clé (toujours préfixée `{tenant_id}/…`, jamais fournie par le client),
  génère une URL PUT présignée (`generate_presigned_put_url`, TTL 900 s),
  le navigateur envoie les octets directement à S3/MinIO, puis un endpoint
  de confirmation revalide `key.startswith(f"{tenant_id}/")` avant de
  persister.
- Patron de lecture authentifiée déjà en place pour les fichiers utilisateur
  (`GET /map-icons/{id}/file`, `core/app/mapicons/routes.py:226-269`) :
  proxy qui relit une permission avant de streamer les octets depuis S3,
  `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`.
- `can(session, *, user_id, action, item: AccessFacts, kind, actor_is_admin)`
  (`core/app/sharing/authorization.py:62`) est la porte unique
  d'autorisation ; pour une collection, `get_access_facts(col)`
  (`collections/repository.py:50`) construit les `AccessFacts` à partir de
  la ligne déjà chargée. `_get_writable()`
  (`features/routes.py:509-522`) est le patron exact du garde d'écriture à
  reproduire pour l'upload/la suppression de pièces jointes ;
  `get_readable_collection()` (`collections/routes.py:138`) est le patron
  du garde de lecture (404 avant 403).
- `PATCH /collections/{id}` (`collections/routes.py:408-460`) accepte déjà
  un sous-ensemble de métadonnées de collection (`title`, `description`,
  `isPublic`, `editable`) sous le même garde d'écriture — pas de privilège
  admin dédié. C'est la porte naturelle pour déclarer les champs
  `attachment` d'une collection.

## 2. Décisions actées avec Tanguy (brainstorming)

1. **Lecture en proxy authentifié**, pas en lien presigné GET — le cœur
   relit `can()`/RLS à chaque octet servi, cohérent avec la preuve de sortie
   du chantier (« invisible des autres ») sans dépendre d'un lien à courte
   durée de vie qui pourrait fuiter. Coût assumé : les octets traversent le
   cœur (comme mapicons aujourd'hui).
2. **Champ `attachment` déclaré dans le schéma de collection** (nouveau
   type, aux côtés des 5 existants), pas une simple section
   « Pièces jointes » anonyme sur l'entité — un même champ nommé (ex.
   « Photos », « Documents ») permet plusieurs slots distincts sur une
   même collection.
3. **Plusieurs fichiers par champ** (liste, pas un seul fichier) — usage
   réel visé (plusieurs photos d'un même relevé terrain).
4. **Tout type de fichier accepté** en v1 (documents + images), pas
   seulement des images — cohérent avec le texte générique du chantier
   (« pièces jointes »), validation par liste noire d'extensions
   dangereuses plutôt que liste blanche stricte.
5. **Périmètre élargi au-delà du texte littéral du chantier** (décidé avec
   Tanguy après une première proposition qui les excluait) : la carte
   interrogeable (popup, SP-24) **et** le rendu `/sites/{slug}` (SP-13)
   affichent aussi les pièces jointes de l'entité sélectionnée, et un outil
   MCP en lecture expose leurs métadonnées. Détail en §3.3/§3.4 — cf. §4 pour
   la frontière précise qui reste hors périmètre (écriture via MCP, quotas).

## 3. Périmètre

### 3.1 Cœur — nouveau domaine `core/app/attachments/`

**Modèle de données** (migration Alembic, testée dans les deux sens sur
base non vide — piège n°8) :

- **`attachments`** (patron `MapIcon`, `core/app/mapicons/models.py:14-25`) :
  - `id: str` (PK, uuid hex)
  - `tenant_id: str` (FK `tenants.id`, indexé)
  - `collection_id: str` (FK `collections.id`)
  - `fid: str` — identifiant de l'entité, **toujours texte** (§1) ; pas de
    FK Postgres (table dynamique par collection, cf. §1)
  - `field_key: str` — clé du champ `attachment` déclaré sur la collection
    (§3.1 « Champs déclarés »)
  - `filename: str`
  - `content_type: str`
  - `byte_size: int`
  - `s3_key: str`
  - `created_by: str` (FK `users.id`)
  - `created_at: datetime`
  - Index `(tenant_id, collection_id, fid, field_key)` — c'est la requête
    de liste (une entité, un champ).
- **`Collection.attachment_fields`** — nouvelle colonne
  `Mapped[list] = mapped_column(JSON, default=list, nullable=False)` sur le
  modèle `Collection` existant (`core/app/collections/models.py`), même
  convention `JSON` générique que `extensions.props`/`items.keywords`
  (jamais `JSONB` dans ce dépôt). Forme : `[{"key": str, "label": str}]`.
  Migration ajoute la colonne avec `server_default='[]'` puis la retire en
  `nullable=False` sans défaut serveur permanent (patron déjà suivi pour les
  colonnes booléennes ajoutées après coup sur `Collection`, à vérifier
  contre la dernière migration ayant touché ce modèle).

**Placement dans le contrat de couches**
(`core/pyproject.toml::[[tool.importlinter.contracts]]`, contrainte
`layers`) — **vérifié empiriquement, pas supposé**, la place correcte n'est
pas triviale :

- `app.features` doit pouvoir importer `app.attachments` (suppression en
  cascade des pièces jointes d'une entité depuis `remove_feature`,
  `features/routes.py:614-644`) → `app.attachments` doit être **en dessous**
  de `app.features` dans la liste.
- `app.attachments` doit pouvoir importer `app.collections`
  (`get_readable_collection`, `get_access_facts`), `app.sharing` (`can`,
  `AccessFacts`), `app.auth` (`get_current_user`), `app.audit`
  (`write_audit`) → tous déjà en dessous de `app.features`, donc
  automatiquement en dessous d'`app.attachments` si celui-ci est placé
  juste sous `app.features`. Position retenue : **entre `app.features` et
  `app.collections`**.
- **Point non trivial** : `app.attachments` doit aussi réutiliser
  `get_s3_client`/`make_s3_client` du patron A6
  (`app.ingestion.routes`/`app.ingestion.storage`). Or `app.ingestion` est
  **au-dessus** d'`app.features` dans la liste actuelle (position ~17 contre
  ~21) — c'est-à-dire au-dessus de la position retenue pour
  `app.attachments`. Les cinq modules qui réutilisent aujourd'hui
  `from app.ingestion.routes import get_s3_client` verbatim (`export`,
  `appexport`, `tileset3d`, `terrain3d`, `mapicons`) sont **tous** placés
  au-dessus d'`app.ingestion` — vérifié par lecture des cinq fichiers, pas
  une coïncidence : c'est la seule position qui autorise cet import sans
  exemption. `app.attachments`, contraint sous `app.features` (donc sous
  `app.ingestion`), serait le **premier** module consommateur de S3 sous
  cette ligne. Deux options :
  1. Dupliquer un `get_s3_client` propre à `app.attachments` (stub qui lève
     `RuntimeError`, overridé indépendamment dans `main.py` avec le même
     `make_s3_client(...)`) — aucune exemption de contrat nécessaire, mais
     rompt la convention « même clé d'override, un seul override enregistré
     dans `main.py` » suivie par les cinq modules existants (commentaire
     explicite à ce sujet dans `main.py`, `app.export.routes réutilise
     ingestion_routes.get_s3_client verbatim`).
  2. **Retenu** : une entrée nommée dans `ignore_imports`
     (`core/pyproject.toml`), exactement le mécanisme déjà utilisé deux fois
     dans ce contrat pour un problème structurellement identique
     (`app.analytics.aggregate -> app.collections.introspection`,
     `app.auth.routes -> app.roles...`) : `"app.attachments.routes ->
     app.ingestion.routes"`, commentée pour expliquer pourquoi la place
     linéaire ne suffit pas ici (le graphe réel n'est pas un ordre total :
     `app.attachments` a besoin d'être à la fois sous `app.features` et au
     niveau de `app.ingestion`). Choisi pour préserver la convention
     « un seul override » plutôt que la dupliquer une sixième fois.

**API** (`core/app/attachments/routes.py`, montée sous le préfixe des
entités, `/collections/{collection_id}/items/{fid}/attachments…`, routeur
inclus dans `main.py` juste après `features_routes.router`) :

- `POST /collections/{id}/items/{fid}/attachments/presign` — body
  `{field_key, filename, content_type}` ; garde d'écriture identique à
  `_get_writable()` (`can(write, collection)` + `col.editable`) ; **valide
  `field_key` contre `Collection.attachment_fields`** (400 si le champ
  n'est pas déclaré) ; clé S3 `{tenant_id}/{collection_id}/{fid}/{uuid4().hex}-{filename}`
  (patron ingestion, toujours choisie par le cœur).
- `POST /collections/{id}/items/{fid}/attachments` — confirme l'upload :
  revalide le préfixe de la clé (patron `POST /uploads`), fait un
  `head_object` S3 pour lire la taille réelle, **rejette et supprime
  l'objet si > 25 Mo** (constante `MAX_ATTACHMENT_BYTES`, seul plafond posé
  en v1 — pas de quota tenant, cf. §5), persiste la ligne, `write_audit`
  (`action="attachment.create"`).
- `GET /collections/{id}/items/{fid}/attachments?field_key=` — liste
  (métadonnées seules, pas les octets), garde de lecture
  `get_readable_collection()`, **`user=Depends(get_current_user_optional)`**
  (patron `features/routes.py:188,247,494` / `collections/routes.py:265,344,389`
  — les routes de lecture publiques supportent déjà l'anonyme, nécessaire ici
  pour §3.4 : un visiteur non connecté de `/sites/{slug}` doit pouvoir lister
  les pièces jointes d'une collection publique).
- `GET /collections/{id}/items/{fid}/attachments/{attachment_id}/file` —
  proxy-read (patron `GET /map-icons/{id}/file` verbatim : `Cache-Control:
  private, max-age=3600`, `X-Content-Type-Options: nosniff`,
  `Content-Disposition: attachment; filename="…"`), même garde de lecture
  optionnelle que la liste ci-dessus.
- `DELETE /collections/{id}/items/{fid}/attachments/{attachment_id}` —
  garde d'écriture, supprime la ligne + l'objet S3 (best-effort sur
  l'objet, comme `mapicons` — un `ClientError` sur `delete_object` est
  logué et avalé, pas remonté en 500), `write_audit`
  (`action="attachment.delete"`).

**Déclaration des champs `attachment` d'une collection** — `CollectionPatch`
(`collections/schemas.py:54-58`) gagne `attachmentFields:
list[AttachmentFieldSpec] | None = None` (`{key, label}`), même garde
d'écriture que le reste du PATCH (pas de privilège admin dédié — aligné sur
`title`/`editable`, pas sur `admin.collections.manage`). `GET
/collections/{id}/schema` (`collections/routes.py:386-405`) fusionne
`col.attachment_fields` dans la réponse : `table_info_to_schema(info,
attachment_fields=col.attachment_fields)` (signature étendue,
`schema_json.py` reste pur — pas d'accès DB, la liste est passée par
l'appelant qui a déjà `col` en scope), ajoutant une entrée `{"name": key,
"type": "attachment", "required": false, "label": label}` par champ
déclaré.

**Cascade de suppression** — `remove_feature`
(`features/routes.py:614-644`) appelle
`attachments_repo.delete_all_for_feature(session, s3_client, bucket,
tenant_id=col.tenant_id, collection_id=col.id, fid=fid)` dans la même
requête, juste après avoir confirmé la suppression de la ligne (`ok` vrai) et
avant le `write_audit` de fin de fonction — supprime toutes les lignes
`attachments` **et** leurs objets S3 (best-effort sur S3, comme la
suppression individuelle) pour ce `(collection_id, fid)`.

### 3.2 Shell

- `ItemClient` (`shell/src/api/itemClient.ts`) : `presignAttachmentUpload`,
  `confirmAttachmentUpload`, `listAttachments`, `deleteAttachment` +
  `attachmentFileUrl(collectionId, fid, attachmentId)` (construit l'URL du
  proxy-read, consommée directement en `src=`/`href=`, pas de méthode
  `fetch` dédiée). Types `AttachmentSummary`.
- `CollectionSchemaField["type"]` (`shell/src/api/types.ts:244`, **type
  écrit à la main**, pas régénéré) gagne `"attachment"` dans l'union ; pas
  de régénération OpenAPI/TS pour cette partie précise (la route `/schema`
  n'a pas de `response_model` côté cœur) — seules les 5 nouvelles routes
  CRUD d'`app.attachments` régénèrent `core/openapi.json` +
  `core-schema.d.ts` (piège n°1).
- `FieldInput` (`shell/src/builder/widgets/form.tsx:233-319`) gagne une
  branche `field.type === "attachment"` : liste des fichiers déjà attachés
  (nom, taille, lien de téléchargement via `attachmentFileUrl`, bouton
  Supprimer), ajout multiple (input file `multiple`, presign → PUT direct
  → confirm, par fichier). **Champ désactivé tant que l'entité n'a pas de
  `fid` réel** (création non enregistrée) — même patron que `pk !== null`
  déjà utilisé partout ailleurs dans ce dépôt pour gater un panneau
  dépendant d'un id persisté (SP-30d/f/g/h) ; pas de mécanisme d'upload
  différé pré-création.
- `EditCollectionPanel.tsx` (`shell/src/shell/EditCollectionPanel.tsx`)
  gagne un éditeur de liste `attachmentFields` (clé + libellé, ajout/
  suppression de lignes), soumis dans le même `updateCollection.mutateAsync`
  que les 4 champs existants.

### 3.3 MCP — un outil en lecture seule

Précédent vérifié (pas supposé) : les ~9 outils MCP existants
(`core/app/mcp/tools.py`, `@server.tool()` sur `register_tools`) sont tous
des fonctions Pydantic-typées, authentifiées par un flux OAuth 2.1+PKCE
**dédié à `/mcp`** (`CORE_MCP_AUDIENCE`, distinct de l'audience OIDC du
shell), et **aucun ne retourne ni n'accepte de contenu binaire** — le seul
précédent pour « exposer un fichier » est côté REST
(`ItemRead.thumbnailUrl`, une URL relative que l'appelant refetch
séparément), pas côté MCP.

- **Nouveau tool `list_attachments(collection_id: str, fid: str, field_key:
  str | None = None) -> list[AttachmentSummary]`** (`mcp/tools.py`) —
  lecture seule, réutilise `_require_collection_read` (même garde que les
  tools `list_items`/`explain_dataset` existants). Chaque
  `AttachmentSummary` porte `filename`, `contentType`, `byteSize`,
  `fieldKey`, et **`fileUrl: str`** — l'URL relative du proxy-read
  (§3.1), sur le patron `ItemRead.thumbnailUrl` : le tool ne transporte
  jamais les octets eux-mêmes, seulement de quoi les récupérer séparément.
- **Pas de tool d'upload ni de suppression via MCP** — décision délibérée,
  pas un oubli : un upload binaire n'a pas de forme naturelle dans un appel
  d'outil JSON-RPC (il faudrait du base64 dans un paramètre, sans précédent
  dans ce module et disproportionné pour ce chantier), et le principe déjà
  établi de l'allowlist copilote (`copilot/tools_allowlist.py`, « exclut
  délibérément les tools mutants ») pousse dans le même sens : lecture
  seule ici.
- **Pas d'ajout à `ALLOWED_MCP_TOOL_NAMES`** (`copilot/tools_allowlist.py`)
  — le copilote du builder (SP-20) est scopé aux 6 tools existants pour la
  génération d'apps/formulaires ; `list_attachments` reste disponible à
  tout client MCP générique (Claude Desktop, etc. connecté en OAuth) mais
  n'est pas offert au copilote in-app dans cette v1. Ajout possible plus
  tard sans migration si un besoin réel apparaît.

### 3.4 Popup carte (SP-24) et site public (`/sites/{slug}`, SP-13)

**`PopupConfig`** (`shell/src/api/types.ts:157-165`) gagne un champ optionnel
`attachmentField?: string` — la clé d'un champ `attachment` déclaré sur la
collection (§3.1). Absent = comportement actuel inchangé (aucune section
pièces jointes).

- **`MapPopup.tsx`** : quand `config.attachmentField` est renseigné et que
  la propriété PK de l'entité cliquée est connue (déjà le cas — c'est ce
  qui identifie la ligne cliquée), une nouvelle section « Pièces jointes »
  s'ajoute sous le contenu existant (`<dl>`/gabarit) : un fetch
  `GET .../attachments?field_key=X` déclenché à l'ouverture du popup (pas au
  chargement de la couche — les pièces jointes ne voyagent jamais dans le
  payload MVT/GeoJSON), rendu en liste nom+lien de téléchargement
  (`attachmentFileUrl`, §3.2). État de chargement bref, section absente si
  la liste est vide (pas de « Aucune pièce jointe » bruyant).
- **`PopupEditor.tsx`** : nouveau sélecteur « Pièces jointes » listant les
  champs de type `attachment` de la collection (déjà distingués dans
  `CollectionSchema` par `type: "attachment"`, §3.1) — absent si la
  collection n'en déclare aucun.
- **`DatasetPage.tsx`** (`/sites/{slug}`, `previewConfig` synthétisé
  §exploration : titre/description, boutons de téléchargement, un widget
  carte + un widget table sur un même `dataset-preview`) — **aucune
  configuration de popup n'existe aujourd'hui sur ce widget synthétisé**
  (comportement par défaut : toutes les colonnes). `previewConfig` est
  étendu pour dériver `PopupConfig.attachmentField` du premier champ
  `attachment` trouvé dans `GET /collections/{id}/schema`, si la collection
  en déclare un — automatique, sans réglage supplémentaire côté
  propriétaire du dataset. Passe par le même `MapPopup`/`attachmentField`
  que ci-dessus, donc par la même route proxy-read en lecture optionnelle
  (§3.1) : un visiteur anonyme d'un site public voit les pièces jointes
  d'une collection publique, exactement comme il voit déjà ses entités.

### 3.5 CLAUDE.md

Ligne `### Livré` datée SP-40 à la clôture, comme SP-38/SP-39 ; 4.12 retiré
de toute liste de suivi informelle si elle y apparaît.

## 4. Hors périmètre, explicitement

- **Upload/suppression de pièces jointes via MCP** — §3.3 : un seul tool en
  lecture (`list_attachments`), aucune mutation possible par ce canal.
- **`list_attachments` dans l'allowlist copilote** (`ALLOWED_MCP_TOOL_NAMES`)
  — reste un tool MCP générique, pas offert au copilote in-app de SP-20
  dans cette v1 (§3.3).
- **Édition/upload de pièces jointes depuis `/sites/{slug}`** — le site
  public ne fait qu'**afficher** les pièces jointes existantes (§3.4),
  jamais en ajouter ni en supprimer ; seul le widget Formulaire (dans un
  contexte authentifié avec droit d'écriture) le permet.
- **Quotas de stockage tenant** (chantier 4.22, séparé) — seul un plafond
  fixe par fichier (25 Mo) est posé, pas de comptage d'usage tenant, pas de
  refus au-delà d'un volume total.
- **Vignettes/redimensionnement d'images** — le fichier est servi tel quel
  par le proxy-read, aucune génération de miniature (contrairement à
  `S3_THUMBNAILS_BUCKET`, réservé aux miniatures d'items).
- **Réassainissement de contenu** (SVG, etc.) — contrairement à mapicons,
  aucune validation de structure du fichier au-delà de la taille et d'une
  liste noire d'extensions dangereuses à l'upload ; les octets ne sont pas
  ré-interprétés côté serveur.
- **Upload différé pré-création d'entité** — champ désactivé tant que
  l'entité n'existe pas encore (§3.2).
- **Purge automatique** — pas de rétention/expiration en v1.

## 5. Tests

1. **Cœur** (`core/tests/test_attachments_*.py`, nouveau module) :
   - Migration testée dans les deux sens sur base non vide.
   - Presign : garde d'écriture (403 sans droit write/collection non
     éditable), 400 si `field_key` non déclaré sur la collection.
   - Confirm : revalidation du préfixe de clé (même test que
     `POST /uploads`, cross-tenant), rejet + suppression de l'objet S3 si
     `head_object` dépasse `MAX_ATTACHMENT_BYTES`.
   - Liste : isolation tenant + collection + `field_key`, ordre.
   - **Preuve de sortie littérale du chantier** : une pièce jointe créée
     par un utilisateur avec droit d'écriture est visible en lecture par un
     second utilisateur du même tenant avec droit de lecture, et retourne
     404 pour un utilisateur d'un autre tenant (proxy-read).
   - Suppression individuelle : ligne + objet S3 supprimés, `write_audit`
     appelé, 403 sans droit d'écriture.
   - **Cascade** : `DELETE /collections/{id}/items/{fid}` supprime aussi
     toutes les pièces jointes de ce `fid` (lignes + objets S3) — test
     dédié, pas seulement une lecture du code.
   - `PATCH /collections/{id}` avec `attachmentFields` : round-trip complet
     (déclarer un champ, le relire via `GET /collections/{id}/schema`,
     confirmer l'entrée `type: "attachment"`).
   - Lecture anonyme (`get_current_user_optional`) : liste + proxy-read
     accessibles sans authentification sur une collection publique,
     refusés (401/404 selon la garde) sur une collection privée.
   - Contrat de couches (`uv run lint-imports`) : l'entrée `ignore_imports`
     ajoutée est bien la SEULE arête qui échouerait sans elle (vérifié en
     la retirant temporairement et en observant l'échec attendu, pas
     supposé).
   - `list_attachments` (MCP) : retourne les bonnes métadonnées + `fileUrl`
     pour une collection lisible, lève sur une collection hors périmètre de
     l'acteur (même garde que `list_items`) ; absent d'`ALLOWED_MCP_TOOL_NAMES`
     (test négatif explicite, pour ne pas le voir apparaître par accident
     dans le copilote à la faveur d'un futur refactor).
2. **Shell — Vitest** :
   - `form.tsx` / `FieldInput` : rendu de la liste existante, ajout
     multi-fichiers (mock presign/PUT/confirm), suppression, champ
     désactivé sans `fid`.
   - `EditCollectionPanel` : ajout/suppression de lignes `attachmentFields`,
     soumission dans le payload PATCH.
   - `MapPopup` : section « Pièces jointes » rendue quand
     `attachmentField` est configuré et la liste non vide, absente sinon ;
     `PopupEditor` : le sélecteur ne propose que les champs `type:
     "attachment"`.
   - `DatasetPage`/`previewConfig` : `attachmentField` dérivé du schéma
     quand la collection en déclare un, absent sinon.
3. **E2E** : au moins deux specs bout en bout nouveaux —
   `shell/e2e/attachments.spec.ts` (preuve de sortie littérale du chantier,
   deux comptes réels via mock OIDC : une pièce jointe créée par l'un est
   visible en lecture par l'autre et invisible d'un troisième hors partage)
   et `shell/e2e/attachments-popup-site.spec.ts` (clic sur une entité dans
   l'éditeur de carte **et** sur `/sites/{slug}` révèle sa pièce jointe,
   accès anonyme vérifié sur le second). Un test E2E à deux/trois sessions
   couvre une différence de visibilité entre acteurs mieux que
   Vitest+pytest isolément.
4. `npm run test`, `uv run pytest`, `npm run e2e` verts ; couverture shell
   non régressée (seuil 88, mesurée après nettoyage de `dist/`/
   `dist-export/`), couverture cœur non régressée (seuil 85).
5. **Régénération OpenAPI/types TS obligatoire** (piège n°1) pour les 5
   routes `app.attachments` (pas pour l'extension de `/schema`, cf. §3.2) ;
   le nouveau tool MCP n'ajoute rien à `core/openapi.json` (FastMCP dérive
   son propre schéma des types Python, hors du pipeline OpenAPI REST) mais
   doit apparaître dans un `tools/list` réel contre un serveur MCP démarré
   en local, pas seulement supposé depuis le code.
6. **Contrôle manuel recommandé, non bloquant** (comme SP-38/SP-39) : si une
   stack `docker compose up -d` est disponible, déclarer un champ
   `attachment` sur une collection réelle, attacher une photo depuis le
   widget Formulaire, vérifier son ouverture par un second compte lecteur,
   son invisibilité pour un compte hors partage, son apparition dans le
   popup de l'éditeur de carte et sur `/sites/{slug}` en visiteur anonyme
   (collection publiée), et une réponse `list_attachments` correcte via un
   client MCP réel.

## 6. Critères de sortie

1. Une photo attachée depuis le widget Formulaire est visible d'un lecteur
   autorisé et invisible des autres (preuve de sortie littérale du
   chantier 4.12), vérifié par un test E2E à deux comptes.
2. Un champ `attachment` se déclare sur une collection (`PATCH
   /collections/{id}`) et apparaît dans `GET /collections/{id}/schema`,
   consommé sans code de routage dupliqué par le widget Formulaire.
3. Plusieurs fichiers, de tout type, s'attachent à un même champ d'une même
   entité ; chacun supprimable individuellement.
4. Supprimer une entité supprime ses pièces jointes (lignes + objets S3).
5. Cliquer une entité dotée d'un champ `attachment` configuré en popup
   révèle ses pièces jointes, dans l'éditeur de carte **et** sur
   `/sites/{slug}` (y compris pour un visiteur anonyme sur une collection
   publiée).
6. Un client MCP générique liste les pièces jointes d'une entité via
   `list_attachments` ; le tool n'apparaît pas dans le copilote in-app.
7. Aucune régression sur le contrat de couches (`lint-imports`), l'entrée
   d'exemption ajoutée est justifiée et minimale (une seule arête nommée).
8. Suites cœur et shell vertes, OpenAPI/types régénérés pour les 5 nouvelles
   routes REST, CLAUDE.md à jour (entrée `### Livré` SP-40).

## 7. Risques et limites connues

- **Intégrité `(collection_id, fid)` sans FK Postgres** — assumé (§1), même
  posture que `feature_count` déjà aujourd'hui ; un `fid` typo à l'upload
  crée une ligne orpheline invisible côté UI (jamais requêtée avec ce
  `fid`), sans risque de sécurité (toujours tenant-scopée et gate-write).
- **Exemption de contrat de couches** — une arête nommée de plus dans
  `ignore_imports` (§3.1), le 3e cas de ce genre dans ce dépôt après
  `app.analytics`/`app.auth`. À surveiller si un futur module rencontre le
  même problème structurel une 4e fois : pourrait signaler que la position
  d'`app.ingestion` dans le contrat mérite d'être repensée plutôt que
  d'accumuler des exemptions.
- **Plafond de taille fixe (25 Mo), pas de quota tenant** — croissance non
  bornée du bucket `S3_ATTACHMENTS_BUCKET` en v1, comme `S3_MAPICONS_BUCKET`
  aujourd'hui ; le chantier 4.22 (quotas) est le point de reprise naturel.
- **Best-effort sur la suppression S3** — un objet peut survivre à la
  suppression de sa ligne (erreur réseau/MinIO) sans que l'opération
  échoue, même posture que mapicons.
- **Aucune miniature** — afficher une galerie de photos dans le formulaire
  charge les fichiers pleine résolution ; acceptable en v1, à revisiter si
  l'usage réel (photos de relevé terrain, potentiellement volumineuses)
  le justifie.
- **Un fetch réseau supplémentaire par ouverture de popup** dès qu'un champ
  `attachmentField` est configuré (§3.4) — les pièces jointes ne voyagent
  jamais dans le payload MVT/GeoJSON de la couche, donc pas de moyen de les
  pré-charger ; latence perçue à l'ouverture du popup, jamais mesurée dans
  ce chantier, à surveiller si le volume de pièces jointes par entité
  grandit.
- **Lecture anonyme du proxy-read sur collection publique** — cohérent avec
  le reste de `/sites/{slug}` (les entités elles-mêmes sont déjà publiques),
  mais élargit la surface anonyme du cœur d'une route de plus ; aucun rate
  limiting spécifique aux pièces jointes au-delà du limiteur générique déjà
  en place (SP-26).
- **Le tool MCP `list_attachments` n'a pas de garde de débit dédiée** —
  même posture que les tools MCP existants (aucun n'en a), pas une lacune
  propre à ce chantier.
