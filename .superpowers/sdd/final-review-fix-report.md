# Rapport — pass de correction sur la revue finale de `scripts/install.sh`

Contexte : revue finale de branche (toutes les 4 tâches SP-Deploy-c déjà
passées individuellement en revue) sur l'ensemble du fichier
`scripts/install.sh`. Ce pass corrige 3 findings cross-cutting relevés par
cette revue finale — 1 critique, 1 important, 1 mineur — sans toucher aux
notes explicitement laissées non bloquantes (sed-delimiter, `ADMIN_SUB`
sans `// empty`, `python3` vs `python`).

## Finding 1 (CRITIQUE) — expansion de tableau vide sous bash 3.2

**Problème** : `launch_stack()` faisait `"${SELECTED_PROFILES[@]}"` puis
`"${profile_args[@]}"` sans garde. Sous `set -u` (actif en tête de script),
bash < 4.4 (donc le bash 3.2.57 fourni en standard sur macOS) lève
`unbound variable` sur l'expansion `"${arr[@]}"` d'un tableau **vide**. Le
cas courant — aucun profil optionnel sélectionné — laisse `SELECTED_PROFILES`
et `profile_args` vides tous les deux : le script se serait arrêté en plein
`launch_stack`, APRÈS installation Docker, génération `.env`, tunnel
Tailscale et création du compte admin Keycloak. Ceci réintroduisait
exactement la classe de bug que la Tâche 2 (`profile_label`, commit
`357e6bd`) avait éliminée en remplaçant un `declare -A` par un `case`.

**Correctif appliqué** (`scripts/install.sh`, dans `launch_stack()`) :
```bash
local profile_args=()
for p in "${SELECTED_PROFILES[@]+"${SELECTED_PROFILES[@]}"}"; do
  profile_args+=(--profile "$p")
done
$COMPOSE ${profile_args[@]+"${profile_args[@]}"} up -d
```
Idiome portable standard `${arr[@]+"${arr[@]}"}` : sous `set -u`, si `arr`
est vide, le paramètre `arr[@]` n'est jamais réellement référencé (l'opérateur
`+` court-circuite), donc pas d'`unbound variable` ; si `arr` a des éléments,
le comportement est identique à `"${arr[@]}"`.

**Vérification réelle effectuée** :
- `bash -n scripts/install.sh` → OK (syntaxe).
- Bash de ce dépôt est 5.3.9 (`bash --version`) — ne reproduit PAS le bug
  nativement (confirmé par le repro ci-dessous, qui ne lève pas d'erreur
  même SANS garde, faute de bash < 4.4 disponible ici). Une vraie machine
  bash 3.2 n'est pas disponible dans cet environnement.
- Copié **exactement** le bloc `launch_stack` du fichier réel (lignes
  303-310 après édition) dans un harnais de test standalone
  (`/tmp/.../test_launch_stack_snippet.sh`), avec `$COMPOSE` remplacé par
  `echo` (aucun appel Docker réel) :
  - Cas `SELECTED_PROFILES=()` (vide) → `COMPOSE_CALLED up -d`, `exit=0`,
    aucune erreur `unbound variable`.
  - Cas `SELECTED_PROFILES=(observability)` (un profil) → 
    `COMPOSE_CALLED --profile observability up -d`, `exit=0` — le flag
    `--profile observability` atteint bien la commande.
- Le raisonnement sur l'idiome `${arr[@]+"${arr[@]}"}` est un standard bash
  bien établi (POSIX/bash FAQ) pour ce problème précis ; corroboré par
  l'absence d'erreur ici et par le comportement correct dans les deux cas.

## Finding 2 (IMPORTANT) — erreur `docker compose config` avalée silencieusement

**Problème initial signalé** : `available="$($COMPOSE config --profiles 2>/dev/null || true)"`
avalait toute erreur de configuration Compose (YAML malformé, mauvais merge)
en une liste de profils vide et silencieuse, sans avertissement — l'opérateur
n'aurait découvert le vrai problème que bien plus tard, à l'échec de
`up -d` dans `launch_stack`.

