#@mediavault
"""
Google Drive client – Service Account preferred, OAuth fallback.
Async-friendly wrappers around the synchronous google-api-python-client.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Dict, List, Optional, Tuple

from cachetools import TTLCache
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from tenacity import retry, stop_after_attempt, wait_exponential

from config import (
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_TOKEN_FILE,
    DRIVE_ROOT_FOLDER_ID,
    USE_SERVICE_ACCOUNT,
    CACHE_TTL_SECONDS,
    MAX_FILE_SIZE_MB,
)

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_executor = ThreadPoolExecutor(max_workers=8)

# Simple in-memory caches
_folder_cache: TTLCache = TTLCache(maxsize=256, ttl=CACHE_TTL_SECONDS)
_search_cache: TTLCache = TTLCache(maxsize=128, ttl=CACHE_TTL_SECONDS)


class DriveClient:
    def __init__(self):
        self.service = None
        self.root_id = DRIVE_ROOT_FOLDER_ID or "root"

    def _build_service(self):
        if USE_SERVICE_ACCOUNT and os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
            creds = service_account.Credentials.from_service_account_file(
                GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
            logger.info("Using Google Service Account")
        else:
            creds = None
            if os.path.exists(GOOGLE_TOKEN_FILE):
                creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_FILE, SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
                        raise FileNotFoundError(
                            "Neither service_account.json nor credentials.json found. "
                            "See README for Google Drive setup."
                        )
                    flow = InstalledAppFlow.from_client_secrets_file(
                        GOOGLE_CREDENTIALS_FILE, SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                with open(GOOGLE_TOKEN_FILE, "w") as token:
                    token.write(creds.to_json())
            logger.info("Using Google OAuth credentials")

        self.service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self.service

    async def connect(self):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, self._build_service)
        logger.info("Google Drive client ready")

    def _run(self, func, *args, **kwargs):
        """Run blocking google client call in thread pool."""
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(_executor, partial(func, *args, **kwargs))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _list_files_sync(
        self,
        query: str,
        page_size: int = 50,
        page_token: str | None = None,
        order_by: str = "folder,name",
    ) -> Dict[str, Any]:
        return (
            self.service.files()
            .list(
                q=query,
                pageSize=page_size,
                pageToken=page_token,
                fields="nextPageToken, files(id, name, mimeType, size, parents, modifiedTime, webViewLink, iconLink, thumbnailLink)",
                orderBy=order_by,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )

    async def list_folder(
        self,
        folder_id: str | None = None,
        page_token: str | None = None,
        page_size: int = 30,
    ) -> Tuple[List[Dict], Optional[str]]:
        folder_id = folder_id or self.root_id
        cache_key = f"folder:{folder_id}:{page_token or '0'}"
        if cache_key in _folder_cache:
            return _folder_cache[cache_key]

        query = f"'{folder_id}' in parents and trashed = false"
        result = await self._run(self._list_files_sync, query, page_size, page_token)
        files = result.get("files", [])
        next_token = result.get("nextPageToken")
        _folder_cache[cache_key] = (files, next_token)
        return files, next_token

    async def search(
        self,
        query: str,
        page_size: int = 20,
        mime_filter: str | None = None,
    ) -> List[Dict]:
        cache_key = f"search:{query}:{mime_filter or ''}"
        if cache_key in _search_cache:
            return _search_cache[cache_key]

        # Escape single quotes
        safe = query.replace("'", "\\'")
        q_parts = [f"name contains '{safe}'", "trashed = false"]
        if mime_filter:
            q_parts.append(f"mimeType contains '{mime_filter}'")
        if self.root_id and self.root_id != "root":
            # Restrict to subtree is harder; for simplicity we still search whole accessible Drive
            pass
        full_q = " and ".join(q_parts)

        result = await self._run(self._list_files_sync, full_q, page_size, None, "name")
        files = result.get("files", [])
        _search_cache[cache_key] = files
        return files

    async def get_file(self, file_id: str) -> Optional[Dict]:
        def _get():
            return (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields="id, name, mimeType, size, parents, modifiedTime, webViewLink, md5Checksum",
                    supportsAllDrives=True,
                )
                .execute()
            )

        try:
            return await self._run(_get)
        except Exception as e:
            logger.error(f"get_file error: {e}")
            return None

    async def download_file(
        self,
        file_id: str,
        dest_path: str,
        progress_callback=None,
    ) -> Optional[str]:
        """
        Download a file to dest_path.
        progress_callback(current: int, total: int) optional.
        Returns path on success.
        """
        meta = await self.get_file(file_id)
        if not meta:
            return None
        size = int(meta.get("size") or 0)
        if size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(f"File too large ({size / 1024 / 1024:.1f} MB > limit)")

        def _download():
            request = self.service.files().get_media(fileId=file_id, supportsAllDrives=True)
            os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
            with io.FileIO(dest_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request, chunksize=1024 * 1024)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status and progress_callback:
                        # progress_callback must be sync-safe or we schedule it
                        current = int(status.resumable_progress)
                        total = int(status.total_size or size or 1)
                        # We can't easily await here; caller can use a queue if needed
                        try:
                            progress_callback(current, total)
                        except Exception:
                            pass
            return dest_path

        return await self._run(_download)

    async def get_path(self, file_id: str) -> str:
        """Reconstruct approximate path by walking parents (limited depth)."""
        parts = []
        current = file_id
        for _ in range(12):  # safety
            meta = await self.get_file(current)
            if not meta:
                break
            parts.append(meta.get("name", "?"))
            parents = meta.get("parents") or []
            if not parents or parents[0] == self.root_id:
                break
            current = parents[0]
        return " / ".join(reversed(parts))


# Global instance
drive = DriveClient()
