"""TIC's hand-kept alias file, `orbit/data/catalog/aliases.yml` (catalog build step 5, 17 Nov 2026).

Design: the private planning notes, section 3. One claim per entry, reviewed by diff:

- a **name** for one object: `norad` (or `jcat` for an object with no number), `name`, `basis`, `source` (an id
  from doctrine/sources.json), `read`, `evidence` (a list: a link needs evidence beyond a name), and optionally
  `swf_key` (SWF's exact text) with `swf_date` (SWF's date text, when one name means different objects on
  different rows: SWF's "Olymp" is 40258 on the Oct 2014 row and 55841 on the Mar 2023 row). `status` says whether
  the name is the object's `current` or `former` name (left out when not established); a former name may carry
  `until`, the day it stopped being the name;
- a **program**: `swf_key`, `program`, `members` (NORAD numbers), `basis`, `source`, `read`, `evidence`;
- a **swap**: `swap` (the payload name in dispute), `claims` (a list of flow mappings, one per source: `source`,
  `read`, `norad` and `as`, the source's own spelling), `status` (`open`, or `settled` with `settled_by`, a source
  id, and `settled`, its date), `evidence`. It records that sources give one payload name to different numbers;
  nothing is reassigned and feeds keep the numbers ("names never move numbers").

An entry is never edited to change a number: a wrong one gets `withdrawn: <date>` and `reason`, stays in the file,
and is skipped.

The file is a small YAML subset, read with the standard library: a top-level list of mappings; values are quoted
strings, numbers, bare words, flow lists (`[40099, 40100]`), block lists of scalars, or block lists of one-line flow
mappings of scalars (`- {source: space-track, norad: 44422}`). Anything else is an error with its line number,
never a guess.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PATH = Path(__file__).resolve().parent / "data" / "catalog" / "aliases.yml"
SOURCE = "aliases"
BASES = ("declared", "attributed", "catalog")
STATUSES = ("current", "former")
NAME_KEYS = {"norad", "jcat", "name", "basis", "source", "source_ref", "read", "evidence", "added_by", "added",
             "swf_key", "swf_date", "withdrawn", "reason", "note", "status", "until"}
PROGRAM_KEYS = {"swf_key", "program", "members", "basis", "source", "source_ref", "read", "evidence", "added_by",
                "added", "withdrawn", "reason", "note"}
SWAP_KEYS = {"swap", "claims", "status", "settled_by", "settled", "evidence", "added_by", "added", "withdrawn",
             "reason", "note"}
CLAIM_KEYS = {"source", "read", "norad", "as"}
SWAP_STATUSES = ("open", "settled")
_KEY = re.compile(r"^([a-z_][a-z0-9_]*):(?:\s+(.*))?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AliasError(ValueError):
    pass


def _strip_comment(s: str) -> str:
    """Cut a `#` comment that is outside quotes and starts a word."""
    q, i = None, 0
    while i < len(s):
        c = s[i]
        if q:
            if c == "\\" and q == '"':
                i += 1  # skip the escaped character
            elif c == q:
                q = None
        elif c in "\"'":
            q = c
        elif c == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
        i += 1
    return s.rstrip()


def _scalar(t: str, ln: int):
    t = t.strip()
    if not t:
        raise AliasError(f"line {ln}: empty value")
    if t[0] == '"':
        try:
            v = json.loads(t)
        except ValueError:
            raise AliasError(f"line {ln}: bad quoted string {t}") from None
        if not isinstance(v, str):
            raise AliasError(f"line {ln}: bad quoted string {t}")
        return v
    if t[0] == "'":
        if len(t) < 2 or t[-1] != "'":
            raise AliasError(f"line {ln}: bad quoted string {t}")
        return t[1:-1].replace("''", "'")
    if t[0] in "[{&*!|>%@`":
        raise AliasError(f"line {ln}: not in the alias file's YAML subset: {t}")
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if t in ("null", "~"):
        return None
    if t in ("true", "false"):
        return t == "true"
    return t


def _flow_list(t: str, ln: int) -> list:
    inner = t.strip()[1:-1].strip()
    if not inner:
        return []
    parts, buf, q = [], "", None
    for c in inner:
        if q:
            buf += c
            if c == q:
                q = None
        elif c in "\"'":
            q = c
            buf += c
        elif c == ",":
            parts.append(buf)
            buf = ""
        elif c in "[]{}":
            raise AliasError(f"line {ln}: nested lists and mappings are not in the subset")
        else:
            buf += c
    parts.append(buf)
    return [_scalar(p, ln) for p in parts]


def _split_flow(inner: str, ln: int) -> list[str]:
    parts, buf, q = [], "", None
    for c in inner:
        if q:
            buf += c
            if c == q:
                q = None
        elif c in "\"'":
            q = c
            buf += c
        elif c == ",":
            parts.append(buf)
            buf = ""
        elif c in "[]{}":
            raise AliasError(f"line {ln}: nested lists and mappings are not in the subset")
        else:
            buf += c
    parts.append(buf)
    return parts


def _flow_map(t: str, ln: int) -> dict:
    """A one-line flow mapping of scalars: `{source: space-track, norad: 44422, as: "COSMOS 2536"}`."""
    inner = t.strip()[1:-1].strip()
    out: dict = {}
    if not inner:
        return out
    for part in _split_flow(inner, ln):
        m = re.match(r"^\s*([a-z_][a-z0-9_]*):\s+(.+)$", part)
        if not m:
            raise AliasError(f"line {ln}: expected 'key: value' in a flow mapping, got {part.strip()!r}")
        if m.group(1) in out:
            raise AliasError(f"line {ln}: '{m.group(1)}' given twice in one mapping")
        out[m.group(1)] = _scalar(m.group(2), ln)
    return out


def _value(t: str, ln: int):
    t = t.strip()
    if t.startswith("{"):
        if not t.endswith("}"):
            raise AliasError(f"line {ln}: a flow mapping must close on its line")
        return _flow_map(t, ln)
    if t.startswith("["):
        if not t.endswith("]"):
            raise AliasError(f"line {ln}: a flow list must close on its line")
        return _flow_list(t, ln)
    return _scalar(t, ln)


def parse(text: str) -> list[dict]:
    """The alias file's text to its entries, each with `line` (the line its `- ` is on)."""
    entries: list[dict] = []
    cur: dict | None = None
    open_list: str | None = None  # key whose block list is being read
    item_indent = None
    for ln, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise AliasError(f"line {ln}: tabs in indentation")
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()
        if indent == 0:
            if not body.startswith("- "):
                raise AliasError(f"line {ln}: expected '- ' to start an entry")
            cur = {"line": ln}
            entries.append(cur)
            open_list = None
            item_indent = 2
            body = body[2:].strip()
            indent = 2
        if cur is None:
            raise AliasError(f"line {ln}: text before the first entry")
        if body.startswith("- "):
            if open_list is None or indent <= item_indent:
                raise AliasError(f"line {ln}: list item without a key")
            cur[open_list].append(_value(body[2:], ln))
            continue
        if indent != item_indent:
            raise AliasError(f"line {ln}: indentation {indent}, expected {item_indent}")
        m = _KEY.match(body)
        if not m:
            raise AliasError(f"line {ln}: expected 'key: value'")
        key, val = m.group(1), m.group(2)
        if key in cur:
            raise AliasError(f"line {ln}: '{key}' given twice in one entry")
        if val is None or not val.strip():
            cur[key] = []
            open_list = key
        else:
            cur[key] = _value(val, ln)
            open_list = None
    return entries


