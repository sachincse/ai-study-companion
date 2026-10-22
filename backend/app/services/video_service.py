"""Lecture discovery: YouTube Data API when a key is configured, yt-dlp search as a
keyless fallback, plus a curated list of channels known for AKTU-oriented lectures.
Results are cached in memory for a few hours to respect quotas.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote_plus

import httpx
import yaml

from app.core.config import get_settings

log = logging.getLogger(__name__)
CACHE_TTL = 6 * 3600
_cache: dict[str, tuple[float, list[dict]]] = {}


@dataclass
class Video:
    video_id: str
    title: str
    channel: str
    url: str
    thumbnail: str
    source: str
    duration_sec: int | None = None
    view_count: int | None = None
    published_at: str | None = None


def build_query(subject_name: str | None, topic: str | None, subject_code: str | None = None) -> str:
    parts = [p for p in (subject_code, subject_name, topic) if p]
    query = " ".join(parts) + " AKTU"
    return query.strip()


async def search_youtube_api(query: str, max_results: int) -> list[Video]:
    settings = get_settings()
    params = {
        "part": "snippet",
        "type": "video",
        "maxResults": max_results,
        "q": query,
        "relevanceLanguage": "en",
        "safeSearch": "strict",
        "videoEmbeddable": "true",
        "key": settings.youtube_api_key,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("https://www.googleapis.com/youtube/v3/search", params=params)
        resp.raise_for_status()
        data = resp.json()
    out: list[Video] = []
    for item in data.get("items", []):
        vid = (item.get("id") or {}).get("videoId")
        snip = item.get("snippet") or {}
        if not vid:
            continue
        out.append(
            Video(
                video_id=vid,
                title=snip.get("title", ""),
                channel=snip.get("channelTitle", ""),
                url=f"https://www.youtube.com/watch?v={vid}",
                thumbnail=((snip.get("thumbnails") or {}).get("medium") or {}).get("url", f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"),
                source="youtube_api",
                published_at=snip.get("publishedAt"),
            )
        )
    return out


def _ytdlp_search_sync(query: str, max_results: int) -> list[Video]:
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "noplaylist": True, "skip_download": True, "socket_timeout": 15}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
    out: list[Video] = []
    for entry in (info or {}).get("entries") or []:
        vid = entry.get("id")
        if not vid:
            continue
        thumbs = entry.get("thumbnails") or []
        thumb = thumbs[-1]["url"] if thumbs else f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
        out.append(
            Video(
                video_id=vid,
                title=entry.get("title") or "",
                channel=entry.get("channel") or entry.get("uploader") or "",
                url=entry.get("url") if str(entry.get("url", "")).startswith("http") else f"https://www.youtube.com/watch?v={vid}",
                thumbnail=thumb,
                source="ytdlp",
                duration_sec=int(entry["duration"]) if entry.get("duration") else None,
                view_count=entry.get("view_count"),
            )
        )
    return out


async def search_videos(query: str, max_results: int = 8) -> tuple[list[dict], str]:
    """Return (videos, source). Source is youtube_api | ytdlp | none."""
    settings = get_settings()
    key = f"{query.lower()}|{max_results}"
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1], (cached[1][0]["source"] if cached[1] else "none")
    videos: list[Video] = []
    source = "none"
    if settings.youtube_api_key:
        try:
            videos = await search_youtube_api(query, max_results)
            source = "youtube_api"
        except Exception as exc:  # noqa: BLE001
            log.warning("YouTube Data API failed: %s", exc)
    if not videos and settings.enable_ytdlp_fallback:
        try:
            videos = await asyncio.wait_for(asyncio.to_thread(_ytdlp_search_sync, query, max_results), timeout=40)
            source = "ytdlp" if videos else source
        except Exception as exc:  # noqa: BLE001
            log.warning("yt-dlp search failed: %s", exc)
    payload = [asdict(v) for v in videos]
    if payload:
        _cache[key] = (time.time(), payload)
    return payload, source


def load_curated() -> dict:
    path = get_settings().data_dir / "videos" / "curated.yaml"
    if not path.exists():
        return {"channels": [], "subjects": {}}
    with Path(path).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {"channels": [], "subjects": {}}


def curated_for(subject_code: str | None, topic: str | None, subject_name: str | None = None) -> dict:
    data = load_curated()
    channels = data.get("channels", [])
    per_subject = (data.get("subjects") or {}).get((subject_code or "").upper(), {})
    picks = []
    preferred = set(per_subject.get("channels", []))
    for ch in channels:
        if preferred and ch.get("id") not in preferred:
            continue
        q = " ".join(p for p in (ch.get("search_prefix", ""), subject_name or subject_code or "", topic or "") if p).strip()
        picks.append(
            {
                "id": ch.get("id"),
                "name": ch.get("name"),
                "url": ch.get("url"),
                "why": ch.get("why", ""),
                "search_url": "https://www.youtube.com/results?search_query=" + quote_plus(q or ch.get("name", "")),
            }
        )
    return {"channels": picks, "playlists": per_subject.get("playlists", []), "tips": data.get("tips", [])}
