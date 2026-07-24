### Task 4 : lancement final, attente de santé, idempotence (critère §7-6)

**Files:**
- Modify: `scripts/install.sh`

**Interfaces:** consomme l'ensemble des Tasks 1-3 du même fichier ; ne produit rien de consommé ailleurs (dernière étape du script).

- [ ] **Step 1: Lancement complet + attente de santé + seed optionnel**

Ajouter à `scripts/install.sh` :

```bash
launch_stack() {
  echo ""
  echo "Démarrage complet de la stack..."
  local profile_args=()
  for p in "${SELECTED_PROFILES[@]}"; do
    profile_args+=(--profile "$p")
  done
  $COMPOSE "${profile_args[@]}" up -d

  echo "Attente de la disponibilité du cœur..."
  for _ in $(seq 1 30); do
    code="$($COMPOSE exec -T core curl -s -o /dev/null -w '%{http_code}' http://localhost:8200/me 2>/dev/null || echo 000)"
    [ "$code" = "401" ] && break
    sleep 2
  done
  if [ "$code" != "401" ]; then
    echo "✗ Le cœur ne répond pas comme attendu (code ${code}) — vérifiez 'docker compose logs core'." >&2
    exit 1
  fi
  echo "✓ Cœur opérationnel."

  if [ "$SEED_DEMO" = "true" ]; then
    $COMPOSE exec -T core python -m scripts.seed_demo || true
  fi
}

print_summary() {
  echo ""
  echo "═══ GeoStudio est en ligne ═══"
  echo "URL publique : https://${PUBLIC_HOST}/"
  echo "Admin        : ${ADMIN_EMAIL:-<déjà existant>}"
  echo ""
  echo "Prochaines étapes :"
  echo "  - Se connecter avec le compte admin (mot de passe temporaire affiché ci-dessus, à changer)."
  echo "  - Si une cible de sauvegarde a été configurée : générer une paire de clés"
  echo "    age (age-keygen) et renseigner BACKUP_AGE_RECIPIENT dans .env, puis"
  echo "    redémarrer le service backup ('docker compose ... restart backup')."
  echo "  - Conserver .env et la clé privée age en lieu sûr, hors de cette machine."
}

launch_stack
print_summary
```

- [ ] **Step 2: Vérifier l'idempotence (relance sans casse, critère §7-6)**

```bash
rm -rf /tmp/geostudio-install-test && git clone . /tmp/geostudio-install-test
cd /tmp/geostudio-install-test
INSTALL_YES=1 TS_AUTHKEY=<clé-de-test-valide> ./scripts/install.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Expected (premier passage) : tous les services `Up`, message final avec l'URL publique.

```bash
INSTALL_YES=1 TS_AUTHKEY=<même-clé> ./scripts/install.sh
```

Expected (second passage) : `.env` conservé (`✓ .env existe déjà`), compte admin réutilisé (`✓ Compte admin déjà existant`), aucune erreur, stack toujours saine (`docker compose ps` inchangé).

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
cd /home/lenen/projets/geostudio && rm -rf /tmp/geostudio-install-test
```

- [ ] **Step 3: Rendre le script exécutable et vérifier le non-régression global**

```bash
chmod +x scripts/install.sh
cd core && uv run pytest && uv run lint-imports
cd ../shell && npm test && npm run build
```

Expected : tous verts — ce sous-plan ne touche à aucun code applicatif.

- [ ] **Step 4: Commit**

```bash
git add scripts/install.sh
git commit -m "feat(deploy): installeur — lancement, attente de santé, idempotence (critère §7-6)"
```
