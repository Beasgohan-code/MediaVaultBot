#@mediavault
"""
Universal yt-dlp with real format listing, quality override, playlist cap, cookies.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import yt_dlp

from config import (
    YTDLP_ENABLED, YTDLP_MAX_FILESIZE, YTDLP_FORMAT,
    YTDLP_COOKIES_FILE, YTDLP_COOKIES_FROM_BROWSER,
    YTDLP_OUTPUT_TEMPLATE, YTDLP_AGE_LIMIT, YTDLP_PLAYLIST_MAX,
    MAX_FILE_SIZE_MB, QUALITY_PRESETS,
)

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=4)

TMP_DIR = Path(tempfile.gettempdir()) / "mediavault_ytdlp"
TMP_DIR.mkdir(exist_ok=True)


def is_supported_url(url: str) -> bool:
    if not YTDLP_ENABLED:
        return False
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def resolve_format(quality_key: str | None) -> str:
    if not quality_key:
        return YTDLP_FORMAT
    if quality_key.startswith("fmt:"):
        # exact format id from yt-dlp
        return quality_key[4:]
    return QUALITY_PRESETS.get(quality_key, YTDLP_FORMAT)


def _parse_size(s: str) -> Optional[int]:
    if not s:
        return None
    s = s.strip().upper()
    units = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3}
    m = re.match(r"^([\d.]+)\s*([KMGT]?B?)?$", s)
    if not m:
        return None
    num = float(m.group(1))
    unit = (m.group(2) or "B").rstrip("B") or "B"
    return int(num * units.get(unit, 1))


def _progress_hook_factory(callback: Optional[Callable[[dict], None]], cancel_check: Optional[Callable[[], bool]] = None):
    def hook(d: dict):
        if cancel_check and cancel_check():
            raise Exception("Cancelled by user")
        if callback:
            try:
                callback(d)
            except Exception:
                pass
    return hook


def _cookie_opts() -> Dict[str, Any]:
    opts: Dict[str, Any] = {}
    if YTDLP_COOKIES_FILE and os.path.exists(YTDLP_COOKIES_FILE):
        opts["cookiefile"] = YTDLP_COOKIES_FILE
    elif YTDLP_COOKIES_FROM_BROWSER:
        parts = YTDLP_COOKIES_FROM_BROWSER.strip().split(":")
        browser = parts[0].lower()
        profile = parts[1] if len(parts) > 1 else None
        opts["cookiesfrombrowser"] = (browser, profile, None, None)
    return opts


def _build_ydl_opts(
    out_dir: str,
    format_str: str | None = None,
    progress_callback: Optional[Callable[[dict], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    playlist: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    outtmpl = str(Path(out_dir) / YTDLP_OUTPUT_TEMPLATE)
    opts: Dict[str, Any] = {
        "format": format_str or YTDLP_FORMAT,
        "outtmpl": outtmpl,
        "noplaylist": not playlist,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "max_filesize": _parse_size(YTDLP_MAX_FILESIZE),
        "progress_hooks": [_progress_hook_factory(progress_callback, cancel_check)],
        "writethumbnail": True,
        "writesubtitles": True,
        "writeautomaticsub": False,
        "subtitleslangs": ["en", "en-US", "hi"],
        "writeinfojson": False,
        "ignoreerrors": False,
        "geo_bypass": True,
        "socket_timeout": 30,
        "age_limit": YTDLP_AGE_LIMIT if YTDLP_AGE_LIMIT > 0 else None,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web", "mweb", "ios"],
                "player_skip": ["webpage", "configs"],
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        },
    }
    if playlist and YTDLP_PLAYLIST_MAX > 0:
        opts["playlistend"] = YTDLP_PLAYLIST_MAX
    opts.update(_cookie_opts())
    if extra:
        opts.update(extra)
    return opts


def _safe_extract_info(opts: Dict[str, Any], url: str, download: bool = False) -> Any:
    """Run yt-dlp extract_info. If browser cookie database fails, strip cookiesfrombrowser and retry."""
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=download)
    except Exception as e:
        err_str = str(e).lower()
        if ("cookies database" in err_str or "could not find" in err_str or "cookie" in err_str) and "cookiesfrombrowser" in opts:
            logger.warning("Browser cookie database failed (%s). Retrying without cookiesfrombrowser...", e)
            opts.pop("cookiesfrombrowser", None)
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download)
        raise e


def list_formats_sync(url: str) -> List[Dict[str, Any]]:
    """Return simplified format list for UI."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        **_cookie_opts(),
    }
    info = _safe_extract_info(opts, url, download=False)
    if not info:
        return []
    formats = info.get("formats") or []
    seen = set()
    out = []
    for f in formats:
        fid = f.get("format_id")
        if not fid or fid in seen:
            continue
        height = f.get("height")
        acodec = f.get("acodec")
        vcodec = f.get("vcodec")
        ext = f.get("ext")
        filesize = f.get("filesize") or f.get("filesize_approx")
        # skip pure storyboard etc
        if vcodec == "none" and acodec == "none":
            continue
        note = f.get("format_note") or ""
        label_parts = []
        if height:
            label_parts.append(f"{height}p")
        elif vcodec == "none":
            label_parts.append("audio")
        if ext:
            label_parts.append(ext)
        if note:
            label_parts.append(note[:20])
        if filesize:
            label_parts.append(f"{filesize // (1024*1024)}MB" if filesize > 1024*1024 else f"{filesize // 1024}KB")
        label = " • ".join(label_parts) or fid
        seen.add(fid)
        out.append({
            "id": fid,
            "label": label[:40],
            "height": height or 0,
            "filesize": filesize,
            "ext": ext,
            "vcodec": vcodec,
            "acodec": acodec,
        })
    # sort: video height desc, then audio
    out.sort(key=lambda x: (x["height"] or (1 if x.get("acodec") != "none" else 0), x["height"] or 0), reverse=True)
    return out[:18]  # keep keyboard manageable


