"""
OSINT / origin-tracing search layer.

`SourceSearchProvider` is the abstraction. `DemoSourceProvider` returns a
clearly-labeled, deterministic set of mock candidate sources so the full
investigation pipeline (including source ranking and propagation graphing)
can be demoed offline. `BraveSourceProvider` is a real-mode implementation
stub that performs genuine web search via the Brave Search API when
BRAVE_API_KEY is configured -- it explicitly does NOT claim to be a true
reverse-image-search API (none is wired by default; see README).

Per platform rules: never bypass CAPTCHA/login/2FA/private-account/paywall
restrictions. If a source is inaccessible, record it as such and move on.
"""
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Generic stand-in image used ONLY when no real preview/thumbnail could be
# located or downloaded for a candidate source (real-mode) or as the visual
# for synthetic demo candidates (DEMO_MODE). This is presentation polish,
# not evidence: it must never be treated as a pixel-verified match, which is
# why every CandidateSource that uses it also sets thumbnail_is_placeholder
# = True. Swap this out (or make it configurable) once real scraped/dataset
# thumbnails are wired in -- see settings.PLACEHOLDER_THUMBNAIL_URL.
PLACEHOLDER_THUMBNAIL_URL = (
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:"
    "ANd9GcQSSHAvfAB_fuF_2-RjSWFB7GmX7suUf-CcBko8gyIVxA&s=10"
)


@dataclass
class CandidateSource:
    url: str
    title: Optional[str]
    platform: Optional[str]
    domain: Optional[str]
    publication_date: Optional[str]  # ISO date string or "unknown"
    accessible: bool = True
    inaccessible_reason: Optional[str] = None
    is_demo: bool = True
    # a synthetic/estimated phash for demo candidates, so perceptual
    # comparison against the uploaded media produces a real (if fake) score
    candidate_phash: Optional[str] = None
    thumbnail_url: Optional[str] = None
    thumbnail_is_placeholder: bool = False


class SourceSearchProvider(ABC):
    @abstractmethod
    def search(self, queries: List[str], media_phash: str) -> List[CandidateSource]:
        ...

    @property
    @abstractmethod
    def reverse_image_search_available(self) -> bool:
        ...


class DemoSourceProvider(SourceSearchProvider):
    """Deterministic, clearly-labeled mock OSINT results for offline demo."""

    reverse_image_search_available = False

    _TEMPLATE = [
        {"platform": "News Wire", "domain": "globalnewswire.example", "days_ago": 6, "dist": 2},
        {"platform": "X", "domain": "x.com", "days_ago": 4, "dist": 3},
        {"platform": "Facebook", "domain": "facebook.com", "days_ago": 3, "dist": 6},
        {"platform": "Instagram", "domain": "instagram.com", "days_ago": 2, "dist": 8},
        {"platform": "News Article", "domain": "dailychronicle.example", "days_ago": 0, "dist": 5},
    ]

    def search(self, queries: List[str], media_phash: str) -> List[CandidateSource]:
        now = datetime.now(timezone.utc)
        results = []
        base_query = queries[0] if queries else "media"
        for i, tpl in enumerate(self._TEMPLATE):
            pub_date = (now - timedelta(days=tpl["days_ago"] + 6)).date().isoformat()
            slug = base_query.lower().replace(" ", "-")[:40] or "media-item"
            results.append(CandidateSource(
                url=f"https://{tpl['domain']}/demo/{slug}-{i}",
                title=f"{tpl['platform']} occurrence of similar media",
                platform=tpl["platform"],
                domain=tpl["domain"],
                publication_date=pub_date,
                accessible=True,
                is_demo=True,
                candidate_phash=_perturb_hash(media_phash, tpl["dist"]),
                thumbnail_url=PLACEHOLDER_THUMBNAIL_URL,
                thumbnail_is_placeholder=True,
            ))
        return results


