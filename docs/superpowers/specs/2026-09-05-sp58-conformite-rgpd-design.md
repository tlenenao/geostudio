# SP-58 — Conformité : quotas par tenant & droit à l'effacement (RGPD)

**Date** : 2026-09-05
**Statut** : spec, prête à devenir un plan
**Demandeur** : Tanguy (explicitement, hors ordre suggéré par la feuille de
route)
**Documents liés** : `docs/revue/2026-09-04-analyse-gaps.md` (GAP-73, GAP-74,
GAP-11), `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` (chantier
4.22), `docs/vision/2026-09-04-feuille-de-route-revisee.md` (ligne SP-58,
§4.1), `docs/vision/2026-07-04-comparatif-projet-actuel-vs-vision.md` (Q2,
lignes 463-465).

---

## 0. Priorité conditionnelle — à lire avant tout le reste

**Ce chantier n'est pas dans le « déjà tranché ».** La feuille de route
révisée le dit explicitement : *« Pertinent dès qu'un tenant réel autre que
l'opérateur est onboardé — voir Q2 au §3 »*
(`docs/vision/2026-09-04-feuille-de-route-revisee.md:87`). Et le §4.1 du même
document est encore plus net : *« Une réponse concrète [à Q2] changerait
directement la priorité relative de […] SP-58 (quotas/RGPD — urgent
seulement si un tenant externe réel est onboardé) »*
(`docs/vision/2026-09-04-feuille-de-route-revisee.md:146-154`).

Q2 (« Premiers utilisateurs réels ») reste une question produit **ouverte**
depuis le 2026-07-04 (`docs/vision/2026-07-04-comparatif-projet-actuel-vs-
vision.md:543-545` : « Q2 — premiers utilisateurs réels […] restent
ouvertes »). Tant qu'elle n'a pas de réponse, GeoStudio n'a — à la
connaissance de ce document — **aucun tenant réel autre que l'opérateur**
(cf. Q9 déjà tranchée : « Pas de besoin immédiat [de multi-tenant], mais
`tenant_id` dès le jour 1 »). Un chantier de conformité RGPD dimensionné pour
un opérateur qui gère ses propres données n'a pas la même urgence qu'un
chantier dimensionné pour héberger les données d'un tiers.

**Cette spec et le plan qu'elle produit sont écrits intégralement** — la
demande de Tanguy est explicite et ne dépend pas de la réponse à Q2 — mais
toute décision de **priorité relative** entre SP-58 et les autres chantiers
de la feuille de route doit rester suspendue à cette question produit. Ne
pas lire l'existence de ce document comme une réévaluation de la priorité de
SP-58 dans la feuille de route.

---

## 1. Contexte : ce que le code fait déjà, ce qu'il ne fait pas

### 1.1 GAP-73/GAP-11 — quotas par tenant (chantier 4.22)

`docs/revue/2026-09-04-analyse-gaps.md:227` (GAP-73, Sérieux, coût 5-8j) :
*« Absence totale de quotas par tenant — aucune limite de stockage, de
nombre de collections/items, ni d'upload (une plateforme qui accepte des
tilesets 3D de plusieurs Go sans aucun plafond). Seuls des rate-limits **par
route coûteuse** existent (sql/llm/jobs/harvest, `_BUDGETS` dans
`limiter.py`), pas un quota de ressources globales par tenant. »* GAP-11
(`docs/revue/2026-09-04-analyse-gaps.md:55`) est le même manque, cité côté
plan d'action pour le rattachement au chantier 4.22
(`docs/vision/2026-08-20-revue-projet-et-plan-daction.md:432` : *« Quotas et
usage (L2) — aucun quota, aucune statistique d'usage, pour une plateforme
qui accepte des uploads de tilesets 3D de plusieurs Go. Preuve de sortie :
Un tenant qui dépasse son quota de stockage voit son upload refusé avec un
message clair. »*).

