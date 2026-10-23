# SPDX-License-Identifier: Apache-2.0
"""REV-281 (b) / ADR 0014 : signature cosign keyless par digest, attestation SBOM,
compose de production épinglé par digest. Tests statiques des workflows + du script
de pin ; la vérification réelle exige un run GitHub (jamais exécuté ici)."""

import pathlib
import re
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.check_published_images import check_signatures, release_images  # noqa: E402
from scripts.pin_compose_digests import build_override, load_compose  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
WF = REPO / ".github/workflows"


def _load(name):
    return yaml.safe_load((WF / name).read_text())


def _steps():
    return _load("_build-and-push.yml")["jobs"]["build-and-push"]["steps"]


def test_reusable_workflow_declares_oidc_and_attestation_permissions():
    perms = _load("_build-and-push.yml")["jobs"]["build-and-push"]["permissions"]
    assert perms["id-token"] == "write"
    assert perms["attestations"] == "write"
    assert perms["packages"] == "write"


def test_callers_grant_at_least_what_the_reusable_job_declares():
    # Un appelant ne peut pas accorder moins que le job appelé (validation statique GitHub).
    for name in ("release.yml", "publish-edge.yml"):
        perms = _load(name)["jobs"]["build-and-push"]["permissions"]
        assert perms["id-token"] == "write", name
        assert perms["attestations"] == "write", name
        assert perms["packages"] == "write", name


def test_images_are_signed_by_digest_never_by_tag():
    steps = _steps()
    build = next(s for s in steps if str(s.get("uses", "")).startswith("docker/build-push-action"))
    assert build["id"] == "build"
    sign = next(s for s in steps if "sign-image.sh" in str(s.get("run", "")))
    run = sign["run"]
    assert "cosign sign --yes" in (REPO / "scripts/ci/sign-image.sh").read_text()
    assert "@${DIGEST}" in run
    assert sign["env"]["DIGEST"] == "${{ steps.build.outputs.digest }}"
    assert not re.search(r"cosign sign[^\n]*:\$\{?(IMAGE_TAG|\{ ?inputs)", run)


def test_cosign_installer_and_attest_are_pinned_by_sha():
    uses = [str(s["uses"]) for s in _steps() if "uses" in s]
    for action in ("sigstore/cosign-installer", "actions/attest"):
        ref = next(u for u in uses if u.startswith(action + "@"))
        assert re.fullmatch(rf"{action}@[0-9a-f]{{40}}", ref), ref
    # attest-sbom est déprécié (son action.yml renvoie vers actions/attest).
    assert not any(u.startswith("actions/attest-sbom") for u in uses)


def test_sbom_is_attested_to_the_image_digest():
    attest = next(s for s in _steps() if str(s.get("uses", "")).startswith("actions/attest@"))
    assert attest["with"]["subject-digest"] == "${{ steps.build.outputs.digest }}"
    assert attest["with"]["push-to-registry"] is True
    assert "sbom-path" in attest["with"]


def test_digest_is_exported_for_the_pin_step():
    steps = _steps()
    assert any(
        str(s.get("uses", "")).startswith("actions/upload-artifact@")
        and str(s["with"]["name"]).startswith("digest-")
        for s in steps
    )
    assert "pin-digests" in _load("release.yml")["jobs"]


def test_verify_published_checks_signatures_in_both_publish_workflows():
    for name in ("release.yml", "publish-edge.yml"):
        steps = _load(name)["jobs"]["verify-published"]["steps"]
        assert any("--verify-signatures" in str(s.get("run", "")) for s in steps), name
        assert any(str(s.get("uses", "")).startswith("sigstore/cosign-installer@") for s in steps)
        # cosign n'authentifie pas seul : sans login, un package GHCR privé paraît « non signé ».
        assert any(str(s.get("uses", "")).startswith("docker/login-action@") for s in steps), name


def test_pin_digests_waits_for_signature_verification():
    needs = _load("release.yml")["jobs"]["pin-digests"]["needs"]
    assert "verify-published" in needs


def test_check_signatures_fails_on_an_unsigned_image():
    digests = {"geostudio-core": "sha256:aaa", "geostudio-shell": "sha256:bbb"}
    verified = []

    def verifier(image, digest):
        verified.append((image, digest))
        return image != "geostudio-shell"  # shell non signée

    bad = check_signatures(
        ["geostudio-core", "geostudio-shell"],
        "v1",
        resolver=lambda image, tag: digests[image],
        verifier=verifier,
    )
    assert bad == ["geostudio-shell"]
    # vérifié par digest, jamais par tag
    assert verified == [("geostudio-core", "sha256:aaa"), ("geostudio-shell", "sha256:bbb")]


def test_check_signatures_treats_an_unresolvable_digest_as_unsigned():
    bad = check_signatures(
        ["geostudio-core"], "v1", resolver=lambda i, t: None, verifier=lambda i, d: True
    )
    assert bad == ["geostudio-core"]


def test_pin_override_pins_every_geostudio_image_of_the_prod_compose():
    prod = load_compose(REPO / "docker-compose.prod.yml")
    names = {
        s["image"].split("/")[-1].split(":")[0]
        for s in prod["services"].values()
        if s.get("image", "").startswith("ghcr.io/tlenenao/")
    }
    assert names <= set(release_images())  # chaque image du compose est publiée (donc a un digest)
    digests = {n: "sha256:" + n.encode().hex().ljust(64, "0")[:64] for n in names}
    override = yaml.safe_load(build_override(prod, digests))
    pinned = {svc: s["image"] for svc, s in override["services"].items()}
    assert set(pinned) == {
        svc
        for svc, s in prod["services"].items()
        if s.get("image", "").startswith("ghcr.io/tlenenao/")
    }
    assert all("@sha256:" in image and ":latest" not in image for image in pinned.values())


def test_pin_override_refuses_a_missing_digest():
    prod = {"services": {"core": {"image": "ghcr.io/tlenenao/geostudio-core:${V:-latest}"}}}
    try:
        build_override(prod, {})
    except KeyError:
        return
    raise AssertionError("un digest manquant doit échouer, pas retomber sur le tag")


def test_sign_step_goes_through_the_idempotent_script():
    # AUD-177 : `cosign sign` nu échoue en 409 sur un digest déjà signé (build identique).
    step = next(s for s in _steps() if s.get("name", "").startswith("Sign image"))
    assert "scripts/ci/sign-image.sh" in step["run"]
    assert "cosign sign" not in step["run"]
