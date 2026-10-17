# SPDX-License-Identifier: Apache-2.0
import os
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app import observability
from app.apikeys import service as api_key_service
from app.auth.export_tokens import ExportTokenError, decode_export_token, is_export_token
from app.db import get_session
from app.sharing.claim_sync import apply_from_token_claims
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


def _mock_mode() -> bool:
    return os.environ.get("CORE_AUTH_MODE", "oidc") == "mock"


def reject_mock_outside_development() -> None:
    """Appelée une fois au démarrage (create_app()), pas par requête —
    contrairement à _mock_mode() ci-dessus. C6 (revue de projet 2026-08-20) :
    CORE_AUTH_MODE=mock donne bootstrap_admin=True à quiconque présente un
    Bearer non vide (cf. get_current_user plus bas), sans aucune vérification
    d'environnement jusqu'ici. CORE_ENV=development est un marqueur explicite,
    pas une valeur par défaut sûre — un déploiement qui omet CORE_ENV ET met
    CORE_AUTH_MODE=mock est traité comme une erreur de configuration,
    jamais comme "sans doute du dev"."""
    if _mock_mode() and os.environ.get("CORE_ENV") != "development":
        raise RuntimeError("CORE_AUTH_MODE=mock requires CORE_ENV=development")


def is_read_only_mode() -> bool:
    """CORE_READ_ONLY_MODE (mode démo, SP-9) — lu à chaque appel, sans cache,
    même convention que _mock_mode() ci-dessus : les tests basculent le mode
    via monkeypatch sans recréer l'app."""
    return os.environ.get("CORE_READ_ONLY_MODE", "false").lower() == "true"


def is_etl_enabled() -> bool:
    """CORE_ETL_ENABLED (SP-15a) — capacité instance-wide optionnelle, même
    convention que is_read_only_mode : lue à chaque appel, sans cache, pour
    que les tests basculent via monkeypatch sans recréer l'app. Défaut
    false : une instance qui monte en version ne voit rien de nouveau tant
    qu'elle n'a pas explicitement activé la capacité (cf. design SP-15a §3)."""
    return os.environ.get("CORE_ETL_ENABLED", "false").lower() == "true"


def is_pipeline_file_io_enabled() -> bool:
    """CORE_PIPELINE_FILE_IO_ENABLED (design desktop-etl §3) — capacité
    instance-wide optionnelle, même convention que is_etl_enabled : lue à
    chaque appel, sans cache. Défaut false : reader.file/writer.file font de
    l'accès disque arbitraire (chemin choisi par l'auteur du pipeline), un
    risque de traversée de chemin inacceptable sur un cœur hébergé
    multi-tenant — le futur sidecar desktop (poste mono-utilisateur, design
    §1) l'activera dans son propre environnement, jamais par défaut ici."""
    return os.environ.get("CORE_PIPELINE_FILE_IO_ENABLED", "false").lower() == "true"


def is_pipeline_experimental_ops_enabled() -> bool:
    """CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED (lot 9, release v0.2.0) — capacité
    instance-wide optionnelle, même convention que is_etl_enabled : lue à chaque
    appel, sans cache. Défaut false : les op de pipeline qui parlent à un service
    tiers sans jamais avoir été rejouées contre le vrai service (cf.
    docs/revue/2026-10-16-ops-experimentales.md) sont masquées du catalogue et
    refusées à l'écriture comme à l'exécution."""
    return os.environ.get("CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED", "false").lower() == "true"


def is_export_enabled() -> bool:
    """CORE_EXPORT_ENABLED (SP-17a) — capacité instance-wide optionnelle,
    même convention que is_etl_enabled : lue à chaque appel, sans cache.
    Défaut false : le worker Playwright/export-worker n'est jamais requis
    pour faire tourner le reste de la plateforme."""
    return os.environ.get("CORE_EXPORT_ENABLED", "false").lower() == "true"


