# SPDX-License-Identifier: Apache-2.0
"""Recherche hybride générique (SP-7) : combine des listes classées
(trigram, vecteur) par Reciprocal Rank Fusion, et une requête SQLAlchemy
paramétrique qui construit ces deux listes candidates au-dessus d'un
`base_stmt` déjà filtré par permissions. Module pur / sans dépendance
domaine (comme app.db) — app.items.repository et app.collections.repository
l'utilisent tous deux (Task 6, Task 7)."""

from sqlalchemy import Select, func
from sqlalchemy.orm import Session


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], *, k: int = 60
) -> list[tuple[str, float]]:
    """score(id) = somme de 1/(k+rang) sur chaque liste où id apparaît (rang
    1-indexé). k=60 = constante standard de l'article RRF original (Cormack
    et al. 2009), utilisée telle quelle. Pas de pénalité pour un id absent
    d'une des listes — juste absent de cette somme."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, obj_id in enumerate(ranked, start=1):
            scores[obj_id] = scores.get(obj_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def hybrid_search_ids(
    session: Session,
    *,
    base_stmt: Select,
    id_column,
    text_columns: list,
    embedding_column,
    query_text: str,
    query_vector: list[float],
    limit: int = 200,
) -> list[str]:
    """Construit deux requêtes candidates (trigram, vecteur) au-dessus de
    `base_stmt` — déjà filtré tenant/scope/permissions par l'appelant, avant
    tout scoring (spec §Recherche hybride + permissions) — et les combine
    par RRF. `base_stmt` est un objet Select immuable : chaque `.where(...)`
    ci-dessous produit une requête indépendante qui garde le FROM/WHERE
    d'origine, sans interférer avec l'autre branche.

    Les deux branches filtrent leurs candidats avant le classement, pas
    seulement après : la branche trigram exclut les similarités quasi
    nulles (`> 0.05`, du bruit de n-grammes) et la branche vecteur exclut
    symétriquement les embeddings au moins aussi éloignés qu'une paire de
    vecteurs orthogonaux (`cosine_distance < 1.0`, c.-à-d. similarité
    cosinus strictement positive). Sans ce filtre, un item dont
    l'embedding est décorrélé de la requête se classe quand même dans
    `vector_ids` dès que le corpus filtré par `base_stmt` est petit (il n'y
    a personne d'autre pour occuper les rangs), et RRF — qui ne pondère que
    le RANG, jamais l'intensité du score — peut alors le faire ressortir
    devant un item réellement proche sémantiquement simplement parce qu'il
    apparaît (même faiblement) dans les deux listes. Constaté empiriquement
    en écrivant le test `postgis` de ce module : un vecteur maximalement
    opposé à la requête reste inclus par la requête vecteur non filtrée dès
    que le corpus ne compte que deux lignes, ce qui suffisait à faire
    gagner l'item au texte faible sur l'item sémantiquement proche."""
    concatenated = text_columns[0]
    for col in text_columns[1:]:
        concatenated = func.concat(concatenated, " ", col)
    similarity_expr = func.similarity(concatenated, query_text)
    trigram_stmt = (
        base_stmt.where(similarity_expr > 0.05)
        .order_by(similarity_expr.desc())
        .limit(limit)
        .with_only_columns(id_column)
    )
    trigram_ids = [row[0] for row in session.execute(trigram_stmt).all()]

    distance_expr = embedding_column.cosine_distance(query_vector)
    vector_stmt = (
        base_stmt.where(embedding_column.isnot(None), distance_expr < 1.0)
        .order_by(distance_expr)
        .limit(limit)
        .with_only_columns(id_column)
    )
    vector_ids = [row[0] for row in session.execute(vector_stmt).all()]

    ranked = reciprocal_rank_fusion([trigram_ids, vector_ids])
    return [obj_id for obj_id, _score in ranked]