class BraveSourceProvider(SourceSearchProvider):
    """
    Real-mode provider using Brave Search's Web Search API for open-web
    similarity search. This is NOT a true reverse-image-search API (Brave
    does not offer one) -- it searches on text queries (filenames, OCR text,
    distinctive phrases) that Claude/OpenClaw derives from the media. The
    platform is explicit about this distinction in the UI/report.
    """
    reverse_image_search_available = False

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, queries: List[str], media_phash: str) -> List[CandidateSource]:
        results: List[CandidateSource] = []
        headers = {"Accept": "application/json", "X-Subscription-Token": self.api_key}
        for q in queries[:5]:
            try:
                resp = httpx.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": q, "count": 5},
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("web", {}).get("results", []):
                    results.append(CandidateSource(
                        url=item.get("url"),
                        title=item.get("title"),
                        platform=_platform_from_domain(item.get("url", "")),
                        domain=_domain_of(item.get("url", "")),
                        publication_date=item.get("age") or "unknown",
                        accessible=True,
                        is_demo=False,
                        candidate_phash=None,  # unknown until fetched/compared
                    ))
            except Exception:
                continue
        return results


class DDGSourceProvider(SourceSearchProvider):
    """
    Free, keyless real-mode provider using DuckDuckGo (via the `ddgs`
    library) for open-web text + image search. Like BraveSourceProvider,
    this is NOT true reverse-image search -- DDG has no image-upload API,
    so it searches on text queries derived from the upload (filename,
    investigation metadata). The platform is explicit about that
    distinction (see orchestrator._stage_origin_search's
    reverse_image_search_available log line).

    Where this differs from BraveSourceProvider: for each image hit, the
    actual thumbnail is downloaded and a REAL perceptual hash is computed
    from real pixels (imagehash.phash), so similarity scoring against the
    uploaded asset is genuine -- not a synthetic phash like
    DemoSourceProvider produces. No API key, no per-request cost, no paid
    quota; this is the default real-mode provider whenever BRAVE_API_KEY
    is not set.
    """
    reverse_image_search_available = False

    def search(self, queries: List[str], media_phash: str) -> List[CandidateSource]:
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS  # older package name
        except ImportError:
            # ddgs isn't installed -- fail closed (empty results), not
            # silently back to demo data.
            return []

        results: List[CandidateSource] = []
        try:
            with DDGS() as ddgs:
                for q in queries[:3]:
                    try:
                        for hit in ddgs.images(q, max_results=6):
                            img_url = hit.get("image")
                            page_url = hit.get("url") or img_url
                            results.append(CandidateSource(
                                url=page_url,
                                title=hit.get("title"),
                                platform=_platform_from_domain(page_url or ""),
                                domain=_domain_of(page_url or ""),
                                publication_date="unknown",
                                accessible=True,
                                is_demo=False,
                                candidate_phash=_download_and_hash(img_url),
                            ))
                    except Exception:
                        pass
                    try:
                        for hit in ddgs.text(q, max_results=5):
                            href = hit.get("href")
                            results.append(CandidateSource(
                                url=href,
                                title=hit.get("title"),
                                platform=_platform_from_domain(href or ""),
                                domain=_domain_of(href or ""),
                                publication_date="unknown",
                                accessible=True,
                                is_demo=False,
                                candidate_phash=None,
                            ))
                    except Exception:
                        pass
        except Exception:
            return results
        return results


