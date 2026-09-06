# SPDX-License-Identifier: Apache-2.0
"""Garde-fou de déployabilité (SP-21, vague 1 du plan d'action 2026-08-20).

Ces tests ne testent pas `core/app/` : ils testent le **dépôt** —
`docker-compose.yml`, l'overlay de production, `release.yml`, `.env.example`
et `deploy/backup/backup.sh`. Entorse assumée au découpage : `core/` est le
seul répertoire du dépôt qui possède déjà un runner Python et une place dans
la CI (`uv run pytest` du job `core`), et la propriété vérifiée ici —
« toute capacité livrée est déployable » — n'a pas d'autre foyer.

Raison d'être : quatre capacités livrées, testées et mergées se sont révélées
non câblées dans la stack packagée (SP-17a, SP-17b, tileset3d, et
`CORE_ETL_ENABLED` trouvée en écrivant ces tests). Chaque règle ci-dessous
correspond à une de ces découvertes, et échoue sur le dépôt tel qu'il était
avant SP-21.

Écrire ces règles en a trouvé quatre instances de plus de la même classe, à
garder dans la raison d'être — ce fichier ne documente pas un incident clos
mais un mode d'échec qui se reproduit :

- trois allowlists d'egress SSRF (`CORE_PIPELINES_/HARVEST_/
  ALERTS_EGRESS_ALLOWLIST`) câblées sur zéro service, deux des trois pourtant
  documentées dans `.env.example` — même piège de lecture que
  `CORE_ETL_ENABLED` (trouvées en passant la règle 3 d'un grep à un résolveur
  AST, tâche 3) ;
- `titiler` qui écoute sur le port 80 alors que `core` proxifie chaque tuile
  de terrain 3D vers `titiler:8000` — le terrain 3D hébergé ne pouvait pas
  fonctionner du tout en stack packagée (trouvée en posant sa sonde,
  tâche 7) ;
- `S3_EXPORTS_BUCKET`/`S3_APPEXPORTS_BUCKET` lues par `core` et par `worker`
  (file `etl`) mais câblées seulement sur `worker`/`export-worker`/
  `appexport-runtime-builder` — sans effet visible, le défaut applicatif
  coïncidant avec la valeur du compose (revue finale SP-21) ;
- sept noms de `.env.example` (identifiants et buckets S3) présentés comme
  réglables alors qu'aucun n'est substitué nulle part, plus `MARTIN_SECRET`,
  généré par `scripts/bootstrap-env.sh` et lu par personne (revue finale
  SP-21, d'où la règle `test_every_documented_env_var_is_wired_or_declared_inert`).

Deux limites de périmètre à connaître avant de lire un test vert comme une
preuve plus large qu'elle n'est :

- les règles qui lisent du code source ne lisent que `core/app/`. La moitié
  shell d'une capacité n'est pas couverte : SP-17a, par exemple, a aussi
  besoin de `VITE_CORE_URL`/`SHELL_BASE_URL` côté `shell`, et c'est
  précisément par là que sa revue finale a trouvé deux variables inertes.
  Couvrir `shell/` demanderait de résoudre les lectures
  `import.meta.env.VITE_*` — non fait ;
- ces règles lisent des fichiers YAML. Elles ne démarrent rien, ne prouvent
  pas qu'un tag existe réellement au registre (seul `docker manifest
  inspect`, à la main, le fait) et ne prouvent pas qu'un
  `docker compose pull && up` de l'overlay complet aboutisse.
"""

import ast
import base64
import json
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
BASE = REPO / "docker-compose.yml"
PROD = REPO / "docker-compose.prod.yml"
RELEASE = REPO / ".github/workflows/release.yml"
ENV_EXAMPLE = REPO / ".env.example"
BOOTSTRAP_ENV_SH = REPO / "scripts/bootstrap-env.sh"
BACKUP_SH = REPO / "deploy/backup/backup.sh"
CORE_APP = REPO / "core/app"
BOOTSTRAP_ENV_SH = REPO / "scripts/bootstrap-env.sh"
KEYCLOAK_REALM_JSON = REPO / "deploy/keycloak/geostudio-realm.json"

# Préfixe des images que nous publions nous-mêmes.
OWN_IMAGE_RE = re.compile(r"ghcr\.io/[^/]+/(geostudio-[a-z0-9-]+)")


class Reset:
    """Sentinel modélisant `!reset` appliqué à un scalaire nul (`build:
    !reset null`) : la clé est *supprimée* par la fusion Compose — ce n'est
    pas la même chose qu'une clé simplement absente, qui n'affirme rien sur
    l'intention de l'overlay. `build_target()` traite les deux comme
    "pas de build", mais une règle qui a besoin de vérifier que l'overlay
    reset *explicitement* le `build:` du fichier de base (au lieu de ne pas
    en parler du tout) doit pouvoir distinguer les deux — d'où ce sentinel
    plutôt qu'un simple `None`."""

    def __repr__(self):  # pragma: no cover - confort de debug uniquement
        return "<reset>"


RESET = Reset()


class ComposeLoader(yaml.SafeLoader):
    """`docker-compose.prod.yml` utilise les tags de fusion propres à Compose
    (`ports: !reset []`, `build: !reset null`) — `yaml.safe_load` lève un
    ConstructorError dessus. Ces tags disent *comment* fusionner : pour une
    séquence/mapping (`!reset []`, `!override […]`), on résout à la valeur
    nue, aucune règle d'ici n'en dépend. Pour un scalaire nul sous `!reset`
    (`build: !reset null`), on résout au sentinel `RESET` plutôt qu'à la
    chaîne littérale `'null'` — sans quoi `build_target()` verrait un
    contexte de build valide au lieu d'une absence de build."""


def _drop_tag(loader, suffix, node):
    if (
        suffix == "reset"
        and isinstance(node, yaml.nodes.ScalarNode)
        and node.value in ("null", "~", "")
    ):
        return RESET
    if isinstance(node, yaml.nodes.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.nodes.MappingNode):
        return loader.construct_mapping(node)
    return node.value


ComposeLoader.add_multi_constructor("!", _drop_tag)


def load_yaml(path: pathlib.Path) -> dict:
    return yaml.load(path.read_text(), Loader=ComposeLoader) or {}


def services(path: pathlib.Path) -> dict:
    return load_yaml(path).get("services") or {}


def build_target(service: dict) -> tuple[str, str] | None:
    """(contexte, dockerfile) normalisé, ou None si le service n'a pas de
    `build:` (absent, ou explicitement `!reset` par l'overlay). La forme
    courte (`build: ./core`) et la forme longue (`build: {context,
    dockerfile}`) donnent le même couple."""
    build = service.get("build")
    if build is None or build is RESET:
        return None
    if isinstance(build, str):
        return (build, "Dockerfile")
    return (build.get("context", "."), build.get("dockerfile", "Dockerfile"))


def build_is_reset(service: dict) -> bool:
    """Vrai seulement si ce service déclare *explicitement* `build: !reset
    null` — contrairement à `build_target() is None`, qui est vrai aussi
    quand la clé est simplement absente."""
    return service.get("build") is RESET


def release_matrix() -> list[dict]:
    return load_yaml(RELEASE)["jobs"]["build-and-push"]["strategy"]["matrix"]["include"]


def test_every_build_service_has_a_released_image():
    """Tout service construit depuis les sources doit avoir une image
    publiée par la CI de release. Sinon, déployer la capacité exige de
    cloner le dépôt sur l'hôte de production et d'y compiler Chromium ou
    QGIS — ce que l'en-tête de l'overlay prod prétend justement éviter."""
    published = {(e["context"], e["dockerfile"]) for e in release_matrix()}
    missing = {}
    for path in (BASE, PROD):
        for name, service in services(path).items():
            target = build_target(service)
            if target and target not in published:
                missing[f"{path.name}:{name}"] = target
    assert not missing, (
        "services construits depuis les sources sans image publiée dans "
        f"release.yml : {missing}. Ajouter une entrée à la matrice "
        "build-and-push avec exactement ce couple (context, dockerfile)."
    )