def _check_date(e: dict, key: str, where: str) -> None:
    if key in e and not (isinstance(e[key], str) and _DATE.match(e[key])):
        raise AliasError(f"{where}: {key} must be a date YYYY-MM-DD, got {e[key]!r}")


def validate(entries: list[dict], source_ids: set[str] | None = None) -> list[dict]:
    """Checks every entry and returns the live ones (withdrawn entries left out). Raises AliasError on the first
    problem, naming the entry's line."""
    live = []
    seen_names: set = set()
    for e in entries:
        where = f"aliases.yml line {e.get('line')}"
        if "swap" in e:
            _check_swap(e, where, source_ids)
            if "withdrawn" not in e:
                k = ("swap", e["swap"].lower())
                if k in seen_names:
                    raise AliasError(f"{where}: the same claim twice")
                seen_names.add(k)
                live.append(e)
            continue
        program = "program" in e
        allowed = PROGRAM_KEYS if program else NAME_KEYS
        extra = set(e) - allowed - {"line"}
        if extra:
            raise AliasError(f"{where}: unknown keys {sorted(extra)}")
        need = ("swf_key", "program", "members", "basis", "source", "read", "evidence") if program else \
            ("name", "basis", "source", "read", "evidence")
        missing = [k for k in need if k not in e]
        if missing:
            raise AliasError(f"{where}: missing {missing}")
        if e["basis"] not in BASES:
            raise AliasError(f"{where}: basis must be one of {BASES}")
        if source_ids is not None and e["source"] not in source_ids:
            raise AliasError(f"{where}: source '{e['source']}' is not in doctrine/sources.json")
        ev = e["evidence"]
        if not (isinstance(ev, list) and ev and all(isinstance(x, str) and x.strip() for x in ev)):
            raise AliasError(f"{where}: evidence must be a list of at least one statement")
        for k in ("read", "added", "withdrawn", "until"):
            _check_date(e, k, where)
        if "withdrawn" in e and not e.get("reason"):
            raise AliasError(f"{where}: a withdrawn entry needs a reason")
        if program:
            m = e["members"]
            if not (isinstance(m, list) and m and all(isinstance(x, int) and x > 0 for x in m)):
                raise AliasError(f"{where}: members must be a list of NORAD numbers")
        else:
            if ("norad" in e) == ("jcat" in e):
                raise AliasError(f"{where}: give exactly one of norad or jcat")
            if "norad" in e and not (isinstance(e["norad"], int) and e["norad"] > 0):
                raise AliasError(f"{where}: norad must be a number")
            if "jcat" in e and not (isinstance(e["jcat"], str) and re.fullmatch(r"[A-Z]\d+", e["jcat"])):
                raise AliasError(f"{where}: jcat must be GCAT's id, e.g. S12345 or A00002")
            if not isinstance(e["name"], str) or not e["name"].strip():
                raise AliasError(f"{where}: name must be text")
            if "swf_date" in e and "swf_key" not in e:
                raise AliasError(f"{where}: swf_date needs swf_key")
            if "status" in e and e["status"] not in STATUSES:
                raise AliasError(f"{where}: status must be one of {STATUSES}")
            if "until" in e and e.get("status") != "former":
                raise AliasError(f"{where}: until needs status: former")
        if "withdrawn" in e:
            continue
        if not program:
            k = (e.get("norad") or e.get("jcat"), e["name"].lower(), e.get("swf_key"), e.get("swf_date"))
            if k in seen_names:
                raise AliasError(f"{where}: the same claim twice")
            seen_names.add(k)
        live.append(e)
    return live


