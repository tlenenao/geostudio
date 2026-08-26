# Task 8 report — Notifier les alertes SLO (3.7)

## Résumé

Implémenté un point de contact webhook Grafana + une politique de routage pour
le dossier SLO, avec preuve de bout en bout réelle (conteneur Docker,
listener HTTP local, POST observé) via la règle `test-alert-do-not-keep-in-prod`
déjà présente dans `rules.yaml`.

## Étape 1 — vérification empirique de l'expansion `${VAR}`

```
docker run --rm --entrypoint sh grafana/otel-lgtm:0.11.4 -c "/otel-lgtm/grafana/bin/grafana-server -v"
→ Version 12.0.1
```

Test empirique exact du brief : fichier `contactpoints.yaml` avec
`url: ${TEST_WEBHOOK_URL}`, conteneur lancé avec
`-e TEST_WEBHOOK_URL=https://example.test/hook`. Réponse de
`GET /api/v1/provisioning/contact-points` :

```json
{"uid":"test-cp-webhook","name":"test-cp","type":"webhook",
 "settings":{"url":"https://example.test/hook"}, "provenance":"file"}
```

L'URL est résolue (littéral `example.test`, pas la chaîne brute
`${TEST_WEBHOOK_URL}`) → **native expansion fonctionne sur Grafana 12.0.1**.
**Branche 2a retenue.**

## Étape 2a — fichiers créés

- `deploy/observability/grafana/provisioning/alerting/contactpoints.yaml` —
  contact point webhook `geostudio-webhook` avec
  `url: ${GRAFANA_ALERT_WEBHOOK_URL}`.
- `deploy/observability/grafana/provisioning/alerting/policies.yaml` —
  policy racine `receiver: geostudio-webhook` + route explicite
  `object_matchers: [["slo", "=~", ".+"]]` (texte du brief, verbatim).

### Déviation par rapport au texte littéral du brief (trouvée empiriquement)

Le brief propose `GRAFANA_ALERT_WEBHOOK_URL: ${GRAFANA_ALERT_WEBHOOK_URL:-}`
dans `docker-compose.yml` (défaut **vide**). Testé empiriquement avant
d'appliquer tel quel : une URL vide dans `contactpoints.yaml` fait échouer le
provisioning alerting de Grafana au démarrage
(`level=error msg="Failed to provision alerting" error="... required field
'url' is not specified"`), **arrête le service Grafana** du conteneur
entier (`api/health` reste inatteignable, `000`), et Grafana ne redémarre pas
tout seul. C'est exactement la classe de bug documentée à répétition dans ce
dépôt (SP-17a/SP-17b/tileset3d/`CORE_ETL_ENABLED`) : une capacité
"documentée avec défaut vide = désactivée" qui casse en réalité le service
dès que la variable n'est pas réglée — ici pire, puisque `otel-lgtm` sert
aussi les dashboards/metrics/traces, pas seulement l'alerting.

Testé aussi si Grafana supportait `${VAR:-default}` façon shell dans son
expansion interne (`${TEST_WEBHOOK_URL:-http://localhost:65535/unconfigured}`)
— non : Grafana traite tout après `${` jusqu'à `}` comme un seul nom de
variable, n'a pas trouvé de variable portant ce nom exact, et a substitué
une chaîne vide (même crash).

**Fix retenu** : le défaut du `${GRAFANA_ALERT_WEBHOOK_URL:-...}` côté
`docker-compose.yml` (résolu par Compose lui-même, avant même que Grafana
voie la variable) pointe vers un localhost inatteignable syntaxiquement
valide : `http://127.0.0.1:1/grafana-alert-webhook-not-configured`. Testé
empiriquement : `api/health` → 200, contact point provisionné avec cette
URL littérale, service démarre normalement. Documenté dans le commentaire
du compose et dans `.env.example`.

## docker-compose.yml

```yaml
  otel-lgtm:
    image: grafana/otel-lgtm:0.11.4
    profiles: ["observability"]
    environment:
      GRAFANA_ALERT_WEBHOOK_URL: ${GRAFANA_ALERT_WEBHOOK_URL:-http://127.0.0.1:1/grafana-alert-webhook-not-configured}
    ports:
      ...
```