def test_every_referenced_ghcr_image_is_released():
    """Miroir de la règle précédente, dans l'autre sens : un service qui
    référence une de nos images GHCR doit la trouver publiée. Sans cette
    règle, remplacer un `build:` par un `image:` (tâche 2) supprimerait le
    contrôle au lieu de le satisfaire."""
    published = {e["image"] for e in release_matrix()}
    missing = {}
    for path in (BASE, PROD):
        for name, service in services(path).items():
            match = OWN_IMAGE_RE.match(service.get("image") or "")
            if match and match.group(1) not in published:
                missing[f"{path.name}:{name}"] = match.group(1)
    assert not missing, f"images GHCR référencées mais jamais publiées : {missing}."


def test_prod_overlay_substitutes_every_build_with_an_image():
    """L'overlay de production annonce en en-tête servir des « images depuis
    GHCR (au lieu de build:) ». La propriété réelle qui compte n'est pas
    « l'overlay ajoute un `image:` » (la fusion Compose est additive : un
    `build:` du fichier de base survit tel quel à côté, cf. rapport SP-21
    Task 2) mais « la configuration résolue ne construit plus rien ».
    Sous la sémantique de fusion documentée de Compose, cette propriété
    équivaut exactement à « l'overlay déclare `image:` *et* réinitialise le
    `build:` hérité (`build: !reset null`) » — vérifié une fois à la main
    contre `docker compose … config` (cf. rapport), pas à chaque exécution
    de ce test source-only (contrainte : pas d'appel docker ici)."""
    base = services(BASE)
    prod = services(PROD)
    not_substituted = []
    not_reset = []
    for name, service in base.items():
        if not build_target(service):
            continue
        prod_service = prod.get(name) or {}
        if not prod_service.get("image"):
            not_substituted.append(name)
        elif not build_is_reset(prod_service):
            not_reset.append(name)
    introduced = [name for name, service in prod.items() if build_target(service)]
    assert not not_substituted, (
        "services encore construits depuis les sources en production : "
        f"{not_substituted}. Ajouter `image: ghcr.io/tlenenao/geostudio-"
        "<nom>:${GEOSTUDIO_VERSION:-latest}` dans docker-compose.prod.yml."
    )
    assert not not_reset, (
        "services avec une image de production mais dont le `build:` du "
        f"fichier de base n'est pas réinitialisé : {not_reset}. La fusion "
        "Compose est additive : ce `build:` hérité survivrait dans la "
        "configuration résolue. Ajouter `build: !reset null` à côté de "
        "`image:` dans docker-compose.prod.yml pour ces services."
    )
    assert not introduced, f"l'overlay de production introduit lui-même un build: {introduced}."


# Variables lues par le cœur mais légitimement absentes du compose de ce
# dépôt. Liste fermée : toute variable nouvelle est soit câblée, soit
# ajoutée ici avec sa raison — c'est cette contrainte qui a de la valeur.
ENV_WIRING_EXEMPTIONS = {
    # Couture de test : permet de lire des partitions CDC depuis le disque
    # local au lieu de S3 (tests analytiques). Jamais réglée en production.
    "S3_CDC_BUCKET_BASE_URI",
    # Lues par l'image mini-serveur de l'export autoporté (SP-18c), dont le
    # docker-compose est **généré** par build_standalone_bundle_zip et livré
    # dans le zip — pas celui de ce dépôt.
    "APPEXPORT_STANDALONE_DATA_DIR",
    "APPEXPORT_STANDALONE_RUNTIME_DIR",
}