def _download_sync(
    url: str,
    out_dir: str,
    format_str: str | None = None,
    progress_callback: Optional[Callable[[dict], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    playlist: bool = False,
) -> Dict[str, Any]:
    ydl_opts = _build_ydl_opts(out_dir, format_str, progress_callback, cancel_check, playlist)
    info = _safe_extract_info(ydl_opts, url, download=True)
    if info is None:
        raise RuntimeError("yt-dlp returned no info")
    # playlist → first entry for simplicity of single-send path
    if "entries" in info:
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise RuntimeError("Empty playlist")
        info = entries[0]
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            base, _ = os.path.splitext(filename)
            for ext in (".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".ogg", ".mov"):
                candidate = base + ext
                if os.path.exists(candidate):
                    filename = candidate
                    break
        return {
            "id": info.get("id"),
            "title": info.get("title") or "Unknown",
            "ext": info.get("ext"),
            "filesize": info.get("filesize") or info.get("filesize_approx"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader") or info.get("channel"),
            "webpage_url": info.get("webpage_url") or url,
            "extractor": info.get("extractor_key") or info.get("extractor"),
            "filepath": filename,
            "thumbnail": info.get("thumbnail"),
            "age_limit": info.get("age_limit"),
        }


async def list_formats(url: str) -> List[Dict[str, Any]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, lambda: list_formats_sync(url))





# Domain catalog: homepage + optional yt-dlp search template
SITE_CATALOG = {
    "youtube.com": {
        "name": "YouTube",
        "home": "https://www.youtube.com",
        "search": "ytsearch{n}:{q}",
        "notes": "Video / music",
    },
    "youtu.be": {
        "name": "YouTube (short)",
        "home": "https://youtu.be",
        "search": "ytsearch{n}:{q}",
        "notes": "Short links",
    },
    "spotify.com": {
        "name": "Spotify",
        "home": "https://open.spotify.com",
        "search": "ytsearch{n}:{q}",
        "notes": "Audio tracks / albums (search fallback)",
    },
    "instagram.com": {
        "name": "Instagram",
        "home": "https://www.instagram.com",
        "search": None,
        "notes": "Reels, Posts, Stories",
    },
    "crunchyroll.com": {
        "name": "Crunchyroll / Anime",
        "home": "https://www.crunchyroll.com",
        "search": None,
        "notes": "Anime episodes",
    },
    "bilibili.com": {
        "name": "Bilibili / Anime",
        "home": "https://www.bilibili.com",
        "search": None,
        "notes": "Anime & videos",
    },
    "soundcloud.com": {
        "name": "SoundCloud",
        "home": "https://soundcloud.com",
        "search": "scsearch{n}:{q}",
        "notes": "Audio",
    },
    "reddit.com": {
        "name": "Reddit",
        "home": "https://www.reddit.com",
        "search": None,
        "notes": "Paste post URL",
    },
    "redd.it": {
        "name": "Reddit short",
        "home": "https://redd.it",
        "search": None,
        "notes": "Paste link",
    },
    "x.com": {
        "name": "X (Twitter)",
        "home": "https://x.com",
        "search": None,
        "notes": "Paste post URL",
    },
    "twitter.com": {
        "name": "Twitter",
        "home": "https://twitter.com",
        "search": None,
        "notes": "Paste post URL",
    },
    "tiktok.com": {
        "name": "TikTok",
        "home": "https://www.tiktok.com",
        "search": None,
        "notes": "Paste video URL",
    },
    "instagram.com": {
        "name": "Instagram",
        "home": "https://www.instagram.com",
        "search": None,
        "notes": "Paste post URL",
    },
    "facebook.com": {
        "name": "Facebook",
        "home": "https://www.facebook.com",
        "search": None,
        "notes": "Paste video URL",
    },
    "vimeo.com": {
        "name": "Vimeo",
        "home": "https://vimeo.com",
        "search": None,
        "notes": "Paste video URL",
    },
    "bandcamp.com": {
        "name": "Bandcamp",
        "home": "https://bandcamp.com",
        "search": None,
        "notes": "Paste track/album URL",
    },
    "twitch.tv": {
        "name": "Twitch",
        "home": "https://www.twitch.tv",
        "search": None,
        "notes": "Clips / VODs — paste URL",
    },
    "streamable.com": {
        "name": "Streamable",
        "home": "https://streamable.com",
        "search": None,
        "notes": "Paste video URL",
    },
}

# Backends that support keyword search via yt-dlp
SEARCH_BACKENDS = {
    k: (v["search"], v["name"])
    for k, v in SITE_CATALOG.items()
    if v.get("search")
}
# alias keys for UI
SEARCH_BACKENDS = {
    "youtube": ("ytsearch{n}:{q}", "YouTube"),
    "soundcloud": ("scsearch{n}:{q}", "SoundCloud"),
    "bilibili": ("ytsearch{n}:bilibili {q}", "Bilibili"),
    "universal": ("ytsearch{n}:{q}", "Universal Web"),
}


def web_search_sync(query: str, limit: int = 10, source: str = "all") -> List[Dict[str, Any]]:
    """Search YouTube / SoundCloud (and more) via yt-dlp search extractors."""
    q = (query or "").strip()
    if not q:
        return []
    limit = max(1, min(int(limit), 20))
    sources = list(SEARCH_BACKENDS.keys()) if source in ("all", "", None) else [source]
    results: List[Dict[str, Any]] = []
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        **_cookie_opts(),
    }
    per = max(3, limit // max(1, len(sources))) if source == "all" else limit
    for key in sources:
        if key not in SEARCH_BACKENDS:
            continue
        tmpl, label = SEARCH_BACKENDS[key]
        search_url = tmpl.format(n=per, q=q)
        try:
            info = _safe_extract_info(opts, search_url, download=False)
            for e in (info or {}).get("entries") or []:
                if not e:
                    continue
                vid = e.get("id") or ""
                url = e.get("url") or e.get("webpage_url") or ""
                if key == "youtube" and vid and not str(url).startswith("http"):
                    url = f"https://www.youtube.com/watch?v={vid}"
                if key == "soundcloud" and vid and not str(url).startswith("http"):
                    url = f"https://soundcloud.com/{vid}" if "/" in str(vid) else url
                if not url or not str(url).startswith("http"):
                    # flat entries sometimes only have id
                    if key == "youtube" and vid:
                        url = f"https://www.youtube.com/watch?v={vid}"
                    else:
                        continue
                results.append({
                    "id": str(vid),
                    "title": e.get("title") or "Untitled",
                    "url": url,
                    "duration": e.get("duration"),
                    "uploader": e.get("uploader") or e.get("channel") or "",
                    "view_count": e.get("view_count"),
                    "source": label,
                    "source_key": key,
                })
        except Exception as ex:
            logger.warning("search %s failed: %s", key, ex)
    return results[:limit]


async def web_search(query: str, limit: int = 10, source: str = "all") -> List[Dict[str, Any]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor, lambda: web_search_sync(query, limit, source)
    )


async def extract_info(url: str, playlist: bool = False) -> Dict[str, Any]:
    def _info():
        opts = _build_ydl_opts("/tmp", playlist=playlist, extra={"skip_download": True})
        opts.pop("progress_hooks", None)
        return _safe_extract_info(opts, url, download=False)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _info)


async def download(
    url: str,
    user_id: int,
    quality: str | None = None,
    progress_callback: Optional[Callable[[dict], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    playlist: bool = False,
) -> Dict[str, Any]:
    if not is_supported_url(url):
        raise ValueError("URL not supported or yt-dlp disabled")
    fmt = resolve_format(quality)
    out_dir = str(TMP_DIR / str(user_id))
    os.makedirs(out_dir, exist_ok=True)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _executor,
        lambda: _download_sync(url, out_dir, fmt, progress_callback, cancel_check, playlist),
    )
    path = result.get("filepath")
    if not path or not os.path.exists(path):
        raise FileNotFoundError("Download finished but file missing")
    size = os.path.getsize(path)
    if size > MAX_FILE_SIZE_MB * 1024 * 1024:
        try:
            os.unlink(path)
        except Exception:
            pass
        raise ValueError(f"File too large ({size / 1024 / 1024:.1f} MB)")
    result["filesize"] = size
    return result
