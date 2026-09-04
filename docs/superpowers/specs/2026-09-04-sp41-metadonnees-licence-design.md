# SP-41 — Métadonnées éditables et licence par jeu (chantier 4.9, B1+B2)

Date : 2026-09-04. Ferme le chantier 4.9 de la vague 4
(`docs/vision/2026-08-20-revue-projet-et-plan-daction.md` §7, constats B1+B2,
rang 5 du classement de valeur produit).

## Contexte et périmètre

**B1** — Le modèle `Item` n'a presque aucune métadonnée (`title`, `abstract`,
`keywords`, `thumbnail_key`, `is_published`, `is_public`). Manquent : licence,
producteur, contact, fréquence de mise à jour, généalogie, langue, version.

**B2** — Conséquence directe : `dcat/serializers.py:61` émet
`"dct:license": {"@id": LICENSE_OTHER}` — la même licence codée en dur pour
tous les jeux —, `dct:language` figé à `"fr"` sur tout le catalogue, et
`dct:publisher` réduit au nom du tenant. `stac/serializers.py:65` émet
`"license": "other"` en dur. Un auteur ne peut déclarer aucune licence :
l'export DCAT-AP est structurellement valide et fonctionnellement vide pour
l'open data (moissonnage data.gouv.fr / European Data Portal impossible à
distinguer d'un jeu sans licence).

**Vérifié avant d'écrire ce document** : DCAT-AP et STAC sérialisent tous les
deux le modèle `Collection` (`core/app/collections/models.py`), pas l'`Item`
générique — `core/app/dcat/routes.py::_dataset_doc` et
`core/app/stac/routes.py` opèrent sur des `Collection`, jamais sur un `Item`
de type `dataset`/`map`/etc. Le texte du §7 parle d'« Item » de façon
imprécise ; ce plan porte donc le gros des nouveaux champs sur `Collection`
(§1), avec un sous-ensemble volontairement réduit (licence + langue) sur
l'`Item` générique pour enrichir l'affichage catalogue de tout type de
document (décision produit, cf. §1.2).