**Piège découvert pendant la vérification** (au-delà de ce que demandait le
finding, mais bloquant si non traité) : la suggestion initiale du finding
était de faire `2>&1` pour capturer stderr dans la même variable en cas
d'échec. Testé en réel :
```
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --profiles
```
→ exit 0, mais **stderr contient de nombreuses lignes
`level=warning msg="The \"PG_PASSWORD\" variable is not set..."`** (normal :
`prompt_profiles` s'exécute AVANT `ensure_env_file`, donc `.env` n'existe pas
encore et docker compose avertit sur chaque variable manquante). Avec
`2>&1`, ces lignes de warning auraient été fusionnées dans `$available` même
en cas de SUCCÈS, et la boucle `while IFS= read -r profile` de
`prompt_profiles` aurait alors traité chaque ligne de warning comme un nom de
profil, proposant à l'opérateur d'« activer » des lignes de log absurdes.
Ce n'était donc PAS sûr pour ce projet, contrairement à l'hypothèse du
finding — vérifié empiriquement plutôt qu'en le supposant.

**Correctif réellement appliqué** (`prompt_profiles()`) — capture stderr
dans un fichier temporaire séparé, jamais mélangé à stdout sur le chemin de
succès :
```bash
local compose_err
compose_err="$(mktemp)"
if ! available="$($COMPOSE config --profiles 2>"$compose_err")"; then
  echo "✗ Impossible de lire la configuration Docker Compose :" >&2
  cat "$compose_err" >&2
  rm -f "$compose_err"
  exit 1
fi
rm -f "$compose_err"
```

**Vérification réelle effectuée** :
- Chemin succès (réel, contre les fichiers compose du dépôt) :
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml config --profiles`
  → stdout = `observability` (1 ligne), stderr = warnings `.env`. Reproduit
  la logique exacte de `prompt_profiles` en isolation (harnais
  `/tmp/.../test_prompt_profiles.sh`) : `AVAILABLE=[observability]`,
  1 seule ligne — confirme que le comportement du chemin de succès est
  inchangé et propre (pas de pollution par les warnings).
- Chemin échec (réel, fichier compose volontairement cassé — YAML flow
  sequence non fermée) : `available=...` échoue, message d'erreur affiché
  proprement avec le détail YAML (`yaml: while parsing a flow sequence at
  line 3, column 15: line 4: did not find expected ',' or ']'`), `exit 1`
  atteint. Confirme le chemin d'erreur.

## Finding 3 (MINEUR) — clé secrète de sauvegarde échoée à l'écran

**Correctif appliqué** (`prompt_backup_target()`) :
```bash
read -r -s -p "  Secret key : " s3_secret
echo
```
Seule la ligne `Secret key` est modifiée ; `Access key`, `Bucket` et
`endpoint` restent en `read -r -p` normal, conformément à la convention du
script (seul le mot de passe admin Keycloak bénéficiait jusqu'ici de ce
traitement).

**Vérification réelle effectuée** : `bash -n scripts/install.sh` passe
après l'ajout du `-s`. Pas de test TTY interactif automatisé réalisé (non
praticable dans cet environnement) — la correction se limite à l'ajout du
flag `-s` (silencieux) documenté du builtin `read` et d'un `echo` pour
restaurer le saut de ligne qu'il supprime ; correction syntaxiquement
propre et de portée strictement locale à cette ligne.

## Commandes exécutées (résumé)

```
bash -n scripts/install.sh                                    # OK
bash --version                                                 # 5.3.9 (ne reproduit pas le bug 3.2 nativement)
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --profiles   # exit 0, stdout="observability", stderr=warnings .env
# harnais standalone reprenant le bloc réel de launch_stack (SELECTED_PROFILES vide / à 1 élément)
# harnais standalone reprenant le bloc réel de prompt_profiles contre les fichiers compose réels
# fichier compose volontairement cassé pour vérifier le chemin d'erreur du Finding 2
```

Aucun conteneur Docker n'a été démarré (les appels `$COMPOSE` étaient
remplacés par `echo` dans les harnais isolés, sauf le seul appel
`docker compose config --profiles` réel — lecture seule, sans side-effect).
Aucun clone jetable du dépôt n'a été nécessaire ni créé. Fichiers temporaires
du scratchpad nettoyés après usage.

## Portée non touchée (rappel)

Conformément aux instructions du controller, n'ont PAS été modifiés :
- `sed`/`&` dans `set_env_var` (idiome partagé pré-existant avec
  `bootstrap-env.sh`).
- Absence de `// empty` dans le filtre jq de `ADMIN_SUB` après `create users`.
- Incohérence cosmétique `python3` vs `python` entre la sonde de santé et
  l'appel `seed_demo`.
