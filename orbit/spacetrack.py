"""Space-Track.org client for the manoeuvre lane (orbit-2.4, 14 Nov 2026).

Space-Track's own rules (space-track.org/documentation, read 14 Nov 2026):
  - "Limit API queries to less than 30 requests per 1 minute(s) and 300 requests per 1 hour(s)."
  - GP: once an hour, at "a minute that is not at the top or bottom of the hour".
  - GP_HISTORY: "Once you download an object's history, you need to store it on your own servers; do not
    download it again." It is not for current element sets; those come from GP.
  - "USSPACECOM has provided express blanket approval for transfer/redistribution of basic SSA data and
    services ... conditioned on appropriate citation." "Publications of analysis based on USSPACECOM data also
    require appropriate citations."

GP once an hour is the account's limit, not a workflow's. Orbit makes three GP queries on the account: the update
run's watch-list query, the GEO region's (`geo_region.py`, workflow geo.yml, from 16 Nov 2026) and, once a day, the
map's rocket bodies and debris (`debrismap.py`, workflow catalog.yml, orbit-2.51); each waits for the other two. Before asking,
`shared_gp_busy` reads the other workflow's recent runs from GitHub's API: a run still going, or its GP step
finished within the hour, and Orbit waits for its next run. If GitHub cannot be read, Orbit waits too: the limit is
kept even when it cannot be checked. The update run checks geo.yml's runs (FOR_MANEUVER), and geo.yml checks the
update run's (FOR_GEO).

Noisefloor (github.com/metacog-osint/noise-floor) logs in with the same account but has made no GP query since
18 Nov 2026 (its GEO page moved here; its Sentinel lane reads GP_HISTORY only, run by hand), so from `orbit-2.21`
Orbit no longer waits for Noisefloor's daily runs. Until then a Noisefloor run in progress made Orbit skip.

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
SHARED_LOOKBACK_S = 3 * 3600              # runs older than this cannot hold a GP query inside the hour
# Orbit's own GEO region query (orbit/geo_region.py, workflow geo.yml, from 16 Nov 2026) and its update run's
# watch-list query (the collect step of update.yml). Each workflow checks the others, never itself.
GEO_RUNS = ("https://api.github.com/repos/metacog-osint/orbit/actions/workflows/geo.yml/runs"
            "?per_page=5&exclude_pull_requests=true")
GEO_STEP = "GEO region (Space-Track)"
UPDATE_RUNS = ("https://api.github.com/repos/metacog-osint/orbit/actions/workflows/update.yml/runs"
               "?per_page=5&exclude_pull_requests=true")
UPDATE_STEP = "Live collection (a failed lane keeps its last good copy and says so on the page)"
# The map's rocket bodies and debris (orbit/debrismap.py, workflow catalog.yml, orbit-2.51): the account's third GP query.
CATALOG_RUNS = ("https://api.github.com/repos/metacog-osint/orbit/actions/workflows/catalog.yml/runs"
                "?per_page=5&exclude_pull_requests=true")
CATALOG_STEP = "Rocket bodies and debris (Space-Track GP, once a day)"   # = debrismap.STEP (a test holds them equal)
GEO = (GEO_RUNS, GEO_STEP, "Orbit's GEO region run")
UPDATE = (UPDATE_RUNS, UPDATE_STEP, "Orbit's update run")
CATALOG = (CATALOG_RUNS, CATALOG_STEP, "Orbit's catalog run")
FOR_MANEUVER = (GEO, CATALOG)    # what the update run's watch-list query waits for
FOR_GEO = (UPDATE, CATALOG)      # what the GEO region query waits for (Noisefloor makes no GP query from 18 Nov 2026)
FOR_DEBRIS = (GEO, UPDATE)       # what the map's rocket-body and debris query waits for


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
        return self.query_path(QUERY.format(cls=cls, ids=",".join(str(i) for i in sorted(ids)), extra=extra), cls)

    def query_path(self, url: str, cls: str = "gp") -> list[dict]:
        """GET a full query URL (the GEO region's gp query selects by mean motion, not by catalog number)."""
        body = self.last_body = self._open(url)
        doc = json.loads(body or b"[]")
        if isinstance(doc, dict):  # an error object, e.g. {"error": "..."}
            raise RuntimeError(f"Space-Track {cls}: {str(doc)[:160]}")
        return doc


def _gh_json(url: str, opener=None, timeout: int = 30):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "research-collector/1.0",
               "X-GitHub-Api-Version": "2022-11-28"}
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = "Bearer " + tok
    with (opener or urllib.request.urlopen)(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
        return json.loads(resp.read())


def _when(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def shared_gp_busy(now: datetime, get=_gh_json, shared=FOR_MANEUVER) -> str | None:
    """Why Orbit must not make a GP query now because of another run's on the same account (None when clear).
    `shared`: (runs URL, step name, label) for each workflow to check; a run of the caller's own workflow must not
    be in it. Any error reading GitHub counts as busy."""
    for runs_url, step_name, label in shared:
        try:
            runs = get(runs_url).get("workflow_runs") or []
            for run in runs:
                started = _when(run.get("run_started_at") or run.get("created_at"))
                if run.get("status") != "completed":
                    return f"{label} {run.get('id')} is {run.get('status')}; its GP query may fall within the hour"
                if started and (now - started).total_seconds() > SHARED_LOOKBACK_S:
                    continue
                for job in get(run["jobs_url"]).get("jobs") or []:
                    for step in job.get("steps") or []:
                        if step.get("name") != step_name or step.get("conclusion") == "skipped":
                            continue
                        done = _when(step.get("completed_at"))
                        if done is None or (now - done).total_seconds() < MIN_GP_GAP_S:
                            return f"{label}'s GP query (run {run.get('id')}) was under an hour ago on the shared account"
        except Exception as exc:
            return f"could not read {label}s from GitHub ({type(exc).__name__}); waiting keeps the hourly limit"
    return None


def history_extra(days: int = HISTORY_DAYS) -> str:
    return f"/EPOCH/>now-{days}"  # as in Space-Track's own examples (">now-10")
