#@mediavault
"""Legal metadata: TMDB search + watch providers (no streams)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from config import TMDB_API_KEY, TMDB_REGION

logger = logging.getLogger(__name__)
BASE = "https://api.themoviedb.org/3"


async def search(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    if not TMDB_API_KEY:
        return []
    url = f"{BASE}/search/multi"
    params = {"api_key": TMDB_API_KEY, "query": query, "include_adult": "false"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return []
            data = await r.json()
    out = []
    for item in data.get("results") or []:
        media = item.get("media_type")
        if media not in ("movie", "tv"):
            continue
        out.append({
            "id": item.get("id"),
            "media_type": media,
            "title": item.get("title") or item.get("name") or "?",
            "year": (item.get("release_date") or item.get("first_air_date") or "")[:4],
            "overview": (item.get("overview") or "")[:280],
            "poster": f"https://image.tmdb.org/t/p/w342{item['poster_path']}" if item.get("poster_path") else None,
        })
        if len(out) >= limit:
            break
    return out


async def watch_providers(media_type: str, tmdb_id: int, region: str | None = None) -> Dict[str, Any]:
    if not TMDB_API_KEY:
        return {}
    region = region or TMDB_REGION
    url = f"{BASE}/{media_type}/{tmdb_id}/watch/providers"
    params = {"api_key": TMDB_API_KEY}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return {}
            data = await r.json()
    results = (data.get("results") or {}).get(region) or {}
    providers = []
    for kind in ("flatrate", "rent", "buy", "free"):
        for p in results.get(kind) or []:
            providers.append({
                "name": p.get("provider_name"),
                "type": kind,
                "logo": f"https://image.tmdb.org/t/p/w45{p['logo_path']}" if p.get("logo_path") else None,
            })
    return {
        "link": results.get("link"),
        "providers": providers,
        "region": region,
    }