Vérifié directement dans le code (`core/app/ratelimit/limiter.py:29-34`) :
`_BUDGETS = {"sql": 10, "llm": 20, "jobs": 15, "harvest": 10}` — un compteur
glissant par **(clé d'appelant = en-tête Authorization brut, groupe de
route)**, en mémoire process, aucune notion de tenant ni de ressource
cumulée (stockage, nombre d'items). `grep -rn "quota" core/app` renvoie zéro
résultat hors ce document. Il n'existe **aucune** colonne de taille de
fichier en octets nulle part dans le schéma sauf `attachments.byte_size`
(`core/app/attachments/models.py:49`) — chaque autre module qui écrit du
binaire dans S3 (uploads GeoJSON/CSV/GPKG/Shapefile, tilesets 3D, terrain
raster-dem, rendus d'export, bundles d'app autoportés, miniatures d'item)
ignore la taille de ce qu'il vient d'écrire.

### 1.2 GAP-74 — droit à l'effacement (aucun mécanisme)

`docs/revue/2026-09-04-analyse-gaps.md:228` (GAP-74, Sérieux — conformité,
pertinent dès qu'un utilisateur européen réel est onboardé, coût 5-10j) :
*« Aucun mécanisme de purge des données ni de droit à l'effacement —
supprimer un item cascade sa config/révisions/partages (SP-1/SP-40 pour les
pièces jointes), mais il n'existe aucune fonctionnalité dédiée « effacer
toutes les données d'un utilisateur/tenant » au sens RGPD. »*

Vérifié : `grep -rn "purge\|right_to_erasure\|rgpd" core/app` (hors faux
positifs) est vide, confirmé indépendamment pendant cette recherche. Ce que
la cascade existante couvre réellement (`core/app/configs/routes.py:78-88`,
`_delete_config_and_item`) :

```python
def _delete_config_and_item(session, config_id, item_id, tenant_id):
    session.execute(delete(ConfigRevision).where(ConfigRevision.config_id == config_id))
    session.execute(delete(Config).where(Config.id == config_id))
    session.execute(delete(ItemShare).where(ItemShare.item_id == item_id))
    session.execute(delete(Item).where(Item.id == item_id, Item.tenant_id == tenant_id))
```

— un seul item à la fois, jamais « tout ce qui appartient à cet
utilisateur/tenant ». Et symétriquement, `unregister_collection`
(`core/app/collections/routes.py:577-624`) supprime une seule collection
(purge des pièces jointes S3 + ligne, retrait de la publication CDC,
`repo.delete_collection`) mais refuse l'opération (409) si un `Dataset`/
`Pipeline` la référence encore (`_require_no_reverse_references`-like garde,
`find_referencing_config_kinds`) — une garde correcte pour une suppression
isolée, mais qui **bloquerait** une purge complète si on l'appelait
telle-quelle sur chaque collection d'un tenant dans un ordre arbitraire.

Il n'existe :
- **aucune route `DELETE /users/{id}`** — vérifié (`grep -rn "\"/users"
  core/app`) : seules `GET /users` et `PATCH /users/{id}` existent
  (`core/app/auth/routes.py:114,131`), et il n'y a **pas de fichier**
  `core/app/users/routes.py` du tout (seulement `models.py`/`repository.py`).
- **aucune route de suppression de tenant** — `grep -rn "delete_tenant\|
  /tenants" core/app` (hors modèle) est vide.
- **aucun concept d'administrateur cross-tenant.** Chaque `User`
  appartient à exactly un tenant (`core/app/users/models.py:21`,
  `tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"),
  nullable=False)`) ; les seuls traitements cross-tenant du dépôt sont des
  balayages cron internes sans identité utilisateur (`configs/repository.py:
  92`, `pipelines/repository.py:120`, `reports/repository.py:90,99` — tous
  commentés « cross-tenant », aucun n'est déclenché par une requête HTTP
  authentifiée). **Conséquence directe pour le design (§3.3)** : ce chantier
  ne peut pas s'appuyer sur un rôle « super-admin » qui n'existe pas — toute
  action de conformité doit être déclenchée par un utilisateur du tenant
  concerné, via un privilège existant ou nouveau, jamais par un acteur
  extérieur au tenant.

### 1.3 L'obstacle réel à la suppression d'un utilisateur : 16 clés étrangères sans cascade

Recherche exhaustive (`grep -rn 'ForeignKey("users.id"' core/app`, hors
tests) : **16 sites** référencent `users.id`, **aucun avec `ondelete=`** :

`items.owner_id`, `groups.created_by`, `group_members.user_id`,
`collections.owner_id`, `mapicons.created_by`, `secrets.created_by`,
`extensions.owner_id`, `ingestion_jobs.created_by`, `harvest_sources.owner_id`,
`app_export_jobs.user_id`, `notifications.recipient_user_id`,
`notification_read.user_id`, `terrain3d_jobs.created_by`,
`export_jobs.user_id`, `tileset3d_jobs.created_by`, `attachments.created_by`.

**`DELETE FROM users WHERE id = ...` échouerait en `IntegrityError` dès que
n'importe laquelle de ces 16 tables porte une ligne pour cet utilisateur** —
ce qui est systématiquement le cas pour tout utilisateur ayant jamais créé
un item, une collection, un groupe, ou reçu une notification. Une
suppression physique de la ligne `users` n'est donc **pas une option
praticable** sans une migration lourde qui ajouterait `ondelete=CASCADE`/
`SET NULL` sur 16 colonnes réparties sur 13 modules — un chantier dont le
risque (cf. CLAUDE.md, piège n°8 : tester toute migration sur base non vide)
dépasse largement ce que « le droit à l'effacement d'une personne » exige
réellement.

**Le droit à l'effacement RGPD (Art. 17) porte sur les données à caractère
personnel d'une personne, pas sur l'intégrité référentielle du système qui
la référence.** L'approche retenue par cette spec (détaillée §3.2) est donc
l'**anonymisation en place** : les colonnes identifiantes de la ligne
`users` (username, email, prénom, nom, `oidc_sub`) sont écrasées ; la ligne
elle-même — et tout ce qui la référence par FK (items possédés, collections,
groupes créés…) — subsiste, attribuée à un compte anonymisé. C'est le même
choix que fait, par construction, l'`audit_log` du dépôt : `actor_id` y est
une **chaîne libre, sans contrainte FK** (`core/app/audit/models.py:20`,
`actor_id: Mapped[str | None] = mapped_column(String, nullable=True)`) —
conçu dès l'origine pour survivre à la disparition de l'acteur qu'il
désigne.

### 1.4 Clés S3 : deux schémas différents, qui déterminent comment mesurer le stockage

Recherche des points de génération de clé S3 (`grep -n "key = f\""` sur les
6 modules qui écrivent du binaire) :

| Bucket (env var, `core/app/main.py`) | Schéma de clé | Préfixé par `tenant_id` ? |
|---|---|---|
| `S3_UPLOADS_BUCKET` (ingestion) | `core/app/ingestion/routes.py:71` : `f"{user.tenant_id}/{uuid4().hex}-{filename}"` | Oui |
| `S3_ATTACHMENTS_BUCKET` | `core/app/attachments/routes.py:186` : `f"{col.tenant_id}/{collection_id}/{fid}/{uuid4().hex}-{filename}"` | Oui |
| `S3_TILESET3D_BUCKET` | `core/app/tileset3d/routes.py:112` : `f"{user.tenant_id}/{uuid4().hex}/{filename}"` | Oui |
| `S3_TERRAIN3D_BUCKET` | `core/app/terrain3d/routes.py:64` : `f"{user.tenant_id}/{uuid4().hex}/{filename}"` | Oui |
| `S3_EXPORTS_BUCKET` (rendus PDF/PNG) | `core/app/export/jobs.py:194` : `f"renders/{job_id}.{format}"` | **Non** |
| `S3_APPEXPORTS_BUCKET` | `core/app/appexport/jobs.py:127` : `f"appexports/{job_id}.zip"` | **Non** |
| `S3_THUMBNAILS_BUCKET` | miniature d'item, une par item (`core/app/items/repository.py:377`) | (non vérifié, hors périmètre — cf. §2) |

Conséquence directe pour la mesure de stockage (détaillée §3.1) : **il
n'existe pas une seule méthode uniforme.** Les 4 premiers buckets peuvent
être mesurés par tenant via `ListObjectsV2(Prefix=f"{tenant_id}/")` sans
toucher au schéma. Les 2 buckets de sortie de job (`exports`, `appexports`)
ne peuvent **pas** être mesurés ainsi — leurs clés portent un `job_id`, pas
un `tenant_id` — et nécessitent une colonne `byte_size` nouvelle sur
`ExportJob`/`AppExportJob` (aucune des deux n'en a une aujourd'hui, vérifié
directement dans `core/app/export/models.py` et `core/app/appexport/
models.py`), renseignée au moment où le job termine (le worker sait déjà la
taille du fichier qu'il vient d'écrire).

### 1.5 Patron déjà écrit à réutiliser : upload en deux temps + vérification post-upload

`core/app/attachments/routes.py:212-222` (`confirm_attachment`) illustre
déjà le patron nécessaire à l'application d'un plafond de taille
**après** un upload S3 direct (le cœur ne voit jamais le flux de l'upload
lui-même, seulement l'URL présignée puis la confirmation) :

```python
head = s3.head_object(Bucket=bucket, Key=body.key)
size = head["ContentLength"]
if size > MAX_ATTACHMENT_BYTES:
    s3.delete_object(Bucket=bucket, Key=body.key)  # best-effort
    raise HTTPException(status_code=400, detail="fichier trop volumineux...")
```

`core/app/tileset3d/routes.py:167` (`complete_tileset3d_upload`),
`core/app/terrain3d/routes.py:74` (`create_terrain3d_upload`) et
`core/app/ingestion/routes.py:105` (`create_upload_job`) sont les points
« confirmation post-upload » équivalents pour les 3 autres buckets
tenant-préfixés — chacun est appelé par le shell **après** que l'upload S3
direct a réussi, donc c'est là (et seulement là) que la taille réelle est
connue côté cœur. C'est le point d'application naturel du quota de
stockage, par le même mécanisme que le plafond par fichier déjà en place
sur les pièces jointes — à vérifier précisément à l'exécution du plan
lequel de ces 3 points appelle déjà `head_object`/connaît déjà la taille
avant cette spec (ne pas supposer, cf. CLAUDE.md piège n°3).

### 1.6 Capacités instance-wide : le patron à suivre pour tout nouveau flag

`core/app/auth/dependency.py:41-72` établit un patron répété 5 fois
(`is_etl_enabled`, `is_export_enabled`, `is_appexport_enabled`,
`is_tileset3d_enabled`, `is_terrain3d_enabled`) : une fonction qui lit
`os.environ.get("CORE_X_ENABLED", "false").lower() == "true"` **à chaque
appel, sans cache** (pour que les tests basculent par `monkeypatch` sans
recréer l'app), défaut toujours `false`. Le même flag est ensuite exposé
côté profil par `MeCapabilities` (`core/app/auth/routes.py:30-47`) — un
doublon **délibéré** avec `GET /instance` (route publique, page de
connexion), les deux gardés synchronisés par
`core/tests/test_auth_me_capabilities.py`. Toute nouvelle capacité
instance-wide de cette spec (quotas) doit suivre ce patron à l'identique :
nouveau champ `MeCapabilities.quotasEnabled`, même champ côté `GET
/instance`, même test de parité étendu.

### 1.7 Privilèges : catalogue à 18, mécanisme d'ajout

`core/app/roles/privileges.py:5-23` : 18 valeurs de l'enum `Privilege`,
chacune accompagnée d'une entrée `PRIVILEGE_METADATA` (domaine shell +
clé i18n, `core/app/roles/repository.py:151`) consommée par `GET /roles/
{id}` pour construire dynamiquement le catalogue affiché par
`RolesAdminPage`. `Privilege.SETTINGS_INSTANCE_MANAGE` existe déjà
(`"settings.instance.manage"`) et gate aujourd'hui la passerelle
`/admin-tools/*` (SP-32, `core/app/admin_tools/routes.py:48`) — c'est le
privilège le plus proche, par sa nature (« action instance-wide,
dangereuse, rarement utilisée »), des actions de conformité de cette spec ;
voir §3.3/§3.4 pour la décision retenue par tenant.

---

## 2. Périmètre

### 2.1 Dans le périmètre

- **Quotas et usage (GAP-73/GAP-11)** :
  1. Compteurs par tenant : nombre d'items, de collections, d'utilisateurs
     (mesure exacte à la demande, `COUNT(*) WHERE tenant_id = ...` — aucune
     table de ledger nécessaire, ces comptages sont bon marché).
  2. Stockage par tenant : octets cumulés sur les 4 buckets tenant-préfixés
     (mesure S3 à la demande, `ListObjectsV2` + somme) + octets cumulés des
     2 buckets de sortie de job via une nouvelle colonne `byte_size`
     (`ExportJob`, `AppExportJob`).
  3. Une vue d'usage consultable par un admin du tenant (`GET /admin/usage`
     ou équivalent).
  4. Une capacité instance-wide `CORE_QUOTAS_ENABLED` + des limites
     configurables (env vars, valeurs uniques appliquées identiquement à
     tout tenant — cf. §3.1 pour la justification de ce choix restreint).
  5. Application du quota aux points de création réels (refus explicite,
     message clair, cf. preuve de sortie du chantier 4.22).
- **Droit à l'effacement (GAP-74)**, en deux opérations distinctes (cf.
  §1.3) :
  1. **Anonymisation d'un utilisateur** — soi-même (« supprimer mon
     compte ») ou par un admin du tenant sur un autre utilisateur. Écrase
     les champs identifiants de `User`, supprime ses notifications, le
     retire de ses groupes. Ne supprime **aucune** ligne référencée par une
     autre table (items, collections, pièces jointes qu'il a créés
     survivent, attribués au compte anonymisé).
  2. **Purge complète d'un tenant** — action distincte, plus destructive,
     déclenchée par un utilisateur du tenant lui-même (cf. §1.2, aucun
     acteur cross-tenant n'existe) muni d'un privilège dédié, avec
     confirmation explicite (taper le slug du tenant). Supprime
     physiquement toutes les lignes du tenant, toutes les tables
     dynamiques de collection, tous les objets S3, puis le tenant
     lui-même — irréversible.
  3. Une preuve d'effacement conservée **hors** du périmètre du tenant
     purgé (table sans FK vers `tenants`, comptages agrégés uniquement,
     aucune donnée personnelle) — répond à l'obligation de pouvoir
     démontrer qu'un effacement a eu lieu sans re-stocker ce qui vient
     d'être effacé.

### 2.2 Hors périmètre (explicite)

- **Un concept d'administrateur cross-tenant.** Cette spec ne l'introduit
  pas (cf. §1.2) — la purge d'un tenant reste une action que ce tenant
  déclenche sur lui-même. Un vrai opérateur multi-tenant qui voudrait
  purger un tenant tiers sans coopération de celui-ci resterait hors
  périmètre — architecture différente, à ouvrir séparément si Q2 y
  conduit un jour.
- **Ajouter `ondelete=CASCADE`/`SET NULL` sur les 16 FK vers `users.id`.**
  Explicitement écarté par le choix d'anonymisation en place (§1.3) — un
  chantier de cette ampleur (13 modules, migration à risque) n'est pas
  justifié par le besoin réel (effacer les données personnelles, pas les
  lignes qui les référencent).
- **Des quotas par tenant configurables individuellement** (tenant A a
  100 Go, tenant B a 10 Go). Cf. §3.1 — une seule limite instance-wide,
  parce qu'aucun acteur ne peut aujourd'hui régler un quota différent par
  tenant sans le concept écarté ci-dessus.
- **La mesure du bucket `S3_THUMBNAILS_BUCKET`** dans le quota de
  stockage — une miniature par item, taille bornée par construction (image
  compressée, pas de multi-Go), ce n'est pas le risque que GAP-73 cite
  (« tilesets 3D de plusieurs Go ») ; son omission est un choix de
  périmètre explicite, pas un oubli.
- **La portabilité des données** (RGPD Art. 20, « export de toutes mes
  données dans un format structuré ») — GAP-74 ne la cite pas, ce n'est pas
  dans le périmètre retenu par la feuille de route pour SP-58. Suivi
  distinct si un besoin réel apparaît.
- **Toute politique de rétention automatique** (purge après N jours
  d'inactivité, expiration programmée) — cette spec construit le mécanisme
  déclenché à la demande, pas une politique de cycle de vie.
- **L'exposition de ces fonctionnalités par MCP.** Une purge de tenant ou
  une anonymisation d'utilisateur ne doit **jamais** être un outil MCP
  allowlisté (SP-20) — action trop destructrice pour un chemin piloté par
  un LLM, même avec confirmation ; ni le quota d'usage en lecture (aucun
  besoin identifié). Décision explicite, à ne pas rouvrir sans arbitrage
  produit séparé.

---

## 3. Design

### 3.1 Quotas et usage

**Pourquoi une seule limite instance-wide plutôt que par tenant** : régler
un quota différent par tenant supposerait un acteur habilité à le faire
pour un tenant qui n'est pas le sien — ce rôle n'existe pas (§1.2). Tant
que cette limite structurelle n'est pas levée par un futur chantier, la
seule forme praticable est : l'opérateur qui exploite l'instance (via ses
variables d'environnement, au déploiement) fixe une limite unique,
appliquée identiquement à tout tenant qui tourne sur cette instance. Un
admin d'un tenant donné ne *règle* rien, il *consulte* sa propre
consommation face à cette limite commune.

**Nouveau module `core/app/quotas/`** :

- `service.py` :
  - `count_items_for_tenant(session, tenant_id) -> int`
  - `count_collections_for_tenant(session, tenant_id) -> int`
  - `count_users_for_tenant(session, tenant_id) -> int`
  - `tenant_prefixed_storage_bytes(s3, bucket, tenant_id) -> int` —
    pagine `list_objects_v2(Bucket=bucket, Prefix=f"{tenant_id}/")`, somme
    `Size`. Appelée pour les 4 buckets du tableau §1.4.
  - `job_output_storage_bytes(session, tenant_id) -> int` — `SELECT
    COALESCE(SUM(byte_size), 0)` sur `ExportJob` et `AppExportJob` filtré
    `tenant_id`, sommés.
  - `usage_for_tenant(session, s3, tenant_id) -> UsageSnapshot` — agrège
    tout ce qui précède. Coût réel : au moins 4 appels S3 paginés par
    calcul — **pas un chemin à appeler sur chaque requête chaude** (cf.
    §3.1.1, mise en cache).
  - `check_quota_or_raise(...)` — comparé aux limites lues depuis
    l'environnement, lève une erreur RFC 7807 (patron SP-26 déjà en place
    pour les erreurs du cœur) avec un message actionnable (« quota de
    stockage du tenant dépassé : X/Y octets ») si dépassement.
- `routes.py` : `GET /admin/usage` — renvoie `UsageSnapshot` du tenant de
  l'appelant. Gardé par `Privilege.SETTINGS_INSTANCE_MANAGE` (§1.7 : c'est
  le privilège le plus proche par nature ; décision à confirmer en séance
  de plan si un privilège dédié `admin.quotas.view` paraît préférable —
  cf. §6).
- Migration (prochain numéro constaté à l'écriture : `0035`, **à vérifier
  au moment de l'exécution** — `ls core/alembic/versions | sort | tail`,
  ne pas supposer) : ajoute `export_jobs.byte_size` et
  `app_export_jobs.byte_size` (`Integer`, nullable — les lignes
  historiques restent `NULL`, traitées comme 0 dans la somme ; limitation
  assumée et à documenter explicitement : les jobs d'export antérieurs à
  cette migration ne compteront jamais dans le quota, seuls les nouveaux
  jobs après déploiement).
- Population de `byte_size` : `core/app/export/jobs.py` et
  `core/app/appexport/jobs.py`, au moment où le job connaît déjà la taille
  du fichier qu'il vient d'écrire sur S3 (`head_object` après upload, ou
  taille du buffer avant upload si déjà en mémoire — à vérifier au code
  réel de chaque job avant d'écrire le correctif, ne pas deviner).

**3.1.1 Coût de la mesure de stockage — pourquoi ne pas la calculer à
chaque requête d'upload** : un `ListObjectsV2` paginé sur 4 buckets à
chaque tentative d'upload serait un aller-retour S3 coûteux sur un chemin
déjà critique. Deux options pour l'exécution du plan à trancher (§6, pas
tranché ici) :
  a) Calculer à la demande, uniquement au moment de la confirmation
     d'upload (§1.5) — un seul calcul par upload réel, pas par requête de
     lecture. Coût acceptable si le nombre d'uploads reste faible (cas
     réaliste pour un opérateur unique aujourd'hui).
  b) Maintenir un compteur incrémental (ligne d'usage mise à jour à chaque
     écriture/suppression, patron `feature_count`-like) — plus rapide à
     lire, mais touche autant de sites d'écriture que de buckets
     (risque de dérive documenté ailleurs dans ce dépôt pour tout
     compteur dupliqué, cf. CLAUDE.md piège n°4/n°11) et exige un
     mécanisme de réconciliation périodique pour rattraper toute
     dérive (crash entre l'écriture S3 et la mise à jour du compteur).
  Recommandation de cette spec : **(a)**, plus simple et suffisant pour le
  volume réel attendu tant que Q2 reste sans réponse ; documenter le choix
  explicitement dans le code (comme les autres decisions de coût de ce
  dépôt) plutôt que de laisser deviner un futur lecteur.

**3.1.2 Points d'application du quota** (comptages) :
  - Création d'item (`POST /configs`, `core/app/configs/routes.py`,
    fonction `create_config`) : vérifier `count_items_for_tenant(...) <
    limite` avant l'insertion.
  - Création de collection (`POST /collections/empty`,
    `core/app/collections/routes.py`) : même garde sur
    `count_collections_for_tenant`.
  Ces deux points sont à confirmer précisément par lecture du code au
  moment du plan (noms de fonction, signatures exactes) — non copiés
  verbatim ici pour éviter l'erreur documentée par CLAUDE.md piège n°3
  (« le texte littéral d'un plan est régulièrement faux sur les interfaces
  réelles »).

