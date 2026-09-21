"""Command line entry point: resolve / collect / report / all / verify / selftest."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, Optional

from . import pipeline
from .httpclient import FetchStats, Http, ProxyAuthError
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


def _resolve_proxy(args) -> Optional[str]:
    """Work out the proxy URL, injecting credentials without ever putting the
    password on the command line (shell history, `ps`, and screen shares all
    leak it there)."""
    import getpass
    import urllib.parse
    import urllib.request

    base = args.proxy or os.environ.get("HTTPS_PROXY") or ""
    if not base:
        detected = urllib.request.getproxies()
        base = detected.get("https") or detected.get("http") or ""
    user = getattr(args, "proxy_user", None)
    if not user or not base:
        return base or None
    if "@" in base.split("//", 1)[-1]:
        return base  # credentials already present
    password = os.environ.get("PROXY_PASSWORD")
    if password is None:
        password = getpass.getpass(f"代理密码 / proxy password for {user} (输入时不显示): ")
    scheme, _, rest = base.partition("://")
    quote = lambda v: urllib.parse.quote(v, safe="")
    return f"{scheme}://{quote(user)}:{quote(password)}@{rest}"


def _http(args) -> Http:
    return Http(
        cache_dir=args.cache,
        ttl_seconds=args.cache_ttl,
        offline=getattr(args, "offline", False),
        proxy=_resolve_proxy(args),
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
    return YouTube(http, key, allow_search_fallback=not getattr(args, "no_search", False))


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
    manual = pipeline.load_json(args.manual) if os.path.exists(args.manual) else None
    analysis = pipeline.analyse(
        raw, model, allow_unverified=not args.verified_only, manual=manual
    )
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



CHECKS = [
    ("YouTube (必需 / required)", "https://www.googleapis.com/youtube/v3/videos?part=id&id=dQw4w9WgXcQ"),
    ("Steam 在线人数 / current players", "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid=730"),
    ("Steam 商店 / store", "https://store.steampowered.com/api/storesearch/?term=dota&cc=us&l=en"),
    ("SteamSpy", "https://steamspy.com/api.php?request=appdetails&appid=570"),
    ("Wikipedia", "https://en.wikipedia.org/w/api.php?action=query&format=json&meta=siteinfo"),
]


def cmd_doctor(args) -> int:
    """Print environment + proxy + per-host reachability, in plain language."""
    import platform
    import urllib.request

    print("== 环境 / environment ==")
    print(f"  Python {platform.python_version()} on {platform.system()} {platform.release()}")
    print(f"  API key: {'已设置 / set' if (args.api_key or os.environ.get('YOUTUBE_API_KEY')) else '未设置 / MISSING'}")

    print("\n== 代理 / proxy ==")
    # getproxies() also surfaces npm_/yarn_/docker_ env vars; only the real
    # scheme keys matter, and the noise buries the one line that does.
    detected = {
        k: v for k, v in urllib.request.getproxies().items()
        if k in ("http", "https", "ftp", "all", "no")
    }
    chosen = _resolve_proxy(args)
    if detected:
        for scheme, value in sorted(detected.items()):
            shown = value if len(value) < 90 else value[:87] + "..."
            print(f"  系统检测到 / detected {scheme}: {shown}")
    else:
        print("  系统未设置代理 / no system proxy detected")
    import re as _re
    safe_chosen = _re.sub(r"://[^/@]*:[^/@]*@", "://***:***@", chosen) if chosen else None
    print(f"  本次使用 / using: {safe_chosen or '不走代理 (direct)'}")

    print("\n== 连通性 / reachability ==")
    key = args.api_key or os.environ.get("YOUTUBE_API_KEY", "")
    failures, proxy_auth = [], False
    for label, url in CHECKS:
        http = Http(cache_dir=args.cache, ttl_seconds=0, timeout=15, retries=0,
                    proxy=chosen, stats=FetchStats())
        target = url + (f"&key={key}" if "googleapis" in url and key else "")
        try:
            http.get_text(target, use_cache=False)
            print(f"  [OK]   {label}")
        except ProxyAuthError:
            proxy_auth = True
            failures.append(label)
            print(f"  [407]  {label} - 代理要求账号密码 / proxy wants credentials")
        except Exception as exc:
            detail = str(exc)
            # A 403 from Google means we reached Google - the key is the issue, not the network.
            if "HTTP 403" in detail and "googleapis" in target:
                print(f"  [OK]   {label} (可达，但 key 被拒 / reachable, key rejected)")
                continue
            failures.append(label)
            print(f"  [FAIL] {label} - {detail.splitlines()[0][:110]}")

    print("\n== 结论 / verdict ==")
    if proxy_auth:
        print("  你的网络必须经过一个需要账号密码的代理。三种解法，任选其一：")
        print("  Your network forces an authenticating proxy. Pick one:")
        print("   1) 如果你在用梯子/代理软件（Clash、V2Ray 等）：在软件里找到 HTTP 端口（常见 7890），然后")
        print("      $env:HTTPS_PROXY=\"http://127.0.0.1:7890\"   再重跑")
        print("   2) 如果是公司代理：python run.py doctor --proxy-user 你的公司账号  (会提示你输密码，不显示)")
        print("   3) 如果这些网站本来就能直接打开：关掉系统代理后重跑")
    elif not failures:
        print("  全部通过，可以直接跑 python run.py all")
    else:
        blocked = ", ".join(failures)
        print(f"  连不上：{blocked}")
        print("  YouTube 连不上则无法出数；Steam/Wikipedia 连不上可以先跳过：")
        print("  python run.py all --no-steam --no-wikipedia")
    return 0 if not failures else 1


def _add_global_args(parser: argparse.ArgumentParser, suppress: bool = False) -> None:
    """Global options, added to the top parser AND to every subparser.

    argparse only accepts a top-level option before the subcommand, so
    `run.py doctor --proxy-user me` would otherwise be rejected - which is
    exactly how people type it. The subparser copies default to SUPPRESS so
    that omitting them does not overwrite what the top-level parser already
    parsed.
    """
    d = (lambda value: argparse.SUPPRESS) if suppress else (lambda value: value)
    parser.add_argument("--catalog", default=d(DEFAULTS["catalog"]))
    parser.add_argument("--model", default=d(DEFAULTS["model"]))
    parser.add_argument("--manual", default=d(DEFAULTS["manual"]))
    parser.add_argument("--out", default=d(DEFAULTS["out"]))
    parser.add_argument("--cache", default=d(DEFAULTS["cache"]))
    parser.add_argument("--cache-ttl", type=int, default=d(24 * 3600),
                        help="Seconds a cached response stays fresh (default 86400, -1 = forever).")
    parser.add_argument("--proxy-user", default=d(None),
                        help="Proxy username; the password is prompted for (never typed on the "
                             "command line) or read from the PROXY_PASSWORD env var.")
    parser.add_argument("--proxy", default=d(None),
                        help="Proxy URL, e.g. http://127.0.0.1:7890 or http://user:pass@host:port.")
    parser.add_argument("--api-key", default=d(None),
                        help="YouTube Data API key (or env YOUTUBE_API_KEY).")
    parser.add_argument("-v", "--verbose", action="store_true",
                        default=argparse.SUPPRESS if suppress else False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Collect Steam + YouTube data for gaming IPs and produce an "
                    "auditable player-scale / ranking report.",
    )
    _add_global_args(parser)

    common = argparse.ArgumentParser(add_help=False)
    _add_global_args(common, suppress=True)

    sub = parser.add_subparsers(dest="command", required=True)

    p_resolve = sub.add_parser("resolve", parents=[common],
                               help="Fill missing Steam appids / YouTube channel ids.")
    p_resolve.add_argument("--no-steam", action="store_true")
    p_resolve.add_argument("--no-youtube", action="store_true")
    p_resolve.set_defaults(func=cmd_resolve, offline=False)

    for name, func, helptext in (
        ("collect", cmd_collect, "Fetch everything into out/raw.json."),
        ("all", cmd_all, "collect + report."),
    ):
        p = sub.add_parser(name, parents=[common], help=helptext)
        p.add_argument("--no-search", action="store_true",
                       help="Skip search.list (saves 100 quota units per query).")
        p.add_argument("--no-steam", action="store_true")
        p.add_argument("--no-wikipedia", action="store_true")
        p.add_argument("--offline", action="store_true", help="Serve everything from cache.")
        p.add_argument("--raw", default=None)
        p.add_argument("--verified-only", action="store_true",
                       help="Ignore manual figures with verified=false.")
        p.set_defaults(func=func)

    p_report = sub.add_parser("report", parents=[common],
                              help="Build report.md + CSVs from out/raw.json.")
    p_report.add_argument("--raw", default=None)
    p_report.add_argument("--verified-only", action="store_true")
    p_report.set_defaults(func=cmd_report, offline=True)

    p_verify = sub.add_parser("verify", parents=[common],
                              help="List hand-entered figures and their staleness.")
    p_verify.set_defaults(func=cmd_verify, offline=True)

    p_doctor = sub.add_parser("doctor", parents=[common],
                              help="Check Python, proxy and which sites are reachable.")
    p_doctor.set_defaults(func=cmd_doctor, offline=False)

    p_self = sub.add_parser("selftest", parents=[common],
                            help="Run the whole analysis on the offline fixture.")
    p_self.set_defaults(func=cmd_selftest, offline=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)