def _check_swap(e: dict, where: str, source_ids: set[str] | None) -> None:
    extra = set(e) - SWAP_KEYS - {"line"}
    if extra:
        raise AliasError(f"{where}: unknown keys {sorted(extra)}")
    missing = [k for k in ("swap", "claims", "status", "evidence") if k not in e]
    if missing:
        raise AliasError(f"{where}: missing {missing}")
    if not isinstance(e["swap"], str) or not e["swap"].strip():
        raise AliasError(f"{where}: swap must be the payload name in dispute")
    claims = e["claims"]
    if not (isinstance(claims, list) and len(claims) >= 2 and all(isinstance(c, dict) for c in claims)):
        raise AliasError(f"{where}: claims must be a list of at least two mappings")
    for c in claims:
        extra = set(c) - CLAIM_KEYS
        missing = sorted(CLAIM_KEYS - set(c))
        if extra or missing:
            raise AliasError(f"{where}: a claim needs exactly {sorted(CLAIM_KEYS)} (extra {sorted(extra)}, "
                             f"missing {missing})")
        if not (isinstance(c["norad"], int) and c["norad"] > 0):
            raise AliasError(f"{where}: a claim's norad must be a number")
        if not (isinstance(c["read"], str) and _DATE.match(c["read"])):
            raise AliasError(f"{where}: a claim's read must be a date YYYY-MM-DD")
        if not isinstance(c["as"], str) or not c["as"].strip():
            raise AliasError(f"{where}: a claim's as must be the source's own text")
        if source_ids is not None and c["source"] not in source_ids:
            raise AliasError(f"{where}: source '{c['source']}' is not in doctrine/sources.json")
    srcs = [c["source"] for c in claims]
    if len(set(srcs)) != len(srcs):
        raise AliasError(f"{where}: one claim per source")
    if len({c["norad"] for c in claims}) < 2:
        raise AliasError(f"{where}: a swap needs claims on at least two numbers")
    if e["status"] not in SWAP_STATUSES:
        raise AliasError(f"{where}: status must be one of {SWAP_STATUSES}")
    if (e["status"] == "settled") != ("settled_by" in e and "settled" in e):
        raise AliasError(f"{where}: a settled swap needs settled_by and settled, an open one neither")
    if "settled_by" in e and source_ids is not None and e["settled_by"] not in source_ids:
        raise AliasError(f"{where}: source '{e['settled_by']}' is not in doctrine/sources.json")
    ev = e["evidence"]
    if not (isinstance(ev, list) and ev and all(isinstance(x, str) and x.strip() for x in ev)):
        raise AliasError(f"{where}: evidence must be a list of at least one statement")
    for k in ("added", "withdrawn", "settled"):
        _check_date(e, k, where)
    if "withdrawn" in e and not e.get("reason"):
        raise AliasError(f"{where}: a withdrawn entry needs a reason")