def is_appexport_enabled() -> bool:
    """CORE_APPEXPORT_ENABLED (SP-18a) — capacité instance-wide optionnelle,
    même convention que is_export_enabled : lue à chaque appel, sans cache.
    Défaut false : construire un bundle statique d'app exige le runtime
    export prébâti (deploy/appexport-runtime-builder), jamais requis pour le
    reste de la plateforme."""
    return os.environ.get("CORE_APPEXPORT_ENABLED", "false").lower() == "true"


def is_tileset3d_enabled() -> bool:
    """CORE_TILESET3D_ENABLED — capacité instance-wide optionnelle, même
    convention que is_export_enabled : lue à chaque appel, sans cache.
    Défaut false : une instance qui monte en version ne provisionne rien de
    nouveau (bucket S3 dédié, route proxy) tant qu'elle n'a pas explicitement
    activé la capacité (design hébergement tileset3d §6)."""
    return os.environ.get("CORE_TILESET3D_ENABLED", "false").lower() == "true"


def is_raster_enabled() -> bool:
    """CORE_RASTER_ENABLED (ARC-33, ADR 0024) — capacité instance-wide optionnelle :
    bucket raster, file `raster`, proxy de tuiles TiTiler. Défaut false."""
    return os.environ.get("CORE_RASTER_ENABLED", "false").lower() == "true"


def is_routing_enabled() -> bool:
    """Routage Valhalla (ARC-34, ADR 0025) configuré : CORE_ROUTING_URL non vide. Sinon les
    routes /v1/routing/* répondent 503 ; le shell masque les surfaces qui en dépendent."""
    return bool(os.environ.get("CORE_ROUTING_URL", "").strip())


def is_external_basemaps_enabled() -> bool:
    """AUD-122 : fonds de carte tiers (MapLibre démo, Carto, IGN Géoplateforme) proposés.
    `false` = déploiement souverain/air-gapped : fond vierge local par défaut, fonds tiers
    masqués dans le shell. Défaut `true` (comportement historique)."""
    return os.environ.get("CORE_EXTERNAL_BASEMAPS_ENABLED", "true").strip().lower() != "false"


def is_terrain3d_enabled() -> bool:
    """CORE_TERRAIN3D_ENABLED — capacité instance-wide optionnelle, même
    convention que is_tileset3d_enabled : lue à chaque appel, sans cache.
    Défaut false : une instance qui monte en version ne provisionne rien de
    nouveau (bucket S3 dédié, dépendances rasterio/rio-cogeo côté worker,
    route proxy) tant qu'elle n'a pas explicitement activé la capacité
    (design terrain hébergé §6)."""
    return os.environ.get("CORE_TERRAIN3D_ENABLED", "false").lower() == "true"


def is_copilot_enabled() -> bool:
    """CORE_LLM_PROVIDER (SP-20) — contrairement aux autres capacités
    instance-wide ci-dessus (is_etl_enabled et consorts), ce n'est pas un
    booléen dédié : le copilote est actif dès qu'un fournisseur LLM est
    configuré, quelle que soit sa valeur (CORE_LLM_PROVIDER=openai, ou
    toute chaîne non vide). Lue à chaque appel, sans cache, même
    convention que is_read_only_mode ci-dessus.

    Éteint en mode démo lecture-seule (I6 de la revue de projet
    2026-08-20) : les écritures y sont déjà bloquées par les outils MCP,
    mais chaque tour consomme jusqu'à 6 appels LLM payés par l'opérateur —
    un visiteur anonyme pouvait donc brûler son budget d'API. Renvoyer
    False ici coupe d'un coup le montage du routeur (main.py) et le
    panneau côté shell (copilotEnabled sur GET /instance)."""
    return bool(os.environ.get("CORE_LLM_PROVIDER")) and not is_read_only_mode()


def is_admin_tools_enabled() -> bool:
    """CORE_ADMIN_TOOLS_ENABLED — capacité instance-wide optionnelle, même
    convention que is_tileset3d_enabled : lue à chaque appel, sans cache.
    Défaut false : les trois routes /admin-tools/* ne sont montées que si
    l'opérateur a explicitement activé la capacité (design URLs admin §3)."""
    return os.environ.get("CORE_ADMIN_TOOLS_ENABLED", "false").lower() == "true"


