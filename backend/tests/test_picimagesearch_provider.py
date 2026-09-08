"""
Tests for app.services.source_search.PicImageSearchProvider.

These tests verify:
  - engine results are correctly mapped into CandidateSource objects
  - one engine raising/failing never aborts the others (best-effort per engine)
  - get_source_provider() picks PicImageSearchProvider first when
    PICIMAGESEARCH_ENABLED is set, ahead of MRISA/Brave/DDG
  - it prefers a local image_path over image_url when both are available

No real network calls or PicImageSearch engines are used: the engine
classes are monkeypatched with fakes.

Run with:
    DATA_DIR=/tmp/mf-test-data DEMO_MODE=true pytest -q tests/test_picimagesearch_provider.py
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATA_DIR", "/tmp/mf-test-data")
os.environ.setdefault("DEMO_MODE", "true")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.config import settings
from app.services import source_search


class FakeGoogleItem:
    def __init__(self, url, title, thumbnail=None):
        self.url = url
        self.title = title
        self.thumbnail = thumbnail


class FakeTineyeItem:
    def __init__(self, url, domain, crawl_date):
        self.url = url
        self.domain = domain
        self.crawl_date = crawl_date


def _fake_engine(items):
    """Returns a fake PicImageSearch sync engine class whose .search()
    returns an object with a .raw list, matching the real response shape."""

    class _Engine:
        def __init__(self, *a, **kw):
            pass

        def search(self, **kwargs):
            return SimpleNamespace(raw=items)

    return _Engine


def _failing_engine(exc):
    class _Engine:
        def __init__(self, *a, **kw):
            pass

        def search(self, **kwargs):
            raise exc

    return _Engine


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "PICIMAGESEARCH_ENABLED", False)
    monkeypatch.setattr(settings, "MRISA_URL", "")
    monkeypatch.setattr(settings, "BRAVE_API_KEY", "")
    yield


def test_maps_google_and_tineye_items_to_candidate_sources():
    provider = source_search.PicImageSearchProvider(image_path="/tmp/fake.jpg", engines=["google", "tineye"])

    fake_google = _fake_engine([FakeGoogleItem("https://example.com/post-1", "A post")])
    fake_tineye = _fake_engine([FakeTineyeItem("https://news.example/post-2", "news.example", "2020-01-01")])

    with patch("PicImageSearch.sync.Google", fake_google), \
         patch("PicImageSearch.sync.Tineye", fake_tineye):
        results = provider.search(["query"], media_phash="abcd1234")

    urls = {r.url for r in results}
    assert urls == {"https://example.com/post-1", "https://news.example/post-2"}

    tineye_result = next(r for r in results if r.url == "https://news.example/post-2")
    assert tineye_result.publication_date == "2020-01-01"
    assert tineye_result.is_demo is False
    assert tineye_result.accessible is True

    google_result = next(r for r in results if r.url == "https://example.com/post-1")
    # Google items never carry a real date in this pipeline.
    assert google_result.publication_date == "unknown"


def test_one_engine_failing_does_not_abort_others():
    provider = source_search.PicImageSearchProvider(image_path="/tmp/fake.jpg", engines=["google", "tineye"])

    broken_google = _failing_engine(RuntimeError("blocked / CAPTCHA"))
    fake_tineye = _fake_engine([FakeTineyeItem("https://news.example/post-3", "news.example", "2021-06-01")])

    with patch("PicImageSearch.sync.Google", broken_google), \
         patch("PicImageSearch.sync.Tineye", fake_tineye):
        results = provider.search(["query"], media_phash="abcd1234")

    assert len(results) == 1
    assert results[0].url == "https://news.example/post-3"


def test_requires_path_or_url():
    with pytest.raises(ValueError):
        source_search.PicImageSearchProvider()


def test_get_source_provider_prefers_picimagesearch_over_mrisa(monkeypatch):
    monkeypatch.setattr(settings, "PICIMAGESEARCH_ENABLED", True)
    monkeypatch.setattr(settings, "PICIMAGESEARCH_ENGINES", "google,yandex,tineye")
    monkeypatch.setattr(settings, "MRISA_URL", "http://127.0.0.1:5000")

    provider = source_search.get_source_provider(
        image_url="http://127.0.0.1:8000/api/investigations/inv1/original",
        image_path="/tmp/data/uploads/inv1.jpg",
    )

    assert isinstance(provider, source_search.PicImageSearchProvider)
    # Local path is preferred over the callback URL when both are given.
    assert provider.image_path == "/tmp/data/uploads/inv1.jpg"
    assert provider.engines == ["google", "yandex", "tineye"]


def test_get_source_provider_falls_back_to_mrisa_when_picimagesearch_disabled(monkeypatch):
    monkeypatch.setattr(settings, "PICIMAGESEARCH_ENABLED", False)
    monkeypatch.setattr(settings, "MRISA_URL", "http://127.0.0.1:5000")

    provider = source_search.get_source_provider(
        image_url="http://127.0.0.1:8000/api/investigations/inv1/original",
    )

    assert isinstance(provider, source_search.MrisaSourceProvider)
