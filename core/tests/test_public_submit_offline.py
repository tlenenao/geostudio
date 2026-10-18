# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: F811  (fixtures importées d'un autre module de test)
"""L8 T5 : soumission publique idempotente (clientOpId), multi-fichiers, preuve de travail."""

import threading
import uuid

import pytest
from sqlalchemy import select, text

from app.attachments.models import Attachment
from app.collect import pow as collect_pow
from app.public_submit.models import Submission, SubmissionFile, SubmissionToken
from tests.test_pow import solve
from tests.test_public_submit_postgis import (  # noqa: F401
    PNG,
    _anon,
    _as,
    _payload,
    _submit,
    pg_app,
    ready,
)

pytestmark = pytest.mark.postgis

OP = "33333333-3333-4333-8333-333333333333"
EXE = b"MZ\x90\x00" + bytes(64)


def _files(n, data=PNG):
    return [("files", (f"p{i}.png", data, "image/png")) for i in range(n)]


def _post(client, token, *, files=None, data=None):
    return client.post(
        f"/v1/public/submit/{token}",
        data={"payload": _payload(), **(data or {})},
        files=files,
    )


def _counts(Session):
    with Session() as s:
        return (
            s.scalar(text("SELECT count(*) FROM submissions")),
            s.scalar(text("SELECT count(*) FROM submission_files")),
            s.scalar(select(SubmissionToken.submission_count)),
        )


def test_replayed_client_op_is_accepted_without_a_second_slot(ready):
    client, app, _a, Session, s3, tok = ready
    _anon(app)
    first = _post(client, tok["token"], data={"clientOpId": OP}, files=_files(1))
    again = _post(client, tok["token"], data={"clientOpId": OP}, files=_files(1))
    assert first.status_code == 202 and again.status_code == 202
    assert _counts(Session) == (1, 1, 1)
    assert s3.puts == 1  # le rejeu n'envoie rien à S3


def test_distinct_client_ops_each_take_a_slot(ready):
    client, app, _a, Session, _s3, tok = ready
    _anon(app)
    for _ in range(2):
        assert (
            _post(client, tok["token"], data={"clientOpId": str(uuid.uuid4())}).status_code == 202
        )
    assert _counts(Session)[0] == 2


def test_invalid_client_op_id_is_a_validation_error(ready):
    client, app, _a, _S, _s3, tok = ready
    _anon(app)
    assert _post(client, tok["token"], data={"clientOpId": "x; DROP"}).status_code == 400


def test_concurrent_same_client_op_creates_one_submission(ready):
    client, app, _a, Session, _s3, tok = ready
    _anon(app)
    codes = []

    def go():
        codes.append(_post(client, tok["token"], data={"clientOpId": OP}).status_code)

    threads = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codes == [202] * 6
    assert _counts(Session)[0] == 1  # résultat final, pas un chrono (piège n°7)
    assert _counts(Session)[2] == 1  # un seul slot consommé


def test_several_files_are_stored_listed_and_all_attached_on_approval(ready):
    client, app, admin, Session, s3, tok = ready
    _anon(app)
    r = _post(client, tok["token"], files=_files(3), data={"fieldKeys": ["photo"] * 3})
    assert r.status_code == 202, r.text
    _as(app, admin)
    sub = client.get("/v1/collections/demo_sub/submissions").json()["submissions"][0]
    assert len(sub["files"]) == 3 and sub["attachment"]["fieldKey"] == "photo"
    one = client.get(
        f"/v1/collections/demo_sub/submissions/{sub['id']}/attachment",
        params={"fileId": sub["files"][1]["id"]},
    )
    assert one.status_code == 200 and one.content == PNG
    approved = client.post(f"/v1/collections/demo_sub/submissions/{sub['id']}/approve")
    assert approved.status_code == 200, approved.text
    with Session() as s:
        assert len(s.scalars(select(Attachment)).all()) == 3
    assert len(s3.objects) == 3  # les objets restent vivants (devenus pièces jointes)


def test_file_count_size_and_total_caps(ready):
    client, app, _a, Session, s3, tok = ready
    _anon(app)
    assert _post(client, tok["token"], files=_files(6)).status_code == 400
    big = PNG + b"\x00" * (10 * 1024 * 1024)
    assert _post(client, tok["token"], files=_files(1, big)).status_code == 413
    nine = PNG + b"\x00" * (9 * 1024 * 1024)
    assert _post(client, tok["token"], files=_files(3, nine)).status_code == 413  # 27 Mo > 25
    # rien n'est conservé, aucun slot consommé
    assert _counts(Session) == (0, 0, 0)
    assert s3.objects == {}