def is_swap(e: dict) -> bool:
    return "swap" in e


def read_of(e: dict) -> str:
    """The day an entry's claim was read: its `read`, or for a swap the latest of its claims' reads."""
    return max(c["read"] for c in e["claims"]) if is_swap(e) else e["read"]


def swap_record(e: dict) -> dict:
    """A swap entry in the catalog's `swaps` shape: {name, claims: {source: [numbers]}, status}, plus each source's
    own spelling (`as`), the alias file's line (`ref`) and `by: aliases`."""
    out = {"name": e["swap"].lower(), "claims": {c["source"]: [str(c["norad"])] for c in e["claims"]},
           "as": {c["source"]: c["as"] for c in e["claims"]}, "status": e["status"], "by": SOURCE,
           "ref": f"aliases.yml:{e['line']}"}
    if e["status"] == "settled":
        out["settled_by"], out["settled"] = e["settled_by"], e["settled"]
    return out


def load(path: Path | str | None = None, source_ids: set[str] | None = None) -> list[dict]:
    p = Path(path) if path else PATH
    if not p.exists():
        return []
    return validate(parse(p.read_text(encoding="utf-8")), source_ids)


def source_ids(root: Path | str) -> set[str]:
    """The ids in doctrine/sources.json (entries may carry `id` or be keyed by it)."""
    doc = json.loads((Path(root) / "doctrine" / "sources.json").read_text(encoding="utf-8"))
    rows = doc.get("sources", doc)
    if isinstance(rows, dict):
        return set(rows)
    return {r["id"] for r in rows if isinstance(r, dict) and "id" in r}


def key_of(e: dict) -> str:
    """The catalog key an entry names: the NORAD number as text, or GCAT's JCAT for an unnumbered object."""
    return str(e["norad"]) if "norad" in e else e["jcat"]


def name_record(e: dict) -> dict:
    """An alias entry as a catalog name record (source `aliases`; the cited source kept as `cited`)."""
    out = {"value": e["name"], "source": SOURCE, "ref": f"aliases.yml:{e['line']}", "read": e["read"],
           "basis": e["basis"], "cited": e["source"]}
    if e.get("source_ref"):
        out["cited_ref"] = e["source_ref"]
    for k in ("status", "until"):
        if k in e:
            out[k] = e[k]
    return out
