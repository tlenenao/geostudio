# Lot L12 : docs, onboarding, supply chain (spec)

Audit 2026-10-16 : AUD-111, 112, 113, 118, 123, 125, 137, 138, 139, 150.
Branche : couloir C. Exécution déjà réalisée ; cette spec fixe le périmètre et les choix par défaut.

## Périmètre

- **Supply chain (111/112/113)** : export-worker construit depuis `uv.lock` (`uv export --frozen`),
  uv épinglé ; garde de licences Python (`core/scripts/check_licenses.py`) et Node
  (`shell/scripts/check-licenses.mjs`) avec fichiers d'exceptions ; Dependabot étendu (cargo, npm
  desktop-etl, docker-compose, helm) ; `docker-compose.prod.yml` sans repli `latest`
  (`GEOSTUDIO_VERSION` obligatoire) ; `mc` vérifié par sha256 ; `scripts/verify-images.sh` (cosign)
  et crochet `INSTALL_VERIFY_SIGNATURES=1` dans `install.sh`.
- **Tests (123/125/137)** : budgets de limiteur épinglés ; boucle `cdc.main.run` testée ; contrat de
  couches élargi aux modules feuilles ; cliquet mypy par fichier (`.mypy-baseline.json`) ; E2E flaky
  stabilisés (cause racine d'`analytics-context` : mock manquant du dataset promu).
- **Docs (118/139)** : README sans chiffres figés, `docs/guides/`, catalogue MCP généré et gardé
  contre la dérive, liens relatifs testés, seed de démo (carte, app, dashboard), lien « Aide » du
  TopBar, runbook d'environnement de test.
- **138/150** : le filet de bundle nomme ses contributeurs et sa marge ; terrain de carte borné.

## Choix par défaut (à valider)

1. Trivy reste informatif (non bloquant) ; documenté dans `docs/supply-chain.md`.
2. Pas d'épinglage de digest des images de base.
3. Pas de dossier `examples/`, pas de captures d'écran.
4. Seed de démo sans pipeline ni alerte.
5. Le lien « Aide » pointe vers `docs/guides` sur GitHub.
6. `mypy --strict` étendu aux seuls modules feuilles propres ; le reste sous cliquet.
7. `app/jobs/common.py` reste hors du contrat de couches (cycle items/notifications).
8. Découpage de MapView/deck.gl (AUD-138) reporté ; seuil de bundle inchangé (640 Ko).

## Hors périmètre

Rejeu réel d'une release signée (AUD-177), migrations (aucune), nouvelles routes REST/outils MCP (aucun).