def test_disguised_executable_among_files_refuses_all_and_cleans_up(ready):
    client, app, _a, Session, s3, tok = ready
    _anon(app)
    files = _files(1) + [("files", ("e.png", EXE, "image/png"))]
    assert _post(client, tok["token"], files=files).status_code == 415
    assert _counts(Session) == (0, 0, 0)
    assert s3.objects == {}


def test_legacy_single_attachment_column_is_still_approved(ready):
    client, app, admin, Session, s3, tok = ready
    _anon(app)
    assert _post(client, tok["token"]).status_code == 202
    s3.objects["default/demo_sub/pending-legacy/old.png"] = PNG
    with Session() as s:
        sub = s.scalars(select(Submission)).one()
        sub.attachment = {
            "fieldKey": "photo",
            "filename": "old.png",
            "contentType": "image/png",
            "byteSize": len(PNG),
        }
        sub.attachment_key = "default/demo_sub/pending-legacy/old.png"
        s.commit()
        sid = sub.id
    _as(app, admin)
    assert client.post(f"/v1/collections/demo_sub/submissions/{sid}/approve").status_code == 200
    with Session() as s:
        assert [a.filename for a in s.scalars(select(Attachment))] == ["old.png"]


def test_reject_deletes_every_file(ready):
    client, app, admin, Session, s3, tok = ready
    _anon(app)
    _post(client, tok["token"], files=_files(2), data={"fieldKeys": ["photo"] * 2})
    assert len(s3.objects) == 2
    _as(app, admin)
    sid = client.get("/v1/collections/demo_sub/submissions").json()["submissions"][0]["id"]
    assert (
        client.post(
            f"/v1/collections/demo_sub/submissions/{sid}/reject", json={"reason": "x"}
        ).status_code
        == 204
    )
    assert s3.objects == {}
    with Session() as s:
        assert all(f.attachment_key is None for f in s.scalars(select(SubmissionFile)))


def test_submission_files_are_never_readable_by_rls_roles(pg_app):
    _c, _app, _a, Session, _s3 = pg_app
    with Session() as s:
        for role in ("gis_rls", "gis_rls_masked"):
            assert (
                s.scalar(
                    text("SELECT has_table_privilege(:r, 'submission_files', 'SELECT')"),
                    {"r": role},
                )
                is False
            )


def test_proof_of_work_is_enforced_when_enabled(ready, monkeypatch):
    client, app, _a, Session, _s3, tok = ready
    _anon(app)
    monkeypatch.delenv("CORE_PUBLIC_SUBMIT_POW_DISABLED")
    collect_pow.reset()
    assert _post(client, tok["token"]).status_code == 403  # sans preuve
    ch = client.get(f"/v1/public/submit/{tok['token']}/challenge").json()
    assert ch["required"] is True and ch["bits"] == 18
    nonce = solve(ch["challenge"])
    ok = _post(client, tok["token"], data={"powChallenge": ch["challenge"], "powNonce": nonce})
    assert ok.status_code == 202
    replay = _post(client, tok["token"], data={"powChallenge": ch["challenge"], "powNonce": nonce})
    assert replay.status_code == 403  # défi consommé
    assert _counts(Session)[0] == 1


def test_replay_does_not_need_a_fresh_proof_of_work(ready, monkeypatch):
    client, app, _a, Session, _s3, tok = ready
    _anon(app)
    assert _post(client, tok["token"], data={"clientOpId": OP}).status_code == 202
    monkeypatch.delenv("CORE_PUBLIC_SUBMIT_POW_DISABLED")
    assert _post(client, tok["token"], data={"clientOpId": OP}).status_code == 202
    assert _counts(Session)[0] == 1


def test_honeypot_and_invalid_token_still_behave(ready):
    client, app, _a, Session, _s3, tok = ready
    _anon(app)
    assert _post(client, tok["token"], data={"website": "spam"}).status_code == 202
    assert _counts(Session)[0] == 0
    assert _submit(client, "gss_" + "1" * 12 + "_bad").status_code == 404