def is_quotas_enabled() -> bool:
    """CORE_QUOTAS_ENABLED (SP-58) — capacité instance-wide optionnelle,
    même convention que is_admin_tools_enabled : lue à chaque appel, sans
    cache. Défaut false : une instance qui monte en version n'applique
    aucune limite tant qu'elle n'a pas explicitement activé la capacité
    (design SP-58 §3.1)."""
    return os.environ.get("CORE_QUOTAS_ENABLED", "false").lower() == "true"


def reject_admin_tools_without_secret() -> None:
    """Appelée une fois au démarrage (create_app()), même patron que
    reject_mock_outside_development() ci-dessus : échec rapide et lisible
    plutôt qu'un 500 opaque au premier appel. jwt.encode(claims, "") lève
    InvalidKeyError("HMAC key must not be empty.") — non attrapé par
    app.admin_tools.routes, ce qui ferait déjà échouer POST
    /admin-tools/launch/{tool} en pratique (fail-closed, pas exploitable),
    mais sans rien dire à l'opérateur sur la cause. CORE_ADMIN_TOOLS_ENABLED
    activé sans secret réglé est exactement l'état que .env.example invite
    par défaut (CORE_ADMIN_TOOLS_TOKEN_SECRET vide)."""
    if is_admin_tools_enabled() and not os.environ.get("CORE_ADMIN_TOOLS_TOKEN_SECRET"):
        raise RuntimeError(
            "CORE_ADMIN_TOOLS_ENABLED=true requires a non-empty CORE_ADMIN_TOOLS_TOKEN_SECRET"
        )


def admin_subs() -> set[str]:
    """OIDC subs à promouvoir admin au prochain get_or_create_user (source de
    vérité de CORE_ADMIN_SUBS — utilisée par le chemin REST ci-dessous ET par
    le chemin MCP, app.mcp.tools._resolve_actor)."""
    raw = os.environ.get("CORE_ADMIN_SUBS", "")
    return {s.strip() for s in raw.split(",") if s.strip()}


def analyst_subs() -> set[str]:
    """OIDC subs à promouvoir analyste au prochain get_or_create_user
    (source de vérité de CORE_ANALYST_SUBS) — miroir de admin_subs()."""
    raw = os.environ.get("CORE_ANALYST_SUBS", "")
    return {s.strip() for s in raw.split(",") if s.strip()}


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    issuer = os.environ["CORE_OIDC_ISSUER"]
    jwks_url = os.environ.get("CORE_OIDC_JWKS_URL", f"{issuer}/protocol/openid-connect/certs")
    return jwt.PyJWKClient(jwks_url, lifespan=600)


_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_READ_POST_MARK = "__gs_read_post__"


def read_post[F: Callable[..., Any]](endpoint: F) -> F:
    """Route POST qui ne fait que LIRE (corps de requête trop riche pour un GET :
    agrégat, recherche). Autorisation explicite, route par route : le jeton
    d'export (rendu PDF des widgets) et la clé d'API en lecture seule peuvent
    l'appeler ; toute autre écriture leur reste refusée (C1 revue SP-L2)."""
    setattr(endpoint, _READ_POST_MARK, True)
    return endpoint


def _is_read(request: Request | None) -> bool:
    if request is None:  # appel direct sans requête (tests) = lecture
        return True
    if request.method in _READ_METHODS:
        return True
    endpoint = request.scope.get("endpoint")
    return request.method == "POST" and bool(getattr(endpoint, _READ_POST_MARK, False))


def forbid_api_key(authorization: str = Header(default="")) -> None:
    """Route réservée à une session interactive : une clé ne gère ni clés (elle
    survivrait à sa propre révocation), ni effacement, liens de partage, jetons
    webhook ou rôles (AUD-094)."""
    if api_key_service.is_api_key(authorization.removeprefix("Bearer ")):
        raise HTTPException(status_code=403, detail="not allowed with an api key")


