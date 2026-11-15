"""Spaceflight News API (The Space Devs): headlines tied to the launches Orbit lists as scheduled (orbit-2.5).

Links only (Tom, 15 Nov 2026): for each article, the headline, the outlet, the publication time and the link to the
outlet's own page. Summaries are the publishers' text and images are theirs, so neither is kept. One request a run,
filtered to the scheduled launches' Launch Library 2 ids; no request when nothing is scheduled.

Standard-library Python only.
"""
from __future__ import annotations

import json
from urllib.parse import quote, urlsplit

API = "https://api.spaceflightnewsapi.net/v4/articles/"
SITE = "https://www.spaceflightnewsapi.net/"
LIMIT = 100        # the API's page size; one page is read
PER_LAUNCH = 3     # newest headlines kept per launch
TITLE_MAX = 200


def url(launch_ids: list[str]) -> str:
    ids = ",".join(quote(i, safe="-") for i in launch_ids)
    return f"{API}?limit={LIMIT}&ordering=-published_at&launch={ids}"


def _safe_link(u) -> str | None:
    if not isinstance(u, str):
        return None
    try:
        parts = urlsplit(u.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return u.strip()


def _text(s, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def parse(body: bytes, launch_ids: list[str]) -> dict:
    """{"articles": [...], "by_launch": {ll2 id: [article index, ...]}, "count": API count}. Articles are newest
    first, one per link; each keeps only the launch ids Orbit lists. A launch keeps its PER_LAUNCH newest."""
    doc = json.loads(body)
    if not isinstance(doc, dict) or not isinstance(doc.get("results"), list):
        raise ValueError("Spaceflight News API: no results list")
    wanted = set(launch_ids)
    seen, articles = set(), []
    for r in doc["results"]:
        link = _safe_link(r.get("url"))
        title = _text(r.get("title"), TITLE_MAX)
        ids = [l.get("launch_id") for l in r.get("launches") or [] if isinstance(l, dict)]
        ids = [i for i in ids if i in wanted]
        if not link or not title or not ids or link in seen:
            continue
        seen.add(link)
        articles.append({"title": title, "site": _text(r.get("news_site"), 60), "url": link,
                         "published_at": str(r.get("published_at") or "")[:19] + "Z" if r.get("published_at") else None,
                         "launches": ids})
    articles.sort(key=lambda a: a["published_at"] or "", reverse=True)
    by_launch: dict[str, list[int]] = {}
    for n, a in enumerate(articles):
        for i in a["launches"]:
            if len(by_launch.setdefault(i, [])) < PER_LAUNCH:
                by_launch[i].append(n)
    kept = sorted({n for ns in by_launch.values() for n in ns})
    remap = {old: new for new, old in enumerate(kept)}
    return {"articles": [articles[n] for n in kept],
            "by_launch": {i: [remap[n] for n in ns] for i, ns in by_launch.items()},
            "count": doc.get("count")}
