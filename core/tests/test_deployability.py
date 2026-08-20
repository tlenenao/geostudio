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
"""
import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
BASE = REPO / "docker-compose.yml"
PROD = REPO / "docker-compose.prod.yml"
RELEASE = REPO / ".github/workflows/release.yml"
ENV_EXAMPLE = REPO / ".env.example"
BACKUP_SH = REPO / "deploy/backup/backup.sh"
CORE_APP = REPO / "core/app"

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
    assert not missing, (
        f"images GHCR référencées mais jamais publiées : {missing}."
    )


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
    assert not introduced, (
        f"l'overlay de production introduit lui-même un build: {introduced}."
    )


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

ENV_READ_RE = re.compile(
    r"os\.environ(?:\.get\(|\[)\s*[\"']([A-Z0-9_]+)"
    r"|os\.getenv\(\s*[\"']([A-Z0-9_]+)"
)


def core_env_vars() -> set[str]:
    """Toute variable d'environnement lue par `core/app/`."""
    found = set()
    for module in CORE_APP.rglob("*.py"):
        for direct, via_getenv in ENV_READ_RE.findall(module.read_text()):
            found.add(direct or via_getenv)
    return found


def _wired_env_vars() -> set[str]:
    wired = set()
    for path in (BASE, PROD):
        for service in services(path).values():
            env = service.get("environment") or {}
            if isinstance(env, dict):
                wired |= set(env)
            else:  # forme liste : "VAR=valeur"
                wired |= {item.split("=", 1)[0] for item in env}
    return wired


def test_every_core_env_var_is_wired_to_a_service():
    """Une variable lue par le cœur mais absente de l'environnement de tout
    service est un réglage inatteignable : l'opérateur la met dans son .env,
    rien ne change, aucun signal. C'est le mode d'échec de SP-17a, SP-17b,
    tileset3d — et de CORE_ETL_ENABLED, trouvée par cette règle."""
    unwired = core_env_vars() - _wired_env_vars() - ENV_WIRING_EXEMPTIONS
    assert not unwired, (
        f"variables lues par core/app/ et câblées sur aucun service : "
        f"{sorted(unwired)}. Les ajouter à l'`environment` du service qui "
        "les lit, ou à ENV_WIRING_EXEMPTIONS avec la raison écrite."
    )


def test_every_compose_substitution_is_documented():
    """Toute valeur que l'opérateur doit fournir (`${VAR}`) doit être
    découvrable dans .env.example. La règle ne porte QUE sur les
    substitutions : les valeurs dérivées calculées dans le compose
    (DATABASE_URL, OTEL_*) n'ont rien à y faire — les y mettre inviterait à
    les régler à la main."""
    substitutions = set()
    for path in (BASE, PROD):
        substitutions |= set(re.findall(r"\$\{([A-Z0-9_]+)", path.read_text()))
    documented = set(re.findall(r"^#?\s*([A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.MULTILINE))
    undocumented = substitutions - documented
    assert not undocumented, (
        f"substitutions de compose absentes de .env.example : {sorted(undocumented)}."
    )
