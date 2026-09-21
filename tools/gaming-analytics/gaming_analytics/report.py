"""Markdown + CSV rendering.

The markdown mirrors the original review table column-for-column, then adds the
two things it was missing: where each number came from, and how wide its error
bars are.
"""

from __future__ import annotations

import csv
import os
from typing import Any, Dict, List, Optional

from .playerscale import human
from .rank import key_ip_order

CONF_MARK = {"high": "A", "medium": "B", "low": "C"}


def _fmt_range(row: Dict[str, Any], prefix: str) -> str:
    low, mid, high = row.get(prefix + "_low"), row.get(prefix + "_mid"), row.get(prefix + "_high")
    if mid is None:
        return "no signal"
    return f"{human(mid)} ({human(low)}–{human(high)})"


def _link(text: Optional[str], url: Optional[str]) -> str:
    if not text:
        return "-"
    return f"[{text}]({url})" if url else text


def render_markdown(analysis: Dict[str, Any]) -> str:
    run = analysis.get("run", {})
    stats = (run.get("fetch_stats") or {})
    out: List[str] = []
    a = out.append

    a("# Gaming IP x YouTube data pack")
    a("")
    if run.get("fixture"):
        a("> ⚠️ **SYNTHETIC FIXTURE RUN.** Every number below comes from "
          "`tests/fixtures/raw_sample.json`, which contains made-up values used to test the "
          "pipeline offline. Do not quote anything here. Run `python3 run.py all` with a "
          "YouTube API key and network access for real figures.")
        a("")
    a(f"Generated: `{analysis['generated_at']}` · "
      f"requests: {stats.get('requests', 0)} (cache hits {stats.get('cache_hits', 0)}) · "
      f"YouTube quota used: {stats.get('youtube_quota_units', 0)} units")
    a("")
    a("Two review comments drove this table:")
    a("")
    a("1. **\"Player Scale 的数据来源和 estimate 逻辑是什么？\"** — every Player Scale cell below "
      "now shows `mid (low–high)`, the method that produced it, and a confidence grade. "
      "The full derivation is in [METHODOLOGY.md](METHODOLOGY.md); the constants are in "
      "`config/model.json`.")
    a("2. **\"Key IPs 按销量和 YouTube 观看量排序\"** — the Key IPs column is ordered by a composite "
      "score (sales + YouTube views + player scale), and the per-IP table below shows the raw "
      "inputs behind that order.")
    a("")
    a("Confidence grades: **A** = first-party disclosure, **B** = derived from a first-party API "
      "(Steam CCU), **C** = derived from third-party estimates or stale/lifetime figures.")
    a("")

    # ------------------------------------------------------ category table
    a("## 1. Category overview")
    a("")
    a("| Category | Key IPs (ranked) | Player Scale (MAU, mid & range) | Method | Conf. | Top-IP YouTube views | Official channels (sum) | Creator channels (sum) | Coverage |")
    a("|---|---|---|---|---|---|---|---|---|")
    for cat in analysis["categories"]:
        rows = cat.get("ranked_ips", [])
        methods = ", ".join(cat.get("methods_used", [])) or "-"
        conf = CONF_MARK.get(cat.get("confidence", "low"), "C")
        scale = (
            f"{human(cat.get('mau_mid'))} ({human(cat.get('mau_low'))}–{human(cat.get('mau_high'))})"
            if cat.get("status") == "ok"
            else "no signal"
        )
        a(
            f"| **{cat['label']}** | {key_ip_order(rows)} | {scale} | {methods} | {conf} | "
            f"{human(cat.get('top_ip_youtube_views'))} | {human(cat.get('official_channel_views_total'))} | "
            f"{human(cat.get('creator_channels_combined_views'))} | "
            f"{cat.get('covered_ips', 0)}/{cat.get('total_ips', 0)} IPs |"
        )
    a("")
    a("> Player Scale is **monthly active players (MAU)**, summed across the category's IPs and then "
      "cut by an overlap discount (`overlap_discount` in `config/catalog.json`) because one person "
      "plays several shooters. Categories where some IPs have no signal are a **floor, not a total** — "
      "see the coverage column and §4.")
    a("")

    # ------------------------------------------------------------ IP table
    a("## 2. Key IP ranking")
    a("")
    a("| # | IP | Category | Score | Units sold | Official channel views | Creator sample views | Most-viewed video | Player Scale (MAU) | Method | Conf. | Missing |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for row in analysis["ips"]:
        rank = row.get("rank")
        units = (
            _link(human(row["units_sold"]), row.get("units_sold_source"))
            if row.get("units_sold")
            else "n/a (F2P or undisclosed)"
        )
        video = (
            _link(human(row.get("top_video_views")), row.get("top_video_url"))
            if row.get("top_video_views")
            else "-"
        )
        a(
            f"| {rank if rank else '-'} | {row['name']} | {row['category_label']} | "
            f"{row['score'] if row['score'] is not None else '-'} | {units} | "
            f"{_link(human(row.get('official_channel_views')), row.get('official_channel_url'))} | "
            f"{human(row.get('creator_sample_views'))} | {video} | {_fmt_range(row, 'player_scale')} | "
            f"{row.get('player_scale_method') or '-'} | "
            f"{CONF_MARK.get(row.get('player_scale_confidence'), '-')} | "
            f"{', '.join(row.get('score_missing') or []) or '-'} |"
        )
    a("")
    weights = analysis["model"]["ranking"]["weights"]
    a(f"Score = weighted mean of log10-normalised sales ({weights['sales']:.0%}), "
      f"YouTube views ({weights['youtube_views']:.0%}) and player scale ({weights['player_scale']:.0%}); "
      "when a dimension is missing the remaining weights are renormalised (the *Missing* column says which).")
    a("")
    a("**\"Creator sample views\"** is the sum of the most-viewed videos the Data API returns for that "
      "IP's search terms, excluding the official channel. It is a *comparable heat index across IPs*, "
      "not the IP's total YouTube views — the API cannot produce an all-time total for a topic. "
      "Whole-ecosystem figures (e.g. Minecraft's 1.5T) only exist at third-party aggregators such as "
      "letsplayindex, which must be cited as such.")
    a("")

    # ------------------------------------------------------- channel table
    a("## 3. Creator channels")
    a("")
    a("| Category | Channel | Subscribers | Lifetime views | Videos | Country |")
    a("|---|---|---|---|---|---|")
    for cat in analysis["categories"]:
        for ch in cat.get("creator_channels", []):
            if ch.get("error"):
                a(f"| {cat['label']} | {ch.get('handle', '?')} | unresolved: {ch['error']} | - | - | - |")
                continue
            a(
                f"| {cat['label']} | {_link(ch.get('title'), ch.get('url'))} | "
                f"{human(ch.get('subscriber_count'))} | {human(ch.get('view_count'))} | "
                f"{human(ch.get('video_count'))} | {ch.get('country') or '-'} |"
            )
    a("")

    # ------------------------------------------------------------- the gaps
    a("## 4. Data gaps (nothing here is estimated — these need a human or a paid panel)")
    a("")
    if analysis["gaps"]:
        a("| IP | Issue | What to do |")
        a("|---|---|---|")
        for gap in analysis["gaps"]:
            a(f"| {gap['name']} | {gap['issue']} | {gap.get('hint') or '-'} |")
    else:
        a("None — every IP had at least one signal for every column.")
    a("")

    # ------------------------------------------------------------ audit log
    a("## 5. Audit trail")
    a("")
    a("Per-IP derivations, including the cross-check methods that were *not* chosen and any "
      "disagreement between them, are in `out/analysis.json` under `ip_detail`. Raw API payloads are "
      "in `out/raw.json`. Both are regenerated by `python3 run.py all`.")
    a("")
    for cat in analysis["categories"]:
        for row in cat.get("ranked_ips", []):
            detail = analysis["ip_detail"].get(row["ip_id"], {})
            est = detail.get("estimate")
            if not est:
                continue
            srcs = ", ".join(
                f"[{s.get('name') or 'source'}]({s.get('url')})" for s in est.get("sources", []) if s.get("url")
            )
            a(f"- **{row['name']}** — {est['method']}, inputs `{est['inputs']}`"
              + (f", sources: {srcs}" if srcs else "")
              + (f" · ⚠ methods disagree {detail['disagreement_factor']}x" if detail.get("disagreement_factor") else ""))
    a("")
    return "\n".join(out)


IP_CSV_FIELDS = [
    "rank", "ip_id", "name", "category_label", "score", "score_coverage", "score_missing",
    "units_sold", "units_sold_as_of", "units_sold_source",
    "official_channel", "official_channel_views", "official_channel_subs", "official_channel_url",
    "creator_sample_views", "creator_sample_size", "youtube_views_total",
    "top_video_views", "top_video_url", "steam_ccu",
    "player_scale_low", "player_scale_mid", "player_scale_high",
    "player_scale_method", "player_scale_confidence",
]

CATEGORY_CSV_FIELDS = [
    "category_id", "label", "mau_low", "mau_mid", "mau_high", "overlap_discount",
    "covered_ips", "total_ips", "coverage", "confidence", "methods_used",
    "official_channel_views_total", "creator_channels_combined_views", "top_ip_youtube_views",
]


def write_csvs(analysis: Dict[str, Any], out_dir: str) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    written = []

    ip_path = os.path.join(out_dir, "ips.csv")
    with open(ip_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=IP_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in analysis["ips"]:
            row = dict(row)
            row["score_missing"] = ";".join(row.get("score_missing") or [])
            writer.writerow(row)
    written.append(ip_path)

    cat_path = os.path.join(out_dir, "categories.csv")
    with open(cat_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CATEGORY_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for cat in analysis["categories"]:
            cat = dict(cat)
            cat["methods_used"] = ";".join(cat.get("methods_used") or [])
            writer.writerow(cat)
    written.append(cat_path)

    ch_path = os.path.join(out_dir, "channels.csv")
    with open(ch_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["category", "channel_id", "title", "handle", "subscribers", "views", "videos", "url"])
        for cat in analysis["categories"]:
            for ch in cat.get("creator_channels", []):
                writer.writerow([
                    cat["label"], ch.get("channel_id"), ch.get("title"), ch.get("handle"),
                    ch.get("subscriber_count"), ch.get("view_count"), ch.get("video_count"), ch.get("url"),
                ])
    written.append(ch_path)
    return written