## Étape 3 — `.env.example`

Nouvelle section `─── Observabilité (Grafana, profil compose observability) ───`
juste après le bloc `CORE_HARVEST_EGRESS_ALLOWLIST` et avant le bloc coffre
de secrets, documentant `GRAFANA_ALERT_WEBHOOK_URL=` (vide, avec le repli
localhost expliqué dans le commentaire).

## Étape 4 — garde-fou de déployabilité

```
cd core && uv run pytest tests/test_deployability.py -v
→ 31 passed
```

`GRAFANA_ALERT_WEBHOOK_URL` apparaît bien comme substitution `${...}` dans
`docker-compose.yml` ET comme ligne active dans `.env.example` — les deux
sens de la règle (`test_every_compose_substitution_is_documented` +
`test_every_documented_env_var_is_wired_or_declared_inert`) passent.

## Étape 5 — preuve de bout en bout

### Approches réseau testées

1. `host.docker.internal` : `docker run --rm alpine sh -c "getent hosts
   host.docker.internal"` → résout (`fdc4:f303:9324::254`). Testé
   accessibilité HTTP réelle avec un `python3 -m http.server 9999 --bind
   0.0.0.0` local + `docker run --rm alpine wget -qO-
   http://host.docker.internal:9999/` → **200, contenu HTML reçu**, sans
   même besoin de `--add-host` (résolution native dans cet environnement
   Docker Desktop/WSL2). Approche retenue.

### Déroulé réel

- `export GRAFANA_ALERT_WEBHOOK_URL="http://host.docker.internal:9999/webhook-test"`
- `docker compose --profile observability up -d otel-lgtm` — **a échoué** de
  façon reproductible (`Error response from daemon: ports are not available:
  exposing port TCP 0.0.0.0:3001 -> 127.0.0.1:0: /forwards/expose returned
  unexpected status: 500`), un problème de forwarding de port WSL2/Docker
  Desktop sans rapport avec cette tâche (port 3001 non occupé localement,
  `ss -ltn` ne montre rien dessus ; retenté plusieurs fois, même échec).
  Contourné en lançant le même conteneur via `docker run` directement
  (mêmes volumes bind-mount, même réseau `geostudio_gis-net` créé par le
  `up` précédent, même variable d'env, port hôte différent 13010 au lieu de
  3001) — reproduit exactement la même config que le service compose
  `otel-lgtm` verrait, seul le port de publication hôte diffère.
- Conteneur up, `GET /api/health` → 200. `GET
  /api/v1/provisioning/contact-points` confirme
  `geostudio-webhook-receiver` avec `url:
  "http://host.docker.internal:9999/webhook-test"` (résolue). `GET
  /api/v1/provisioning/policies` confirme la politique
  (`receiver: geostudio-webhook`, route `object_matchers: [["slo","=~",".+"]]`).
  `GET /api/v1/provisioning/alert-rules` confirme les 4 règles SLO +
  `test-alert-always-firing` avec `isPaused: true` — comportement par
  défaut correct.
- `isPaused: true → false` dans `rules.yaml` (fichier hôte, bind-mount).
  `docker restart manual-otel-lgtm` pour forcer une relecture de
  provisioning (délai de repoll non attendu). Après redémarrage,
  `isPaused: false` confirmé côté API.
- **Notification réellement observée** : le log du listener HTTP local
  affiche `POST /webhook-test HTTP/1.1" 501 -` (501 = `http.server` stdlib
  ne gère pas POST par défaut, sans rapport avec la livraison elle-même —
  la requête est bien arrivée). `GET
  /api/alertmanager/grafana/api/v2/alerts` confirme une alerte active
  (`fingerprint 4b06ed1687fbba8e`, `status.state: "active"`,
  `receivers: [{"name": "geostudio-webhook"}]`) — la résolution de route
  (chute sur le receiver racine `geostudio-webhook`, la règle de test ne
  porte pas de label `slo`) est celle attendue.
