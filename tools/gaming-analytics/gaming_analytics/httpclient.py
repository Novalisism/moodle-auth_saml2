"""Small dependency-free HTTP client: on-disk cache, retries, quota counting.

stdlib only on purpose - this has to run on a laptop with nothing installed
but python3, and inside CI, without a requirements.txt fight.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger(__name__)

DEFAULT_UA = (
    "gaming-analytics/0.1 (research tooling; contact: set GA_CONTACT env var)"
)
# Query params never used in a cache key (secrets, or noise).
_SECRET_PARAMS = {"key", "api_key", "apikey", "token", "access_token"}


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} for {url}: {body[:300]}")
        self.status = status
        self.url = url
        self.body = body


@dataclass
class FetchStats:
    requests: int = 0
    cache_hits: int = 0
    retries: int = 0
    errors: int = 0
    quota_units: int = 0
    per_host: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "requests": self.requests,
            "cache_hits": self.cache_hits,
            "retries": self.retries,
            "errors": self.errors,
            "youtube_quota_units": self.quota_units,
            "per_host": dict(self.per_host),
        }


class Http:
    """GET-only JSON/text fetcher with a file cache and polite backoff."""

    def __init__(
        self,
        cache_dir: str,
        ttl_seconds: int = 24 * 3600,
        timeout: int = 30,
        retries: int = 4,
        min_interval: float = 0.25,
        user_agent: Optional[str] = None,
        offline: bool = False,
        stats: Optional[FetchStats] = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.ttl = ttl_seconds
        self.timeout = timeout
        self.retries = retries
        self.min_interval = min_interval
        self.user_agent = user_agent or os.environ.get("GA_USER_AGENT", DEFAULT_UA)
        self.offline = offline
        self.stats = stats or FetchStats()
        self._last_call: Dict[str, float] = {}
        os.makedirs(self.cache_dir, exist_ok=True)

    # ---------------------------------------------------------------- caching
    def _cache_key(self, url: str, params: Optional[Dict[str, Any]]) -> str:
        safe = {k: v for k, v in (params or {}).items() if k.lower() not in _SECRET_PARAMS}
        raw = url + "?" + urllib.parse.urlencode(sorted(safe.items()))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]

    def _cache_path(self, key: str) -> str:
        return os.path.join(self.cache_dir, key + ".json")

    def _read_cache(self, key: str) -> Optional[Dict[str, Any]]:
        path = self._cache_path(key)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                blob = json.load(fh)
        except (OSError, ValueError):
            return None
        if self.ttl >= 0 and time.time() - blob.get("fetched_at", 0) > self.ttl:
            if not self.offline:
                return None
            log.warning("offline: serving stale cache for %s", blob.get("url"))
        return blob

    def _write_cache(self, key: str, url: str, body: str) -> None:
        tmp = self._cache_path(key) + ".tmp"
        payload = {"url": url, "fetched_at": time.time(), "body": body}
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, self._cache_path(key))
        except OSError as exc:  # cache is best effort
            log.debug("cache write failed: %s", exc)

    # --------------------------------------------------------------- fetching
    def _throttle(self, host: str) -> None:
        last = self._last_call.get(host)
        if last is not None:
            wait = self.min_interval - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_call[host] = time.time()

    def get_text(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        quota_cost: int = 0,
        use_cache: bool = True,
    ) -> Tuple[str, bool]:
        """Return (body, from_cache)."""
        key = self._cache_key(url, params)
        if use_cache:
            cached = self._read_cache(key)
            if cached is not None:
                self.stats.cache_hits += 1
                return cached["body"], True
        if self.offline:
            raise HttpError(0, url, "offline mode and no cache entry")

        full = url
        if params:
            full = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        host = urllib.parse.urlparse(full).netloc
        self.stats.per_host[host] = self.stats.per_host.get(host, 0) + 1

        req_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/html;q=0.8, */*;q=0.5",
            "Accept-Encoding": "gzip",
        }
        req_headers.update(headers or {})

        delay = 2.0
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            self._throttle(host)
            try:
                req = urllib.request.Request(full, headers=req_headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    body = raw.decode("utf-8", errors="replace")
                self.stats.requests += 1
                self.stats.quota_units += quota_cost
                if use_cache:
                    self._write_cache(key, full, body)
                return body, False
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                # 4xx other than rate limiting will not get better by retrying.
                if exc.code not in (408, 429) and exc.code < 500:
                    self.stats.errors += 1
                    raise HttpError(exc.code, full, body) from exc
                last_exc = HttpError(exc.code, full, body)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
            if attempt < self.retries:
                self.stats.retries += 1
                log.warning("retry %d/%d for %s (%s)", attempt + 1, self.retries, host, last_exc)
                time.sleep(delay)
                delay *= 2
        self.stats.errors += 1
        raise HttpError(0, full, f"gave up after {self.retries} retries: {last_exc}")

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        quota_cost: int = 0,
        use_cache: bool = True,
    ) -> Any:
        body, _ = self.get_text(url, params, headers, quota_cost, use_cache)
        try:
            return json.loads(body)
        except ValueError as exc:
            raise HttpError(0, url, f"non-JSON response: {body[:200]}") from exc