**3.1.3 Erreur retournée** : suivre le format RFC 7807 déjà en place
(SP-26) plutôt qu'un nouveau format ad hoc — un dépassement de quota est un
409 (conflit avec une contrainte métier, pas une requête malformée ni un
throttling temporaire comme le 429 du rate limiter existant) avec un
`type`/`title` dédiés (`urn:geostudio:quota-exceeded` ou équivalent, format
exact à confirmer sur le générateur d'erreurs RFC 7807 existant).

### 3.2 Anonymisation d'un utilisateur

**Nouveau module** (ou extension d'`app/users/`, à trancher au plan —
`app/users/` n'a aujourd'hui aucune route, cf. §1.2 ; toute nouvelle route
utilisateur vit soit là, soit dans un module `app/compliance/` dédié aux
deux opérations de cette section — cf. §6).

Fonction `anonymize_user(session, *, tenant_id, user_id)` :
1. Vérifie que l'utilisateur appartient au tenant de l'appelant (jamais
   d'anonymisation cross-tenant).
2. Écrase, sur la ligne `User` :
   - `username` → `f"utilisateur-efface-{user_id[:8]}"`
   - `email` → `None`
   - `first_name`/`last_name` → `""`
   - `oidc_sub` → un placeholder garanti unique (`f"erased:{uuid4()}"`) —
     **respecte la contrainte `uq_users_tenant_oidc_sub`**
     (`core/app/users/models.py:18`) sans jamais pouvoir entrer en
     collision avec un vrai `sub` OIDC (préfixe `erased:` impossible à
     produire par Keycloak). Effet de bord assumé et documenté
     explicitement : la personne qui se reconnecte ensuite avec son vrai
     `sub` OIDC ne retrouve **pas** son ancien compte (le `sub` a changé) —
     `get_or_create_user` (`core/app/users/repository.py`, à vérifier
     nommément) lui crée un compte neuf, sans historique. C'est l'effet
     recherché par un droit à l'effacement, pas un bug à corriger.
   - `erased_at` → horodatage (nouvelle colonne, migration additive sur
     `User`, cf. §3.4 pour le regroupement de migrations) — sert à
     l'idempotence (un second appel sur un compte déjà anonymisé est un
     404/409 explicite, pas une double écriture silencieuse) et à
     l'affichage admin (« compte effacé le … »).
3. Supprime les lignes qui référencent l'utilisateur **par leur nature
   strictement personnelle**, pas par nécessité d'intégrité : toutes les
   `Notification` où `recipient_user_id = user_id`
   (`core/app/notifications/models.py:33`, FK sans cascade — sans cette
   suppression explicite, aucun problème d'intégrité immédiat puisqu'on ne
   supprime pas la ligne `User`, mais les notifications resteraient
   adressées à un compte anonymisé sans aucune valeur), et retire
   l'utilisateur de tout `GroupMember` (`core/app/sharing/models.py:24-30`,
   clé primaire composite, suppression triviale).