- `isPaused: false → true` restauré dans `rules.yaml`. `docker restart` de
  nouveau. Log du listener vidé avant redémarrage puis observé pendant
  ~20s après : **aucune nouvelle requête**. `GET
  /api/alertmanager/grafana/api/v2/alerts` → `[]` (plus d'alerte active).
- `git diff deploy/observability/grafana/provisioning/alerting/rules.yaml` →
  **vide** (confirmé, `isPaused` restauré à `true`, aucun changement non
  voulu committé).
- Nettoyage : `docker rm -f manual-otel-lgtm`, `docker compose --profile
  observability down` (supprime le conteneur/réseau créés par la tentative
  `up` initiale), listener Python local tué.

**Conclusion : livraison réelle observée de bout en bout**, pas seulement
l'API de provisioning — un vrai POST HTTP est arrivé sur un process tiers
totalement indépendant de Grafana, déclenché par le déblocage d'
`isPaused`, et s'est arrêté au re-blocage.

## Fichiers modifiés/créés

- `deploy/observability/grafana/provisioning/alerting/contactpoints.yaml`
  (nouveau)
- `deploy/observability/grafana/provisioning/alerting/policies.yaml`
  (nouveau)
- `docker-compose.yml` (bloc `environment:` sur le service `otel-lgtm`)
- `.env.example` (nouvelle section observabilité, `GRAFANA_ALERT_WEBHOOK_URL`)
- `deploy/observability/grafana/provisioning/alerting/rules.yaml` — édité
  deux fois pendant Step 5 (isPaused false puis true), diff final vide,
  rien à committer sur ce fichier.

## Auto-revue

- Complétude : contact point + policy créés, correctement scopés au dossier
  SLO via `object_matchers`/`receiver`, `docker-compose.yml` câble bien la
  variable sur `otel-lgtm`, `.env.example` la documente, garde-fou vert,
  `isPaused` restauré à `true` dans l'état final committable.
- Qualité : YAML validé syntaxiquement (`yaml.safe_load` sur les 3
  fichiers). Contact point/policy repris du texte exact du brief (Step 2a),
  sauf le défaut de `docker-compose.yml` (déviation documentée et testée
  ci-dessus).
- Discipline : rien de généré/rendu committé (branche 2a, pas de template
  envsubst, pas d'entrée `.gitignore` nécessaire). `rules.yaml` n'a aucun
  diff résiduel.

## Points d'attention / suivis

- **Déviation assumée vs. texte littéral du brief** : le défaut de
  `GRAFANA_ALERT_WEBHOOK_URL` dans `docker-compose.yml` n'est PAS vide comme
  suggéré par le brief (`${GRAFANA_ALERT_WEBHOOK_URL:-}`), mais un localhost
  inatteignable syntaxiquement valide — testé et confirmé nécessaire pour
  que le service `otel-lgtm` démarre du tout sans configuration opérateur.
  Documenté dans le commentaire compose + `.env.example`. C'est un bug réel
  du texte littéral du brief, corrigé sans repasser par l'utilisateur,
  cohérent avec la pratique établie par les SP précédents documentée dans
  CLAUDE.md (corriger une trouvaille contre le texte du plan sans
  re-demander).
- **Panne de forwarding de port WSL2/Docker Desktop non liée à cette
  tâche** : `docker compose --profile observability up -d otel-lgtm` échoue
  systématiquement sur `0.0.0.0:3001` dans cet environnement (`/forwards/
  expose returned unexpected status: 500`). Contourné pour la preuve E2E via
  un `docker run` manuel équivalent (mêmes volumes/réseau/env, port hôte
  différent) — le comportement observé (contact point, policy, notification
  réelle) est représentatif du service compose réel, seul le mécanisme de
  publication de port hôte diffère. À signaler comme suivi non bloquant
  distinct de SP-26/3.7 : quiconque tente `docker compose --profile
  observability up` dans cet environnement WSL2 particulier rencontrera la
  même erreur, sans rapport avec ce chantier.
- Le fichier non commité `deploy/postgis/pg_hba.conf` vu en `git status` au
  début de la session est pré-existant (documenté dans CLAUDE.md, section
  Suivis non bloquants SP-20/21) et n'a pas été touché par cette tâche.
