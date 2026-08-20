#@mediavault
"""ffmpeg helpers, auto-tags (guessit), metadata cards."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config import FFMPEG_PATH

logger = logging.getLogger(__name__)


def auto_tags(title: str) -> Dict[str, Any]:
    """Extract show/movie metadata via guessit."""
    try:
        from guessit import guessit
        g = guessit(title)
        return {
            "clean_title": g.get("title") or title,
            "year": g.get("year"),
            "season": g.get("season"),
            "episode": g.get("episode"),
            "type": g.get("type"),
            "screen_size": g.get("screen_size"),
        }
    except Exception:
        return {"clean_title": title}


async def run_ffmpeg(args: list[str], timeout: int = 600) -> Tuple[int, str, str]:
    cmd = [FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error"] + args
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", "ffmpeg timeout"
    return proc.returncode or 0, out.decode(errors="ignore"), err.decode(errors="ignore")


async def extract_audio(video_path: str, out_path: str | None = None) -> Optional[str]:
    out = out_path or str(Path(video_path).with_suffix(".m4a"))
    code, _, err = await run_ffmpeg(["-i", video_path, "-vn", "-acodec", "copy", out])
    if code != 0:
        # fallback re-encode
        code, _, err = await run_ffmpeg(["-i", video_path, "-vn", "-acodec", "aac", "-b:a", "192k", out])
    if code == 0 and os.path.exists(out):
        return out
    logger.warning("extract_audio failed: %s", err)
    return None


async def mux_av(video: str, audio: str, out_path: str) -> Optional[str]:
    code, _, err = await run_ffmpeg([
        "-i", video, "-i", audio,
        "-c", "copy", "-map", "0:v:0", "-map", "1:a:0",
        out_path,
    ])
    if code == 0 and os.path.exists(out_path):
        return out_path
    logger.warning("mux failed: %s", err)
    return None


async def embed_subs(video: str, srt: str, out_path: str) -> Optional[str]:
    code, _, err = await run_ffmpeg([
        "-i", video, "-i", srt,
        "-c", "copy", "-c:s", "mov_text",
        out_path,
    ])
    if code == 0 and os.path.exists(out_path):
        return out_path
    # soft fail — return original
    return None


def metadata_card(
    title: str,
    *,
    uploader: str = "",
    duration: int | None = None,
    size: int | None = None,
    extractor: str = "",
    quality: str = "",
    tags: Dict | None = None,
    url: str = "",
    quota: str = "",
) -> str:
    from core.utils import format_size
    dur = f"{duration // 60}:{duration % 60:02d}" if duration else "—"
    size_s = format_size(size) if size else "—"
    tag_line = ""
    if tags:
        bits = []
        if tags.get("clean_title") and tags["clean_title"] != title:
            bits.append(tags["clean_title"])
        if tags.get("year"):
            bits.append(str(tags["year"]))
        if tags.get("season") is not None:
            bits.append(f"S{tags['season']:02d}")
        if tags.get("episode") is not None:
            bits.append(f"E{tags['episode']:02d}")
        if bits:
            tag_line = "🏷 " + " • ".join(str(b) for b in bits) + "\n"

    return (
        f"<blockquote>🎬 <b>{title[:90]}</b>\n"
        f"{tag_line}"
        f"👤 {uploader or '—'}\n"
        f"⏱ {dur} | 📦 {size_s}\n"
        f"🌐 {extractor or 'web'}"
        f"{(' | ' + quality) if quality else ''}\n"
        f"{('📊 ' + quota + chr(10)) if quota else ''}"
        f"</blockquote>"
    )


def ffmpeg_available() -> bool:
    return shutil.which(FFMPEG_PATH) is not None