4. Ce qui **survit intact**, par choix explicite (§2.1) : `items.owner_id`,
   `collections.owner_id`, `attachments.created_by`, tout job qu'il a
   lancé — attribués au compte anonymisé, visibles comme tels par
   quiconque consultait déjà ces objets (aucune fuite nouvelle : ces
   objets étaient déjà visibles avant l'anonymisation, seul le nom de leur
   auteur change).

**Route** : `POST /compliance/users/{user_id}/erase` (nom à confirmer au
plan). Deux cas d'appel :
  - `user_id == "me"` ou l'id du user courant : aucun privilège
    supplémentaire requis au-delà de l'authentification — chacun peut
    effacer son propre compte.
  - Un autre `user_id` du même tenant : requiert `Privilege.
    ADMIN_USERS_MANAGE` (déjà utilisé par `UsersAdminPage`, cf. CLAUDE.md
    entrée SP-38) — pas de nouveau privilège nécessaire pour ce cas,
    contrairement à la purge de tenant (§3.3).

**Audit** : `write_audit(action="user.erase", object_type="user",
object_id=user_id, payload={})` — jamais l'ancien username/email dans le
payload (l'audit_log ne doit pas devenir lui-même une fuite de la donnée
qu'on vient d'effacer).

### 3.3 Purge complète d'un tenant