class OpenverseSourceProvider(SourceSearchProvider):
    """
    Free, keyless real-mode provider using the Openverse API
    (https://api.openverse.org/v1/images/) -- a public search engine over
    ~800M openly-licensed images aggregated from Wikimedia Commons, Flickr
    (CC-licensed subset), museums, etc.

    Like DDGSourceProvider, this is NOT true reverse-image search --
    Openverse has no image-upload endpoint, so it searches on text queries
    derived from the upload. Where it earns its place alongside DDG:
      - Every result carries REAL, structured provenance the search
        engines above don't: a `license`, `creator`/`creator_url`, and a
        `foreign_landing_url` (the original source page) straight from the
        API response -- not inferred from a domain name.
      - No API key or account is required for basic use (anonymous
        requests are allowed). Openverse *does* apply IP-based throttling
        (see response rate-limit headers) and recommends registering a
        free OPENVERSE_CLIENT_ID/SECRET for sustained/heavy use, but there
        is no hard published cap on casual, per-investigation query volume
        the way there is for e.g. Google Vision's paid tier -- so this is
        treated as "no meaningful rate limit for this app's traffic shape"
        rather than "provably zero limit".
      - Real thumbnail_url per hit (Openverse serves its own thumbnail
        proxy), so this doesn't need the placeholder-thumbnail wrapper the
        way demo/undated candidates do.

    Always merged in via get_source_provider() (see _CompositeProvider)
    rather than gated behind a settings flag -- it's free, keyless, and
    additive to whatever primary provider is configured.
    """
    reverse_image_search_available = False

    BASE_URL = "https://api.openverse.org/v1/images/"

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        # Anonymous by default. Passing a free client id/secret (register
        # at api.openverse.org) raises the rate ceiling but is not
        # required -- left optional so this provider works out of the box.
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None

    def _get_token(self) -> Optional[str]:
        if not (self.client_id and self.client_secret):
            return None
        if self._token:
            return self._token
        try:
            resp = httpx.post(
                "https://api.openverse.org/v1/auth_tokens/token/",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=8,
            )
            resp.raise_for_status()
            self._token = resp.json().get("access_token")
        except Exception:
            self._token = None
        return self._token

    def search(self, queries: List[str], media_phash: str) -> List[CandidateSource]:
        results: List[CandidateSource] = []
        headers = {}
        token = self._get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        for q in queries[:3]:
            try:
                resp = httpx.get(
                    self.BASE_URL,
                    params={"q": q, "page_size": 8},
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("results", []):
                    landing_url = item.get("foreign_landing_url") or item.get("url")
                    img_url = item.get("url")
                    if not landing_url:
                        continue
                    results.append(CandidateSource(
                        url=landing_url,
                        title=item.get("title"),
                        platform=item.get("source") or _platform_from_domain(landing_url),
                        domain=_domain_of(landing_url),
                        # Openverse's search index doesn't expose an
                        # upload/publication date -- Wayback enrichment
                        # (below) fills this in on a best-effort basis.
                        publication_date="unknown",
                        accessible=True,
                        is_demo=False,
                        candidate_phash=_download_and_hash(img_url) if img_url else None,
                        thumbnail_url=item.get("thumbnail") or img_url,
                    ))
            except Exception:
                continue
        return results


class _CompositeProvider(SourceSearchProvider):
    """Runs several providers concurrently and merges their candidates,
    deduped by URL (first occurrence wins -- providers earlier in the list
    take priority when the same URL is found twice). Used so a free,
    keyless, always-on source (OpenverseSourceProvider) adds coverage on
    top of whichever primary provider is configured, instead of the two
    being mutually exclusive."""

    def __init__(self, providers: List[SourceSearchProvider]):
        self.providers = providers

    @property
    def reverse_image_search_available(self) -> bool:
        return any(p.reverse_image_search_available for p in self.providers)

    def search(self, queries: List[str], media_phash: str) -> List[CandidateSource]:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=len(self.providers)) as pool:
            futures = [pool.submit(p.search, queries, media_phash) for p in self.providers]
            per_provider = []
            for f in futures:
                try:
                    per_provider.append(f.result())
                except Exception:
                    per_provider.append([])

        seen_urls = set()
        merged: List[CandidateSource] = []
        for candidates in per_provider:
            for c in candidates:
                if not c.url or c.url in seen_urls:
                    continue
                seen_urls.add(c.url)
                merged.append(c)
        return merged


