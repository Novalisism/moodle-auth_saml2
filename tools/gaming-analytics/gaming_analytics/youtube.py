"""YouTube Data API v3 collector.

Quota costs (units, default daily allowance is 10,000):
    channels.list  1      videos.list 1      search.list 100
`Http` tracks the running total so a collect run can be budgeted before it is
started - see README "Quota budget".
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, Iterable, List, Optional

from .httpclient import Http, HttpError

log = logging.getLogger(__name__)

API = "https://www.googleapis.com/youtube/v3"
COST_CHANNELS = 1
COST_VIDEOS = 1
COST_SEARCH = 100


def _chunks(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YouTube:
    def __init__(self, http: Http, api_key: str):
        if not api_key:
            raise ValueError(
                "YouTube API key missing. Create one at "
                "https://console.cloud.google.com/apis/credentials (enable "
                "'YouTube Data API v3') and export YOUTUBE_API_KEY."
            )
        self.http = http
        self.key = api_key

    def _get(self, path: str, params: Dict[str, Any], cost: int) -> Dict[str, Any]:
        params = dict(params)
        params["key"] = self.key
        try:
            return self.http.get_json(f"{API}/{path}", params, quota_cost=cost)
        except HttpError as exc:
            if exc.status == 403 and "quotaExceeded" in exc.body:
                raise RuntimeError(
                    "YouTube API daily quota exhausted. Wait for the midnight "
                    "Pacific reset, use a second project's key, or rerun with "
                    "--no-search (search.list is 100x the cost of everything else)."
                ) from exc
            raise

    # ----------------------------------------------------------- channel data
    def channel_by_handle(self, handle: str) -> Optional[Dict[str, Any]]:
        handle = handle if handle.startswith("@") else "@" + handle
        data = self._get(
            "channels",
            {"part": "snippet,statistics", "forHandle": handle},
            COST_CHANNELS,
        )
        items = data.get("items") or []
        if not items:
            log.warning("handle %s did not resolve; falling back to search", handle)
            return self.search_channel(handle.lstrip("@"))
        return self._channel_record(items[0])

    def channels_by_ids(self, channel_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for chunk in _chunks([c for c in channel_ids if c], 50):
            data = self._get(
                "channels",
                {"part": "snippet,statistics", "id": ",".join(chunk)},
                COST_CHANNELS,
            )
            for item in data.get("items") or []:
                rec = self._channel_record(item)
                out[rec["channel_id"]] = rec
        return out

    def search_channel(self, query: str) -> Optional[Dict[str, Any]]:
        data = self._get(
            "search",
            {"part": "snippet", "q": query, "type": "channel", "maxResults": 5},
            COST_SEARCH,
        )
        items = data.get("items") or []
        if not items:
            return None
        cid = items[0]["snippet"].get("channelId") or items[0]["id"].get("channelId")
        found = self.channels_by_ids([cid])
        rec = found.get(cid)
        if rec:
            rec["resolved_by"] = "search"
        return rec

    @staticmethod
    def _channel_record(item: Dict[str, Any]) -> Dict[str, Any]:
        stats = item.get("statistics", {})
        snip = item.get("snippet", {})
        return {
            "channel_id": item.get("id"),
            "title": snip.get("title"),
            "handle": snip.get("customUrl"),
            "published_at": snip.get("publishedAt"),
            "country": snip.get("country"),
            "view_count": _int(stats.get("viewCount")),
            "subscriber_count": _int(stats.get("subscriberCount")),
            "video_count": _int(stats.get("videoCount")),
            "hidden_subscriber_count": stats.get("hiddenSubscriberCount", False),
            "url": f"https://www.youtube.com/channel/{item.get('id')}",
            "resolved_by": "handle",
        }

    # ------------------------------------------------------------ video stats
    def top_videos(
        self,
        query: str,
        max_results: int = 50,
        order: str = "viewCount",
        published_after_days: Optional[int] = None,
        region_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Most-viewed videos matching a query, with real view counts attached.

        search.list returns no statistics, so the ids are re-fetched through
        videos.list (1 unit) - that is the only way to get true view counts.
        """
        params: Dict[str, Any] = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": order,
            "maxResults": min(50, max_results),
        }
        if published_after_days:
            since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=published_after_days)
            params["publishedAfter"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        if region_code:
            params["regionCode"] = region_code

        search = self._get("search", params, COST_SEARCH)
        ids = [
            it["id"]["videoId"]
            for it in search.get("items") or []
            if it.get("id", {}).get("videoId")
        ]
        if not ids:
            return []
        videos: List[Dict[str, Any]] = []
        for chunk in _chunks(ids, 50):
            data = self._get(
                "videos",
                {"part": "snippet,statistics", "id": ",".join(chunk)},
                COST_VIDEOS,
            )
            for item in data.get("items") or []:
                stats = item.get("statistics", {})
                snip = item.get("snippet", {})
                videos.append(
                    {
                        "video_id": item.get("id"),
                        "title": snip.get("title"),
                        "channel_id": snip.get("channelId"),
                        "channel_title": snip.get("channelTitle"),
                        "published_at": snip.get("publishedAt"),
                        "view_count": _int(stats.get("viewCount")) or 0,
                        "like_count": _int(stats.get("likeCount")),
                        "comment_count": _int(stats.get("commentCount")),
                        "url": f"https://www.youtube.com/watch?v={item.get('id')}",
                    }
                )
        videos.sort(key=lambda v: v["view_count"], reverse=True)
        return videos

    def query_result_estimate(self, query: str) -> Optional[int]:
        """YouTube's own (rough) 'number of matching videos' for a query."""
        data = self._get(
            "search",
            {"part": "id", "q": query, "type": "video", "maxResults": 1},
            COST_SEARCH,
        )
        return _int((data.get("pageInfo") or {}).get("totalResults"))
