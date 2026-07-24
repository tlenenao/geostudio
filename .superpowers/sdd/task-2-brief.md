### Task 2 : menu de profils (découverte, pas codé en dur)

**Files:**
- Modify: `scripts/install.sh`

**Interfaces:**
- Consumes: `docker compose config --profiles` (sous-commande vérifiée disponible, Docker Compose v2).
- Produces: variable `SELECTED_PROFILES` (tableau bash, ex. `(observability)` ou vide) et `SEED_DEMO` (`true`/`false`) — consommées par la Task 4 (lancement).

**Contexte vérifié :** `docker compose config --profiles` sur ce dépôt liste aujourd'hui exactement `observability` (seul profil défini, `docker-compose.yml` services `otel-lgtm`/`postgres-exporter`) — confirmé en l'exécutant réellement pendant l'écriture de ce plan.

- [ ] **Step 1: Découverte + menu**

Ajouter à `scripts/install.sh` :

```bash
declare -A KNOWN_PROFILE_LABELS=(
  [observability]="Observabilité (Grafana/Loki/Tempo/Prometheus)"
  [etl]="ETL no-code (SP-17)"
)

SELECTED_PROFILES=()
SEED_DEMO=false

prompt_profiles() {
  local available
  available="$($COMPOSE config --profiles 2>/dev/null || true)"

  echo ""
  echo "── Profils disponibles ──"
  while IFS= read -r profile; do
    [ -z "$profile" ] && continue
    label="${KNOWN_PROFILE_LABELS[$profile]:-$profile}"
    if confirm "Activer : ${label} ?"; then
      SELECTED_PROFILES+=("$profile")
    fi
  done <<< "$available"

  # ETL (SP-17) : toujours affiché, jamais activable tant qu'absent du
  # dépôt — ne ment pas à l'utilisateur (spec §5.2).
  if ! grep -qx "etl" <<< "$available"; then
    echo "  (ETL no-code (SP-17) — à venir, pas encore disponible dans ce dépôt)"
  fi

  echo ""
  if confirm "Charger des données de démo (collections incidents/points_interet, publiques, éditables) ?"; then
    SEED_DEMO=true
  fi
}

prompt_profiles
```

- [ ] **Step 2: Vérifier réellement (mode non-interactif)**

```bash
rm -rf /tmp/geostudio-install-test && git clone . /tmp/geostudio-install-test
cd /tmp/geostudio-install-test
INSTALL_YES=1 ./scripts/install.sh 2>&1 | grep -A3 "Profils disponibles"
```

Expected : `Activer : Observabilité (Grafana/Loki/Tempo/Prometheus) ? [y/N] → y (INSTALL_YES=1)`, ligne `(ETL no-code (SP-17) — à venir...)` affichée (le profil `etl` n'existe pas encore dans ce dépôt), puis la question sur le seed de démo.

```bash
cd /home/lenen/projets/geostudio && rm -rf /tmp/geostudio-install-test
```

- [ ] **Step 3: Commit**

```bash
git add scripts/install.sh
git commit -m "feat(deploy): installeur — menu de profils découverts dynamiquement"
```

---

