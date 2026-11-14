"""Navigational warnings that announce launch hazard areas and space-debris drop zones.

Two official sources, each read as its issuer publishes it:

* NGA (US National Geospatial-Intelligence Agency) Maritime Safety Information: the in-force daily memoranda for
  HYDROPAC, HYDROLANT, HYDROARC, NAVAREA IV and NAVAREA XII. NGA's MSI API (msi.nga.mil/api/publications/
  broadcast-warn) has answered 503 "MSI IS CURRENTLY UNDER MAINTENANCE" since at least 6 Nov 2026; its
  maintenance page still serves these memoranda as plain text, refreshed daily. When the API returns, read it.
* Japan Coast Guard (Hydrographic and Oceanographic Department), coordinator of NAVAREA XI, which covers the
  western North Pacific, including the waters off China where Chinese launches drop stages. The list comes from
  warnings.cgi (XML; Japanese titles) and each warning's text, in English, from disp_warnings.cgi. Japan's
  Government Standard Terms of Use 2.0 apply (commercial use allowed, source credited, edits marked).

Only warnings whose text names rocket launching, space debris or reentry are kept; missile firings and
everything else are left out. Each warning is reported as its issuer wrote it: the areas, the time windows and
the cancel time. Orbit does not say which launch a warning is for; the page only shows, as a time coincidence,
scheduled launches whose NET falls in one of a warning's windows.

The same area is often broadcast by more than one coordinator (HYDROPAC rebroadcasts NAVAREA XI and XII
warnings). Warnings with the same windows and the same vertices (within 0.05 degrees) are grouped as one area
with every broadcast listed; vertices that differ between broadcasts are counted, not corrected.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

NGA_BASE = "https://msi.nga.mil/apology_objects/"
NGA_MEMOS = {
    "HYDROPAC": NGA_BASE + "DailyMemPAC.txt",
    "HYDROLANT": NGA_BASE + "DailyMemLAN.txt",
    "HYDROARC": NGA_BASE + "DailyMemARC.txt",
    "NAVAREA IV": NGA_BASE + "DailyMemIV.txt",
    "NAVAREA XII": NGA_BASE + "DailyMemXII.txt",
}
NGA_PAGE = "https://msi.nga.mil/NavWarnings"
# NGA's MSI API, read first. It has answered 503 since at least 6 Nov 2026, and before that it served a set frozen at
# May 2024 (Cordon's note), so a list whose newest warning is over STALE_DAYS old is passed over for the memoranda.
NGA_API = "https://msi.nga.mil/api/publications/broadcast-warn?output=json&status=active"
NGA_AREA_CODES = {"P": "HYDROPAC", "A": "HYDROLANT", "C": "HYDROARC", "4": "NAVAREA IV", "12": "NAVAREA XII"}
STALE_DAYS = 7
JCG_LIST = "https://www1.kaiho.mlit.go.jp/TUHO/keiho/cgi/warnings.cgi?YEAR={year}&TYPE=NAVAREA11&LANG=JP"
JCG_MSG = "https://www1.kaiho.mlit.go.jp/TUHO/keiho/cgi/disp_warnings.cgi?TYPE=NAVAREA11&TANA={tana}&LANG=JP"
JCG_PAGE = "https://www1.kaiho.mlit.go.jp/TUHO/keiho/navarea11.html"
# Not read since 14 Nov 2026: www1.kaiho.mlit.go.jp/robots.txt disallows /TUHO/ for every crawler but the National Diet
# Library's, and the list and every message sit under it. The parsers stay for a source that permits reading.
JCG_READ = False
JCG_OFF = ("not read: the Japan Coast Guard's robots.txt disallows /TUHO/ for automated readers (seen 14 Nov 2026); "
           "NAVAREA XI shows only where NGA rebroadcasts it")


class SourceOff(Exception):
    """A source Orbit has stopped reading on purpose."""
# Japanese title words for a launch, space debris or reentry; the English text is checked again after.
JCG_TITLE = re.compile("ロケット|宇宙|再突入")
JST = timezone(timedelta(hours=9))

HAZARD = re.compile(r"ROCKET LAUNCH\w*(?: SUSPENDED)?|SPACE DEBRIS|SPACE VEHICLE|SPACECRAFT|RE-?ENTRY")
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
MON = "(" + "|".join(MONTHS) + ")"
COORD = re.compile(r"(\d{1,2})-(\d{2}(?:\.\d+)?)\s?([NS])[,\s]+(\d{1,3})-(\d{2}(?:\.\d+)?)\s?([EW])")
PAIR = re.compile(r"\b(\d{2})(\d{2})(\d{2})Z TO (\d{2})(\d{2})(\d{2})Z\b")
DAILY = re.compile(r"\b(\d{2})(\d{2})Z TO (\d{2})(\d{2})Z (?:COMMENCING )?DAILY (\d{1,2})(?: " + MON + r")?"
                   r" (?:THRU|THR|TO) (\d{1,2}) " + MON)
DAILY_AND = re.compile(r"\b(\d{2})(\d{2})Z TO (\d{2})(\d{2})Z (?:COMMENCING )?DAILY ((?:\d{1,2}(?:, | AND ))+\d{1,2}) "
                       + MON)
CANCEL_THIS = re.compile(r"CANCEL THIS MSG (\d{2})(\d{2})(\d{2})Z " + MON + r"(?: (\d{2}))?")
CANCEL_OTHER = re.compile(r"CANCEL (?!THIS)((?:HYDROPAC|HYDROLANT|HYDROARC|NAVAREA [IVX]+) )?(\d{3,4})/(\d{2})")
AREA_LABEL = re.compile(r"(?m)^\s*([A-Z])\.\s+")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _year_for(month: int, issued: datetime) -> int:
    """A window's year: the warning's own year, or the next one for a January window issued in December."""
    return issued.year + 1 if month < issued.month - 6 else issued.year


def _when(day: int, hh: int, mm: int, month: int, issued: datetime) -> datetime:
    return datetime(_year_for(month, issued), month, day, hh, mm, tzinfo=timezone.utc)


def parse_windows(text: str, issued: datetime) -> tuple[list[dict], str]:
    """Time windows in a warning's own words, as UTC [start, end] pairs, and how they were written:
    'single', 'alternates' (the first window, then the issuer's alternates), 'daily', or '' if none parsed."""
    t = re.sub(r"\s+", " ", text)
    out: list[dict] = []
    mode = ""
    for m in DAILY.finditer(t):
        h0, m0, h1, m1, d0, mon0, d1, mon1 = m.groups()
        end_month = MONTHS.index(mon1) + 1
        start_month = MONTHS.index(mon0) + 1 if mon0 else end_month
        day = _when(int(d0), 0, 0, start_month, issued)
        last = _when(int(d1), 0, 0, end_month, issued)
        while day <= last and len(out) < 62:
            s = day.replace(hour=int(h0), minute=int(m0))
            e = day.replace(hour=int(h1), minute=int(m1))
            if e <= s:
                e += timedelta(days=1)
            out.append({"start": _iso(s), "end": _iso(e)})
            day += timedelta(days=1)
        mode = "daily"
    for m in DAILY_AND.finditer(t):
        h0, m0, h1, m1, days, mon = m.groups()
        for d in re.findall(r"\d{1,2}", days):
            s = _when(int(d), int(h0), int(m0), MONTHS.index(mon) + 1, issued)
            e = s.replace(hour=int(h1), minute=int(m1))
            if e <= s:
                e += timedelta(days=1)
            out.append({"start": _iso(s), "end": _iso(e)})
        mode = "daily"
    pairs = list(PAIR.finditer(t))
    for m in pairs:
        mon = re.compile(r"\b" + MON + r"\b").search(t, m.end())
        if not mon:
            continue
        month = MONTHS.index(mon.group(1)) + 1
        d0, h0, n0, d1, h1, n1 = (int(g) for g in m.groups())
        s = _when(d0, h0, n0, month, issued)
        e = _when(d1, h1, n1, month, issued)
        if e <= s:  # the window ends in the next month: the month named is the end's
            s = _when(d0, h0, n0, month - 1 or 12, issued)
        out.append({"start": _iso(s), "end": _iso(e)})
    if pairs:
        mode = "alternates" if "ALTERNATE" in t else ("single" if len(pairs) == 1 and mode != "daily" else mode or "list")
    out.sort(key=lambda w: w["start"])
    seen, uniq = set(), []
    for w in out:
        k = (w["start"], w["end"])
        if k not in seen:
            seen.add(k)
            uniq.append(w)
    return uniq, mode


def parse_coords(text: str) -> list[list[float]]:
    """Every vertex as [lon, lat], longitudes unwrapped so an area across 180 degrees stays one shape."""
    pts = []
    for m in COORD.finditer(text):
        la = int(m.group(1)) + float(m.group(2)) / 60
        lo = int(m.group(4)) + float(m.group(5)) / 60
        la = -la if m.group(3) == "S" else la
        lo = -lo if m.group(6) == "W" else lo
        if pts:
            while lo - pts[-1][0] > 180:
                lo -= 360
            while pts[-1][0] - lo > 180:
                lo += 360
        pts.append([round(lo, 4), round(la, 4)])
    return pts


def parse_body(text: str, issued: datetime) -> dict | None:
    """One warning's text -> hazard, regions, areas (each with its own windows when the text gives them), the
    message-level windows, its cancel time and the warnings it cancels. None if it is not about a launch."""
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    full = "\n".join(lines)
    hz = HAZARD.search(full)
    if not hz:
        return None
    regions = []
    for ln in lines:
        if not ln:
            continue
        if ln.startswith("1.") or HAZARD.search(ln) or re.match(r"\d{4}Z|\d{6}Z", ln):
            break
        regions.append(ln.rstrip("."))
    expires = None
    cm = CANCEL_THIS.search(full)
    if cm:
        d, h, n, mon, yy = cm.groups()
        exp_issued = issued.replace(year=2000 + int(yy)) if yy else issued
        expires = _iso(_when(int(d), int(h), int(n), MONTHS.index(mon) + 1, exp_issued))
    cancels = [((m.group(1) or "").strip() + " " + m.group(2) + "/" + m.group(3)).strip()
               for m in CANCEL_OTHER.finditer(full)]
    # Body of the hazard paragraph: from the hazard words to the next numbered paragraph or the cancel line.
    start = hz.start()
    stop = re.compile(r"(?m)^\d\.\s|CANCEL ").search(full, hz.end())
    para = full[start: stop.start() if stop else len(full)]
    labels = list(AREA_LABEL.finditer(para))
    blocks = []
    if labels:
        head = para[: labels[0].start()]
        for i, lb in enumerate(labels):
            blocks.append((lb.group(1), para[lb.end(): labels[i + 1].start() if i + 1 < len(labels) else len(para)]))
    else:
        head, blocks = para, [("", para)]
    windows, mode = parse_windows(head, issued)
    areas = []
    for label, btxt in blocks:
        coords = parse_coords(btxt)
        own, own_mode = parse_windows(btxt, issued) if labels else ([], "")
        if not coords:
            continue
        area = {"label": label, "coords": coords}
        if own:
            area["windows"], area["window_mode"] = own, own_mode
        areas.append(area)
    if not windows:  # every area carries its own windows (NAVAREA XII style): the message's are their union
        by_start: dict[str, str] = {}  # areas opening together are one window; it ends when the last area closes
        for a in areas:
            for w in a.get("windows", []):
                by_start[w["start"]] = max(by_start.get(w["start"], ""), w["end"])
        windows = [{"start": k, "end": v} for k, v in sorted(by_start.items())]
        modes = {a.get("window_mode") for a in areas if a.get("window_mode")}
        mode = modes.pop() if len(modes) == 1 else ("alternates" if "ALTERNATE" in para else "list")
    window_text = re.split(r"\bIN AREAS? BOUND|\bAREAS? BOUNDED", re.sub(r"\s+", " ", head))[0].strip(" ,:")
    window_text = window_text[len(hz.group(0)):].strip(" ,.:") if window_text.startswith(hz.group(0)) else window_text
    return {"hazard": hz.group(0).lower().replace("re-entry", "reentry"),
            "regions": regions, "areas": areas, "windows": windows, "window_mode": mode,
            "window_text": window_text[:300], "expires": expires, "cancels": cancels}


# --- NGA daily memoranda ------------------------------------------------------------------------------------------

MEMO_HEAD = re.compile(r"^(HYDROPAC|HYDROLANT|HYDROARC|NAVAREA [IVX]+) IN FORCE AS OF (\d{2})(\d{2})(\d{2})Z " + MON)
DTG = re.compile(r"^(\d{2})(\d{2})(\d{2})Z " + MON + r" (\d{2})$")
MSG_ID = re.compile(r"^(HYDROPAC|HYDROLANT|HYDROARC|NAVAREA [IVX]+) (\d{1,4})/(\d{2})\.?$")


def parse_memo(body: bytes, area: str, now: datetime) -> dict:
    """An NGA in-force memorandum -> {"as_of", "in_force", "warnings": [...]} (launch-related only)."""
    text = body.decode("utf-8", errors="replace").replace("\r", "")
    lines = text.split("\n")
    head = next((MEMO_HEAD.match(ln.strip()) for ln in lines[:20] if MEMO_HEAD.match(ln.strip())), None)
    if not head:
        raise ValueError(f"not an NGA in-force memorandum for {area}: {text[:120]!r}")
    _, d, h, n, mon = head.groups()
    month = MONTHS.index(mon) + 1
    year = now.year - 1 if month > now.month + 6 else now.year
    as_of = datetime(year, month, int(d), int(h), int(n), tzinfo=timezone.utc)
    starts = []
    for i in range(len(lines) - 1):
        dm, im = DTG.match(lines[i].strip()), MSG_ID.match(lines[i + 1].strip())
        if dm and im:
            starts.append((i, dm, im))
    out = []
    for k, (i, dm, im) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        dd, hh, nn, mon, yy = dm.groups()
        issued = datetime(2000 + int(yy), MONTHS.index(mon) + 1, int(dd), int(hh), int(nn), tzinfo=timezone.utc)
        body_text = "\n".join(lines[i + 2: end]).strip()
        parsed = parse_body(body_text, issued)
        if not parsed:
            continue
        wid = f"{im.group(1)} {int(im.group(2))}/{im.group(3)}"
        parsed["cancels"] = [c if " " in c else f"{im.group(1)} {c}" for c in parsed["cancels"]]
        out.append({"id": wid, "issuer": "nga", "coordinator": im.group(1), "issued": _iso(issued),
                    "url": NGA_PAGE, "text": body_text[:2500], **parsed})
    return {"as_of": _iso(as_of), "in_force": len(starts), "warnings": out}


API_DATE = re.compile(r"^(\d{2})(\d{2})(\d{2})Z\s+" + MON + r"\s+(\d{4})$")


def parse_api(doc: dict, now: datetime) -> dict:
    """NGA's broadcast-warn JSON -> {"newest", "memos": {area: {"in_force", "warnings"}}}, launch-related warnings
    only, in the same form as parse_memo. Raises when nothing is listed or the newest warning is over STALE_DAYS old:
    NGA issues warnings every day, so an old list is a frozen copy, never a quiet sea."""
    memos = {a: {"in_force": 0, "warnings": []} for a in NGA_MEMOS}
    newest = None
    for w in doc.get("broadcast-warn", []) or []:
        area = NGA_AREA_CODES.get(str(w.get("navArea") or "").strip().upper())
        m = API_DATE.match(re.sub(r"\s+", " ", str(w.get("issueDate") or "")).strip().upper())
        if not area or not m:
            continue
        dd, hh, nn, mon, yyyy = m.groups()
        issued = datetime(int(yyyy), MONTHS.index(mon) + 1, int(dd), int(hh), int(nn), tzinfo=timezone.utc)
        newest = issued if newest is None else max(newest, issued)
        memos[area]["in_force"] += 1
        text = str(w.get("text") or "").replace("\r", "").strip()
        parsed = parse_body(text, issued)
        if not parsed:
            continue
        wid = f"{area} {int(w.get('msgNumber'))}/{int(w.get('msgYear')) % 100:02d}"
        parsed["cancels"] = [c if " " in c else f"{area} {c}" for c in parsed["cancels"]]
        memos[area]["warnings"].append({"id": wid, "issuer": "nga", "coordinator": area, "issued": _iso(issued),
                                        "url": NGA_PAGE, "text": text[:2500], **parsed})
    if newest is None:
        raise ValueError("no warnings in the API's list")
    if newest < now - timedelta(days=STALE_DAYS):
        raise ValueError(f"stale: newest warning issued {newest:%Y-%m-%d}")
    return {"newest": _iso(newest), "memos": memos}


# --- Japan Coast Guard, NAVAREA XI -------------------------------------------------------------------------------

def parse_jcg_list(body: bytes) -> list[dict]:
    root = ET.fromstring(body)
    out = []
    for m in root.findall("Member"):
        out.append({"number": (m.findtext("number") or "").strip(), "tana": (m.findtext("tana") or "").strip(),
                    "title": (m.findtext("title") or "").strip(), "category": (m.findtext("categoly") or "").strip()})
    return out


def jcg_wanted(items: list[dict]) -> list[dict]:
    return [x for x in items if JCG_TITLE.search(x["title"]) and x["tana"]]


def parse_jcg_message(body: bytes, item: dict) -> dict | None:
    raw = body.decode("utf-8", errors="replace")
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    text = html.unescape(re.sub(r"<[^>]+>", "", raw))
    hm = re.search(r"NO\.(\d{2})-(\d{3,4})\s*発表日時：(\d{4})年(\d{2})月(\d{2})日\s*(\d{1,2})時", text)
    if not hm:
        raise ValueError(f"NAVAREA XI message {item.get('tana')} has no header")
    yy, num, y, mo, d, h = hm.groups()
    issued = datetime(int(y), int(mo), int(d), int(h), tzinfo=JST).astimezone(timezone.utc)  # stamped in JST
    body_text = "\n".join(ln.strip() for ln in text[hm.end():].split("\n") if ln.strip())
    parsed = parse_body(body_text, issued)
    if not parsed:
        return None
    parsed["cancels"] = [c if " " in c else f"NAVAREA XI {c}" for c in parsed["cancels"]]
    return {"id": f"NAVAREA XI {num}/{yy}", "issuer": "jcg", "coordinator": "NAVAREA XI", "issued": _iso(issued),
            "url": JCG_MSG.format(tana=item["tana"]), "title_ja": item["title"], "text": body_text[:2500],
            **parsed}


# --- grouping and filtering ----------------------------------------------------------------------------------------

def _norm_lon(lo: float) -> float:
    return ((lo + 180) % 360) - 180


def _verts(w: dict) -> list[tuple[float, float]]:
    return [(round(_norm_lon(lo), 2), round(la, 2)) for a in w["areas"] for lo, la in a["coords"]]


def _same_area(a: dict, b: dict) -> tuple[bool, int]:
    va, vb = _verts(a), _verts(b)
    if not va or len(va) != len(vb):
        return False, 0
    if [(w["start"], w["end"]) for w in a["windows"]] != [(w["start"], w["end"]) for w in b["windows"]]:
        return False, 0
    diff = sum(1 for p, q in zip(va, vb) if abs(p[0] - q[0]) > 0.05 or abs(p[1] - q[1]) > 0.05)
    return diff <= max(1, len(va) // 5), diff


def current(warnings: list[dict], now: datetime) -> list[dict]:
    """Drop warnings already cancelled by their own cancel time or with every window over."""
    t = _iso(now)
    keep = []
    for w in warnings:
        if w.get("expires") and w["expires"] <= t:
            continue
        if w["windows"] and all(x["end"] <= t for x in w["windows"]):
            continue
        keep.append(w)
    return keep


def group(warnings: list[dict]) -> list[dict]:
    """One entry per hazard area, with every broadcast of it. NAVAREA XI (the coordinator for the western
    Pacific) is listed first when it is one of them, then NAVAREA IV/XII, then HYDROPAC and the others."""
    rank = {"NAVAREA XI": 0, "NAVAREA IV": 1, "NAVAREA XII": 1}
    ordered = sorted(warnings, key=lambda w: (rank.get(w["coordinator"], 2), w["issued"]))
    groups: list[dict] = []
    for w in ordered:
        for g in groups:
            same, diff = _same_area(g["lead"], w)
            if same:
                g["broadcasts"].append(w)
                g["vertex_differences"] = max(g["vertex_differences"], diff)
                break
        else:
            groups.append({"lead": w, "broadcasts": [w], "vertex_differences": 0})
    out = []
    for g in groups:
        lead = g["lead"]
        first = lead["windows"][0]["start"] if lead["windows"] else (lead.get("expires") or lead["issued"])
        out.append({
            "key": re.sub(r"[^a-z0-9]+", "-", lead["id"].lower()).strip("-"),
            "hazard": lead["hazard"], "regions": lead["regions"], "areas": lead["areas"],
            "windows": lead["windows"], "window_mode": lead["window_mode"], "window_text": lead["window_text"],
            "expires": lead["expires"], "cancels": sorted({c for b in g["broadcasts"] for c in b["cancels"]}),
            "broadcasts": [{"id": b["id"], "issuer": b["issuer"], "issued": b["issued"], "url": b["url"],
                            **({"title_ja": b["title_ja"]} if b.get("title_ja") else {})} for b in g["broadcasts"]],
            "vertex_differences": g["vertex_differences"], "first_window": first,
            "text": lead["text"],
        })
    out.sort(key=lambda g: g["first_window"])
    return out