def _string_literal(node: ast.AST) -> str | None:
    """Valeur si `node` est une constante chaîne littérale (`"CORE_FOO"`) —
    None pour tout le reste (f-string, concaténation, appel, nom non
    résolu)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    """Résout les affectations de niveau module d'une constante chaîne à un
    nom simple (`_ALLOWLIST_ENV = "CORE_FOO"`) — motif réel de
    `app/pipelines/egress.py`, `app/harvest/egress.py`, `app/alerts/egress.py`.
    Une seule passe sur le corps du module, sans suivi de ré-affectation ni
    de flux de contrôle : une deuxième affectation au même nom plus bas dans
    le fichier écrase la première (comme à l'exécution), une affectation à
    l'intérieur d'une fonction ou d'une classe n'est pas vue."""
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                value = _string_literal(node.value)
                if value is not None:
                    constants[target.id] = value
    return constants


def _is_os_attr(node: ast.AST, attr: str) -> bool:
    """Vrai pour `os.<attr>` — reconnaît seulement le nom de module littéral
    `os` (pas un alias d'import comme `import os as o`, pas `getattr(os,
    ...)`)."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == attr
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _env_key_node(node: ast.AST) -> ast.AST | None:
    """Si `node` est un appel/accès qui lit une variable d'environnement
    (`os.environ.get(KEY, ...)`, `os.getenv(KEY, ...)`, `os.environ[KEY]`),
    renvoie le nœud de la clé — sinon None."""
    if isinstance(node, ast.Call):
        func = node.func
        if _is_os_attr(func, "getenv") and node.args:
            return node.args[0]
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and _is_os_attr(func.value, "environ")
            and node.args
        ):
            return node.args[0]
        return None
    if isinstance(node, ast.Subscript) and _is_os_attr(node.value, "environ"):
        return node.slice
    return None


def core_env_vars() -> set[str]:
    """Toute variable d'environnement lue par `core/app/`, littéralement
    (`os.environ.get("CORE_FOO")`) ou par indirection via une constante de
    niveau module (`_ALLOWLIST_ENV = "CORE_FOO"` puis
    `os.environ.get(_ALLOWLIST_ENV)`) — motif des trois gardes d'egress SSRF
    (pipelines/harvest/alerts). Parcourt l'AST plutôt qu'une regex : une
    regex sur le texte ne peut pas voir qu'un nom désigne une constante,
    l'AST le peut. Limites assumées, pas couvertes : une valeur calculée
    (f-string, concaténation, retour de fonction), une indirection plus
    profonde qu'un nom simple (attribut d'objet, `getattr`, alias d'import
    de `os`), ou une clé passée par un nom réaffecté ailleurs qu'au niveau
    module. Un futur lecteur ne doit pas sur-faire confiance à cette
    fonction au-delà de ce périmètre."""
    found = set()
    for module in CORE_APP.rglob("*.py"):
        tree = ast.parse(module.read_text())
        constants = _module_string_constants(tree)
        for node in ast.walk(tree):
            key_node = _env_key_node(node)
            if key_node is None:
                continue
            literal = _string_literal(key_node)
            if literal is not None:
                found.add(literal)
            elif isinstance(key_node, ast.Name) and key_node.id in constants:
                found.add(constants[key_node.id])
    return found


def _wired_env_vars() -> set[str]:
    wired = set()
    for path in (BASE, PROD):
        for service in services(path).values():
            env = service.get("environment") or {}
            if isinstance(env, dict):
                wired |= set(env)
            elif isinstance(env, list):  # forme liste : "VAR=valeur"
                wired |= {item.split("=", 1)[0] for item in env}
            # Sinon (ex. `environment: !reset null` → sentinel RESET,
            # truthy mais non itérable) : traité comme absent plutôt que de
            # lever un TypeError sur `for item in env`.
    return wired


def test_every_core_env_var_is_wired_to_a_service():
    """Une variable lue par le cœur mais absente de l'environnement de tout
    service est un réglage inatteignable : l'opérateur la met dans son .env,
    rien ne change, aucun signal. C'est le mode d'échec de SP-17a, SP-17b,
    tileset3d — et de CORE_ETL_ENABLED, trouvée par cette règle.

    Limite assumée (revue finale SP-21, item 5) : `_wired_env_vars()` fait
    l'union de l'`environment:` de TOUS les services — la règle sait que la
    variable est câblée *quelque part*, jamais sur quel process précis. Elle
    a donc laissé passer `S3_EXPORTS_BUCKET`/`S3_APPEXPORTS_BUCKET`, lues par
    `core` (app/main.py, app/export/routes.py, app/reports/routes.py,
    app/appexport/routes.py) mais câblées jusqu'ici seulement sur
    `worker`/`export-worker`/`appexport-runtime-builder` — sans effet visible
    puisque le défaut applicatif coïncidait avec la valeur du compose, mais
    un accident du même genre que cette règle existe pour éliminer. Un
    lecteur futur ne doit pas sur-interpréter un test vert ici comme « câblé
    sur le bon process » : il faudrait une carte site-de-lecture→service
    pour ça, qui n'existe pas."""
    unwired = core_env_vars() - _wired_env_vars() - ENV_WIRING_EXEMPTIONS
    assert not unwired, (
        f"variables lues par core/app/ et câblées sur aucun service : "
        f"{sorted(unwired)}. Les ajouter à l'`environment` du service qui "
        "les lit, ou à ENV_WIRING_EXEMPTIONS avec la raison écrite."
    )


def compose_substitutions() -> set[str]:
    """Tout nom apparaissant dans une substitution `${VAR}` du compose de
    base ou de l'overlay de production."""
    substitutions = set()
    for path in (BASE, PROD):
        substitutions |= set(re.findall(r"\$\{([A-Z0-9_]+)", path.read_text()))
    return substitutions


def documented_env_vars(include_commented: bool = True) -> set[str]:
    """Noms de variable présents dans .env.example. Par défaut (
    `include_commented=True`), voit aussi les lignes commentées
    (`#S3_CDC_BUCKET=…`) — la convention établie tâche 4 pour « découvrable,
    pas réglable ». `include_commented=False` ne renvoie que les lignes
    ACTIVES (`VAR=valeur`, sans `#` en tête) : celles qu'un opérateur lira
    comme un réglage possible."""
    pattern = r"^#?\s*([A-Z0-9_]+)=" if include_commented else r"^([A-Z0-9_]+)="
    return set(re.findall(pattern, ENV_EXAMPLE.read_text(), re.MULTILINE))


def test_every_compose_substitution_is_documented():
    """Toute valeur que l'opérateur doit fournir (`${VAR}`) doit être
    découvrable dans .env.example. La règle ne porte QUE sur les
    substitutions : les valeurs dérivées calculées dans le compose
    (DATABASE_URL, OTEL_*) n'ont rien à y faire — les y mettre inviterait à
    les régler à la main."""
    undocumented = compose_substitutions() - documented_env_vars()
    assert not undocumented, (
        f"substitutions de compose absentes de .env.example : {sorted(undocumented)}."
    )


# Noms activement documentés dans .env.example (donc, aux yeux d'un
# opérateur, réglables) mais légitimement substitués nulle part dans aucun
# des deux compose. Liste fermée, comme ENV_WIRING_EXEMPTIONS/
# BACKUP_EXCLUDED_BUCKETS ci-dessus : une nouvelle entrée est une décision
# écrite, jamais un oubli qui se glisse en silence.
# Vide depuis SP-45 (GAP-41) : MARTIN_SECRET, seule occupante depuis SP-21,
# a été retirée des 3 emplacements (bootstrap-env.sh, .env.example, ici)
# plutôt que câblée — l'accès à Martin est déjà protégé par
# admin-auth@docker (forwardAuth Traefik), une seconde protection par
# secret partagé aurait été redondante. Le mécanisme reste déclaré, pas
# retiré : point d'extension pour une future dérive de même classe (nom
# documenté, jamais consommé).
DOCUMENTED_BUT_UNWIRED_EXEMPTIONS: set[str] = set()


def test_every_documented_env_var_is_wired_or_declared_inert():
    """Sens inverse de la règle précédente (revue finale SP-21, item 3) :
    `test_every_compose_substitution_is_documented` ne vérifie que
    ${VAR} ⇒ documenté. Rien ne vérifiait documenté ⇒
    substitué-ou-explicitement-inerte — la direction qui compte pour
    l'illusion « documenté donc câblé » (le nom existe dans .env.example,
    donc l'opérateur croit pouvoir le régler).

    Deux des six instances de la classe de bug que ce fichier existe pour
    arrêter ont exactement cette forme (un nom actif de .env.example
    substitué nulle part) plutôt que la forme « câblé sur le mauvais
    service » des autres : `CORE_ETL_ENABLED` (la découverte fondatrice qui
    a fait naître ce fichier de tests) et les identifiants/buckets S3 +
    `MARTIN_SECRET` corrigés par l'item 2 de cette même revue finale (7 noms
    passés en ligne commentée, 1 exempté ci-dessus). Sans cette règle,
    chacune de ces découvertes restait un jugement humain non outillé,
    aussi reproductible à l'identique par le prochain bucket ou identifiant
    documenté par erreur comme réglable.

    Une ligne commentée (`#S3_CDC_BUCKET=…`) n'est PAS une ligne active :
    `documented_env_vars(include_commented=False)` ne la voit pas, donc le
    correctif de l'item 2 (commenter ces lignes) satisfait cette règle au
    lieu d'avoir besoin d'une exemption — c'est précisément la distinction
    que `DOCUMENTED_BUT_UNWIRED_EXEMPTIONS` n'a pas besoin de porter pour
    elles."""
    active = documented_env_vars(include_commented=False)
    unwired = active - compose_substitutions() - DOCUMENTED_BUT_UNWIRED_EXEMPTIONS
    assert not unwired, (
        f"noms actifs (non commentés) de .env.example jamais substitués "
        f"dans un compose : {sorted(unwired)}. Soit ce nom doit être câblé "
        "(`${...}` dans docker-compose.yml/.prod.yml), soit il est "
        "légitimement inerte et doit passer en ligne commentée "
        "(`#VAR=valeur`, convention tâche 4) ou rejoindre "
        "DOCUMENTED_BUT_UNWIRED_EXEMPTIONS avec sa raison écrite."
    )


def test_martin_secret_is_fully_removed():
    """GAP-41 : MARTIN_SECRET était générée par bootstrap-env.sh et
    documentée dans .env.example sans jamais être consommée par le service
    martin (docker-compose.yml) — dérive connue depuis SP-1d3, jamais
    corrigée avant ce test. Retirée plutôt que câblée : l'accès à Martin
    est déjà protégé par admin-auth@docker (forwardAuth Traefik), une
    seconde protection par secret partagé serait redondante et n'aurait
    jamais rien protégé de plus (spec SP-45 §2)."""
    assert "MARTIN_SECRET" not in ENV_EXAMPLE.read_text()
    assert "MARTIN_SECRET" not in BOOTSTRAP_ENV_SH.read_text()
    assert "MARTIN_SECRET" not in DOCUMENTED_BUT_UNWIRED_EXEMPTIONS


def _resolve_effective_value(raw: str, var: str) -> str:
    """Valeur que le service `core` recevrait pour `var` si aucune variable
    d'environnement n'était positionnée (aucun `.env` fourni) — c'est-à-dire
    la valeur *résolue*, pas seulement la syntaxe de substitution.

    Gère `${VAR}`/`${VAR:-défaut}` (résout au défaut, `""` s'il n'y en a
    pas) ET le cas où la valeur est écrite en dur dans le compose sans
    passer par aucune substitution (`CORE_ENV: development` littéral) — un
    grep ciblant uniquement `${VAR:-...}` laisserait passer ce second cas en
    silence. Revue finale SP-26 round 2 (M1) : c'est exactement cette
    seconde forme de régression que l'ancienne version de ce test (basée sur
    `_substitution_default`, qui ne reconnaissait que `${VAR:-...}`) ne
    pouvait pas attraper — un `CORE_ENV: development` codé en dur aurait
    fait retourner `None` à l'ancien extracteur, et `None != "development"`
    passait le test."""
    match = re.fullmatch(rf"\$\{{{var}(:-(?P<default>[^}}]*))?\}}", raw)
    if match:
        return match.group("default") or ""
    return raw


def test_core_env_default_cannot_silently_satisfy_the_mock_mode_guard():
    """Revue finale SP-26 (I2) : le service `core` de docker-compose.yml
    câblait CORE_AUTH_MODE avec un défaut "mock" ET CORE_ENV avec un défaut
    "development" — quiconque démarre ce fichier sans `.env` obtenait donc
    les deux par défaut, et la garde de démarrage
    core/app/auth/dependency.py::reject_mock_outside_development() (qui ne
    refuse `mock` que si CORE_ENV != "development") ne se déclenchait
    jamais, exactement le déploiement qu'elle existe pour attraper. Épingle
    que CORE_ENV ne résout plus à une valeur qui satisfasse la garde tant
    que CORE_AUTH_MODE peut par défaut valoir "mock" — le flux documenté
    (.env.example -> scripts/bootstrap-env.sh -> .env) reste inchangé, lui,
    puisqu'il fixe CORE_ENV=development explicitement dans le `.env`
    généré, jamais via ce défaut de compose.

    Assertion sur la valeur RÉSOLUE (`_resolve_effective_value`), pas
    seulement sur la syntaxe `${CORE_ENV:-...}` — sans quoi un
    `CORE_ENV: development` codé en dur directement dans docker-compose.yml
    (au lieu d'une substitution) rouvrirait exactement le défaut d'origine
    sans faire échouer ce test (M1, revue finale SP-26 round 2)."""
    core_env = services(BASE)["core"]["environment"]
    auth_mode_raw = core_env["CORE_AUTH_MODE"]
    env_raw = core_env["CORE_ENV"]
    auth_mode_effective = _resolve_effective_value(auth_mode_raw, "CORE_AUTH_MODE")
    env_effective = _resolve_effective_value(env_raw, "CORE_ENV")
    assert auth_mode_effective == "mock", (
        f"ce test suppose CORE_AUTH_MODE résolu à 'mock' (raw={auth_mode_raw!r}) "
        "pour que le scénario testé (aucun .env fourni) soit réel."
    )
    assert env_effective != "development", (
        "CORE_ENV résout à 'development' pour le service `core` quand aucun "
        ".env n'est fourni (que ce soit via un défaut de substitution "
        "${CORE_ENV:-...} ou une valeur littérale codée en dur) : combiné au "
        "défaut 'mock' de CORE_AUTH_MODE ci-dessus, ceci désarme "
        "silencieusement reject_mock_outside_development()."
    )


CI = REPO / ".github/workflows/ci.yml"


def _postgres_run_flags(workflow: pathlib.Path, job: str) -> set[str]:
    """Flags `-c cle=valeur` passés à l'image Postgres par l'étape « Start
    Postgres » d'un job donné. Lit le `run:` de l'étape plutôt que d'exécuter
    quoi que ce soit — même parti que le reste du fichier."""
    doc = yaml.safe_load(workflow.read_text())
    steps = doc["jobs"][job]["steps"]
    scripts = [st.get("run", "") for st in steps if st.get("name") == "Start Postgres"]
    assert scripts, f"{workflow.name}: le job {job} n'a plus d'étape « Start Postgres »"
    flags = set()
    for script in scripts:
        flags |= set(re.findall(r"-c\s+([A-Za-z0-9_]+=[^\s\\]+)", script))
    return flags


def test_release_gate_starts_postgres_like_ci():
    """La porte de test de `release.yml` doit démarrer Postgres avec au moins
    les réglages du job `core` de `ci.yml`. Sinon la CI est verte et la
    release échoue — ou, pire, passe en n'exécutant pas les mêmes tests.

    Écrite en réaction à un échec réel : le tag `v0.1.0` a échoué sur
    `logical decoding requires wal_level >= logical`, deux tests
    `@pytest.mark.postgis` du consommateur CDC (SP-11) que `ci.yml` exécute et
    que cette porte n'exécutait pas, faute des flags. La dérive était
    invisible parce que la dernière release taguée (`v0.1.0-rc1`, 2026-07-15)
    précède ces tests : la porte ne les avait jamais rencontrés. C'est la
    forme « chemin de release jamais exercé » de la classe de bug que ce
    fichier existe pour arrêter, un cran au-dessus du compose."""
    ci_flags = _postgres_run_flags(CI, "core")
    release_flags = _postgres_run_flags(RELEASE, "test-gate")
    missing = ci_flags - release_flags
    assert not missing, (
        f"release.yml (test-gate) démarre Postgres sans les réglages que "
        f"ci.yml (core) lui donne : {sorted(missing)}. La porte de release "
        "n'exécute donc pas les mêmes tests que la CI."
    )


# Buckets volontairement hors sauvegarde, avec la raison. `exports` et
# `appexports` ne contiennent que des artefacts régénérables : un PDF de
# rapport ou un bundle d'app se re-demande en un clic.
BACKUP_EXCLUDED_BUCKETS = {
    "S3_EXPORTS_BUCKET",
    "S3_APPEXPORTS_BUCKET",
}


def test_backup_covers_every_bucket_the_core_uses():
    """Un bucket utilisé par le cœur et absent de la sauvegarde produit le
    pire mode d'échec possible : après restauration, l'item réapparaît
    intact en pointant sur une clé S3 disparue — cassé pour toujours, sans
    erreur au moment de la restauration. Le cas réel est `tileset3d` : un
    tileset uploadé est un objet S3 jamais extrait, sans autre copie."""
    used = {v for v in core_env_vars() if v.startswith("S3_") and v.endswith("_BUCKET")}
    mirrored = set(re.findall(r"\$\{(S3_[A-Z0-9_]*_BUCKET)", BACKUP_SH.read_text()))
    missing = used - mirrored - BACKUP_EXCLUDED_BUCKETS
    assert not missing, (
        f"buckets utilisés par le cœur et jamais sauvegardés : {sorted(missing)}. "
        "Les ajouter à la boucle de miroir de deploy/backup/backup.sh, ou à "
        "BACKUP_EXCLUDED_BUCKETS avec la raison écrite."
    )


# Mots-clés de tags mouvants : comme `latest`, ils avancent à chaque nouvelle
# publication sans jamais changer de nom — même classe de danger.
FLOATING_WORD_TAGS = {
    "latest",
    "stable",
    "edge",
    "main",
    "master",
    "dev",
    "nightly",
    "release",
}

# Un tag « flottant » : v3.0 suit tous les patchs à venir, 24.0 aussi, et un
# tag majeur seul (v3, 3) suit en plus tous les mineurs à venir. La règle est
# une liste noire volontaire (absence de tag, mot-clé mouvant, majeur/mineur
# flottant) et non une exigence de forme : des tags parfaitement pinnés ne
# sont pas semver (minio publie RELEASE.2025-09-07T16-13-09Z, pgbouncer
# 1.22.1-p0), et une exigence de forme les rejetterait à tort.
FLOATING_TAG_RE = re.compile(r"^v?\d+(\.\d+)?$")


def unpinned_reason(image: str) -> str | None:
    """Classe une référence d'image Docker telle qu'écrite dans un fichier
    compose (donc potentiellement porteuse d'une substitution `${...}` non
    résolue) : None si elle est pinnée de façon reproductible, une raison
    lisible sinon. Extrait de `test_images_are_pinned` pour être testable
    directement sur une chaîne, sans passer par un fichier compose.

    Trois cas particuliers, chacun corrigeant un écart entre le docstring de
    `test_images_are_pinned` et ce qu'elle vérifiait réellement avant ce
    correctif (aucun des trois n'était vivant dans ce dépôt) :

    - une image derrière une substitution (`${VAR}`) n'est exemptée que si
      c'est une des nôtres (`OWN_IMAGE_RE`, pinnée par le tag de release CI) —
      une image tierce hypothétique derrière une variable reste un tag fourni
      par l'opérateur, invérifiable ici, donc signalée plutôt qu'exemptée ;
    - un digest (`image@sha256:…`) est le pin le plus fort possible, accepté
      sans lire de tag ;
    - le tag n'est résolu que dans le dernier segment de chemin, pour qu'un
      hôte de registre avec port (`host:5000/img`) ne fasse pas passer une
      image sans tag pour pinnée.
    """
    if "${" in image:
        if OWN_IMAGE_RE.match(image):
            return None  # nos propres images : pinnées par le tag de release
        return f"{image} (image tierce derrière une substitution, invérifiable ici)"
    if "@sha256:" in image:
        return None  # digest : le pin le plus fort possible
    last_segment = image.rpartition("/")[2]
    _, _, tag = last_segment.rpartition(":")
    if tag == last_segment or not tag:
        return f"{image} (aucun tag)"
    if tag in FLOATING_WORD_TAGS:
        return f"{image} ({tag})"
    if FLOATING_TAG_RE.fullmatch(tag):
        kind = "mineur flottant" if "." in tag else "majeur flottant"
        return f"{image} ({kind})"
    return None


def test_images_are_pinned():
    """Une image sans tag, en `latest`, en tag mouvant (`stable`/`edge`/…),
    ou pinnée au majeur/mineur, change sous les pieds de l'opérateur : deux
    `docker compose pull` à un mois d'écart ne donnent pas la même stack, et
    un incident devient irreproductible. Un digest (`@sha256:…`) est
    toujours accepté — c'est le pin le plus fort. Seule une des nôtres
    (`ghcr.io/<owner>/geostudio-*`) est exemptée derrière une substitution
    `${VAR}`, parce qu'elle est alors pinnée par le tag de release CI plutôt
    que par ce fichier — une image tierce derrière une substitution reste un
    tag fourni par l'opérateur, invérifiable ici, et donc signalée."""
    unpinned = {}
    for path in (BASE, PROD):
        for name, service in services(path).items():
            image = service.get("image")
            if not image:
                continue
            reason = unpinned_reason(image)
            if reason:
                unpinned[f"{path.name}:{name}"] = reason
    assert not unpinned, (
        f"images non pinnées : {unpinned}. Résoudre le tag exact contre le "
        "registre — jamais l'inventer (précédent SP-15d : qgis/qgis:latest "
        "pointait vers un build 4.3.0-master instable)."
    )


# Les neuf références d'images tierces réellement présentes dans les deux
# compose, recopiées telles quelles. Le durcissement du regex flottant est
# la seule chose qui pourrait les rejeter à tort : aucune n'est du semver
# canonique (`RELEASE.2025-…`, `1.22.1-p0`), et le chemin de registre
# multi-segment (`ghcr.io/maplibre/…`) est précisément ce que la résolution
# du tag par dernier segment doit traverser sans se tromper.
@pytest.mark.parametrize(
    "image",
    [
        "minio/minio:RELEASE.2025-09-07T16-13-09Z",
        "edoburu/pgbouncer:1.22.1-p0",
        "ghcr.io/maplibre/martin:v0.18.0",
        "ghcr.io/developmentseed/titiler:0.18.4",
        "grafana/otel-lgtm:0.11.4",
        "prometheuscommunity/postgres-exporter:v0.20.1",
        "traefik:v3.0.4",
        "quay.io/keycloak/keycloak:24.0.5",
        "tailscale/tailscale:v1.102.3",
    ],
)
def test_unpinned_reason_accepts_real_pinned_tags(image):
    assert unpinned_reason(image) is None


def test_unpinned_reason_registry_port_is_not_read_as_a_tag():
    """Fix 1 : `host:5000/img` sans tag doit être signalé comme non pinné,
    pas silencieusement accepté parce que `5000/img` ressemble à un tag."""
    reason = unpinned_reason("myregistry.example.com:5000/myimage")
    assert reason is not None
    assert "aucun tag" in reason


@pytest.mark.parametrize("image", ["myimage:3", "myimage:v3"])
def test_unpinned_reason_flags_major_only_tags(image):
    """Fix 2 : un tag majeur seul (`:3`, `:v3`) flotte sur tous les mineurs
    et patchs à venir, tout comme `:3.0` flotte sur tous les patchs."""
    assert unpinned_reason(image) is not None


@pytest.mark.parametrize(
    "image",
    [
        "myimage:stable",
        "myimage:edge",
        "myimage:main",
        "myimage:master",
        "myimage:dev",
        "myimage:nightly",
        "myimage:release",
    ],
)
def test_unpinned_reason_flags_word_based_moving_tags(image):
    """Fix 2 : ces mots-clés bougent sous les pieds de l'opérateur exactement
    comme `latest`, que la règle rejette déjà par son nom."""
    assert unpinned_reason(image) is not None


def test_unpinned_reason_accepts_digest_pin():
    """Un pin par digest est le pin le plus fort possible — toujours
    accepté, même si aucune image du dépôt n'en utilise à ce jour."""
    assert (
        unpinned_reason(
            "myimage@sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        is None
    )


def test_unpinned_reason_rejects_third_party_image_behind_substitution():
    """Fix 3 : seules nos propres images ghcr.io/<owner>/geostudio-* sont
    pinnées par le tag de release et donc exemptées ici — une image tierce
    hypothétique derrière une substitution reste un tag fourni par
    l'opérateur, impossible à vérifier depuis ce fichier, et doit être
    signalée plutôt que silencieusement acceptée."""
    reason = unpinned_reason("somevendor/something:${SOMEVENDOR_TAG}")
    assert reason is not None


def test_unpinned_reason_accepts_own_image_behind_substitution():
    """Miroir du cas précédent : une de nos propres images GHCR derrière une
    substitution reste exemptée, comme avant ce fix."""
    assert unpinned_reason("ghcr.io/tlenenao/geostudio-core:${GEOSTUDIO_VERSION:-latest}") is None


# Revue finale SP-26 (C1) : core/Dockerfile (service `worker`, même image que
# `core`) et deploy/qgis-worker/Dockerfile se passent des fichiers via le
# volume nommé `etl-scratch:/scratch` (docker-compose.yml) —
# core/app/pipelines/runtime.py y écrit `in.gpkg` comme l'utilisateur `app`,
# le sidecar QGIS y écrit `out.gpkg` comme l'utilisateur `qgis`. Ces deux
# tests figent statiquement le correctif (vérifié empiriquement en session :
# build réel des deux images, `id -u` comparé, écriture croisée réussie dans
# les deux ordres de démarrage possibles) pour qu'une future modification de
# l'un des deux Dockerfiles ne fasse pas diverger silencieusement les uid, ou
# ne retire pas la création de /scratch.

CORE_DOCKERFILE = REPO / "core" / "Dockerfile"
QGIS_DOCKERFILE = REPO / "deploy" / "qgis-worker" / "Dockerfile"


def _useradd_uid(dockerfile: pathlib.Path) -> str | None:
    match = re.search(r"useradd\s+[^\n]*--uid[= ]+(\d+)", dockerfile.read_text())
    return match.group(1) if match else None


def test_core_and_qgis_worker_pin_the_same_scratch_uid():
    core_uid = _useradd_uid(CORE_DOCKERFILE)
    qgis_uid = _useradd_uid(QGIS_DOCKERFILE)
    assert core_uid is not None, "core/Dockerfile doit fixer un --uid explicite pour `app`"
    assert qgis_uid is not None, (
        "deploy/qgis-worker/Dockerfile doit fixer un --uid explicite pour `qgis`"
    )
    assert core_uid == qgis_uid, (
        f"uid divergents entre core/Dockerfile (app={core_uid}) et "
        f"deploy/qgis-worker/Dockerfile (qgis={qgis_uid}) — le partage de "
        "fichiers via etl-scratch échouera en PermissionError selon l'ordre "
        "de démarrage des conteneurs."
    )


SCRATCH_DOCKERFILES = [
    pytest.param(CORE_DOCKERFILE, "app", id="core"),
    pytest.param(QGIS_DOCKERFILE, "qgis", id="qgis-worker"),
]


@pytest.mark.parametrize("dockerfile,user_name", SCRATCH_DOCKERFILES)
def test_dockerfile_creates_and_chowns_scratch_before_switching_user(dockerfile, user_name):
    """Généralisé en revue finale SP-26 round 2 (M2) : à l'origine, seul
    core/Dockerfile était épinglé ici — deploy/qgis-worker/Dockerfile porte
    exactement le même mkdir+chown de /scratch, tout aussi structurant pour
    le partage `etl-scratch` (test_core_and_qgis_worker_pin_the_same_scratch_uid
    juste au-dessus vérifie que les DEUX uid convergent, mais rien ne
    vérifiait jusqu'ici que le mkdir+chown de qgis-worker existe encore)."""
    text = dockerfile.read_text()
    mkdir_pos = text.find("mkdir -p /scratch")
    user_pos = text.find(f"\nUSER {user_name}")
    assert mkdir_pos != -1, f"{dockerfile} doit créer /scratch avant USER {user_name}"
    assert user_pos != -1, f"{dockerfile} doit passer USER {user_name}"
    assert mkdir_pos < user_pos, "/scratch doit être créé avant le passage non-root"
    chown_line = re.search(r"^RUN .*chown[^\n]*$", text, re.MULTILINE)
    assert chown_line is not None and "/scratch" in chown_line.group(0), (
        f"{dockerfile} doit chown /scratch vers l'utilisateur `{user_name}`"
    )


# ─── Gate admin-tools (Traefik /admin/<tool>) ──────────────────────────
#
# Revue finale du plan Traefik admin-tools (2026-09-01, finding I4) : aucune
# règle de ce fichier ne couvrait le câblage Traefik du gate — trois
# routeurs (martin/titiler/grafana) tous gardés par le même middleware
# forwardauth `admin-auth`, avec une exception délibérée pour grafana (pas
# de stripprefix, contrairement à martin/titiler — Grafana attend le
# préfixe conservé, vérifié empiriquement contre l'image réelle, cf.
# commentaire du service `otel-lgtm` dans docker-compose.yml). Rien ne
# vérifiait mécaniquement que cette exception reste correcte, que les trois
# routeurs restent bien gardés, ni que l'overlay prod ne diverge pas du
# fichier de base sur ces noms.

ADMIN_TOOL_ROUTERS = ("martin", "titiler", "grafana")


def _traefik_labels(service: dict) -> dict[str, str]:
    """`labels:` d'un service Traefik en dict `clé=valeur` — les labels
    Traefik n'ont jamais de `=` dans la clé elle-même, `split("=", 1)`
    suffit. `ComposeLoader` a déjà résolu `!override`/`!override […]` à une
    liste nue (cf. `_drop_tag` plus haut), donc `service["labels"]` est
    toujours une liste de chaînes ici, jamais un objet `!override`."""
    return dict(label.split("=", 1) for label in service.get("labels") or [])


def _router_middlewares(labels: dict[str, str], router: str) -> list[str]:
    raw = labels.get(f"traefik.http.routers.{router}.middlewares", "")
    return [m for m in raw.split(",") if m]


@pytest.mark.parametrize("compose", [BASE, PROD], ids=["base", "prod"])
def test_grafana_router_has_no_stripprefix_middleware(compose):
    """Exception délibérée à la recette martin/titiler (design admin-tools
    §3, vérifié contre `grafana/otel-lgtm:0.11.4` réel) : Grafana sert déjà
    ses assets avec le préfixe `/admin/grafana` conservé
    (GF_SERVER_SERVE_FROM_SUB_PATH=true) — un stripprefix Traefik devant lui
    casserait le routage. Aucun middleware `stripprefix` (quel que soit le
    service qui le DÉFINIT — Traefik fusionne les labels `@docker`
    globalement à travers tous les conteneurs, cf. docstring de
    `test_admin_auth_forwardauth_middleware_defined_exactly_once` — donc un
    `strip-admin-grafana` déclaré sur `martin` mais référencé par le
    routeur `grafana` échapperait à un scan limité à `otel-lgtm`) ne doit
    être référencé par le routeur grafana."""
    all_labels = {
        name: _traefik_labels(service) for name, service in services(compose).items()
    }
    stripprefix_middleware_names = {
        key.split(".")[3]
        for labels in all_labels.values()
        for key in labels
        if key.startswith("traefik.http.middlewares.") and ".stripprefix." in key
    }
    middlewares = _router_middlewares(all_labels["otel-lgtm"], "grafana")
    referenced_stripprefix = [
        m for m in middlewares if m.split("@", 1)[0] in stripprefix_middleware_names
    ]
    assert not referenced_stripprefix, (
        f"le routeur grafana ({compose.name}) référence un middleware "
        f"stripprefix ({referenced_stripprefix}) — Grafana attend le "
        "préfixe conservé, contrairement à martin/titiler."
    )


@pytest.mark.parametrize("compose", [BASE, PROD], ids=["base", "prod"])
@pytest.mark.parametrize("tool", ADMIN_TOOL_ROUTERS)
def test_admin_tool_router_is_gated_by_admin_auth(compose, tool):
    """Les trois outils (martin, titiler, grafana) doivent tous passer par
    le même gate — un routeur qui perdrait `admin-auth@docker` de sa liste
    de middlewares deviendrait accessible sans authentification admin,
    silencieusement (Traefik ne refuse pas de démarrer pour ça)."""
    service_name = "otel-lgtm" if tool == "grafana" else tool
    labels = _traefik_labels(services(compose)[service_name])
    middlewares = _router_middlewares(labels, tool)
    assert "admin-auth@docker" in middlewares, (
        f"le routeur {tool} ({compose.name}) doit référencer "
        f"admin-auth@docker dans ses middlewares, a trouvé : {middlewares}"
    )


@pytest.mark.parametrize("compose", [BASE, PROD], ids=["base", "prod"])
def test_admin_auth_forwardauth_middleware_defined_exactly_once(compose):
    """Le middleware `admin-auth` (forwardauth) n'est déclaré que sur le
    service `martin` — titiler/grafana le RÉFÉRENCENT
    (`admin-auth@docker` dans leurs `middlewares`) sans le redéfinir.
    Compose fusionne les labels Traefik globalement à travers tous les
    services d'un même provider (`@docker`) : une redéfinition sur un
    second service serait soit redondante soit, pire, silencieusement
    divergente (une autre `address`) selon l'ordre de découverte des
    conteneurs. Vérifie aussi que la seule définition existante pointe bien
    vers `/admin-tools/verify`, la cible réelle du forwardAuth Traefik
    (`core/app/admin_tools/routes.py::verify_admin_tool_session`)."""
    defining_services = {}
    for name, service in services(compose).items():
        labels = _traefik_labels(service)
        if "traefik.http.middlewares.admin-auth.forwardauth.address" in labels:
            defining_services[name] = labels["traefik.http.middlewares.admin-auth.forwardauth.address"]
    assert list(defining_services) == ["martin"], (
        f"le middleware admin-auth.forwardauth.address doit être défini "
        f"exactement une fois, sur le service martin — trouvé sur : "
        f"{sorted(defining_services)} ({compose.name})"
    )
    address = defining_services["martin"]
    assert address.endswith("/admin-tools/verify"), (
        f"admin-auth.forwardauth.address ({compose.name}) doit cibler "
        f"/admin-tools/verify, a trouvé : {address!r}"
    )


_TRAEFIK_NAME_RE = re.compile(r"^traefik\.http\.(routers|services|middlewares)\.([^.]+)\.")


def _traefik_names(labels: dict[str, str]) -> set[tuple[str, str]]:
    """Ensemble de couples (routers|services|middlewares, nom) référencés
    par un jeu de labels — pas les clés complètes : `entrypoints`,
    `priority`, `tls.certresolver` diffèrent légitimement entre base et
    prod (base seule a l'ACME letsencrypt, cf. commentaires !override dans
    docker-compose.prod.yml), seuls les NOMS doivent coïncider."""
    names = set()
    for key in labels:
        match = _TRAEFIK_NAME_RE.match(key)
        if match:
            names.add((match.group(1), match.group(2)))
    return names


def test_base_and_prod_agree_on_admin_tool_router_names():
    """Base et overlay prod redéfinissent entièrement `labels:` pour
    martin/titiler/grafana (`!override`, cf. commentaires en tête de chaque
    bloc dans docker-compose.prod.yml) : rien ne garantit mécaniquement que
    les deux copies gardent les mêmes noms de routeur/service/middleware —
    une faute de frappe dans l'un des deux fichiers désynchroniserait
    silencieusement le routage entre dev et prod (le routeur mal nommé
    n'existerait tout simplement pas, 404 silencieux)."""
    base_services = services(BASE)
    prod_services = services(PROD)
    for tool in ADMIN_TOOL_ROUTERS:
        service_name = "otel-lgtm" if tool == "grafana" else tool
        base_names = _traefik_names(_traefik_labels(base_services[service_name]))
        prod_names = _traefik_names(_traefik_labels(prod_services[service_name]))
        assert base_names == prod_names, (
            f"noms de routeur/service/middleware Traefik divergents pour "
            f"{tool} entre base et prod : seulement en base = "
            f"{sorted(base_names - prod_names)}, seulement en prod = "
            f"{sorted(prod_names - base_names)}"
        )


# ─── SP-42, lot infra critical (F-infra-ci-01 / F-infra-ci-02) ─────────


def test_bootstrap_env_generates_a_well_formed_core_secrets_master_key(tmp_path):
    """SP-42/F-infra-ci-01 (critical) : `scripts/bootstrap-env.sh` (et donc
    `scripts/install.sh`, qui l'invoque via `ensure_env_file()` puis ne
    référence plus jamais cette variable) ne générait aucune valeur pour
    `CORE_SECRETS_MASTER_KEY` — elle restait à la chaîne vide de
    `.env.example`, que `core/app/secrets/crypto.py::load_master_key()`
    refuse dès le premier appel de `create_app()` (`core/app/main.py`),
    avant même la connexion DB : le cœur crash-loop sur toute installation
    neuve suivant le flux documenté. Exécuté dans un répertoire jetable
    (jamais le `.env` réel du dépôt) reproduisant la structure attendue par
    le script (`scripts/bootstrap-env.sh` à côté de `.env.example`, appelé
    depuis la racine)."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(BOOTSTRAP_ENV_SH, tmp_path / "scripts" / "bootstrap-env.sh")
    shutil.copy(ENV_EXAMPLE, tmp_path / ".env.example")
    subprocess.run(
        ["bash", "scripts/bootstrap-env.sh"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    env_text = (tmp_path / ".env").read_text()
    match = re.search(r"^CORE_SECRETS_MASTER_KEY=(.*)$", env_text, re.MULTILINE)
    assert match is not None, ".env généré doit contenir CORE_SECRETS_MASTER_KEY"
    value = match.group(1).strip()
    assert value, "CORE_SECRETS_MASTER_KEY ne doit pas être vide après bootstrap-env.sh"
    try:
        decoded = base64.b64decode(value, validate=True)
    except Exception as exc:
        pytest.fail(f"CORE_SECRETS_MASTER_KEY générée n'est pas du base64 valide : {exc}")
    assert len(decoded) == 32, (
        "CORE_SECRETS_MASTER_KEY doit décoder en 32 octets (exigence de "
        "core/app/secrets/crypto.py::load_master_key()), a décodé en "
        f"{len(decoded)} octet(s)"
    )


def test_keycloak_router_carries_security_and_rate_limit_middlewares():
    """SP-42/F-infra-ci-02 (critical) : le routeur `keycloak` en production
    ne portait aucun middleware — ni `security-headers@docker` (en-têtes de
    sécurité sur la page de login : HSTS, nosniff, frame-deny, referrer-
    policy), ni `rate-limit@docker` (frein de débit sur l'endpoint de
    connexion/token OIDC, `POST .../protocol/openid-connect/token`) —
    contrairement à tous les autres routeurs publics de cet overlay
    (core/shell/martin/titiler/grafana). Keycloak n'est routé par Traefik
    qu'en production — le fichier de base ne l'expose que par le port hôte
    8180, sans aucun label Traefik — ce test ne porte donc que sur l'overlay
    prod, contrairement aux règles admin-tools ci-dessus qui couvrent aussi
    `base`."""
    labels = _traefik_labels(services(PROD)["keycloak"])
    middlewares = _router_middlewares(labels, "keycloak")
    for required in ("security-headers@docker", "rate-limit@docker"):
        assert required in middlewares, (
            f"le routeur keycloak (prod) doit référencer {required} dans "
            f"ses middlewares, a trouvé : {middlewares}"
        )


def test_keycloak_realm_enables_brute_force_protection():
    """SP-42/F-infra-ci-02 (critical, second volet) :
    `deploy/keycloak/geostudio-realm.json` déclarait `bruteForceProtected:
    false` — aucune protection native contre le bourrage d'identifiants
    côté Keycloak lui-même, indépendamment du rate-limit Traefik vérifié
    ci-dessus (défense en profondeur : le edge et l'IdP protègent contre
    des choses différentes). Seul ce bit d'activation change ici — tous les
    réglages associés que ce realm porte déjà (`failureFactor: 30`,
    `maxFailureWaitSeconds: 900`, `minimumQuickLoginWaitSeconds: 60`,
    `waitIncrementSeconds: 60`, `quickLoginCheckMilliSeconds: 1000`,
    `maxDeltaTimeSeconds: 43200`) sont les valeurs par défaut de Keycloak
    lui-même (export d'un realm jamais réglé sur ce point) : ce garde-fou
    n'introduit aucune politique de verrouillage plus agressive.
    `permanentLockout` doit rester `false` — un verrouillage permanent
    (nécessitant une intervention admin pour débloquer un compte) serait
    une décision produit distincte, non prise ici."""
    realm = json.loads(KEYCLOAK_REALM_JSON.read_text())
    assert realm.get("bruteForceProtected") is True, (
        "deploy/keycloak/geostudio-realm.json doit activer "
        "bruteForceProtected — aucune protection anti-bourrage native sur "
        "l'endpoint de login sinon."
    )
    assert realm.get("permanentLockout") is False, (
        "permanentLockout ne doit pas passer à true par ce garde-fou — "
        "verrouillage permanent = décision produit distincte, hors périmètre."
    )


def test_traefik_has_a_restart_policy():
    """GAP-79 : traefik (point d'entrée public unique) était le seul
    service durablement actif sans restart:, dans docker-compose.yml comme
    dans son overlay prod (hérité, non redéclaré) — un crash de l'ingress
    laissait toute l'instance publique indisponible jusqu'à intervention
    manuelle."""
    assert services(BASE)["traefik"].get("restart") == "unless-stopped"


SEO_ROUTERS = ("seo-static", "seo-bots")


@pytest.mark.parametrize("compose", [BASE, PROD], ids=["base", "prod"])
@pytest.mark.parametrize("router", SEO_ROUTERS)
def test_seo_router_priority_above_shell_catch_all_and_distinct_from_admin(compose, router):
    """SP-55 GAP-07 (chantier 4.10) : sitemap.xml/robots.txt/aperçu social
    doivent gagner contre le catch-all shell (priorité 1) — une régression
    de priorité les ferait silencieusement absorber par le SPA (200 sur le
    HTML de l'app plutôt que le XML/texte/HTML minimal attendu). Distincte
    aussi de 15 (routeurs admin martin/titiler/grafana) : Traefik ne
    refuserait pas de démarrer sur une collision, le comportement de
    départage deviendrait juste non documenté."""
    labels = _traefik_labels(services(compose)["core"])
    priority = int(labels[f"traefik.http.routers.{router}.priority"])
    assert priority > 1, f"{router} ({compose.name}) doit primer sur le catch-all shell (priorité 1)"
    assert priority != 15, f"{router} ({compose.name}) ne doit pas collisionner avec les routeurs admin (15)"


@pytest.mark.parametrize("compose", [BASE, PROD], ids=["base", "prod"])
@pytest.mark.parametrize("router", SEO_ROUTERS)
def test_seo_router_is_not_gated_by_admin_auth(compose, router):
    """Contrairement aux routeurs admin (martin/titiler/grafana), les
    routes SEO sont PUBLIQUES par construction (sitemap/robots/aperçu
    social sont faits pour être lus par des robots anonymes) — une
    régression qui leur ajouterait admin-auth@docker les rendrait
    inaccessibles à ces robots, silencieusement (Traefik démarre quand
    même)."""
    labels = _traefik_labels(services(compose)["core"])
    middlewares = _router_middlewares(labels, router)
    assert "admin-auth@docker" not in middlewares, (
        f"{router} ({compose.name}) ne doit jamais référencer admin-auth@docker "
        f"(route publique), a trouvé : {middlewares}"
    )


# ─── SP-48/GAP-72 : CSP calculée dynamiquement, poussée par Traefik via un
# provider fichier additif au provider Docker existant ───────────────────


def test_csp_dynamic_conf_volume_is_shared_between_worker_and_traefik():
    assert "csp-dynamic-conf" in (load_yaml(BASE).get("volumes") or {})
    worker_volumes = services(BASE)["worker"].get("volumes") or []
    traefik_volumes = services(BASE)["traefik"].get("volumes") or []
    assert any("csp-dynamic-conf" in v for v in worker_volumes), (
        f"worker (base) doit monter csp-dynamic-conf, a trouvé : {worker_volumes}"
    )
    assert any("csp-dynamic-conf" in v for v in traefik_volumes), (
        f"traefik (base) doit monter csp-dynamic-conf, a trouvé : {traefik_volumes}"
    )


def test_traefik_command_enables_file_provider_with_watch():
    command = services(BASE)["traefik"]["command"]
    assert "--providers.file.watch=true" in command
    assert any(c.startswith("--providers.file.directory=") for c in command)


def test_prod_traefik_command_also_enables_file_provider():
    """docker-compose.prod.yml déclare son propre bloc traefik: command: —
    la fusion Compose remplace cette liste entièrement plutôt que de la
    concaténer (vérifié contre `docker compose config` réel, cf. ledger de
    session) : ce bloc doit donc recopier --providers.docker=true/
    --entrypoints.web.address=:80 en plus des 2 nouvelles entrées, sinon
    l'overlay prod perdrait silencieusement le provider Docker (piège
    CLAUDE.md n°2)."""
    command = services(PROD)["traefik"]["command"]
    assert "--providers.file.watch=true" in command
    assert any(c.startswith("--providers.file.directory=") for c in command)
    assert "--providers.docker=true" in command, (
        "l'overlay prod ne doit jamais perdre --providers.docker=true en "
        "ajoutant le provider fichier (command: remplace, ne fusionne pas)"
    )


def test_prod_traefik_volumes_also_carries_csp_dynamic_conf():
    """docker-compose.prod.yml déclare traefik: volumes: !override — un
    remplacement intégral (pas une fusion) : csp-dynamic-conf doit donc être
    redéclaré explicitement ici, sinon traefik (prod) perdrait
    silencieusement l'accès au fragment de CSP calculée que worker écrit."""
    traefik_volumes = services(PROD)["traefik"].get("volumes") or []
    assert any("csp-dynamic-conf" in v for v in traefik_volumes), (
        f"traefik (prod) doit monter csp-dynamic-conf, a trouvé : {traefik_volumes}"
    )


CSP_DYNAMIC_ROUTERS = (
    (BASE, "core"),
    (BASE, "shell"),
    (BASE, "seo-static"),
    (BASE, "seo-bots"),
    (BASE, "martin"),
    (BASE, "titiler"),
    (BASE, "grafana"),
    (PROD, "core"),
    (PROD, "shell"),
    (PROD, "seo-static"),
    (PROD, "seo-bots"),
    (PROD, "martin"),
    (PROD, "titiler"),
    (PROD, "grafana"),
    (PROD, "keycloak"),
)


@pytest.mark.parametrize(("compose_path", "router"), CSP_DYNAMIC_ROUTERS)
def test_every_router_carrying_security_headers_also_carries_csp_dynamic(compose_path, router):
    """Chaque routeur qui référence déjà security-headers@docker aujourd'hui
    doit gagner csp-dynamic@file — même périmètre, pas une nouvelle
    décision de portée (GAP-72 ne change pas QUI est protégé, seulement
    COMMENT la CSP est calculée). `grafana` est un routeur défini sur le
    service `otel-lgtm` (labels), d'où la recherche par nom de routeur
    plutôt que par nom de service, comme test_grafana_router_has_no_stripprefix_middleware
    ci-dessus."""
    all_labels = {name: _traefik_labels(svc) for name, svc in services(compose_path).items()}
    labels = next(
        l for l in all_labels.values() if f"traefik.http.routers.{router}.middlewares" in l
    )
    middlewares = _router_middlewares(labels, router)
    assert "security-headers@docker" in middlewares, (
        f"{router} ({compose_path.name}) doit toujours référencer "
        f"security-headers@docker (non-régression), a trouvé : {middlewares}"
    )
    assert "csp-dynamic@file" in middlewares, (
        f"{router} ({compose_path.name}) doit référencer csp-dynamic@file, "
        f"a trouvé : {middlewares}"
    )


def test_prod_overlay_no_longer_hardcodes_a_static_csp_header():
    """SP-48/GAP-72 : la valeur Content-Security-Policy-Report-Only fixée en
    dur sur security-headers (docker-compose.prod.yml, posée à SP-26/3.3)
    est retirée — remplacée par la valeur calculée dynamiquement portée par
    csp-dynamic@file (cf. tests ci-dessus)."""
    labels = _traefik_labels(services(PROD)["core"])
    assert not any(
        "Content-Security-Policy" in k and "customResponseHeaders" in k for k in labels
    ), "la CSP doit venir de csp-dynamic@file, plus d'une valeur statique sur security-headers"


def test_prod_overlay_defaults_csp_mode_to_enforce():
    env = services(PROD)["worker"].get("environment") or {}
    assert env.get("CORE_CSP_MODE") == "${CORE_CSP_MODE:-enforce}", (
        f"worker (prod) doit fixer CORE_CSP_MODE à enforce par défaut "
        f"(rollback opérateur possible via .env.prod), a trouvé : {env.get('CORE_CSP_MODE')!r}"
    )


def test_base_worker_defaults_csp_mode_to_report_only():
    env = services(BASE)["worker"].get("environment") or {}
    assert env.get("CORE_CSP_MODE") == "${CORE_CSP_MODE:-report-only}", (
        f"worker (base) doit fixer CORE_CSP_MODE à report-only par défaut "
        f"(GAP-72 ne visait que l'overlay prod), a trouvé : {env.get('CORE_CSP_MODE')!r}"
    )


def test_shell_nginx_conf_no_longer_hardcodes_its_own_csp():
    """SP-48/GAP-72 blocage 4 : shell/nginx.conf portait sa propre valeur
    Content-Security-Policy-Report-Only, reconnue fausse par son propre
    commentaire pour la topologie 'ports publiés directement' du fichier
    de base — retirée plutôt que resynchronisée indéfiniment avec la
    valeur Traefik (spec §3). Traefik (base et prod, cf. tests ci-dessus)
    est désormais la seule source de CSP dans toute topologie qui passe
    par lui — la seule documentée par ce dépôt."""
    content = (REPO / "shell/nginx.conf").read_text()
    assert "Content-Security-Policy" not in content
