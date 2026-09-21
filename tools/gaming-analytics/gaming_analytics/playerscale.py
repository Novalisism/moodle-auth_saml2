"""Player-scale estimator - the answer to "where does Player Scale come from?".

Design rules, in order of importance:

1. Never invent a number. Every estimate is derived from at least one fetched
   or explicitly cited input, and carries those inputs in `inputs`.
2. Never output a point estimate alone. Everything is (low, mid, high).
3. Say which method produced it. A figure derived from a publisher-disclosed
   MAU and one derived from a SteamSpy owners band are not the same kind of
   object, and the report must not present them as if they were.
4. Cross-check. When two independent methods disagree by more than
   `DISAGREEMENT_FACTOR`, the confidence is downgraded and the disagreement is
   reported rather than hidden by averaging.

METHODOLOGY.md is the prose version of this module; keep them in sync.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

DISAGREEMENT_FACTOR = 2.5


def parse_as_of(value: Optional[str]) -> Optional[dt.date]:
    """Accept 2024, 2024-02, 2024-02-15 (and ISO timestamps)."""
    if not value:
        return None
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return dt.datetime.strptime(text[: len(fmt.replace("%Y", "2024"))], fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class Estimate:
    ip_id: str
    method: str
    mau_low: float
    mau_mid: float
    mau_high: float
    inputs: Dict[str, Any] = field(default_factory=dict)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    as_of: Optional[str] = None
    confidence: str = "medium"
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ip_id": self.ip_id,
            "method": self.method,
            "mau_low": round(self.mau_low),
            "mau_mid": round(self.mau_mid),
            "mau_high": round(self.mau_high),
            "inputs": self.inputs,
            "sources": self.sources,
            "as_of": self.as_of,
            "confidence": self.confidence,
            "notes": self.notes,
        }


class PlayerScaleEstimator:
    def __init__(self, model: Dict[str, Any], today: Optional[dt.date] = None):
        self.model = model
        self.today = today or dt.date.today()

    # ------------------------------------------------------------- helpers
    def _band(self, method: str) -> float:
        return float(self.model["method_band"].get(method, 2.0))

    def _platform_multiplier(self, platforms: List[str]) -> float:
        cfg = self.model["platform_multipliers"]
        total = 0.0
        for platform in platforms or ["pc"]:
            total += float(cfg.get(platform, 0.0))
        return min(max(total, 1.0), float(cfg.get("cap", 6.0)))

    def _freshness_penalty(self, as_of: Optional[str]) -> float:
        """>1.0 widens the band for a stale input."""
        cfg = self.model["freshness"]
        date = parse_as_of(as_of)
        if date is None:
            return 1.0 + float(cfg["max_penalty"]) / 2
        age_days = max(0, (self.today - date).days)
        if age_days <= int(cfg["full_confidence_days"]):
            return 1.0
        extra_years = (age_days - int(cfg["full_confidence_days"])) / 365.25
        return 1.0 + min(extra_years * float(cfg["penalty_per_year"]), float(cfg["max_penalty"]))

    def _apply_band(self, mid: float, method: str, as_of: Optional[str]) -> tuple:
        band = self._band(method) * self._freshness_penalty(as_of)
        return mid / band, mid * band

    @staticmethod
    def _lifetime_rate(model: Dict[str, Any], game_type: str) -> Dict[str, float]:
        table = model["lifetime_to_mau"]
        if game_type not in table:
            log.warning("unknown game_type %r - falling back to live_service", game_type)
        return table.get(game_type, table["live_service"])

    # ------------------------------------------------------------- methods
    # How much the source itself can be trusted, before staleness is considered.
    SOURCE_GRADE = {
        "official_disclosure": "high",
        "press_report": "medium",
        "third_party_estimate": "low",
    }

    def from_official_mau(self, ip: Dict[str, Any], figure: Dict[str, Any]) -> Estimate:
        mid = float(figure["value"])
        low, high = self._apply_band(mid, "official_mau", figure.get("as_of"))
        penalty = self._freshness_penalty(figure.get("as_of"))
        grade = self.SOURCE_GRADE.get(figure.get("confidence"), "low")
        notes = ["Disclosed MAU used as-is; the band covers staleness, not method error."]
        if penalty > 1.3:
            # A two-year-old official number is not an A-grade current figure.
            grade = {"high": "medium", "medium": "low"}.get(grade, "low")
            notes.append(
                f"Downgraded for age: the figure is from {figure.get('as_of')}, "
                "so it describes the past, not today."
            )
        if grade == "low" and figure.get("confidence") == "third_party_estimate":
            notes.append(
                "Third-party panel estimate, not a publisher figure - publish it as an "
                "estimate with the panel named, never as the company's own number."
            )
        return Estimate(
            ip_id=ip["id"],
            method="official_mau",
            mau_low=low,
            mau_mid=mid,
            mau_high=high,
            inputs={"disclosed_mau": mid, "as_of": figure.get("as_of")},
            sources=[
                {
                    "name": figure.get("source_name"),
                    "url": figure.get("source_url"),
                    "as_of": figure.get("as_of"),
                    "kind": figure.get("confidence"),
                }
            ],
            as_of=figure.get("as_of"),
            confidence=grade,
            notes=notes,
        )

    def from_steam_ccu(self, ip: Dict[str, Any], ccu_record: Dict[str, Any]) -> Estimate:
        ccu = float(ccu_record["concurrent_players"])
        m = self.model
        platforms = ip.get("platforms") or ["pc"]
        plat_mult = self._platform_multiplier(platforms)
        steam_share = float(m["steam_share_of_pc"]["value"])
        # Only discount for non-Steam PC storefronts when the title actually
        # ships on more than Steam; a Steam-exclusive has steam_share = 1.
        pc_share = steam_share if ip.get("pc_multi_store") else 1.0

        def compute(c2d: float, d2m: float) -> float:
            return ccu * c2d * d2m / pc_share * plat_mult

        mid = compute(float(m["ccu_to_dau"]["value"]), float(m["dau_to_mau"]["value"]))
        raw_low = compute(float(m["ccu_to_dau"]["low"]), float(m["dau_to_mau"]["low"]))
        raw_high = compute(float(m["ccu_to_dau"]["high"]), float(m["dau_to_mau"]["high"]))
        band_low, band_high = self._apply_band(mid, "steam_ccu", str(self.today))
        return Estimate(
            ip_id=ip["id"],
            method="steam_ccu",
            mau_low=min(raw_low, band_low),
            mau_mid=mid,
            mau_high=max(raw_high, band_high),
            inputs={
                "steam_concurrent_players": ccu,
                "ccu_to_dau": m["ccu_to_dau"]["value"],
                "dau_to_mau": m["dau_to_mau"]["value"],
                "pc_store_share": pc_share,
                "platform_multiplier": plat_mult,
                "platforms": platforms,
            },
            sources=[
                {
                    "name": ccu_record.get("source"),
                    "url": ccu_record.get("source_url"),
                    "as_of": str(self.today),
                    "kind": "first_party_api",
                }
            ],
            as_of=str(self.today),
            confidence="medium",
            notes=[
                "CCU is a single instantaneous sample - collect at a fixed hour, "
                "or average several samples, before quoting it.",
                "Console/mobile audience is extrapolated from PC, not measured.",
            ],
        )

    def from_steam_owners(self, ip: Dict[str, Any], spy: Dict[str, Any]) -> Estimate:
        rate = self._lifetime_rate(self.model, ip.get("game_type", "live_service"))
        plat_mult = self._platform_multiplier(ip.get("platforms") or ["pc"])
        mid_owners = float(spy.get("owners_mid") or 0)
        low_owners = float(spy.get("owners_low") or mid_owners)
        high_owners = float(spy.get("owners_high") or mid_owners)
        mid = mid_owners * float(rate["value"]) * plat_mult
        low = low_owners * float(rate["low"]) * plat_mult
        high = high_owners * float(rate["high"]) * plat_mult
        return Estimate(
            ip_id=ip["id"],
            method="steam_owners",
            mau_low=low,
            mau_mid=mid,
            mau_high=high,
            inputs={
                "steamspy_owners_low": low_owners,
                "steamspy_owners_high": high_owners,
                "lifetime_to_mau": rate["value"],
                "platform_multiplier": plat_mult,
            },
            sources=[
                {
                    "name": spy.get("source"),
                    "url": spy.get("source_url"),
                    "as_of": str(self.today),
                    "kind": "third_party_estimate",
                }
            ],
            as_of=str(self.today),
            confidence="low",
            notes=["SteamSpy owners is itself an estimate with a wide band."],
        )

    def from_units_sold(self, ip: Dict[str, Any], figure: Dict[str, Any]) -> Estimate:
        rate = self._lifetime_rate(self.model, ip.get("game_type", "single_player"))
        units = float(figure["value"])
        mid = units * float(rate["value"])
        low = units * float(rate["low"])
        high = units * float(rate["high"])
        penalty = self._freshness_penalty(figure.get("as_of"))
        return Estimate(
            ip_id=ip["id"],
            method="units_sold",
            mau_low=low / penalty,
            mau_mid=mid,
            mau_high=high * penalty,
            inputs={
                "units_sold": units,
                "lifetime_to_mau": rate["value"],
                "freshness_penalty": round(penalty, 3),
                "as_of": figure.get("as_of"),
            },
            sources=[
                {
                    "name": figure.get("source_name"),
                    "url": figure.get("source_url"),
                    "as_of": figure.get("as_of"),
                    "kind": figure.get("confidence"),
                }
            ],
            as_of=figure.get("as_of"),
            confidence="low",
            notes=[
                "Lifetime units are cumulative; the active share is the assumption "
                "doing all the work here (see config/model.json lifetime_to_mau)."
            ],
        )

    def from_registered_users(self, ip: Dict[str, Any], figure: Dict[str, Any]) -> Estimate:
        cfg = self.model["registered_to_mau"]
        reg = float(figure["value"])
        mid = reg * float(cfg["value"])
        return Estimate(
            ip_id=ip["id"],
            method="registered_users",
            mau_low=reg * float(cfg["low"]),
            mau_mid=mid,
            mau_high=reg * float(cfg["high"]),
            inputs={"registered_users": reg, "registered_to_mau": cfg["value"]},
            sources=[
                {
                    "name": figure.get("source_name"),
                    "url": figure.get("source_url"),
                    "as_of": figure.get("as_of"),
                    "kind": figure.get("confidence"),
                }
            ],
            as_of=figure.get("as_of"),
            confidence="low",
            notes=["Registered accounts include lapsed, duplicate and bot accounts."],
        )

    # ------------------------------------------------------------ orchestration
    def estimate_ip(self, ip: Dict[str, Any], signals: Dict[str, Any]) -> Dict[str, Any]:
        """signals: {'official_mau':figure, 'steam_ccu':rec, 'steamspy':rec,
        'units_sold':figure, 'registered_users':figure}"""
        candidates: List[Estimate] = []
        if signals.get("official_mau", {}).get("value"):
            candidates.append(self.from_official_mau(ip, signals["official_mau"]))
        if signals.get("steam_ccu", {}).get("concurrent_players"):
            candidates.append(self.from_steam_ccu(ip, signals["steam_ccu"]))
        if signals.get("steamspy", {}).get("owners_mid"):
            candidates.append(self.from_steam_owners(ip, signals["steamspy"]))
        if signals.get("units_sold", {}).get("value"):
            candidates.append(self.from_units_sold(ip, signals["units_sold"]))
        if signals.get("registered_users", {}).get("value"):
            candidates.append(self.from_registered_users(ip, signals["registered_users"]))

        if not candidates:
            return {
                "ip_id": ip["id"],
                "name": ip.get("name"),
                "estimate": None,
                "cross_checks": [],
                "status": "no_signal",
                "missing": self._missing_hint(ip),
            }

        priority = self.model["method_priority"]
        candidates.sort(key=lambda e: priority.index(e.method) if e.method in priority else 99)
        primary, others = candidates[0], candidates[1:]

        disagreement = None
        for other in others:
            if other.mau_mid <= 0 or primary.mau_mid <= 0:
                continue
            ratio = max(primary.mau_mid, other.mau_mid) / min(primary.mau_mid, other.mau_mid)
            if ratio >= DISAGREEMENT_FACTOR:
                disagreement = max(disagreement or 0, ratio)
        if disagreement:
            primary.confidence = "low"
            primary.notes.append(
                f"Methods disagree by {disagreement:.1f}x "
                f"({primary.method} vs {', '.join(o.method for o in others)}); "
                "range widened, do not quote the midpoint without the band."
            )
            primary.mau_low = min([primary.mau_low] + [o.mau_low for o in others])
            primary.mau_high = max([primary.mau_high] + [o.mau_high for o in others])

        return {
            "ip_id": ip["id"],
            "name": ip.get("name"),
            "estimate": primary.as_dict(),
            "cross_checks": [o.as_dict() for o in others],
            "status": "ok",
            "disagreement_factor": round(disagreement, 2) if disagreement else None,
        }

    @staticmethod
    def _missing_hint(ip: Dict[str, Any]) -> str:
        if not ip.get("on_steam"):
            return (
                f"{ip.get('name')} is not on Steam and has no seeded figure. "
                "Add a publisher disclosure to config/manual_figures.json, or buy a "
                "third-party panel (Sensor Tower / Newzoo / Circana) and cite it."
            )
        return "Steam endpoints returned nothing - check the appid in config/catalog.json."

    def estimate_category(
        self, category: Dict[str, Any], ip_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        overlap = float(category.get("overlap_discount", 0.0))
        usable = [r for r in ip_results if r.get("estimate")]
        if not usable:
            return {
                "category_id": category["id"],
                "label": category["label"],
                "status": "no_signal",
                "covered_ips": 0,
                "total_ips": len(ip_results),
            }
        low = sum(r["estimate"]["mau_low"] for r in usable) * (1 - overlap)
        mid = sum(r["estimate"]["mau_mid"] for r in usable) * (1 - overlap)
        high = sum(r["estimate"]["mau_high"] for r in usable) * (1 - overlap)
        weakest = min(
            (r["estimate"]["confidence"] for r in usable),
            key=lambda c: {"high": 0, "medium": 1, "low": 2}.get(c, 2),
            default="low",
        )
        confidences = [r["estimate"]["confidence"] for r in usable]
        coverage = len(usable) / max(1, len(ip_results))
        return {
            "category_id": category["id"],
            "label": category["label"],
            "status": "ok",
            "mau_low": round(low),
            "mau_mid": round(mid),
            "mau_high": round(high),
            "overlap_discount": overlap,
            "covered_ips": len(usable),
            "total_ips": len(ip_results),
            "coverage": round(coverage, 2),
            "confidence": "low" if coverage < 0.6 or "low" in confidences else weakest,
            "methods_used": sorted({r["estimate"]["method"] for r in usable}),
            "notes": [
                f"Sum of per-IP MAU minus a {overlap:.0%} overlap discount for players "
                "active in more than one title in this category.",
                f"{len(usable)}/{len(ip_results)} IPs had a usable signal; uncovered IPs "
                "are listed in the report and make this a FLOOR, not a total.",
            ],
        }


def human(n: Optional[float]) -> str:
    """1234567 -> '1.2M'. Used by the report layer."""
    if n is None:
        return "n/a"
    n = float(n)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= limit:
            value = n / limit
            return f"{value:.1f}{suffix}" if value < 100 else f"{value:.0f}{suffix}"
    return str(int(n))


def log_scale(value: Optional[float]) -> float:
    return math.log10(value) if value and value > 0 else 0.0
