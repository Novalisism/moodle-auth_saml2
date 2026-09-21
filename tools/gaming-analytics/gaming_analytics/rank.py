"""Key-IP ranking - the answer to "rank the Key IPs by sales and YouTube views".

Scores are log10-scaled before normalising: view counts span three orders of
magnitude (a 1.5T-view franchise next to a 200M-view one), and a linear scale
would collapse everything below the leader into an indistinguishable zero.

Missing dimensions are NOT filled with zeros - that would punish an IP for a
data gap. The available weights are renormalised and `coverage` records how
much of the intended weight actually had data behind it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .playerscale import log_scale


def _minmax(values: Dict[str, float]) -> Dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-9:
        return {k: 1.0 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def rank_ips(ip_rows: List[Dict[str, Any]], weights: Dict[str, float]) -> List[Dict[str, Any]]:
    """ip_rows need: ip_id, units_sold, youtube_views_total, player_scale_mid."""
    dims = {
        "sales": "units_sold",
        "youtube_views": "youtube_views_total",
        "player_scale": "player_scale_mid",
    }
    normalised: Dict[str, Dict[str, float]] = {}
    for dim, field in dims.items():
        raw = {
            row["ip_id"]: log_scale(row.get(field))
            for row in ip_rows
            if row.get(field)
        }
        normalised[dim] = _minmax(raw)

    ranked: List[Dict[str, Any]] = []
    for row in ip_rows:
        available = {
            dim: normalised[dim][row["ip_id"]]
            for dim in dims
            if row["ip_id"] in normalised[dim]
        }
        weight_sum = sum(weights.get(dim, 0.0) for dim in available)
        if weight_sum > 0:
            score = sum(weights.get(dim, 0.0) * val for dim, val in available.items()) / weight_sum
        else:
            score = None
        out = dict(row)
        out["score"] = round(score, 4) if score is not None else None
        out["score_components"] = {dim: round(val, 4) for dim, val in available.items()}
        out["score_coverage"] = round(weight_sum / sum(weights.values()), 2) if weights else 0.0
        out["score_missing"] = sorted(set(dims) - set(available))
        ranked.append(out)

    ranked.sort(key=lambda r: (r["score"] is not None, r["score"] or 0), reverse=True)
    rank = 0
    for row in ranked:
        if row["score"] is None:
            row["rank"] = None
            continue
        rank += 1
        row["rank"] = rank
    return ranked


def rank_within_categories(
    ranked_ips: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for row in ranked_ips:
        by_cat.setdefault(row["category_id"], []).append(row)
    for rows in by_cat.values():
        rows.sort(key=lambda r: (r["score"] is not None, r["score"] or 0), reverse=True)
    return by_cat


def key_ip_order(rows: List[Dict[str, Any]], limit: Optional[int] = None) -> str:
    """'CS2 > Fortnite > CoD ...' - the Key IPs cell, now actually ordered."""
    names = [r["name"] for r in rows if r.get("score") is not None]
    unscored = [r["name"] for r in rows if r.get("score") is None]
    if limit:
        names = names[:limit]
    text = " > ".join(names) if names else "-"
    if unscored:
        text += f" (unranked, no data: {', '.join(unscored)})"
    return text