**Fonction `purge_tenant(session, s3, *, tenant_id)` dans un nouveau
module `core/app/compliance/`.** Contrairement à `_delete_config_and_item`
et `unregister_collection` (§1.2), qui protègent contre les références
orphelines *parce qu'il reste d'autres données dans le tenant après leur
appel*, une purge complète n'a pas ce problème : **tout** disparaît dans le
même passage, donc l'ordre n'a besoin de respecter que les contraintes FK
(enfant avant parent), jamais les gardes métier « encore référencé par »
(qui existent pour protéger un tenant partiel, pas un tenant qu'on vide
entièrement).

Ordre proposé (enfant avant parent sur chaque FK, à vérifier et ajuster
précisément à l'exécution — le graphe de FK réel doit être relu au moment
d'écrire le code, cette liste est un point de départ argumenté, pas une
liste garantie complète) :

1. Pour chaque item du tenant (toutes les 9 kinds), delete
   `ConfigRevision` → `Config` → `ItemShare` → `Item` (même corps que
   `_delete_config_and_item`, mais appelé pour **tous** les items du
   tenant, sans passer par la garde `_require_no_reverse_references`).
2. Pour chaque collection du tenant : `remove_table_from_publication` (CDC,
   patron déjà existant) puis `DROP TABLE` de la table dynamique de
   collection (fonction déjà utilisée par `repo.delete_collection`),
   sans passer par la garde `find_referencing_config_kinds` (déjà retirée
   à l'étape 1).
3. Supprime les objets S3 : `ListObjectsV2(Prefix=f"{tenant_id}/")` +
   `delete_objects` en lot sur les 4 buckets tenant-préfixés (§1.4) ; pour
   les 2 buckets de sortie de job, itère les `result_key` des lignes
   `ExportJob`/`AppExportJob` du tenant et les supprime individuellement
   (pas de préfixe commun disponible, §1.4).
4. Supprime les lignes des tables suivantes, filtrées `tenant_id` (ordre
   FK-safe à confirmer précisément à l'exécution, une par une) :
   `attachments`, `export_jobs`, `app_export_jobs`, `tileset3d_jobs`,
   `terrain3d_jobs`, `ingestion_jobs`, `notifications`,
   `notification_read`, `secrets`, `harvest_sources` (+ tables filles),
   `mapicons`, `extensions`, `group_members`, `groups`.
5. Supprime les `User` du tenant (désormais safe : les 16 FK de §1.3 ont
   toutes été vidées par les étapes précédentes pour ce tenant).
6. Supprime les `Role` du tenant (les 4 rôles prédéfinis **sont
   tenant-scopés**, cf. CLAUDE.md SP-31 : « 4 rôles prédéfinis immuables
   par tenant » — donc à supprimer aussi, après les `User` qui les
   référencent par `role_id` NOT NULL).
7. Supprime les lignes `audit_log` du tenant (`core/app/audit/models.py:19`,
   FK vers `tenants.id` sans `ondelete=` — la ligne `tenants` ne pourra
   pas être supprimée tant que des lignes `audit_log` la référencent).
8. Écrit une ligne dans une nouvelle table `purge_receipts`
   (**volontairement sans FK vers `tenants`** — sinon elle disparaîtrait
   avec le reste, ce qui viderait la preuve d'effacement elle-même) :
   `id`, `tenant_slug` (texte brut, snapshot — le tenant n'existe plus
   ensuite), `requested_by_user_id` (texte brut, snapshot), `requested_at`,
   `completed_at`, `counts` (JSON : nombre de lignes supprimées par table,
   octets S3 libérés — **jamais** de contenu, seulement des comptages).
   C'est la preuve exigible qu'un effacement a eu lieu, sans réintroduire
   la donnée personnelle qu'on vient d'effacer.
9. Supprime la ligne `Tenant` elle-même.

**Caractère asynchrone** : un tenant réel peut porter un volume de données
significatif (collections à des dizaines de milliers de lignes, tilesets
de plusieurs Go). Cette purge doit tourner en job `procrastinate` (patron
déjà en place pour tout traitement long — `queue="etl"` ou une nouvelle
queue dédiée, à trancher au plan), pas en ligne dans la requête HTTP qui la
déclenche. La route ne fait que créer le job et retourner son id ;
l'utilisateur consulte l'avancement comme pour les autres jobs du dépôt
(patron `GET /uploads/{job_id}` déjà répété 4 fois).

**Confirmation** : la route de déclenchement exige que le corps de la
requête répète le **slug** du tenant (`{"confirmSlug": "mon-tenant"}`) —
patron déjà utilisé ailleurs dans ce type de produit pour une action
irréversible, à écrire côté shell comme un champ de saisie obligatoire
avant d'activer le bouton, jamais une simple case à cocher.

**Privilège** : nouveau `Privilege.COMPLIANCE_MANAGE` (`"compliance.
manage"`), 19e valeur de l'enum (§1.7) — décision de cette spec, **à
confirmer par Tanguy au moment du plan** (§6) : réutiliser
`SETTINGS_INSTANCE_MANAGE` réduirait le nombre de privilèges mais mêlerait
« configurer l'instance » (relance de service martin/titiler, faible
risque de perte de données) et « effacer irréversiblement toutes les
données d'un tenant » (risque maximal) sous un seul geste d'attribution de
rôle — cette spec recommande la séparation, mais ce n'est pas un fait du
code, c'est un jugement produit.

**Rôle prédéfini concerné** : par défaut, aucun des 4 rôles prédéfinis
(Administrateur/Créateur/Analyste/Lecteur, cf. CLAUDE.md SP-31) ne devrait
porter `compliance.manage` automatiquement — même l'Administrateur, qui
porte déjà la totalité des privilèges "admin.*", ne l'a pas nécessairement
par défaut (cf. §6, à trancher explicitement, ne pas le glisser
silencieusement dans `BUILT_IN_ROLE_PRIVILEGES["administrateur"]` sans
décision consciente compte tenu de son caractère irréversible).

### 3.4 Migrations regroupées

Au moins 3 changements de schéma additifs, à regrouper en une ou plusieurs
migrations selon la convention du dépôt (numérotation à vérifier à
l'exécution, `0035` et suivants à confirmer) :
- `export_jobs.byte_size` (Integer, nullable) — §3.1.
- `app_export_jobs.byte_size` (Integer, nullable) — §3.1.
- `users.erased_at` (DateTime, nullable) — §3.2.
- Nouvelle table `purge_receipts` (§3.3) — sans FK vers `tenants`,
  volontairement.

Chaque migration testée dans les deux sens sur base non vide (CLAUDE.md
piège n°8), et vérifiée par le comparateur modèle↔Alembic si SP-43 l'a
livré avant l'exécution de ce plan (`core/tests/test_model_alembic_
parity.py` — à vérifier qu'il existe : cf. commentaires trouvés dans
`core/app/items/models.py`/`core/app/configs/routes.py` pendant cette
recherche, qui indiquent que SP-43 a déjà tourné sur ce dépôt au moment de
l'écriture de cette spec).

---

## 4. Nouveau schéma (résumé)

| Table/colonne | Nature | Rationale |
|---|---|---|
| `export_jobs.byte_size` | colonne additive nullable | §3.1, mesure de stockage sur bucket non tenant-préfixé |
| `app_export_jobs.byte_size` | colonne additive nullable | idem |
| `users.erased_at` | colonne additive nullable | §3.2, idempotence + affichage admin |
| `purge_receipts` | nouvelle table, sans FK vers `tenants` | §3.3, preuve d'effacement qui doit survivre à la disparition du tenant |
| `Privilege.COMPLIANCE_MANAGE` | nouvelle valeur d'enum (pas une table) | §3.3, geste distinct de `SETTINGS_INSTANCE_MANAGE` |

---

## 5. Risques

- **Ordre de suppression de la purge de tenant faux ou incomplet** :
  risque le plus élevé de cette spec. Contre-mesure recommandée au plan
  (§6) : un test caractéristique unique qui crée une ligne dans **chaque**
  table qui porte `tenant_id` (script qui énumère les modèles via
  `Base.registry.mappers` plutôt qu'une liste recopiée à la main — même
  piège que §1.2 de la spec SP-43 sur `toFrontLayer()`, ne pas répéter la
  même erreur ici), appelle `purge_tenant`, et vérifie qu'aucune ligne ne
  subsiste nulle part pour ce tenant — le filet qui aurait immédiatement
  signalé un site oublié.
- **Anonymisation partielle si une future table ajoute une colonne
  personnelle sur `User`** (ex. un futur champ téléphone) sans que
  `anonymize_user` soit mis à jour : même classe de défaut que
  `toFrontLayer()` (SP-43 §1.2) — un filet qui échoue à la compilation si
  un champ personnel est ajouté sans être couvert serait la protection
  correcte, pas une liste de champs recopiée à la main.
- **Confusion entre anonymisation et purge** côté shell/UI : les deux
  actions doivent être visuellement et textuellement très distinctes
  (l'une réversible dans son effet limité — un compte reste vide, mais le
  tenant continue de fonctionner ; l'autre efface tout un tenant,
  irréversible) — un bouton mal libellé qui déclenche l'un en croyant
  déclencher l'autre serait le pire résultat possible de ce chantier.
- **Quota de stockage jamais recalculé après une purge/suppression**
  (dérive à la baisse jamais vue si le calcul n'est fait qu'à l'écriture) :
  atténué par le choix de calcul à la demande (§3.1.1 option a) plutôt
  qu'un compteur incrémental — la mesure recalculée à chaque upload est
  toujours exacte, elle ne peut pas dériver.
- **Le job de purge crashe à mi-chemin** (panne réseau S3, redémarrage du
  worker) : le tenant se retrouve dans un état partiellement purgé,
  potentiellement invisible (plus d'items mais tenant encore présent, ou
  pire, disparu de moitié). Le plan doit rendre `purge_tenant` idempotent
  et rejouable (chaque étape testable pour « déjà fait, rien à refaire »)
  plutôt que de supposer une exécution atomique de bout en bout sur un
  volume potentiellement important — une seule transaction Postgres sur
  un DROP TABLE + des milliers de suppressions S3 n'est de toute façon pas
  réaliste (les appels S3 ne sont pas transactionnels avec Postgres).
- **`CORE_QUOTAS_ENABLED` non câblé dans `docker-compose.yml`/
  `.env.example`/`core/tests/test_deployability.py`** — piège CLAUDE.md
  n°2, déjà responsable de 5 occurrences dans ce dépôt. Toute nouvelle
  variable d'environnement de cette spec doit être ajoutée aux trois
  endroits avant de considérer la tâche close.
- **Priorité mal jugée par une session future** qui lirait « SP-58 livré »
  dans CLAUDE.md sans relire §0 de cette spec : rappeler explicitement,
  dans l'entrée `### Livré` qui clôturera ce plan, que la priorité
  *relative* de ce chantier reste conditionnée à Q2 — livrer le code ne
  tranche pas la question produit.

---

## 6. Ce que cette spec ne tranche pas

- Le privilège exact qui garde `GET /admin/usage` (`SETTINGS_INSTANCE_
  MANAGE` réutilisé, ou un nouveau `admin.quotas.view` plus fin) — §3.1.
- Le nom exact du nouveau privilège de purge (`compliance.manage` proposé,
  §3.3) et **si l'Administrateur prédéfini le porte par défaut** — décision
  produit à prendre consciemment, pas à hériter silencieusement.
- Le choix entre calcul de stockage à la demande vs compteur incrémental
  (§3.1.1) — recommandation donnée, pas imposée.
- Le nom et l'emplacement exacts des nouvelles routes (`/compliance/*` vs
  extension d'`app/users/`) et des fichiers shell (nouvelle page admin
  « Conformité » vs extension d'`UsersAdminPage`/panneau dédié dans le
  domaine `admin` déjà défini par `shell/src/auth/capabilities.ts`).
- La valeur par défaut des limites de quota (nombre d'items/collections,
  octets de stockage) — aucune donnée réelle d'usage n'existe aujourd'hui
  pour la calibrer ; le plan doit proposer une valeur de repli
  documentée comme arbitraire (ex. 10 Go, 1000 items) plutôt que de
  prétendre qu'elle est mesurée.
- La reformulation ou non de la question Q2 elle-même — hors périmètre
  total de ce document (cf. §0).
