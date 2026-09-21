"""Command line entry point: resolve / collect / report / all / verify / selftest."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, Optional

from . import pipeline
from .httpclient import FetchStats, Http
from .playerscale import human, parse_as_of
from .report import render_markdown, write_csvs
from .steam import Steam, SteamSpy
from .wikipedia import Wikipedia
from .youtube import YouTube

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULTS = {
    "catalog": os.path.join(HERE, "config", "catalog.json"),
    "resolved": os.path.join(HERE, "config", "catalog.resolved.json"),
    "model": os.path.join(HERE, "config", "model.json"),
    "manual": os.path.join(HERE, "config", "manual_figures.json"),
    "out": os.path.join(HERE, "out"),
    "cache": os.path.join(HERE, ".cache"),
}
log = logging.getLogger("gaming_analytics")


def _catalog_path(args) -> str:
    """Prefer the resolved catalog when it exists and the user did not override."""
    if args.catalog != DEFAULTS["catalog"]:
        return args.catalog
    if os.path.exists(DEFAULTS["resolved"]):
        return DEFAULTS["resolved"]
    return args.catalog


def _http(args) -> Http:
    return Http(
        cache_dir=args.cache,
        ttl_seconds=args.cache_ttl,
        offline=getattr(args, "offline", False),
        stats=FetchStats(),
    )


def _youtube(http: Http, args) -> Optional[YouTube]:
    key = args.api_key or os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        log.warning(
            "No YouTube API key (set YOUTUBE_API_KEY or pass --api-key). "
            "Continuing without any YouTube data."
        )
        return None
    return YouTube(http, key)


# ---------------------------------------------------------------- commands
def cmd_resolve(args) -> int:
    http = _http(args)
    catalog = pipeline.load_json(_catalog_path(args))
    steam = Steam(http) if not args.no_steam else None
    youtube = _youtube(http, args) if not args.no_youtube else None
    catalog, actions = pipeline.resolve_identifiers(
        catalog, steam, youtube, do_steam=not args.no_steam, do_youtube=not args.no_youtube
    )
    pipeline.dump_json(DEFAULTS["resolved"], catalog)
    pipeline.dump_json(os.path.join(args.out, "resolve_log.json"), actions)
    print(f"resolved catalog -> {DEFAULTS['resolved']}")
    for action in actions:
        status = action.get("error") or f"{action.get('value')} ({action.get('matched_name', '')})"
        print(f"  {action.get('ip') or action.get('category')}.{action['field']}: {status}")
    print("\nReview config/catalog.resolved.json before trusting it: store search and "
          "channel search both return plausible wrong answers.")
    return 0


def cmd_collect(args) -> int:
    http = _http(args)
    catalog = pipeline.load_json(_catalog_path(args))
    model = pipeline.load_json(args.model)
    manual = pipeline.load_json(args.manual)
    raw = pipeline.collect(
        catalog,
        manual,
        model,
        steam=None if args.no_steam else Steam(http),
        steamspy=None if args.no_steam else SteamSpy(http),
        youtube=_youtube(http, args),
        wikipedia=None if args.no_wikipedia else Wikipedia(http),
        with_search=not args.no_search,
        stats=http.stats,
    )
    path = os.path.join(args.out, "raw.json")
    pipeline.dump_json(path, raw)
    stats = http.stats.as_dict()
    print(f"raw data -> {path}")
    print(f"requests={stats['requests']} cache_hits={stats['cache_hits']} "
          f"errors={stats['errors']} youtube_quota={stats['youtube_quota_units']}")
    return 0


def cmd_report(args) -> int:
    raw_path = args.raw or os.path.join(args.out, "raw.json")
    if not os.path.exists(raw_path):
        print(f"{raw_path} not found - run `collect` first.", file=sys.stderr)
        return 2
    raw = pipeline.load_json(raw_path)
    model = pipeline.load_json(args.model)
    analysis = pipeline.analyse(raw, model, allow_unverified=not args.verified_only)
    pipeline.dump_json(os.path.join(args.out, "analysis.json"), analysis)
    markdown = render_markdown(analysis)
    md_path = os.path.join(args.out, "report.md")
    os.makedirs(args.out, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(markdown)
    written = write_csvs(analysis, args.out)
    print(f"report -> {md_path}")
    for path in written:
        print(f"csv    -> {path}")
    if analysis["gaps"]:
        print(f"\n{len(analysis['gaps'])} data gaps - see section 4 of the report.")
    return 0


def cmd_all(args) -> int:
    code = cmd_collect(args)
    return code or cmd_report(args)


def cmd_verify(args) -> int:
    """List every hand-entered figure and how stale it is."""
    manual = pipeline.load_json(args.manual)
    import datetime as dt

    today = dt.date.today()
    rows = manual.get("figures", [])
    print(f"{len(rows)} manual figures in {args.manual}\n")
    unverified = 0
    for row in rows:
        date = parse_as_of(row.get("as_of"))
        age = f"{(today - date).days}d old" if date else "no date"
        value = human(row["value"]) if row.get("value") else "MISSING"
        flag = "OK " if row.get("verified") else "TODO"
        if not row.get("verified"):
            unverified += 1
        print(f"[{flag}] {row['ip']:<20} {row['metric']:<16} {value:>8}  {age:<12} {row.get('source_url')}")
        if row.get("note"):
            print(f"       note: {row['note']}")
    print(
        f"\n{unverified} figure(s) still marked verified=false. Open each source_url, confirm the "
        "number and the date, then set verified=true. `report --verified-only` refuses to use the rest."
    )
    return 0


def cmd_selftest(args) -> int:
    """Run analyse+render against the committed fixture - no network, no key."""
    fixture = os.path.join(HERE, "tests", "fixtures", "raw_sample.json")
    raw = pipeline.load_json(fixture)
    model = pipeline.load_json(args.model)
    analysis = pipeline.analyse(raw, model)
    markdown = render_markdown(analysis)
    out_dir = os.path.join(args.out, "selftest")
    pipeline.dump_json(os.path.join(out_dir, "analysis.json"), analysis)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(markdown)
    write_csvs(analysis, out_dir)
    ranked = [r for r in analysis["ips"] if r["rank"]]
    print(f"selftest ok: {len(analysis['categories'])} categories, {len(ranked)} ranked IPs, "
          f"{len(analysis['gaps'])} gaps -> {out_dir}/report.md")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Collect Steam + YouTube data for gaming IPs and produce an "
                    "auditable player-scale / ranking report.",
    )
    parser.add_argument("--catalog", default=DEFAULTS["catalog"])
    parser.add_argument("--model", default=DEFAULTS["model"])
    parser.add_argument("--manual", default=DEFAULTS["manual"])
    parser.add_argument("--out", default=DEFAULTS["out"])
    parser.add_argument("--cache", default=DEFAULTS["cache"])
    parser.add_argument("--cache-ttl", type=int, default=24 * 3600,
                        help="Seconds a cached response stays fresh (default 86400, -1 = forever).")
    parser.add_argument("--api-key", default=None, help="YouTube Data API key (or env YOUTUBE_API_KEY).")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    p_resolve = sub.add_parser("resolve", help="Fill missing Steam appids / YouTube channel ids.")
    p_resolve.add_argument("--no-steam", action="store_true")
    p_resolve.add_argument("--no-youtube", action="store_true")
    p_resolve.set_defaults(func=cmd_resolve, offline=False)

    for name, func, helptext in (
        ("collect", cmd_collect, "Fetch everything into out/raw.json."),
        ("all", cmd_all, "collect + report."),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--no-search", action="store_true",
                       help="Skip search.list (saves 100 quota units per query).")
        p.add_argument("--no-steam", action="store_true")
        p.add_argument("--no-wikipedia", action="store_true")
        p.add_argument("--offline", action="store_true", help="Serve everything from cache.")
        p.add_argument("--raw", default=None)
        p.add_argument("--verified-only", action="store_true",
                       help="Ignore manual figures with verified=false.")
        p.set_defaults(func=func)

    p_report = sub.add_parser("report", help="Build report.md + CSVs from out/raw.json.")
    p_report.add_argument("--raw", default=None)
    p_report.add_argument("--verified-only", action="store_true")
    p_report.set_defaults(func=cmd_report, offline=True)

    p_verify = sub.add_parser("verify", help="List hand-entered figures and their staleness.")
    p_verify.set_defaults(func=cmd_verify, offline=True)

    p_self = sub.add_parser("selftest", help="Run the whole analysis on the offline fixture.")
    p_self.set_defaults(func=cmd_selftest, offline=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)
