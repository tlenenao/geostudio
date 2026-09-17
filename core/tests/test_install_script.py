# SPDX-License-Identifier: Apache-2.0
"""Comportement de scripts/install.sh (spec 2026-09-14, volet C.1).

Même patron que test_restore_script.py (SP-59) : pas de framework de test
shell dans ce dépôt, donc double de test — un exécutable `docker` et un
exécutable `jq` factices sur un PATH de test, qui journalisent leurs
arguments et renvoient des réponses canned plutôt que de toucher un vrai
Docker/Keycloak. install.sh porte déjà toutes les échappatoires
non-interactives nécessaires (INSTALL_YES, INSTALL_PROFILES/
INSTALL_SEED_DEMO, GEOSTUDIO_PUBLIC_HOST, BACKUP_S3_ENDPOINT,
INSTALL_ADMIN_EMAIL) — posées pour un usage de test jamais écrit avant ce
fichier (le commentaire de confirm() le dit littéralement) ; aucune
modification du script de production n'a été nécessaire (vérifié en
lisant le script en entier avant d'écrire ces tests)."""

import os
import pathlib
import shutil
import stat
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
INSTALL_SH = REPO / "scripts/install.sh"
ENV_EXAMPLE = REPO / ".env.example"

_FAKE_DOCKER = r"""#!/bin/sh
echo "docker $*" >> "$FAKE_BIN_LOG"
if [ "$1" = "compose" ]; then
  shift
  while [ "$1" = "-f" ] || [ "$1" = "--profile" ]; do shift; shift; done
  case "$1" in
    config)
      echo "${FAKE_COMPOSE_PROFILES:-}"
      exit 0
      ;;
    up)
      exit 0
      ;;
    exec)
      shift
      shift
      service="$1"
      shift
      if [ "$service" = "keycloak" ]; then
        sub="$2"
        case "$sub" in
          config)
            [ "${FAKE_KC_AUTH_FAILS:-0}" = "1" ] && exit 1
            exit 0
            ;;
          get)
            if grep -q "kcadm.sh create users" "$FAKE_BIN_LOG" 2>/dev/null; then
              echo "[{\"id\":\"created-fake-id\"}]"
            elif [ -n "${FAKE_KC_EXISTING_USER_ID:-}" ]; then
              echo "[{\"id\":\"${FAKE_KC_EXISTING_USER_ID}\"}]"
            else
              echo "[]"
            fi
            exit 0
            ;;
          create)
            exit 0
            ;;
          *)
            exit 0
            ;;
        esac
      elif [ "$service" = "core" ]; then
        if printf '%s' "$*" | grep -q "scripts.seed_demo"; then
          exit 0
        fi
        echo 401
        exit 0
      else
        exit 0
      fi
      ;;
    *)
      exit 0
      ;;
  esac
fi
exit 0
"""

_FAKE_JQ = """#!/usr/bin/env python3
import sys, json

args = sys.argv[1:]
if args == ["--version"]:
    print("fake-jq-1.0")
    sys.exit(0)
filt = args[-1]
data = json.load(sys.stdin)


def first_id(d):
    return d[0]["id"] if d else None


if filt == ".[0].id // empty":
    value = first_id(data)
    print(value if value is not None else "")
elif filt == ".[0].id":
    print(first_id(data))
else:
    sys.exit(f"fake jq: unsupported filter {filt!r}")
"""


@pytest.fixture()
def install_workdir(tmp_path):
    work = tmp_path / "repo"
    (work / "scripts").mkdir(parents=True)
    shutil.copy(INSTALL_SH, work / "scripts/install.sh")
    shutil.copy(ENV_EXAMPLE, work / ".env")
    return work


@pytest.fixture()
def fake_bin_path(tmp_path):
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    log_file = tmp_path / "fake-bin.log"
    log_file.write_text("")

    docker = bin_dir / "docker"
    docker.write_text(_FAKE_DOCKER)
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)

    jq = bin_dir / "jq"
    jq.write_text(_FAKE_JQ)
    jq.chmod(jq.stat().st_mode | stat.S_IEXEC)

    return bin_dir, log_file


def _run_install(install_workdir, fake_bin_path, *, extra_env=None, timeout=30):
    bin_dir, log_file = fake_bin_path
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_BIN_LOG"] = str(log_file)
    env["INSTALL_YES"] = "1"
    env["INSTALL_PROFILES"] = ""
    env["INSTALL_SEED_DEMO"] = "0"
    env["INSTALL_CORE_ETL_ENABLED"] = "0"
    env["GEOSTUDIO_PUBLIC_HOST"] = "geostudio-test.example"
    env["TS_AUTHKEY"] = "tskey-test-fake"
    env["BACKUP_S3_ENDPOINT"] = ""
    env["INSTALL_ADMIN_EMAIL"] = "admin@test.example"
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        ["bash", str(install_workdir / "scripts/install.sh")],
        cwd=install_workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result, log_file.read_text()


def test_install_creates_an_admin_account_and_writes_core_admin_subs(
    install_workdir, fake_bin_path
):
    result, log = _run_install(install_workdir, fake_bin_path)

    assert result.returncode == 0, result.stderr
    assert "kcadm.sh create users" in log
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "CORE_ADMIN_SUBS=created-fake-id" in env_lines


def test_install_reuses_an_existing_admin_account_idempotently(install_workdir, fake_bin_path):
    result, log = _run_install(
        install_workdir,
        fake_bin_path,
        extra_env={"FAKE_KC_EXISTING_USER_ID": "existing-user-42"},
    )

    assert result.returncode == 0, result.stderr
    assert "kcadm.sh create users" not in log
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "CORE_ADMIN_SUBS=existing-user-42" in env_lines


def test_install_fails_cleanly_when_keycloak_never_authenticates(install_workdir, fake_bin_path):
    # La boucle de retry réelle du script (30 tentatives × 2s) s'exécute en
    # entier — ~60s, volontairement non raccourcie (pas de knob dédié dans
    # install.sh, et en ajouter un romprait le patron déjà en place pour ne
    # pas modifier le script de production dans ce volet).
    result, _ = _run_install(
        install_workdir,
        fake_bin_path,
        extra_env={"FAKE_KC_AUTH_FAILS": "1"},
        timeout=90,
    )

    assert result.returncode == 1
    assert "Échec d'authentification" in result.stderr
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "CORE_ADMIN_SUBS=" in env_lines  # jamais écrit


def test_install_selects_profiles_and_launches_the_stack_with_them(install_workdir, fake_bin_path):
    result, log = _run_install(
        install_workdir,
        fake_bin_path,
        extra_env={
            "INSTALL_PROFILES": "observability",
            "FAKE_COMPOSE_PROFILES": "observability\netl",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "--profile observability up -d" in log


def test_install_enables_the_core_etl_engine_independently_of_the_qgis_profile(
    install_workdir, fake_bin_path
):
    result, _ = _run_install(
        install_workdir,
        fake_bin_path,
        extra_env={"INSTALL_CORE_ETL_ENABLED": "1"},
    )

    assert result.returncode == 0, result.stderr
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "CORE_ETL_ENABLED=true" in env_lines


def test_install_leaves_the_core_etl_engine_disabled_by_default(install_workdir, fake_bin_path):
    result, _ = _run_install(install_workdir, fake_bin_path)

    assert result.returncode == 0, result.stderr
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "CORE_ETL_ENABLED=false" in env_lines
