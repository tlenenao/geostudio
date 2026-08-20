# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import select

from app.db import Base, make_session_factory
from app.items.models import Item
from app.search.providers import FakeProvider
from app.search.ranking import hybrid_search_ids, reciprocal_rank_fusion
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_rrf_favors_items_present_in_both_lists():
    ranked = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]])
    ids = [i for i, _score in ranked]
    # "a" et "b" apparaissent dans les deux listes (rangs proches) ; "c" et
    # "d" n'apparaissent que dans une seule — a/b doivent sortir devant.
    assert ids.index("a") < ids.index("c")
    assert ids.index("b") < ids.index("d")


def test_rrf_handles_an_id_present_in_only_one_list():
    ranked = reciprocal_rank_fusion([["a"], []])
    assert ranked == [("a", 1 / 61)]


def test_rrf_handles_empty_lists():
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_k_constant_is_configurable():
    ranked_default = reciprocal_rank_fusion([["a"]])
    ranked_k1 = reciprocal_rank_fusion([["a"]], k=1)
    assert ranked_default[0][1] == 1 / 61
    assert ranked_k1[0][1] == 1 / 2


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(text("TRUNCATE items, users, tenants CASCADE"))


@pytest.mark.postgis
def test_hybrid_search_ids_ranks_a_vector_match_ahead_of_a_weak_text_match(pg_session):
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    close_vector = [1.0] * 1536
    query_vector = [0.99] * 1536  # très proche de close_vector (cosine)
    far_vector = [-1.0] * 1536

    semantically_close = Item(
        id="i-close",
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="app",
        title="Sujet totalement différent",
        embedding=close_vector,
    )
    weak_text_match = Item(
        id="i-weak",
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="app",
        title="incidents",
        embedding=far_vector,
    )
    # Un troisième item, meilleur match trigram qu'"incidents" seul et pas
    # encore embeddé (dégradation gracieuse SP-7 Task 2/5 : embedding NULL
    # tant que le job d'embedding n'est pas passé) — pousse i-weak au rang 2
    # trigram, pour que le RRF combiné départage strictement i-close et
    # i-weak au lieu de les faire arriver exactement à égalité (les deux ne
    # figurant chacun que dans une seule liste, au rang 1). Sans lui, la
    # comparaison i-close/i-weak dépend d'un ex-æquo flottant fragile —
    # jamais rencontré avec de vrais embeddings/textes, mais artificiel ici
    # avec seulement deux lignes candidates.
    unrelated_but_unembedded = Item(
        id="i-filler",
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="app",
        title="incidents voirie",
        embedding=None,
    )
    pg_session.add_all([semantically_close, weak_text_match, unrelated_but_unembedded])
    pg_session.flush()

    base_stmt = select(Item).where(Item.tenant_id == tenant.id)
    provider = FakeProvider(vectors={"incidents voirie": query_vector})
    ids = hybrid_search_ids(
        pg_session,
        base_stmt=base_stmt,
        id_column=Item.id,
        text_columns=[Item.title, Item.abstract],
        embedding_column=Item.embedding,
        query_text="incidents voirie",
        query_vector=provider.embed("incidents voirie"),
    )
    assert ids.index("i-close") < ids.index("i-weak")
