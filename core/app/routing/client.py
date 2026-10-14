# SPDX-License-Identifier: Apache-2.0
"""Routage et isochrones (ARC-34, ADR 0025) : client Valhalla (MIT) en service externe.

Seul point de contact avec Valhalla : routes REST, outils MCP et ops de pipeline passent ici
(jamais directement chez Valhalla). Garde d'egress dédiée : le service est typiquement sur le
réseau privé de l'opérateur (compose `valhalla:8002`), donc les plages privées/loopback sont
admises MAIS seulement pour l'hôte de `CORE_ROUTING_URL` ; link-local (métadonnées cloud),
multicast et non-spécifiées restent toujours bloquées ; pas de redirection suivie ; connexion
épinglée sur l'IP validée (net_pin). Service non configuré ou injoignable =
`RoutingUnavailable` (503 côté REST/MCP), jamais un crash."""

import functools
import ipaddress
import os
import socket
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from urllib.parse import urlparse

import httpx

from app.net_pin import ValidatedIp, send_pinned
from app.ratelimit.limiter import PgRateLimiter, make_rate_limiter

COSTINGS = ("auto", "bicycle", "pedestrian", "truck", "bus", "motor_scooter")
MAX_ROUTE_POINTS = 20
MAX_MATRIX_SIDE = 50  # sources ou cibles ; produit <= MAX_MATRIX_CELLS
MAX_MATRIX_CELLS = 1000
MAX_ORIGINS = 10  # zones de service
MAX_CONTOURS = 4
MAX_CONTOUR_MINUTES = 60
MAX_RESPONSE_BYTES = 5_242_880
RATE_LIMIT_PER_MIN = 100
_TIMEOUT_S = 15.0
_UNAVAILABLE = "Le service de routage est indisponible."


class RoutingUnavailable(Exception):
    """Service absent, injoignable, bloqué par la garde d'egress ou réponse illisible."""


class RoutingError(Exception):
    """Requête refusée par Valhalla (pas d'itinéraire, point hors réseau…) : erreur d'appelant."""


class _EgressBlocked(Exception):
    pass


def _configured_url() -> str:
    url = os.environ.get("CORE_ROUTING_URL", "").strip().rstrip("/")
    if not url:
        raise RoutingUnavailable("Routage désactivé sur cette instance (CORE_ROUTING_URL vide).")
    return url


def assert_egress_allowed(url: str) -> ValidatedIp:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise _EgressBlocked(f"schéma interdit : {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise _EgressBlocked("hôte absent")
    if host != urlparse(_configured_url()).hostname:
        raise _EgressBlocked(f"hôte hors CORE_ROUTING_URL : {host!r}")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(i[4][0]) for i in socket.getaddrinfo(host, None)]
        except socket.gaierror as exc:
            raise _EgressBlocked(f"hôte non résoluble : {host!r}") from exc
    if not addresses:
        raise _EgressBlocked(f"hôte non résoluble : {host!r}")
    for ip in addresses:
        ip = getattr(ip, "ipv4_mapped", None) or ip  # ::ffff:169.254.169.254 = 169.254.169.254
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            raise _EgressBlocked(f"adresse interdite : {ip}")
    return ValidatedIp(str(addresses[0]), [str(a) for a in addresses])


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return send_pinned(
            self._inner.handle_request, request, assert_egress_allowed(str(request.url))
        )

    def close(self) -> None:
        self._inner.close()


def build_guarded_client() -> httpx.Client:
    return httpx.Client(
        transport=_GuardedTransport(httpx.HTTPTransport()),
        timeout=_TIMEOUT_S,
        follow_redirects=False,
    )


class RateLimited(Exception):
    pass


@functools.cache
def _shared_limiter(backend: str, database_url: str) -> PgRateLimiter | None:
    del backend  # clé de cache seulement (les tests basculent l'env)
    limiter = make_rate_limiter(database_url)
    return limiter if isinstance(limiter, PgRateLimiter) else None


class _Window:
    """Fenêtre glissante par clé (utilisateur), 100 appels/min. CORE_RATELIMIT_BACKEND=postgres :
    budget partagé entre réplicas `core` ET workers (PgRateLimiter, groupe `routing`, ARC-32) ;
    sinon compteur par process (ADR 0019)."""

    def __init__(self, budget: int = RATE_LIMIT_PER_MIN, window: float = 60.0):
        self.budget, self.window = budget, window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        shared = _shared_limiter(
            os.environ.get("CORE_RATELIMIT_BACKEND", "memory"), os.environ.get("DATABASE_URL", "")
        )
        if shared is not None:
            if not shared.allow(f"routing:{key}", "routing"):
                raise RateLimited()
            return
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 1024:  # purge des clés inactives (pas de fuite par utilisateur)
                for k in [k for k, h in self._hits.items() if not h or now - h[-1] > self.window]:
                    del self._hits[k]
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.budget:
                raise RateLimited()
            hits.append(now)

    def acquire(self, key: str, wait: float) -> None:
        """Comme `check`, mais attend jusqu'à `wait` s qu'un créneau se libère (ops de pipeline :
        un run long ralentit au lieu d'échouer)."""
        deadline = time.monotonic() + wait
        while True:
            try:
                return self.check(key)
            except RateLimited:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(min(1.0, self.window / 60))


rate_window = _Window()


