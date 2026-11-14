"""Space-Track.org client for the manoeuvre lane (orbit-2.4, 14 Nov 2026).

Space-Track's own rules (space-track.org/documentation, read 14 Nov 2026):
  - "Limit API queries to less than 30 requests per 1 minute(s) and 300 requests per 1 hour(s)."
  - GP: once an hour, at "a minute that is not at the top or bottom of the hour".
  - GP_HISTORY: "Once you download an object's history, you need to store it on your own servers; do not
    download it again." It is not for current element sets; those come from GP.
  - "USSPACECOM has provided express blanket approval for transfer/redistribution of basic SSA data and
    services ... conditioned on appropriate citation." "Publications of analysis based on USSPACECOM data also
    require appropriate citations."

So a run makes at most four requests (log in, GP for the watch list, GP_HISTORY once for objects that have no
stored history yet, log out), at least 2.5 s apart; never within an hour of the last GP query; and never at
:57-:03 or :27-:33 (it waits for a clear minute instead, plus a random 0-60 s).

Credentials and the watch list are Tom's: SPACETRACK_IDENTITY and SPACETRACK_PASSWORD, and ORBIT_WATCH (NORAD
numbers, comma-separated), from the environment (GitHub secrets in the workflow) or, locally, from the
git-ignored files `.env` and `private/watch.txt`. Nothing here prints or stores them, and the query URLs, which
name the watched objects, are never written to the published snapshot.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.space-track.org"
LOGIN = BASE + "/ajaxauth/login"
LOGOUT = BASE + "/ajaxauth/logout"
QUERY = BASE + "/basicspacedata/query/class/{cls}/NORAD_CAT_ID/{ids}{extra}/orderby/EPOCH%20asc/format/json"
REDACTED = BASE + "/basicspacedata/query/class/{cls}/ (watch list withheld)"
GAP_S = 2.5          # seconds between requests: 24 a minute at most, under the 30 allowed
MIN_GP_GAP_S = 3600  # GP once an hour
HISTORY_DAYS = 60    # first reading of an object: its last 60 days, stored and never asked for again
BLOCKED_MINUTES = set(range(57, 60)) | set(range(0, 4)) | set(range(27, 34))


class NotReady(Exception):
    """The lane cannot run on purpose (no credentials, no watch list, an hour not yet passed)."""


def _dotenv(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():  # -sig: Notepad may add a byte-order mark
            m = re.match(r"\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m and not line.lstrip().startswith("#"):
                out[m.group(1)] = m.group(2).strip('"').strip("'")
    return out


def credentials(root: Path) -> tuple[str, str] | None:
    env = {**_dotenv(Path(root) / ".env"), **os.environ}
    ident, pw = env.get("SPACETRACK_IDENTITY"), env.get("SPACETRACK_PASSWORD")
    return (ident, pw) if ident and pw else None


def watch_list(root: Path) -> list[int]:
    raw = os.environ.get("ORBIT_WATCH")
    if not raw:
        p = Path(root) / "private" / "watch.txt"
        raw = p.read_text(encoding="utf-8") if p.exists() else ""
    ids = []
    for line in raw.replace(",", "\n").splitlines():
        tok = line.split("#", 1)[0].strip()  # private/watch.txt may carry a note after '#'; never read further
        if tok.isdigit() and int(tok) not in ids:
            ids.append(int(tok))
    return ids


def wait_for_clear_minute(now=None, sleep=time.sleep, rng=random.random) -> float:
    """Sleep out a blocked minute (top or bottom of the hour), then a random 0-60 s. Returns seconds slept."""
    t = now or datetime.now(timezone.utc)
    slept = 0.0
    m, s = t.minute, t.second
    if m in BLOCKED_MINUTES:
        nxt = next(k for k in range(1, 61) if (m + k) % 60 not in BLOCKED_MINUTES)
        slept = nxt * 60 - s
    slept += rng() * 60
    sleep(slept)
    return slept


class Client:
    """A logged-in session. `opener` and `sleep` are replaceable for tests."""

    def __init__(self, identity: str, password: str, opener=None, sleep=time.sleep, timeout: int = 120):
        self._cred = {"identity": identity, "password": password}
        self._opener = opener or urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self._sleep, self._timeout, self._last = sleep, timeout, None
        self.requests = 0
        self.last_body = b""

    def _open(self, url: str, data: bytes | None = None) -> bytes:
        if self._last is not None:
            wait = GAP_S - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "research-collector/1.0"})
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                return resp.read()
        finally:
            self._last = time.monotonic()
            self.requests += 1

    def login(self) -> None:
        body = self._open(LOGIN, urllib.parse.urlencode(self._cred).encode("ascii"))
        if b"Failed" in body:  # Space-Track answers {"Login":"Failed"}; the reply itself is not kept
            raise PermissionError("Space-Track refused the login")

    def logout(self) -> None:
        try:
            self._open(LOGOUT)
        except Exception:
            pass

    def query(self, cls: str, ids: list[int], extra: str = "") -> list[dict]:
        url = QUERY.format(cls=cls, ids=",".join(str(i) for i in sorted(ids)), extra=extra)
        body = self.last_body = self._open(url)
        doc = json.loads(body or b"[]")
        if isinstance(doc, dict):  # an error object, e.g. {"error": "..."}
            raise RuntimeError(f"Space-Track {cls}: {str(doc)[:160]}")
        return doc


def history_extra(days: int = HISTORY_DAYS) -> str:
    return f"/EPOCH/>now-{days}"  # as in Space-Track's own examples (">now-10")
