"""Steam + SteamSpy collectors.

All three endpoints are public and keyless:
  * ISteamUserStats/GetNumberOfCurrentPlayers - current concurrent players (Valve)
  * store.steampowered.com/api/storesearch      - appid lookup by name
  * steamspy.com/api.php                        - owners band + 2-week actives
SteamSpy is a third-party estimate, not Valve data: it is recorded with its own
provenance and never silently merged into a Valve-sourced number.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .httpclient import Http, HttpError

log = logging.getLogger(__name__)

PLAYERS_API = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
STORE_SEARCH = "https://store.steampowered.com/api/storesearch/"
APPDETAILS = "https://store.steampowered.com/api/appdetails"
STEAMSPY = "https://steamspy.com/api.php"

_OWNERS_RE = re.compile(r"([\d,\.]+)\s*\.\.\s*([\d,\.]+)")


class Steam:
    def __init__(self, http: Http):
        self.http = http

    def current_players(self, appid: int) -> Optional[Dict[str, Any]]:
        try:
            data = self.http.get_json(PLAYERS_API, {"appid": appid}, use_cache=False)
        except HttpError as exc:
            log.warning("current players failed for %s: %s", appid, exc)
            return None
        resp = data.get("response") or {}
        if resp.get("result") != 1 or "player_count" not in resp:
            return None
        return {
            "appid": appid,
            "concurrent_players": int(resp["player_count"]),
            "source": "Valve ISteamUserStats/GetNumberOfCurrentPlayers",
            "source_url": f"{PLAYERS_API}?appid={appid}",
            "note": "Instantaneous concurrents at fetch time - NOT the 24h peak.",
        }

    def search_appid(self, term: str) -> List[Dict[str, Any]]:
        try:
            data = self.http.get_json(STORE_SEARCH, {"term": term, "cc": "us", "l": "en"})
        except HttpError as exc:
            log.warning("store search failed for %r: %s", term, exc)
            return []
        return [
            {"appid": item.get("id"), "name": item.get("name"), "type": item.get("type")}
            for item in (data.get("items") or [])
        ]

    def appdetails(self, appid: int) -> Optional[Dict[str, Any]]:
        try:
            data = self.http.get_json(APPDETAILS, {"appids": appid, "cc": "us", "l": "en"})
        except HttpError as exc:
            log.warning("appdetails failed for %s: %s", appid, exc)
            return None
        entry = (data or {}).get(str(appid)) or {}
        if not entry.get("success"):
            return None
        d = entry.get("data") or {}
        return {
            "appid": appid,
            "name": d.get("name"),
            "release_date": (d.get("release_date") or {}).get("date"),
            "is_free": d.get("is_free"),
            "developers": d.get("developers"),
            "publishers": d.get("publishers"),
            "source_url": f"https://store.steampowered.com/app/{appid}",
        }


class SteamSpy:
    def __init__(self, http: Http):
        self.http = http

    def appdetails(self, appid: int) -> Optional[Dict[str, Any]]:
        try:
            data = self.http.get_json(STEAMSPY, {"request": "appdetails", "appid": appid})
        except HttpError as exc:
            log.warning("steamspy failed for %s: %s", appid, exc)
            return None
        if not data or not data.get("name"):
            return None
        low, high = self._owners_band(data.get("owners", ""))
        return {
            "appid": appid,
            "name": data.get("name"),
            "owners_low": low,
            "owners_high": high,
            "owners_mid": (low + high) // 2 if low is not None and high is not None else None,
            "ccu_yesterday": data.get("ccu"),
            "players_2weeks": data.get("players_2weeks"),
            "average_2weeks_minutes": data.get("average_2weeks"),
            "source": "SteamSpy (third-party estimate from public profiles)",
            "source_url": f"https://steamspy.com/app/{appid}",
            "note": "Owners is a WIDE band and includes free/gifted copies. Never quote the midpoint as a fact.",
        }

    @staticmethod
    def _owners_band(raw: str):
        match = _OWNERS_RE.search(raw or "")
        if not match:
            return None, None
        clean = lambda s: int(s.replace(",", "").replace(".", ""))
        try:
            return clean(match.group(1)), clean(match.group(2))
        except ValueError:
            return None, None
