"""Offline unit tests: python3 -m unittest discover -s tests -v"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from gaming_analytics import pipeline, rank, report, wikipedia  # noqa: E402
from gaming_analytics.httpclient import (  # noqa: E402
    Http,
    HttpError,
    ProxyAuthError,
    _is_proxy_auth_failure,
)
from gaming_analytics.playerscale import (  # noqa: E402
    PlayerScaleEstimator,
    human,
    parse_as_of,
)
from gaming_analytics.steam import SteamSpy  # noqa: E402

MODEL = pipeline.load_json(os.path.join(ROOT, "config", "model.json"))


class TestParsing(unittest.TestCase):
    def test_units_from_wikitext(self):
        self.assertEqual(wikipedia._parse_units("| 300,000,000"), 300_000_000)
        self.assertEqual(wikipedia._parse_units("|{{nts|230}}<ref name=a/>"), 230_000_000)
        self.assertEqual(wikipedia._parse_units("| 1.5 billion"), 1_500_000_000)
        self.assertEqual(wikipedia._parse_units("| {{sort|33.10|33.10 million}}"), 33_100_000)
        self.assertIsNone(wikipedia._parse_units("| TBA"))

    def test_owners_band(self):
        self.assertEqual(
            SteamSpy._owners_band("100,000,000 .. 200,000,000"), (100_000_000, 200_000_000)
        )
        self.assertEqual(SteamSpy._owners_band("unknown"), (None, None))

    def test_as_of_formats(self):
        self.assertEqual(parse_as_of("2024-02-15"), dt.date(2024, 2, 15))
        self.assertEqual(parse_as_of("2024-02"), dt.date(2024, 2, 1))
        self.assertEqual(parse_as_of("2024"), dt.date(2024, 1, 1))
        self.assertIsNone(parse_as_of(None))

    def test_human(self):
        self.assertEqual(human(1.5e12), "1.5T")
        self.assertEqual(human(None), "n/a")


class TestEstimator(unittest.TestCase):
    def setUp(self):
        self.est = PlayerScaleEstimator(MODEL, today=dt.date(2026, 9, 21))
        self.ip = {
            "id": "demo",
            "name": "Demo",
            "game_type": "live_service",
            "platforms": ["pc"],
            "on_steam": True,
        }

    def test_ccu_math_is_the_documented_formula(self):
        est = self.est.from_steam_ccu(self.ip, {"concurrent_players": 1_000_000})
        expected = 1_000_000 * MODEL["ccu_to_dau"]["value"] * MODEL["dau_to_mau"]["value"]
        self.assertAlmostEqual(est.mau_mid, expected, places=3)
        self.assertLess(est.mau_low, est.mau_mid)
        self.assertGreater(est.mau_high, est.mau_mid)

    def test_platform_multiplier_raises_cross_platform_titles(self):
        pc_only = self.est.from_steam_ccu(self.ip, {"concurrent_players": 100_000})
        cross = self.est.from_steam_ccu(
            {**self.ip, "platforms": ["pc", "console", "mobile"]},
            {"concurrent_players": 100_000},
        )
        self.assertGreater(cross.mau_mid, pc_only.mau_mid)
        self.assertLessEqual(cross.mau_mid / pc_only.mau_mid, MODEL["platform_multipliers"]["cap"])

    def test_stale_official_figure_gets_a_wider_band(self):
        fresh = self.est.from_official_mau(self.ip, {"value": 1e8, "as_of": "2026-08"})
        stale = self.est.from_official_mau(self.ip, {"value": 1e8, "as_of": "2018-01"})
        self.assertEqual(fresh.mau_mid, stale.mau_mid)
        self.assertGreater(stale.mau_high - stale.mau_low, fresh.mau_high - fresh.mau_low)

    def test_single_player_converts_units_far_more_conservatively(self):
        sp = self.est.from_units_sold(
            {**self.ip, "game_type": "single_player"}, {"value": 1e8, "as_of": "2026-06"}
        )
        live = self.est.from_units_sold(
            {**self.ip, "game_type": "live_service"}, {"value": 1e8, "as_of": "2026-06"}
        )
        self.assertLess(sp.mau_mid, live.mau_mid)

    def test_method_priority_prefers_official_disclosure(self):
        result = self.est.estimate_ip(
            self.ip,
            {
                "official_mau": {"value": 5e7, "as_of": "2026-08", "confidence": "official_disclosure"},
                "steam_ccu": {"concurrent_players": 100_000},
            },
        )
        self.assertEqual(result["estimate"]["method"], "official_mau")
        self.assertEqual(result["cross_checks"][0]["method"], "steam_ccu")

    def test_disagreement_downgrades_confidence_and_widens_range(self):
        result = self.est.estimate_ip(
            self.ip,
            {
                "official_mau": {"value": 1e6, "as_of": "2026-08", "confidence": "official_disclosure"},
                "steam_ccu": {"concurrent_players": 1_000_000},  # ~29M, a 29x gap
            },
        )
        self.assertEqual(result["estimate"]["confidence"], "low")
        self.assertIsNotNone(result["disagreement_factor"])
        self.assertGreater(result["estimate"]["mau_high"], 1e7)

    def test_no_signal_is_reported_not_guessed(self):
        result = self.est.estimate_ip(self.ip, {})
        self.assertIsNone(result["estimate"])
        self.assertEqual(result["status"], "no_signal")

    def test_category_applies_overlap_discount_and_tracks_coverage(self):
        ips = [
            self.est.estimate_ip(self.ip, {"steam_ccu": {"concurrent_players": 100_000}}),
            self.est.estimate_ip({**self.ip, "id": "demo2"}, {}),
        ]
        summary = self.est.estimate_category(
            {"id": "c", "label": "C", "overlap_discount": 0.25}, ips
        )
        single = ips[0]["estimate"]["mau_mid"]
        self.assertAlmostEqual(summary["mau_mid"], round(single * 0.75), delta=1)
        self.assertEqual(summary["covered_ips"], 1)
        self.assertEqual(summary["total_ips"], 2)
        self.assertEqual(summary["confidence"], "low")  # coverage < 0.6


class TestRanking(unittest.TestCase):
    def test_missing_dimension_renormalises_instead_of_scoring_zero(self):
        rows = [
            {"ip_id": "a", "name": "A", "category_id": "c", "units_sold": 3e8,
             "youtube_views_total": 1e12, "player_scale_mid": 1e8},
            {"ip_id": "b", "name": "B", "category_id": "c", "units_sold": None,
             "youtube_views_total": 9e11, "player_scale_mid": 9e7},
            {"ip_id": "c", "name": "C", "category_id": "c", "units_sold": None,
             "youtube_views_total": None, "player_scale_mid": None},
        ]
        ranked = rank.rank_ips(rows, MODEL["ranking"]["weights"])
        by_id = {r["ip_id"]: r for r in ranked}
        self.assertEqual(by_id["a"]["rank"], 1)
        self.assertLess(by_id["b"]["score_coverage"], 1.0)
        self.assertIsNone(by_id["c"]["rank"])
        self.assertIsNone(by_id["c"]["score"])

    def test_log_scaling_keeps_small_ips_distinguishable(self):
        rows = [
            {"ip_id": str(i), "name": str(i), "category_id": "c", "units_sold": None,
             "youtube_views_total": v, "player_scale_mid": None}
            for i, v in enumerate([1e12, 1e10, 1e9, 1e8])
        ]
        ranked = rank.rank_ips(rows, {"sales": 0, "youtube_views": 1, "player_scale": 0})
        scores = [r["score"] for r in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertGreater(scores[-2], 0.0)  # not collapsed to zero by the outlier

    def test_key_ip_order_names_unranked_ips(self):
        rows = [{"name": "A", "score": 0.9}, {"name": "B", "score": None}]
        text = rank.key_ip_order(rows)
        self.assertIn("A", text)
        self.assertIn("unranked", text)


class TestHttpCache(unittest.TestCase):
    def test_api_key_never_reaches_the_cache_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            http = Http(cache_dir=tmp)
            with_key = http._cache_key("https://x/y", {"q": "a", "key": "SECRET"})
            without = http._cache_key("https://x/y", {"q": "a"})
            self.assertEqual(with_key, without)

    def test_offline_without_cache_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            http = Http(cache_dir=tmp, offline=True)
            with self.assertRaises(HttpError):
                http.get_text("https://example.invalid/nothing")

    def test_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            http = Http(cache_dir=tmp, offline=True)
            key = http._cache_key("https://x/y", None)
            http._write_cache(key, "https://x/y", '{"ok": true}')
            body, cached = http.get_text("https://x/y")
            self.assertTrue(cached)
            self.assertEqual(json.loads(body)["ok"], True)


class TestProxyHandling(unittest.TestCase):
    def test_407_is_recognised_as_a_proxy_auth_failure(self):
        self.assertTrue(
            _is_proxy_auth_failure(
                OSError("Tunnel connection failed: 407 Proxy Authentication Required")
            )
        )
        self.assertFalse(_is_proxy_auth_failure(OSError("connection reset by peer")))
        self.assertFalse(_is_proxy_auth_failure(OSError("HTTP 407")))  # no proxy wording

    def test_proxy_auth_fails_fast_instead_of_retrying(self):
        """Four backoff rounds per URL cannot fix missing credentials."""
        import urllib.error

        with tempfile.TemporaryDirectory() as tmp:
            http = Http(cache_dir=tmp, retries=4, min_interval=0)
            calls = []

            class FakeOpener:
                def open(self, req, timeout=None):
                    calls.append(req.full_url)
                    raise urllib.error.URLError(
                        "Tunnel connection failed: 407 Proxy Authentication Required"
                    )

            http._opener = FakeOpener()
            with self.assertRaises(ProxyAuthError) as ctx:
                http.get_text("https://example.invalid/x", use_cache=False)
            self.assertEqual(len(calls), 1)
            self.assertIn("run.py doctor", str(ctx.exception))

    def test_explicit_proxy_is_installed_on_the_opener(self):
        with tempfile.TemporaryDirectory() as tmp:
            http = Http(cache_dir=tmp, proxy="http://127.0.0.1:7890")
            self.assertEqual(http.proxy, "http://127.0.0.1:7890")
            self.assertTrue(any(
                type(h).__name__ == "ProxyHandler" for h in http._opener.handlers
            ))


class TestEndToEnd(unittest.TestCase):
    def test_fixture_runs_through_analyse_and_render(self):
        raw = pipeline.load_json(os.path.join(HERE, "fixtures", "raw_sample.json"))
        analysis = pipeline.analyse(raw, MODEL)
        self.assertEqual(len(analysis["categories"]), 5)
        self.assertTrue(any(r["rank"] == 1 for r in analysis["ips"]))
        markdown = report.render_markdown(analysis)
        self.assertIn("SYNTHETIC FIXTURE RUN", markdown)
        self.assertIn("Player Scale", markdown)
        # Every IP with an estimate must carry a method and a source.
        for detail in analysis["ip_detail"].values():
            est = detail.get("estimate")
            if est:
                self.assertTrue(est["method"])
                self.assertTrue(est["sources"])
                self.assertLessEqual(est["mau_low"], est["mau_mid"])
                self.assertGreaterEqual(est["mau_high"], est["mau_mid"])

    def test_csv_columns_stay_stable(self):
        raw = pipeline.load_json(os.path.join(HERE, "fixtures", "raw_sample.json"))
        analysis = pipeline.analyse(raw, MODEL)
        with tempfile.TemporaryDirectory() as tmp:
            paths = report.write_csvs(analysis, tmp)
            self.assertEqual(len(paths), 3)
            with open(paths[0], encoding="utf-8") as fh:
                header = fh.readline().strip().split(",")
            self.assertIn("player_scale_mid", header)
            self.assertIn("units_sold_source", header)

    def test_verified_only_drops_unverified_manual_figures(self):
        raw = pipeline.load_json(os.path.join(HERE, "fixtures", "raw_sample.json"))
        lenient = pipeline.analyse(raw, MODEL, allow_unverified=True)
        strict = pipeline.analyse(raw, MODEL, allow_unverified=False)
        minecraft_lenient = lenient["ip_detail"]["minecraft"]["estimate"]
        minecraft_strict = strict["ip_detail"]["minecraft"]["estimate"]
        self.assertEqual(minecraft_lenient["method"], "official_mau")
        # With verified=false figures ignored, Minecraft (not on Steam) loses its signal.
        self.assertIsNone(minecraft_strict)


if __name__ == "__main__":
    unittest.main()