def decode_polyline6(shape: str) -> list[list[float]]:
    """Polyline encodée précision 6 (Valhalla) -> [[lon, lat], ...]."""
    coords, i, lat, lon = [], 0, 0, 0
    while i < len(shape):
        for axis in (0, 1):
            result = shift = 0
            while True:
                b = ord(shape[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        coords.append([lon / 1e6, lat / 1e6])
    return coords


def _loc(p: dict) -> dict:
    lon, lat = float(p["lon"]), float(p["lat"])
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("coordonnées hors limites")
    return {"lon": lon, "lat": lat}


def _costing(costing: str) -> str:
    if costing not in COSTINGS:
        raise ValueError(f"costing inconnu : {costing!r} (attendu : {', '.join(COSTINGS)})")
    return costing


class Valhalla:
    def __init__(
        self,
        base_url: str,
        client_factory: Callable[[], httpx.Client] = build_guarded_client,
        throttle: Callable[[], None] | None = None,
    ):
        self._url = base_url
        self._client_factory = client_factory
        # Appelé avant CHAQUE requête amont (service_area = 1 par origine) ; lève RateLimited.
        self._throttle = throttle

    def _post(self, path: str, body: dict) -> dict:
        if self._throttle is not None:
            self._throttle()
        try:
            with self._client_factory() as client:
                response = client.post(f"{self._url}{path}", json=body)
            if response.status_code == 400:  # requête valide mais sans solution
                try:
                    message = str(response.json().get("error", "requête refusée"))
                except ValueError:
                    message = "requête refusée"
                raise RoutingError(message)
            response.raise_for_status()
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise ValueError("réponse de routage trop volumineuse")
            return response.json()
        except RoutingError:
            raise
        except (httpx.HTTPError, _EgressBlocked, ValueError) as exc:
            raise RoutingUnavailable(_UNAVAILABLE) from exc

    def route(self, points: list[dict], costing: str = "auto") -> dict:
        if not 2 <= len(points) <= MAX_ROUTE_POINTS:
            raise ValueError(f"un itinéraire exige 2 à {MAX_ROUTE_POINTS} points")
        data = self._post(
            "/route",
            {
                "locations": [_loc(p) for p in points],
                "costing": _costing(costing),
                "directions_options": {"units": "kilometers", "language": "fr-FR"},
            },
        )
        try:
            trip = data["trip"]
            line: list[list[float]] = []
            legs = []
            for leg in trip["legs"]:
                shape = decode_polyline6(leg["shape"])
                line += shape[1:] if line else shape
                legs.append(
                    {
                        "distance_km": leg["summary"]["length"],
                        "duration_s": leg["summary"]["time"],
                        "maneuvers": [
                            {
                                "instruction": m["instruction"],
                                "distance_km": m["length"],
                                "duration_s": m["time"],
                            }
                            for m in leg.get("maneuvers", [])
                        ],
                    }
                )
            return {
                "distance_km": trip["summary"]["length"],
                "duration_s": trip["summary"]["time"],
                "geometry": {"type": "LineString", "coordinates": line},
                "legs": legs,
            }
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RoutingUnavailable(_UNAVAILABLE) from exc

    def isochrone(self, origin: dict, minutes: list[float], costing: str = "auto") -> dict:
        """FeatureCollection de polygones, `contour_minutes` en propriété."""
        if not 1 <= len(minutes) <= MAX_CONTOURS or any(
            not 0 < m <= MAX_CONTOUR_MINUTES for m in minutes
        ):
            raise ValueError(
                f"1 à {MAX_CONTOURS} contours de 0 à {MAX_CONTOUR_MINUTES} minutes attendus"
            )
        data = self._post(
            "/isochrone",
            {
                "locations": [_loc(origin)],
                "costing": _costing(costing),
                "contours": [{"time": m} for m in sorted(minutes)],
                "polygons": True,
                "generalize": 50,
            },
        )
        try:
            features = [
                {
                    "type": "Feature",
                    "geometry": f["geometry"],
                    "properties": {"contour_minutes": f["properties"]["contour"]},
                }
                for f in data["features"]
                if f["geometry"]["type"] in ("Polygon", "MultiPolygon")
            ]
        except (KeyError, TypeError) as exc:
            raise RoutingUnavailable(_UNAVAILABLE) from exc
        return {"type": "FeatureCollection", "features": features}

    def service_area(
        self, origins: list[dict], minutes: list[float], costing: str = "auto"
    ) -> dict:
        if not 1 <= len(origins) <= MAX_ORIGINS:
            raise ValueError(f"1 à {MAX_ORIGINS} origines attendues")
        features = []
        for index, origin in enumerate(origins):
            for f in self.isochrone(origin, minutes, costing)["features"]:
                f["properties"]["origin_index"] = index
                features.append(f)
        return {"type": "FeatureCollection", "features": features}

    def matrix(self, sources: list[dict], targets: list[dict], costing: str = "auto") -> dict:
        if not (1 <= len(sources) <= MAX_MATRIX_SIDE and 1 <= len(targets) <= MAX_MATRIX_SIDE):
            raise ValueError(f"1 à {MAX_MATRIX_SIDE} sources et cibles attendues")
        if len(sources) * len(targets) > MAX_MATRIX_CELLS:
            raise ValueError(f"matrice limitée à {MAX_MATRIX_CELLS} cellules")
        data = self._post(
            "/sources_to_targets",
            {
                "sources": [_loc(p) for p in sources],
                "targets": [_loc(p) for p in targets],
                "costing": _costing(costing),
                "units": "kilometers",
            },
        )
        try:
            rows = [
                [{"distance_km": c["distance"], "duration_s": c["time"]} for c in row]
                for row in data["sources_to_targets"]
            ]
        except (KeyError, TypeError) as exc:
            raise RoutingUnavailable(_UNAVAILABLE) from exc
        return {"matrix": rows}


def get_routing(throttle: Callable[[], None] | None = None) -> Valhalla:
    return Valhalla(
        _configured_url(), throttle=throttle
    )  # RoutingUnavailable si CORE_ROUTING_URL est vide
