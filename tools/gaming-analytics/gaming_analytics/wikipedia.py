"""Best-selling units from Wikipedia's maintained sales lists.

Wikipedia is used as an INDEX, not as a source: each row keeps the citation
that Wikipedia itself carries, so the report can point at the publisher's own
filing rather than at an encyclopaedia.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .httpclient import Http, HttpError

log = logging.getLogger(__name__)

API = "https://en.wikipedia.org/w/api.php"
PAGES = [
    "List of best-selling video games",
    "List of best-selling video game franchises",
]

_ROW_SPLIT = re.compile(r"\n\|-")
_CELL_SPLIT = re.compile(r"\n\s*\|")
_LINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_REF = re.compile(r"<ref.*?(?:/>|</ref>)", re.S)
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_TAGS = re.compile(r"<[^>]+>")
_NUM = re.compile(r"([\d][\d,\.]*)\s*(million|billion|m\b|bn\b)?", re.I)
_URL = re.compile(r"url\s*=\s*([^|}\s]+)")


def _clean(cell: str) -> str:
    cell = _REF.sub("", cell)
    cell = _TEMPLATE.sub("", cell)
    cell = _LINK.sub(r"\1", cell)
    cell = _TAGS.sub("", cell)
    return cell.strip().strip("|").strip()


def _unwrap_templates(cell: str) -> str:
    """{{nts|230}} / {{sort|33.10|...}} carry the number - keep it, drop the wrapper."""
    def repl(match):
        args = [a.strip() for a in match.group(1).split("|")[1:]]
        keep = [a for a in args if _NUM.fullmatch(a)]
        return " " + (keep[0] if keep else "") + " "

    prev, text = None, cell
    while prev != text:
        prev = text
        text = re.sub(r"\{\{([^{}]*)\}\}", repl, text)
    return text


def _parse_units(cell: str) -> Optional[int]:
    text = _clean(_unwrap_templates(cell)).lower().replace(" ", "")
    match = _NUM.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = (match.group(2) or "").lower()
    if unit.startswith("b"):
        value *= 1_000_000_000
    elif unit.startswith("m"):
        value *= 1_000_000
    elif value < 10_000:  # bare "230" in a list of millions
        value *= 1_000_000
    return int(value)


class Wikipedia:
    def __init__(self, http: Http):
        self.http = http

    def _wikitext(self, page: str) -> Optional[str]:
        try:
            data = self.http.get_json(
                API,
                {
                    "action": "parse",
                    "page": page,
                    "prop": "wikitext",
                    "format": "json",
                    "formatversion": "2",
                    "redirects": "1",
                },
            )
        except HttpError as exc:
            log.warning("wikipedia fetch failed for %r: %s", page, exc)
            return None
        return ((data.get("parse") or {}).get("wikitext")) or None

    def sales_table(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for page in PAGES:
            text = self._wikitext(page)
            if not text:
                continue
            for raw_row in _ROW_SPLIT.split(text):
                cells = [c for c in _CELL_SPLIT.split(raw_row) if c.strip()]
                if len(cells) < 2:
                    continue
                title, units, ref_url = None, None, None
                for cell in cells[:5]:
                    cleaned = _clean(cell)
                    if title is None and cleaned and not cleaned[0].isdigit():
                        title = cleaned
                        continue
                    if units is None:
                        units = _parse_units(cell)
                    url_match = _URL.search(cell)
                    if url_match and not ref_url:
                        ref_url = url_match.group(1)
                if title and units and units >= 1_000_000:
                    rows.append(
                        {
                            "title": title,
                            "units_sold": units,
                            "citation_url": ref_url,
                            "source": f"Wikipedia: {page}",
                            "source_url": "https://en.wikipedia.org/wiki/"
                            + page.replace(" ", "_"),
                        }
                    )
        if len(rows) < 10:
            log.warning(
                "wikipedia sales parse produced only %d rows - the table layout "
                "probably changed; check gaming_analytics/wikipedia.py",
                len(rows),
            )
        return rows

    def lookup(self, name: str, table: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not name:
            return None
        needle = name.lower().strip()
        exact = [r for r in table if r["title"].lower().strip() == needle]
        if exact:
            return max(exact, key=lambda r: r["units_sold"])
        partial = [r for r in table if needle in r["title"].lower()]
        if partial:
            best = max(partial, key=lambda r: r["units_sold"])
            best = dict(best)
            best["match"] = "partial"
            return best
        return None