**Décision produit actée avec Tanguy** : périmètre étendu à l'`Item`
générique (pas seulement `Collection`), sous-ensemble limité à
licence + langue (pas producteur/contact/fréquence/généalogie/version, qui
n'ont de sens que sur une `Collection` publiable en open data).

**Hors périmètre explicite** :
- L'emprise spatiale n'est **pas** un champ à ajouter : elle est déjà calculée
  dynamiquement depuis la géométrie (`app/stac/extent.py::estimated_bbox_4326`,
  consommé par DCAT et STAC). Le B1 du §7 la liste comme manquante sur `Item`
  générique, ce qui est vrai mais sans conséquence : `Item` n'est jamais
  sérialisé en DCAT/STAC.
- Facettes de recherche catalogue sur ces nouveaux champs (chantier 4.7,
  distinct).
- Un outil MCP `describe_collection` exposant ces métadonnées — aucun outil de
  ce type n'existe aujourd'hui, pas de régression à couvrir.
- Validation stricte de format (URI, email) — saisie best-effort, pas de
  blocage niveau schéma au-delà des types de base.
- Toute modification du modèle de licence STAC/DCAT au-delà des deux exports
  déjà existants (pas de nouvel export CSW/CKAN à adapter : les connecteurs
  SP-12 sont des *consommateurs* de sources externes, pas des producteurs de
  ce catalogue).

## 1. Modèle de données

### 1.1 `Collection` (`core/app/collections/models.py`)

Neuf nouvelles colonnes, toutes nullable ou avec défaut — aucune donnée
existante n'est retouchée par la migration :

| Colonne | Type | Défaut | Note |
|---|---|---|---|
| `license` | `String \| None` | `None` | id du catalogue curaté §2.1 |
| `license_uri` | `String \| None` | `None` | utilisé seulement si `license == "other"` |
| `producer` | `String \| None` | `None` | texte libre ; vide ⇒ repli sur `tenant.name` |
| `contact` | `String \| None` | `None` | texte libre (email ou nom) |
| `update_frequency` | `String \| None` | `None` | id du catalogue curaté §2.2 |
| `lineage` | `String \| None` | `None` | texte libre (généalogie/provenance) |
| `language` | `String` | `"fr"` | id du catalogue curaté §2.3, jamais null |
| `version` | `String \| None` | `None` | texte libre |
| `temporal_start` | `Date \| None` | `None` | déclaration manuelle, pas de calcul |
| `temporal_end` | `Date \| None` | `None` | déclaration manuelle, pas de calcul |

`temporal_start`/`temporal_end` sont une déclaration manuelle simple (pas un
calcul sur une colonne de données de la collection) : le concept de « champ
temporel » calculé existe déjà ailleurs (contexte temps global A29, animation
4.17) mais à un niveau différent (une colonne de la table de données, pas un
attribut de la `Collection` elle-même) — ne pas confondre les deux, ne pas
tenter de les unifier dans ce plan.

### 1.2 `Item` (`core/app/items/models.py`, `core/app/items/schemas.py`)

Deux nouvelles colonnes, même catalogues que `Collection` :

| Colonne | Type | Défaut |
|---|---|---|
| `license` | `String \| None` | `None` |
| `language` | `String` | `"fr"` |

`ItemRead` gagne `license: str | None = None` et `language: str = "fr"`.
`ItemUpdatePatch` gagne `license: str | None = None` et
`language: str | None = None` (patron identique aux champs existants).

### 1.3 Migration Alembic

Une seule migration, testée dans les deux sens (`upgrade` puis `downgrade`)
sur une base Postgres réellement non vide (piège n°8 CLAUDE.md) — patron
`sp40`/`sp39` : construire une base jetable séparée du conteneur
`postgis-test` partagé (qui n'a pas de `alembic_version`, cf. notes SP-39),
insérer un tenant + une collection + un item réels avant `upgrade head`,
vérifier `downgrade -1` puis `upgrade head` de nouveau.

## 2. Catalogues curatés

Nouveau module `core/app/collections/metadata_catalog.py`, listes figées en
code (patron palettes SP-25 / icônes curatées SP-27 : pas de table SQL, pas de
gestion CRUD, juste une constante versionnée avec le code). Partagé entre
`Collection` et `Item` — un seul module, pas de duplication.

Exposé en lecture par une nouvelle route **top-level** `GET /metadata-catalog`
(pas sous `/collections/`, puisque partagé par `Collection` et `Item` —
inconditionnelle, comme les 6 routes `/notifications*` de SP-39 : aucune
capacité à gater, c'est un catalogue statique) plutôt que dupliqué en
constante TS : source de vérité unique, le shell ne peut pas dériver.

### 2.1 Licences

| id | Libellé | URI DCAT-AP (authority table ou référence externe) | id SPDX (STAC) |
|---|---|---|---|
| `etalab-2.0` | Licence Ouverte / Open Licence 2.0 (Etalab) | `https://spdx.org/licenses/etalab-2.0.html` | `etalab-2.0` |
| `cc0-1.0` | CC0 1.0 Universal | `http://publications.europa.eu/resource/authority/licence/CC0` | `CC0-1.0` |
| `cc-by-4.0` | Creative Commons Attribution 4.0 | `http://publications.europa.eu/resource/authority/licence/CC_BY` | `CC-BY-4.0` |
| `cc-by-sa-4.0` | Creative Commons Attribution-ShareAlike 4.0 | `http://publications.europa.eu/resource/authority/licence/CC_BY_SA` | `CC-BY-SA-4.0` |
| `odbl-1.0` | Open Database License 1.0 | `https://spdx.org/licenses/ODbL-1.0.html` | `ODbL-1.0` |
| `proprietary` | Propriétaire (aucune réutilisation) | `http://publications.europa.eu/resource/authority/access-right/NON_PUBLIC` (via `dct:accessRights`, pas `dct:license` — cf. note ci-dessous) | `proprietary` |
| `other` | Autre (URI à saisir) | valeur de `license_uri` | `other` |

Note d'implémentation à vérifier avant de coder (piège n°3, ne pas faire
confiance à la table écrite ici de mémoire) : la table d'autorité UE des
licences (`http://publications.europa.eu/resource/authority/licence/`) n'a
pas d'entrée dédiée pour Etalab — l'URI SPDX (`spdx.org`) est le choix
pragmatique déjà pratiqué par plusieurs catalogues DCAT-AP français faute de
mieux. `proprietary` n'a pas de licence DCAT-AP à proprement parler : émettre
`dct:license` avec l'URI `LICENSE_OTHER` existante (comportement actuel) et
ne rien changer côté `dct:accessRights` (déjà géré indépendamment par
`is_public`).

### 2.2 Fréquences de mise à jour (`dct:accrualPeriodicity`, MDR-FREQ)

`irregular`, `daily`, `weekly`, `monthly`, `quarterly`, `annual`,
`continuous`, `unknown` (valeur par défaut si non renseigné — mais absent de
l'export, cf. §3, pas émis avec la valeur `unknown`).

URI MDR-FREQ à vérifier contre la table réelle avant de coder (ex.
`http://publications.europa.eu/resource/authority/frequency/DAILY`) — piège
n°3.

### 2.3 Langues (`dct:language`)

`fr`, `en`, `de`, `es`, `it` — mappées vers les codes alpha-3 majuscules de la
table d'autorité UE (`FRA`, `ENG`, `DEU`, `SPA`, `ITA`) pour DCAT. STAC n'a
aucun champ langue : pas d'impact sur `stac/serializers.py`.

## 3. Export DCAT-AP (`core/app/dcat/serializers.py`)

Tout nouveau champ est **omis de la sortie s'il n'est pas renseigné** —
comportement actuel préservé à l'identique pour toute collection qui ne
touche pas ce nouveau formulaire (critère de sortie testé explicitement,
§7).

- `dct:license` : résolu depuis le catalogue si `license` est renseigné (URI
  DCAT-AP de §2.1, ou `license_uri` si `license == "other"`) ; sinon
  `LICENSE_OTHER` (inchangé).
- `dct:language` : par `Collection` au lieu d'une constante — le catalogue
  racine (`catalog()`) garde `"fr"` (c'est un choix de langue de l'instance,
  pas d'un jeu), chaque `dataset()` porte sa propre langue résolue.
- `dct:publisher` : `producer` si renseigné, sinon `tenant.name` (comportement
  actuel).
- `dct:accrualPeriodicity` : nouveau, `{"@id": <URI MDR-FREQ>}`, omis si
  `update_frequency` absent.
- `dct:provenance` : nouveau, `{"@type": "dct:ProvenanceStatement", "rdfs:label": lineage}`
  (ajoute le préfixe `rdfs` au `CONTEXT`), omis si `lineage` absent.
- `dcat:contactPoint` : nouveau, omis si `contact` absent ; heuristique simple
  — si la valeur contient `@`, `{"@type": "vcard:Kind", "vcard:hasEmail": "mailto:" + contact}`,
  sinon `{"@type": "vcard:Kind", "vcard:fn": contact}` (ajoute le préfixe
  `vcard` au `CONTEXT`).
- `dct:temporal` : `dcat:startDate`/`dcat:endDate` depuis `temporal_start`/
  `temporal_end` si renseignés (les deux ou aucun — si un seul est renseigné,
  utiliser celui-là seul, ne pas inventer l'autre) ; sinon repli actuel
  (`dcat:startDate = created_at`, pas de fin).
- `dct:hasVersion` : nouveau, texte libre, omis si `version` absent.

## 4. Export STAC (`core/app/stac/serializers.py`)

- `license` : id SPDX résolu depuis le catalogue (§2.1) si `license`
  renseigné, sinon `"other"` (inchangé).
- `providers` : nouveau tableau `[{"name": producer ou tenant.name, "roles": ["producer"]}]` —
  toujours présent (cohérent avec `dct:publisher`, jamais vide car retombe sur
  `tenant.name`).
- `extent.temporal` : `[[temporal_start ou None, temporal_end ou None]]` si au
  moins l'un des deux est renseigné (colonnes `Collection.temporal_start`/
  `temporal_end`, §1.1), sinon comportement actuel — repli sur le paramètre
  `temporal_start` déjà existant de `serializers.collection()` (qui reçoit
  aujourd'hui `created_at`, nom de paramètre à conserver tel quel, aucune
  collision : c'est la même notion, seule sa source change).
- Pas de champ langue (STAC n'en a pas de natif).

## 5. UI shell

### 5.1 `EditCollectionPanel.tsx`

Passe sur `ui/kit/Tabs` (déjà utilisé ailleurs dans le shell, aucun nouveau
composant à écrire) pour ne pas empiler ~13 champs dans un seul formulaire :

- **Général** (contenu actuel, inchangé) : titre, description, Public,
  Éditable.
- **Métadonnées ouvertes** (nouveau) : licence (`Select` du kit, peuplé
  depuis `GET /collections/metadata-catalog` ; champ `license_uri` en texte
  libre affiché seulement si `license === "other"`), producteur (`Input`),
  contact (`Input`), fréquence de mise à jour (`Select`), généalogie
  (`Textarea`), langue (`Select`), version (`Input`), emprise temporelle
  (deux `Input type="date"`, libellés « Début » / « Fin »).
- **Pièces jointes** (section existante SP-40, déplacée telle quelle, aucun
  changement de logique).

Un seul `submit` global (comme aujourd'hui) : tous les champs des 3 onglets
partent ensemble dans le même appel à `useUpdateCollection`, pas de
sauvegarde par onglet.

### 5.2 `MetadataForm.tsx` (consommé par `ItemDetailPage`, tout type d'item)

Ajoute deux champs : licence (`Select`, même catalogue, même source
`GET /metadata-catalog`) et langue (`Select`).

### 5.3 Correctif du bug keywords

`ItemDetailPage.tsx:133` et `:153` :
`initial={{ title: item.title, abstract: item.abstract, keywords: [] }}` →
`initial={{ title: item.title, abstract: item.abstract, keywords: item.keywords ?? [] }}`.
Sans ce correctif, les mots-clés existants d'un item disparaissent (dans le
formulaire, pas en base) à chaque ouverture du panneau Éditer — un
utilisateur qui enregistre après avoir touché n'importe quel autre champ les
efface réellement.

## 6. Chemins de lecture (piège n°5)

`ItemRead`/`CollectionAdmin` (schéma shell, `shell/src/api/types.ts`) doivent
tous deux porter les nouveaux champs pour que `getItem`/`listCollections`
survivent à un rechargement — vérifier en implémentation qu'aucun mapping
manuel n'existe entre le JSON reçu et le type TS qui omettrait les nouveaux
champs (le passthrough actuel de `getItem`/`getCollection` semble direct,
sans reconstruction champ à champ — à confirmer, pas à supposer).

## 7. Critères de sortie

1. Une collection avec `license: "etalab-2.0"` sort de
   `GET /dcat/datasets/{id}` avec `dct:license` pointant vers l'URI Etalab et
   de `GET /stac/collections/{id}` avec `"license": "etalab-2.0"`.
2. Une collection sans aucun nouveau champ renseigné produit un export DCAT-AP
   et STAC **identique** à celui d'avant ce plan (test de non-régression
   explicite, comparaison de payload).
3. Producteur, contact, fréquence, généalogie, version et emprise temporelle
   apparaissent dans l'export dès qu'ils sont renseignés, absents sinon.
4. Un item de n'importe quel type (map/app/dashboard/pipeline/…) édité via
   `ItemDetailPage` conserve ses mots-clés existants à la réouverture du
   panneau Éditer (non-régression du correctif §5.3).
5. Un item quelconque peut se voir attribuer une licence et une langue depuis
   le même panneau, et les relit après rechargement.
6. Migration Alembic testée dans les deux sens sur une base Postgres non vide
   réelle (pas seulement `Base.metadata.create_all()`).
7. Suites shell (Vitest, `tsc --noEmit`) et cœur (`pytest`, `ruff`,
   `mypy --strict` sur les modules déjà dans le périmètre CI) vertes ; E2E
   complet rejoué avant clôture (piège n°6) ; OpenAPI/types TS régénérés
   (piège n°1, diff non vide attendu cette fois — nouvelle route et nouveaux
   champs).

## 8. Décomposition en tâches (indicatif, affiné en plan)

1. Modèle + migration `Collection` (9 colonnes) + `Item` (2 colonnes).
2. Catalogue curaté (`metadata_catalog.py`) + route `GET /collections/metadata-catalog`.
3. `dcat/serializers.py` + `dcat/routes.py` (câblage des nouveaux champs).
4. `stac/serializers.py` + `stac/routes.py` (câblage des nouveaux champs).
5. Tests de non-régression (export identique sans nouveaux champs) + tests
   des nouveaux champs, DCAT et STAC.
6. `EditCollectionPanel.tsx` — onglets (Général / Métadonnées ouvertes /
   Pièces jointes).
7. `MetadataForm.tsx` + correctif keywords `ItemDetailPage.tsx`.
8. Régénération OpenAPI/TS, vérification finale (suites complètes + E2E +
   migration deux sens sur base non vide réelle), revue finale de branche.
