#@mediavault
"""Async PostgreSQL — users, library, collections, schedules, quotas."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Integer, String, Text,
    select, update, delete, func, UniqueConstraint,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine, AsyncEngine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import DATABASE_URL, OWNER_ID

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ban_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    preferred_quality: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    settings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Favorite(Base):
    __tablename__ = "favorites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    file_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DownloadLog(Base):
    __tablename__ = "download_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    file_id: Mapped[str] = mapped_column(String(256))
    file_name: Mapped[str] = mapped_column(String(512))
    size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RateEvent(Base):
    __tablename__ = "rate_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class LibraryItem(Base):
    """Unified index of downloaded / known media."""
    __tablename__ = "library_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    source: Mapped[str] = mapped_column(String(32))  # ytdlp | drive
    external_id: Mapped[str] = mapped_column(String(256), index=True)
    title: Mapped[str] = mapped_column(String(512))
    clean_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    season: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    episode: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    extractor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    webpage_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CollectionItem(Base):
    __tablename__ = "collection_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(Integer, index=True)
    library_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    url: Mapped[str] = mapped_column(Text)
    quality: Mapped[str] = mapped_column(String(32), default="best")
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|done|failed|cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Database:
    def __init__(self, url: str = DATABASE_URL):
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._url = url

    async def connect(self) -> None:
        self.engine = create_async_engine(self._url, echo=False, pool_size=10, max_overflow=20, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL ready")
        if OWNER_ID:
            await self.ensure_user(OWNER_ID, is_admin=True)

    async def close(self) -> None:
        if self.engine:
            await self.engine.dispose()

    async def _session(self) -> AsyncSession:
        assert self.session_factory
        return self.session_factory()

    # ── Users ──
    async def ensure_user(self, user_id: int, username: str | None = None, full_name: str | None = None, is_admin: bool = False) -> User:
        async with await self._session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(id=user_id, username=username, full_name=full_name, is_admin=is_admin or (user_id == OWNER_ID))
                session.add(user)
            else:
                user.username = username or user.username
                user.full_name = full_name or user.full_name
                user.last_active = datetime.now(timezone.utc)
                if is_admin:
                    user.is_admin = True
            await session.commit()
            await session.refresh(user)
            return user

    async def is_admin(self, user_id: int) -> bool:
        if user_id == OWNER_ID:
            return True
        async with await self._session() as session:
            r = await session.execute(select(User.is_admin).where(User.id == user_id))
            return bool(r.scalar_one_or_none())

    async def is_banned(self, user_id: int) -> bool:
        async with await self._session() as session:
            r = await session.execute(select(User).where(User.id == user_id))
            user = r.scalar_one_or_none()
            if not user or not user.is_banned:
                return False
            if user.ban_until and user.ban_until < datetime.now(timezone.utc):
                user.is_banned = False
                user.ban_until = None
                user.ban_reason = None
                await session.commit()
                return False
            return True

    async def ban_user(self, user_id: int, reason: str = "", days: int | None = None) -> None:
        until = datetime.now(timezone.utc) + timedelta(days=days) if days and days > 0 else None
        async with await self._session() as session:
            await session.execute(update(User).where(User.id == user_id).values(is_banned=True, ban_reason=reason, ban_until=until))
            await session.commit()

    async def unban_user(self, user_id: int) -> None:
        async with await self._session() as session:
            await session.execute(update(User).where(User.id == user_id).values(is_banned=False, ban_reason=None, ban_until=None))
            await session.commit()

    async def get_user_count(self) -> int:
        async with await self._session() as session:
            r = await session.execute(select(func.count()).select_from(User))
            return r.scalar_one()

    async def list_admins(self) -> List[User]:
        async with await self._session() as session:
            r = await session.execute(select(User).where(User.is_admin == True))
            return list(r.scalars().all())

    async def get_preferred_quality(self, user_id: int) -> str | None:
        async with await self._session() as session:
            r = await session.execute(select(User.preferred_quality).where(User.id == user_id))
            return r.scalar_one_or_none()

    async def set_preferred_quality(self, user_id: int, quality: str) -> None:
        async with await self._session() as session:
            await session.execute(update(User).where(User.id == user_id).values(preferred_quality=quality))
            await session.commit()

    # ── Settings ──
    async def get_setting(self, key: str, default: Any = None) -> Any:
        async with await self._session() as session:
            r = await session.execute(select(Setting.value).where(Setting.key == key))
            val = r.scalar_one_or_none()
            if val is None:
                return default
            if val.lower() in ("true", "false"):
                return val.lower() == "true"
            try:
                return int(val)
            except ValueError:
                return val

    async def set_setting(self, key: str, value: Any) -> None:
        async with await self._session() as session:
            existing = await session.execute(select(Setting).where(Setting.key == key))
            row = existing.scalar_one_or_none()
            if row:
                row.value = str(value)
                row.updated_at = datetime.now(timezone.utc)
            else:
                session.add(Setting(key=key, value=str(value)))
            await session.commit()

    # ── Favorites ──
    async def add_favorite(self, user_id: int, file_id: str, name: str, mime_type: str | None = None, size: int | None = None) -> None:
        async with await self._session() as session:
            exists = await session.execute(select(Favorite).where(Favorite.user_id == user_id, Favorite.file_id == file_id))
            if exists.scalar_one_or_none():
                return
            session.add(Favorite(user_id=user_id, file_id=file_id, name=name, mime_type=mime_type, size=size))
            await session.commit()

    async def list_favorites(self, user_id: int) -> List[Favorite]:
        async with await self._session() as session:
            r = await session.execute(select(Favorite).where(Favorite.user_id == user_id).order_by(Favorite.added_at.desc()))
            return list(r.scalars().all())

    # ── Logs ──
    async def log_download(self, user_id: int, file_id: str, file_name: str, size: int | None = None, status: str = "success") -> None:
        async with await self._session() as session:
            session.add(DownloadLog(user_id=user_id, file_id=file_id, file_name=file_name, size=size, status=status))
            await session.commit()

    # ── Quota ──
    async def get_daily_usage(self, user_id: int) -> tuple[int, int]:
        today = datetime.now(timezone.utc).date()
        async with await self._session() as session:
            r = await session.execute(
                select(func.count(DownloadLog.id), func.coalesce(func.sum(DownloadLog.size), 0)).where(
                    DownloadLog.user_id == user_id,
                    func.date(DownloadLog.created_at) == today,
                    DownloadLog.status == "success",
                )
            )
            row = r.one()
            return int(row[0] or 0), int(row[1] or 0)

    async def check_quota(self, user_id: int) -> tuple[bool, str]:
        from config import QUOTA_DAILY_DOWNLOADS, QUOTA_DAILY_MB, QUOTA_ADMIN_UNLIMITED, OWNER_ID
        if QUOTA_ADMIN_UNLIMITED and (user_id == OWNER_ID or await self.is_admin(user_id)):
            return True, "unlimited (admin)"
        count, bytes_used = await self.get_daily_usage(user_id)
        mb_used = bytes_used / (1024 * 1024)
        if QUOTA_DAILY_DOWNLOADS > 0 and count >= QUOTA_DAILY_DOWNLOADS:
            return False, f"Daily limit {QUOTA_DAILY_DOWNLOADS} downloads reached"
        if QUOTA_DAILY_MB > 0 and mb_used >= QUOTA_DAILY_MB:
            return False, f"Daily limit {QUOTA_DAILY_MB} MB reached"
        return True, f"{count}/{QUOTA_DAILY_DOWNLOADS or '∞'} dl • {mb_used:.0f}/{QUOTA_DAILY_MB or '∞'} MB"

    async def check_rate_limit(self, user_id: int, limit_per_min: int) -> tuple[bool, int]:
        if limit_per_min <= 0:
            return True, 0
        since = datetime.now(timezone.utc) - timedelta(minutes=1)
        async with await self._session() as session:
            r = await session.execute(select(func.count(RateEvent.id)).where(RateEvent.user_id == user_id, RateEvent.created_at >= since))
            count = int(r.scalar_one() or 0)
            if count >= limit_per_min:
                return False, count
            session.add(RateEvent(user_id=user_id))
            await session.commit()
            return True, count + 1

    # ── Library ──
    async def add_library_item(self, **kwargs) -> LibraryItem:
        async with await self._session() as session:
            item = LibraryItem(**kwargs)
            session.add(item)
            await session.commit()
            await session.refresh(item)
            return item

    async def find_duplicates(self, user_id: int, title: str, duration: int | None = None) -> List[LibraryItem]:
        async with await self._session() as session:
            q = select(LibraryItem).where(LibraryItem.user_id == user_id)
            # simple title contains
            q = q.where(LibraryItem.title.ilike(f"%{title[:40]}%"))
            if duration:
                q = q.where(LibraryItem.duration.between(duration - 3, duration + 3))
            r = await session.execute(q.limit(5))
            return list(r.scalars().all())

    async def search_library(self, user_id: int, query: str, limit: int = 20) -> List[LibraryItem]:
        async with await self._session() as session:
            r = await session.execute(
                select(LibraryItem).where(
                    LibraryItem.user_id == user_id,
                    LibraryItem.title.ilike(f"%{query}%"),
                ).order_by(LibraryItem.created_at.desc()).limit(limit)
            )
            return list(r.scalars().all())

    # ── Collections ──
    async def create_collection(self, user_id: int, name: str) -> Collection:
        async with await self._session() as session:
            c = Collection(user_id=user_id, name=name)
            session.add(c)
            await session.commit()
            await session.refresh(c)
            return c

    async def list_collections(self, user_id: int) -> List[Collection]:
        async with await self._session() as session:
            r = await session.execute(select(Collection).where(Collection.user_id == user_id).order_by(Collection.created_at.desc()))
            return list(r.scalars().all())

    async def add_to_collection(self, collection_id: int, title: str, url: str | None = None, library_id: int | None = None) -> None:
        async with await self._session() as session:
            session.add(CollectionItem(collection_id=collection_id, title=title, url=url, library_id=library_id))
            await session.commit()

    async def collection_items(self, collection_id: int) -> List[CollectionItem]:
        async with await self._session() as session:
            r = await session.execute(select(CollectionItem).where(CollectionItem.collection_id == collection_id).order_by(CollectionItem.added_at.desc()))
            return list(r.scalars().all())

    # ── Scheduled ──
    async def schedule_download(self, user_id: int, url: str, quality: str, run_at: datetime) -> ScheduledJob:
        async with await self._session() as session:
            job = ScheduledJob(user_id=user_id, url=url, quality=quality, run_at=run_at)
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job

    async def pending_schedules(self, before: datetime) -> List[ScheduledJob]:
        async with await self._session() as session:
            r = await session.execute(
                select(ScheduledJob).where(ScheduledJob.status == "pending", ScheduledJob.run_at <= before)
            )
            return list(r.scalars().all())

    async def set_schedule_status(self, job_id: int, status: str) -> None:
        async with await self._session() as session:
            await session.execute(update(ScheduledJob).where(ScheduledJob.id == job_id).values(status=status))
            await session.commit()

    async def user_schedules(self, user_id: int) -> List[ScheduledJob]:
        async with await self._session() as session:
            r = await session.execute(
                select(ScheduledJob).where(ScheduledJob.user_id == user_id).order_by(ScheduledJob.run_at.desc()).limit(20)
            )
            return list(r.scalars().all())


db = Database()
