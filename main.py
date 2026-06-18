"""
VintIQ Microservice — FastAPI wrapper around `vinted-api-wrapper`.

Exposes a small HTTP surface that the Lovable app (Cloudflare Workers) can call
to fetch Vinted data. Includes Bearer-token auth, a tiny in-memory TTL cache
and optional proxy support to reduce rate-limit / ban risk.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# vinted-api-wrapper
try:
    from vinted import Vinted  # type: ignore
except Exception:  # pragma: no cover
    from vinted_api_wrapper import Vinted  # type: ignore


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_TOKEN = os.environ.get("API_TOKEN", "").strip()
PROXY_URL = os.environ.get("PROXY_URL", "").strip() or None
DEFAULT_DOMAIN = os.environ.get("DEFAULT_DOMAIN", "de").strip() or "de"
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "60"))

if not API_TOKEN:
    # Service still boots so /health works, but authed routes will 500.
    print("WARNING: API_TOKEN env var is not set. All authed endpoints will reject requests.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="VintIQ Microservice", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # the bearer token is the real gate
    allow_methods=["GET"],
    allow_headers=["*"],
)

bearer = HTTPBearer(auto_error=False)


def require_token(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> None:
    if not API_TOKEN:
        raise HTTPException(status_code=500, detail="Server misconfigured: API_TOKEN not set")
    if creds is None or creds.scheme.lower() != "bearer" or creds.credentials != API_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing bearer token")


# ---------------------------------------------------------------------------
# Vinted client (per-domain singleton)
# ---------------------------------------------------------------------------

_clients: dict[str, Any] = {}


def get_client(domain: str) -> Any:
    domain = (domain or DEFAULT_DOMAIN).strip().lstrip(".")
    if domain not in _clients:
        kwargs: dict[str, Any] = {"domain": domain}
        if PROXY_URL:
            kwargs["proxy"] = PROXY_URL  # supported by vinted-api-wrapper
        try:
            _clients[domain] = Vinted(**kwargs)
        except TypeError:
            # Older/newer signature fallback
            _clients[domain] = Vinted(domain=domain)
    return _clients[domain]


# ---------------------------------------------------------------------------
# Tiny in-memory TTL cache
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}


def cache_get(key: str) -> Any | None:
    hit = _cache.get(key)
    if not hit:
        return None
    expires_at, value = hit
    if expires_at < time.time():
        _cache.pop(key, None)
        return None
    return value


def cache_set(key: str, value: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
    _cache[key] = (time.time() + ttl, value)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "default_domain": DEFAULT_DOMAIN,
        "proxy_configured": bool(PROXY_URL),
        "auth_configured": bool(API_TOKEN),
        "cache_entries": len(_cache),
    }


@app.get("/search", dependencies=[Depends(require_token)])
def search(
    request: Request,
    query: Optional[str] = None,
    catalog_ids: Optional[str] = Query(None, description="Comma-separated IDs"),
    brand_ids: Optional[str] = Query(None, description="Comma-separated IDs"),
    size_ids: Optional[str] = Query(None, description="Comma-separated IDs"),
    color_ids: Optional[str] = Query(None, description="Comma-separated IDs"),
    material_ids: Optional[str] = Query(None, description="Comma-separated IDs"),
    status_ids: Optional[str] = Query(None, description="Comma-separated IDs"),
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
    order: Optional[str] = "newest_first",
    page: int = 1,
    per_page: int = 96,
    domain: str = DEFAULT_DOMAIN,
) -> Any:
    cache_key = f"search::{domain}::{request.url.query}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    client = get_client(domain)
    params: dict[str, Any] = {
        "page": page,
        "per_page": per_page,
        "order": order,
    }
    if query:
        params["search_text"] = query
    if catalog_ids:
        params["catalog_ids"] = catalog_ids
    if brand_ids:
        params["brand_ids"] = brand_ids
    if size_ids:
        params["size_ids"] = size_ids
    if color_ids:
        params["color_ids"] = color_ids
    if material_ids:
        params["material_ids"] = material_ids
    if status_ids:
        params["status_ids"] = status_ids
    if price_from is not None:
        params["price_from"] = price_from
    if price_to is not None:
        params["price_to"] = price_to

    try:
        result = client.search(params=params)
    except TypeError:
        result = client.search(**params)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Vinted search failed: {e}")

    cache_set(cache_key, result)
    return result


@app.get("/item/{item_id}", dependencies=[Depends(require_token)])
def item(item_id: int, domain: str = DEFAULT_DOMAIN) -> Any:
    cache_key = f"item::{domain}::{item_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    client = get_client(domain)
    try:
        result = client.item_info(item_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Vinted item_info failed: {e}")

    cache_set(cache_key, result)
    return result


@app.get("/user/{user_id}", dependencies=[Depends(require_token)])
def user(user_id: int, domain: str = DEFAULT_DOMAIN) -> Any:
    cache_key = f"user::{domain}::{user_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    client = get_client(domain)
    try:
        result = client.user_info(user_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Vinted user_info failed: {e}")

    cache_set(cache_key, result)
    return result