def get_current_user(
    request: Request = None,  # type: ignore[assignment]  # injecté par FastAPI
    authorization: str = Header(default=""),
    session: Session = Depends(get_session, scope="function"),
) -> User:
    # Appel direct sans requête (tests) = lecture ; FastAPI injecte toujours la requête.
    user = _resolve_current_user(authorization, session, is_read=_is_read(request))
    observability.tag_current_span_with_user(user)  # AUD-040
    return user


def _resolve_current_user(authorization: str, session: Session, *, is_read: bool) -> User:
    # REV-012 : la résolution du tenant (get_or_create_default_tenant peut
    # INSÉRER une ligne) ne doit se produire qu'après ce contrôle — sinon
    # toute requête non authentifiée sur une route protégée déclenche un
    # accès base avant même son 401. Les trois branches ci-dessous
    # (mock/jeton d'export/OIDC) sont toutes en aval de ce contrôle.
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ")

    tenant = get_or_create_default_tenant(session)

    # ARC-06 (ADR 0016) : clé d'API de service. Résout vers son créateur — mêmes
    # rôle/partages que lui, donc même porte can()/require_privilege en aval.
    # Avant la branche mock : en mock tout Bearer est accepté, la clé serait
    # sinon intestable ; un jeton "gsk_" invalide reste un 401 dans tous les modes.
    if api_key_service.is_api_key(token):
        api_user = api_key_service.authenticate(session, token=token, tenant_id=tenant.id)
        if api_user is None:
            raise HTTPException(status_code=401, detail="invalid api key")
        if api_user.api_key_read_only and not is_read:  # AUD-091
            raise HTTPException(status_code=403, detail="read-only api key")
        return api_user

    if _mock_mode():
        return get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
            bootstrap_admin=True,
            bootstrap_analyst=True,
        )

    if is_export_token(token):
        try:
            claims = decode_export_token(token)
        except ExportTokenError as exc:
            raise HTTPException(status_code=401, detail="invalid export token") from exc
        if claims.tenant_id != tenant.id:
            raise HTTPException(status_code=401, detail="invalid export token")
        # AUD-024 : un jeton d'export ne fait que lire (GET, ou POST marqué @read_post).
        if not is_read:
            raise HTTPException(status_code=403, detail="export token is read-only")
        user = session.get(User, claims.user_id)
        if user is None or user.erased_at is not None:  # AUD-094
            raise HTTPException(status_code=401, detail="invalid export token")
        return user

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        # Nommée séparément de `claims` (ExportTokenClaims, branche ci-dessus)
        # : type distinct (dict brut du JWT OIDC), les deux branches sont
        # mutuellement exclusives mais réutiliser le même nom forçait un seul
        # type sur toute la fonction.
        oidc_claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=os.environ["CORE_OIDC_AUDIENCE"],
            issuer=os.environ["CORE_OIDC_ISSUER"],
        )
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(status_code=503, detail="identity provider unreachable") from exc
    except jwt.PyJWKClientError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc

    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub=oidc_claims["sub"],
        username=oidc_claims.get("preferred_username", oidc_claims["sub"]),
        email=oidc_claims.get("email"),
        first_name=oidc_claims.get("given_name", ""),
        last_name=oidc_claims.get("family_name", ""),
        bootstrap_admin=oidc_claims["sub"] in admin_subs(),
        bootstrap_analyst=oidc_claims["sub"] in analyst_subs(),
    )
    # ARC-24 (ADR 0022) : appartenances alimentées par les claims, additif, jamais bloquant.
    apply_from_token_claims(session, tenant_id=tenant.id, user_id=user.id, claims=oidc_claims)
    return user


def get_current_user_optional(
    request: Request = None,  # type: ignore[assignment]  # injecté par FastAPI
    authorization: str = Header(default=""),
    session: Session = Depends(get_session, scope="function"),
) -> User | None:
    """Comme get_current_user, mais renvoie None sans header (accès anonyme
    aux collections publiques — URLs OGC stables, spec SP-3 §2)."""
    if not authorization.startswith("Bearer "):
        return None
    return get_current_user(request, authorization=authorization, session=session)
