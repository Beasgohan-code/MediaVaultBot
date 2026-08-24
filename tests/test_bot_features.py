import pytest
from core.ytdlp import is_supported_url, resolve_format, SITE_CATALOG
from telegram.plugins.url_download import URL_REGEX


def test_supported_urls():
    assert is_supported_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_supported_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
    assert is_supported_url("https://www.instagram.com/reel/C123456789")
    assert is_supported_url("https://www.crunchyroll.com/watch/123456")
    assert not is_supported_url("not_a_url")


def test_url_regex_matching():
    match_yt = URL_REGEX.search("Check this video: https://youtu.be/dQw4w9WgXcQ")
    assert match_yt is not None
    assert "youtu.be" in match_yt.group(0)

    match_sp = URL_REGEX.search("Listen to https://open.spotify.com/track/12345")
    assert match_sp is not None

    match_ig = URL_REGEX.search("See https://www.instagram.com/p/C123456789")
    assert match_ig is not None


def test_resolve_format():
    assert "height<=1080" in resolve_format("1080")
    assert resolve_format("fmt:22") == "22"


def test_site_catalog_entries():
    assert "spotify.com" in SITE_CATALOG
    assert "instagram.com" in SITE_CATALOG
    assert "crunchyroll.com" in SITE_CATALOG


def test_search_backends():
    from core.ytdlp import SEARCH_BACKENDS
    assert "youtube" in SEARCH_BACKENDS
    assert "soundcloud" in SEARCH_BACKENDS
    assert "bilibili" in SEARCH_BACKENDS


def test_support_url_config():
    from config import SUPPORT_URL
    assert isinstance(SUPPORT_URL, str)


def test_thumbnail_manager():
    from telegram.plugins.thumbnails import get_user_thumb
    assert get_user_thumb(99999999) is None
