# Plan de lancement grand public (2026-10-23)

Objectif : une release publique **v0.2.0** qu'on peut annoncer sans réserve. « Parfait » n'est pas vérifiable ; on le remplace par des **portes go/no-go mesurables**. Le lancement n'a lieu que lorsque toutes les portes sont vertes ; un écart se corrige ou se déclare par écrit dans les notes de version.

État de départ : PR #189 (dev → main) ouverte, CI verte sur `9ad2204f` ; 30 REV ouvertes + 17 partielles ; v0.1.0 est le dernier tag.

## Portes (toutes obligatoires)

| # | Porte | Preuve attendue |
|---|---|---|
| G1 | Code sur `main`, CI verte | PR #189 fusionnée, `main` vert sur push |
| G2 | Aucun constat Critical/Important ouvert | REV-371 à 403 : tous fermés ou reclassés par décision écrite |
| G3 | Migrations sûres sur base non vide, dans les deux sens | test de migration 0001→head puis downgrade sur base peuplée (AUD-188 à 192) |
| G4 | Chaîne de livraison prouvée | tag candidat `v0.2.0-rc1` : build multi-arch, cosign signé ET vérifié (`verify-images.sh`), compose de prod par digests, bases épinglées |
| G5 | Pile réelle rejouée | `scripts/replay/run.sh` : OIDC réel, sauvegarde/restauration, SSE derrière Traefik, collecte hors-ligne (T21), export réel (AUD-133) |
| G6 | Sécurité | intégrité des relations (AUD-165 à 167), sidecar/`reader.file` (158 à 160), conteneurs non-root (179), alertes CodeQL/Trivy/gitleaks à zéro |
| G7 | Charge et exploitabilité | mesure à 10^6 lignes rejouée sur la pile réelle, LCP < 2,5 s, runbooks incident/rollback/restauration testés |
| G8 | Produit public | PoW exigée par défaut (décidé 2026-10-23), câblée dans le compose ; RGAA/RTL/L13 (b) livrés ou écartés par écrit, CHANGELOG + notes de rupture, guides à jour |
| G9 | Reprise à froid | installation depuis zéro sur une machine vierge (Proxmox ET OCI arm64) en suivant uniquement la doc |

## Lots (3 couloirs parallèles, migrations 0190+ réservées par couloir)

**Couloir A — Données et intégrité (G2, G3, G6)**
A1 migrations 188–192 (lock_timeout, NOT VALID/VALIDATE, backfill, gardes de downgrade, test base non vide) · A2 relations 163–167 (check_write dans repository, before_update, audit à la suppression, 4xx sur FilterError) · A3 AUD-171 curseur `/changes` · A4 AUD-186 If-Match obligatoire derrière drapeau · A5 jumelles piège n°14 (REV-402).

**Couloir B — Sécurité et supply chain (G4, G6)**
B1 sidecar/`reader.file` 158–161 · B2 cosign (lire la cause, corriger, tag rc) · B3 digests des bases + Dependabot docker + MinIO commit vérifié (178, 182) · B4 non-root minio/titiler (179), scripts hors image (187), limites cpus/pids (184), `docker compose config` par valeur pour 183 · B5 partiels 154–156, 172.

**Couloir C — Rejeu réel, produit, doc (G5, G7, G8, G9)**
C1 rejeu pile réelle complet + rapport · C2 mesures 10^6 et LCP · C3 PoW par défaut + câblage compose · C4 mineurs (REV-400/401) · C5 installation à froid Proxmox/OCI · C6 CHANGELOG/notes de rupture/guides, E2E desktop vert.

**Couloir D — Périmètre élargi (décision de Tanguy du 2026-10-23 : « tout dans v0.2.0 »)** (G8)
D1 RGAA (audit + corrections) et ProConnect/OIDC administration · D2 RTL · D3 L13 classe (b) : PythonCaller, Airbyte, Postgres HA, commentaires (specs d'abord, `102-l13-cadrage.md`) · D4 reliquats AUD ouverts : 010 (D4), 116 (D8), 029, 057, 059, 099, 129, `jobs/common.py`, DCAT `@en`. Chaque item passe par brainstorm → spec → plan avant exécution ; aucun n'est lancé sans spec validée.

## Méthode

Chaque lot : spec courte → TDD → revue par tâche → **revue finale de branche** ; je fusionne en série dans `dev`, régénère OpenAPI/inventaire/bilan, rebase les migrations. Tout est rejoué par la suite complète (pytest, vitest, E2E, mypy, lint-imports) avant la PR de promotion. Tag `v0.2.0-rc1` après G1–G4, `rc2` après G5–G7, `v0.2.0` quand G1–G9 sont verts.

## Ce qui ne dépend pas de moi

- PR #189 fusionnée le 2026-10-23.
- Actions propriétaire : secrets/droits GitHub pour cosign et GHCR, DNS/TLS du domaine public, clé `age` de test (rotation ?).
- Décisions produit (voir questions) : PoW par défaut, périmètre RTL/RGAA/ProConnect, L13 classe (b).
- Un vrai test d'accessibilité par lecteur d'écran/appareil tactile restera une limite assumée.
