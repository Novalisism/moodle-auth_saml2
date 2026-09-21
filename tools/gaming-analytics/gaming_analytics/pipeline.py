"""Collect -> analyse. Collection writes raw.json; analysis never re-fetches.

Keeping the two apart means the expensive, quota-burning part runs once and the
model can be re-tuned (config/model.json) and re-reported for free.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from typing import Any, Dict, List, Optional

from .playerscale import PlayerScaleEstimator
from .rank import rank_ips, rank_within_categories

log = logging.getLogger(__name__)


def iter_ips(catalog: Dict[str, Any]):
    for category in catalog["categories"]:
        for ip in category["ips"]:
            yield category, ip


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# ------------------------------------------------------------------ resolve
def resolve_identifiers(catalog: Dict[str, Any], steam, youtube, do_steam=True, do_youtube=True):
    """Fill missing Steam appids / YouTube channel ids. Returns (catalog, log)."""
    actions: List[Dict[str, Any]] = []
    for category, ip in iter_ips(catalog):
        if do_steam and ip.get("on_steam") and not ip.get("steam_appid") and steam:
            hits = steam.search_appid(ip["name"])
            games = [h for h in hits if h.get("type") in (None, "game", "app")]
            if games:
                ip["steam_appid"] = games[0]["appid"]
                ip["steam_appid_resolved_from"] = games[0]["name"]
                actions.append(
                    {
                        "ip": ip["id"],
                        "field": "steam_appid",
                        "value": games[0]["appid"],
                        "matched_name": games[0]["name"],
                        "confirm": "Check matched_name is the right SKU (editions/bundles rank high).",
                        "alternatives": games[1:4],
                    }
                )
            else:
                actions.append({"ip": ip["id"], "field": "steam_appid", "value": None, "error": "no store match"})

        if do_youtube and youtube:
            yt_cfg = ip.get("youtube") or {}
            if yt_cfg.get("official_handle") and not yt_cfg.get("official_channel_id"):
                rec = youtube.channel_by_handle(yt_cfg["official_handle"])
                if rec:
                    yt_cfg["official_channel_id"] = rec["channel_id"]
                    actions.append(
                        {
                            "ip": ip["id"],
                            "field": "official_channel_id",
                            "value": rec["channel_id"],
                            "matched_name": rec["title"],
                            "resolved_by": rec.get("resolved_by"),
                            "confirm": "Verify this is the official channel, not a fan mirror.",
                        }
                    )
                else:
                    actions.append(
                        {"ip": ip["id"], "field": "official_channel_id", "value": None, "error": "unresolved"}
                    )
            ip["youtube"] = yt_cfg

    if do_youtube and youtube:
        for category in catalog["categories"]:
            for channel in category.get("creator_channels", []):
                if channel.get("channel_id") or not channel.get("handle"):
                    continue
                rec = youtube.channel_by_handle(channel["handle"])
                if rec:
                    channel["channel_id"] = rec["channel_id"]
                    actions.append(
                        {
                            "category": category["id"],
                            "field": "creator_channel_id",
                            "handle": channel["handle"],
                            "value": rec["channel_id"],
                            "matched_name": rec["title"],
                        }
                    )
                else:
                    actions.append(
                        {
                            "category": category["id"],
                            "field": "creator_channel_id",
                            "handle": channel["handle"],
                            "value": None,
                            "error": "unresolved",
                        }
                    )
    return catalog, actions


# ------------------------------------------------------------------ collect
def collect(
    catalog: Dict[str, Any],
    manual: Dict[str, Any],
    model: Dict[str, Any],
    steam=None,
    steamspy=None,
    youtube=None,
    wikipedia=None,
    with_search: bool = True,
    stats=None,
) -> Dict[str, Any]:
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    yt_cfg = model.get("youtube", {})
    sample_size = int(yt_cfg.get("search_sample_size", 50))

    sales_table: List[Dict[str, Any]] = []
    if wikipedia:
        sales_table = wikipedia.sales_table()

    ips: Dict[str, Any] = {}
    for category, ip in iter_ips(catalog):
        record: Dict[str, Any] = {
            "catalog": ip,
            "category_id": category["id"],
            "category_label": category["label"],
            "errors": [],
        }
        appid = ip.get("steam_appid")
        if steam and appid:
            record["steam_ccu"] = steam.current_players(appid)
            record["steam_app"] = steam.appdetails(appid)
            for extra in ip.get("companion_appids", []) or []:
                record.setdefault("companion_ccu", []).append(steam.current_players(extra))
        if steamspy and appid:
            record["steamspy"] = steamspy.appdetails(appid)
        if wikipedia and ip.get("sales_key"):
            record["wikipedia_sales"] = wikipedia.lookup(ip["sales_key"], sales_table)

        if youtube:
            yt: Dict[str, Any] = {"official_channel": None, "top_videos": [], "queries": []}
            channel_id = (ip.get("youtube") or {}).get("official_channel_id")
            handle = (ip.get("youtube") or {}).get("official_handle")
            try:
                if channel_id:
                    yt["official_channel"] = youtube.channels_by_ids([channel_id]).get(channel_id)
                elif handle:
                    yt["official_channel"] = youtube.channel_by_handle(handle)
            except Exception as exc:  # collection must not die on one channel
                record["errors"].append(f"youtube channel: {exc}")
            if with_search:
                seen = set()
                for query in (ip.get("youtube") or {}).get("search_queries", []):
                    try:
                        videos = youtube.top_videos(
                            query,
                            max_results=sample_size,
                            order=yt_cfg.get("search_order", "viewCount"),
                        )
                    except Exception as exc:
                        record["errors"].append(f"youtube search {query!r}: {exc}")
                        continue
                    fresh = [v for v in videos if v["video_id"] not in seen]
                    seen.update(v["video_id"] for v in fresh)
                    yt["top_videos"].extend(fresh)
                    yt["queries"].append({"query": query, "returned": len(videos), "new": len(fresh)})
                yt["top_videos"].sort(key=lambda v: v["view_count"], reverse=True)
            record["youtube"] = yt
        ips[ip["id"]] = record

    channels: Dict[str, Any] = {}
    if youtube:
        for category in catalog["categories"]:
            for channel in category.get("creator_channels", []):
                key = channel.get("channel_id") or channel.get("handle")
                if not key:
                    continue
                try:
                    if channel.get("channel_id"):
                        rec = youtube.channels_by_ids([channel["channel_id"]]).get(channel["channel_id"])
                    else:
                        rec = youtube.channel_by_handle(channel["handle"])
                except Exception as exc:
                    rec = {"error": str(exc), "handle": channel.get("handle")}
                if rec:
                    rec = dict(rec)
                    rec["category_id"] = category["id"]
                    rec.setdefault("handle", channel.get("handle"))
                    channels[key] = rec

    return {
        "run": {
            "started_at": started,
            "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "with_search": with_search,
            "fetch_stats": stats.as_dict() if stats else None,
            "collectors": {
                "steam": bool(steam),
                "steamspy": bool(steamspy),
                "youtube": bool(youtube),
                "wikipedia": bool(wikipedia),
            },
        },
        "catalog": catalog,
        "manual_figures": manual.get("figures", []),
        "ips": ips,
        "creator_channels": channels,
        "wikipedia_rows": len(sales_table),
    }


# ------------------------------------------------------------------ analyse
F2P_TYPES = {"live_service", "gacha_live_service", "sandbox_live"}


def _units_hint(ip: Dict[str, Any], manual_rows: List[Dict[str, Any]]) -> str:
    """A useful next step, not a generic excuse - premium and F2P fail differently."""
    seeded = next(
        (r for r in manual_rows if r.get("ip") == ip["id"] and r.get("metric") == "units_sold"),
        None,
    )
    if seeded and not seeded.get("value"):
        return f"Seed row exists but is empty - pull the figure from {seeded.get('source_url')}."
    if ip.get("game_type") in F2P_TYPES and not ip.get("sales_key"):
        return ("Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the "
                "sales column blank rather than implying zero.")
    return ("Premium title with no units figure - check the publisher's IR page and add it to "
            "config/manual_figures.json, or set sales_key so the Wikipedia lookup can find it.")


def _manual_for(manual_rows, ip_id: str, metric: str, allow_unverified: bool):
    for row in manual_rows:
        if row.get("ip") == ip_id and row.get("metric") == metric and row.get("value"):
            if row.get("verified") or allow_unverified:
                return row
    return None


def analyse(raw: Dict[str, Any], model: Dict[str, Any], allow_unverified: bool = True) -> Dict[str, Any]:
    estimator = PlayerScaleEstimator(model)
    manual_rows = raw.get("manual_figures", [])
    catalog = raw["catalog"]

    ip_rows: List[Dict[str, Any]] = []
    detail: Dict[str, Any] = {}
    gaps: List[Dict[str, Any]] = []

    for category, ip in iter_ips(catalog):
        rec = raw["ips"].get(ip["id"], {})
        signals = {
            "official_mau": _manual_for(manual_rows, ip["id"], "mau", allow_unverified) or {},
            "steam_ccu": rec.get("steam_ccu") or {},
            "steamspy": rec.get("steamspy") or {},
            "units_sold": _manual_for(manual_rows, ip["id"], "units_sold", allow_unverified) or {},
            "registered_users": _manual_for(manual_rows, ip["id"], "registered_users", allow_unverified) or {},
        }
        wiki = rec.get("wikipedia_sales")
        if not signals["units_sold"].get("value") and wiki:
            signals["units_sold"] = {
                "value": wiki["units_sold"],
                "as_of": None,
                "source_name": wiki["source"],
                "source_url": wiki.get("citation_url") or wiki["source_url"],
                "confidence": "press_report",
            }
        result = estimator.estimate_ip({**ip, **{"platforms": ip.get("platforms")}}, signals)
        detail[ip["id"]] = result

        yt = rec.get("youtube") or {}
        official = yt.get("official_channel") or {}
        official_views = official.get("view_count")
        sample_videos = yt.get("top_videos") or []
        creator_views = sum(
            v["view_count"]
            for v in sample_videos
            if v.get("channel_id") != official.get("channel_id")
        )
        units = signals["units_sold"].get("value")
        estimate = result.get("estimate") or {}

        if not estimate:
            gaps.append({"ip": ip["id"], "name": ip["name"], "issue": "no player-scale signal", "hint": result.get("missing")})
        if units is None:
            gaps.append({"ip": ip["id"], "name": ip["name"], "issue": "no units-sold figure",
                         "hint": _units_hint(ip, manual_rows)})
        if official_views is None:
            gaps.append({"ip": ip["id"], "name": ip["name"], "issue": "official YouTube channel unresolved",
                         "hint": "Set youtube.official_channel_id in config/catalog.json or rerun `resolve`."})

        ip_rows.append(
            {
                "ip_id": ip["id"],
                "name": ip["name"],
                "category_id": category["id"],
                "category_label": category["label"],
                "units_sold": units,
                "units_sold_source": signals["units_sold"].get("source_url"),
                "units_sold_as_of": signals["units_sold"].get("as_of"),
                "official_channel": official.get("title"),
                "official_channel_url": official.get("url"),
                "official_channel_views": official_views,
                "official_channel_subs": official.get("subscriber_count"),
                "creator_sample_views": creator_views or None,
                "creator_sample_size": len(sample_videos) or None,
                "youtube_views_total": (official_views or 0) + (creator_views or 0) or None,
                "top_video_url": sample_videos[0]["url"] if sample_videos else None,
                "top_video_views": sample_videos[0]["view_count"] if sample_videos else None,
                "player_scale_low": estimate.get("mau_low"),
                "player_scale_mid": estimate.get("mau_mid"),
                "player_scale_high": estimate.get("mau_high"),
                "player_scale_method": estimate.get("method"),
                "player_scale_confidence": estimate.get("confidence"),
                "steam_ccu": (rec.get("steam_ccu") or {}).get("concurrent_players"),
            }
        )

    ranked = rank_ips(ip_rows, model["ranking"]["weights"])
    by_category = rank_within_categories(ranked)

    categories: List[Dict[str, Any]] = []
    for category in catalog["categories"]:
        results = [detail[ip["id"]] for ip in category["ips"]]
        summary = estimator.estimate_category(category, results)
        rows = by_category.get(category["id"], [])
        channel_rows = [
            c for c in raw.get("creator_channels", {}).values() if c.get("category_id") == category["id"]
        ]
        summary["ranked_ips"] = rows
        summary["creator_channels"] = channel_rows
        summary["creator_channels_combined_views"] = sum(
            c.get("view_count") or 0 for c in channel_rows
        ) or None
        summary["official_channel_views_total"] = sum(
            r.get("official_channel_views") or 0 for r in rows
        ) or None
        summary["top_ip_youtube_views"] = max(
            (r.get("youtube_views_total") or 0 for r in rows), default=0
        ) or None
        categories.append(summary)

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model": model,
        "categories": categories,
        "ips": ranked,
        "ip_detail": detail,
        "gaps": gaps,
        "run": raw.get("run", {}),
    }