class MrisaSourceProvider(SourceSearchProvider):
    """
    Real reverse-image-search provider using a self-hosted MRISA instance
    (https://github.com/vivithemage/mrisa) -- a small Flask API that wraps
    Google's search-by-image endpoint. Unlike Brave/DDG above, this
    actually searches BY IMAGE, not by derived text queries, so it's a
    true reverse-image search.

    Free, self-hosted, no API key -- but note MRISA works by scraping
    Google's public search-by-image endpoint, which is not an officially
    sanctioned API. It can break or get rate-limited without notice. Run
    it locally (default http://127.0.0.1:5000) per its README.

    Requires the uploaded media to be reachable at a public/local URL that
    MRISA's backend process can fetch -- this is `image_url`, built from
    OPENCLAW_BACKEND_BASE_URL + the investigation's /original endpoint.
    """
    reverse_image_search_available = True

    def __init__(self, mrisa_url: str, image_url: str):
        self.mrisa_url = mrisa_url.rstrip("/")
        self.image_url = image_url

    def search(self, queries: List[str], media_phash: str) -> List[CandidateSource]:
        results: List[CandidateSource] = []
        try:
            resp = httpx.post(
                f"{self.mrisa_url}/search",
                json={"image_url": self.image_url, "resized_images": False},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return results

        # MRISA returns a list of match dicts with Google's raw keys:
        # ru=resource_url (the page it was found on), ou=original_url of
        # the image itself, oh/ow=original height/width, pt=page title,
        # rh=resource_host.
        for item in data if isinstance(data, list) else data.get("results", []):
            page_url = item.get("ru") or item.get("ou")
            img_url = item.get("ou")
            if not page_url:
                continue
            results.append(CandidateSource(
                url=page_url,
                title=item.get("pt"),
                platform=_platform_from_domain(page_url),
                domain=item.get("rh") or _domain_of(page_url),
                publication_date="unknown",  # MRISA/Google image search doesn't return dates
                accessible=True,
                is_demo=False,
                candidate_phash=_download_and_hash(img_url) if img_url else None,
            ))
        return results


class PicImageSearchProvider(SourceSearchProvider):
    """
    Real reverse-image-search provider using the `PicImageSearch` library
    (https://github.com/kitUIN/PicImageSearch) -- a maintained aggregator
    that wraps several engines' real search-by-image endpoints (Google,
    Google Lens, Yandex, Bing, TinEye, SauceNAO, ...) behind one interface.

    Why this replaces MrisaSourceProvider as the default true-reverse-image
    provider:
      - No second long-running process to keep alive -- it's a plain pip
        dependency called in-process, unlike MRISA's separate Flask server.
      - Queries multiple engines per search instead of exactly one, so a
        single engine getting blocked/rate-limited (the documented failure
        mode of scraping Google directly) degrades the result set instead
        of zeroing it out.
      - TinEye in particular returns a genuine crawl_date per match, which
        is exactly the "earliest occurrence" signal this platform is
        chasing -- Google/MRISA never return dates at all.

    Same category of caveat as MRISA still applies to the Google/Yandex/Bing
    legs specifically (unofficial, can break without notice); TinEye has a
    real supported web frontend PicImageSearch scrapes more conservatively.
    This provider treats every engine as best-effort: one engine failing
    never aborts the others (see `_run_engine`).

    Prefers reading the media directly off local disk (`image_path`) over
    fetching it via a callback URL (`image_url`) -- avoids the class of
    failure where the search backend can't reach the app's own HTTP server
    (network/container boundary, auth, etc.). Falls back to `image_url` if
    no local path is available (e.g. a future non-local deployment).
    """
    reverse_image_search_available = True

    #: Engines to try, in order. Each name maps to a PicImageSearch sync
    #: engine class below. Kept as an explicit allowlist (rather than "all
    #: engines PicImageSearch supports") because several of its engines
    #: (e.g. SauceNAO, e-hentai) are tuned for anime/illustration search and
    #: aren't a fit for general photo/video provenance work.
    DEFAULT_ENGINES = ("google", "yandex", "tineye")

    def __init__(
        self,
        image_path: Optional[str] = None,
        image_url: Optional[str] = None,
        engines: Optional[List[str]] = None,
    ):
        if not image_path and not image_url:
            raise ValueError("PicImageSearchProvider requires image_path or image_url")
        self.image_path = image_path
        self.image_url = image_url
        self.engines = list(engines) if engines else list(self.DEFAULT_ENGINES)

    def search(self, queries: List[str], media_phash: str) -> List[CandidateSource]:
        # Imported lazily so the rest of the app doesn't hard-depend on
        # PicImageSearch being installed when it's never configured/used
        # (mirrors how imagehash/PIL are imported lazily in
        # `_download_and_hash` below).
        #
        # IMPORTANT: we deliberately do NOT use `PicImageSearch.sync`
        # (its `syncify()` monkeypatch) here. That wrapper does
        # `asyncio.get_event_loop()` and attaches/reuses whatever event
        # loop is bound to the *current thread*. This code runs inside a
        # FastAPI BackgroundTasks callback, which executes on a pooled,
        # reused worker thread (via anyio.to_thread.run_sync) -- not a
        # fresh thread/process per call like a standalone script. If a
        # loop attached to that thread from an earlier call is later
        # closed/left in a bad state, every engine call here silently
        # raises "Event loop is closed" (or similar), gets swallowed by
        # the try/except below, and this whole search pass returns 0
        # candidates in milliseconds while looking like it "worked".
        # Calling the real async engines ourselves via `asyncio.run()`
        # sidesteps that entirely: asyncio.run() always creates a brand
        # new event loop and guarantees it's closed afterward. This is
        # safe to do here specifically because we're in a background
        # thread, not inside uvicorn's own event loop (never call
        # asyncio.run() from inside an async route handler).
        try:
            from PicImageSearch import Google, Tineye, Yandex
        except ImportError:
            logger.warning(
                "PICIMAGESEARCH_ENABLED is set but the `PicImageSearch` "
                "package isn't installed (pip install PicImageSearch); "
                "returning no candidates for this pass."
            )
            return []

        engine_classes = {"google": Google, "yandex": Yandex, "tineye": Tineye}
        wanted = [(name, engine_classes[name]) for name in self.engines if name in engine_classes]
        if not wanted:
            return []

        import asyncio

        async def _run_all():
            return await asyncio.gather(
                *(self._run_engine_async(name, cls) for name, cls in wanted)
            )

        per_engine_results = asyncio.run(_run_all())
        results: List[CandidateSource] = []
        for r in per_engine_results:
            results.extend(r)
        return results

    async def _run_engine_async(self, name: str, engine_cls) -> List[CandidateSource]:
        """Runs one async engine end-to-end; any failure is caught and
        logged so one bad/blocked engine never takes down the whole
        search pass. Logged at WARNING (not INFO) so real failures are
        visible with uvicorn's default log level instead of silently
        vanishing."""
        try:
            engine = engine_cls()
            kwargs = {"file": self.image_path} if self.image_path else {"url": self.image_url}
            resp = await engine.search(**kwargs)
        except Exception as exc:
            logger.warning("PicImageSearch engine '%s' failed, skipping: %s: %s", name, type(exc).__name__, exc)
            return []

        out: List[CandidateSource] = []
        for item in getattr(resp, "raw", []) or []:
            url = getattr(item, "url", None)
            if not url:
                continue
            pub_date = self._extract_date(item)
            domain = getattr(item, "domain", None) or getattr(item, "source", None) or _domain_of(url)
            thumb = getattr(item, "thumbnail", None)
            out.append(CandidateSource(
                url=url,
                title=getattr(item, "title", None),
                platform=_platform_from_domain(url) if not domain else _platform_from_domain(f"//{domain}"),
                domain=domain,
                publication_date=pub_date,
                accessible=True,
                is_demo=False,
                candidate_phash=_hash_from_thumbnail(thumb),
            ))
        return out

    @staticmethod
    def _extract_date(item) -> str:
        # Only TineyeItem currently exposes a real crawl date; every other
        # engine here returns "unknown" rather than a guessed value.
        crawl_date = getattr(item, "crawl_date", None)
        return crawl_date or "unknown"


class GoogleVisionSourceProvider(SourceSearchProvider):
    """
    Real reverse-image-search provider using the OFFICIAL, supported Google
    Cloud Vision API's WEB_DETECTION feature (cloud.google.com/vision/docs/
    detecting-web) -- this is the same underlying technology behind Google
    Images' own "Find image source" button. Unlike PicImageSearchProvider's
    Google/Yandex/TinEye legs, this is a documented REST API called with an
    API key, not a scrape of a search-results HTML page -- so it doesn't
    silently return empty/garbage results when Google decides a request
    looks like a bot.

    Response gives three tiers of match, all surfaced here as candidates:
      - pagesWithMatchingImages: pages where this exact image (or a
        near-duplicate) was found -- the strongest "where did this appear"
        signal.
      - visuallySimilarImages: same subject, not necessarily the same
        photo -- used only as a fallback when nothing stronger is found.

    Costs $0 for the first 1000 requests/month, $3.50/1000 after
    (cloud.google.com/vision/pricing) -- effectively free for personal/
    investigative use. No crawl/publication dates are returned by this API
    (Google doesn't expose that); see `wayback_earliest_date()` below,
    used via `_WaybackEnrichingProvider` to backfill an approximate date
    for every candidate this returns.
    """
    reverse_image_search_available = True
    API_URL = "https://vision.googleapis.com/v1/images:annotate"

    def __init__(self, api_key: str, image_path: Optional[str] = None, image_url: Optional[str] = None):
        if not image_path and not image_url:
            raise ValueError("GoogleVisionSourceProvider requires image_path or image_url")
        self.api_key = api_key
        self.image_path = image_path
        self.image_url = image_url

    def _build_image_payload(self) -> dict:
        import base64
        if self.image_path:
            with open(self.image_path, "rb") as f:
                content = base64.b64encode(f.read()).decode("ascii")
            return {"content": content}
        # Vision API can fetch a public/reachable URL directly instead of
        # inline bytes -- used only when no local path is available.
        return {"source": {"imageUri": self.image_url}}

    def search(self, queries: List[str], media_phash: str) -> List[CandidateSource]:
        payload = {
            "requests": [{
                "image": self._build_image_payload(),
                "features": [{"type": "WEB_DETECTION", "maxResults": 30}],
            }]
        }
        try:
            resp = httpx.post(self.API_URL, params={"key": self.api_key}, json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Google Vision Web Detection request failed: %s: %s", type(exc).__name__, exc)
            return []

        response0 = (data.get("responses") or [{}])[0]
        if "error" in response0:
            logger.warning("Google Vision Web Detection API error: %s", response0["error"])
            return []
        web = response0.get("webDetection") or {}

        results: List[CandidateSource] = []

        def _add(pages):
            for p in pages or []:
                url = p.get("url")
                if not url:
                    continue
                sub = (p.get("fullMatchingImages") or p.get("partialMatchingImages") or [])
                thumb = sub[0].get("url") if sub else None
                results.append(CandidateSource(
                    url=url,
                    title=p.get("pageTitle"),
                    platform=_platform_from_domain(url),
                    domain=_domain_of(url),
                    publication_date="unknown",  # backfilled by _WaybackEnrichingProvider
                    accessible=True,
                    is_demo=False,
                    candidate_phash=_download_and_hash(thumb) if thumb else None,
                ))

        _add(web.get("pagesWithMatchingImages"))
        # Visually-similar (not confirmed same-image) results are a much
        # weaker signal for "where did THIS image first appear" -- only
        # include them if we found nothing stronger, so they don't drown
        # out real matches with lookalikes.
        if not results:
            for img in (web.get("visuallySimilarImages") or [])[:10]:
                url = img.get("url")
                if not url:
                    continue
                results.append(CandidateSource(
                    url=url, title=None, platform=_platform_from_domain(url),
                    domain=_domain_of(url), publication_date="unknown",
                    accessible=True, is_demo=False,
                    candidate_phash=_download_and_hash(url),
                ))
        return results


def wayback_earliest_date(url: str, timeout: float = 6.0) -> Optional[str]:
    """
    Free, keyless lookup against the Internet Archive's Wayback Machine CDX
    API for the earliest known capture of `url` -- used to approximate a
    "first seen" date for candidates from providers that don't return real
    publication/crawl dates (Google Vision, Yandex/Google via
    PicImageSearch). Best-effort: any failure/empty result returns None,
    it never raises. Returns an ISO date string (YYYY-MM-DD) or None.

    Caveat: this is an *approximation*, not a citation -- the earliest
    archive.org crawl of a URL isn't necessarily when the image was first
    posted there, just the earliest evidence available. It's stronger for
    older/static pages than fast-moving social media posts, which
    archive.org may crawl late or not at all.
    """
    try:
        resp = httpx.get(
            "https://web.archive.org/cdx/search/cdx",
            params={"url": url, "output": "json", "limit": 1, "sort": "ascending", "fl": "timestamp"},
            timeout=timeout,
        )
        resp.raise_for_status()
        rows = resp.json()
        if len(rows) < 2:  # first row is the header
            return None
        ts = rows[1][0]  # yyyyMMddhhmmss
        return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
    except Exception:
        return None


def _enrich_with_wayback_dates(candidates: List[CandidateSource]) -> List[CandidateSource]:
    """Backfills publication_date for candidates that don't have a real
    one, using wayback_earliest_date(), run concurrently and capped to
    settings.WAYBACK_ENRICH_MAX_CANDIDATES to bound latency. Only touches
    candidates whose date is missing/"unknown" -- never overwrites a real
    date (e.g. TinEye's genuine crawl_date via PicImageSearch)."""
    if not settings.WAYBACK_ENRICH_DATES:
        return candidates
    needs_date = [c for c in candidates if not c.publication_date or c.publication_date == "unknown"]
    if not needs_date:
        return candidates
    needs_date = needs_date[: settings.WAYBACK_ENRICH_MAX_CANDIDATES]

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        dates = list(pool.map(lambda c: wayback_earliest_date(c.url), needs_date))
    for c, d in zip(needs_date, dates):
        if d:
            c.publication_date = d
    return candidates


class _WaybackEnrichingProvider(SourceSearchProvider):
    """Thin wrapper: runs any provider's search() then backfills missing
    dates via Wayback CDX. Kept as a wrapper (rather than baked into each
    provider) so the enrichment logic and its settings live in one place."""

    def __init__(self, inner: SourceSearchProvider):
        self.inner = inner

    @property
    def reverse_image_search_available(self) -> bool:
        return self.inner.reverse_image_search_available

    def search(self, queries: List[str], media_phash: str) -> List[CandidateSource]:
        return _enrich_with_wayback_dates(self.inner.search(queries, media_phash))


class _PlaceholderThumbnailFillingProvider(SourceSearchProvider):
    """Thin wrapper (same pattern as _WaybackEnrichingProvider): runs any
    provider's search() then fills in PLACEHOLDER_THUMBNAIL_URL for any
    candidate that came back with no real thumbnail (real-mode providers
    only set thumbnail_url when they actually resolved/downloaded a real
    image -- see the individual provider docstrings above).

    This exists purely so demo videos/screenshots don't show broken-image
    boxes while the real scraped dataset (~20 days out per plan) isn't
    wired in yet. It NEVER touches a candidate that already has a real
    thumbnail, and it always marks the ones it does touch with
    thumbnail_is_placeholder=True so report.py / confidence scoring can
    keep treating them as "no verified visual preview" rather than as
    corroborating evidence. Remove this wrapper (or make it a no-op via
    settings) once every active provider reliably returns real thumbnails.
    """

    def __init__(self, inner: SourceSearchProvider):
        self.inner = inner

    @property
    def reverse_image_search_available(self) -> bool:
        return self.inner.reverse_image_search_available

    def search(self, queries: List[str], media_phash: str) -> List[CandidateSource]:
        candidates = self.inner.search(queries, media_phash)
        for c in candidates:
            if not c.thumbnail_url:
                c.thumbnail_url = PLACEHOLDER_THUMBNAIL_URL
                c.thumbnail_is_placeholder = True
        return candidates


def _openverse_provider() -> OpenverseSourceProvider:
    return OpenverseSourceProvider(
        client_id=settings.OPENVERSE_CLIENT_ID or None,
        client_secret=settings.OPENVERSE_CLIENT_SECRET or None,
    )


def get_source_provider(
    image_url: Optional[str] = None, image_path: Optional[str] = None
) -> SourceSearchProvider:
    if settings.DEMO_MODE:
        return DemoSourceProvider()

    # Pick the primary provider first (unchanged priority order)...
    if settings.GOOGLE_VISION_API_KEY and (image_path or image_url):
        primary = GoogleVisionSourceProvider(settings.GOOGLE_VISION_API_KEY, image_path=image_path, image_url=image_url)
    elif settings.PICIMAGESEARCH_ENABLED and (image_path or image_url):
        engines = [e.strip() for e in settings.PICIMAGESEARCH_ENGINES.split(",") if e.strip()]
        primary = PicImageSearchProvider(image_path=image_path, image_url=image_url, engines=engines)
    elif settings.MRISA_URL and image_url:
        primary = MrisaSourceProvider(settings.MRISA_URL, image_url)
    elif settings.BRAVE_API_KEY:
        primary = BraveSourceProvider(settings.BRAVE_API_KEY)
    else:
        primary = DDGSourceProvider()

    # ...then always merge in Openverse on top of it. It's free, keyless,
    # and additive (real license/creator/landing-page metadata that the
    # other providers don't return), so there's no reason to gate it
    # behind "only when nothing else is configured" the way DDG is.
    base = _CompositeProvider([primary, _openverse_provider()])
    return _PlaceholderThumbnailFillingProvider(_WaybackEnrichingProvider(base))


def _download_and_hash(image_url: Optional[str]) -> Optional[str]:
    """Downloads a candidate image and computes a REAL perceptual hash from
    its actual pixels -- used only by real-mode providers (never by
    DemoSourceProvider, which uses _perturb_hash to fabricate one)."""
    if not image_url:
        return None
    try:
        import imagehash
        from io import BytesIO
        from PIL import Image
        resp = httpx.get(image_url, timeout=8, follow_redirects=True)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        return str(imagehash.phash(img))
    except Exception:
        return None


def _hash_from_thumbnail(thumbnail: Optional[str]) -> Optional[str]:
    """Computes a REAL perceptual hash from a PicImageSearch item's
    thumbnail -- which may be a plain image URL (Yandex/TinEye) or a
    base64-encoded data string (Google). Handles both; used only by
    PicImageSearchProvider."""
    if not thumbnail:
        return None
    if thumbnail.startswith("http://") or thumbnail.startswith("https://"):
        return _download_and_hash(thumbnail)
    try:
        import base64
        import imagehash
        from io import BytesIO
        from PIL import Image
        raw = thumbnail.split(",", 1)[-1]  # strip a "data:image/...;base64," prefix if present
        img = Image.open(BytesIO(base64.b64decode(raw))).convert("RGB")
        return str(imagehash.phash(img))
    except Exception:
        return None


def _domain_of(url: str) -> str:
    try:
        return url.split("//", 1)[-1].split("/", 1)[0]
    except Exception:
        return "unknown"


def _platform_from_domain(url: str) -> str:
    domain = _domain_of(url)
    mapping = {
        "x.com": "X", "twitter.com": "X",
        "facebook.com": "Facebook", "instagram.com": "Instagram",
        "reddit.com": "Reddit", "youtube.com": "YouTube",
    }
    for key, val in mapping.items():
        if key in domain:
            return val
    return "Web"


def _perturb_hash(hash_hex: str, target_distance: int) -> str:
    """Flips `target_distance` bits of a hex hash string -- used only to
    generate believable-but-fake candidate phashes for DEMO_MODE."""
    try:
        bits = bin(int(hash_hex, 16))[2:].zfill(len(hash_hex) * 4)
    except ValueError:
        return hash_hex
    bits = list(bits)
    rng = random.Random(hash_hex)
    positions = rng.sample(range(len(bits)), min(target_distance, len(bits)))
    for p in positions:
        bits[p] = "1" if bits[p] == "0" else "0"
    new_val = int("".join(bits), 2)
    return format(new_val, f"0{len(hash_hex)}x")
